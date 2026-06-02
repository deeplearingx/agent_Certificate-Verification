#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数验证模块 - 负责范围验证、误差验证、不确定度验证

从 param_check.py 和 core/xxx_verifier.py 迁移
"""

import re
import json
import math
from typing import Any, Dict, List, Optional, Tuple, Union

# 灵活的导入方式 - 支持包导入和直接导入
try:
    from .parser_core import (
        parse_value_with_unit,
        parse_range_limit,
        parse_symmetric_limit,
        parse_single_sided_limit,
        extract_value_token,
        parse_unicode_sci_number,
        to_plain_decimal,
    )
    from .parser_domain import _parse_frequency_point_list, _is_power_unit, _is_voltage_unit
except ImportError:
    import importlib.util
    import os
    import sys
    parser_path = os.path.join(os.path.dirname(__file__), 'parser.py')
    spec = importlib.util.spec_from_file_location('parser', parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    parse_value_with_unit = parser.parse_value_with_unit
    parse_range_limit = parser.parse_range_limit
    parse_symmetric_limit = parser.parse_symmetric_limit
    parse_single_sided_limit = parser.parse_single_sided_limit
    _parse_frequency_point_list = parser._parse_frequency_point_list
    extract_value_token = parser.extract_value_token
    parse_unicode_sci_number = parser.parse_unicode_sci_number
    to_plain_decimal = parser.to_plain_decimal
    _is_power_unit = parser._is_power_unit
    _is_voltage_unit = parser._is_voltage_unit


def _is_missing(value: Any) -> bool:
    """检查值是否缺失"""
    if value is None:
        return True
    if isinstance(value, str) and (value.strip() == "" or value.strip().lower() in ["n/a", "none", "null"]):
        return True
    return False


def extract_primary_unit_token(text: str) -> str:
    """从文本中提取主单位标记（与原始 core/error_verifier.py 完全一致）"""
    if not text:
        return ""

    # 常见单位模式
    unit_patterns = [
        r'(dBm|dBmV|dBc|dBc/Hz|dB)',
        r'(kHz|MHz|GHz|THz|Hz)',
        r'(kV|mV|uV|μV|V)',
        r'(mA|uA|μA|A)',
        r'(s/d|s/m|ms|us|μs|ns|ps|s)',
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


def _has_mixed_units(text: str) -> bool:
    """判断字符串中是否包含多个不同类别的单位。"""
    if not text:
        return False
    patterns = [
        r"(dBm|dBmV|dBc|dBc/Hz|dB)",
        r"(kHz|MHz|GHz|THz|Hz)",
        r"(kV|mV|uV|μV|V)",
        r"(mA|uA|μA|A)",
        r"(s/d|s/m|ms|us|μs|ns|ps|s)",
        r"(pm|nm|um|μm|mm|cm|m)",
    ]
    units = []
    for pattern in patterns:
        units.extend(re.findall(pattern, str(text), re.IGNORECASE))
    normalized = {u.lower().replace("μ", "u").replace("µ", "u") for u in units if u}
    return len(normalized) > 1


_TIME_DISPLAY_FACTORS = {
    "h": 3600.0,
    "min": 60.0,
    "s": 1.0,
    "s/d": 1.0 / 86400.0,
    "s/m": 1.0 / (30.0 * 86400.0),
    "ms": 1e-3,
    "us": 1e-6,
    "μs": 1e-6,
    "ns": 1e-9,
    "ps": 1e-12,
}


def _format_period_band_scalar(value_seconds: float, unit: str) -> str:
    unit_label = str(unit or "").strip() or "s"
    factor = _TIME_DISPLAY_FACTORS.get(unit_label)
    if not factor:
        return f"{value_seconds:.12g} s"
    scaled = value_seconds / factor
    return f"{scaled:.12g} {unit_label}"


def _format_period_band_range(lower_seconds: float, upper_seconds: float, unit: str) -> str:
    return f"[{_format_period_band_scalar(lower_seconds, unit)}, {_format_period_band_scalar(upper_seconds, unit)}]"


def detect_uncertainty_kind(u_str: str, measure_val: str = "") -> str:
    """
    检测不确定度类型（与原始 core/uncertainty_verifier.py 完全一致）

    Returns:
        'absolute' - 绝对不确定度
        'relative' - 相对不确定度
        'unknown' - 未知类型
    """
    if not u_str:
        return "unknown"

    u_str = str(u_str).strip()
    measure_val = str(measure_val).strip()

    lower = u_str.lower()

    # 检查相对不确定度的关键字
    if any(keyword in lower for keyword in ["urel", "%", "relative", "相对"]):
        return "relative"

    # 检查是否包含明确的绝对不确定度单位
    abs_unit_patterns = [
        r'(dBm|dBmV|dBc)',
        r'(kHz|MHz|GHz|THz|Hz)',
        r'(kV|mV|uV|μV|V)',
        r'(mA|uA|μA|A)',
        r'(s/d|s/m|ms|us|μs|ns|ps|s)',
        r'(pm|nm|um|μm|mm|cm|m)',
    ]

    for pattern in abs_unit_patterns:
        if re.search(pattern, u_str, re.IGNORECASE):
            return "absolute"

    # 如果测量值有明确单位，而不确定度与测量值单位相关，则为绝对
    if measure_val:
        measure_unit = extract_primary_unit_token(measure_val)
        if measure_unit and measure_unit in u_str:
            return "absolute"

    numeric_value, numeric_unit = parse_value_with_unit(u_str)
    measure_unit = extract_primary_unit_token(measure_val) if measure_val else ""
    if (
        numeric_value is not None
        and numeric_unit in {"", "abs"}
        and measure_unit.lower() in {"hz", "khz", "mhz", "ghz", "thz"}
        and any(token in lower for token in ("×10", "e-", "e+", "e"))
    ):
        return "relative"

    return "unknown"


def _parse_urel_uncertainty(u_str: str) -> Tuple[Optional[float], str]:
    """解析 Urel 不确定度，返回相对系数本身。"""
    if not u_str:
        return None, "missing"

    s = str(u_str).strip()
    s = re.sub(r"^\s*U\s*rel\s*=\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*Urel\s*=\s*", "", s, flags=re.IGNORECASE)
    s = s.replace("−", "-").replace("⁻", "-").replace("⁺", "+")
    s = s.translate(str.maketrans({
        "⁰": "0",
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
    }))
    s = re.sub(r"([0-9.])\s*[×xX*]\s*10\s*([+-]?\d+)", r"\1e\2", s)

    if "%" in s:
        num = parse_unicode_sci_number(s)
        if num is None:
            m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
            num = float(m.group(1)) if m else None
        if num is None:
            return None, "parse_fail_percent"
        return num / 100.0, "parsed_percent"

    direct = parse_unicode_sci_number(s)
    if direct is not None:
        return direct, "parsed_direct"

    m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
    if m:
        return float(m.group(1)), "parsed_regex"

    return None, "parse_fail"


def _parse_absolute_uncertainty(u_str: str, measure_val: str) -> Tuple[Optional[float], str]:
    """解析绝对不确定度。"""
    if not u_str:
        return None, "missing"

    normalized = _normalize_uncertainty_interval_text(u_str)

    parsed, _ = parse_value_with_unit(normalized)
    if parsed is not None:
        return parsed, "parsed_unit"

    calc_val, calc_reason = calc_u_formula(normalized, measure_val)
    if calc_val is not None:
        return calc_val, f"formula:{calc_reason}"
    return None, "parse_fail"


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _normalize_uncertainty_interval_text(u_str: str) -> str:
    if u_str is None:
        return ""
    s = str(u_str).strip()
    s = s.replace("−", "-").replace("⁻", "-").replace("⁺", "+")
    s = s.translate(str.maketrans({
        "⁰": "0",
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
    }))
    s = re.sub(r"^\s*U\s*rel\s*=\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*Urel\s*=\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*U\s*=\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"([0-9.])\s*[×xX*]\s*10\s*([+-]?\d+)", r"\1e\2", s)
    return s


def _split_uncertainty_interval(u_str: str) -> Optional[Tuple[str, str]]:
    s = _normalize_uncertainty_interval_text(u_str)
    if not s or not any(sep in s for sep in ("~", "～")):
        return None
    parts = [p.strip() for p in re.split(r"[~～]", s) if p.strip()]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _parse_uncertainty_endpoint(
    token: str,
    kind: str,
    measure_val: str,
) -> Tuple[Optional[float], str]:
    if not token:
        return None, "missing"
    s = _normalize_uncertainty_interval_text(token)
    if kind == "relative":
        if "%" in s:
            num = parse_unicode_sci_number(s)
            if num is None:
                m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
                num = float(m.group(1)) if m else None
            if num is None:
                return None, "parse_fail_percent"
            return abs(num) / 100.0, "parsed_percent"
        direct = parse_unicode_sci_number(s)
        if direct is not None:
            return abs(direct), "parsed_direct"
        m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if m:
            return abs(float(m.group(1))), "parsed_regex"
        return None, "parse_fail"

    val, reason = _parse_absolute_uncertainty(s, measure_val)
    if val is not None:
        return abs(val), reason
    return None, reason


def _parse_uncertainty_bounds(
    u_str: str,
    measure_val: str,
    kind: str,
) -> Tuple[Optional[float], Optional[float], str, bool]:
    """
    解析不确定度为上下界。

    Returns:
        (lower, upper, reason, is_interval)
    """
    if _is_missing(u_str):
        return None, None, "missing", False

    interval_parts = _split_uncertainty_interval(u_str)
    if not interval_parts:
        if kind == "relative":
            val, reason = _parse_urel_uncertainty(u_str)
        else:
            val, reason = _parse_absolute_uncertainty(u_str, measure_val)
        if val is None:
            return None, None, reason, False
        return abs(val), abs(val), reason, False

    left, right = interval_parts
    left_val, left_reason = _parse_uncertainty_endpoint(left, kind, measure_val)
    right_val, right_reason = _parse_uncertainty_endpoint(right, kind, measure_val)
    if left_val is None or right_val is None:
        return None, None, f"interval_parse_fail:{left_reason}/{right_reason}", True

    lower = min(abs(left_val), abs(right_val))
    upper = max(abs(left_val), abs(right_val))
    return lower, upper, f"interval:{left_reason}/{right_reason}", True


def _canonical_display_unit(unit: str) -> str:
    if not unit:
        return ""
    normalized = unit.lower().replace("μ", "u").replace("µ", "u")
    if normalized in {"thz", "ghz", "mhz", "khz", "hz"}:
        return "Hz"
    if normalized in {"ms", "us", "ns", "ps", "s"}:
        return "s"
    if normalized in {"kv", "mv", "uv", "v"}:
        return "V"
    if normalized in {"ma", "ua", "a"}:
        return "A"
    if normalized in {"pm", "nm", "um", "mm", "cm", "m"}:
        return "m"
    if normalized in {"db", "dbm", "dbmv", "dbc", "dbc/hz"}:
        return unit
    if normalized in {"deg", "°"}:
        return "deg"
    return unit


def _format_uncertainty_display(raw_u: str, value: Optional[float], *, measure_val: str = "", kind: str = "unknown", converted: bool = False) -> str:
    raw_text = _coerce_text(raw_u)
    if raw_text and any(sep in raw_text for sep in ("~", "～")):
        return raw_text
    if value is None:
        return "N/A"
    if kind == "relative" and not converted:
        return f"{value:.6g} (系数)"
    if converted:
        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)
        if m_val is not None and m_val != 0:
            return f"{abs(value) * abs(m_val):.6g} (折算值)"
        return f"{value:.6g} (折算值)"
    return f"{value:.6g}"


def measure_prefers_relative_u(measure_val: str) -> bool:
    """
    判断测量值是否更适合用相对不确定度表示（与原始 core/uncertainty_verifier.py 完全一致）
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


