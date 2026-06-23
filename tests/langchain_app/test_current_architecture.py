#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Current LangGraph/LangChain architecture smoke checks."""

from __future__ import annotations


def collect_architecture_status() -> dict:
    """Return the import/build status used by both pytest and direct script runs."""
    from langchain_app.checks import (
        check_certificate_integrity,
        check_cycle_reasonableness,
        check_environment,
        check_location,
    )
    from langchain_app.core import LLMClient
    from langchain_app.core.pipeline import run_verification
    from langchain_app.graph import build_verification_graph
    from langchain_app.services.parsing import pdf_to_md_first_step
    from langchain_app.tools import get_all_tools
    from langchain_app.utils import get_app_config

    config = get_app_config()
    graph = build_verification_graph()
    compiled_graph = graph.compile()
    tools = get_all_tools()

    return {
        "config": config,
        "compiled_graph": compiled_graph,
        "tools": tools,
        "tool_names": [tool.name for tool in tools],
        "imports": {
            "LLMClient": LLMClient,
            "run_verification": run_verification,
            "pdf_to_md_first_step": pdf_to_md_first_step,
            "check_certificate_integrity": check_certificate_integrity,
            "check_environment": check_environment,
            "check_location": check_location,
            "check_cycle_reasonableness": check_cycle_reasonableness,
        },
    }


def test_current_architecture_imports_and_builds():
    status = collect_architecture_status()

    assert status["config"].model
    assert status["compiled_graph"] is not None
    assert status["tool_names"] == [
        "parse_pdf_to_md",
        "parse_md_to_json",
        "info_check",
        "environment_check",
        "location_check",
        "cycle_check",
        "parameter_check",
    ]
    assert all(status["imports"].values())


if __name__ == "__main__":
    status = collect_architecture_status()
    print("=" * 60)
    print("测试当前 LangGraph/LangChain 架构的基本功能")
    print("=" * 60)
    print(f"[OK] 配置加载成功: root={status['config'].root_dir}")
    print(f"[OK] 模型: {status['config'].model}")
    print("[OK] Graph 构建和编译成功")
    print(f"[OK] 工具加载成功，共 {len(status['tools'])} 个工具")
    for tool_name in status["tool_names"]:
        print(f"  - {tool_name}")
    print("[OK] langchain_app 主线模块导入成功")
