#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试 parse_value_with_unit 函数对不同格式的处理
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

parameter_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks", "parameter")
import importlib.util
parser_path = os.path.join(parameter_dir, "parser.py")
spec = importlib.util.spec_from_file_location("parser", parser_path)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)

print("=== 调试 parse_value_with_unit ===")

test_cases = [
    "+/-5 mV",
    "±5 mV",
    "5 mV",
    "+/- 5 mV",
]

for s in test_cases:
    print(f"\n测试: '{s}'")
    # 模拟 parse_value_with_unit 的处理流程
    s_mod = s
    print(f"  原始: '{s_mod}'")

    # 步骤 1: 去除 +/- 前缀
    if "+/-" in s_mod:
        cleaned_str = s_mod.replace("+/-", "").strip()
        print(f"  去除 +/- 后: '{cleaned_str}'")
    else:
        cleaned_str = s_mod

    # 步骤 2: 提取数字
    import re
    m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", cleaned_str)
    if m:
        num_str = m.group(1)
        print(f"  提取数字: '{num_str}'")

    # 步骤 3: 提取单位
    unit_source_str = s_mod.replace("+/-", "").strip() if "+/-" in s_mod else s_mod
    unit_part = re.sub(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", "", unit_source_str).strip()
    print(f"  提取单位: '{unit_part}'")

    # 调用实际函数
    val, unit_type = parser.parse_value_with_unit(s, keep_sign=True)
    print(f"  parse_value_with_unit 返回: val={val}, type={unit_type}")