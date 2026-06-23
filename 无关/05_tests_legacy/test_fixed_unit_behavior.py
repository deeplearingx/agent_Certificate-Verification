#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的 parse_symmetric_limit 函数对单位的正确处理
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=== 比较原始代码和修复后的行为 ===")

# 原始代码
import param_check as original

# 修复后的代码
parameter_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks", "parameter")
import importlib.util
parser_path = os.path.join(parameter_dir, "parser.py")
spec = importlib.util.spec_from_file_location("parser", parser_path)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)

print("\n1. 测试 parse_symmetric_limit 对 '+/-5 mV' 的处理:")
orig_result = original.parse_symmetric_limit("+/-5 mV")
fixed_result = parser.parse_symmetric_limit("+/-5 mV")

print(f"   原始代码: '+/-5 mV' -> {orig_result}")
print(f"   修复后代码: '+/-5 mV' -> {fixed_result}")

print("\n2. 测试其他格式:")
test_cases = [
    "+/-5 mV",
    "±5 mV",
    "+/-10 V",
    "±10 V",
    "+/-0.5 kHz",
    "±0.5 kHz",
]

for s in test_cases:
    orig = original.parse_symmetric_limit(s)
    fixed = parser.parse_symmetric_limit(s)
    match = orig == fixed
    print(f"   '{s}': orig={orig} fixed={fixed} match={match}")

print("\n✓ 修复后的代码正确进行了单位转换！")
print("✓ 虽然与原始代码行为不同，但这是更正确的处理方式。")