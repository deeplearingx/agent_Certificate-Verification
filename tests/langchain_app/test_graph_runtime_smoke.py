#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Graph runtime smoke test.

This test executes the verification graph with lightweight stub nodes so we can
verify the graph wiring and final report assembly without depending on external
services or real PDF/JSON parsing.
"""

import sys
from pathlib import Path

# Add project root to import path. This file lives in tests/langchain_app/.
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Set UTF-8 output on Windows
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)

from langchain_app.graph.state import create_initial_state
import langchain_app.graph.verification_graph as verification_graph
from langchain_app.utils import AppConfig


def _stub_parse_pdf(state):
    state.md_path = "stub.md"
    state.add_log("stub parse_pdf")
    state.add_report_section("## PDF -> MD 成功\n> 生成 MD: `stub.md`\n")
    return state


def _stub_parse_json(state):
    state.json_path = "stub.json"
    state.add_log("stub parse_json")
    state.add_report_section("## MD 解析成功\n> 生成 JSON: `stub.json`\n")
    return state


def _stub_integrity(state):
    state.integrity_result = "integrity ok"
    state.add_report_section("integrity ok")
    return state


def _stub_environment(state):
    state.environment_result = "environment ok"
    state.add_report_section("environment ok")
    return state


def _stub_location(state):
    state.location_result = "location ok"
    state.add_report_section("location ok")
    return state


def _stub_cycle(state):
    state.cycle_result = "cycle ok"
    state.add_report_section("cycle ok")
    return state


def _stub_parameter(state):
    state.parameter_result = "parameter ok"
    state.add_report_section("parameter ok")
    return state


def _build_config(root_dir: Path) -> AppConfig:
    return AppConfig(
        root_dir=root_dir,
        api_key="test-key",
        api_base="https://api.example.com",
        model="smoke-model",
        temperature=0.1,
        max_tokens=1024,
        topk=3,
        batch_size=2,
        max_workers=1,
        embed_model_path=str(root_dir / "models"),
        cnas_db_dir=str(root_dir / "vector_db" / "cnas_calibration"),
        temperature_db_dir=str(root_dir / "vector_db" / "temperature"),
        general_cycle_db_dir=str(root_dir / "vector_db" / "general_cycle"),
        huawei_cycle_db_dir=str(root_dir / "vector_db" / "huawei_cycle"),
        address_db_dir=str(root_dir / "vector_db" / "address"),
        cnas_collection="calibration_data",
        address_collection="calibration_address",
        default_cycle="12个月",
        use_llm_verification=True,
        use_llm_location_check=True,
        must_match_threshold=0.45,
        optional_match_threshold=0.4,
        llm_temperature=0.0,
        llm_max_tokens=256,
        local_pdf_dir=root_dir / "local_pdf",
        local_md_dir=root_dir / "local_md",
        local_json_dir=root_dir / "local_json",
        final_reports_dir=root_dir / "final_reports",
        reports_dir=root_dir / "reports",
    )


def run_graph_runtime_smoke_test():
    """Build and invoke the verification graph with stubbed nodes."""
    print("=" * 60)
    print("Graph Runtime Smoke Test")
    print("=" * 60)
    print()

    original_nodes = {
        "parse_pdf_node": verification_graph.parse_pdf_node,
        "parse_json_node": verification_graph.parse_json_node,
        "integrity_check_node": verification_graph.integrity_check_node,
        "environment_check_node": verification_graph.environment_check_node,
        "location_check_node": verification_graph.location_check_node,
        "cycle_check_node": verification_graph.cycle_check_node,
        "parameter_check_node": verification_graph.parameter_check_node,
    }

    verification_graph.parse_pdf_node = _stub_parse_pdf
    verification_graph.parse_json_node = _stub_parse_json
    verification_graph.integrity_check_node = _stub_integrity
    verification_graph.environment_check_node = _stub_environment
    verification_graph.location_check_node = _stub_location
    verification_graph.cycle_check_node = _stub_cycle
    verification_graph.parameter_check_node = _stub_parameter

    try:
        print("正在创建、编译并执行验证图...")
        graph = verification_graph.build_verification_graph().compile()
        print("[OK] 验证图编译成功")
        print(f"  节点数: {len(graph.nodes)}")
        print(f"  节点列表: {list(graph.nodes.keys())}")

        config = _build_config(project_root / ".graph_runtime_smoke")

        initial_state = create_initial_state(
            pdf_path="smoke.pdf",
            config=config,
            embedder=None,
            llm_client=None,
        )

        final_state = graph.invoke(initial_state)
        print("[OK] 验证图执行成功")

        if isinstance(final_state, dict):
            errors = final_state.get("errors", [])
            final_report = final_state.get("final_report")
        else:
            errors = getattr(final_state, "errors", [])
            final_report = getattr(final_state, "final_report", None)

        if errors:
            print(f"[FAIL] Graph 执行出现错误: {errors}")
            return False

        if not final_report:
            print("[FAIL] final_report 为空")
            return False

        required_sections = [
            "integrity ok",
            "environment ok",
            "location ok",
            "cycle ok",
            "parameter ok",
        ]
        missing = [section for section in required_sections if section not in final_report]
        if missing:
            print(f"[FAIL] 报告缺少章节内容: {missing}")
            return False

        print("[OK] final_report 已生成，且包含所有预期章节")
        print()
        print("=" * 60)
        print("[OK] 所有验证通过！Graph 运行测试成功。")
        return True

    except Exception as exc:
        print(f"[FAIL] Graph 运行测试失败: {exc}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        for name, fn in original_nodes.items():
            setattr(verification_graph, name, fn)


if __name__ == "__main__":
    try:
        success = run_graph_runtime_smoke_test()
        sys.exit(0 if success else 1)
    except Exception as exc:
        print(f"\n[FAIL] 测试失败: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
