#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF -> Markdown graph node.
"""

from pathlib import Path
from typing import Optional

from langchain_app.checks.integrity import (
    build_non_cnas_skip_report,
    is_explicit_non_cnas_flag,
    normalize,
    normalize_cnas_flag,
)
from langchain_app.graph.state import VerificationState
from langchain_app.services.parsing import pdf_to_md_first_step, probe_pdf_header_meta


def parse_pdf_node(state: VerificationState) -> VerificationState:
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [0/7]: PDF -> MD")
    state.emit_progress(3)
    state.set_progress(0.1, "PDF解析")
    state.add_log("开始PDF解析")

    try:
        pdf_path = Path(state.source_pdf_path)
        preflight_meta = probe_pdf_header_meta(pdf_path, state.config, hooks=state.hooks, lang="ch")
        if preflight_meta:
            preflight_is_cnas = normalize_cnas_flag(preflight_meta)
            if is_explicit_non_cnas_flag(preflight_is_cnas):
                cert_no = normalize(preflight_meta.get("证书编号"))
                state.add_report_section(
                    build_non_cnas_skip_report(
                        source_name=pdf_path.name,
                        cert_no=cert_no,
                        is_cnas=preflight_is_cnas,
                    )
                )
                state.emit_status("Processing [0/7]: PDF -> MD (非CNAS跳过)")
                state.emit_warning("从 PDF 页眉识别为非 CNAS，跳过当前文件后续核验")
                state.should_stop = True
                state.set_progress(0.1, "非CNAS跳过")
                state.add_log("PDF页眉预判为非CNAS，直接跳过")
                return state

        md_path = pdf_to_md_first_step(
            pdf_path=pdf_path,
            config=state.config,
            hooks=state.hooks,
            stop_event=state.stop_event,
            lang="ch",
        )
        if md_path is None:
            raise RuntimeError("PDF parser returned None")

        state.md_path = str(md_path)
        state.set_progress(0.2, "PDF解析完成")
        state.add_log(f"PDF解析成功: {md_path}")
        state.add_report_section(f"## PDF -> MD 成功\n> 生成 MD: `{md_path.name}`\n")
        return state
    except Exception as exc:
        state.emit_error(f"PDF -> MD failed: {exc}")
        state.should_stop = True
        state.set_progress(0.2, "PDF解析失败")
        return state


def parse_pdf_to_md(pdf_path: str, config) -> Optional[str]:
    try:
        result = pdf_to_md_first_step(
            pdf_path=Path(pdf_path),
            config=config,
            hooks=None,
            stop_event=None,
            lang="ch",
        )
        return str(result) if result else None
    except Exception:
        return None
