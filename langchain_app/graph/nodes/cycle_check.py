#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cycle check graph node.
"""

from langchain_app.checks import check_cycle_reasonableness
from langchain_app.graph.state import VerificationState


def cycle_check_node(state: VerificationState) -> VerificationState:
    if state.should_stop:
        return state
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [5/6]: Cycle check")
    state.emit_progress(70)
    state.set_progress(0.95, "校准周期核验")
    state.add_log("开始校准周期核验")

    try:
        report = check_cycle_reasonableness(
            state.json_path,
            cfg=state.config,
            stop_event=state.stop_event,
            embedder_obj=state.embedder,
            llm_client=state.llm_client,
        )
        state.cycle_result = report
        state.add_report_section(report)
        state.set_progress(0.98, "校准周期核验完成")
        state.add_log("校准周期核验完成")
        return state
    except Exception as exc:
        state.emit_warning(f"Cycle check failed: {exc}")
        state.add_report_section(f"## 周期核验异常\n> Error: {exc}\n")
        state.set_progress(0.98, "校准周期核验异常")
        return state
