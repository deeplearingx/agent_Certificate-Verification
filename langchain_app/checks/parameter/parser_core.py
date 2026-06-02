#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameter parsing core layer.

This module owns the low-level token / unit / limit parsing helpers used across
langgraph parameter verification.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

# ===================== 1. 定义 Python 计算工具集 =====================

# 支持 6.6×10⁻⁹ 这类科学计数法的解析
SUPERSCRIPT_MAP = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    '⁻': '-', '⁺': '+',
}
# ===================== 新增：单位换算表 =====================
UNIT_MULTIPLIERS = {
    'T': 1e12, 'G': 1e9, 'M': 1e6, 'k': 1e3, 'K': 1e3, # 频率/电阻等
    'm': 1e-3, 'u': 1e-6, 'μ': 1e-6, 'n': 1e-9, 'p': 1e-12 # 电压/时间等
}

# ✅ 长度单位白名单：为了可读性，保留 nm/um/mm/pm 作为原单位，不按前缀换算成 m
ATOMIC_LENGTH_UNITS = {
    "pm", "nm", "um", "μm", "mm", "cm"  # 你需要哪些就留哪些
}

CANONICAL_UNIT_MAP = {
    "thz": "THz",
    "ghz": "GHz",
    "mhz": "MHz",
    "khz": "kHz",
    "hz": "Hz",
    "kv": "kV",
    "mv": "mV",
    "uv": "uV",
    "v": "V",
    "ma": "mA",
    "ua": "uA",
    "a": "A",
    "ms": "ms",
    "s/d": "s/d",
    "s/m": "s/m",
    "us": "us",
    "min": "min",
    "h": "h",
    "ns": "ns",
    "ps": "ps",
    "s": "s",
    "pm": "pm",
    "nm": "nm",
    "um": "um",
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "m2": "m2",
    "m3": "m3",
    "m/s": "m/s",
    "m/s2": "m/s2",
    "m/s3": "m/s3",
    "db": "dB",
    "dbc": "dBc",
    "dbc/hz": "dBc/Hz",
    "dbm": "dBm",
    "dbmv": "dBmV",
    "deg": "deg",
    "°": "°",
}

EXACT_UNIT_MULTIPLIERS = {
    "THz": 1e12,
    "GHz": 1e9,
    "MHz": 1e6,
    "kHz": 1e3,
    "Hz": 1.0,
    "kV": 1e3,
    "V": 1.0,
    "mV": 1e-3,
    "uV": 1e-6,
    "A": 1.0,
    "mA": 1e-3,
    "uA": 1e-6,
    "s": 1.0,
    "s/d": 1.0 / 86400.0,
    "s/m": 1.0 / (30.0 * 86400.0),
    "h": 3600.0,
    "ms": 1e-3,
    "us": 1e-6,
    "min": 60.0,
    "ns": 1e-9,
    "ps": 1e-12,
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "pm": 1e-12,
    "m2": 1.0,
    "m3": 1.0,
    "m/s": 1.0,
    "m/s2": 1.0,
    "m/s3": 1.0,
    "dB": 1.0,
    "dBc": 1.0,
    "dBc/Hz": 1.0,
    "dBm": 1.0,
    "dBmV": 1.0,
    "deg": 1.0,
    "°": 1.0,
}

VALUE_TOKEN_PATTERN = re.compile(
    r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*"
    r"(dBc/Hz|dBc|dBmV|dBm|dB|%|°|deg|THz|GHz|MHz|kHz|Hz|"
    r"kV|mV|uV|μV|µV|V|mA|uA|μA|µA|A|"
    r"m/s(?:\^?[23]|[²³虏鲁])?|pm|nm|um|μm|µm|mm|cm|ms|min|us|μs|µs|ns|ps|h|s/d|s/m|s|"
    r"m(?:\^?[23]|[²³虏鲁])?)?",
    flags=re.IGNORECASE,
)

