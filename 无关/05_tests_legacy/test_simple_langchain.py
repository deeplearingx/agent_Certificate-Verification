#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在 langchain conda 环境中简单测试我们的更改
"""

import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Simple test in langchain conda environment")
print("=" * 60)

print(f"\nPython version: {sys.version}")
print(f"Python executable: {sys.executable}")

# 检查关键依赖是否存在
print("\n=== Checking critical dependencies ===")
critical_deps = ["pydantic"]
for dep in critical_deps:
    try:
        __import__(dep)
        print(f"OK: {dep} is available")
    except ImportError:
        print(f"ERROR: {dep} is NOT available")

# 测试我们的核心修复 - parameter 模块的解析函数
print("\n=== Testing parameter parser ===")

try:
    # 导入原始模块用于对比
    import param_check as original
    print("OK: Original param_check.py imported")

    # 直接导入我们的 parser
    parameter_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks", "parameter")
    import importlib.util

    parser_path = os.path.join(parameter_dir, "parser.py")
    spec = importlib.util.spec_from_file_location("parser", parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    print("OK: New parser.py loaded")

    # 测试所有解析函数
    print("\nTesting parser functions:")

    # 1. parse_value_with_unit
    print("\n1. parse_value_with_unit:")
    orig_val, orig_type = original.parse_value_with_unit("10.5 V", keep_sign=True)
    new_val, new_type = parser.parse_value_with_unit("10.5 V", keep_sign=True)
    match_val = orig_val == new_val
    print(f"   '10.5 V': orig={orig_val} new={new_val} match={match_val}")

    # 2. parse_range_limit
    print("\n2. parse_range_limit:")
    orig_range = original.parse_range_limit("0~20 V")
    new_range = parser.parse_range_limit("0~20 V")
    match_range = orig_range == new_range
    print(f"   '0~20 V': orig={orig_range} new={new_range} match={match_range}")

    # 3. parse_symmetric_limit
    print("\n3. parse_symmetric_limit:")
    orig_sym = original.parse_symmetric_limit("±10 V")
    new_sym = parser.parse_symmetric_limit("±10 V")
    match_sym = orig_sym == new_sym
    print(f"   '±10 V': orig={orig_sym} new={new_sym} match={match_sym}")

    # 4. parse_single_sided_limit
    print("\n4. parse_single_sided_limit:")
    orig_single = original.parse_single_sided_limit("≥0 V")
    new_single = parser.parse_single_sided_limit("≥0 V")
    match_single = orig_single == new_single
    print(f"   '≥0 V': orig={orig_single} new={new_single} match={match_single}")

    # 5. 测试范围验证逻辑
    print("\n=== Testing range verification ===")

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

    print("\nComparing verify_range_logic:")

    # 首先导入我们的 validator
    validator_path = os.path.join(parameter_dir, "validator.py")
    spec = importlib.util.spec_from_file_location("validator", validator_path)
    validator = importlib.util.module_from_spec(spec)

    # 设置正确的模块上下文
    import sys
    sys.modules['langchain_app.checks.parameter.parser'] = parser

    # 现在加载 validator
    spec.loader.exec_module(validator)
    print("OK: validator.py loaded")

    all_match = True
    for measure, range_str in test_cases:
        orig_result = original.verify_range_logic(measure, range_str)
        new_result = validator.verify_range_logic(measure, range_str)

        orig_obj = json.loads(orig_result)
        new_obj = json.loads(new_result)

        orig_status = orig_obj.get('status', 'UNKNOWN')
        new_status = new_obj.get('status', 'UNKNOWN')
        match = orig_status == new_status
        all_match = all_match and match

        print(f"  {measure:10} in {range_str:10} -> orig:{orig_status:6} new:{new_status:6} {'OK' if match else 'FAIL'}")

    print("\n" + "=" * 60)
    if all_match:
        print("All test cases match! OK")
    else:
        print("Some tests don't match! FAIL")
    print("=" * 60)

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()

print("\nTest complete!")