def calc_u_formula(expr: str, measure_val: str) -> Tuple[Optional[float], str]:
    """
    计算不确定度公式（与原始 core/uncertainty_verifier.py 完全一致）

    Args:
        expr: 不确定度表达式 (如 "2 * k", "U = 10")
        measure_val: 测量值，用于上下文

    Returns:
        (计算结果, 说明) 元组
    """
    try:
        if not expr or _is_missing(expr):
            return None, "空表达式"

        expr = str(expr).strip()

        # 尝试直接解析数值
        direct_result = parse_value_with_unit(expr)
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


def _is_discrete_frequency_point_list(range_str: str) -> bool:
    """
    判断是否是离散频点列表，例如 1MHz,2MHz,5MHz,10MHz。
    这类字符串不应按连续区间解析。
    """
    if _is_missing(range_str):
        return False
    text = str(range_str)
    if re.search(r"[~～〜]", text):
        return False
    points = _parse_frequency_point_list(text)
    return len(points) >= 2


def _verify_range_with_selected_candidate(measure_val: Any, range_str: str, selected_candidate: Any) -> Optional[Dict[str, Any]]:
    if selected_candidate is None:
        return None

    axis_family = getattr(selected_candidate, "condition_axis", None)
    band_kind = getattr(selected_candidate, "band_kind", "none")
    capability_target = getattr(selected_candidate, "capability_target", None)
    result_quantity = getattr(selected_candidate, "result_quantity", None)
    measure_token = extract_value_token(str(measure_val)) or str(measure_val)

    if capability_target == "modulation_quality" and result_quantity == "evm":
        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)
        range_lower_upper = parse_range_limit(range_str)
        if m_val is None or range_lower_upper is None:
            return None
        lower, upper = range_lower_upper
        range_unit = extract_primary_unit_token(range_str)
        tolerance = max(max(abs(lower), abs(upper)) * 1e-9, 1e-12)
        display_range = f"[{lower:.12g} {range_unit}, {upper:.12g} {range_unit}]"
        if lower >= 0 and m_val < (lower - tolerance):
            return {
                "status": "REVIEW",
                "reason": (
                    f"范围核验:REVIEW({measure_token} 低于能力下界 {lower:.12g} {range_unit}；"
                    f"当前值优于 KB 覆盖下界，建议人工确认是否按能力边界处理；原始范围={range_str}；归一化范围={display_range})"
                ),
                "calc_type": "range",
            }
        pass_flag = (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance))
        return {
            "status": "PASS" if pass_flag else "FAIL",
            "reason": (
                f"范围核验:PASS({measure_token} 在 {display_range}；原始范围={range_str})"
                if pass_flag
                else f"范围核验:FAIL({measure_token} 不在 {display_range}；原始范围={range_str})"
            ),
            "calc_type": "range",
        }

    # 对于“功率范围 + 频率轴”的复合 KB 条目，频率轴只用于筛候选，
    # 最终范围判定应回退到功率区间本身，而不是把 dBm 值拿去和 Hz 频段比较。
    if (
        capability_target == "power_accuracy"
        and axis_family == "frequency_band"
        and result_quantity in {"power_value", "power_error"}
    ):
        return None

    display_unit = extract_primary_unit_token(range_str)
    if axis_family == "frequency_band":
        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)
        display_unit = "Hz"
    elif axis_family == "period_band":
        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)
        display_unit = display_unit or "s"
    else:
        if band_kind != "range":
            return None
        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)

    if m_val is None:
        return None

    if band_kind == "discrete":
        discrete_points = tuple(getattr(selected_candidate, "discrete_points", ()) or ())
        matched = None
        for point in discrete_points:
            tol = max(abs(point) * 1e-12, 1e-12)
            if abs(m_val - point) <= tol:
                matched = point
                break
        if matched is not None:
            return {
                "status": "PASS",
                "reason": (
                    f"范围核验:PASS({measure_token} 命中 KB 离散点 "
                    f"[{', '.join(f'{p:.12g} {display_unit}' for p in discrete_points)}]；原始范围={range_str})"
                ),
                "calc_type": "range",
            }
        return {
            "status": "FAIL",
            "reason": (
                f"范围核验:FAIL({measure_token} 未命中 KB 离散点 "
                f"[{', '.join(f'{p:.12g} {display_unit}' for p in discrete_points)}]；原始范围={range_str})"
            ),
            "calc_type": "range",
        }

    if band_kind == "range":
        lower = getattr(selected_candidate, "band_lower", None)
        upper = getattr(selected_candidate, "band_upper", None)
        if lower is None or upper is None:
            return None
        tolerance = max(max(abs(lower), abs(upper)) * 1e-9, 1e-12)
        compared_token = measure_token
        if axis_family == "period_band":
            compared_token = _format_period_band_scalar(m_val, display_unit)
        if (
            capability_target == "modulation_quality"
            and result_quantity == "evm"
            and lower >= 0
            and m_val < (lower - tolerance)
        ):
            unit_label = display_unit or extract_primary_unit_token(range_str)
            if axis_family == "period_band":
                display_range = _format_period_band_range(lower, upper, unit_label)
            else:
                display_range = f"[{lower:.12g} {unit_label}, {upper:.12g} {unit_label}]"
            return {
                "status": "REVIEW",
                "reason": (
                    f"范围核验:REVIEW({compared_token} 低于能力下界 "
                    f"{_format_period_band_scalar(lower, unit_label) if axis_family == 'period_band' else f'{lower:.12g} {unit_label}'}；"
                    f"当前值优于 KB 覆盖下界，建议人工确认是否按能力边界处理；原始范围={range_str}；归一化范围={display_range})"
                ),
                "calc_type": "range",
            }
        pass_flag = (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance))
        if axis_family == "period_band":
            display_range = _format_period_band_range(lower, upper, display_unit)
        else:
            display_range = f"[{lower:.12g} {display_unit}, {upper:.12g} {display_unit}]"
        if pass_flag:
            reason = f"范围核验:PASS({compared_token} 在 {display_range}；原始范围={range_str})"
        else:
            reason = f"范围核验:FAIL({compared_token} 不在 {display_range}；原始范围={range_str})"
        return {
            "status": "PASS" if pass_flag else "FAIL",
            "reason": reason,
            "calc_type": "range",
        }

    return None


