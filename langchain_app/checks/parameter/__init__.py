#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数与不确定度核验子包

包含完整的参数解析、验证和报告生成功能。
主入口函数使用惰性导入，避免在只使用底层工具时强制加载 LLM 依赖。
"""
from .parser_core import (
    parse_value_with_unit,
    parse_range_limit,
    parse_symmetric_limit,
    parse_single_sided_limit,
    extract_basis_code,
    norm_code,
    to_plain_decimal,
    SUPERSCRIPT_MAP,
    CANONICAL_UNIT_MAP,
    EXACT_UNIT_MULTIPLIERS,
    UNIT_MULTIPLIERS,
    ATOMIC_LENGTH_UNITS,
    VALUE_TOKEN_PATTERN,
    PREFERRED_RANGE_VALUE_PATTERNS,
    RANGE_TOOL_VALUE_PATTERNS,
    RANGE_TOOL_VALUE_PATTERNS_SAFE,
)
from .parser_domain import (
    _is_power_unit,
    _is_voltage_unit,
    _parse_frequency_to_hz,
    _parse_frequency_range,
    _parse_frequency_point_list,
    _extract_frequency_from_measurement,
    _filter_kb_entries_by_frequency,
    _parse_value_to_base_unit,
    _parse_range_to_base_units,
    _extract_value_from_measurement,
    _filter_kb_entries_by_range,
    _filter_kb_entries_by_voltage,
    _filter_kb_entries_by_current,
    _filter_kb_entries_by_power,
    _filter_kb_entries_multidimensional,
)
from .parser_core import (
    _unit_multiplier_from_text,
    _normalize_unit_text,
    extract_value_token,
    _extract_value_token,
    _parse_extracted_token,
    _extract_preferred_measure_token,
    parse_unicode_sci_number,
    _normalize_formula_unit,
    convert_time_unit,
)
from .semantic import (
    infer_param_semantics,
    select_basis_with_audit,
    semantic_filter_basis_entries,
)
from .validator import (
    verify_range_logic,
    verify_error_logic,
    verify_uncertainty_logic,
)
from .selector import (
    NormalizedKbCandidate,
    NormalizedCertPoint,
    normalize_cert_point,
    normalize_kb_candidate,
    select_kb_candidates,
)
from .reporter import (
    build_param_table,
    build_batch_summary_table,
    enforce_kb_missing_fail,
    enforce_uncertainty_by_tool,
)


__all__ = [
    # 主函数
    "check_parameters",
    "parameter_check_wrapper",
    "run_llm_mode",

    # 解析器
    "parse_value_with_unit",
    "parse_range_limit",
    "parse_symmetric_limit",
    "parse_single_sided_limit",
    "extract_basis_code",
    "norm_code",
    "to_plain_decimal",

    # 语义分析
    "infer_param_semantics",
    "select_basis_with_audit",
    "semantic_filter_basis_entries",

    # 验证器
    "verify_range_logic",
    "verify_error_logic",
    "verify_uncertainty_logic",

    # 确定性选择器
    "NormalizedKbCandidate",
    "NormalizedCertPoint",
    "normalize_cert_point",
    "normalize_kb_candidate",
    "select_kb_candidates",

    # 报告生成
    "build_param_table",
    "build_batch_summary_table",
    "enforce_kb_missing_fail",
    "enforce_uncertainty_by_tool",

    # 检索
    "search_calibration_data",
    "filter_kb_entries",
    "parse_kb_entry",
]


def __getattr__(name):
    if name in {"check_parameters", "parameter_check_wrapper", "run_llm_mode"}:
        from .parameter import check_parameters, parameter_check_wrapper, run_llm_mode

        namespace = {
            "check_parameters": check_parameters,
            "parameter_check_wrapper": parameter_check_wrapper,
            "run_llm_mode": run_llm_mode,
        }
        return namespace[name]
    if name in {"search_calibration_data", "filter_kb_entries", "parse_kb_entry"}:
        from .retrieval import filter_kb_entries, parse_kb_entry, search_calibration_data

        namespace = {
            "search_calibration_data": search_calibration_data,
            "filter_kb_entries": filter_kb_entries,
            "parse_kb_entry": parse_kb_entry,
        }
        return namespace[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
