#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown -> JSON graph node.
"""

from pathlib import Path
from typing import Optional

import md_parser_no_llm

from langchain_app.checks.integrity import (
    build_non_cnas_skip_report,
    is_explicit_non_cnas_flag,
    normalize,
    normalize_cnas_flag,
)
from langchain_app.graph.state import VerificationState
from langchain_app.services.parsing import json_cache_needs_refresh, parse_md_to_json


def parse_json_node(state: VerificationState) -> VerificationState:
    if state.stop_event is not None and state.stop_event.is_set():
        state.should_stop = True
        return state

    state.emit_status("Processing [1/6]: MD -> JSON")
    state.emit_progress(10)
    state.set_progress(0.3, "Markdown解析")
    state.add_log("开始Markdown解析")

    def parser_progress(stage: str, current: int, total: int, message: str) -> None:
        total = max(int(total or 0), 1)
        current = max(0, min(int(current or 0), total))
        progress_value = 12
        if stage.startswith("meta_extract"):
            progress_value = 14 if stage.endswith("done") else 12
        elif stage.startswith("row_llm_fallback"):
            progress_value = 14 + int((current / total) * 14)
        state.emit_status(f"Processing [1/6]: MD -> JSON ({message})")
        state.emit_progress(progress_value)
        if stage in {"meta_extract_done", "row_llm_fallback_done"}:
            state.add_log(message)

    try:
        md_path = Path(state.md_path)
        expected_json_name = md_path.with_suffix(".json").name
        json_path = Path(state.config.local_json_dir) / expected_json_name

        md_text = md_path.read_text(encoding="utf-8", errors="ignore")
        md_meta = md_parser_no_llm.extract_meta_from_text(md_text)
        md_is_cnas = normalize_cnas_flag(md_meta)
        if is_explicit_non_cnas_flag(md_is_cnas):
            cert_no = normalize(md_meta.get("证书编号"))
            state.add_report_section(
                build_non_cnas_skip_report(
                    source_name=Path(state.source_pdf_path).name if state.source_pdf_path else md_path.name,
                    cert_no=cert_no,
                    is_cnas=md_is_cnas,
                )
            )
            state.emit_status("Processing [1/6]: MD -> JSON (非CNAS跳过)")
            state.emit_warning("从 MD 头部识别为非 CNAS，跳过当前文件后续核验")
            state.should_stop = True
            state.set_progress(0.4, "非CNAS跳过")
            return state

        if json_path.exists() and json_cache_needs_refresh(json_path):
            state.emit_warning(f"Detected stale JSON cache, reparsing {expected_json_name}")
            json_path.unlink()

        if json_path.exists():
            state.emit_info(f"Cache hit: reuse JSON {expected_json_name}")
            state.add_report_section(
                f"## MD 解析 (跳过)\n> 检测到现有 JSON `{expected_json_name}`，直接使用。\n"
            )
        else:
            hook_proxy = type("_ParserHookProxy", (), {})()
            hook_proxy.parser_progress_callback = parser_progress
            result = parse_md_to_json(
                str(md_path),
                state.config.local_json_dir,
                llm_client=state.llm_client,
                allow_llm_fallback=bool(state.config and state.config.use_llm_verification),
                hooks=hook_proxy,
            )
            if result is None:
                raise RuntimeError("MD parser returned empty result")
            if not json_path.exists():
                raise FileNotFoundError(f"JSON file was not written: {json_path}")
            state.add_report_section(f"## MD 解析成功\n> 生成 JSON: `{json_path.name}`\n")

        state.json_path = str(json_path)
        state.set_progress(0.4, "Markdown解析完成")
        state.add_log(f"Markdown解析成功: {json_path}")
        return state
    except Exception as exc:
        state.emit_error(f"MD -> JSON failed: {exc}")
        state.add_report_section(f"## MD -> JSON 失败\n> Error: {exc}\n")
        state.should_stop = True
        state.set_progress(0.4, "Markdown解析失败")
        return state


def parse_md_to_json_wrapper(md_path: str, config) -> Optional[str]:
    try:
        json_path = parse_md_to_json(md_path, config.local_json_dir)
        return str(json_path) if json_path else None
    except Exception:
        return None
