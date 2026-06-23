#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试参数核验模块的导入和基本功能
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("测试参数核验模块")
print("=" * 60)

print("\n1. 测试 parameter 子包的导入...")
try:
    from langchain_app.checks import check_parameters, parameter_check_wrapper, run_llm_mode
    print("   ✓ 主函数导入成功")
    print(f"   - check_parameters: {check_parameters}")
    print(f"   - parameter_check_wrapper: {parameter_check_wrapper}")
    print(f"   - run_llm_mode: {run_llm_mode}")
except Exception as e:
    print(f"   ✗ 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n2. 测试 parameter 子模块的导入...")
submodules = [
    "parser",
    "retrieval",
    "parameter",
]

for name in submodules:
    try:
        module_name = f"langchain_app.checks.parameter.{name}"
        __import__(module_name)
        print(f"   ✓ {name}.py 导入成功")
    except Exception as e:
        print(f"   ✗ {name}.py 导入失败: {e}")

print("\n3. 检查 parameter 目录结构...")
parameter_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks", "parameter")
if os.path.exists(parameter_dir):
    files = sorted(os.listdir(parameter_dir))
    print(f"   目录 {parameter_dir} 存在")
    print(f"   文件列表:")
    for f in files:
        if f.endswith(".py"):
            print(f"      - {f}")
else:
    print(f"   ✗ 目录 {parameter_dir} 不存在")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
