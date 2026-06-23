#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试参数模块的功能，避免相对导入问题
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

parameter_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks", "parameter")

import importlib.util

# 直接导入 parser
parser_path = os.path.join(parameter_dir, "parser.py")
spec = importlib.util.spec_from_file_location("parser", parser_path)
parser = importlib.util.module_from_spec(spec)
sys.modules['langchain_app.checks.parameter.parser'] = parser
spec.loader.exec_module(parser)
print('✓ parser.py loaded')

# 导入 validator
validator_path = os.path.join(parameter_dir, "validator.py")
spec = importlib.util.spec_from_file_location("validator", validator_path)
validator = importlib.util.module_from_spec(spec)
sys.modules['langchain_app.checks.parameter.validator'] = validator
spec.loader.exec_module(validator)
print('✓ validator.py loaded')

print("\n=== 基本解析测试 ===")
for test_str in ['10.5 V', '-5 V', '25.0 mV', '0.1%']:
    val, unit_type = parser.parse_value_with_unit(test_str, keep_sign=True)
    print(f"  {test_str:10} -> val={val:6.3g}, type={unit_type}")

print("\n=== 对称限制解析 ===")
test_cases = ['+/-5 mV', '±5 mV', '+/-0.5 kHz', '±0.5 kHz', '+/-10 V']
for test_str in test_cases:
    result = parser.parse_symmetric_limit(test_str)
    print(f"  {test_str:10} -> {result}")

print("\n=== 范围验证 ===")
test_cases = [
    ('10.5 V', '0~20 V'),
    ('25 V', '0~20 V'),
    ('-5 V', '±10 V'),
    ('15 V', '±10 V'),
]
for measure, limit in test_cases:
    result = validator.verify_range_logic(measure, limit)
    print(f"  {measure:10} in {limit:10} -> {result}")

print("\n=== 所有测试完成 ===")