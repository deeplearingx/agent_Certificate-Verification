#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单位转换模块 - 从param_check.py提取重构
负责工程单位转换和单位规范化
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from core.number_parser import NumberParser, CANONICAL_UNIT_MAP, UNIT_MULTIPLIERS


class UnitConverter:
    """单位转换器 - 负责工程单位转换和规范化"""

    @staticmethod
    def is_power_unit(unit: str) -> bool:
        """判断是否是功率单位 (dBm, dBmV)"""
        if not unit:
            return False
        unit = unit.strip().lower()
        return unit in ["dbm", "dbmv", "dbc"]

    @staticmethod
    def is_voltage_unit(unit: str) -> bool:
        """判断是否是电压单位 (V, mV, uV)"""
        if not unit:
            return False
        unit = unit.strip().lower()
        return unit in ["v", "mv", "uv", "μv"] or (len(unit) > 1 and unit[-1] == "v" and unit[0] in ["k", "m", "u", "μ"])

    @staticmethod
    def normalize_unit(unit: str) -> str:
        """规范化单位"""
        if not unit:
            return ""
        unit = unit.strip().lower()
        return CANONICAL_UNIT_MAP.get(unit, unit)

    @staticmethod
    def get_multiplier(unit: str) -> float:
        """获取单位前缀的倍数"""
        if not unit:
            return 1.0

        # 精确匹配
        if unit in EXACT_UNIT_MULTIPLIERS:
            return EXACT_UNIT_MULTIPLIERS[unit]

        # 前缀匹配
        for prefix, multiplier in UNIT_MULTIPLIERS.items():
            if unit.startswith(prefix):
                return multiplier

        return 1.0

    @staticmethod
    def convert_value(value: float, from_unit: str, to_unit: str) -> Optional[float]:
        """
        转换数值单位

        Returns:
            转换后的值，失败返回 None
        """
        try:
            if from_unit == to_unit:
                return value

            from_multiplier = UnitConverter.get_multiplier(from_unit)
            to_multiplier = UnitConverter.get_multiplier(to_unit)

            return value * from_multiplier / to_multiplier

        except Exception as e:
            return None

    @staticmethod
    def unit_convert_tool(val_str: str, impedance: float = 50.0) -> dict:
        """
        单位转换工具 - 处理复杂单位转换

        Args:
            val_str: 待转换的数值字符串
            impedance: 阻抗值（用于功率电压转换）

        Returns:
            转换结果字典
        """
        try:
            value, unit, original = NumberParser.parse_value_with_unit(val_str)
            if value is None:
                return {"status": "error", "message": "无法解析数值"}

            # 规范化单位
            unit = UnitConverter.normalize_unit(unit)

            result = {
                "input": original,
                "value": value,
                "unit": unit,
                "impedance": impedance
            }

            # 支持的转换类型
            conversions = []

            # dBm ↔ mV 转换 (50欧姆系统)
            if unit == "dBm":
                # dBm 转 mV
                mV = 10 ** (value / 20) * 1000 * (impedance ** 0.5)
                conversions.append({"value": round(mV, 3), "unit": "mV"})

            elif unit == "mV":
                # mV 转 dBm
                dBm = 20 * (value / 1000 / (impedance ** 0.5)).log10()
                conversions.append({"value": round(dBm, 3), "unit": "dBm"})

            # 频率单位转换
            elif unit in ["Hz", "kHz", "MHz", "GHz", "THz"]:
                base_value = NumberParser.parse_value_with_unit(val_str)[0]
                freq_units = ["Hz", "kHz", "MHz", "GHz", "THz"]
                for target_unit in freq_units:
                    if target_unit != unit:
                        converted = UnitConverter.convert_value(base_value, unit, target_unit)
                        if converted is not None:
                            conversions.append({
                                "value": round(converted, 3),
                                "unit": target_unit
                            })

            # 电压单位转换
            elif UnitConverter.is_voltage_unit(unit):
                voltage_units = ["V", "mV", "uV"]
                for target_unit in voltage_units:
                    if target_unit != unit:
                        converted = UnitConverter.convert_value(value, unit, target_unit)
                        if converted is not None:
                            conversions.append({
                                "value": round(converted, 3),
                                "unit": target_unit
                            })

            result["conversions"] = conversions

            return result

        except Exception as e:
            return {"status": "error", "message": f"转换失败: {str(e)}"}


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
