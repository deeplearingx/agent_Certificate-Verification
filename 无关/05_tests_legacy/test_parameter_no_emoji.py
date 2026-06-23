#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试参数核验模块（无emoji）
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing parameter check module")
print("=" * 60)

print("\n1. Testing submodule imports...")
try:
    from langchain_app.checks.parameter import (
        # 解析器
        parse_value_with_unit,
        parse_range_limit,
        parse_symmetric_limit,
        parse_single_sided_limit,
        extract_basis_code,
        norm_code,
        to_plain_decimal,
        # 语义分析
        infer_param_semantics,
        select_basis_with_audit,
        semantic_filter_basis_entries,
        # 验证器
        verify_range_logic,
        verify_error_logic,
        verify_uncertainty_logic,
        # 报告生成
        build_param_table,
        build_batch_summary_table,
        enforce_kb_missing_fail,
        enforce_uncertainty_by_tool,
        # 检索
        search_calibration_data,
        filter_kb_entries,
    )
    print("   OK: All submodule imports successful")
except Exception as e:
    print(f"   ERROR: Import failed: {e}")
    import traceback
    traceback.print_exc()

print("\n2. Testing verifier functions...")
try:
    range_result = verify_range_logic("10.5 V", "0~20 V")
    print(f"   OK: verify_range_logic: {range_result[:100]}...")

    error_result = verify_error_logic("0.5", "1.0")
    print(f"   OK: verify_error_logic: {error_result[:100]}...")

    u_result = verify_uncertainty_logic("10.0", "0.5", "0.8")
    print(f"   OK: verify_uncertainty_logic: {u_result[:100]}...")
except Exception as e:
    print(f"   ERROR: Verifier test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n3. Testing semantic analysis...")
try:
    semantics = infer_param_semantics("电压", "10.0 V")
    print(f"   OK: infer_param_semantics: category={semantics.get('category')}")
except Exception as e:
    print(f"   ERROR: Semantic analysis test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n4. Testing main function imports...")
try:
    from langchain_app.checks import check_parameters, parameter_check_wrapper, run_llm_mode
    print("   OK: Main function imports successful")
except Exception as e:
    print(f"   ERROR: Main function import failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
