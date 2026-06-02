#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment check graph node.
"""

from langchain_app.checks import check_environment
from langchain_app.graph.state import VerificationState


def environment_check_node(state: VerificationState) -> VerificationState:
    if state.should_stop:
        return state
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [3/6]: Environment check")
    state.emit_progress(50)
    state.set_progress(0.7, "环境条件核验")
    state.add_log("开始环境条件核验")

    try:
        report = check_environment(
            state.json_path,
            cfg=state.config,
            stop_event=state.stop_event,
            embedder_obj=state.embedder,
            llm_client=state.llm_client,
        )
        state.environment_result = report
        state.add_report_section(report)
        state.set_progress(0.8, "环境条件核验完成")
        state.add_log("环境条件核验完成")
        return state
    except Exception as exc:
        state.emit_warning(f"Environment check failed: {exc}")
        state.add_report_section(f"## 环境核验异常\n> Error: {exc}\n")
        state.set_progress(0.8, "环境条件核验异常")
        return state
