#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
范围验证模块 - 从param_check.py提取重构
负责解析和验证各种范围格式
"""

import re
import json
from typing import Any, Dict, List, Optional, Tuple

from core.number_parser import NumberParser


class RangeVerifier:
    """范围验证器 - 负责解析和验证各种范围格式"""

    @staticmethod
    def parse_single_sided_limit(limit_str: str) -> Optional[Tuple[str, float]]:
        """解析单边范围 (如 <10, ≤10, >5, ≥5)"""
        if not limit_str:
            return None

        limit_str = str(limit_str).strip()

        # 支持的操作符
        operators = ["<=", ">=", "<", ">"]

        for op in operators:
            if limit_str.startswith(op):
                try:
                    value = NumberParser.parse_value_with_unit(limit_str[len(op):].strip())[0]
                    if value is not None:
                        return (op, value)
                except:
                    continue

        return None

    @staticmethod
    def parse_range_limit(limit_str: str) -> Optional[Tuple[float, float]]:
        """解析范围限制 (如 0~20, 10-30, -5~+15)"""
        if not limit_str:
            return None

        limit_str = str(limit_str).strip()

        # 支持的范围分隔符
        separators = ["~", "～", "-", " to "]

        for sep in separators:
            if sep in limit_str:
                parts = [part.strip() for part in limit_str.split(sep)]
                if len(parts) >= 2:
                    try:
                        lower = NumberParser.parse_value_with_unit(parts[0])[0]
                        upper = NumberParser.parse_value_with_unit(parts[1])[0]

                        if lower is not None and upper is not None:
                            return (min(lower, upper), max(lower, upper))

                    except:
                        continue

        return None

    @staticmethod
    def parse_symmetric_limit(limit_str: str) -> Optional[float]:
        """解析对称范围 (如 ±10, ±(0.5~1.0))"""
        if not limit_str:
            return None

        limit_str = str(limit_str).strip()

        # 匹配 ±格式
        symmetric_match = re.match(r"^\s*[±±](.*)$", limit_str)
        if symmetric_match:
            try:
                # 解析对称范围值
                value_str = symmetric_match.group(1).strip()

                # 如果包含范围，取平均值
                range_match = RangeVerifier.parse_range_limit(value_str)
                if range_match:
                    lower, upper = range_match
                    return (abs(lower) + abs(upper)) / 2

                # 直接解析数值
                value = NumberParser.parse_value_with_unit(value_str)[0]
                if value is not None:
                    return abs(value)

            except:
                pass

        return None

    @staticmethod
    def convert_time_unit(value: float, from_unit: str, to_unit: str) -> float:
        """转换时间单位"""
        unit_map = {
            "ps": 1e-12, "ns": 1e-9, "us": 1e-6,
            "ms": 1e-3, "s": 1.0, "m": 60, "h": 3600,
            "d": 86400, "w": 604800, "mo": 2592000, "y": 31536000
        }

        from_multiplier = unit_map.get(from_unit.lower(), 1.0)
        to_multiplier = unit_map.get(to_unit.lower(), 1.0)

        return value * from_multiplier / to_multiplier

    @staticmethod
    def verify_range_logic(measure_val, range_str):
        """
        范围核验逻辑 - 核心核验函数

        Returns:
            JSON字符串形式的核验结果
        """
        try:
            if NumberParser.is_missing(measure_val) or NumberParser.is_missing(range_str):
                return json.dumps(
                    {"status": "PASS", "reason": "测量值或范围缺失 -> Skip", "calc_type": "range"},
                    ensure_ascii=False,
                )

            # 解析测量值
            measure_token = NumberParser.extract_value_token(str(measure_val)) or str(measure_val)
            m_val, measure_unit, _ = NumberParser.parse_value_with_unit(measure_val)

            if m_val is None:
                return json.dumps(
                    {"status": "ERROR", "reason": f"无法解析测量值: {measure_val}", "calc_type": "range"},
                    ensure_ascii=False,
                )

            # 规范化范围
            range_str = str(range_str).strip()

            # 检查范围格式
            symmetric_limit = RangeVerifier.parse_symmetric_limit(range_str)
            if symmetric_limit:
                # 对称范围验证
                if abs(m_val) <= symmetric_limit:
                    return json.dumps(
                        {"status": "PASS", "reason": f"测量值({measure_token})在对称范围±{symmetric_limit}内核验通过", "calc_type": "range"},
                        ensure_ascii=False,
                    )
                else:
                    return json.dumps(
                        {"status": "FAIL", "reason": f"测量值({measure_token})超出对称范围±{symmetric_limit}", "calc_type": "range"},
                        ensure_ascii=False,
                    )

            single_sided = RangeVerifier.parse_single_sided_limit(range_str)
            if single_sided:
                # 单边范围验证
                op, limit = single_sided
                if (op == "<" and m_val < limit) or \
                   (op == ">" and m_val > limit) or \
                   (op == "<=" and m_val <= limit) or \
                   (op == ">=" and m_val >= limit):
                    return json.dumps(
                        {"status": "PASS", "reason": f"测量值({measure_token})满足条件{op}{limit}", "calc_type": "range"},
                        ensure_ascii=False,
                    )
                else:
                    return json.dumps(
                        {"status": "FAIL", "reason": f"测量值({measure_token})不满足条件{op}{limit}", "calc_type": "range"},
                        ensure_ascii=False,
                    )

            range_limit = RangeVerifier.parse_range_limit(range_str)
            if range_limit:
                # 范围验证
                lower, upper = range_limit

                # 改进容差计算
                range_span = upper - lower
                tolerance = max(range_span * 0.01, 1e-15)

                if (lower - tolerance) <= m_val <= (upper + tolerance):
                    return json.dumps(
                        {"status": "PASS", "reason": f"测量值({measure_token})在范围[{lower}, {upper}]内核验通过", "calc_type": "range"},
                        ensure_ascii=False,
                    )
                else:
                    return json.dumps(
                        {"status": "FAIL", "reason": f"测量值({measure_token})超出范围[{lower}, {upper}]", "calc_type": "range"},
                        ensure_ascii=False,
                    )

            return json.dumps(
                {"status": "ERROR", "reason": f"无法解析范围格式: {range_str}", "calc_type": "range"},
                ensure_ascii=False,
            )

        except Exception as e:
            return json.dumps(
                {"status": "ERROR", "reason": f"核验出错: {str(e)}", "calc_type": "range"},
                ensure_ascii=False,
            )
