#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
不确定度验证模块 - 从param_check.py提取重构
负责不确定度计算和验证
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from core.number_parser import NumberParser


class UncertaintyVerifier:
    """不确定度验证器 - 负责不确定度计算和验证"""

    @staticmethod
    def detect_uncertainty_kind(u_str: str, measure_val: str = "") -> str:
        """
        检测不确定度类型

        Returns:
            'absolute' - 绝对不确定度
            'relative' - 相对不确定度
            'unknown' - 未知类型
        """
        if not u_str:
            return "unknown"

        u_str = str(u_str).strip()
        measure_val = str(measure_val).strip()

        # 检查相对不确定度的关键字
        if any(keyword in u_str.lower() for keyword in ["%", "relative", "相对"]):
            return "relative"

        # 检查是否包含明确的绝对不确定度单位
        abs_unit_patterns = [
            r'(dBm|dBmV|dBc)',
            r'(kHz|MHz|GHz|THz|Hz)',
            r'(kV|mV|uV|μV|V)',
            r'(mA|uA|μA|A)',
            r'(ms|us|μs|ns|ps|s)',
            r'(pm|nm|um|μm|mm|cm|m)',
        ]

        for pattern in abs_unit_patterns:
            if re.search(pattern, u_str, re.IGNORECASE):
                return "absolute"

        # 如果测量值有明确单位，而不确定度与测量值单位相关，则为绝对
        if measure_val:
            from core.error_verifier import ErrorVerifier
            measure_unit = ErrorVerifier.extract_primary_unit_token(measure_val)
            if measure_unit and measure_unit in u_str:
                return "absolute"

        return "unknown"

    @staticmethod
    def measure_prefers_relative_u(measure_val: str) -> bool:
        """
        判断测量值是否更适合用相对不确定度表示

        Returns:
            True - 更适合用相对不确定度
            False - 更适合用绝对不确定度
        """
        if not measure_val:
            return False

        measure_val = str(measure_val).strip()

        # 以下情况更适合用相对不确定度
        relative_preferred_patterns = [
            r'\bEVM\b',
            r'误差.*%',
            r'相对',
        ]

        for pattern in relative_preferred_patterns:
            if re.search(pattern, measure_val, re.IGNORECASE):
                return True

        # 频率测量如果单位是dB相关的，更适合绝对不确定度
        power_related_patterns = [
            r'dBm',
            r'dBmV',
            r'dBc',
            r'dB',
        ]

        for pattern in power_related_patterns:
            if re.search(pattern, measure_val, re.IGNORECASE):
                return False

        return False

    @staticmethod
    def calc_u_formula(expr: str, measure_val: str) -> Tuple[Optional[float], str]:
        """
        计算不确定度公式

        Args:
            expr: 不确定度表达式 (如 "2 * k", "U = 10")
            measure_val: 测量值，用于上下文

        Returns:
            (计算结果, 说明) 元组
        """
        try:
            if not expr or NumberParser.is_missing(expr):
                return None, "空表达式"

            expr = str(expr).strip()

            # 尝试直接解析数值
            direct_result = NumberParser.parse_value_with_unit(expr)
            if direct_result[0] is not None:
                return direct_result[0], "直接解析"

            # 处理简单公式
            # 模式1: U = x 或 U=x
            eq_match = re.match(r'[Uu]\s*[=:]\s*([-+]?\d+\.?\d*)', expr)
            if eq_match:
                try:
                    value = float(eq_match.group(1))
                    return value, "从等式提取"
                except ValueError:
                    pass

            # 模式2: 尝试提取最后一个数值
            num_matches = re.findall(r'[-+]?\d+\.?\d*', expr)
            if num_matches:
                try:
                    return float(num_matches[-1]), "提取最后一个数值"
                except ValueError:
                    pass

            return None, "无法解析公式"

        except Exception as e:
            return None, f"公式计算出错: {str(e)}"

    @staticmethod
    def verify_uncertainty_logic(measure_val, cert_u, kb_u) -> str:
        """
        不确定度验证逻辑

        Args:
            measure_val: 测量值
            cert_u: 证书不确定度
            kb_u: 知识库不确定度要求

        Returns:
            JSON字符串形式的验证结果
        """
        import json

        try:
            if NumberParser.is_missing(measure_val) or NumberParser.is_missing(cert_u) or NumberParser.is_missing(kb_u):
                return json.dumps(
                    {"status": "PASS", "reason": "测量值或不确定度缺失 -> Skip", "calc_type": "uncertainty"},
                    ensure_ascii=False,
                )

            # 解析测量值
            m_val, m_unit, m_original = NumberParser.parse_value_with_unit(measure_val)
            if m_val is None:
                return json.dumps(
                    {"status": "ERROR", "reason": f"无法解析测量值: {measure_val}", "calc_type": "uncertainty"},
                    ensure_ascii=False,
                )

            # 解析证书不确定度
            cert_u_val, cert_u_unit, cert_u_original = NumberParser.parse_value_with_unit(cert_u)
            if cert_u_val is None:
                # 尝试使用公式计算
                cert_u_val, cert_u_reason = UncertaintyVerifier.calc_u_formula(cert_u, measure_val)
                if cert_u_val is None:
                    return json.dumps(
                        {"status": "PASS", "reason": f"无法解析证书不确定度: {cert_u}, 默认通过", "calc_type": "uncertainty"},
                        ensure_ascii=False,
                    )

            # 解析知识库不确定度
            kb_u_val, kb_u_unit, kb_u_original = NumberParser.parse_value_with_unit(kb_u)
            if kb_u_val is None:
                # 尝试使用公式计算
                kb_u_val, kb_u_reason = UncertaintyVerifier.calc_u_formula(kb_u, measure_val)
                if kb_u_val is None:
                    return json.dumps(
                        {"status": "ERROR", "reason": f"无法解析知识库不确定度: {kb_u}", "calc_type": "uncertainty"},
                        ensure_ascii=False,
                    )

            # 检测不确定度类型
            cert_kind = UncertaintyVerifier.detect_uncertainty_kind(cert_u, measure_val)
            kb_kind = UncertaintyVerifier.detect_uncertainty_kind(kb_u, measure_val)

            # 规范化比较
            # 如果一个是相对，一个是绝对，需要转换
            if cert_kind != kb_kind and m_val != 0:
                if cert_kind == "relative" and kb_kind == "absolute":
                    # 证书是相对，转换为绝对
                    cert_u_val_abs = abs(cert_u_val) * abs(m_val) / 100.0
                    cert_u_val = cert_u_val_abs
                elif cert_kind == "absolute" and kb_kind == "relative":
                    # 知识库是相对，转换证书到相对
                    kb_u_val_abs = abs(kb_u_val) * abs(m_val) / 100.0
                    kb_u_val = kb_u_val_abs

            # 验证逻辑：证书不确定度 ≤ 知识库要求
            cert_u_abs = abs(cert_u_val)
            kb_u_abs = abs(kb_u_val)

            tolerance = max(kb_u_abs * 0.001, 1e-15)

            if cert_u_abs <= (kb_u_abs + tolerance):
                return json.dumps(
                    {
                        "status": "PASS",
                        "reason": f"证书不确定度({cert_u_original}) ≤ 知识库要求({kb_u_original})",
                        "cert_u": cert_u_val,
                        "kb_u": kb_u_val,
                        "cert_kind": cert_kind,
                        "kb_kind": kb_kind,
                        "calc_type": "uncertainty"
                    },
                    ensure_ascii=False,
                )
            else:
                return json.dumps(
                    {
                        "status": "FAIL",
                        "reason": f"证书不确定度({cert_u_original}) > 知识库要求({kb_u_original})",
                        "cert_u": cert_u_val,
                        "kb_u": kb_u_val,
                        "cert_kind": cert_kind,
                        "kb_kind": kb_kind,
                        "calc_type": "uncertainty"
                    },
                    ensure_ascii=False,
                )

        except Exception as e:
            return json.dumps(
                {"status": "ERROR", "reason": f"不确定度验证出错: {str(e)}", "calc_type": "uncertainty"},
                ensure_ascii=False,
            )
