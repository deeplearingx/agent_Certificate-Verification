#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrity check graph node.
"""

from langchain_app.checks import check_certificate_integrity
from langchain_app.graph.state import VerificationState


def integrity_check_node(state: VerificationState) -> VerificationState:
    if state.should_stop:
        return state
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [2/6]: Integrity check")
    state.emit_progress(30)
    state.set_progress(0.5, "完整性核验")
    state.add_log("开始完整性核验")

    try:
        report = check_certificate_integrity(
            state.json_path,
            cfg=state.config,
            stop_event=state.stop_event,
            embedder_obj=state.embedder,
            llm_client=state.llm_client,
        )
        state.integrity_result = report
        state.add_report_section(report)
        if any(token in report for token in ("# [终止]", "## [终止]", "# [跳过]", "## [跳过]", "终止", "跳过核验")):
            state.should_stop = True
            state.emit_status("Processing [2/6]: Integrity check (当前文件终止)")
            state.emit_warning("当前文件非 CNAS，跳过当前文件核验并继续后续文件")
        else:
            state.emit_success("Integrity check completed")
        state.set_progress(0.6, "完整性核验完成")
        state.add_log("完整性核验完成")
        return state
    except Exception as exc:
        state.emit_error(f"Integrity check failed: {exc}")
        state.add_report_section(f"## 完整性核验异常\n> Error: {exc}\n")
        state.set_progress(0.6, "完整性核验异常")
        state.should_stop = True
        return state
