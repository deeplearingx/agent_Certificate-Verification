#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试零阈值的边界情况
"""

import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing zero threshold edge case")
print("=" * 60)

# 测试原始模块
print("\n1. Original param_check.py:")
import param_check as original

measure_val = "-5 V"
range_str = "≥0 V"
result = original.verify_range_logic(measure_val, range_str)
result_obj = json.loads(result)
print(f"   measure_val: {measure_val}")
print(f"   range_str: {range_str}")
print(f"   status: {result_obj['status']}")
print(f"   reason: {result_obj['reason']}")

# 让我们手动测试 parse_single_sided_limit
print("\n   Manual test:")
single_limit = original.parse_single_sided_limit(range_str)
print(f"   parse_single_sided_limit('{range_str}'): {single_limit}")

if single_limit:
    op, thr = single_limit
    print(f"   op: {op}, thr: {thr}")

    # 解析测量值
    m_val, _ = original.parse_value_with_unit(measure_val)
    print(f"   m_val: {m_val}")

    # 计算容差和比较
    tolerance = max(abs(thr) * 0.01, 1e-15)
    print(f"   tolerance: {tolerance}")

    if op == ">=":
        pass_flag = m_val >= (thr - tolerance)
        print(f"   m_val >= (thr - tolerance): {m_val} >= {thr - tolerance} = {pass_flag}")

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
