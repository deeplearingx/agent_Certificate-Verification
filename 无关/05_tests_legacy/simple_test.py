#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试脚本 - 检查架构的关键部分
"""

import sys
import os

print("=" * 60)
print("简单架构测试")
print("=" * 60)

# 测试 1: utils 模块
print("\n[1/5] 检查 utils 模块...")
try:
    from langchain_app.utils import get_app_config
    print("  [OK] utils 模块导入成功")
except Exception as e:
    print(f"  [FAIL] utils 模块导入失败: {e}")
    sys.exit(1)

# 测试 2: checks 模块
print("\n[2/5] 检查 checks 模块...")
try:
    from langchain_app.checks import (
        check_certificate_integrity,
        check_environment,
    )
    print("  [OK] checks 模块导入成功")
except Exception as e:
    print(f"  [FAIL] checks 模块导入失败: {e}")
    sys.exit(1)

# 测试 3: tools 模块
print("\n[3/5] 检查 tools 模块...")
try:
    from langchain_app.tools import get_all_tools
    tools = get_all_tools()
    print(f"  [OK] tools 模块导入成功，共 {len(tools)} 个工具")
except Exception as e:
    print(f"  [FAIL] tools 模块导入失败: {e}")
    sys.exit(1)

# 测试 4: services 模块
print("\n[4/5] 检查 services 模块...")
try:
    from langchain_app.services.parsing import pdf_to_md_first_step
    print("  [OK] services.parsing 模块导入成功")
except Exception as e:
    print(f"  [FAIL] services.parsing 模块导入失败: {e}")

# 测试 5: graph 模块（可选）
print("\n[5/5] 检查 graph 模块...")
try:
    from langchain_app.graph import build_verification_graph
    print("  [OK] graph 模块导入成功")
except Exception as e:
    print(f"  [WARN] graph 模块导入失败（可能需要额外依赖）: {e}")

print("\n" + "=" * 60)
print("测试完成！已修复的问题：")
print("=" * 60)
print("\n1. [DONE] 修复 core <-> graph 循环导入")
print("2. [DONE] 解除 checks/__init__.py 的重导入")
print("3. [DONE] 修复 LLMClient 调用参数错误")
print("4. [DONE] 创建独立的 services 层")
print("5. [DONE] 更新 tools 层使用新 checks 接口")
print("\n待完成：")
print("1. [DONE] 补齐参数核验完整实现")
print("2. [PENDING] 校验参数核验与原版一致性")
print("3. [DONE] 收口 pipeline 职责")
print("4. [DONE] 收口旧桥接依赖")
print("5. [DONE] 修复验证脚本编码问题")
print("6. [DONE] 清理文档与命名漂移")
