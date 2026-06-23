#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch runner for langchain_app verification.

Recursively scans PDFs under an input directory, runs the full verification
pipeline for each file, and mirrors the input directory structure under an
output root:

- output/local_pdf/<relative-subdir>/<file>.pdf
- output/local_md/<relative-subdir>/<file>.md
- output/local_json/<relative-subdir>/<file>.json
- output/final_reports/<relative-subdir>/Report_<file>.md
- output/reports/<relative-subdir>/*
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from langchain_app.utils.runtime_cache import apply_default_windows_ai_cache_env

apply_default_windows_ai_cache_env()

from langchain_app.core import load_shared_embedder, run_verification
from langchain_app.core.pipeline import PipelineHooks
from langchain_app.utils.config import AppConfig, get_app_config


@dataclass(frozen=True)
class OutputTargets:
    local_pdf_dir: Path
    local_md_dir: Path
    local_json_dir: Path
    final_reports_dir: Path
    reports_dir: Path
    copied_pdf_path: Path
    md_path: Path
    json_path: Path
    report_path: Path


@dataclass(frozen=True)
class StagingTargets:
    local_pdf_dir: Path
    local_md_dir: Path
    local_json_dir: Path
    final_reports_dir: Path
    reports_dir: Path
    copied_pdf_path: Path
    md_path: Path
    json_path: Path
    report_path: Path


@dataclass
class BatchResult:
    source_pdf: str
    relative_dir: str
    status: str
    report_path: str
    duration_seconds: float
    error: str = ""


class ConsoleHooks(PipelineHooks):
    def __init__(self, pdf_label: str) -> None:
        prefix = f"[{pdf_label}]"
        self.logs: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.successes: list[str] = []
        super().__init__(
            set_status=lambda message: print(f"{prefix} STATUS {message}"),
            set_progress=lambda value: print(f"{prefix} PROGRESS {value}%"),
            info=self._emit_info,
            warning=self._emit_warning,
            error=self._emit_error,
            success=self._emit_success,
        )

        self._prefix = prefix

    def _emit_info(self, message: str) -> None:
        self.logs.append(message)
        print(f"{self._prefix} INFO {message}")

    def _emit_warning(self, message: str) -> None:
        self.warnings.append(message)
        print(f"{self._prefix} WARNING {message}")

    def _emit_error(self, message: str) -> None:
        self.errors.append(message)
        print(f"{self._prefix} ERROR {message}")

    def _emit_success(self, message: str) -> None:
        self.successes.append(message)
        print(f"{self._prefix} SUCCESS {message}")


def is_non_cnas_skip_report(final_report: str) -> bool:
    return "# [跳过] 非CNAS文件，跳过核验" in final_report


def iter_pdf_files(input_dir: Path) -> Iterable[Path]:
    return sorted(path for path in input_dir.rglob("*.pdf") if path.is_file())


def build_output_targets(output_root: Path, relative_pdf_path: Path) -> OutputTargets:
    relative_parent = relative_pdf_path.parent
    file_name = relative_pdf_path.name
    stem = relative_pdf_path.stem

    local_pdf_dir = output_root / "local_pdf" / relative_parent
    local_md_dir = output_root / "local_md" / relative_parent
    local_json_dir = output_root / "local_json" / relative_parent
    final_reports_dir = output_root / "final_reports" / relative_parent
    reports_dir = output_root / "reports" / relative_parent

    return OutputTargets(
        local_pdf_dir=local_pdf_dir,
        local_md_dir=local_md_dir,
        local_json_dir=local_json_dir,
        final_reports_dir=final_reports_dir,
        reports_dir=reports_dir,
        copied_pdf_path=local_pdf_dir / file_name,
        md_path=local_md_dir / f"{stem}.md",
        json_path=local_json_dir / f"{stem}.json",
        report_path=final_reports_dir / f"Report_{stem}.md",
    )


def build_staging_targets(staging_root: Path, file_name: str, stem: str) -> StagingTargets:
    local_pdf_dir = staging_root / "local_pdf"
    local_md_dir = staging_root / "local_md"
    local_json_dir = staging_root / "local_json"
    final_reports_dir = staging_root / "final_reports"
    reports_dir = staging_root / "reports"
    return StagingTargets(
        local_pdf_dir=local_pdf_dir,
        local_md_dir=local_md_dir,
        local_json_dir=local_json_dir,
        final_reports_dir=final_reports_dir,
        reports_dir=reports_dir,
        copied_pdf_path=local_pdf_dir / file_name,
        md_path=local_md_dir / f"{stem}.md",
        json_path=local_json_dir / f"{stem}.json",
        report_path=final_reports_dir / f"Report_{stem}.md",
    )


def build_file_config(base_config: AppConfig, staging: StagingTargets) -> AppConfig:
    return (
        base_config.with_overrides(
            local_pdf_dir=staging.local_pdf_dir,
            local_md_dir=staging.local_md_dir,
            local_json_dir=staging.local_json_dir,
            final_reports_dir=staging.final_reports_dir,
            reports_dir=staging.reports_dir,
        )
        .ensure_directories()
    )


def should_skip_existing(targets: OutputTargets, force: bool) -> bool:
    if force:
        return False
    return targets.report_path.exists() and targets.report_path.stat().st_size > 0


def clear_staging_targets(staging: StagingTargets) -> None:
    for path in (
        staging.copied_pdf_path,
        staging.md_path,
        staging.json_path,
        staging.report_path,
    ):
        if path.exists():
            path.unlink()


def ensure_output_directories(targets: OutputTargets) -> None:
    for directory in (
        targets.local_pdf_dir,
        targets.local_md_dir,
        targets.local_json_dir,
        targets.final_reports_dir,
        targets.reports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def _copy_first_existing(target: Path, candidates: Iterable[Path]) -> None:
    for candidate in candidates:
        if candidate.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target)
            return


def preload_staging_cache(
    staging: StagingTargets,
    targets: OutputTargets,
    base_config: AppConfig,
) -> None:
    _copy_first_existing(
        staging.md_path,
        (
            targets.md_path,
            Path(base_config.local_md_dir) / staging.md_path.name,
        ),
    )
    _copy_first_existing(
        staging.json_path,
        (
            targets.json_path,
            Path(base_config.local_json_dir) / staging.json_path.name,
        ),
    )


def mirror_run_outputs(staging: StagingTargets, targets: OutputTargets) -> None:
    shutil.copyfile(staging.copied_pdf_path, targets.copied_pdf_path)
    if staging.md_path.exists():
        shutil.copyfile(staging.md_path, targets.local_md_dir / staging.md_path.name)
    if staging.json_path.exists():
        shutil.copyfile(staging.json_path, targets.local_json_dir / staging.json_path.name)
    if staging.report_path.exists():
        shutil.copyfile(staging.report_path, targets.report_path)
    else:
        raise FileNotFoundError(f"Expected staged final report not found: {staging.report_path}")

    if staging.reports_dir.exists():
        for path in staging.reports_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(staging.reports_dir)
            dst = targets.reports_dir / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dst)


def validate_successful_run(
    staging: StagingTargets,
    final_report: str,
    hooks: ConsoleHooks,
) -> Optional[str]:
    if hooks.errors:
        return f"pipeline emitted errors: {hooks.errors[0]}"
    if is_non_cnas_skip_report(final_report):
        return None
    if not staging.md_path.exists():
        return f"expected staged markdown not found: {staging.md_path}"
    if not staging.json_path.exists():
        return f"expected staged json not found: {staging.json_path}"
    if "## PDF -> MD" not in final_report or "## MD 解析" not in final_report:
        return "final report is missing parse sections; likely only header was rendered"
    return None


def run_single_pdf(
    pdf_path: Path,
    input_dir: Path,
    output_root: Path,
    base_config: AppConfig,
    *,
    embedder,
    llm_client,
    force: bool,
) -> BatchResult:
    relative_pdf_path = pdf_path.relative_to(input_dir)
    targets = build_output_targets(output_root, relative_pdf_path)
    staging_root = output_root / ".batch_runtime"
    staging = build_staging_targets(staging_root, relative_pdf_path.name, relative_pdf_path.stem)
    relative_dir = str(relative_pdf_path.parent).replace("\\", "/")
    if relative_dir == ".":
        relative_dir = ""

    if should_skip_existing(targets, force):
        return BatchResult(
            source_pdf=str(pdf_path),
            relative_dir=relative_dir,
            status="skipped",
            report_path=str(targets.report_path),
            duration_seconds=0.0,
        )

    file_config = build_file_config(base_config, staging)
    ensure_output_directories(targets)
    clear_staging_targets(staging)
    preload_staging_cache(staging, targets, base_config)
    shutil.copyfile(pdf_path, staging.copied_pdf_path)

    hooks = ConsoleHooks(relative_pdf_path.as_posix())
    started_at = time.perf_counter()
    try:
        final_report = run_verification(
            pdf_file_path=staging.copied_pdf_path,
            config=file_config,
            hooks=hooks,
            embedder=embedder,
            llm_client=llm_client,
        )
        duration = time.perf_counter() - started_at
        if not final_report:
            return BatchResult(
                source_pdf=str(pdf_path),
                relative_dir=relative_dir,
                status="failed",
                report_path=str(targets.report_path),
                duration_seconds=duration,
                error="run_verification returned no final report",
            )
        validation_error = validate_successful_run(staging, final_report, hooks)
        if validation_error:
            return BatchResult(
                source_pdf=str(pdf_path),
                relative_dir=relative_dir,
                status="failed",
                report_path=str(targets.report_path),
                duration_seconds=duration,
                error=validation_error,
            )
        staging.report_path.write_text(final_report, encoding="utf-8")
        mirror_run_outputs(staging, targets)
        return BatchResult(
            source_pdf=str(pdf_path),
            relative_dir=relative_dir,
            status="passed",
            report_path=str(targets.report_path),
            duration_seconds=duration,
        )
    except Exception as exc:  # pragma: no cover - runtime-facing path
        duration = time.perf_counter() - started_at
        return BatchResult(
            source_pdf=str(pdf_path),
            relative_dir=relative_dir,
            status="failed",
            report_path=str(targets.report_path),
            duration_seconds=duration,
            error=str(exc),
        )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-run langchain_app verification over a PDF tree.")
    parser.add_argument(
        "--input-dir",
        default="pdf",
        help="Directory containing input PDFs. Default: pdf",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Root directory for mirrored outputs. Default: output",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on number of PDFs to process. 0 means no limit.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run files even if the target report already exists.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent
    input_dir = (repo_root / args.input_dir).resolve()
    output_root = (repo_root / args.output_dir).resolve()

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return 1

    pdf_files = list(iter_pdf_files(input_dir))
    if args.limit and args.limit > 0:
        pdf_files = pdf_files[: args.limit]

    if not pdf_files:
        print(f"No PDF files found under: {input_dir}")
        return 1

    base_config = get_app_config()
    embedder = load_shared_embedder(str(base_config.embed_model_path))
    results: list[BatchResult] = []
    for index, pdf_path in enumerate(pdf_files, start=1):
        rel = pdf_path.relative_to(input_dir).as_posix()
        print(f"[{index}/{len(pdf_files)}] RUN {rel}")
        result = run_single_pdf(
            pdf_path,
            input_dir,
            output_root,
            base_config,
            embedder=embedder,
            llm_client=None,
            force=args.force,
        )
        results.append(result)
        if result.status == "failed":
            print(f"[{index}/{len(pdf_files)}] FAIL {rel} :: {result.error}")
        elif result.status == "skipped":
            print(f"[{index}/{len(pdf_files)}] SKIP {rel}")
        else:
            print(f"[{index}/{len(pdf_files)}] PASS {rel} -> {result.report_path}")

    summary_path = output_root / "batch_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    passed = sum(1 for item in results if item.status == "passed")
    skipped = sum(1 for item in results if item.status == "skipped")
    failed = sum(1 for item in results if item.status == "failed")
    print(f"Done. passed={passed} skipped={skipped} failed={failed}")
    print(f"Summary: {summary_path}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