def verify_range_logic(measure_val, range_str, selected_candidate=None):
    """
    范围核验逻辑，保持和原版主线一致：
    1. 频点列表如 1MHz,2MHz,5MHz,10MHz 视为离散点集合。
    2. 其他范围按上下限、单边限值或对称限值判断。
    """
    try:
        if _is_missing(measure_val) or _is_missing(range_str):
            return json.dumps(
                {"status": "PASS", "reason": "测量值或范围缺失 -> Skip", "calc_type": "range"},
                ensure_ascii=False,
            )

        direct_selected_payload = _verify_range_with_selected_candidate(measure_val, range_str, selected_candidate)
        if direct_selected_payload is not None:
            return json.dumps(direct_selected_payload, ensure_ascii=False)

        measure_token = extract_value_token(str(measure_val)) or str(measure_val)
        measure_str = str(measure_val)
        measure_unit = None

        sensitivity_match = re.search(
            r"(?:Sensitivity|sensitivity)[^:]*:\s*([-+]?\d*\.?\d+)\s*(dBm|dBmV)",
            measure_str,
            re.IGNORECASE,
        )
        if sensitivity_match:
            measure_unit = sensitivity_match.group(2)
        else:
            dbm_match = re.search(r"[-+]?\d*\.?\d+\s*(dBm|dBmV)", measure_str)
            if dbm_match:
                measure_unit = dbm_match.group(1)
            else:
                measure_unit = extract_primary_unit_token(measure_val) or extract_primary_unit_token(range_str)

        range_unit = extract_primary_unit_token(range_str)

        if _is_power_unit(measure_unit) and _is_voltage_unit(range_unit):
            freq_match = re.search(r"\(([^)]+)\)", str(range_str))
            if freq_match:
                freq_range_str = freq_match.group(1)
                freq_token = None
                freq_units = ["Hz", "kHz", "MHz", "GHz", "THz"]
                for fu in freq_units:
                    m = re.search(r"(\d+(?:\.\d+)?)\s*" + re.escape(fu), str(measure_val), re.IGNORECASE)
                    if m:
                        freq_token = m.group(0)
                        break

                if freq_token:
                    return json.dumps(
                        {
                            "status": "PASS",
                            "reason": f"电平范围核验:PASS({measure_unit} vs {range_unit}，频点 {freq_token} 位于 {freq_range_str} 内)",
                            "calc_type": "range",
                        },
                        ensure_ascii=False,
                    )

            return json.dumps(
                {
                    "status": "PASS",
                    "reason": f"电平范围核验:PASS({measure_unit} vs {range_unit})",
                    "calc_type": "range",
                },
                ensure_ascii=False,
            )

        def _fmt_with_unit(val: float, explicit_unit: str = "") -> str:
            unit = explicit_unit or measure_unit
            if unit in _TIME_DISPLAY_FACTORS:
                return _format_period_band_scalar(val, unit)
            return f"{val} {unit}".strip()

        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)
        if m_val is None:
            return json.dumps(
                {"status": "ERROR", "reason": f"无法解析测量值: {measure_val}", "calc_type": "range"},
                ensure_ascii=False,
            )

        discrete_points = _parse_frequency_point_list(str(range_str))
        if discrete_points and _is_discrete_frequency_point_list(str(range_str)):
            matched_point = None
            for candidate in discrete_points:
                candidate_tol = max(abs(candidate) * 1e-9, 1e-12)
                if abs(m_val - candidate) <= candidate_tol:
                    matched_point = candidate
                    break

            if matched_point is not None:
                status = "PASS"
                reason = f"范围核验:PASS({measure_token} 位于 [{range_str}])"
            else:
                status = "FAIL"
                reason = f"范围核验:FAIL({measure_token} 不在 [{range_str}])"
            return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)

        prefix_match = re.match(r"^(<=|>=|<|>)", str(range_str).strip())
        if prefix_match:
            range_lower_upper = parse_range_limit(range_str)
            if range_lower_upper is not None:
                lower, upper = range_lower_upper
                tolerance = max(max(abs(lower), abs(upper)) * 1e-9, 1e-12)
                pass_flag = (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance))
                status = "PASS" if pass_flag else "FAIL"
                reason = (
                    f"范围核验:PASS({measure_token} 在 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}])"
                    if pass_flag
                    else f"范围核验:FAIL({measure_token} 不在 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}])"
                )
                return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)

        symmetric_limit = parse_symmetric_limit(range_str)
        if symmetric_limit is not None:
            kind = symmetric_limit[0]
            abs_val = abs(m_val)
            if kind == "range":
                lower, upper = symmetric_limit[1], symmetric_limit[2]
                tolerance = max(max(abs(lower), abs(upper)) * 1e-9, 1e-12)
                pass_flag = (abs_val >= (lower - tolerance)) and (abs_val <= (upper + tolerance))
                status = "PASS" if pass_flag else "FAIL"
                reason = (
                    f"对称范围核验:PASS({ _fmt_with_unit(abs_val) } 在 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}])"
                    if pass_flag
                    else f"对称范围核验:FAIL({ _fmt_with_unit(abs_val) } 不在 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}])"
                )
                return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)
            if kind == "limit":
                thr = symmetric_limit[1]
                tolerance = max(abs(thr) * 1e-9, 1e-12)
                pass_flag = abs_val <= (thr + tolerance)
                status = "PASS" if pass_flag else "FAIL"
                reason = (
                    f"对称限值核验:PASS({ _fmt_with_unit(abs_val) } <= {_fmt_with_unit(thr, range_unit)})"
                    if pass_flag
                    else f"对称限值核验:FAIL({ _fmt_with_unit(abs_val) } > {_fmt_with_unit(thr, range_unit)})"
                )
                return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)

        range_lower_upper = parse_range_limit(range_str)
        if range_lower_upper is not None:
            lower, upper = range_lower_upper
            tolerance = max(max(abs(lower), abs(upper)) * 1e-9, 1e-12)
            mixed_units = _has_mixed_units(str(range_str))
            display_range = str(range_str).strip() if mixed_units else f"[{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"

            if (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance)):
                status = "PASS"
                reason = f"范围核验:PASS({measure_token} 在 {display_range})"
            else:
                status = "FAIL"
                reason = f"范围核验:FAIL({measure_token} 不在 {display_range})"
        else:
            single_limit = parse_single_sided_limit(range_str)
            if single_limit is not None:
                op, thr = single_limit
                pass_flag = False
                tolerance = max(abs(thr) * 1e-9, 1e-12)
                if op == "<":
                    pass_flag = m_val < (thr + tolerance)
                elif op == "<=":
                    pass_flag = m_val <= (thr + tolerance)
                elif op == ">":
                    pass_flag = m_val > (thr - tolerance)
                elif op == ">=":
                    pass_flag = m_val >= (thr - tolerance)

                if pass_flag:
                    status = "PASS"
                    reason = f"单边限值核验:PASS({measure_token} {op}{_fmt_with_unit(thr, range_unit)})"
                else:
                    status = "FAIL"
                    reason = f"单边限值核验:FAIL({measure_token} 不满足 {op}{_fmt_with_unit(thr, range_unit)})"
            else:
                if re.search(r"\d", str(range_str)):
                    status = "PASS"
                    reason = f"范围核验:PASS(按文本范围判断，范围={range_str})"
                else:
                    status = "ERROR"
                    reason = f"无法解析范围: {range_str}"

        return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "ERROR", "reason": str(e), "calc_type": "range"}, ensure_ascii=False)
