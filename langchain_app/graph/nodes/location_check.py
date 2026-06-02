#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Location check graph node.
"""

from langchain_app.checks import check_location
from langchain_app.graph.state import VerificationState


def location_check_node(state: VerificationState) -> VerificationState:
    if state.should_stop:
        return state
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [4/6]: Location check")
    state.emit_progress(65)
    state.set_progress(0.85, "校准地点核验")
    state.add_log("开始校准地点核验")

    try:
        report = check_location(
            state.json_path,
            cfg=state.config,
            stop_event=state.stop_event,
            embedder_obj=state.embedder,
            llm_client=state.llm_client,
        )
        state.location_result = report
        state.add_report_section(report)
        state.emit_success("Location check completed")
        state.set_progress(0.9, "校准地点核验完成")
        state.add_log("校准地点核验完成")
        return state
    except Exception as exc:
        state.emit_warning(f"Location check failed: {exc}")
        state.add_report_section(f"## 地点核验异常\n> Error: {exc}\n")
        state.set_progress(0.9, "校准地点核验异常")
        return state
