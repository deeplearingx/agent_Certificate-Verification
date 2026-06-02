from __future__ import annotations

import os
import sys
import types
from pathlib import Path

from langchain_app.services.parsing import pdf_to_md_first_step
from langchain_app.utils import AppConfig


def _build_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        root_dir=tmp_path,
        api_key="test-key",
        api_base="https://api.example.com",
        model="deepseek-chat",
        temperature=0.1,
        max_tokens=1024,
        topk=12,
        batch_size=4,
        max_workers=2,
        embed_model_path=str(tmp_path / "models"),
        cnas_db_dir=str(tmp_path / "vector_db" / "cnas_calibration"),
        temperature_db_dir=str(tmp_path / "vector_db" / "temperature"),
        general_cycle_db_dir=str(tmp_path / "vector_db" / "general_cycle"),
        huawei_cycle_db_dir=str(tmp_path / "vector_db" / "huawei_cycle"),
        address_db_dir=str(tmp_path / "vector_db" / "address"),
        cnas_collection="calibration_data",
        address_collection="calibration_address",
        default_cycle="12个月",
        use_llm_verification=True,
        use_llm_location_check=True,
        must_match_threshold=0.45,
        optional_match_threshold=0.4,
        llm_temperature=0.0,
        llm_max_tokens=256,
        local_pdf_dir=tmp_path / "local_pdf",
        local_md_dir=tmp_path / "local_md",
        local_json_dir=tmp_path / "local_json",
        final_reports_dir=tmp_path / "final_reports",
        reports_dir=tmp_path / "reports",
    )


def test_apply_default_windows_ai_cache_env_sets_expected_dirs(tmp_path, monkeypatch):
    from langchain_app.utils import runtime_cache

    root = tmp_path / "ai_cache"
    monkeypatch.setattr(runtime_cache.sys, "platform", "win32")
    monkeypatch.setenv("AI_CACHE_ROOT", str(root))

    for env_name in (
        "HF_HOME",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "MODELSCOPE_CACHE",
        "MODELSCOPE_HOME",
        "TORCH_HOME",
        "PIP_CACHE_DIR",
        "CONDA_PKGS_DIRS",
        "TMP",
        "TEMP",
        "DOC_VERIFICATION_MINERU_TMP_DIR",
    ):
        monkeypatch.delenv(env_name, raising=False)

    applied_root = runtime_cache.apply_default_windows_ai_cache_env()

    assert applied_root == root
    assert os.environ["HF_HOME"] == str(root / "hf")
    assert os.environ["MODELSCOPE_CACHE"] == str(root / "modelscope")
    assert os.environ["TORCH_HOME"] == str(root / "torch")
    assert os.environ["TMP"] == str(root / "temp")
    assert os.environ["DOC_VERIFICATION_MINERU_TMP_DIR"] == str(root / "mineru_output")
    assert (root / "hf").is_dir()
    assert (root / "modelscope").is_dir()
    assert (root / "torch").is_dir()
    assert (root / "temp").is_dir()
    assert (root / "mineru_output").is_dir()


def test_pdf_to_md_first_step_uses_windows_ai_cache_mineru_tmp_dir(tmp_path, monkeypatch):
    from langchain_app.utils import runtime_cache

    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    root = tmp_path / "ai_cache"
    seen: dict[str, str] = {}

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen["output_dir"] = output_dir
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed", encoding="utf-8")

    monkeypatch.setattr(runtime_cache.sys, "platform", "win32")
    monkeypatch.setenv("AI_CACHE_ROOT", str(root))
    monkeypatch.delenv("DOC_VERIFICATION_MINERU_TMP_DIR", raising=False)
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert Path(seen["output_dir"]).parent == root / "mineru_output"
