#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试 parameter 模块的核心功能
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing parameter module core functions")
print("=" * 60)

print("\n1. Testing parser functions...")
try:
    from langchain_app.checks.parameter.parser import (
        parse_value_with_unit,
        parse_range_limit,
        parse_symmetric_limit,
        parse_single_sided_limit,
        extract_basis_code,
        norm_code,
    )

    # Test parse_value_with_unit
    val, kind = parse_value_with_unit("10.5 V")
    print(f"   parse_value_with_unit('10.5 V'): value={val}, kind={kind}")

    # Test norm_code
    code = norm_code("JJG 237-2010")
    print(f"   norm_code('JJG 237-2010'): {code}")

    # Test extract_basis_code
    basis = extract_basis_code("依据 JJF 1234-2020 进行校准")
    print(f"   extract_basis_code('依据 JJF 1234-2020 进行校准'): {basis}")

    print("   OK: Parser functions test passed")
except Exception as e:
    print(f"   ERROR: Parser test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n2. Testing validator functions...")
try:
    from langchain_app.checks.parameter.validator import (
        verify_range_logic,
        verify_error_logic,
        verify_uncertainty_logic,
    )

    # Test verify_range_logic
    range_result = verify_range_logic("10.5 V", "0~20 V")
    print(f"   verify_range_logic: {range_result[:150]}...")

    # Test verify_error_logic
    error_result = verify_error_logic("0.5", "1.0")
    print(f"   verify_error_logic: {error_result[:150]}...")

    # Test verify_uncertainty_logic
    u_result = verify_uncertainty_logic("10.0", "0.5", "0.8")
    print(f"   verify_uncertainty_logic: {u_result[:150]}...")

    print("   OK: Validator functions test passed")
except Exception as e:
    print(f"   ERROR: Validator test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n3. Testing semantic functions...")
try:
    from langchain_app.checks.parameter.semantic import (
        infer_param_semantics,
        FirstCandidateDecider,
        infer_uncertainty_kind,
        norm_code,
        extract_basis_code,
    )

    # Test infer_param_semantics
    semantics = infer_param_semantics("电压", "10.0 V", "0.1 V")
    print(f"   infer_param_semantics: task_intent={semantics.task_intent}, unit_family={semantics.unit_family}")

    # Test infer_uncertainty_kind
    kind = infer_uncertainty_kind("0.5%")
    print(f"   infer_uncertainty_kind('0.5%'): {kind}")

    print("   OK: Semantic functions test passed")
except Exception as e:
    print(f"   ERROR: Semantic test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n4. Testing reporter functions...")
try:
    from langchain_app.checks.parameter.reporter import (
        build_param_table,
        build_batch_summary_table,
        enforce_kb_missing_fail,
    )

    # Test build_param_table
    test_entries = [
        {"参数名称": "电压", "测量值": "10.5", "单位": "V", "范围": "0~20 V", "误差": "0.5", "不确定度": "0.2", "status": "PASS"},
    ]
    table = build_param_table(test_entries)
    print(f"   build_param_table: generated table with {len(table.splitlines())} lines")

    print("   OK: Reporter functions test passed")
except Exception as e:
    print(f"   ERROR: Reporter test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n5. Testing retrieval functions...")
try:
    from langchain_app.checks.parameter.retrieval import (
        filter_kb_entries,
    )

    print("   OK: Retrieval functions import passed")
except Exception as e:
    print(f"   ERROR: Retrieval test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
