from __future__ import annotations

import os
import sys
import types
from pathlib import Path

from langchain_app.services.parsing import _mineru_pipeline_available, pdf_to_md_first_step
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


class _Hooks:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def emit_status(self, _message: str) -> None:
        pass

    def emit_progress(self, _value: int) -> None:
        pass

    def emit_info(self, _message: str) -> None:
        pass

    def emit_error(self, message: str) -> None:
        self.errors.append(message)


def test_pdf_to_md_first_step_uses_hybrid_pytorch_without_forwarding_offload_folder(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: dict[str, str] = {}

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen["output_dir"] = output_dir
        seen["offload_folder"] = str(kwargs.get("offload_folder") or "")
        seen["lmdeploy_backend"] = str(kwargs.get("lmdeploy_backend") or "")
        seen["hybrid_batch_ratio"] = str(os.getenv("MINERU_HYBRID_BATCH_RATIO") or "")
        seen["processing_window_size"] = str(os.getenv("MINERU_PROCESSING_WINDOW_SIZE") or "")
        seen["cuda_alloc_conf"] = str(os.getenv("PYTORCH_CUDA_ALLOC_CONF") or "")
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed", encoding="utf-8")

    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)
    monkeypatch.setattr("langchain_app.core.embedding_loader.sys.platform", "linux")

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert md_path.read_text(encoding="utf-8") == "# parsed"
    assert seen["offload_folder"] == ""
    assert seen["lmdeploy_backend"] == "pytorch"
    assert seen["hybrid_batch_ratio"] == "1"
    assert seen["processing_window_size"] == "16"
    assert seen["cuda_alloc_conf"] == "expandable_segments:True"


