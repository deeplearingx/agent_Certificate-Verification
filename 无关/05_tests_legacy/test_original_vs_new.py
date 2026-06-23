#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比测试原始 param_check.py 和新的 parameter 模块
"""

import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 70)
print("Testing original param_check.py vs new parameter module")
print("=" * 70)

# 首先测试原始模块
print("\n1. Testing original param_check.py...")
try:
    import param_check as original
    print("   OK: original param_check imported")

    # 测试原始函数
    test_cases = [
        ("10.5 V", "0~20 V"),
        ("25 V", "0~20 V"),
        ("-5 V", "±10 V"),
        ("15 V", "±10 V"),
        ("5 V", "≥0 V"),
        ("-5 V", "≥0 V"),
        ("5 V", "≤10 V"),
        ("15 V", "≤10 V"),
    ]

    print("\n   Original verify_range_logic:")
    for measure, range_str in test_cases:
        result = original.verify_range_logic(measure, range_str)
        result_obj = json.loads(result)
        print(f"      {measure:10} in {range_str:10} -> {result_obj['status']:6} - {result_obj.get('reason', '')[:60]}")

    print("\n   Original verify_error_logic:")
    error_cases = [("0.5", "1.0"), ("1.5", "1.0"), ("-0.5", "1.0")]
    for err, limit in error_cases:
        result = original.verify_error_logic(err, limit)
        result_obj = json.loads(result)
        print(f"      err={err:5}, limit={limit:5} -> {result_obj['status']:6}")

except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# 现在测试新模块
print("\n" + "=" * 70)
print("2. Testing new parameter module...")
print("=" * 70)

try:
    # 直接导入新模块
    from langchain_app.checks.parameter import parser, validator
    print("   OK: new parameter modules imported")

    print("\n   New verify_range_logic:")
    for measure, range_str in test_cases:
        result = validator.verify_range_logic(measure, range_str)
        result_obj = json.loads(result)
        print(f"      {measure:10} in {range_str:10} -> {result_obj['status']:6} - {result_obj.get('reason', '')[:60]}")

    print("\n   New verify_error_logic:")
    for err, limit in error_cases:
        result = validator.verify_error_logic(err, limit)
        result_obj = json.loads(result)
        print(f"      err={err:5}, limit={limit:5} -> {result_obj['status']:6}")

except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Test complete!")
print("=" * 70)
