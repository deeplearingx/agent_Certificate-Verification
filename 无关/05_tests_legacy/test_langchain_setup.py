#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 LangChain 架构设置
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """测试配置模块"""
    try:
        from langchain_app.utils import AppConfig
        print("[1/4] 测试配置模块...")
        config = AppConfig.from_env()
        print(f"  - API Key: {config.api_key[:10]}..." if config.api_key else "  - API Key: (not set)")
        print(f"  - Model: {config.model}")
        print(f"  - Embedding Model: {config.embed_model_path}")
        print(f"  - Temperature: {config.temperature}")
        print("  [OK] Config 模块测试通过！")
        return True
    except Exception as e:
        print(f"  [ERROR] Config 模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_core_modules():
    """测试核心模块"""
    try:
        print("[2/4] 测试核心模块导入...")
        from langchain_app.core import LLMClient
        print("  [OK] LLMClient 导入成功")

        from langchain_app.core import VectorDatabase
        print("  [OK] VectorDatabase 导入成功")

        from langchain_app.core import VerificationReport
        print("  [OK] VerificationReport 导入成功")
        return True
    except Exception as e:
        print(f"  [ERROR] 核心模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tools():
    """测试工具模块"""
    try:
        print("[3/4] 测试工具模块...")
        from langchain_app.tools.example_tools import get_all_tools
        tools = get_all_tools()
        print(f"  - 找到 {len(tools)} 个工具")
        for tool in tools:
            print(f"    - {tool.name}")
        print("  [OK] 工具模块测试通过！")
        return True
    except Exception as e:
        print(f"  [ERROR] 工具模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agents():
    """测试 Agent 模块"""
    try:
        print("[4/4] 测试 Agent 模块...")
        from langchain_app.agents import VerificationAgent
        print("  [OK] VerificationAgent 导入成功")
        return True
    except Exception as e:
        print(f"  [ERROR] Agent 模块测试失败: {e}")
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
        status = "[OK] 通过" if passed else "[ERROR] 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("[SUCCESS] 所有测试通过！LangChain 架构设置成功！")
    else:
        print("[WARNING] 部分测试失败，请检查上面的错误信息")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
