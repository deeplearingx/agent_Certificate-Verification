#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameter check graph node.
"""

from langchain_app.checks import check_parameters, run_llm_mode
from langchain_app.graph.state import VerificationState


def parameter_check_node(state: VerificationState) -> VerificationState:
    if state.should_stop:
        return state
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [6/6]: Parameter check")
    state.emit_progress(90)
    state.set_progress(0.99, "参数与不确定度核验")
    state.add_log("开始参数与不确定度核验")

    try:
        report = check_parameters(
            state.json_path,
            cfg=state.config,
            stop_event=state.stop_event,
            embedder_obj=state.embedder,
            llm_client=state.llm_client,
        )
        state.parameter_result = report
        state.add_report_section(report)
        state.set_progress(1.0, "参数与不确定度核验完成")
        state.add_log("参数与不确定度核验完成")
        return state
    except Exception as exc:
        state.emit_error(f"Parameter check failed: {exc}")
        state.add_report_section(f"## 参数核验异常\n> Error: {exc}\n")
        state.set_progress(1.0, "参数与不确定度核验异常")
        return state
