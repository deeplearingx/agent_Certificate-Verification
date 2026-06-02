#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNAS 参数核验核心模块 - 统一导出接口
"""

# 版本信息
__version__ = "2.0.0"
__author__ = "Refactored from param_check.py"

# 配置模块
from core.config import Config

# 核心功能模块
from core.number_parser import NumberParser, CANONICAL_UNIT_MAP, UNIT_MULTIPLIERS
from core.unit_converter import UnitConverter, EXACT_UNIT_MULTIPLIERS
from core.risk_verifier import RangeVerifier
from core.error_verifier import ErrorVerifier
from core.uncertainty_verifier import UncertaintyVerifier

# 高级功能模块
from core.table_processor import TableProcessor
from core.report_generator import ReportGenerator
from core.filters import (
    KBFilters,
    extract_param_name_for_semantic_prefilter,
    extract_cert_u_for_semantic_prefilter,
    extract_point_text_for_semantic_prefilter,
    apply_semantic_basis_prefilter
)

# 语义选择器
try:
    from core.semantic_basis_selector import FirstCandidateDecider, infer_param_semantics, select_basis_with_audit
except ImportError:
    pass

# 向后兼容 - 保持旧的函数名称
# 这确保现有代码无需修改就能运行

# 数值解析相关
_parse_unicode_sci_number = NumberParser.parse_unicode_sci_number
parse_value_with_unit = NumberParser.parse_value_with_unit
to_plain_decimal = NumberParser.to_plain_decimal
_extract_value_token = NumberParser.extract_value_token
_is_missing = NumberParser.is_missing

# 范围验证相关
parse_single_sided_limit = RangeVerifier.parse_single_sided_limit
parse_range_limit = RangeVerifier.parse_range_limit
parse_symmetric_limit = RangeVerifier.parse_symmetric_limit
convert_time_unit = RangeVerifier.convert_time_unit

# 单位转换相关
unit_convert_tool = UnitConverter.unit_convert_tool
_is_power_unit = UnitConverter.is_power_unit
_is_voltage_unit = UnitConverter.is_voltage_unit

# 误差验证相关
verify_error_logic = ErrorVerifier.verify_error_logic
_extract_primary_unit_token = ErrorVerifier.extract_primary_unit_token

# 不确定度验证相关
verify_uncertainty_logic = UncertaintyVerifier.verify_uncertainty_logic
calc_u_formula = UncertaintyVerifier.calc_u_formula
_measure_prefers_relative_u = UncertaintyVerifier.measure_prefers_relative_u
_detect_uncertainty_kind = UncertaintyVerifier.detect_uncertainty_kind

# 表格处理相关
_looks_like_table_header = TableProcessor.looks_like_table_header
_looks_like_summary_heading = TableProcessor.looks_like_summary_heading
_extract_param_name = TableProcessor.extract_param_name
_summarize_table_statuses = TableProcessor.summarize_table_statuses
_count_statuses_from_table_lines = TableProcessor.count_statuses_from_table_lines
_normalize_param_name_for_merge = TableProcessor.normalize_param_name_for_merge
_build_fallback_param_name = TableProcessor.build_fallback_param_name
_find_status_column_index = TableProcessor.find_status_column_index
_find_kb_code_column_index = TableProcessor.find_kb_code_column_index
_find_note_column_index = TableProcessor.find_note_column_index
_is_kb_missing_fail = TableProcessor.is_kb_missing_fail

# 报告生成相关
_build_param_table = ReportGenerator.build_param_table
enforce_kb_missing_fail = ReportGenerator.enforce_kb_missing_fail
enforce_uncertainty_by_tool = ReportGenerator.enforce_uncertainty_by_tool
enforce_batch_summary_from_table = ReportGenerator.enforce_batch_summary_from_table
_generate_json_report = ReportGenerator.generate_json_report
_collect_certificate_params = ReportGenerator.collect_certificate_params

# 范围验证主函数
verify_range_logic = RangeVerifier.verify_range_logic

# 导入配置相关
from core.config import LAST_QUERY_ERROR

# 模块导出列表
__all__ = [
    # 配置
    'Config',
    'LAST_QUERY_ERROR',

    # 核心模块
    'NumberParser',
    'UnitConverter',
    'RangeVerifier',
    'ErrorVerifier',
    'UncertaintyVerifier',
    'TableProcessor',
    'ReportGenerator',
    'KBFilters',

    # 常量
    'CANONICAL_UNIT_MAP',
    'UNIT_MULTIPLIERS',
    'EXACT_UNIT_MULTIPLIERS',

    # 过滤器相关
    'extract_param_name_for_semantic_prefilter',
    'extract_cert_u_for_semantic_prefilter',
    'extract_point_text_for_semantic_prefilter',
    'apply_semantic_basis_prefilter',

    # 向后兼容函数
    '_parse_unicode_sci_number',
    'parse_value_with_unit',
    'to_plain_decimal',
    '_extract_value_token',
    '_is_missing',
    'parse_single_sided_limit',
    'parse_range_limit',
    'parse_symmetric_limit',
    'convert_time_unit',
    'unit_convert_tool',
    '_is_power_unit',
    '_is_voltage_unit',
    'verify_error_logic',
    '_extract_primary_unit_token',
    'verify_uncertainty_logic',
    'calc_u_formula',
    '_measure_prefers_relative_u',
    '_detect_uncertainty_kind',
    '_looks_like_table_header',
    '_looks_like_summary_heading',
    '_extract_param_name',
    '_summarize_table_statuses',
    '_count_statuses_from_table_lines',
    '_normalize_param_name_for_merge',
    '_build_fallback_param_name',
    '_find_status_column_index',
    '_find_kb_code_column_index',
    '_find_note_column_index',
    '_is_kb_missing_fail',
    '_build_param_table',
    'enforce_kb_missing_fail',
    'enforce_uncertainty_by_tool',
    'enforce_batch_summary_from_table',
    '_generate_json_report',
    '_collect_certificate_params',
    'verify_range_logic',

    # 语义选择器
    'FirstCandidateDecider',
    'infer_param_semantics',
    'select_basis_with_audit',
]

# 原始 pipeline 导入
from .pipeline import PipelineHooks, run_verification

