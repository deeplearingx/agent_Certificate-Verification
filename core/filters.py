#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库过滤模块 - 从param_check.py提取重构
负责频率、电压、电流、功率等多维过滤
"""

import re
from typing import Any, Dict, List, Optional, Tuple


class KBFilters:
    """知识库过滤器 - 负责各种过滤操作"""

    # ===================== 频率相关 =====================
    @staticmethod
    def parse_frequency_to_hz(freq_str: str) -> Optional[float]:
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

    @staticmethod
    def parse_frequency_range(range_str: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
        """
        解析频率范围字符串，返回 (lower_hz, upper_hz)
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
                lower_hz = lower_hz * (1 + 1e-12)
            elif lower_op == '<':
                lower_hz = None
            if upper_op == '<':
                upper_hz = upper_hz * (1 - 1e-12)
            elif upper_op == '>':
                upper_hz = None

            return (lower_hz, upper_hz)
        except (ValueError, KeyError):
            return None

    @staticmethod
    def extract_frequency_from_measurement(measurement: Dict[str, Any]) -> Optional[float]:
        """从测量值中提取频率"""
        if not measurement or not isinstance(measurement, dict):
            return None

        # 尝试从各个字段中提取频率
        measure_val = measurement.get('measure_val', '')
        point_text = measurement.get('point_text', '')

        for text in [measure_val, point_text]:
            if text:
                freq_hz = KBFilters.parse_frequency_to_hz(str(text))
                if freq_hz is not None:
                    return freq_hz

        return None

    @staticmethod
    def filter_kb_entries_by_frequency(
        kb_entries: List[Dict[str, Any]],
        batch_params: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        根据频率过滤知识库条目
        """
        if not kb_entries or not batch_params:
            return kb_entries

        # 从批次参数中提取频率
        target_freqs = []
        for param in batch_params:
            freq = KBFilters.extract_frequency_from_measurement(param)
            if freq is not None:
                target_freqs.append(freq)

        if not target_freqs:
            return kb_entries

        # 过滤知识库条目
        filtered = []
        for entry in kb_entries:
            # 尝试从知识库条目中提取频率范围
            measure_range = entry.get('measure_range_text', '')
            freq_range = KBFilters.parse_frequency_range(measure_range)

            if freq_range is None:
                # 无法解析频率范围，保留条目
                filtered.append(entry)
                continue

            lower_hz, upper_hz = freq_range
            matches = False

            for target_freq in target_freqs:
                # 检查目标频率是否在范围内
                if lower_hz is not None and upper_hz is not None:
                    if lower_hz <= target_freq <= upper_hz:
                        matches = True
                        break
                elif lower_hz is not None:
                    if target_freq >= lower_hz:
                        matches = True
                        break
                elif upper_hz is not None:
                    if target_freq <= upper_hz:
                        matches = True
                        break

            if matches:
                filtered.append(entry)

        # 如果过滤后为空，返回原始条目
        return filtered if filtered else kb_entries

    # ===================== 电压、电流、功率过滤 =====================
    @staticmethod
    def _parse_value_to_base_units(value_str: str, unit_type: str) -> Optional[float]:
        """
        将值字符串解析为基本单位
        """
        if not value_str or not unit_type:
            return None

        try:
            from core.number_parser import NumberParser
            return NumberParser.parse_value_with_unit(value_str)[0]
        except:
            return None

    @staticmethod
    def _parse_range_to_base_units(range_str: str, unit_type: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
        """
        将范围字符串解析为基本单位
        """
        if not range_str or not unit_type:
            return None

        try:
            from core.risk_verifier import RangeVerifier
            range_val = RangeVerifier.parse_range_limit(range_str)
            if range_val:
                return (range_val[0], range_val[1])
        except:
            pass

        return None

    @staticmethod
    def _extract_value_from_measurement(
        measurement: Dict[str, Any],
        unit_type: str
    ) -> Optional[float]:
        """
        从测量值中提取指定单位类型的数值
        """
        if not measurement or not unit_type or not isinstance(measurement, dict):
            return None

        measure_val = measurement.get('measure_val', '')
        point_text = measurement.get('point_text', '')

        for text in [measure_val, point_text]:
            if text:
                try:
                    value = KBFilters._parse_value_to_base_units(str(text), unit_type)
                    if value is not None:
                        return value
                except:
                    continue

        return None

    @staticmethod
    def filter_kb_entries_by_range(
        kb_entries: List[Dict[str, Any]],
        batch_params: List[Dict[str, Any]],
        unit_type: str = 'frequency'
    ) -> List[Dict[str, Any]]:
        """
        通用的KB条目范围匹配过滤层（可扩展）
        """
        if not kb_entries or not batch_params:
            return kb_entries

        # 收集所有测量点的数值
        measurements = []
        for param in batch_params:
            value = KBFilters._extract_value_from_measurement(param, unit_type)
            if value is not None:
                measurements.append(value)

        if not measurements:
            return kb_entries

        filtered_entries = []
        for entry in kb_entries:
            measure_range = entry.get('measure_range_text', '')
            range_vals = KBFilters._parse_range_to_base_units(measure_range, unit_type)

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

    @staticmethod
    def filter_kb_entries_by_voltage(
        kb_entries: List[Dict[str, Any]],
        batch_params: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        电压范围匹配过滤（专门版本，调用通用函数）
        """
        return KBFilters.filter_kb_entries_by_range(kb_entries, batch_params, 'voltage')

    @staticmethod
    def filter_kb_entries_by_current(
        kb_entries: List[Dict[str, Any]],
        batch_params: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        电流范围匹配过滤（专门版本，调用通用函数）
        """
        return KBFilters.filter_kb_entries_by_range(kb_entries, batch_params, 'current')

    @staticmethod
    def filter_kb_entries_by_power(
        kb_entries: List[Dict[str, Any]],
        batch_params: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        功率范围匹配过滤（专门版本，调用通用函数）
        """
        return KBFilters.filter_kb_entries_by_range(kb_entries, batch_params, 'power')

    @staticmethod
    def filter_kb_entries_multidimensional(
        kb_entries: List[Dict[str, Any]],
        batch_params: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        多维范围匹配过滤（同时考虑多个参数类型）
        """
        if not kb_entries or not batch_params:
            return kb_entries

        filtered_entries = kb_entries
        for unit_type in ['frequency', 'voltage', 'current', 'power']:
            filtered = KBFilters.filter_kb_entries_by_range(filtered_entries, batch_params, unit_type)
            if filtered:
                filtered_entries = filtered
            if not filtered_entries:
                break

        return filtered_entries


# ===================== 语义预过滤 =====================
def extract_param_name_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    """提取参数名称用于语义预过滤"""
    if not param or not isinstance(param, dict):
        return ""

    # 尝试从各个字段提取
    param_name = param.get('param_name', '')
    measure_val = param.get('measure_val', '')

    if param_name:
        return str(param_name)
    return str(measure_val)


def extract_cert_u_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    """提取证书不确定度用于语义预过滤"""
    if not param or not isinstance(param, dict):
        return ""
    return str(param.get('cert_u', ''))


def extract_point_text_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    """提取点文本用于语义预过滤"""
    if not param or not isinstance(param, dict):
        return ""
    return str(param.get('point_text', ''))


def apply_semantic_basis_prefilter(
    kb_items: List[Dict[str, Any]],
    batch_params: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """应用语义依据预过滤"""
    return kb_items, []
