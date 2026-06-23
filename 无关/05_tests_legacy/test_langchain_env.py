#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在 langchain conda 环境中测试我们的更改
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing in langchain conda environment")
print("=" * 60)

print(f"\nPython version: {sys.version}")
print(f"Python executable: {sys.executable}")

# 检查 langchain 相关的依赖是否存在
print("\n=== Checking dependencies ===")
dependencies = [
    "langchain",
    "langchain_core",
    "langchain_openai",
    "langgraph",
    "pydantic",
]

for dep in dependencies:
    try:
        __import__(dep)
        print(f"✓ {dep} is available")
    except ImportError:
        print(f"✗ {dep} is NOT available")

# 测试我们的模块
print("\n=== Testing our modules ===")

try:
    # 直接从原始 param_check.py 导入进行对比
    import param_check as original
    print("✓ Original param_check.py imported")

    # 测试原始函数
    print("\nTesting original functions:")
    test_result = original.verify_range_logic("10.5 V", "0~20 V")
    print(f"  verify_range_logic('10.5 V', '0~20 V') = {test_result[:80]}")

except Exception as e:
    print(f"✗ Original param_check test failed: {e}")

# 尝试导入我们的新模块（绕过 checks/__init__.py 来避免依赖问题
print("\n=== Testing new parameter module ===")

try:
    import sys
    import os
    parameter_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks", "parameter")

    # 直接导入 parser
    import importlib.util
    parser_path = os.path.join(parameter_dir, "parser.py")
    spec = importlib.util.spec_from_file_location("parser", parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    print("✓ parser.py loaded")

    # 测试 parser 函数
    print("\nTesting parser functions:")
    result = parser.parse_range_limit("0~20 V")
    print(f"  parse_range_limit('0~20 V') = {result}")

    result = parser.parse_symmetric_limit("±10 V")
    print(f"  parse_symmetric_limit('±10 V') = {result}")

    result = parser.parse_single_sided_limit("≥0 V")
    print(f"  parse_single_sided_limit('≥0 V') = {result}")

    # 测试 parse_value_with_unit
    val, unit = parser.parse_value_with_unit("10.5 V", keep_sign=True)
    print(f"  parse_value_with_unit('10.5 V') = {val}, {unit}")

    # 现在测试 validator
    validator_path = os.path.join(parameter_dir, "validator.py")
    spec = importlib.util.spec_from_file_location("validator", validator_path)
    validator = importlib.util.module_from_spec(spec)

    # 设置 sys.modules['langchain_app.checks.parameter.parser'] = parser
    sys.modules['langchain_app.checks.parameter'] = sys.modules['__main__']

    spec.loader.exec_module(validator)
    print("\n✓ validator.py loaded")

    # 测试 validator 函数
    print("\nTesting validator functions:")

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

    print("\nComparing original vs new:")
    all_match = True
    for measure, range_str in test_cases:
        orig_result = original.verify_range_logic(measure, range_str)
        new_result = validator.verify_range_logic(measure, range_str)

        import json
        orig_obj = json.loads(orig_result)
        new_obj = json.loads(new_result)

        orig_status = orig_obj.get('status', 'UNKNOWN')
        new_status = new_obj.get('status', 'UNKNOWN')
        match = orig_status == new_status
        all_match = all_match and match

        print(f"  {measure:10} in {range_str:10} -> orig:{orig_status:6} new:{new_status:6} {'✓' if match else '✗'}")

    print("\n" + "=" * 60)
    if all_match:
        print("All test cases match! ✓")
    else:
        print("Some tests don't match! ✗")
    print("=" * 60)

except Exception as e:
    print(f"\n✗ Test failed: {e}")
    import traceback
    traceback.print_exc()

print("\nTest complete!")
