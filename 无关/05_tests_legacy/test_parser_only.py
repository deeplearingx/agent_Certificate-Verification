#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只测试 parser 模块，不涉及 validator 的相对导入问题
"""

import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing parser module only")
print("=" * 60)

print(f"\nPython version: {sys.version}")

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
    test_values = [
        ("10.5 V", True),
        ("-5 V", True),
        ("25.0 mV", False),
        ("0.1%", False),
    ]
    all_match = True
    for val_str, keep_sign in test_values:
        orig_val, orig_type = original.parse_value_with_unit(val_str, keep_sign=keep_sign)
        new_val, new_type = parser.parse_value_with_unit(val_str, keep_sign=keep_sign)
        match = orig_val == new_val
        all_match = all_match and match
        print(f"   '{val_str}' (keep_sign={keep_sign}): orig={orig_val} new={new_val} match={match}")

    # 2. parse_range_limit
    print("\n2. parse_range_limit:")
    range_strs = [
        "0~20 V",
        "-10~10 mV",
        "0.5~1.5 GHz",
    ]
    for range_str in range_strs:
        orig_range = original.parse_range_limit(range_str)
        new_range = parser.parse_range_limit(range_str)
        match = orig_range == new_range
        all_match = all_match and match
        print(f"   '{range_str}': orig={orig_range} new={new_range} match={match}")

    # 3. parse_symmetric_limit
    print("\n3. parse_symmetric_limit:")
    sym_strs = [
        "±10 V",
        "+/-5 mV",
        "±(0.5~1.5)",
    ]
    for sym_str in sym_strs:
        orig_sym = original.parse_symmetric_limit(sym_str)
        new_sym = parser.parse_symmetric_limit(sym_str)
        match = orig_sym == new_sym
        all_match = all_match and match
        print(f"   '{sym_str}': orig={orig_sym} new={new_sym} match={match}")

    # 4. parse_single_sided_limit
    print("\n4. parse_single_sided_limit:")
    single_strs = [
        "≥0 V",
        "≤10 mV",
        ">0.5",
        "<1.5",
    ]
    for single_str in single_strs:
        orig_single = original.parse_single_sided_limit(single_str)
        new_single = parser.parse_single_sided_limit(single_str)
        match = orig_single == new_single
        all_match = all_match and match
        print(f"   '{single_str}': orig={orig_single} new={new_single} match={match}")

    print("\n" + "=" * 60)
    if all_match:
        print("ALL PARSER TESTS PASSED!")
        print("All parser functions return identical values as original!")
    else:
        print("Some parser tests failed!")
    print("=" * 60)

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()

print("\nParser test complete!")
