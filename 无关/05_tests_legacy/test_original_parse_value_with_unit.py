#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试原始 parse_value_with_unit 函数对不同格式的处理
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import param_check as original
import re

print("=== Testing parse_value_with_unit ===")

# 测试不同格式的字符串
test_strings = [
    "+/-5 mV",    # 测试1: +/-格式
    "+/- 5 mV",   # 测试2: +/- 带空格
    "+/-  5 mV",  # 测试3: +/- 带多个空格
    "±5 mV",      # 测试4: ±格式
    "+/-10 V",    # 测试5: +/- 不带单位
    "+/-1.5 kHz", # 测试6: 浮点数
    "1.5 mV",     # 测试7: 普通格式
]

print("\n1. parse_value_with_unit:")
for s in test_strings:
    val, unit_type = original.parse_value_with_unit(s, keep_sign=True)
    print(f"   '{s}' -> val={val}, type={unit_type}")

print("\n2. 使用正则表达式分析:")
for s in test_strings:
    # 复制原始函数中的一些处理步骤
    s_mod = s.replace("≤", "<=").replace("≥", ">=")
    s_mod = s_mod.replace("＋", "+").replace("﹢", "+")
    s_mod = s_mod.replace("—", "-").replace("−", "-")
    print(f"   '{s}' -> '{s_mod}'")

print("\n3. 查看 VALUE_TOKEN_PATTERN 匹配:")
for s in test_strings:
    match = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
    if match:
        found_num = match.group(1)
        print(f"   '{s}' -> num='{found_num}'")