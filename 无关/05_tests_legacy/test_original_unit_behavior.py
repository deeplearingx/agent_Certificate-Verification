#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试原始 param_check.py 对单位的处理
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import param_check as original

print("=== Testing original param_check.py ===")

test_cases = [
    "5 mV",
    "+/-5 mV",
    "±5 mV",
    "10 kHz",
    "0.5 GHz",
]

print("\n1. parse_value_with_unit:")
for val_str in test_cases:
    val, unit_type = original.parse_value_with_unit(val_str, keep_sign=True)
    print(f"   '{val_str}' -> val={val}, type={unit_type}")

print("\n2. parse_symmetric_limit:")
for val_str in ["+/-5 mV", "±5 mV", "±10 kHz"]:
    result = original.parse_symmetric_limit(val_str)
    print(f"   '{val_str}' -> {result}")

print("\n3. parse_range_limit:")
for range_str in ["0~20 V", "0~50 mV", "0~10 kHz"]:
    result = original.parse_range_limit(range_str)
    print(f"   '{range_str}' -> {result}")