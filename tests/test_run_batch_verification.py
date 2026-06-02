from pathlib import Path

from langchain_app.utils.config import get_app_config
from run_batch_verification import (
    build_output_targets,
    build_staging_targets,
    parse_args,
    run_single_pdf,
)


def test_build_output_targets_preserves_relative_category_structure():
    output_root = Path("/tmp/out-root")
    relative_pdf_path = Path("时间和频率证书2026/秒表/2GB25028626-0040.pdf")

    targets = build_output_targets(output_root, relative_pdf_path)

    assert targets.local_pdf_dir == output_root / "local_pdf" / "时间和频率证书2026/秒表"
    assert targets.local_md_dir == output_root / "local_md" / "时间和频率证书2026/秒表"
    assert targets.local_json_dir == output_root / "local_json" / "时间和频率证书2026/秒表"
    assert targets.final_reports_dir == output_root / "final_reports" / "时间和频率证书2026/秒表"
    assert targets.reports_dir == output_root / "reports" / "时间和频率证书2026/秒表"
    assert targets.copied_pdf_path == output_root / "local_pdf" / "时间和频率证书2026/秒表/2GB25028626-0040.pdf"
    assert targets.md_path == output_root / "local_md" / "时间和频率证书2026/秒表/2GB25028626-0040.md"
    assert targets.json_path == output_root / "local_json" / "时间和频率证书2026/秒表/2GB25028626-0040.json"
    assert targets.report_path == output_root / "final_reports" / "时间和频率证书2026/秒表/Report_2GB25028626-0040.md"


def test_build_staging_targets_uses_flat_runtime_layout():
    staging_root = Path("/tmp/out-root/.batch_runtime")
    targets = build_staging_targets(staging_root, "2GB25028626-0040.pdf", "2GB25028626-0040")

    assert targets.local_pdf_dir == staging_root / "local_pdf"
    assert targets.local_md_dir == staging_root / "local_md"
    assert targets.local_json_dir == staging_root / "local_json"
    assert targets.final_reports_dir == staging_root / "final_reports"
    assert targets.reports_dir == staging_root / "reports"
    assert targets.copied_pdf_path == staging_root / "local_pdf/2GB25028626-0040.pdf"
    assert targets.md_path == staging_root / "local_md/2GB25028626-0040.md"
    assert targets.json_path == staging_root / "local_json/2GB25028626-0040.json"
    assert targets.report_path == staging_root / "final_reports/Report_2GB25028626-0040.md"


def test_parse_args_defaults_to_pdf_input_and_output_root():
    args = parse_args([])

    assert args.input_dir == "pdf"
    assert args.output_dir == "output"
    assert args.limit == 0
    assert args.force is False


def test_run_single_pdf_fails_when_report_only_has_header(monkeypatch, tmp_path):
    input_dir = tmp_path / "pdf"
    pdf_dir = input_dir / "时间和频率证书2026" / "脉冲计数器"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "2GB25000800-0015.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    output_root = tmp_path / "out"
    base_config = get_app_config().with_overrides(
        local_pdf_dir=tmp_path / "unused_local_pdf",
        local_md_dir=tmp_path / "unused_local_md",
        local_json_dir=tmp_path / "unused_local_json",
        final_reports_dir=tmp_path / "unused_final_reports",
        reports_dir=tmp_path / "unused_reports",
    )

    def fake_run_verification(**kwargs):
        return (
            "# 全流程智能核验报告\n"
            "**源文件**: `2GB25000800-0015.pdf`\n"
            "**核验时间**: `2026-04-27 15:15:31`\n"
            "**核验模型**: `deepseek-v4-flash` (Temp: 0.1, TopK: 50)\n"
            "---\n"
        )

    monkeypatch.setattr("run_batch_verification.run_verification", fake_run_verification)

    result = run_single_pdf(
        pdf_path,
        input_dir,
        output_root,
        base_config,
        embedder=object(),
        llm_client=None,
        force=True,
    )

    assert result.status == "failed"
    assert "expected staged markdown not found" in result.error


