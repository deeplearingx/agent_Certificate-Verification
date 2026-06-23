#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
表格处理模块 - 从param_check.py提取重构
负责Markdown表格解析和操作
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from core.number_parser import NumberParser


class TableProcessor:
    """表格处理器 - 负责Markdown表格的解析和操作"""

    @staticmethod
    def looks_like_table_header(line: str) -> bool:
        """判断是否是表格标题行"""
        if not line:
            return False

        line = line.strip()

        # 包含表格分隔符
        if "|" in line and len(line.split("|")) >= 3:
            # 检查是否有列标题
            if any(cell.strip() for cell in line.split("|")):
                return True

        return False

    @staticmethod
    def looks_like_summary_heading(line: str) -> bool:
        """判断是否是摘要标题"""
        if not line:
            return False

        line = line.strip().lower()

        return line.startswith("**") and (
            "摘要" in line or "summary" in line or "统计" in line
        )

    @staticmethod
    def extract_param_name(line: str) -> Optional[str]:
        """从行中提取参数名称"""
        if not line:
            return None

        line = line.strip()

        # 常见参数名称模式
        patterns = [
            r"^\*\*(.*?)\*\*",  # 加粗格式
            r"^(.*?)\s*[：:]",  # 中文冒号前缀
            r"^\[(.*?)\]",  # 方括号格式
            r"^([^\s:：]+?)\s*[:：]",  # 字母数字前缀
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                param_name = match.group(1).strip()
                if param_name and len(param_name) <= 100:
                    return param_name

        return None

    @staticmethod
    def summarize_table_statuses(table_lines: List[str]) -> Dict[str, int]:
        """统计表格状态"""
        if not table_lines:
            return {}

        status_counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}

        for line in table_lines:
            line = line.strip()
            if line and "|" in line:
                cells = [cell.strip() for cell in line.split("|")]

                # 查找状态列
                for cell in cells:
                    cell_lower = cell.lower()

                    # 统计通过/失败
                    if "pass" in cell_lower or "通过" in cell_lower:
                        status_counts["PASS"] += 1
                    elif "fail" in cell_lower or "失败" in cell_lower:
                        status_counts["FAIL"] += 1
                    elif "error" in cell_lower or "错误" in cell_lower:
                        status_counts["ERROR"] += 1
                    elif "skip" in cell_lower or "跳过" in cell_lower:
                        status_counts["SKIP"] += 1

        return status_counts

    @staticmethod
    def count_statuses_from_table_lines(table_lines: List[str]) -> Tuple[int, int, int]:
        """从表格行统计状态"""
        counts = TableProcessor.summarize_table_statuses(table_lines)
        return (counts["PASS"], counts["FAIL"], counts["ERROR"])

    @staticmethod
    def normalize_param_name_for_merge(param_name: str) -> str:
        """规范化参数名称用于合并"""
        if not param_name:
            return ""

        param_name = param_name.strip()

        # 移除前缀和后缀
        param_name = re.sub(r"^[：:]+\s*", "", param_name)
        param_name = re.sub(r"\s*[：:]+$", "", param_name)

        # 统一格式
        param_name = param_name.lower()

        # 移除特殊字符
        param_name = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "", param_name)

        return param_name

    @staticmethod
    def build_fallback_param_name(expected_param_names: Optional[List[str]]) -> Optional[str]:
        """构建备用参数名称"""
        if expected_param_names:
            for name in expected_param_names:
                if name and name.strip():
                    return name.strip()
        return None

    @staticmethod
    def find_status_column_index(cols: List[str]) -> Optional[int]:
        """查找状态列索引"""
        if not cols:
            return None

        for i, col in enumerate(cols):
            col_lower = col.strip().lower()
            if any(keyword in col_lower for keyword in ["status", "状态", "结果"]):
                return i

        return None

    @staticmethod
    def find_kb_code_column_index(cols: List[str]) -> Optional[int]:
        """查找知识库代码列索引"""
        if not cols:
            return None

        for i, col in enumerate(cols):
            col_lower = col.strip().lower()
            if any(keyword in col_lower for keyword in ["kb_code", "kb", "知识库"]):
                return i

        return None

    @staticmethod
    def find_note_column_index(cols: List[str]) -> Optional[int]:
        """查找备注列索引"""
        if not cols:
            return None

        for i, col in enumerate(cols):
            col_lower = col.strip().lower()
            if any(keyword in col_lower for keyword in ["note", "备注"]):
                return i

        return None

    @staticmethod
    def is_kb_missing_fail(status: str, kb_code: str, note: str) -> bool:
        """判断是否是知识库缺失导致的失败"""
        status = (status or "").strip().lower()
        kb_code = (kb_code or "").strip().lower()
        note = (note or "").strip().lower()

        # 检查知识库代码是否为空或缺失
        if status == "fail" and (not kb_code or "missing" in kb_code):
            return True

        # 检查备注是否包含相关信息
        if status == "fail" and "kb" in note and "missing" in note:
            return True

        return False