def test_pdf_to_md_first_step_skips_expandable_segments_on_windows(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: dict[str, str] = {}

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen["cuda_alloc_conf"] = str(os.getenv("PYTORCH_CUDA_ALLOC_CONF") or "")
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed", encoding="utf-8")

    monkeypatch.delenv("PYTORCH_CUDA_ALLOC_CONF", raising=False)
    monkeypatch.setattr("langchain_app.core.embedding_loader.sys.platform", "win32")
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert seen["cuda_alloc_conf"] == ""


def test_pdf_to_md_first_step_keeps_user_mineru_runtime_overrides(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: dict[str, str] = {}

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen["hybrid_batch_ratio"] = str(os.getenv("MINERU_HYBRID_BATCH_RATIO") or "")
        seen["processing_window_size"] = str(os.getenv("MINERU_PROCESSING_WINDOW_SIZE") or "")
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed", encoding="utf-8")

    monkeypatch.setenv("MINERU_HYBRID_BATCH_RATIO", "3")
    monkeypatch.setenv("MINERU_PROCESSING_WINDOW_SIZE", "8")
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert seen["hybrid_batch_ratio"] == "3"
    assert seen["processing_window_size"] == "8"


def test_pdf_to_md_first_step_reports_real_mineru_error_when_parse_raises(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    hooks = _Hooks()

    def fake_parse_doc_md_only(**_kwargs):
        raise ValueError("At least one submodule requires offload_folder")

    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config, hooks=hooks)

    assert md_path is None
    assert hooks.errors
    assert "offload_folder" in hooks.errors[-1]


def test_pdf_to_md_first_step_keeps_hybrid_error_by_default_when_offload_runtime_error(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: list[tuple[str, str, str]] = []

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen.append((backend, method, str(kwargs.get("lmdeploy_backend") or "")))
        if backend == "hybrid-auto-engine":
            raise ValueError(
                "At least one of the model submodule will be offloaded to disk, please pass along an `offload_folder`."
            )
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed via pipeline", encoding="utf-8")

    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path is None
    assert seen == [("hybrid-auto-engine", "auto", "pytorch")]


def test_pdf_to_md_first_step_retries_pipeline_only_when_explicitly_enabled(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: list[tuple[str, str, str]] = []

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen.append((backend, method, str(kwargs.get("lmdeploy_backend") or "")))
        if backend == "hybrid-auto-engine":
            raise ValueError(
                "At least one of the model submodule will be offloaded to disk, please pass along an `offload_folder`."
            )
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed via pipeline", encoding="utf-8")

    monkeypatch.setenv("DOC_VERIFICATION_ALLOW_MINERU_PIPELINE_FALLBACK", "1")
    monkeypatch.setattr(
        "langchain_app.services.parsing._mineru_pipeline_available",
        lambda: True,
    )
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert md_path.read_text(encoding="utf-8") == "# parsed via pipeline"
    assert seen == [
        ("hybrid-auto-engine", "auto", "pytorch"),
        ("pipeline", "auto", ""),
    ]


def test_pdf_to_md_first_step_retries_pipeline_on_cuda_oom_without_extra_flag(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: list[tuple[str, str, str]] = []

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen.append((backend, method, str(kwargs.get("lmdeploy_backend") or "")))
        if backend == "hybrid-auto-engine":
            raise RuntimeError("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 20.00 MiB")
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed via pipeline after oom", encoding="utf-8")

    monkeypatch.setattr(
        "langchain_app.services.parsing._mineru_pipeline_available",
        lambda: True,
    )
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert md_path.read_text(encoding="utf-8") == "# parsed via pipeline after oom"
    assert seen == [
        ("hybrid-auto-engine", "auto", "pytorch"),
        ("pipeline", "auto", ""),
    ]


def test_pdf_to_md_first_step_reports_cuda_oom_when_pipeline_backend_missing(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    hooks = _Hooks()

    def fake_parse_doc_md_only(**_kwargs):
        raise RuntimeError("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 20.00 MiB")

    monkeypatch.setattr(
        "langchain_app.services.parsing._mineru_pipeline_available",
        lambda: False,
    )
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config, hooks=hooks)

    assert md_path is None
    assert hooks.errors
    assert "out of memory" in hooks.errors[-1].lower()


def test_mineru_pipeline_available_requires_successful_import(monkeypatch):
    required_modules = {
        "mineru.backend.pipeline.pipeline_analyze",
        "mineru.backend.pipeline.pipeline_middle_json_mkcontent",
        "mineru.backend.pipeline.model_json_to_middle_json",
    }

    monkeypatch.setattr(
        "langchain_app.services.parsing.importlib.util.find_spec",
        lambda module_name: object() if module_name in required_modules else None,
    )

    def fake_import_module(module_name: str):
        if module_name == "mineru.backend.pipeline.pipeline_middle_json_mkcontent":
            raise ImportError("broken pipeline install")
        return object()

    monkeypatch.setattr(
        "langchain_app.services.parsing.importlib.import_module",
        fake_import_module,
    )

    assert _mineru_pipeline_available() is False


def test_pdf_to_md_first_step_retries_pipeline_on_windows_pagefile_error(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    seen: list[tuple[str, str, str]] = []

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        seen.append((backend, method, str(kwargs.get("lmdeploy_backend") or "")))
        if backend == "hybrid-auto-engine":
            raise OSError("页面文件太小，无法完成操作。 (os error 1455)")
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed via pipeline after pagefile", encoding="utf-8")

    monkeypatch.setattr(
        "langchain_app.services.parsing._mineru_pipeline_available",
        lambda: True,
    )
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert md_path.read_text(encoding="utf-8") == "# parsed via pipeline after pagefile"
    assert seen == [
        ("hybrid-auto-engine", "auto", "pytorch"),
        ("pipeline", "auto", ""),
    ]


def test_pdf_to_md_first_step_retries_hybrid_page_by_page_after_internal_engine_error(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    calls: list[tuple[str, int | None, int | None]] = []

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        start_page_id = kwargs.get("start_page_id")
        end_page_id = kwargs.get("end_page_id")
        calls.append((backend, start_page_id, end_page_id))
        md_path = Path(output_dir) / "sample.md"
        if start_page_id is None:
            print("ResponseType.INTERNAL_ENGINE_ERROR")
            md_path.write_text("# degraded", encoding="utf-8")
            return
        md_path.write_text(f"# page {start_page_id + 1}", encoding="utf-8")

    monkeypatch.setattr("langchain_app.services.parsing._count_pdf_pages", lambda _pdf_path: 3)
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert md_path.read_text(encoding="utf-8") == "# page 1\n\n# page 2\n\n# page 3"
    assert calls == [
        ("hybrid-auto-engine", None, None),
        ("hybrid-auto-engine", 0, 0),
        ("hybrid-auto-engine", 1, 1),
        ("hybrid-auto-engine", 2, 2),
    ]


def test_pdf_to_md_first_step_does_not_retry_pages_for_generic_warnings(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    calls: list[tuple[str, int | None, int | None]] = []

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        start_page_id = kwargs.get("start_page_id")
        end_page_id = kwargs.get("end_page_id")
        calls.append((backend, start_page_id, end_page_id))
        print("line does not match layout format: benign warning")
        md_path = Path(output_dir) / "sample.md"
        md_path.write_text("# parsed once", encoding="utf-8")

    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config)

    assert md_path == config.local_md_dir / "sample.md"
    assert md_path.read_text(encoding="utf-8") == "# parsed once"
    assert calls == [("hybrid-auto-engine", None, None)]


def test_pdf_to_md_first_step_rejects_output_when_page_retry_still_has_internal_engine_error(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    config.local_md_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    hooks = _Hooks()

    def fake_parse_doc_md_only(*, path_list, output_dir, lang, backend, method, **kwargs):
        start_page_id = kwargs.get("start_page_id")
        md_path = Path(output_dir) / "sample.md"
        if start_page_id is None:
            print("ResponseType.INTERNAL_ENGINE_ERROR")
            md_path.write_text("# degraded", encoding="utf-8")
            return
        if start_page_id == 1:
            print("ResponseType.INTERNAL_ENGINE_ERROR")
            md_path.write_text("# still bad", encoding="utf-8")
            return
        md_path.write_text(f"# page {start_page_id + 1}", encoding="utf-8")

    monkeypatch.setattr("langchain_app.services.parsing._count_pdf_pages", lambda _pdf_path: 3)
    fake_module = types.SimpleNamespace(parse_doc_md_only=fake_parse_doc_md_only)
    monkeypatch.setitem(sys.modules, "pdf_md", fake_module)

    md_path = pdf_to_md_first_step(pdf_path, config, hooks=hooks)

    assert md_path is None
    assert hooks.errors
    assert "page-level retry still failed" in hooks.errors[-1]
