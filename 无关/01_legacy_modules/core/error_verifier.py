#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
误差验证模块 - 从param_check.py提取重构
负责误差和限值验证
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from core.number_parser import NumberParser


class ErrorVerifier:
    """误差验证器 - 负责误差验证和误差限值计算"""

    @staticmethod
    def verify_error_logic(error_val, limit_val) -> str:
        """
        误差验证逻辑

        Args:
            error_val: 误差值或误差表达式
            limit_val: 限值或限值范围

        Returns:
            验证结果字符串
        """
        try:
            if NumberParser.is_missing(error_val) or NumberParser.is_missing(limit_val):
                return json.dumps(
                    {"status": "PASS", "reason": "误差或限值缺失 -> Skip", "calc_type": "error"},
                    ensure_ascii=False,
                )

            # 解析误差值
            err_value, err_unit, err_original = NumberParser.parse_value_with_unit(error_val)
            if err_value is None:
                # 尝试解析绝对误差标记
                return json.dumps(
                    {"status": "PASS", "reason": "误差值格式无法解析，默认通过", "calc_type": "error"},
                    ensure_ascii=False,
                )

            # 解析限值
            limit_value, limit_unit, limit_original = NumberParser.parse_value_with_unit(limit_val)
            if limit_value is None:
                return json.dumps(
                    {"status": "ERROR", "reason": f"无法解析限值: {limit_val}", "calc_type": "error"},
                    ensure_ascii=False,
                )

            # 规范化单位
            if err_unit and limit_unit:
                from core.unit_converter import UnitConverter
                err_in_limit_unit = UnitConverter.convert_value(err_value, err_unit, limit_unit)
                if err_in_limit_unit is not None:
                    err_value = err_in_limit_unit

            # 验证逻辑
            # 误差绝对值 ≤ 限值
            err_abs = abs(err_value)
            limit_abs = abs(limit_value)

            # 使用容差判断
            tolerance = max(limit_abs * 0.001, 1e-15)

            if err_abs <= (limit_abs + tolerance):
                return json.dumps(
                    {
                        "status": "PASS",
                        "reason": f"误差值({err_original}) ≤ 限值({limit_original})",
                        "error_value": err_value,
                        "limit_value": limit_value,
                        "calc_type": "error"
                    },
                    ensure_ascii=False,
                )
            else:
                return json.dumps(
                    {
                        "status": "FAIL",
                        "reason": f"误差值({err_original}) > 限值({limit_original})",
                        "error_value": err_value,
                        "limit_value": limit_value,
                        "calc_type": "error"
                    },
                    ensure_ascii=False,
                )

        except Exception as e:
            return json.dumps(
                {"status": "ERROR", "reason": f"误差验证出错: {str(e)}", "calc_type": "error"},
                ensure_ascii=False,
            )

    @staticmethod
    def calc_absolute_error(measured: float, reference: float) -> float:
        """
        计算绝对误差

        Args:
            measured: 测量值
            reference: 参考值

        Returns:
            绝对误差 (measured - reference)
        """
        return measured - reference

    @staticmethod
    def calc_relative_error(measured: float, reference: float) -> float:
        """
        计算相对误差

        Args:
            measured: 测量值
            reference: 参考值

        Returns:
            相对误差 (measured - reference) / |reference|
        """
        if reference == 0:
            return float('inf')
        return (measured - reference) / abs(reference)

    @staticmethod
    def extract_primary_unit_token(text: str) -> str:
        """从文本中提取主单位标记"""
        if not text:
            return ""

        # 常见单位模式
        unit_patterns = [
            r'(dBm|dBmV|dBc|dBc/Hz|dB)',
            r'(kHz|MHz|GHz|THz|Hz)',
            r'(kV|mV|uV|μV|V)',
            r'(mA|uA|μA|A)',
            r'(ms|us|μs|ns|ps|s)',
            r'(pm|nm|um|μm|mm|cm|m)',
            r'(m/s|m/s2|m/s3)',
            r'(m2|m3)',
            r'(deg|°)',
        ]

        for pattern in unit_patterns:
            match = re.search(pattern, str(text), re.IGNORECASE)
            if match:
                return match.group(1)

        return ""


import json