PREFERRED_RANGE_VALUE_PATTERNS = [
    r"标准值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s/d|s/m|s|pm|nm|um|mm|cm|m)",
    r"标准值[:：]\s*([^,，;；<\n]+)",
    r"Reference\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s/d|s/m|s|pm|nm|um|mm|cm|m)",
    r"Reference[:：]\s*([^,，;；<\n]+)",
    r"测量值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s/d|s/m|s|pm|nm|um|mm|cm|m)",
    r"测量值[:：]\s*([^,，;；<\n]+)",
    r"指示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s/d|s/m|s|pm|nm|um|mm|cm|m)",
    r"指示值[:：]\s*([^,，;；<\n]+)",
    r"示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s/d|s/m|s|pm|nm|um|mm|cm|m)",
    r"示值[:：]\s*([^,，;；<\n]+)",
    r"读数(?:\s*\([^)]*\))?\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s/d|s/m|s|pm|nm|um|mm|cm|m)",
    r"读数(?:\s*\([^)]*\))?\s*[:：]\s*([^,，;；<\n]+)",
    r"\bEVM\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"\bEVM\b\s*[:：]\s*([^,，;；<\n]+)",
    r"\bPhase Error\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"\bPhase Error\b\s*[:：]\s*([^,，;；<\n]+)",
    r"\bIQ Offset\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|min|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"\bIQ Offset\b\s*[:：]\s*([^,，;；<\n]+)",
    r"二次谐波\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"二次谐波\s*[:：]\s*([^,，;；<\n]+)",
    r"杂波抑制\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"杂波抑制\s*[:：]\s*([^,，;；<\n]+)",
]


RANGE_TOOL_VALUE_PATTERNS = [
    r"标称值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"标称值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"Nominal\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"Nominal[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"\bEVM\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"\bEVM\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bPhase Error\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"\bPhase Error\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bIQ Offset\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"\bIQ Offset\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"二次谐波\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"二次谐波\s*[:：=]\s*([^,，;；<\n]+)",
    r"杂波抑制\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"杂波抑制\s*[:：=]\s*([^,，;；<\n]+)",
    r"测量值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"测量值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"指示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"指示值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"示值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"读数(?:\s*\([^)]*\))?\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"读数(?:\s*\([^)]*\))?\s*[:：=]\s*([^,，;；<\n]+)",
    r"(?:开机特性|Warm-up(?:\s+Characteristics?)?)\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"(?:开机特性|Warm-up(?:\s+Characteristics?)?)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"(?:短期频率稳定度|频率稳定度|Short-Term(?:\s+Frequency)?\s+Stability)\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"(?:短期频率稳定度|频率稳定度|Short-Term(?:\s+Frequency)?\s+Stability)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"标准值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"标准值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"Reference\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|h|s|pm|nm|um|mm|cm|m)",
    r"Reference[^:：=]*[:：=]\s*([^,，;；<\n]+)",
]


RANGE_TOOL_VALUE_PATTERNS_SAFE = [
    r"(?:标称值|Nominal)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"\bEVM\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bPhase Error\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bIQ Offset\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"(?:二次谐波|杂波抑制)\s*[:：=]\s*([^,，;；<\n]+)",
    r"(?:测量值|指示值|示值|读数(?:\s*\([^)]*\))?)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"(?:标准值|Reference)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
]


def _normalize_unit_text(unit: str) -> str:
    u = (unit or "").strip()
    if not u:
        return ""

    u = u.replace(" ", "")
    u = u.replace("μ", "u").replace("µ", "u")
    u = u.replace("²", "2").replace("³", "3").replace("^2", "2").replace("^3", "3")
    u = u.replace("虏", "2").replace("鲁", "3")

    lowered = u.lower()
    return CANONICAL_UNIT_MAP.get(lowered, u)


