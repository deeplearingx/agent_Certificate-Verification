#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parsing services for LangGraph mainline.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from langchain_app.checks.parameter.contracts import parameter_contract_schema_version
from langchain_app.core.embedding_loader import configure_torch_cuda_allocator
from langchain_app.services.md_parser_pipeline import md_parser_pipeline_signature
from langchain_app.utils.runtime_cache import apply_default_windows_ai_cache_env, get_mineru_tmp_dir
from langchain_app.utils.config import AppConfig


_MINERU_INTERNAL_ENGINE_ERROR_PATTERNS = ("responsetype.internal_engine_error",)


def _is_mineru_offload_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "offload_folder" in text or "offloaded to disk" in text


def _is_mineru_cuda_oom_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        token in text
        for token in (
            "cuda out of memory",
            "torch.outofmemoryerror",
            "cublas_status_alloc_failed",
            "cuda error: out of memory",
        )
    )


def _is_mineru_windows_pagefile_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        token in text
        for token in (
            "os error 1455",
            "pagefile too small",
            "page file too small",
            "页面文件太小",
        )
    )


def _allow_pipeline_fallback() -> bool:
    return str(os.getenv("DOC_VERIFICATION_ALLOW_MINERU_PIPELINE_FALLBACK", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _mineru_pipeline_available() -> bool:
    required_modules = (
        "mineru.backend.pipeline.pipeline_analyze",
        "mineru.backend.pipeline.pipeline_middle_json_mkcontent",
        "mineru.backend.pipeline.model_json_to_middle_json",
    )
    for module_name in required_modules:
        if importlib.util.find_spec(module_name) is None:
            return False
        try:
            importlib.import_module(module_name)
        except Exception:
            return False
    return True


def _should_retry_pipeline_after_hybrid_error(exc: Exception) -> bool:
    if _is_mineru_cuda_oom_error(exc):
        return True
    if _is_mineru_windows_pagefile_error(exc):
        return True
    if _is_mineru_offload_error(exc) and _allow_pipeline_fallback():
        return True
    return False


def _apply_default_mineru_runtime_env(backend: str) -> None:
    normalized_backend = str(backend or "").strip().lower()
    if not normalized_backend.startswith("hybrid-"):
        return
    configure_torch_cuda_allocator()
    if not str(os.getenv("MINERU_HYBRID_BATCH_RATIO", "") or "").strip():
        os.environ["MINERU_HYBRID_BATCH_RATIO"] = "1"
    if not str(os.getenv("MINERU_PROCESSING_WINDOW_SIZE", "") or "").strip():
        os.environ["MINERU_PROCESSING_WINDOW_SIZE"] = "16"


def _count_pdf_pages(pdf_path: Path) -> int:
    try:
        import fitz  # pymupdf

        doc = fitz.open(pdf_path)
        return int(doc.page_count or 0)
    except Exception:
        return 0


def _extract_pdf_header_text(pdf_path: Path, *, max_pages: int = 2, max_chars: int = 6000) -> str:
    try:
        import fitz  # pymupdf

        doc = fitz.open(pdf_path)
        chunks: list[str] = []
        for page_index in range(min(int(doc.page_count or 0), max_pages)):
            page_text = doc.load_page(page_index).get_text("text")
            if page_text:
                chunks.append(page_text)
            merged = "\n".join(chunks)
            if len(merged) >= max_chars or "DIRECTIONS" in merged or "说 明" in merged:
                break
        return "\n".join(chunks)[:max_chars]
    except Exception:
        return ""


def _is_trustworthy_pdf_header_probe(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if len(re.sub(r"\s+", "", normalized)) < 80:
        return False

    hint_tokens = (
        "校准证书",
        "CALIBRATION CERTIFICATE",
        "证书编号",
        "Certificate No",
        "委托单位",
        "型号",
        "制造商",
    )
    hint_count = sum(1 for token in hint_tokens if token.lower() in normalized.lower())
    return hint_count >= 2


def _extract_meta_from_header_text(header_text: str) -> dict:
    import md_parser_no_llm

    meta = md_parser_no_llm.extract_meta_from_text(header_text) or {}
    if not isinstance(meta, dict):
        return {}
    return meta


def _extract_pdf_header_text_with_mineru_probe(
    pdf_path: Path,
    config: AppConfig,
    *,
    hooks=None,
    lang: str = "ch",
) -> str:
    apply_default_windows_ai_cache_env()
    mineru_tmp_dir = get_mineru_tmp_dir()
    if mineru_tmp_dir is not None:
        mineru_tmp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=str(mineru_tmp_dir) if mineru_tmp_dir is not None else None) as tmp_out:
        tmp_out_dir = Path(tmp_out)
        try:
            import sys

            sys.path.insert(0, str(config.root_dir))
            import pdf_md  # type: ignore

            _apply_default_mineru_runtime_env("hybrid-auto-engine")
            _run_pdf_md_parse_with_capture(
                pdf_md,
                path_list=[pdf_path],
                output_dir=str(tmp_out_dir),
                lang=lang,
                backend="hybrid-auto-engine",
                method="auto",
                lmdeploy_backend="pytorch",
                start_page_id=0,
                end_page_id=0,
            )
            md_path = _collect_single_md_file(tmp_out_dir)
            if md_path is None:
                return ""
            return md_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            if hooks:
                hooks.emit_info(f"PDF 页眉轻量探测失败，回退完整解析: {exc}")
            return ""


def probe_pdf_header_meta(
    pdf_path: Path,
    config: Optional[AppConfig] = None,
    *,
    hooks=None,
    lang: str = "ch",
) -> dict:
    header_text = _extract_pdf_header_text(pdf_path)
    if _is_trustworthy_pdf_header_probe(header_text):
        return _extract_meta_from_header_text(header_text)

    if config is None:
        return {}

    probe_text = _extract_pdf_header_text_with_mineru_probe(pdf_path, config, hooks=hooks, lang=lang)
    if not _is_trustworthy_pdf_header_probe(probe_text):
        return {}
    return _extract_meta_from_header_text(probe_text)


def _mineru_internal_engine_error_count(log_text: str) -> int:
    lowered = str(log_text or "").lower()
    return sum(lowered.count(pattern) for pattern in _MINERU_INTERNAL_ENGINE_ERROR_PATTERNS)


def _run_pdf_md_parse_with_capture(
    pdf_md_module,
    *,
    path_list,
    output_dir: str,
    lang: str,
    backend: str,
    method: str,
    **kwargs,
) -> str:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        pdf_md_module.parse_doc_md_only(
            path_list=path_list,
            output_dir=output_dir,
            lang=lang,
            backend=backend,
            method=method,
            **kwargs,
        )
    return stdout_buffer.getvalue() + "\n" + stderr_buffer.getvalue()


def _collect_single_md_file(output_dir: Path) -> Optional[Path]:
    md_files = sorted(output_dir.glob("**/*.md"))
    if not md_files:
        return None
    return md_files[0]


def _rerun_hybrid_per_page(
    pdf_md_module,
    *,
    pdf_path: Path,
    output_dir: Path,
    lang: str,
    hooks=None,
) -> Path:
    page_count = _count_pdf_pages(pdf_path)
    if page_count <= 0:
        raise RuntimeError("MinerU hybrid parse degraded and page count could not be determined for page-level retry")

    page_md_chunks: list[str] = []
    retry_error_details: list[str] = []

    for page_index in range(page_count):
        if hooks:
            hooks.emit_info(
                f"MinerU hybrid degraded; retry page {page_index + 1}/{page_count} with conservative hybrid settings"
            )
        page_output_dir = output_dir / f"page_retry_{page_index + 1:03d}"
        page_output_dir.mkdir(parents=True, exist_ok=True)
        captured = _run_pdf_md_parse_with_capture(
            pdf_md_module,
            path_list=[pdf_path],
            output_dir=str(page_output_dir),
            lang=lang,
            backend="hybrid-auto-engine",
            method="auto",
            lmdeploy_backend="pytorch",
            start_page_id=page_index,
            end_page_id=page_index,
        )
        if _mineru_internal_engine_error_count(captured) > 0:
            retry_error_details.append(f"page {page_index + 1}")
            continue
        page_md_path = _collect_single_md_file(page_output_dir)
        if page_md_path is None:
            retry_error_details.append(f"page {page_index + 1} missing md")
            continue
        page_md_chunks.append(page_md_path.read_text(encoding="utf-8"))

    if retry_error_details:
        raise RuntimeError(
            "MinerU hybrid parse degraded and page-level retry still failed: "
            + ", ".join(retry_error_details)
        )

    combined_md_path = output_dir / f"{pdf_path.stem}.md"
    combined_md_path.write_text("\n\n".join(chunk.strip() for chunk in page_md_chunks if chunk.strip()), encoding="utf-8")
    return combined_md_path


def pdf_to_md_first_step(
    pdf_path: Path,
    config: AppConfig,
    hooks=None,
    stop_event=None,
    lang: str = "ch",
) -> Optional[Path]:
    """
    Convert PDF to Markdown using MinerU, preserving the original cache behavior.
    """
    if stop_event is not None and stop_event.is_set():
        return None

    stem = pdf_path.stem
    cached_md = config.local_md_dir / f"{stem}.md"
    if cached_md.exists() and cached_md.stat().st_size > 0:
        if hooks:
            hooks.emit_status("Processing [0/7]: PDF -> MD (cache hit)")
            hooks.emit_progress(10)
            hooks.emit_info(f"Cache hit: reuse MD {cached_md.name}")
        return cached_md

    if hooks:
        hooks.emit_status("Processing [0/7]: PDF -> MD")
        hooks.emit_progress(3)

    apply_default_windows_ai_cache_env()
    mineru_tmp_dir = get_mineru_tmp_dir()
    if mineru_tmp_dir is not None:
        mineru_tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(mineru_tmp_dir) if mineru_tmp_dir is not None else None) as tmp_out:
        tmp_out_dir = Path(tmp_out)
        offload_dir = tmp_out_dir / "mineru_offload"
        offload_dir.mkdir(parents=True, exist_ok=True)
        if hooks:
            hooks.emit_status("Processing [0/7]: PDF -> MD (MinerU running)")
            hooks.emit_progress(6)
        try:
            import sys

            sys.path.insert(0, str(config.root_dir))
            import pdf_md  # type: ignore

            try:
                _apply_default_mineru_runtime_env("hybrid-auto-engine")
                parse_log = _run_pdf_md_parse_with_capture(
                    pdf_md,
                    path_list=[pdf_path],
                    output_dir=str(tmp_out_dir),
                    lang=lang,
                    backend="hybrid-auto-engine",
                    method="auto",
                    lmdeploy_backend="pytorch",
                )
            except Exception as exc:
                if not _should_retry_pipeline_after_hybrid_error(exc):
                    raise
                if not _mineru_pipeline_available():
                    raise
                if hooks:
                    if _is_mineru_cuda_oom_error(exc):
                        hooks.emit_info(
                            "MinerU hybrid backend hit CUDA OOM during model startup; retry with pipeline backend"
                        )
                    elif _is_mineru_windows_pagefile_error(exc):
                        hooks.emit_info(
                            "MinerU hybrid backend hit Windows pagefile/memory-map limit during model startup; retry with pipeline backend"
                        )
                    else:
                        hooks.emit_info(
                            "MinerU hybrid backend hit offload-folder runtime issue; retry with pipeline backend"
                        )
                parse_log = _run_pdf_md_parse_with_capture(
                    pdf_md,
                    path_list=[pdf_path],
                    output_dir=str(tmp_out_dir),
                    lang=lang,
                    backend="pipeline",
                    method="auto",
                )
            if _mineru_internal_engine_error_count(parse_log) > 0:
                if hooks:
                    hooks.emit_info(
                        "MinerU hybrid emitted INTERNAL_ENGINE_ERROR; discard degraded output and retry page-by-page"
                    )
                md_path = _rerun_hybrid_per_page(
                    pdf_md,
                    pdf_path=pdf_path,
                    output_dir=tmp_out_dir,
                    lang=lang,
                    hooks=hooks,
                )
            else:
                md_path = _collect_single_md_file(tmp_out_dir)
            if stop_event is not None and stop_event.is_set():
                return None
            if md_path is None:
                if hooks:
                    hooks.emit_error("PDF -> MD failed: no markdown output found")
                return None
        except Exception as exc:
            if hooks:
                hooks.emit_error(f"PDF -> MD failed: {exc}")
            return None

        if hooks:
            hooks.emit_status("Processing [0/7]: PDF -> MD (finalizing)")
            hooks.emit_progress(9)
        dst_md_path = config.local_md_dir / f"{stem}.md"
        shutil.copyfile(md_path, dst_md_path)
        if hooks:
            hooks.emit_status("Processing [0/7]: PDF -> MD completed")
            hooks.emit_progress(10)
        return dst_md_path


def json_cache_needs_refresh(json_path: Path) -> bool:
    """
    Recreate the original stale-cache detection for JSON parsing output.
    """
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return True

    if int(data.get("__parameter_contract_schema_version") or 0) != parameter_contract_schema_version():
        return True

    if str(data.get("__md_parser_pipeline_signature") or "").strip() != md_parser_pipeline_signature():
        return True

    rows = next((value for value in data.values() if isinstance(value, list)), None)
    if not isinstance(rows, list):
        return True
    if not rows:
        return True

    props = (
        data.get("properties", {})
        .get("证书列表", {})
        .get("items", {})
        .get("properties", {})
    )

    def meta_contains_embedded_label(value: object) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        return bool(
            re.search(
                r"(?:委托单位|委托方地址|仪器名称|型号规格|制造商|制造厂|机身号|管理号)\s*[：:]",
                text,
            )
        )

    for key in ("委托单位", "委托方地址", "制造商", "制造厂"):
        if meta_contains_embedded_label(props.get(key)):
            return True

    def row_has_only_channel(details: dict) -> bool:
        if not isinstance(details, dict) or len(details) != 1:
            return False
        key = next(iter(details.keys()), "")
        key_text = str(key).lower()
        return "channel" in key_text or "閫氶亾" in key_text

    def values_include_any_unit(details: dict, candidate_keys: tuple[str, ...]) -> bool:
        for key, value in (details or {}).items():
            key_text = str(key).lower()
            if any(token in key_text for token in candidate_keys):
                value_text = str(value)
                if any(
                    unit in value_text
                    for unit in ("kHz", "MHz", "Hz", "ns", "μs", "us", "mV", "V", "m/s", "m/s2", "m/s3", "m/s²", "m/s³")
                ):
                    return True
        return False

    def motion_row_needs_refresh(title: str, details: dict, parser_meta: dict | None) -> bool:
        lowered_title = str(title or "").lower()
        if not any(token in lowered_title for token in ("accelerated speed", "stacking velocity", "加速度", "加加速度", "速度")):
            return False
        if isinstance(parser_meta, dict) and parser_meta.get("unit_inherited"):
            return False
        return not values_include_any_unit(details, ("nominal", "reference", "indicated", "error", "limit", "u"))

    def looks_like_condition_frequency(value: object) -> bool:
        text = str(value or "").strip().lower()
        if not text or "dbc/hz" in text or "/hz" in text:
            return False
        return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:g|m|k)?hz\b", text))

    def needs_signal_quality_refresh(title: str, normalized: dict, parser_meta: dict | None) -> bool:
        section_rule = str((parser_meta or {}).get("section_rule") or "").strip().lower()
        lowered_title = str(title or "").lower()
        is_signal_quality = (
            section_rule in {"modulation_quality", "phase_noise", "spectral_purity"}
            or any(token in lowered_title for token in ("信号质量", "signal quality", "相位噪声", "phase noise", "信号纯度", "spectral purity"))
        )
        if not is_signal_quality:
            return False

        measure_value = str((normalized or {}).get("measure_value") or "").strip()
        reference_value = str((normalized or {}).get("reference_value") or "").strip()
        if not measure_value or not reference_value:
            return False
        return looks_like_condition_frequency(measure_value) and not looks_like_condition_frequency(reference_value)

    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("测量值", row.get("标题", "")))
        details = row.get("数据明细", row.get("详细数据", {}))
        parser_meta = row.get("__parser_meta", {})
        normalized = row.get("__normalized_fields", {})
        contract = row.get("__parameter_contract", {})
        if not isinstance(details, dict):
            continue
        if not isinstance(contract, dict):
            return True
        if int(contract.get("schema_version") or 0) != parameter_contract_schema_version():
            return True

        if row_has_only_channel(details):
            return True

        if motion_row_needs_refresh(title, details, parser_meta):
            return True

        if isinstance(normalized, dict) and needs_signal_quality_refresh(title, normalized, parser_meta):
            return True

        if "Frequency Measurement Error" in title:
            channel = str(details.get("通道 (Channel)", details.get("Channel", ""))).strip()
            if channel and channel not in {"1", "2"}:
                return True
            if not values_include_any_unit(details, ("reference", "indicated", "error", "limit")):
                return True

        if "Period Measurement Error" in title:
            channel = str(details.get("通道 (Channel)", details.get("Channel", ""))).strip()
            if channel and channel not in {"1", "2"}:
                return True
            if not values_include_any_unit(details, ("reference", "indicated", "error")):
                return True

        if "Input Sensitivity Check" in title:
            if not values_include_any_unit(details, ("frequency", "sensitivity")):
                return True

    return False


def parse_md_to_json(
    md_path: str,
    out_dir: Optional[Path] = None,
    *,
    llm_client: Optional[object] = None,
    allow_llm_fallback: bool = False,
    hooks=None,
) -> Optional[Path]:
    """
    Parse Markdown to JSON and return the generated JSON path.
    """
    md_path_obj = Path(md_path)
    output_dir = Path(out_dir) if out_dir is not None else md_path_obj.parent
    try:
        import md_parser_no_llm

        result = md_parser_no_llm.parse_md_to_json(
            md_path=str(md_path_obj),
            out_dir=output_dir,
            llm_client=llm_client if allow_llm_fallback else None,
            progress_callback=getattr(hooks, "parser_progress_callback", None) if hooks is not None else None,
        )
        if not result:
            raise RuntimeError(f"MD parser returned empty result for {md_path_obj.name}")

        json_path = output_dir / md_path_obj.with_suffix(".json").name
        if not json_path.exists():
            raise FileNotFoundError(f"MD parser did not write JSON: {json_path}")
        return json_path
    except Exception as exc:
        if isinstance(exc, (RuntimeError, FileNotFoundError)):
            raise
        raise RuntimeError(f"MD parser failed for {md_path_obj.name}: {exc}") from exc
