from pathlib import Path

from langchain_app.graph.nodes import parse_json as parse_json_module
from langchain_app.graph.state import create_initial_state
from langchain_app.utils.config import AppConfig


def test_parse_json_node_passes_shared_llm_client_to_md_parser(tmp_path, monkeypatch):
    seen = {}
    sentinel_llm = object()
    sentinel_hooks = object()
    config = AppConfig(
        root_dir=tmp_path,
        api_key="test-key",
        api_base="https://api.example.com",
        model="deepseek-chat",
        temperature=0.0,
        max_tokens=256,
        topk=20,
        batch_size=2,
        max_workers=1,
        embed_model_path=str(tmp_path / "models"),
        cnas_db_dir=str(tmp_path / "vector_db" / "cnas"),
        temperature_db_dir=str(tmp_path / "vector_db" / "temperature"),
        general_cycle_db_dir=str(tmp_path / "vector_db" / "general"),
        huawei_cycle_db_dir=str(tmp_path / "vector_db" / "huawei"),
        address_db_dir=str(tmp_path / "vector_db" / "address"),
        cnas_collection="calibration_data",
        address_collection="calibration_address",
        default_cycle="12个月",
        use_llm_verification=True,
        use_llm_location_check=True,
        must_match_threshold=0.45,
        optional_match_threshold=0.45,
        llm_temperature=0.0,
        llm_max_tokens=256,
        local_pdf_dir=tmp_path / "local_pdf",
        local_md_dir=tmp_path / "local_md",
        local_json_dir=tmp_path / "local_json",
        final_reports_dir=tmp_path / "final_reports",
        reports_dir=tmp_path / "reports",
    ).ensure_directories()
    md_path = config.local_md_dir / "sample.md"
    md_path.write_text("# sample\n中国认可国际互认校准 CALIBRATION CNASL13344\n证书编号：TEST-001\n", encoding="utf-8")

    def fake_parse_md_to_json(md_path_arg, out_dir_arg, *, llm_client=None, allow_llm_fallback=False, hooks=None):
        seen["llm_client"] = llm_client
        seen["allow_llm_fallback"] = allow_llm_fallback
        seen["hooks"] = hooks
        hooks.parser_progress_callback("meta_extract_start", 0, 1, "头部信息解析")
        hooks.parser_progress_callback("meta_extract_done", 1, 1, "头部信息解析完成")
        json_path = Path(out_dir_arg) / "sample.json"
        json_path.write_text('{"__parameter_contract_schema_version": 2, "properties": {"证书列表": {"items": {"properties": {}}}}, "依据参数_中间数据": []}', encoding="utf-8")
        return json_path

    monkeypatch.setattr(parse_json_module, "parse_md_to_json", fake_parse_md_to_json)

    state = create_initial_state(config=config, llm_client=sentinel_llm, hooks=sentinel_hooks)
    state.md_path = str(md_path)
    updated = parse_json_module.parse_json_node(state)

    assert updated.json_path == str(config.local_json_dir / "sample.json")
    assert seen["llm_client"] is sentinel_llm
    assert seen["allow_llm_fallback"] is True
    assert seen["hooks"] is not None


def test_parse_json_node_records_failure_section_on_exception(tmp_path, monkeypatch):
    config = AppConfig(
        root_dir=tmp_path,
        api_key="test-key",
        api_base="https://api.example.com",
        model="deepseek-chat",
        temperature=0.0,
        max_tokens=256,
        topk=20,
        batch_size=2,
        max_workers=1,
        embed_model_path=str(tmp_path / "models"),
        cnas_db_dir=str(tmp_path / "vector_db" / "cnas"),
        temperature_db_dir=str(tmp_path / "vector_db" / "temperature"),
        general_cycle_db_dir=str(tmp_path / "vector_db" / "general"),
        huawei_cycle_db_dir=str(tmp_path / "vector_db" / "huawei"),
        address_db_dir=str(tmp_path / "vector_db" / "address"),
        cnas_collection="calibration_data",
        address_collection="calibration_address",
        default_cycle="12个月",
        use_llm_verification=True,
        use_llm_location_check=True,
        must_match_threshold=0.45,
        optional_match_threshold=0.45,
        llm_temperature=0.0,
        llm_max_tokens=256,
        local_pdf_dir=tmp_path / "local_pdf",
        local_md_dir=tmp_path / "local_md",
        local_json_dir=tmp_path / "local_json",
        final_reports_dir=tmp_path / "final_reports",
        reports_dir=tmp_path / "reports",
    ).ensure_directories()
    md_path = config.local_md_dir / "sample.md"
    md_path.write_text("# sample\n中国认可国际互认校准 CALIBRATION CNASL13344\n证书编号：TEST-001\n", encoding="utf-8")

    def fake_parse_md_to_json(*args, **kwargs):
        raise RuntimeError("parser boom")

    monkeypatch.setattr(parse_json_module, "parse_md_to_json", fake_parse_md_to_json)

    state = create_initial_state(config=config)
    state.md_path = str(md_path)
    updated = parse_json_module.parse_json_node(state)

    assert updated.should_stop is True
    assert any("## MD -> JSON 失败" in section for section in updated.report_sections)
