#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 LangChain 架构重构是否成功
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("LangChain 架构重构验证")
print("=" * 60)
print()

try:
    from langchain_app import __version__
    print(f"[OK] LangChain App 版本: v{__version__}")
    print()

    from langchain_app.utils import get_app_config
    config = get_app_config()
    print("[OK] 配置管理模块加载成功")
    print(f"  - API Key: {'[OK]' if config.api_key else '[ERROR]'}")
    print(f"  - Model: {config.model}")
    print(f"  - Temperature: {config.temperature}")
    print()

    from langchain_app.tools import get_all_tools
    tools = get_all_tools()
    print(f"[OK] 工具模块加载成功 - 找到 {len(tools)} 个工具:")
    for i, tool in enumerate(tools, 1):
        print(f"  {i:2d}. {tool.name}")
    print()

    from langchain_app.core import PipelineHooks
    hooks = PipelineHooks()
    print("[OK] PipelineHooks 加载成功")
    print()

    from langchain_app.agents import VerificationAgent
    print("[OK] VerificationAgent 模块加载成功")
    print()

    from langchain_app.core import VectorDatabase, LLMClient
    print("[OK] 核心模块加载成功")
    print()

    print("=" * 60)
    print("所有核心模块验证成功！")
    print("=" * 60)
    print()
    print("当前架构已完整，下一步:")
    print("  1. 激活 langchain 环境: conda activate langchain")
    print("  2. 安装依赖: pip install -r requirements_langchain.txt")
    print("  3. 运行快速测试: python test_langchain_simple.py")
    print("  4. 启动应用: streamlit run langchain_app/app.py --server.port 8502")
    print()
    print("迁移计划文档: langchain_migration_plan.md")
    print()

except Exception as e:
    print(f"[ERROR] 验证失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
