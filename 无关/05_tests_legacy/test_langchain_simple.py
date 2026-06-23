#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试 LangChain 架构
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """测试配置模块"""
    try:
        from langchain_app.utils import AppConfig
        config = AppConfig.from_env()
        print("[OK] Config 模块加载成功")
        print(f"  - Model: {config.model}")
        print(f"  - Embedding Model: {config.embed_model_path}")
        print(f"  - Temperature: {config.temperature}")
        return True
    except Exception as e:
        print(f"[FAIL] Config 模块加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_core_modules():
    """测试核心模块"""
    try:
        from langchain_app.core import LLMClient
        print("[OK] LLMClient 导入成功")

        from langchain_app.core import VectorDatabase
        print("[OK] VectorDatabase 导入成功")

        from langchain_app.core import VerificationReport
        print("[OK] VerificationReport 导入成功")
        return True
    except Exception as e:
        print(f"[FAIL] 核心模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tools():
    """测试工具模块"""
    try:
        from langchain_app.tools.example_tools import get_all_tools
        tools = get_all_tools()
        print(f"[OK] 工具模块加载成功")
        print(f"  - 找到 {len(tools)} 个工具")
        return True
    except Exception as e:
        print(f"[FAIL] 工具模块加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agents():
    """测试 Agent 模块"""
    try:
        from langchain_app.agents import VerificationAgent
        print("[OK] VerificationAgent 导入成功")
        return True
    except Exception as e:
        print(f"[FAIL] Agent 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("LangChain 重构版 - 架构测试")
    print("=" * 60)
    print()

    results = []
    results.append(("配置模块", test_config()))
    print()
    results.append(("核心模块", test_core_modules()))
    print()
    results.append(("工具模块", test_tools()))
    print()
    results.append(("Agent 模块", test_agents()))
    print()

    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "通过" if passed else "失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("所有测试通过！LangChain 架构设置成功！")
    else:
        print("部分测试失败，请检查上面的错误信息")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