def _unit_multiplier_from_text(unit: str) -> float:
    u = _normalize_unit_text(unit)
    if not u:
        return 1.0

    if u in EXACT_UNIT_MULTIPLIERS:
        return EXACT_UNIT_MULTIPLIERS[u]

    if "/" in u:
        return 1.0

    if u.startswith("dB") or u in {"deg", "°"}:
        return 1.0

    if len(u) > 1 and u[0] in UNIT_MULTIPLIERS and re.search(r"[A-Za-zΩ]", u[1:]):
        return UNIT_MULTIPLIERS[u[0]]

    return 1.0


def _extract_value_token(text: str) -> Optional[str]:
    if not text:
        return None

    s = str(text).strip()
    s = s.replace("μ", "u").replace("µ", "u")
    s = s.replace("²", "2").replace("³", "3").replace("^2", "2").replace("^3", "3")
    s = s.replace("虏", "2").replace("鲁", "3")

    better_sci_match = re.search(
        r"([-+]?\d*\.?\d+\s*[×脳xX*]\s*10(?:\s*\^\s*[-+]?\d+|\s*[-+0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+))"
        r"\s*([A-Za-z%/°μ²³\-]*)",
        s,
        flags=re.IGNORECASE,
    )
    if better_sci_match:
        num = better_sci_match.group(1).strip()
        unit = _normalize_unit_text(better_sci_match.group(2) or "")
        return f"{num} {unit}".strip()

    sci_match = re.search(
        r"([-+]?\d*\.?\d+\s*[脳xX*]\s*10(?:\s*\^\s*[-+]?\d+|\s*[-+0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+))"
        r"\s*(dBc/Hz|dBc|dBmV|dBm|dB|%|掳|deg|THz|GHz|MHz|kHz|Hz|"
        r"kV|mV|uV|渭V|碌V|V|mA|uA|渭A|碌A|A|"
        r"m/s(?:\^?[23]|[虏鲁铏忛瞾])?|pm|nm|um|渭m|碌m|mm|cm|m(?:\^?[23]|[虏鲁铏忛瞾])?|"
        r"ms|us|渭s|碌s|ns|ps|s)?",
        s,
        flags=re.IGNORECASE,
    )
    if sci_match:
        num = sci_match.group(1).strip()
        unit = _normalize_unit_text(sci_match.group(2) or "")
        return f"{num} {unit}".strip()

    m = VALUE_TOKEN_PATTERN.search(s)
    if not m:
        return None

    num = m.group(1)
    unit = _normalize_unit_text(m.group(2) or "")
    return f"{num} {unit}".strip()


def extract_value_token(text: str) -> Optional[str]:
    """对外兼容导出。"""
    return _extract_value_token(text)


def _normalize_formula_unit(unit: str) -> str:
    u = _normalize_unit_text(unit)
    if not u:
        return ""

    if u in {"dBc/Hz", "m/s", "m/s2", "m/s3"}:
        return u

    if "/div" in u.lower():
        return _normalize_unit_text(u.split("/", 1)[0])

    if "/" in u:
        return _normalize_unit_text(u.split("/", 1)[0])

    return u


def _parse_extracted_token(token: str, keep_sign: bool = False) -> Tuple[Optional[float], Optional[str]]:
    normalized = _extract_value_token(token)
    if not normalized:
        return None, None

    value, _ = parse_value_with_unit(normalized, keep_sign=keep_sign)
    m = VALUE_TOKEN_PATTERN.search(normalized)
    unit = _normalize_unit_text(m.group(2) or "") if m else None
    return value, unit or None


def _extract_preferred_measure_token(measure_val: str) -> Optional[str]:
    s = str(measure_val or "")
    for pattern in PREFERRED_RANGE_VALUE_PATTERNS:
        m = re.search(pattern, s, flags=re.IGNORECASE)
        if m:
            # 检查有多少个捕获组
            if len(m.groups()) == 2:
                # 新模式：两个捕获组，需要合并为 "数值 单位"
                num = m.group(1)
                unit = m.group(2)
                if num and unit:
                    token = f"{num} {unit}"
                    return token
            elif len(m.groups()) == 1:
                # 旧模式：一个捕获组
                token = _extract_value_token(m.group(1))
                if token:
                    return token
    return _extract_value_token(s)
