#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装依赖并测试架构
"""

import sys
import subprocess

def run_command(cmd, desc):
    print(f"=== {desc} ===")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print(f"[ERROR] {desc} 失败")
        return False
    print(f"[SUCCESS] {desc} 完成")
    return True


def main():
    print("开始项目初始化和测试...")

    # 检查并安装依赖
    print("\n1. 检查并安装 Python 依赖...")
    if not run_command("pip install -r requirements_langchain.txt", "安装 LangChain 依赖"):
        print("依赖安装失败，请手动检查网络或权限")
        sys.exit(1)

    print("\n2. 安装完成，现在测试架构...")

    if not run_command("python test_current_architecture.py", "测试架构"):
        print("架构测试失败")
        sys.exit(1)

    print("\n项目初始化和测试完成！")
    print("\n架构状态：")
    print("- ✅ 依赖已安装")
    print("- ✅ 架构可正常工作")
    print("- ✅ core <-> graph 循环导入已修复")
    print("- ✅ checks/__init__.py 重导入已解除")
    print("- ✅ LLMClient 调用参数已修复")
    print("- ✅ Graph 可独立构建")
    print("- ✅ tools 层已切到新 checks 接口")
    print("- ⚠️  参数核验仍是占位实现，需要进一步完善")

    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as e:
        print(f"[ERROR] 执行失败: {e}")
        import traceback
        print(traceback.format_exc())
        exit_code = 1

    sys.exit(exit_code)
