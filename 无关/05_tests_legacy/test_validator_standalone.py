#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立测试 validator 修复，不依赖完整的 langchain_app 导入
"""

import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 70)
print("Testing validator module fixes - standalone")
print("=" * 70)

# 直接导入原始模块用于对比
print("\n1. Original param_check.py results (for comparison):")
try:
    import param_check as original
    print("   OK: original param_check imported")

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

    original_results = {}
    for measure, range_str in test_cases:
        result = original.verify_range_logic(measure, range_str)
        result_obj = json.loads(result)
        original_results[(measure, range_str)] = result_obj
        print(f"   {measure:10} in {range_str:10} -> {result_obj['status']:6}")

except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()
    original_results = {}

# 现在直接加载我们的模块文件
print("\n" + "=" * 70)
print("2. Testing our fixed parser and validator:")
print("=" * 70)

parameter_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "langchain_app", "checks", "parameter")

# 首先加载 parser
import importlib.util
parser_path = os.path.join(parameter_dir, "parser.py")
spec = importlib.util.spec_from_file_location("parser", parser_path)
parser = importlib.util.module_from_spec(spec)

# 创建一个最小化的环境
import types
mock_langchain_app = types.ModuleType('langchain_app')
mock_checks = types.ModuleType('langchain_app.checks')
mock_parameter = types.ModuleType('langchain_app.checks.parameter')
sys.modules['langchain_app'] = mock_langchain_app
sys.modules['langchain_app.checks'] = mock_checks
sys.modules['langchain_app.checks.parameter'] = mock_parameter
sys.modules['langchain_app.checks.parameter.parser'] = parser

spec.loader.exec_module(parser)
print("   OK: parser loaded")

# 现在加载 validator
validator_path = os.path.join(parameter_dir, "validator.py")
spec = importlib.util.spec_from_file_location("validator", validator_path)
validator = importlib.util.module_from_spec(spec)
sys.modules['langchain_app.checks.parameter.validator'] = validator
# 确保 validator 能找到 parser
validator.parser = parser

try:
    spec.loader.exec_module(validator)
    print("   OK: validator loaded")

    print("\n   Testing verify_range_logic:")
    all_match = True
    for measure, range_str in test_cases:
        try:
            result = validator.verify_range_logic(measure, range_str)
            result_obj = json.loads(result)
            orig_result = original_results.get((measure, range_str), {})
            orig_status = orig_result.get('status', 'UNKNOWN')
            new_status = result_obj.get('status', 'UNKNOWN')
            match = orig_status == new_status
            all_match = all_match and match
            print(f"   {measure:10} in {range_str:10} -> new:{new_status:6} orig:{orig_status:6} {'OK' if match else 'FAIL'}")
            if not match:
                print(f"      New reason: {result_obj.get('reason', '')[:80]}")
                print(f"      Orig reason: {orig_result.get('reason', '')[:80]}")
        except Exception as e:
            print(f"   {measure:10} in {range_str:10} -> ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_match = False

    print("\n" + "=" * 70)
    if all_match and original_results:
        print("All test cases match! OK")
    else:
        print("Some tests don't match! FAIL")
    print("=" * 70)

except Exception as e:
    print(f"\n   ERROR loading validator: {e}")
    import traceback
    traceback.print_exc()

print("\nTest complete!")
