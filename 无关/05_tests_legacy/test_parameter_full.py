#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面测试参数核验模块
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("全面测试参数核验模块")
print("=" * 60)

print("\n1. 测试所有子模块导入...")
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
    print("   ✓ 所有子模块导入成功")
except Exception as e:
    print(f"   ✗ 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n2. 测试验证器函数...")
try:
    range_result = verify_range_logic("10.5 V", "0~20 V")
    print(f"   ✓ verify_range_logic: {range_result}")

    error_result = verify_error_logic("0.5", "1.0")
    print(f"   ✓ verify_error_logic: {error_result}")

    u_result = verify_uncertainty_logic("10.0", "0.5", "0.8")
    print(f"   ✓ verify_uncertainty_logic: {u_result}")
except Exception as e:
    print(f"   ✗ 验证器测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n3. 测试语义分析函数...")
try:
    semantics = infer_param_semantics("电压", "10.0 V")
    print(f"   ✓ infer_param_semantics: category={semantics.get('category')}")
except Exception as e:
    print(f"   ✗ 语义分析测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n4. 测试主函数导入...")
try:
    from langchain_app.checks import check_parameters, parameter_check_wrapper, run_llm_mode
    print("   ✓ 主函数导入成功")
except Exception as e:
    print(f"   ✗ 主函数导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
