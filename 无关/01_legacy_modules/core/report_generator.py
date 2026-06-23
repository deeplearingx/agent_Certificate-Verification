#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告生成模块 - 从param_check.py提取重构
负责报告生成和统计功能
"""

import re
import json
from typing import Any, Dict, List, Optional, Tuple

from core.number_parser import NumberParser
from core.table_processor import TableProcessor


class ReportGenerator:
    """报告生成器 - 负责Markdown报告的生成和统计"""

    @staticmethod
    def build_param_table(entries: List[Dict], top_k: int = 10) -> str:
        """构建参数表格"""
        if not entries:
            return ""

        # 表头
        header = "| 参数名称 | 测量值 | 允许范围 | 状态 | 知识库代码 | 备注 |"
        separator = "|---------|-------|----------|------|----------|------|"

        # 构建表格行
        rows = []
        selected_entries = entries[:top_k]

        for entry in selected_entries:
            param_name = entry.get("param_name", "N/A")
            measure_val = entry.get("measure_val", "N/A")
            range_str = entry.get("range_str", "N/A")
            status = entry.get("status", "N/A")
            kb_code = entry.get("kb_code", "N/A")
            note = entry.get("note", "")

            # 转义管道字符
            row = f"| {param_name} | {measure_val} | {range_str} | {status} | {kb_code} | {note} |"
            rows.append(row)

        # 添加截断提示
        if len(entries) > top_k:
            rows.append(f"| ... | ... | ... | ... | ... | 显示前 {top_k} 条，共 {len(entries)} 条 |")

        return "\n".join([header, separator] + rows)

    @staticmethod
    def enforce_kb_missing_fail(md: str) -> str:
        """强制知识库缺失时失败"""
        if not md:
            return md

        lines = md.split("\n")
        output = []

        for line in lines:
            if TableProcessor.looks_like_table_header(line):
                output.append(line)

                # 检查下一行是否是表格
                next_line_idx = len(output)
                if next_line_idx < len(lines):
                    next_line = lines[next_line_idx]

                    if TableProcessor.looks_like_table_header(next_line):
                        output.append(next_line)

                # 统计表格状态
                table_stats = TableProcessor.summarize_table_statuses(lines)
                if table_stats.get("PASS", 0) == 0 and table_stats.get("FAIL", 0) > 0:
                    output.append("**⚠️ 知识库缺失导致全部失败**")

            else:
                output.append(line)

        return "\n".join(output)

    @staticmethod
    def enforce_uncertainty_by_tool(md: str) -> str:
        """强制按工具计算不确定度"""
        if not md:
            return md

        lines = md.split("\n")
        output = []

        for line in lines:
            # 检查是否包含不确定度信息
            u_match = re.search(r"U\s*=\s*([^,，;；<]+)", line, re.IGNORECASE)
            if u_match:
                # 尝试计算不确定度
                try:
                    u_str = u_match.group(1).strip()

                    # 检查是否包含dBm
                    if "dBm" in u_str or "dBmV" in u_str:
                        # 对于dBm单位的不确定度，检查是否有自动计算标记
                        if not re.search(r"\(自动计算\)", line):
                            output.append(line.replace(u_str, f"{u_str} (未计算)"))
                            continue

                except:
                    pass

            output.append(line)

        return "\n".join(output)

    @staticmethod
    def enforce_batch_summary_from_table(md: str, expected_param_names: Optional[List[str]] = None) -> str:
        """强制从表格中生成批次摘要"""
        if not md:
            return md

        lines = md.split("\n")
        output = []

        param_tables = []
        current_table = []
        in_table = False

        # 提取所有参数表格
        for i, line in enumerate(lines):
            if TableProcessor.looks_like_table_header(line) and not TableProcessor.looks_like_summary_heading(line):
                in_table = True
                current_table = [line]

            elif in_table and line.strip():
                current_table.append(line)

            elif in_table and not line.strip():
                param_tables.append(current_table)
                in_table = False

        if in_table and current_table:
            param_tables.append(current_table)

        # 检查是否已包含摘要
        has_summary = any(TableProcessor.looks_like_summary_heading(line) for line in lines)

        if not has_summary and param_tables:
            summary_lines = ReportGenerator._build_summary_lines_from_table(lines)
            if summary_lines:
                # 在第一个表格前插入摘要
                first_table_idx = len(lines)
                for i, line in enumerate(lines):
                    if TableProcessor.looks_like_table_header(line) and not TableProcessor.looks_like_summary_heading(line):
                        first_table_idx = i
                        break

                output = lines[:first_table_idx] + summary_lines + lines[first_table_idx:]
                return "\n".join(output)

        return md

    @staticmethod
    def _build_summary_lines_from_table(table_lines: List[str]) -> List[str]:
        """从表格中构建摘要行"""
        total_pass, total_fail, total_error = TableProcessor.count_statuses_from_table_lines(table_lines)
        total_checks = total_pass + total_fail + total_error

        if total_checks == 0:
            return []

        summary_lines = [
            "",
            "## 核验摘要",
            "| 总数 | 合格 | 不合格 | 错误 | 合格率 |",
            "|------|------|--------|------|--------|",
            f"| {total_checks} | {total_pass} | {total_fail} | {total_error} | "
            f"{round(total_pass / total_checks * 100, 1)}% |"
        ]

        return summary_lines

    @staticmethod
    def generate_json_report(results: List[Dict]) -> str:
        """生成JSON报告"""
        if not results:
            return "{}"

        report = {
            "summary": {
                "total": len(results),
                "pass": sum(1 for r in results if r.get("status") == "PASS"),
                "fail": sum(1 for r in results if r.get("status") == "FAIL"),
                "error": sum(1 for r in results if r.get("status") == "ERROR"),
                "skip": sum(1 for r in results if r.get("status") == "SKIP"),
            },
            "results": results
        }

        return json.dumps(report, ensure_ascii=False, indent=2)

    @staticmethod
    def collect_certificate_params(cert_root: Dict[str, Any]) -> List[Dict]:
        """收集证书参数"""
        if not cert_root or not isinstance(cert_root, dict):
            return []

        params = []

        # 常见参数路径
        param_paths = [
            "params",
            "parameters",
            "cert_params",
            "certificate_params",
            "data.params"
        ]

        for path in param_paths:
            try:
                parts = path.split(".")
                current = cert_root
                found = True

                for part in parts:
                    if part in current:
                        current = current[part]
                    else:
                        found = False
                        break

                if found and isinstance(current, list):
                    params.extend(current)
            except:
                continue

        return params