def verify_error_logic(error_val: Any, limit_val: str, measure_val: Any = None) -> str:
    """
    误差核验逻辑（与原始 core/error_verifier.py 完全一致）
    """
    try:
        if _is_missing(error_val) or _is_missing(limit_val):
            return json.dumps(
                {"status": "PASS", "reason": "误差或限值缺失 -> Skip", "calc_type": "error"},
                ensure_ascii=False,
            )

        # 解析误差值，保留符号，避免负阈值被误判
        err_value, _ = parse_value_with_unit(error_val, keep_sign=True)
        if err_value is None:
            # 尝试解析绝对误差标记
            return json.dumps(
                {"status": "PASS", "reason": "误差值格式无法解析，默认通过", "calc_type": "error"},
                ensure_ascii=False,
            )

        limit_text = str(limit_val).strip()
        measure_text = _coerce_text(measure_val)

        single_limit = parse_single_sided_limit(limit_text)
        if single_limit is not None:
            op, thr = single_limit
            if "%" in limit_text:
                limit_ratio = abs(thr)
                if "%" in str(error_val):
                    err_ratio, _ = parse_value_with_unit(error_val, keep_sign=True)
                    if err_ratio is None:
                        return json.dumps(
                            {"status": "ERROR", "reason": f"无法解析误差值: {error_val}", "calc_type": "error"},
                            ensure_ascii=False,
                        )
                else:
                    measure_abs, _ = parse_value_with_unit(measure_text, keep_sign=True)
                    if measure_abs is None or measure_abs == 0:
                        return json.dumps(
                            {
                                "status": "REVIEW",
                                "reason": f"百分比限值需要测量值换算为相对误差，但测量值缺失或为0：measure='{measure_val}'",
                                "calc_type": "error",
                            },
                            ensure_ascii=False,
                        )
                    err_abs, _ = parse_value_with_unit(error_val, keep_sign=True)
                    if err_abs is None:
                        return json.dumps(
                            {"status": "ERROR", "reason": f"无法解析误差值: {error_val}", "calc_type": "error"},
                            ensure_ascii=False,
                        )
                    err_ratio = abs(err_abs) / abs(measure_abs)
                tolerance = max(abs(limit_ratio) * 0.001, 1e-15)
                ok = err_ratio <= (limit_ratio + tolerance)
                return json.dumps(
                    {
                        "status": "PASS" if ok else "FAIL",
                        "reason": (
                            f"相对误差核验:PASS({err_ratio * 100:.3f}% <= {limit_ratio * 100:.3f}%)"
                            if ok
                            else f"相对误差核验:FAIL({err_ratio * 100:.3f}% > {limit_ratio * 100:.3f}%)"
                        ),
                        "error_value": err_ratio,
                        "limit_value": limit_ratio,
                        "calc_type": "error",
                    },
                    ensure_ascii=False,
                )
            tolerance = max(abs(thr) * 0.001, 1e-15)
            if op == "<":
                ok = err_value < (thr + tolerance)
            elif op == "<=":
                ok = err_value <= (thr + tolerance)
            elif op == ">":
                ok = err_value > (thr - tolerance)
            else:
                ok = err_value >= (thr - tolerance)
            return json.dumps(
                {
                    "status": "PASS" if ok else "FAIL",
                    "reason": f"误差值({error_val}) {op} 限值({limit_val})",
                    "error_value": err_value,
                    "limit_value": thr,
                    "calc_type": "error",
                },
                ensure_ascii=False,
            )

        if "%" in limit_text:
            limit_ratio, _ = parse_value_with_unit(limit_text, keep_sign=True)
            if limit_ratio is None:
                return json.dumps(
                    {"status": "ERROR", "reason": f"无法解析限值: {limit_val}", "calc_type": "error"},
                    ensure_ascii=False,
                )
            if "%" in str(error_val):
                err_ratio, _ = parse_value_with_unit(error_val, keep_sign=True)
                if err_ratio is None:
                    return json.dumps(
                        {"status": "ERROR", "reason": f"无法解析误差值: {error_val}", "calc_type": "error"},
                        ensure_ascii=False,
                    )
            else:
                measure_abs, _ = parse_value_with_unit(measure_text, keep_sign=True)
                if measure_abs is None or measure_abs == 0:
                    return json.dumps(
                        {
                            "status": "REVIEW",
                            "reason": f"百分比限值需要测量值换算为相对误差，但测量值缺失或为0：measure='{measure_val}'",
                            "calc_type": "error",
                        },
                        ensure_ascii=False,
                    )
                err_abs, _ = parse_value_with_unit(error_val, keep_sign=True)
                if err_abs is None:
                    return json.dumps(
                        {"status": "ERROR", "reason": f"无法解析误差值: {error_val}", "calc_type": "error"},
                        ensure_ascii=False,
                    )
                err_ratio = abs(err_abs) / abs(measure_abs)
            tolerance = max(abs(limit_ratio) * 0.001, 1e-15)
            ok = err_ratio <= (limit_ratio + tolerance)
            return json.dumps(
                {
                    "status": "PASS" if ok else "FAIL",
                    "reason": (
                        f"相对误差核验:PASS({err_ratio * 100:.3f}% <= {limit_ratio * 100:.3f}%)"
                        if ok
                        else f"相对误差核验:FAIL({err_ratio * 100:.3f}% > {limit_ratio * 100:.3f}%)"
                    ),
                    "error_value": err_ratio,
                    "limit_value": limit_ratio,
                    "calc_type": "error",
                },
                ensure_ascii=False,
            )

        symmetric_limit = parse_symmetric_limit(limit_text)
        if symmetric_limit is not None:
            kind = symmetric_limit[0]
            err_abs = abs(err_value)
            if kind == "range":
                lower, upper = symmetric_limit[1], symmetric_limit[2]
                tolerance = max(abs(upper - lower) * 0.001, 1e-15)
                ok = (err_abs >= (lower - tolerance)) and (err_abs <= (upper + tolerance))
                return json.dumps(
                    {
                        "status": "PASS" if ok else "FAIL",
                        "reason": (
                            f"误差绝对值({err_abs}) 在对称范围 [{lower}, {upper}] 内"
                            if ok
                            else f"误差绝对值({err_abs}) 不在对称范围 [{lower}, {upper}] 内"
                        ),
                        "error_value": err_value,
                        "limit_value": [lower, upper],
                        "calc_type": "error",
                    },
                    ensure_ascii=False,
                )
            if kind == "limit":
                thr = symmetric_limit[1]
                tolerance = max(abs(thr) * 0.001, 1e-15)
                ok = abs(err_value) <= (thr + tolerance)
                return json.dumps(
                    {
                        "status": "PASS" if ok else "FAIL",
                        "reason": (
                            f"abs({error_val}) <= {limit_val}"
                            if ok
                            else f"abs({error_val}) > {limit_val}"
                        ),
                        "error_value": err_value,
                        "limit_value": thr,
                        "calc_type": "error",
                    },
                    ensure_ascii=False,
                )

        range_limit = parse_range_limit(limit_text)
        if range_limit is not None:
            lower, upper = range_limit
            if lower > upper:
                lower, upper = upper, lower
            tolerance = max(abs(upper - lower) * 0.001, 1e-15)
            ok = (err_value >= (lower - tolerance)) and (err_value <= (upper + tolerance))
            return json.dumps(
                {
                    "status": "PASS" if ok else "FAIL",
                    "reason": (
                        f"误差值({error_val}) 在范围 [{lower}, {upper}] 内"
                        if ok
                        else f"误差值({error_val}) 不在范围 [{lower}, {upper}] 内"
                    ),
                    "error_value": err_value,
                    "limit_value": [lower, upper],
                    "calc_type": "error",
                },
                ensure_ascii=False,
            )

        # 回退：按绝对值比较
        limit_value, _ = parse_value_with_unit(limit_val, keep_sign=True)
        if limit_value is None:
            return json.dumps(
                {"status": "ERROR", "reason": f"无法解析限值: {limit_val}", "calc_type": "error"},
                ensure_ascii=False,
            )

        err_abs = abs(err_value)
        limit_abs = abs(limit_value)
        tolerance = max(limit_abs * 0.001, 1e-15)
        if err_abs <= (limit_abs + tolerance):
            return json.dumps(
                {
                    "status": "PASS",
                    "reason": f"误差值({error_val}) ≤ 限值({limit_val})",
                    "error_value": err_value,
                    "limit_value": limit_value,
                    "calc_type": "error",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "FAIL",
                "reason": f"误差值({error_val}) > 限值({limit_val})",
                "error_value": err_value,
                "limit_value": limit_value,
                "calc_type": "error",
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps(
            {"status": "ERROR", "reason": f"误差验证出错: {str(e)}", "calc_type": "error"},
            ensure_ascii=False,
        )


def verify_uncertainty_logic(measure_val: Any, cert_u: str, kb_u: str) -> str:
    """
    不确定度核验逻辑（与原始 core/uncertainty_verifier.py 完全一致）
    """
    try:
        if _is_missing(measure_val) or _is_missing(cert_u) or _is_missing(kb_u):
            return json.dumps(
                {"status": "PASS", "reason": "测量值或不确定度缺失 -> Skip", "calc_type": "uncertainty"},
                ensure_ascii=False,
            )

        # 解析测量值
        m_val, _ = parse_value_with_unit(measure_val)
        if m_val is None:
            return json.dumps(
                {"status": "ERROR", "reason": f"无法解析测量值: {measure_val}", "calc_type": "uncertainty"},
                ensure_ascii=False,
            )

        cert_kind = detect_uncertainty_kind(cert_u, measure_val)
        kb_kind = detect_uncertainty_kind(kb_u, measure_val)

        cert_lower, cert_upper, cert_reason, cert_is_interval = _parse_uncertainty_bounds(cert_u, measure_val, cert_kind)
        kb_lower, kb_upper, kb_reason, kb_is_interval = _parse_uncertainty_bounds(kb_u, measure_val, kb_kind)

        if cert_lower is None or kb_lower is None:
            return json.dumps(
                {
                    "status": "ERROR",
                    "reason": f"证书U或KB_U缺失或无法解析：cert_u='{cert_u}', kb_u='{kb_u}'",
                    "calc_type": "uncertainty",
                },
                ensure_ascii=False,
            )

        interval_mode = cert_is_interval or kb_is_interval
        both_relative = cert_kind == "relative" and kb_kind == "relative"
        compare_as_relative = both_relative
        base_for_rel = abs(m_val) if m_val is not None else None

        cert_lower_cmp, cert_upper_cmp = cert_lower, cert_upper
        kb_lower_cmp, kb_upper_cmp = kb_lower, kb_upper
        if not compare_as_relative and (cert_kind == "relative" or kb_kind == "relative"):
            if base_for_rel is None or base_for_rel == 0:
                return json.dumps(
                    {
                        "status": "REVIEW",
                        "reason": "相对不确定度需要测量值换算为绝对值，但测量值缺失或为0，需人工核验",
                        "cert_u": cert_upper if cert_is_interval else cert_lower,
                        "kb_u": kb_upper if kb_is_interval else kb_lower,
                        "cert_u_display": _format_uncertainty_display(
                            cert_u,
                            cert_upper if cert_is_interval else cert_lower,
                            measure_val=measure_val,
                            kind=cert_kind,
                            converted=cert_kind == "relative" and not cert_is_interval,
                        ),
                        "kb_u_display": _format_uncertainty_display(
                            kb_u,
                            kb_upper if kb_is_interval else kb_lower,
                            measure_val=measure_val,
                            kind=kb_kind,
                            converted=kb_kind == "relative" and not kb_is_interval,
                        ),
                        "conversion_summary": "测量值缺失，无法将相对不确定度换算为绝对值",
                        "comparison_mode": "interval_bounds" if interval_mode else "normalized_abs",
                        "cert_kind": cert_kind,
                        "kb_kind": kb_kind,
                        "detail": "relative_to_absolute_failed",
                        "calc_type": "uncertainty",
                    },
                    ensure_ascii=False,
                )
            if cert_kind == "relative":
                cert_lower_cmp = cert_lower * base_for_rel
                cert_upper_cmp = cert_upper * base_for_rel
            if kb_kind == "relative":
                kb_lower_cmp = kb_lower * base_for_rel
                kb_upper_cmp = kb_upper * base_for_rel

        compare_scale = max(abs(kb_upper_cmp), abs(kb_lower_cmp), abs(cert_upper_cmp), abs(cert_lower_cmp))
        tolerance = max(compare_scale * 0.001, 1e-15)
        cert_display = _format_uncertainty_display(
            cert_u,
            cert_upper if cert_is_interval else cert_lower,
            measure_val=measure_val,
            kind=cert_kind,
            converted=cert_kind == "relative" and not both_relative and not cert_is_interval,
        )
        kb_display = _format_uncertainty_display(
            kb_u,
            kb_upper if kb_is_interval else kb_lower,
            measure_val=measure_val,
            kind=kb_kind,
            converted=kb_kind == "relative" and not both_relative and not kb_is_interval,
        )
        conversion_summary = f"证书={cert_display}; KB={kb_display}"

        if interval_mode:
            if cert_lower_cmp >= (kb_upper_cmp - tolerance):
                reason_text = (
                    f"证书区间[{to_plain_decimal(cert_lower_cmp)}, {to_plain_decimal(cert_upper_cmp)}] "
                    f"≥ KB区间[{to_plain_decimal(kb_lower_cmp)}, {to_plain_decimal(kb_upper_cmp)}]，按上下界比较"
                )
                status = "PASS"
            elif cert_upper_cmp < (kb_lower_cmp + tolerance):
                reason_text = (
                    f"证书区间[{to_plain_decimal(cert_lower_cmp)}, {to_plain_decimal(cert_upper_cmp)}] "
                    f"< KB区间[{to_plain_decimal(kb_lower_cmp)}, {to_plain_decimal(kb_upper_cmp)}]，按上下界比较"
                )
                status = "FAIL"
            else:
                reason_text = (
                    f"证书区间[{to_plain_decimal(cert_lower_cmp)}, {to_plain_decimal(cert_upper_cmp)}] "
                    f"与 KB区间[{to_plain_decimal(kb_lower_cmp)}, {to_plain_decimal(kb_upper_cmp)}] 存在重叠，按区间规则判定为 PASS"
                )
                status = "PASS"
            return json.dumps(
                {
                    "status": status,
                    "reason": reason_text,
                    "cert_u": cert_upper_cmp if cert_is_interval else cert_lower_cmp,
                    "kb_u": kb_upper_cmp if kb_is_interval else kb_lower_cmp,
                    "cert_u_display": cert_display,
                    "kb_u_display": kb_display,
                    "conversion_summary": conversion_summary,
                    "comparison_mode": "interval_bounds",
                    "cert_kind": cert_kind,
                    "kb_kind": kb_kind,
                    "detail": f"cert={cert_reason}; kb={kb_reason}",
                    "calc_type": "uncertainty",
                },
                ensure_ascii=False,
            )

        # 非区间，按单值比较
        cert_u_abs = abs(cert_upper_cmp)
        kb_u_abs = abs(kb_lower_cmp)

        if cert_kind == "relative" or kb_kind == "relative":
            converted_note = "，已将相对不确定度按测量值换算为绝对不确定度后比较"
        else:
            converted_note = ""

        if cert_u_abs >= (kb_u_abs - tolerance):
            if both_relative:
                reason_text = f"证书不确定度({cert_u}) ≥ 知识库要求({kb_u})，均为相对不确定度，直接比较系数"
            else:
                reason_text = f"证书不确定度({cert_u}) ≥ 知识库要求({kb_u}){converted_note}"
            return json.dumps(
                {
                    "status": "PASS",
                    "reason": reason_text,
                    "cert_u": cert_upper,
                    "kb_u": kb_lower,
                    "cert_u_display": cert_display,
                    "kb_u_display": kb_display,
                    "conversion_summary": conversion_summary,
                    "comparison_mode": "relative_coef" if both_relative else "normalized_abs",
                    "cert_kind": cert_kind,
                    "kb_kind": kb_kind,
                    "detail": f"cert={cert_reason}; kb={kb_reason}",
                    "calc_type": "uncertainty"
                },
                ensure_ascii=False,
            )
        else:
            if both_relative:
                reason_text = f"证书不确定度({cert_u}) < 知识库要求({kb_u})，均为相对不确定度，直接比较系数"
            else:
                reason_text = f"证书不确定度({cert_u}) < 知识库要求({kb_u}){converted_note}"
            return json.dumps(
                {
                    "status": "FAIL",
                    "reason": reason_text,
                    "cert_u": cert_upper,
                    "kb_u": kb_lower,
                    "cert_u_display": cert_display,
                    "kb_u_display": kb_display,
                    "conversion_summary": conversion_summary,
                    "comparison_mode": "relative_coef" if both_relative else "normalized_abs",
                    "cert_kind": cert_kind,
                    "kb_kind": kb_kind,
                    "detail": f"cert={cert_reason}; kb={kb_reason}",
                    "calc_type": "uncertainty"
                },
                ensure_ascii=False,
            )

    except Exception as e:
        return json.dumps(
            {"status": "ERROR", "reason": f"不确定度验证出错: {str(e)}", "calc_type": "uncertainty"},
            ensure_ascii=False,
        )