def test_run_single_pdf_passes_when_staged_artifacts_and_sections_exist(monkeypatch, tmp_path):
    input_dir = tmp_path / "pdf"
    pdf_dir = input_dir / "时间和频率证书2026" / "脉冲计数器"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "2GB25000800-0015.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    output_root = tmp_path / "out"
    base_config = get_app_config().with_overrides(
        local_pdf_dir=tmp_path / "unused_local_pdf",
        local_md_dir=tmp_path / "unused_local_md",
        local_json_dir=tmp_path / "unused_local_json",
        final_reports_dir=tmp_path / "unused_final_reports",
        reports_dir=tmp_path / "unused_reports",
    )

    def fake_run_verification(pdf_file_path, config, hooks, **kwargs):
        stem = Path(pdf_file_path).stem
        (config.local_md_dir / f"{stem}.md").write_text("# md", encoding="utf-8")
        (config.local_json_dir / f"{stem}.json").write_text("{}", encoding="utf-8")
        return (
            "# 全流程智能核验报告\n"
            "**源文件**: `2GB25000800-0015.pdf`\n"
            "---\n"
            "## PDF -> MD 成功\n> 生成 MD: `2GB25000800-0015.md`\n\n"
            "## MD 解析成功\n> 生成 JSON: `2GB25000800-0015.json`\n"
        )

    monkeypatch.setattr("run_batch_verification.run_verification", fake_run_verification)

    result = run_single_pdf(
        pdf_path,
        input_dir,
        output_root,
        base_config,
        embedder=object(),
        llm_client=None,
        force=True,
    )

    assert result.status == "passed"
    assert (output_root / "local_md" / "时间和频率证书2026/脉冲计数器/2GB25000800-0015.md").exists()
    assert (output_root / "local_json" / "时间和频率证书2026/脉冲计数器/2GB25000800-0015.json").exists()
    assert (output_root / "final_reports" / "时间和频率证书2026/脉冲计数器/Report_2GB25000800-0015.md").exists()


def test_run_single_pdf_reuses_existing_output_md_and_json(monkeypatch, tmp_path):
    input_dir = tmp_path / "pdf"
    pdf_dir = input_dir / "时间和频率证书2026" / "秒表"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "2GB25028626-0040.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    output_root = tmp_path / "output"
    existing_md = output_root / "local_md" / "时间和频率证书2026" / "秒表" / "2GB25028626-0040.md"
    existing_json = output_root / "local_json" / "时间和频率证书2026" / "秒表" / "2GB25028626-0040.json"
    existing_md.parent.mkdir(parents=True, exist_ok=True)
    existing_json.parent.mkdir(parents=True, exist_ok=True)
    existing_md.write_text("# cached md", encoding="utf-8")
    existing_json.write_text('{"cached": true}', encoding="utf-8")

    base_config = get_app_config().with_overrides(
        local_pdf_dir=tmp_path / "unused_local_pdf",
        local_md_dir=tmp_path / "unused_local_md",
        local_json_dir=tmp_path / "unused_local_json",
        final_reports_dir=tmp_path / "unused_final_reports",
        reports_dir=tmp_path / "unused_reports",
    )

    def fake_run_verification(pdf_file_path, config, hooks, **kwargs):
        stem = Path(pdf_file_path).stem
        assert (config.local_md_dir / f"{stem}.md").read_text(encoding="utf-8") == "# cached md"
        assert (config.local_json_dir / f"{stem}.json").read_text(encoding="utf-8") == '{"cached": true}'
        return (
            "# 全流程智能核验报告\n"
            f"**源文件**: `{Path(pdf_file_path).name}`\n"
            "---\n"
            f"## PDF -> MD (跳过)\n> 检测到现有 MD `{stem}.md`，直接使用。\n\n"
            f"## MD 解析 (跳过)\n> 检测到现有 JSON `{stem}.json`，直接使用。\n"
        )

    monkeypatch.setattr("run_batch_verification.run_verification", fake_run_verification)

    result = run_single_pdf(
        pdf_path,
        input_dir,
        output_root,
        base_config,
        embedder=object(),
        llm_client=None,
        force=True,
    )

    assert result.status == "passed"
    assert existing_md.read_text(encoding="utf-8") == "# cached md"
    assert existing_json.read_text(encoding="utf-8") == '{"cached": true}'


