#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameter parsing domain layer.

This module owns frequency / period parsing, KB range filtering, and semantic
prefilter helpers that sit above the token-level core parser.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .parser_core import parse_range_limit, parse_value_with_unit
from .rules import KB_MEASURED_RULES, PARAMETER_NAME_RULES

def _is_power_unit(unit: str) -> bool:
    """判断是否是功率单位（dBm, dBmV等）"""
    if not unit:
        return False
    u_lower = unit.lower()
    return any(pu in u_lower for pu in ["dbm", "dbmv", "dbμv", "dbuv", "db"])


def _is_voltage_unit(unit: str) -> bool:
    """判断是否是电压单位（V, mV, μV等）"""
    if not unit:
        return False
    u_lower = unit.lower()
    # 排除 dBmV 这类带dB的电压单位
    if "db" in u_lower:
        return False
    return any(vu in u_lower for vu in ["v", "mv", "μv", "uv"])


def _parse_frequency_to_hz(freq_str: str) -> Optional[float]:
    """
    将频率字符串解析为赫兹数值
    支持格式：100 Hz, 1.5 MHz, 10 kHz, 0.93 GHz
    """
    if not freq_str or not isinstance(freq_str, str):
        return None

    # 匹配数字 + 单位的模式
    match = re.search(r'([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)', freq_str, re.IGNORECASE)
    if not match:
        return None

    try:
        num = float(match.group(1))
        unit = match.group(2).lower()

        multipliers = {
            'hz': 1.0,
            'khz': 1000.0,
            'mhz': 1_000_000.0,
            'ghz': 1_000_000_000.0,
            'thz': 1_000_000_000_000.0,
        }

        return num * multipliers[unit]
    except (ValueError, KeyError):
        return None


def _parse_frequency_range(range_str: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """
    解析频率范围字符串，返回 (lower_hz, upper_hz)
    支持格式：
    - "0.1 Hz～100 kHz"
    - ">100 kHz～20 MHz"
    - "(0.1 Hz～100 kHz)"
    """
    if not range_str or not isinstance(range_str, str):
        return None

    # 去除括号
    clean_str = range_str.replace('(', '').replace(')', '').strip()

    # 匹配范围模式
    pattern = r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)'
    match = re.search(pattern, clean_str, re.IGNORECASE)

    if not match:
        # 尝试匹配只有一个边界的情况
        single_pattern = r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)'
        single_match = re.search(single_pattern, clean_str, re.IGNORECASE)
        if single_match:
            lower_op = single_match.group(1)
            num = float(single_match.group(2))
            unit = single_match.group(3).lower()

            multipliers = {
                'hz': 1.0,
                'khz': 1000.0,
                'mhz': 1_000_000.0,
                'ghz': 1_000_000_000.0,
                'thz': 1_000_000_000_000.0,
            }

            value = num * multipliers[unit]

            if lower_op == '>':
                return (value, None)
            elif lower_op == '<':
                return (None, value)
            else:
                return (value, value)
        return None

    try:
        lower_op = match.group(1)
        lower_num = float(match.group(2))
        lower_unit = match.group(3).lower()
        upper_op = match.group(4)
        upper_num = float(match.group(5))
        upper_unit = match.group(6).lower()

        multipliers = {
            'hz': 1.0,
            'khz': 1000.0,
            'mhz': 1_000_000.0,
            'ghz': 1_000_000_000.0,
            'thz': 1_000_000_000_000.0,
        }

        lower_hz = lower_num * multipliers[lower_unit]
        upper_hz = upper_num * multipliers[upper_unit]

        # 处理边界符号
        if lower_op == '>':
            lower_hz = lower_hz * (1 + 1e-12)  # 稍微大一点，避免浮点误差
        elif lower_op == '<':
            lower_hz = None
        elif lower_op == '>=':
            lower_hz = lower_hz * (1 - 1e-12)  # 稍微小一点

        if upper_op == '<':
            upper_hz = upper_hz * (1 - 1e-12)
        elif upper_op == '>':
            upper_hz = None
        elif upper_op == '<=':
            upper_hz = upper_hz * (1 + 1e-12)

        return (lower_hz, upper_hz)
    except (ValueError, KeyError):
        return None


