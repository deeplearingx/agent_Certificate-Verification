#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数值解析模块 - 从param_check.py提取重构
负责解析带单位的数值、科学计数法等
"""

import re
import math
from typing import Any, Dict, List, Optional, Tuple

# 上标数字映射
SUPERSCRIPT_MAP = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    '⁻': '-', '⁺': '+',
}

# 单位前缀倍数
UNIT_MULTIPLIERS = {
    'T': 1e12, 'G': 1e9, 'M': 1e6, 'k': 1e3, 'K': 1e3,
    'm': 1e-3, 'u': 1e-6, 'μ': 1e-6, 'n': 1e-9, 'p': 1e-12
}

# 规范单位映射
CANONICAL_UNIT_MAP = {
    "thz": "THz", "ghz": "GHz", "mhz": "MHz", "khz": "kHz", "hz": "Hz",
    "kv": "kV", "mv": "mV", "uv": "uV", "v": "V",
    "ma": "mA", "ua": "uA", "a": "A",
    "ms": "ms", "us": "us", "ns": "ns", "ps": "ps", "s": "s",
    "pm": "pm", "nm": "nm", "um": "um", "mm": "mm", "cm": "cm", "m": "m",
    "m2": "m2", "m3": "m3",
    "m/s": "m/s", "m/s2": "m/s2", "m/s3": "m/s3",
    "db": "dB", "dbc": "dBc", "dbc/hz": "dBc/Hz",
    "dbm": "dBm", "dbmv": "dBmV",
    "deg": "deg", "°": "°",
}


class NumberParser:
    """数值解析器 - 负责解析各种格式的数值"""

    @staticmethod
    def parse_unicode_sci_number(s: str) -> Optional[float]:
        """解析Unicode上标科学计数法 (如 6.6×10⁻⁹)"""
        if not s or not isinstance(s, str):
            return None

        s = s.strip().replace('×', 'x').replace('X', 'x')

        # 转换上标数字
        for uni, normal in SUPERSCRIPT_MAP.items():
            s = s.replace(uni, normal)

        # 匹配格式: 6.6x10-9 或 6.6e-9
        match = re.match(r'^(-?\d+\.?\d*)\s*[xe]\s*10\^?\s*(-?\d+)$', s, re.IGNORECASE)
        if match:
            mantissa = float(match.group(1))
            exponent = int(match.group(2))
            return mantissa * (10 ** exponent)

        # 尝试普通浮点数解析
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def normalize_unit_text(unit: str) -> str:
        """规范化单位文本"""
        if not unit:
            return ""
        unit = unit.strip().lower()
        return CANONICAL_UNIT_MAP.get(unit, unit)

    @staticmethod
    def get_unit_multiplier(unit: str) -> float:
        """获取单位前缀的倍数"""
        if not unit:
            return 1.0

        # 检查特殊单位
        if unit in EXACT_UNIT_MULTIPLIERS:
            return EXACT_UNIT_MULTIPLIERS[unit]

        # 提取前缀
        for prefix, multiplier in UNIT_MULTIPLIERS.items():
            if unit.startswith(prefix):
                return multiplier

        return 1.0

    @staticmethod
    def extract_value_token(text: str) -> Optional[str]:
        """从文本中提取数值标记"""
        if not text:
            return None

        # 常见模式匹配
        patterns = [
            r'([-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)\s*([a-zA-Z/°²³\u00B2\u00B3]+)',
            r'([-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, str(text))
            if match:
                return match.group(0)

        return None

    @staticmethod
    def parse_value_with_unit(val_str, base_val=None, keep_sign: bool = False):
        """
        解析带单位的数值

        Returns:
            (value, unit, original_str) or (None, None, None) if parsing fails
        """
        if val_str is None:
            return None, None, None

        val_str = str(val_str).strip()
        if not val_str or val_str.lower() in ('nan', 'none', 'null', ''):
            return None, None, None

        # 尝试解析Unicode科学计数法
        unicode_val = NumberParser.parse_unicode_sci_number(val_str)
        if unicode_val is not None:
            return unicode_val, "", val_str

        # 提取数值和单位
        # 匹配模式: 数字 + 可选单位
        match = re.match(r'^([-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)\s*([a-zA-Z/°²³\u00B2\u00B3]*)$', val_str)
        if match:
            try:
                value = float(match.group(1))
                unit = match.group(2) if match.group(2) else ""

                if not keep_sign and value < 0 and base_val is not None:
                    # 处理相对值的情况
                    value = abs(value)

                return value, unit, val_str
            except ValueError:
                pass

        # 尝试纯数值解析
        try:
            value = float(val_str)
            return value, "", val_str
        except ValueError:
            pass

        return None, None, None

    @staticmethod
    def to_plain_decimal(x: Optional[float], max_digits: int = 12) -> str:
        """将浮点数转换为纯十进制字符串，避免科学计数法"""
        if x is None:
            return ""

        # 格式化并去除末尾的0
        formatted = f"{x:.{max_digits}f}"
        formatted = formatted.rstrip('0').rstrip('.')

        return formatted if formatted else "0"

    @staticmethod
    def is_missing(value) -> bool:
        """检查值是否缺失或无效"""
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().lower() in ('', 'nan', 'none', 'null', 'missing')
        return False

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


# 额外的精确单位倍数表
EXACT_UNIT_MULTIPLIERS = {
    "THz": 1e12, "GHz": 1e9, "MHz": 1e6, "kHz": 1e3, "Hz": 1.0,
    "kV": 1e3, "V": 1.0, "mV": 1e-3, "uV": 1e-6,
    "A": 1.0, "mA": 1e-3, "uA": 1e-6,
    "s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12,
    "m": 1.0, "cm": 1e-2, "mm": 1e-3, "um": 1e-6, "nm": 1e-9, "pm": 1e-12,
    "m2": 1.0, "m3": 1.0,
    "m/s": 1.0, "m/s2": 1.0, "m/s3": 1.0,
    "dB": 1.0, "dBc": 1.0, "dBc/Hz": 1.0, "dBm": 1.0, "dBmV": 1.0,
    "deg": 1.0, "°": 1.0,
}
