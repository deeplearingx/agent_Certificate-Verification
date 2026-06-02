#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph verification pipeline graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from langchain_app.graph.nodes.assemble_report import assemble_report_node
from langchain_app.graph.nodes.cycle_check import cycle_check_node
from langchain_app.graph.nodes.environment_check import environment_check_node
from langchain_app.graph.nodes.integrity_check import integrity_check_node
from langchain_app.graph.nodes.location_check import location_check_node
from langchain_app.graph.nodes.parameter_check import parameter_check_node
from langchain_app.graph.nodes.parse_json import parse_json_node
from langchain_app.graph.nodes.parse_pdf import parse_pdf_node
from langchain_app.graph.routers import (
    after_cycle_check,
    after_environment_check,
    after_integrity_check,
    after_location_check,
    after_parameter_check,
    after_parse_json,
    check_should_stop,
)
from langchain_app.graph.state import VerificationState, create_initial_state


def _coerce_state_result(result: Any, fallback: VerificationState) -> VerificationState:
    if isinstance(result, VerificationState):
        return result
    if isinstance(result, dict):
        try:
            if hasattr(VerificationState, "model_validate"):
                return VerificationState.model_validate(result)
            return VerificationState.parse_obj(result)
        except Exception as exc:
            fallback.add_error(f"Graph result could not be converted to VerificationState: {exc}")
            return fallback
    fallback.add_error(f"Graph returned unexpected state type: {type(result).__name__}")
    return fallback


def build_verification_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(VerificationState)
    graph.add_node("parse_pdf", parse_pdf_node)
    graph.add_node("parse_json", parse_json_node)
    graph.add_node("integrity_check", integrity_check_node)
    graph.add_node("environment_check", environment_check_node)
    graph.add_node("location_check", location_check_node)
    graph.add_node("cycle_check", cycle_check_node)
    graph.add_node("parameter_check", parameter_check_node)
    graph.add_node("assemble_report", assemble_report_node)

    graph.set_entry_point("parse_pdf")
    graph.add_conditional_edges(
        "parse_pdf",
        check_should_stop,
        {
            "assemble_report": "assemble_report",
            "parse_json": "parse_json",
        },
    )
    graph.add_conditional_edges(
        "parse_json",
        after_parse_json,
        {
            "assemble_report": "assemble_report",
            "integrity_check": "integrity_check",
        },
    )
    graph.add_conditional_edges(
        "integrity_check",
        after_integrity_check,
        {
            "assemble_report": "assemble_report",
            "environment_check": "environment_check",
        },
    )
    graph.add_conditional_edges(
        "environment_check",
        after_environment_check,
        {
            "assemble_report": "assemble_report",
            "location_check": "location_check",
        },
    )
    graph.add_conditional_edges(
        "location_check",
        after_location_check,
        {
            "assemble_report": "assemble_report",
            "cycle_check": "cycle_check",
        },
    )
    graph.add_conditional_edges(
        "cycle_check",
        after_cycle_check,
        {
            "assemble_report": "assemble_report",
            "parameter_check": "parameter_check",
        },
    )
    graph.add_conditional_edges(
        "parameter_check",
        after_parameter_check,
        {
            "assemble_report": "assemble_report",
        },
    )
    graph.add_edge("assemble_report", END)
    return graph


def create_graph():
    return build_verification_graph().compile()


def run_verification_graph(initial_state: VerificationState) -> VerificationState:
    try:
        graph = create_graph()
        return _coerce_state_result(graph.invoke(initial_state), initial_state)
    except Exception as exc:
        print(f"Graph执行失败: {exc}")
        import traceback

        traceback.print_exc()
        initial_state.add_error(f"Graph执行失败: {exc}")
        return initial_state


def run_verification_graph_with_config(
    pdf_path: str,
    config: Any,
    embedder: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    hooks: Optional[Any] = None,
    stop_event=None,
) -> Optional[str]:
    from langchain_app.core import create_llm_client, load_shared_embedder

    if embedder is None:
        embedder = load_shared_embedder(str(config.embed_model_path))

    if llm_client is None:
        try:
            llm_client = create_llm_client(config)
        except Exception:
            llm_client = None

    state = create_initial_state(
        pdf_path=pdf_path,
        config=config,
        embedder=embedder,
        llm_client=llm_client,
        hooks=hooks,
        stop_event=stop_event,
    )

    result = _coerce_state_result(run_verification_graph(state), state)
    return result.final_report if result.final_report else None


def build_graph():
    return build_verification_graph()
