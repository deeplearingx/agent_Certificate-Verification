#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameter report helpers for the LangGraph parameter check.

This module keeps the public helper names used by `parameter.py`, but the
implementation is intentionally small and stable:
- clean up known failure markers
- normalize uncertainty text when tool-based calculation is used
- build parameter tables
- summarize batch detail tables by measurement point, not by parameter name
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from langchain_app.utils import AppConfig, get_app_config


def get_config(cfg: Optional[AppConfig] = None) -> AppConfig:
    return cfg or get_app_config()


def _escape_markdown_table_cell(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return "-"
    text = text.replace("\\", "\\\\")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    text = text.replace("|", "\\|")
    return text


def enforce_kb_missing_fail(md: str) -> str:
    """Normalize KB-missing cases to REVIEW rather than FAIL."""
    if not md:
        return md

    if any(tag in md for tag in ("KB_NOT_FOUND", "KB_ABSENT", "知识库未匹配")):
        md = re.sub(r"\*\*PASS\*\*", "**REVIEW**", md)
        md = re.sub(r"✅\s*PASS", "⚠ REVIEW", md)
        if "知识库未匹配" not in md and "KB_NOT_FOUND" not in md:
            md = re.sub(r"(\|.*\|.*\|)", r"\1知识库未匹配，需人工核验", md)
    return md


def enforce_uncertainty_by_tool(md: str) -> str:
    """Normalize wording so tool-based uncertainty calculation is explicit."""
    if not md:
        return md

    md = md.replace("手动计算", "工具计算")
    md = md.replace("人工计算", "工具计算")
    return md


def build_param_table(entries: List[Dict], top_k: int = 10) -> str:
    if not entries:
        return (
            "| 参数名 | 测量值 | 单位 | 范围 | 误差 | 不确定度 | 状态 |\n"
            "|------|------|------|------|------|--------|------|\n"
            "| - | - | - | - | - | - | KB_ABSENT |\n"
        )

    table_lines = [
        "| 参数名 | 测量值 | 单位 | 范围 | 误差 | 不确定度 | 状态 |",
        "|------|------|------|------|------|--------|------|",
    ]

    for entry in entries[:top_k]:
        param_name = entry.get("参数名称", entry.get("PARAM_NAME", "-"))
        measure_val = str(entry.get("测量值", entry.get("measure_val", "-")))
        unit = entry.get("单位", entry.get("unit", "-"))
        range_val = str(entry.get("范围", entry.get("range_str", "-")))
        error_val = str(entry.get("误差", entry.get("error_val", "-")))
        u_val = str(entry.get("不确定度", entry.get("cert_u", "-")))
        status = entry.get("status", "PASS")
        row = [
            _escape_markdown_table_cell(param_name),
            _escape_markdown_table_cell(measure_val),
            _escape_markdown_table_cell(unit),
            _escape_markdown_table_cell(range_val),
            _escape_markdown_table_cell(error_val),
            _escape_markdown_table_cell(u_val),
            _escape_markdown_table_cell(status),
        ]
        table_lines.append("| " + " | ".join(row) + " |")

    if len(entries) > top_k:
        table_lines.append(f"| ... 其余{len(entries) - top_k}个参数 | ... | ... | ... | ... | ... | ... |")

    return "\n".join(table_lines)


def extract_param_names_from_table(md: str) -> List[str]:
    """Extract the first column values from the first parameter-style table."""
    if not md:
        return []

    lines = md.splitlines()
    param_names: List[str] = []
    in_table = False
    header_seen = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not header_seen:
            if any(token in stripped for token in ("参数名", "测量点", "点位")):
                header_seen = True
                in_table = True
            continue

        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if not cells:
            continue

        first_cell = cells[0]
        if first_cell and first_cell != "-":
            param_names.append(first_cell)

    # De-duplicate while preserving order
    seen = set()
    unique_names = []
    for name in param_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)
    return unique_names


def _extract_detail_table_lines(md: str) -> List[str]:
    """Extract the first batch detail table from a generated report."""
    if not md:
        return []

    lines = md.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if "参数核验详情" in line:
            start_idx = idx + 1
            break

    if start_idx is None:
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("|") and "判定" in stripped:
                start_idx = idx
                break

    if start_idx is None:
        return []

    table_lines: List[str] = []
    in_table = False
    for line in lines[start_idx:]:
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            break

    return table_lines


def _summarize_detail_table_lines(table_lines: List[str]) -> Dict[str, int]:
    """Count PASS / FAIL / ERROR / UNKNOWN rows in a detail table."""
    summary = {"pass": 0, "fail": 0, "error": 0, "unknown": 0, "total": 0}
    if not table_lines:
        return summary

    status_idx = None
    for line in table_lines:
        if not line.startswith("|"):
            continue

        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if status_idx is None:
            for idx, col in enumerate(cols):
                if col in {"判定", "status", "状态"}:
                    status_idx = idx
                    break
            continue

        if all(set(col) <= {"-", ":", " "} for col in cols):
            continue
        if status_idx >= len(cols):
            continue

        status = cols[status_idx].upper()
        summary["total"] += 1
        if "PASS" in status:
            summary["pass"] += 1
        elif "FAIL" in status:
            summary["fail"] += 1
        elif "ERROR" in status:
            summary["error"] += 1
        else:
            summary["unknown"] += 1

    return summary


def build_batch_summary_table(param_names: List[str], results: List[Dict]) -> str:
    """Build a simple summary table keyed by parameter name."""
    table_lines = [
        "| 参数名 | 状态 | 说明 |",
        "|------|------|------|",
    ]

    for param_name in param_names:
        param_results = [r for r in results if r.get("param_name") == param_name]
        if param_results:
            status = str(param_results[0].get("status", "ERROR"))
            reason = str(param_results[0].get("reason", "-"))
            status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏳"
            row = [
                _escape_markdown_table_cell(param_name),
                _escape_markdown_table_cell(f"{status_icon} {status}"),
                _escape_markdown_table_cell(reason),
            ]
            table_lines.append("| " + " | ".join(row) + " |")
        else:
            row = [
                _escape_markdown_table_cell(param_name),
                _escape_markdown_table_cell("⏳ ERROR"),
                _escape_markdown_table_cell("未找到核验结果"),
            ]
            table_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(table_lines)


def enforce_batch_summary_from_table(
    md: str,
    expected_param_names: Optional[List[str]] = None,
) -> str:
    """Prepend a batch summary based on the detail table rows."""
    if not md:
        return md

    param_names = extract_param_names_from_table(md)
    if expected_param_names:
        param_names = expected_param_names

    detail_summary = _summarize_detail_table_lines(_extract_detail_table_lines(md))
    if not param_names and detail_summary["total"] == 0:
        return md

    if detail_summary["total"] > 0:
        pass_count = detail_summary["pass"]
        fail_count = detail_summary["fail"]
        error_count = detail_summary["error"]
        unknown_count = detail_summary["unknown"]
        total_count = detail_summary["total"]
    else:
        pass_count = fail_count = error_count = unknown_count = 0
        total_count = len(param_names)

    summary_lines = [
        "## 批次统计",
        f"- 参数种类: {len(param_names)} 个",
        f"- 测量点数: {total_count} 个",
        "",
        "| 测量点总数 | 通过 | 失败 | 错误 | 未知 |",
        "|---------|------|------|------|------|",
        f"| {total_count} | {pass_count} | {fail_count} | {error_count} | {unknown_count} |",
    ]

    return "\n".join(summary_lines) + "\n" + md
