import json
import sys
import types
from pathlib import Path

import md_parser_no_llm

from langchain_app.checks.integrity import (
    build_non_cnas_skip_report,
    check_certificate_integrity,
    is_explicit_non_cnas_flag,
    normalize_cnas_flag,
)
from langchain_app.graph import verification_graph
from langchain_app.graph.nodes import parse_pdf as parse_pdf_module
from langchain_app.graph.nodes import parse_json as parse_json_module
from langchain_app.graph.state import create_initial_state
from langchain_app.services import parsing as parsing_module
from langchain_app.utils.config import AppConfig


def _build_config(tmp_path):
    return AppConfig(
        root_dir=tmp_path,
        api_key="test-key",
        api_base="https://api.example.com",
        model="deepseek-chat",
        temperature=0.0,
        max_tokens=256,
        topk=5,
        batch_size=1,
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
        use_llm_verification=False,
        use_llm_location_check=False,
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


def test_non_cnas_report_uses_skip_wording(tmp_path):
    config = _build_config(tmp_path)
    json_path = config.local_json_dir / "sample.json"
    json_path.write_text(
        json.dumps(
            {
                "properties": {
                    "证书列表": {
                        "items": {
                            "properties": {
                                "证书编号": "TEST-001",
                                "CNAS": "否",
                            }
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = check_certificate_integrity(str(json_path), cfg=config)

    assert "# [跳过] 非CNAS文件，跳过核验" in report
    assert "当前文件跳过后续核验流程" in report
    assert "系统拒绝处理" not in report


def test_normalize_cnas_flag_treats_missing_value_as_unknown():
    assert normalize_cnas_flag({}) == "N/A"
    assert is_explicit_non_cnas_flag(normalize_cnas_flag({})) is False


def test_parse_json_node_skips_non_cnas_md_before_json_parse(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    md_path = config.local_md_dir / "sample.md"
    md_path.write_text(
        "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-002",
                "非CNAS认可范围的技术依据：JJF 1922-2021",
            ]
        ),
        encoding="utf-8",
    )

    called = {"parse": False}

    def fake_parse_md_to_json(*args, **kwargs):
        called["parse"] = True
        raise AssertionError("should not parse json for non-cnas md")

    monkeypatch.setattr(parse_json_module, "parse_md_to_json", fake_parse_md_to_json)

    state = create_initial_state(config=config)
    state.source_pdf_path = str(config.local_pdf_dir / "sample.pdf")
    state.md_path = str(md_path)
    updated = parse_json_module.parse_json_node(state)

    assert updated.should_stop is True
    assert called["parse"] is False
    report = "\n".join(updated.report_sections)
    assert build_non_cnas_skip_report(
        source_name="sample.pdf",
        cert_no="TEST-002",
        is_cnas="否",
    ) in report


def test_parse_json_node_does_not_skip_when_cnas_is_unknown(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    md_path = config.local_md_dir / "sample.md"
    md_path.write_text(
        "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-UNKNOWN",
                "委托单位：示例公司",
                "型号：ABC-1",
            ]
        ),
        encoding="utf-8",
    )

    def fake_parse_md_to_json(_md_path, out_dir, **kwargs):
        json_path = Path(out_dir) / "sample.json"
        json_path.write_text("{}", encoding="utf-8")
        return {}

    monkeypatch.setattr(parse_json_module, "parse_md_to_json", fake_parse_md_to_json)

    state = create_initial_state(config=config)
    state.source_pdf_path = str(config.local_pdf_dir / "sample.pdf")
    state.md_path = str(md_path)
    updated = parse_json_module.parse_json_node(state)

    assert updated.should_stop is False
    assert updated.json_path == str(config.local_json_dir / "sample.json")
    report = "\n".join(updated.report_sections)
    assert "# [跳过] 非CNAS文件，跳过核验" not in report


def test_parse_pdf_node_skips_non_cnas_before_md_parse(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    pdf_path = config.local_pdf_dir / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    called = {"parse_pdf": False}

    def fake_probe_pdf_header_meta(_pdf_path, _config=None, hooks=None, lang="ch"):
        return {
            "证书编号": "TEST-001A",
            "CNAS": "否",
        }

    def fake_pdf_to_md_first_step(*args, **kwargs):
        called["parse_pdf"] = True
        raise AssertionError("should not parse markdown for non-cnas pdf")

    monkeypatch.setattr(parse_pdf_module, "probe_pdf_header_meta", fake_probe_pdf_header_meta)
    monkeypatch.setattr(parse_pdf_module, "pdf_to_md_first_step", fake_pdf_to_md_first_step)

    state = create_initial_state(pdf_path=str(pdf_path), config=config)
    updated = parse_pdf_module.parse_pdf_node(state)

    assert updated.should_stop is True
    assert called["parse_pdf"] is False
    assert updated.report_sections == [
        build_non_cnas_skip_report(
            source_name="sample.pdf",
            cert_no="TEST-001A",
            is_cnas="否",
        )
    ]


def test_parse_pdf_node_continues_when_probe_cnas_is_unknown(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    pdf_path = config.local_pdf_dir / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    md_path = config.local_md_dir / "sample.md"

    def fake_probe_pdf_header_meta(_pdf_path, _config=None, hooks=None, lang="ch"):
        return {"证书编号": "TEST-UNKNOWN"}

    def fake_pdf_to_md_first_step(*args, **kwargs):
        md_path.write_text("# md", encoding="utf-8")
        return md_path

    monkeypatch.setattr(parse_pdf_module, "probe_pdf_header_meta", fake_probe_pdf_header_meta)
    monkeypatch.setattr(parse_pdf_module, "pdf_to_md_first_step", fake_pdf_to_md_first_step)

    state = create_initial_state(pdf_path=str(pdf_path), config=config)
    updated = parse_pdf_module.parse_pdf_node(state)

    assert updated.should_stop is False
    assert updated.md_path == str(md_path)
    assert updated.report_sections == ["## PDF -> MD 成功\n> 生成 MD: `sample.md`"]


def test_probe_pdf_header_meta_falls_back_to_mineru_first_page(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    pdf_path = config.local_pdf_dir / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(parsing_module, "_extract_pdf_header_text", lambda _pdf_path: "")
    monkeypatch.setattr(parsing_module, "_is_trustworthy_pdf_header_probe", lambda text: bool(text))
    monkeypatch.setattr(
        parsing_module,
        "_extract_pdf_header_text_with_mineru_probe",
        lambda _pdf_path, _config, hooks=None, lang="ch": "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-005",
                "委托单位：示例公司",
                "型号：ABC-1",
            ]
        ),
    )
    monkeypatch.setattr(
        parsing_module,
        "_extract_meta_from_header_text",
        lambda header_text: {"证书编号": "TEST-005", "CNAS": "否"} if header_text else {},
    )

    meta = parsing_module.probe_pdf_header_meta(pdf_path, config)

    assert meta["证书编号"] == "TEST-005"
    assert normalize_cnas_flag(meta) == "否"


def test_extract_meta_from_text_empty_input_does_not_default_to_non_cnas():
    meta = md_parser_no_llm.extract_meta_from_text("")

    assert normalize_cnas_flag(meta) == "N/A"


def test_verification_graph_short_circuits_non_cnas_before_integrity(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    called = {"integrity": False}
    end_token = "__end__"

    class FakeCompiledGraph:
        def __init__(self, nodes, edges, conditional_edges, entry_point):
            self._nodes = nodes
            self._edges = edges
            self._conditional_edges = conditional_edges
            self._entry_point = entry_point

        def invoke(self, state):
            current = self._entry_point
            while current != end_token:
                state = self._nodes[current](state)
                if current in self._conditional_edges:
                    router, _mapping = self._conditional_edges[current]
                    current = router(state)
                else:
                    current = self._edges[current]
            return state

    class FakeStateGraph:
        def __init__(self, _state_type):
            self._nodes = {}
            self._edges = {}
            self._conditional_edges = {}
            self._entry_point = None

        def add_node(self, name, fn):
            self._nodes[name] = fn

        def set_entry_point(self, name):
            self._entry_point = name

        def add_edge(self, src, dst):
            self._edges[src] = dst

        def add_conditional_edges(self, src, router, mapping):
            self._conditional_edges[src] = (router, mapping)

        def compile(self):
            return FakeCompiledGraph(
                self._nodes,
                self._edges,
                self._conditional_edges,
                self._entry_point,
            )

    def fake_parse_pdf_node(state):
        state.add_report_section("## PDF -> MD 成功\n> 生成 MD: `sample.md`\n")
        return state

    def fake_parse_json_node(state):
        state.add_report_section(
            build_non_cnas_skip_report(
                source_name="sample.pdf",
                cert_no="TEST-003",
                is_cnas="否",
            )
        )
        state.should_stop = True
        return state

    def fake_integrity_check_node(state):
        called["integrity"] = True
        return state

    monkeypatch.setattr(verification_graph, "parse_pdf_node", fake_parse_pdf_node)
    monkeypatch.setattr(verification_graph, "parse_json_node", fake_parse_json_node)
    monkeypatch.setattr(verification_graph, "integrity_check_node", fake_integrity_check_node)
    fake_langgraph = types.ModuleType("langgraph.graph")
    fake_langgraph.END = end_token
    fake_langgraph.StateGraph = FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", types.ModuleType("langgraph"))
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_langgraph)

    state = create_initial_state(pdf_path=str(config.local_pdf_dir / "sample.pdf"), config=config)
    final_state = verification_graph.run_verification_graph(state)

    assert called["integrity"] is False
    assert final_state.final_report is not None
    assert "# [跳过] 非CNAS文件，跳过核验" in final_state.final_report
    assert "## PDF -> MD 成功" not in final_state.final_report


def test_verification_graph_short_circuits_non_cnas_before_parse_json(tmp_path, monkeypatch):
    config = _build_config(tmp_path)
    called = {"parse_json": False}
    end_token = "__end__"

    class FakeCompiledGraph:
        def __init__(self, nodes, edges, conditional_edges, entry_point):
            self._nodes = nodes
            self._edges = edges
            self._conditional_edges = conditional_edges
            self._entry_point = entry_point

        def invoke(self, state):
            current = self._entry_point
            while current != end_token:
                state = self._nodes[current](state)
                if current in self._conditional_edges:
                    router, _mapping = self._conditional_edges[current]
                    current = router(state)
                else:
                    current = self._edges[current]
            return state

    class FakeStateGraph:
        def __init__(self, _state_type):
            self._nodes = {}
            self._edges = {}
            self._conditional_edges = {}
            self._entry_point = None

        def add_node(self, name, fn):
            self._nodes[name] = fn

        def set_entry_point(self, name):
            self._entry_point = name

        def add_edge(self, src, dst):
            self._edges[src] = dst

        def add_conditional_edges(self, src, router, mapping):
            self._conditional_edges[src] = (router, mapping)

        def compile(self):
            return FakeCompiledGraph(
                self._nodes,
                self._edges,
                self._conditional_edges,
                self._entry_point,
            )

    def fake_parse_pdf_node(state):
        state.add_report_section(
            build_non_cnas_skip_report(
                source_name="sample.pdf",
                cert_no="TEST-004",
                is_cnas="否",
            )
        )
        state.should_stop = True
        return state

    def fake_parse_json_node(state):
        called["parse_json"] = True
        return state

    monkeypatch.setattr(verification_graph, "parse_pdf_node", fake_parse_pdf_node)
    monkeypatch.setattr(verification_graph, "parse_json_node", fake_parse_json_node)
    fake_langgraph = types.ModuleType("langgraph.graph")
    fake_langgraph.END = end_token
    fake_langgraph.StateGraph = FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", types.ModuleType("langgraph"))
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_langgraph)

    state = create_initial_state(pdf_path=str(config.local_pdf_dir / "sample.pdf"), config=config)
    final_state = verification_graph.run_verification_graph(state)

    assert called["parse_json"] is False
    assert final_state.final_report is not None
    assert "# [跳过] 非CNAS文件，跳过核验" in final_state.final_report