def _parse_frequency_point_list(range_str: str) -> List[float]:
    if not range_str or not isinstance(range_str, str):
        return []
    if "~" in range_str or "～" in range_str:
        return []

    values: List[float] = []
    for part in re.split(r"[，,；;、]\s*", range_str):
        freq_hz = _parse_frequency_to_hz(part.strip())
        if freq_hz is not None:
            values.append(freq_hz)
    return values


def _extract_frequency_from_measurement(measurement: Dict[str, Any]) -> Optional[float]:
    """
    从测量点数据中提取频率值（Hz）
    查找包含频率字段的数据
    """
    if not measurement or not isinstance(measurement, dict):
        return None

    # 查找所有可能包含频率的字段
    for key, value in measurement.items():
        if not key or not value:
            continue
        key_lower = str(key).lower()
        value_str = str(value)

        # 检查字段名是否包含频率相关
        if any(keyword in key_lower for keyword in ['频率', 'frequency', 'freq']):
            freq_hz = _parse_frequency_to_hz(value_str)
            if freq_hz is not None:
                return freq_hz

        # 检查值是否包含频率格式
        freq_hz = _parse_frequency_to_hz(value_str)
        if freq_hz is not None:
            return freq_hz

    return None


def _filter_kb_entries_by_frequency(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    程序化的KB条目范围匹配过滤层

    原理：
    1. 从测量点中提取频率
    2. 从KB条目中解析频率范围
    3. 只保留频率匹配的KB条目

    参数:
        kb_entries: 原始的KB条目列表
        batch_params: 待核验的测量参数批次

    返回:
        过滤后的KB条目列表
    """
    if not kb_entries or not batch_params:
        return kb_entries

    # 首先收集所有测量点的频率
    measurement_frequencies = []
    for param in batch_params:
        freq_hz = _extract_frequency_from_measurement(param)
        if freq_hz is not None:
            measurement_frequencies.append(freq_hz)

    if not measurement_frequencies:
        # 没有找到频率数据，不进行过滤
        return kb_entries

    # 找到最小和最大的频率，用于覆盖所有测量点
    min_freq = min(measurement_frequencies)
    max_freq = max(measurement_frequencies)

    filtered_entries = []

    for entry in kb_entries:
        measure_range = entry.get('measure_range_text', '')

        # 尝试解析KB条目的频率范围
        freq_range = _parse_frequency_range(measure_range)
        freq_points = _parse_frequency_point_list(measure_range)

        if freq_points:
            match = False
            for freq_hz in measurement_frequencies:
                for point_hz in freq_points:
                    if abs(freq_hz - point_hz) <= max(point_hz * 1e-9, 1e-6):
                        match = True
                        break
                if match:
                    break
            if match:
                filtered_entries.append(entry)
            continue

        if freq_range is None:
            # 无法解析频率范围，保留这个条目（作为兜底）
            filtered_entries.append(entry)
            continue

        lower_hz, upper_hz = freq_range

        # 检查是否有任何测量频率在此范围内
        match = False
        for freq_hz in measurement_frequencies:
            if lower_hz is not None and freq_hz < lower_hz:
                continue
            if upper_hz is not None and freq_hz > upper_hz:
                continue
            match = True
            break

        if match:
            filtered_entries.append(entry)

    # 如果过滤后没有条目了，返回原始条目（兜底）
    if not filtered_entries:
        return kb_entries

    return filtered_entries


# ==============================
# 通用范围匹配过滤（可扩展架构
# ==============================


def _parse_value_to_base_unit(value_str: str, unit_type: str) -> Optional[float]:
    """
    将数值字符串解析为基础单位的数值
    支持多种类型的参数：频率、电压、电流、功率等

    参数:
        value_str: 要解析的字符串
        unit_type: 参数类型，如 'frequency', 'voltage', 'current', 'power'

    返回:
        解析后的数值，None表示无法解析
    """
    if not value_str or not isinstance(value_str, str) or not unit_type:
        return None

    def _get_multiplier(unit: str, multipliers: dict) -> Optional[float]:
        """获取单位对应的倍数，处理大小写敏感的情况"""
        # 首先尝试精确匹配（大小写敏感）
        if unit in multipliers:
            return multipliers[unit]

        # 对于功率单位，需要特殊处理 MW（兆瓦）和 mW（毫瓦）
        if unit == 'MW':
            return 1_000_000.0
        if unit == 'mW':
            return 0.001

        # 其他单位尝试小写匹配
        unit_lower = unit.lower()
        if unit_lower in multipliers:
            return multipliers[unit_lower]

        return None

    unit_configs = {
        'frequency': {
            'pattern': r'([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)',
            'multipliers': {
                'Hz': 1.0,
                'kHz': 1000.0,
                'MHz': 1_000_000.0,
                'GHz': 1_000_000_000.0,
                'THz': 1_000_000_000_000.0,
                'hz': 1.0,
                'khz': 1000.0,
                'mhz': 1_000_000.0,
                'ghz': 1_000_000_000.0,
                'thz': 1_000_000_000_000.0,
            },
        },
        'voltage': {
            'pattern': r'([\d.]+)\s*(V|mV|μV|kV)',
            'multipliers': {
                'V': 1.0,
                'mV': 0.001,
                'μV': 0.000001,
                'kV': 1000.0,
                'v': 1.0,
                'mv': 0.001,
                'uv': 0.000001,
                'μv': 0.000001,
                'kv': 1000.0,
            },
        },
        'current': {
            'pattern': r'([\d.]+)\s*(A|mA|μA|kA)',
            'multipliers': {
                'A': 1.0,
                'mA': 0.001,
                'μA': 0.000001,
                'kA': 1000.0,
                'a': 1.0,
                'ma': 0.001,
                'ua': 0.000001,
                'μa': 0.000001,
                'ka': 1000.0,
            },
        },
        'power': {
            'pattern': r'([\d.]+)\s*(W|mW|μW|kW|MW|GW)',
            'multipliers': {
                'W': 1.0,
                'mW': 0.001,  # 毫瓦
                'μW': 0.000001,
                'kW': 1000.0,
                'MW': 1_000_000.0,  # 兆瓦（大小写敏感）
                'GW': 1_000_000_000.0,
                'w': 1.0,
                'uw': 0.000001,
                'μw': 0.000001,
                'kw': 1000.0,
                'gw': 1_000_000_000.0,
            },
        },
        'time': {
            'pattern': r'([\d.]+)\s*(ns|μs|us|ms|s|min|h|d|天|小时|分钟)',
            'multipliers': {
                'ps': 1e-12,      # 皮秒
                'ns': 1e-9,       # 纳秒
                'μs': 1e-6,       # 微秒
                'us': 1e-6,       # 微秒
                'ms': 1e-3,       # 毫秒
                's': 1.0,         # 秒
                'min': 60.0,      # 分钟
                'h': 3600.0,      # 小时
                'd': 86400.0,     # 天
                '天': 86400.0,
                '小时': 3600.0,
                '分钟': 60.0,
            },
        },
    }

    if unit_type not in unit_configs:
        return None

    config = unit_configs[unit_type]
    # 不使用 IGNORECASE，保持大小写敏感
    match = re.search(config['pattern'], value_str)
    if not match:
        # 尝试大小写不敏感匹配作为兜底
        match = re.search(config['pattern'], value_str, re.IGNORECASE)
        if not match:
            return None

    try:
        num = float(match.group(1))
        unit = match.group(2)
        multiplier = _get_multiplier(unit, config['multipliers'])
        if multiplier is None:
            return None
        return num * multiplier
    except (ValueError, KeyError):
        return None


def _parse_range_to_base_units(range_str: str, unit_type: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """
    解析范围字符串，返回基础单位的 (lower, upper) 范围
    """
    if not range_str or not isinstance(range_str, str):
        return None

    # 去除括号
    clean_str = range_str.replace('(', '').replace(')', '').strip()

    unit_configs = {
        'frequency': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)',
            'multipliers': {
                'hz': 1.0,
                'khz': 1000.0,
                'mhz': 1_000_000.0,
                'ghz': 1_000_000_000.0,
                'thz': 1_000_000_000_000.0,
            },
        },
        'voltage': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(V|mV|μV|kV)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(V|mV|μV|kV)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(V|mV|μV|kV)',
            'multipliers': {
                'v': 1.0,
                'mv': 0.001,
                'uv': 0.000001,
                'μv': 0.000001,
                'kv': 1000.0,
            },
        },
        'current': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(A|mA|μA|kA)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(A|mA|μA|kA)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(A|mA|μA|kA)',
            'multipliers': {
                'a': 1.0,
                'ma': 0.001,
                'ua': 0.000001,
                'μa': 0.000001,
                'ka': 1000.0,
            },
        },
        'power': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(W|mW|μW|kW|MW|GW)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(W|mW|μW|kW|MW|GW)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(W|mW|μW|kW|MW|GW)',
            'multipliers': {
                'W': 1.0,
                'mW': 0.001,  # 毫瓦
                'μW': 0.000001,
                'kW': 1000.0,
                'MW': 1_000_000.0,  # 兆瓦（大小写敏感）
                'GW': 1_000_000_000.0,
                'w': 1.0,
                'uw': 0.000001,
                'μw': 0.000001,
                'kw': 1000.0,
                'gw': 1_000_000_000.0,
            },
        },
        'time': {
            'pattern': r'([<>]?)\s*([-+]?\d+(?:\.\d+)?)\s*(ps|ns|μs|us|ms|s/d|s/m|s|min|h|d|天|小时|分钟)\s*[~～]\s*([<>]?)\s*([-+]?\d+(?:\.\d+)?)\s*(ps|ns|μs|us|ms|s/d|s/m|s|min|h|d|天|小时|分钟)',
            'single_pattern': r'([<>]?)\s*([-+]?\d+(?:\.\d+)?)\s*(ps|ns|μs|us|ms|s/d|s/m|s|min|h|d|天|小时|分钟)',
            'multipliers': {
                'ps': 1e-12,      # 皮秒
                'ns': 1e-9,       # 纳秒
                'μs': 1e-6,       # 微秒
                'us': 1e-6,       # 微秒
                'ms': 1e-3,       # 毫秒
                's': 1.0,         # 秒
                's/d': 1.0 / 86400.0,
                's/m': 1.0 / (30.0 * 86400.0),
                'min': 60.0,      # 分钟
                'h': 3600.0,      # 小时
                'd': 86400.0,     # 天
                '天': 86400.0,
                '小时': 3600.0,
                '分钟': 60.0,
            },
        },
    }

    if unit_type not in unit_configs:
        return None

    config = unit_configs[unit_type]

    def _get_multiplier(unit: str, multipliers: dict) -> Optional[float]:
        """获取单位对应的倍数，处理大小写敏感的情况"""
        if unit in multipliers:
            return multipliers[unit]
        if unit == 'MW':
            return 1_000_000.0
        if unit == 'mW':
            return 0.001
        unit_lower = unit.lower()
        if unit_lower in multipliers:
            return multipliers[unit_lower]
        return None

    # 尝试匹配范围模式
    if unit_type == 'time':
        shared_suffix_pattern = (
            r'([<>]?)\s*([-+]?\d+(?:\.\d+)?)\s*[~～]\s*'
            r'([<>]?)\s*([-+]?\d+(?:\.\d+)?)\s*'
            r'(ps|ns|μs|us|ms|s/d|s/m|s|min|h|d|天|小时|分钟)\b'
        )
        match = re.search(shared_suffix_pattern, clean_str)
        if not match:
            match = re.search(shared_suffix_pattern, clean_str, re.IGNORECASE)
        if match:
            try:
                lower_num = float(match.group(2))
                upper_num = float(match.group(4))
                suffix_unit = match.group(5)
                multiplier = _get_multiplier(suffix_unit, config['multipliers'])
                if multiplier is None:
                    return None

                lower_val = lower_num * multiplier
                upper_val = upper_num * multiplier
                return (min(lower_val, upper_val), max(lower_val, upper_val))
            except (ValueError, KeyError):
                return None

    match = re.search(config['pattern'], clean_str)
    if not match:
        match = re.search(config['pattern'], clean_str, re.IGNORECASE)
    if match:
        try:
            lower_op = match.group(1)
            lower_num = float(match.group(2))
            lower_unit = match.group(3)
            upper_op = match.group(4)
            upper_num = float(match.group(5))
            upper_unit = match.group(6)

            lower_multiplier = _get_multiplier(lower_unit, config['multipliers'])
            upper_multiplier = _get_multiplier(upper_unit, config['multipliers'])

            if lower_multiplier is None or upper_multiplier is None:
                return None

            lower_val = lower_num * lower_multiplier
            upper_val = upper_num * upper_multiplier

            # 双边范围优先按真实端点排序。
            # 对于时间段这类表述，形如 "<10 μs～50 ns" 实际表示
            # 50 ns 到 10 μs 的闭区间，不应把左端符号误解释成“只剩右端上界”。
            if unit_type == 'time':
                return (min(lower_val, upper_val), max(lower_val, upper_val))

            # 其他类型保持原有开闭边界处理。
            if lower_op == '>':
                lower_val = lower_val * (1 + 1e-12)
            elif lower_op == '<':
                lower_val = None
            elif lower_op == '>=':
                lower_val = lower_val * (1 - 1e-12)

            if upper_op == '<':
                upper_val = upper_val * (1 - 1e-12)
            elif upper_op == '>':
                upper_val = None
            elif upper_op == '<=':
                upper_val = upper_val * (1 + 1e-12)

            return (lower_val, upper_val)
        except (ValueError, KeyError):
            return None

    # 尝试匹配单边界范围
    single_match = re.search(config['single_pattern'], clean_str)
    if not single_match:
        single_match = re.search(config['single_pattern'], clean_str, re.IGNORECASE)
    if single_match:
        try:
            op = single_match.group(1)
            num = float(single_match.group(2))
            unit = single_match.group(3)
            multiplier = _get_multiplier(unit, config['multipliers'])

            if multiplier is None:
                return None

            value = num * multiplier

            if op == '>':
                return (value * (1 + 1e-12), None)
            elif op == '<':
                return (None, value * (1 - 1e-12))
            elif op == '>=':
                return (value * (1 - 1e-12), None)
            elif op == '<=':
                return (None, value * (1 + 1e-12))
            else:
                return (value, value)
        except (ValueError, KeyError):
            return None

    return None


def _extract_value_from_measurement(measurement: Dict[str, Any], unit_type: str) -> Optional[float]:
    """
    从测量点数据中提取指定类型的数值（基础单位）
    """
    if not measurement or not isinstance(measurement, dict):
        return None

    keyword_configs = {
        'frequency': ['频率', 'frequency', 'freq'],
        'voltage': ['电压', 'voltage', 'volt', 'vpp'],
        'current': ['电流', 'current', 'amp'],
        'power': ['功率', 'power', 'watt'],
        'time': ['时间', 'time', '间隔', 'interval', '周期', 'period'],
    }

    if unit_type not in keyword_configs:
        return None

    keywords = keyword_configs[unit_type]

    for key, value in measurement.items():
        if not key or not value:
            continue
        key_lower = str(key).lower()
        value_str = str(value)

        if any(keyword in key_lower for keyword in keywords):
            parsed_val = _parse_value_to_base_unit(value_str, unit_type)
            if parsed_val is not None:
                return parsed_val

        parsed_val = _parse_value_to_base_unit(value_str, unit_type)
        if parsed_val is not None:
            return parsed_val

    return None


def _filter_kb_entries_by_range(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]],
                                unit_type: str = 'frequency') -> List[Dict[str, Any]]:
    """
    通用的KB条目范围匹配过滤层（可扩展）

    原理：
    1. 从测量点中提取指定类型的数值
    2. 从KB条目中解析范围
    3. 只保留与测量点范围匹配的KB条目

    参数:
        kb_entries: 原始的KB条目列表
        batch_params: 待核验的测量参数批次
        unit_type: 要匹配的单位类型，如 'frequency', 'voltage'

    返回:
        过滤后的KB条目列表
    """
    if not kb_entries or not batch_params:
        return kb_entries

    # 收集所有测量点的数值
    measurements = []
    for param in batch_params:
        value = _extract_value_from_measurement(param, unit_type)
        if value is not None:
            measurements.append(value)

    if not measurements:
        return kb_entries

    filtered_entries = []
    for entry in kb_entries:
        measure_range = entry.get('measure_range_text', '')
        range_vals = _parse_range_to_base_units(measure_range, unit_type)

        if range_vals is None:
            filtered_entries.append(entry)
            continue

        lower, upper = range_vals
        match = False

        for val in measurements:
            if lower is not None and val < lower:
                continue
            if upper is not None and val > upper:
                continue
            match = True
            break

        if match:
            filtered_entries.append(entry)

    return filtered_entries if filtered_entries else kb_entries


def _filter_kb_entries_by_voltage(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    电压范围匹配过滤（专门版本，调用通用函数）
    """
    return _filter_kb_entries_by_range(kb_entries, batch_params, 'voltage')


def _filter_kb_entries_by_current(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    电流范围匹配过滤（专门版本，调用通用函数）
    """
    return _filter_kb_entries_by_range(kb_entries, batch_params, 'current')


def _filter_kb_entries_by_power(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    功率范围匹配过滤（专门版本，调用通用函数）
    """
    return _filter_kb_entries_by_range(kb_entries, batch_params, 'power')


def _filter_kb_entries_multidimensional(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    多维范围匹配过滤（同时考虑多个参数类型）

    先对每个参数类型进行过滤，然后取交集。
    这样可以确保只保留同时满足多个参数范围的条目。
    """
    if not kb_entries or not batch_params:
        return kb_entries

    # 依次对多个参数类型进行过滤，取交集
    filtered_entries = kb_entries
    for unit_type in ['frequency', 'voltage', 'current', 'power']:
        filtered = _filter_kb_entries_by_range(filtered_entries, batch_params, unit_type)
        if filtered:
            filtered_entries = filtered
        # 停止条件：没有条目可过滤了
        if not filtered_entries:
            break

    return filtered_entries


def _extract_param_name_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    for key in ("param_name", "项目名称", "测量值", "name"):
        value = param.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _extract_cert_u_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    details = param.get("数据明细")
    if isinstance(details, dict):
        for key, value in details.items():
            key_text = str(key).lower()
            if "u" in key_text and value not in (None, ""):
                return str(value).strip()

    for key in ("证书U", "cert_u", "u"):
        value = param.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _extract_point_text_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    details = param.get("数据明细")
    if isinstance(details, dict) and details:
        parts = [f"{k}: {v}" for k, v in details.items() if v not in (None, "")]
        if parts:
            return ", ".join(parts)

    parts = []
    for key, value in param.items():
        if key == "数据明细" or value in (None, ""):
            continue
        parts.append(f"{key}: {value}")
    return ", ".join(parts)


def _apply_semantic_basis_prefilter(
    kb_items: List[Dict[str, Any]],
    batch_params: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    from .semantic import infer_param_semantics, select_basis_with_audit

    if not kb_items or not batch_params:
        return kb_items, []

    selected_sources: List[Dict[str, Any]] = []
    selected_ids = set()
    audit_lines: List[str] = []

    for param in batch_params:
        param_name = _extract_param_name_for_semantic_prefilter(param)
        point_text = _extract_point_text_for_semantic_prefilter(param)
        cert_u = _extract_cert_u_for_semantic_prefilter(param)

        semantic = infer_param_semantics(param_name, point_text, cert_u)
        if semantic.task_intent == "unknown":
            audit_lines.append(f"- {param_name}: semantic prefilter skipped (unknown task)")
            continue

        result = select_basis_with_audit(
            param_name=param_name,
            point_text=point_text,
            cert_u=cert_u,
            kb_entries=kb_items,
        )
        if result.audit.prefiltered_candidates:
            audit_lines.append(
                f"- {param_name}: {result.audit.task_goal} -> candidates={result.audit.prefiltered_candidates} -> "
                f"selected={result.audit.selected_candidate_id or result.audit.selected_measured}"
            )
        else:
            audit_lines.append(
                f"- {param_name}: {result.audit.task_goal} -> no semantic candidates, fallback to original KB set"
            )

        selected_items = [result.selected_candidate.source] if result.selected_candidate is not None else []
        for source in selected_items:
            source_id = id(source)
            if source_id in selected_ids:
                continue
            selected_ids.add(source_id)
            selected_sources.append(source)

    if not selected_ids:
        return kb_items, audit_lines

    filtered = [item for item in selected_sources if id(item) in selected_ids]
    return filtered if filtered else kb_items, audit_lines
