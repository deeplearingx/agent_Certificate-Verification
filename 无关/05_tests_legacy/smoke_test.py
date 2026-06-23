#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke Test - 最小冒烟测试

用于快速验证配置加载、模块导入等基础功能
"""

import sys
import os
from pathlib import Path

# 确保项目根目录在路径中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

def print_line(char='=', length=60):
    print(char * length)

def test_config():
    """测试配置加载"""
    print_line()
    print("测试: 配置模块加载")
    print_line()
    try:
        from langchain_app.utils import get_app_config
        config = get_app_config()
        print("[OK] 配置模块加载成功")
        print(f"  根目录: {config.root_dir}")
        print(f"  模型: {config.model}")
        print(f"  API Key: {'已设置' if config.api_key else '未设置'}")
        return True
    except Exception as e:
        print(f"[FAIL] 配置模块加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_core_imports():
    """测试核心模块导入"""
    print_line()
    print("测试: 核心模块导入")
    print_line()

    modules_to_test = [
        ("LLMClient", "from langchain_app.core import LLMClient"),
        ("VectorDatabase", "from langchain_app.core import VectorDatabase"),
        ("VerificationReport", "from langchain_app.core import VerificationReport"),
        ("PipelineHooks", "from langchain_app.core import PipelineHooks"),
        ("load_shared_embedder", "from langchain_app.core import load_shared_embedder"),
    ]

    all_ok = True
    for name, import_stmt in modules_to_test:
        try:
            exec(import_stmt)
            print(f"[OK] {name} 导入成功")
        except Exception as e:
            print(f"[FAIL] {name} 导入失败: {e}")
            all_ok = False
    return all_ok

def test_tools_import():
    """测试工具模块导入"""
    print_line()
    print("测试: 工具模块导入")
    print_line()
    try:
        from langchain_app.tools import get_all_tools
        tools = get_all_tools()
        print(f"[OK] 工具模块加载成功")
        print(f"  找到 {len(tools)} 个工具")
        for i, tool in enumerate(tools, 1):
            print(f"    {i}. {tool.name}")
        return True
    except Exception as e:
        print(f"[FAIL] 工具模块加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agents_import():
    """测试 Agent 模块导入"""
    print_line()
    print("测试: Agent 模块导入")
    print_line()
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
    print_line()
    print("LangGraph 重构 - 冒烟测试")
    print_line()
    print()

    results = []
    results.append(("配置加载", test_config()))
    print()
    results.append(("核心模块", test_core_imports()))
    print()
    results.append(("工具模块", test_tools_import()))
    print()
    results.append(("Agent 模块", test_agents_import()))
    print()

    print_line()
    print("测试结果汇总")
    print_line()
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print_line()
    if all_passed:
        print("所有测试通过！基础架构验证完成。")
        print_line()
        print("\n下一步操作:")
        print("  1. 激活 langchain 环境: conda activate langchain")
        print("  2. 安装依赖: pip install -r requirements_langchain.txt")
        print("  3. 继续进行阶段 2: 引入 LangGraph 骨架")
    else:
        print("部分测试失败，请检查上面的错误信息")
    print_line()

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