def test_run_single_pdf_falls_back_to_root_local_md_and_json(monkeypatch, tmp_path):
    input_dir = tmp_path / "pdf"
    pdf_dir = input_dir / "时间和频率证书2026" / "GNSS导航信号采集回放仪"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "2GB25006175-0001A.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    output_root = tmp_path / "output"
    root_local_md = tmp_path / "local_md" / "2GB25006175-0001A.md"
    root_local_json = tmp_path / "local_json" / "2GB25006175-0001A.json"
    root_local_md.parent.mkdir(parents=True, exist_ok=True)
    root_local_json.parent.mkdir(parents=True, exist_ok=True)
    root_local_md.write_text("# root cached md", encoding="utf-8")
    root_local_json.write_text('{"root_cached": true}', encoding="utf-8")

    base_config = get_app_config().with_overrides(
        local_pdf_dir=tmp_path / "unused_local_pdf",
        local_md_dir=tmp_path / "local_md",
        local_json_dir=tmp_path / "local_json",
        final_reports_dir=tmp_path / "unused_final_reports",
        reports_dir=tmp_path / "unused_reports",
    )

    def fake_run_verification(pdf_file_path, config, hooks, **kwargs):
        stem = Path(pdf_file_path).stem
        assert (config.local_md_dir / f"{stem}.md").read_text(encoding="utf-8") == "# root cached md"
        assert (config.local_json_dir / f"{stem}.json").read_text(encoding="utf-8") == '{"root_cached": true}'
        return (
            "# 全流程智能核验报告\n"
            f"**源文件**: `{Path(pdf_file_path).name}`\n"
            "---\n"
            f"## PDF -> MD (跳过)\n> 检测到现有 MD `{stem}.md`，直接使用。\n\n"
            f"## MD 解析 (跳过)\n> 检测到现有 JSON `{stem}.json`，直接使用。\n"
        )

    monkeypatch.setattr("run_batch_verification.run_verification", fake_run_verification)

    result = run_single_pdf(
        pdf_path,
        input_dir,
        output_root,
        base_config,
        embedder=object(),
        llm_client=None,
        force=True,
    )

    assert result.status == "passed"
    assert (output_root / "local_md" / "时间和频率证书2026/GNSS导航信号采集回放仪/2GB25006175-0001A.md").read_text(encoding="utf-8") == "# root cached md"
    assert (output_root / "local_json" / "时间和频率证书2026/GNSS导航信号采集回放仪/2GB25006175-0001A.json").read_text(encoding="utf-8") == '{"root_cached": true}'


def test_run_single_pdf_passes_for_non_cnas_skip_report_without_json(monkeypatch, tmp_path):
    input_dir = tmp_path / "pdf"
    pdf_dir = input_dir / "时间和频率证书2026" / "秒表"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "2GB25013402-0009.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    output_root = tmp_path / "out"
    base_config = get_app_config().with_overrides(
        local_pdf_dir=tmp_path / "unused_local_pdf",
        local_md_dir=tmp_path / "unused_local_md",
        local_json_dir=tmp_path / "unused_local_json",
        final_reports_dir=tmp_path / "unused_final_reports",
        reports_dir=tmp_path / "unused_reports",
    )

    def fake_run_verification(pdf_file_path, config, hooks, **kwargs):
        return (
            "# 全流程智能核验报告\n"
            f"**源文件**: `{Path(pdf_file_path).name}`\n"
            "---\n"
            "# [跳过] 非CNAS文件，跳过核验\n"
            f"**证书文件**：{Path(pdf_file_path).name}\n"
            "**证书编号**：2GB25013402-0009\n\n"
            "## [跳过] 跳过说明\n"
            "> **原因**：该证书未标记为 CNAS 认可证书。\n"
            "> **处理**：当前文件跳过后续核验流程。\n"
        )

    monkeypatch.setattr("run_batch_verification.run_verification", fake_run_verification)

    result = run_single_pdf(
        pdf_path,
        input_dir,
        output_root,
        base_config,
        embedder=object(),
        llm_client=None,
        force=True,
    )

    assert result.status == "passed"
    assert (output_root / "final_reports" / "时间和频率证书2026/秒表/Report_2GB25013402-0009.md").exists()
    assert not (output_root / "local_json" / "时间和频率证书2026/秒表/2GB25013402-0009.json").exists()
