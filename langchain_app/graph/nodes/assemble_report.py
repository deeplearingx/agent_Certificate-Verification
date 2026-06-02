#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final report assembly node.
"""

import time
from pathlib import Path

from langchain_app.core.report_generator import build_verification_report_header
from langchain_app.graph.state import VerificationState


def _select_report_sections(state: VerificationState) -> list[str]:
    skip_marker = "# [跳过] 非CNAS文件，跳过核验"
    for section in reversed(state.report_sections):
        if skip_marker in section:
            return [section]
    return list(state.report_sections)


def assemble_report_node(state: VerificationState) -> VerificationState:
    state.set_progress(1.0, "报告组装")
    state.add_log("开始报告组装")

    try:
        report = build_verification_report_header(
            source_name=Path(state.source_pdf_path).name if state.source_pdf_path else "",
            verified_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            model=getattr(state.config, "model", ""),
            temperature=getattr(state.config, "temperature", 0.0),
            topk=getattr(state.config, "topk", 3),
        )

        for idx, section in enumerate(_select_report_sections(state)):
            report.add_section(section, prepend_divider=idx > 0)

        state.final_report = report.render()
        state.emit_status("Verification completed")
        state.emit_progress(100)
        state.set_progress(1.0, "报告组装完成")
        state.add_log("报告组装完成")
        return state
    except Exception as exc:
        state.emit_error(f"报告组装失败: {exc}")
        state.set_progress(1.0, "报告组装失败")
        return state


def assemble_report_from_results(results) -> str:
    report = build_verification_report_header(
        source_name="",
        verified_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        model="",
        temperature=0.0,
        topk=3,
    )
    for idx, section in enumerate(results.values()):
        if section:
            report.add_section(section, prepend_divider=idx > 0)
    return report.render()