##识别KB的解析器
def norm_code(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"  # 无空格
    return re.sub(r"\s+", "", s).upper()



def extract_basis_code(criterion: str) -> Optional[str]:
    """
    统一忽略年份后缀：
    - JJG 237-2010 -> JJG 237
    - JJF 1234-2020 -> JJF 1234
    - GJB 7691-2012 -> GJB 7691
    """
    if not criterion:
        return None

    s = str(criterion)
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", s, re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"




def parse_unicode_sci_number(s: str) -> Optional[float]:
    """
    解析类似：
      - 6.6×10⁻⁹
      - 3.2x10⁻⁶
      - 1.0*10⁻³
      - 6.6x10^-9
      - 6.6×10^-9
    返回 float，解析失败返回 None
    """
    if not s:
        return None

    # 首先尝试解析 ^ 格式的科学计数法
    m = re.search(r'([+-]?\d*\.?\d+)\s*[×xX*]\s*10\s*\^\s*([+-]?\d+)', s)
    if m:
        try:
            mantissa = float(m.group(1))
            exp = int(m.group(2))
            return mantissa * (10 ** exp)
        except:
            pass

    # 然后解析 Unicode 上标格式的科学计数法
    m = re.search(r'([+-]?\d*\.?\d+)\s*[×xX*]\s*10\s*([\-+0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)', s)
    if not m:
        return None

    mantissa = float(m.group(1))
    exp_raw = m.group(2)

    # 上标指数 → 普通字符串
    exp_str = ''.join(SUPERSCRIPT_MAP.get(ch, ch) for ch in exp_raw)
    try:
        exp = int(exp_str)
    except ValueError:
        return None

    return mantissa * (10 ** exp)


def parse_value_with_unit(val_str, base_val=None, keep_sign: bool = False):
    """
    数值解析与单位折算工具 (增强版)
    - 支持 Unicode 科学计数法：6.6×10⁻⁹
    - 支持单位前缀：k/M/G/m/u/μ/n/p
    - 支持相对不确定度：
        * 0.5%   -> base * 0.005  (当 base_val 存在)
        * Urel=8e-9 -> base * 8e-9 (当 base_val 存在)
      并且当 base_val 不存在时：
        * 0.5% 返回 0.005（fraction），避免被当作 0.5
    - keep_sign=True 时保留正负号（用于误差单边阈值判断）
    """

    # 1) 缺失/无效
    if val_str is None:
        return None, "missing"
    s = str(val_str).strip()
    # ✅ 修正 OCR 常见大小写错误，避免 MV/UV 被当成倍率前缀 M/U
    s = re.sub(r"\bMV\b", "mV", s)
    s = re.sub(r"\bUV\b", "uV", s)
    s = re.sub(r"\bKV\b", "kV", s)

        # ✅ 修正频率单位大小写：mhz/ghz/khz -> MHz/GHz/kHz

    s = re.sub(r"\b(mhz|MHZ)\b", "MHz", s)   # 只归一化全小写/全大写错误写法
    s = re.sub(r"\b(ghz|GHZ)\b", "GHz", s)   # mHz(毫赫兹) 不受影响
    s = re.sub(r"\b(khz|KHZ)\b", "kHz", s)
    s = re.sub(r"\b(hz|HZ)\b",   "Hz",  s)
    # 注意：Mhz（M大写h小写）也应归一化为 MHz，按需加入：
    # s = re.sub(r"\\bMhz\\b", "MHz", s)

    if s == "" or s in ["-", "/", "N/A", "n/a", "None", "none"]:
        return None, "missing"

    s_lower = s.lower()
    has_percent = "%" in s_lower
    is_rel_keyword = ("urel" in s_lower) or ("u rel" in s_lower) or ("rel" in s_lower)

    # 2) 提取数值（保留符号）
    num = None
    sci_val = parse_unicode_sci_number(s)
    if sci_val is not None:
        num = sci_val
    else:
        m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if m:
            num = float(m.group(1))

    if num is None:
        return None, "missing"

    # 3) 单位倍率（避免把 m/s、m、dBc/Hz 等误当成前缀缩放）
    multiplier = 1.0
    if not has_percent:
        unit_part = re.sub(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", "", s).strip()
        if unit_part:
            unit_part_norm = _normalize_unit_text(unit_part)
            if unit_part_norm in ATOMIC_LENGTH_UNITS:
                multiplier = 1.0
            else:
                multiplier = _unit_multiplier_from_text(unit_part_norm)


    signed_val = num * multiplier
    abs_or_signed = signed_val if keep_sign else abs(signed_val)

    # 4) 相对不确定度换算（有 base_val 时直接转绝对值）
    if base_val is not None:
        if has_percent:
            # 0.5% -> base * 0.005
            v = base_val * (num / 100.0)
            return (v if keep_sign else abs(v)), "rel_percent_converted"
        if is_rel_keyword:
            # Urel=8e-9 -> base * 8e-9
            v = base_val * num
            return (v if keep_sign else abs(v)), "rel_coef_converted"

    # 5) 没有 base_val，但遇到百分数：返回 fraction，避免 0.5% 被当 0.5
    if base_val is None and has_percent:
        v = num / 100.0
        return (v if keep_sign else abs(v)), "percent_fraction"

    return abs_or_signed, "abs"



def to_plain_decimal(x: Optional[float], max_digits: int = 12) -> str:
    """
    将浮点数转为“非科学计数法”的字符串，如：
    6.6e-09 -> '0.0000000066'
    0.000066 -> '0.000066'
    """
    if x is None:
        return ""
    # 先用 g 避免太长
    s = f"{x:.{max_digits}g}"
    if "e" in s or "E" in s:
        # 再转成定点小数，然后去掉多余的 0
        fixed_digits = max(max_digits, 24)
        s = f"{x:.{fixed_digits}f}".rstrip("0").rstrip(".")
    return s





def parse_single_sided_limit(limit_str: str):
    """
    解析单边限值，例如:
      "<-75", "<= -75.0 dBc/Hz", ">0.1", ">= +3"
    返回: (op, threshold)  其中 op in {"<", "<=", ">", ">="}
    解析失败返回 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip()
    s = s.replace("≤", "<=").replace("≥", ">=")
    s = s.replace("＋", "+").replace("﹢", "+")
    s = s.replace("—", "-").replace("−", "-")

    m = re.search(r"(<=|>=|<|>)\s*(.+)$", s)
    if not m:
        return None

    op = m.group(1)
    thr, _ = parse_value_with_unit(m.group(2).strip(), keep_sign=True)
    if thr is None:
        return None
    return op, thr


def parse_range_limit(limit_str: str):
    """
    解析区间限值，例如:
      "-0.2~+0.1", "(-0.2, +0.1)", "-0.2 ～ 0.1"
    返回: (lower, upper) 或 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("[", "").replace("]", "")
    s = s.replace("（", "").replace("）", "")
    s = s.replace("(", "").replace(")", "")
    s = s.replace("～", "~")
    s = s.replace("≤", "<=").replace("≥", ">=")
    s = s.replace("＋", "+").replace("﹢", "+")
    s = s.replace("—", "-").replace("−", "-")

    # 先处理范围字符串前的比较符号（如 ">1 ms～" 这样的格式）
    prefix_op = None
    prefix_match = re.match(r"(<=|>=|<|>)\s*", s)
    if prefix_match:
        prefix_op = prefix_match.group(1)
        s = s[prefix_match.end():].strip()

    if "~" in s:
        parts = [p.strip() for p in s.split("~") if p.strip()]
    elif re.search(r"[，,]", s):
        parts = [p.strip() for p in re.split(r"[，,]", s) if p.strip()]
    else:
        return None

    if len(parts) < 2:
        return None

    def _extract_explicit_unit(part: str) -> Optional[str]:
        normalized = str(part or "").strip()
        if not normalized:
            return None
        for match in reversed(list(VALUE_TOKEN_PATTERN.finditer(normalized))):
            unit = _normalize_unit_text(match.group(2) or "")
            if unit and not normalized[match.end():].strip():
                return unit
        return None

    left_part = parts[0]
    right_part = parts[1]
    left_unit = _extract_explicit_unit(left_part)
    right_unit = _extract_explicit_unit(right_part)
    shared_unit = left_unit or right_unit or _extract_explicit_unit(s)

    if shared_unit and not left_unit:
        left_part = f"{left_part} {shared_unit}"
    if shared_unit and not right_unit:
        right_part = f"{right_part} {shared_unit}"

    a, _ = parse_value_with_unit(left_part, keep_sign=True)
    b, _ = parse_value_with_unit(right_part, keep_sign=True)
    if a is None or b is None:
        return None

    # 接受任意顺序的范围，自动处理为 [min, max]
    # CNAS文件明确说明这种格式是有效的，不再发出警告
    lower, upper = min(a, b), max(a, b)

    # 前缀比较符仅表示边界开闭，不应改变端点排序。
    # 例如 "<10 μs～50 ns" 仍应视作 [50 ns, 10 μs]。

    return lower, upper


def convert_time_unit(value: float, from_unit: str, to_unit: str) -> float:
    """
    时间单位换算
    支持: ns, us/μs, ms, s
    """
    units = {
        "ns": 1e-9,
        "us": 1e-6,
        "μs": 1e-6,
        "ms": 1e-3,
        "s": 1.0,
        "h": 3600.0
    }
    from_factor = units.get(from_unit, 1.0)
    to_factor = units.get(to_unit, 1.0)
    return value * from_factor / to_factor


def parse_symmetric_limit(limit_str: str):
    """
    解析对称容差，例如:
      "±0.1", "+/-0.1", "0.1"
    特殊格式理解：
      "±(a~b)" - 表示对称容差范围，[a, b] 可以是任意顺序，代表允许误差的范围
    返回: limit(>=0) 或 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip()
    s = s.replace("鈮?", "<=").replace("鈮?", ">=")
    s = s.replace("锛?", "+").replace("锕?", "+")
    s = s.replace("鈥?", "-").replace("鈭?", "-")
    s = s.replace("锝?", "~")

    has_symmetric_marker = any(mark in s for mark in ["卤", "±", "+/-", "＋/－"])
    if not has_symmetric_marker:
        return None

    # ±(a~b) / +/- (a~b) 表示对称容差范围，接受任意顺序
    if has_symmetric_marker:
        range_part = s
        for mark in ["卤", "±", "+/-", "＋/－"]:
            range_part = range_part.replace(mark, "")
        range_part = range_part.strip().strip("()")
        parsed = parse_range_limit(range_part)
        if parsed is not None:
            lower, upper = parsed

            # 对于对称范围，我们需要接受任意顺序的范围表示
            # 这反映了CNAS文件中的特殊表示法
            abs_lower = abs(lower)
            abs_upper = abs(upper)

            # 确保范围逻辑正确：[min, max]
            if abs_lower > abs_upper:
                abs_lower, abs_upper = abs_upper, abs_lower
                # 不再警告，因为源数据明确说明范围就是这样写的

            return ("range", abs_lower, abs_upper)

    val, _ = parse_value_with_unit(s.replace("卤", "").replace("±", ""), keep_sign=True)
    if val is None:
        return None
    return ("limit", abs(val))


