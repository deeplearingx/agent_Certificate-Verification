#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 validator.py 的修复是否正确
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing validator.py fixes")
print("=" * 60)

parameter_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "langchain_app", "checks", "parameter")

# 测试 parser 和 validator
print("\n1. Testing parser and validator together...")
try:
    import importlib.util

    # 导入 parser
    parser_path = os.path.join(parameter_dir, "parser.py")
    spec = importlib.util.spec_from_file_location("parser", parser_path)
    parser_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser_mod)
    print("   OK: parser imported")

    # 导入 validator
    validator_path = os.path.join(parameter_dir, "validator.py")
    spec = importlib.util.spec_from_file_location("langchain_app.checks.parameter.validator", validator_path)
    validator_mod = importlib.util.module_from_spec(spec)
    sys.modules["langchain_app.checks.parameter.validator"] = validator_mod
    # 确保 parser 模块已正确加载
    sys.modules['langchain_app.checks.parameter.parser'] = parser_mod
    # 临时添加 langchain_app 路径
    langchain_app_dir = os.path.abspath(os.path.join(parameter_dir, "..", ".."))
    sys.path.append(langchain_app_dir)
    spec.loader.exec_module(validator_mod)
    print("   OK: validator imported")

    # 测试范围验证
    print("\n2. Testing range verification...")

    test_cases = [
        ("10.5 V", "0~20 V", "PASS"),
        ("25 V", "0~20 V", "FAIL"),
        ("-5 V", "±10 V", "PASS"),
        ("15 V", "±10 V", "FAIL"),
        ("5 V", "≥0 V", "PASS"),
        ("-5 V", "≥0 V", "FAIL"),
        ("5 V", "≤10 V", "PASS"),
        ("15 V", "≤10 V", "FAIL"),
    ]

    all_passed = True
    for measure_val, range_str, expected in test_cases:
        result = validator_mod.verify_range_logic(measure_val, range_str)
        import json
        result_obj = json.loads(result)
        status = result_obj.get("status", "UNKNOWN")
        ok = status == expected
        all_passed = all_passed and ok
        print(f"   {measure_val} in {range_str}: {status} {'✓' if ok else '✗'} (expected {expected})")
        if not ok:
            print(f"     Reason: {result_obj.get('reason', '')}")

    # 测试误差验证
    print("\n3. Testing error verification...")

    error_cases = [
        ("0.5", "1.0", "PASS"),
        ("1.5", "1.0", "FAIL"),
        ("-0.5", "1.0", "PASS"),
        ("0.5 dB", "1.0 dB", "PASS"),
    ]

    for error_val, limit_val, expected in error_cases:
        result = validator_mod.verify_error_logic(error_val, limit_val)
        import json
        result_obj = json.loads(result)
        status = result_obj.get("status", "UNKNOWN")
        ok = status == expected
        all_passed = all_passed and ok
        print(f"   error={error_val}, limit={limit_val}: {status} {'✓' if ok else '✗'} (expected {expected})")

    # 测试不确定度验证
    print("\n4. Testing uncertainty verification...")

    uncertainty_cases = [
        ("10.0", "0.5", "0.8", "PASS"),
        ("10.0", "1.0", "0.8", "FAIL"),
        ("10.0", "5%", "10%", "PASS"),  # relative
    ]

    for measure_val, cert_u, kb_u, expected in uncertainty_cases:
        result = validator_mod.verify_uncertainty_logic(measure_val, cert_u, kb_u)
        import json
        result_obj = json.loads(result)
        status = result_obj.get("status", "UNKNOWN")
        ok = status == expected
        all_passed = all_passed and ok
        print(f"   measure={measure_val}, cert={cert_u}, kb={kb_u}: {status} {'✓' if ok else '✗'} (expected {expected})")

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ✗")
    print("=" * 60)

except Exception as e:
    print(f"\nERROR: Test failed: {e}")
    import traceback
    traceback.print_exc()
