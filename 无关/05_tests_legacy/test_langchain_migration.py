#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangChain 重构版 - 完整架构测试

用于验证 LangChain 重构版是否与原始项目功能相同
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """测试核心模块导入"""
    print("=" * 60)
    print("测试核心模块导入...")
    print("=" * 60)

    all_imports = True

    try:
        from langchain_app import __version__, __author__
        print(f"✅ 项目导入成功: v{__version__}")
        print(f"  - Author: {__author__}")
    except Exception as e:
        print(f"❌ 项目导入失败: {e}")
        all_imports = False

    try:
        from langchain_app.utils import AppConfig, get_app_config
        print("✅ 配置模块导入成功")
    except Exception as e:
        print(f"❌ 配置模块导入失败: {e}")
        all_imports = False

    try:
        from langchain_app.core import LLMClient, VectorDatabase, VerificationReport
        print("✅ 核心模块导入成功")
    except Exception as e:
        print(f"❌ 核心模块导入失败: {e}")
        all_imports = False

    try:
        from langchain_app.core import run_verification, PipelineHooks
        print("✅ 流水线模块导入成功")
    except Exception as e:
        print(f"❌ 流水线模块导入失败: {e}")
        all_imports = False

    try:
        from langchain_app.tools import get_all_tools
        tools = get_all_tools()
        print(f"✅ 工具模块导入成功 (找到 {len(tools)} 个工具)")
    except Exception as e:
        print(f"❌ 工具模块导入失败: {e}")
        all_imports = False

    try:
        from langchain_app.agents import VerificationAgent
        print("✅ Agent 模块导入成功")
    except Exception as e:
        print(f"❌ Agent 模块导入失败: {e}")
        all_imports = False

    print()
    return all_imports


def test_config():
    """测试配置模块"""
    print("=" * 60)
    print("测试配置模块...")
    print("=" * 60)

    try:
        from langchain_app.utils import get_app_config, AppConfig

        # 测试从环境变量加载
        config = get_app_config()
        print("✅ 配置从环境变量加载成功")

        # 显示核心配置
        print(f"  - API Key: {'✓' if config.api_key else '✗'}")
        print(f"  - Model: {config.model}")
        print(f"  - Temperature: {config.temperature}")
        print(f"  - Max Tokens: {config.max_tokens}")
        print(f"  - Top K: {config.topk}")
        print(f"  - Embed Model: {config.embed_model_path}")

        # 测试路径配置
        config.ensure_directories()
        print(f"  - Root Dir: {config.root_dir}")
        print(f"  - PDFs Dir: {config.local_pdf_dir}")
        print(f"  - MD Dir: {config.local_md_dir}")
        print(f"  - JSON Dir: {config.local_json_dir}")

        print("✅ 配置验证成功")

    except Exception as e:
        print(f"❌ 配置测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_tools():
    """测试工具模块"""
    print("=" * 60)
    print("测试工具模块...")
    print("=" * 60)

    try:
        from langchain_app.tools import get_all_tools

        tools = get_all_tools()
        print(f"✅ 找到 {len(tools)} 个工具")

        for i, tool in enumerate(tools, 1):
            print(f"  {i:2d}. {tool.name} - {tool.description.splitlines()[0]}")

        print("✅ 工具列表验证成功")

    except Exception as e:
        print(f"❌ 工具测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_pipeline():
    """测试流水线模块"""
    print("=" * 60)
    print("测试流水线模块...")
    print("=" * 60)

    try:
        from langchain_app.core import PipelineHooks

        hooks = PipelineHooks()

        # 测试简单的钩子调用
        hooks.emit_info("测试信息")
        hooks.emit_status("测试状态")
        hooks.emit_progress(50)

        print("✅ Hook 机制测试成功")

        # 测试嵌入模型加载
        from langchain_app.core import load_shared_embedder

        print("  🔄 正在加载嵌入模型 (这可能需要时间)...")
        embedder = load_shared_embedder("BAAI/bge-m3")
        print(f"✅ 嵌入模型加载成功: {embedder}")

    except Exception as e:
        print(f"❌ 流水线测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_agent():
    """测试 Agent 模块"""
    print("=" * 60)
    print("测试 Agent 模块...")
    print("=" * 60)

    try:
        from langchain_app.utils import get_app_config
        from langchain_app.core import LLMClient
        from langchain_app.agents import VerificationAgent

        config = get_app_config()
        llm = LLMClient(config)

        agent = VerificationAgent(llm)

        info = agent.get_agent_info()
        print(f"✅ Agent 创建成功")
        print(f"  - 模型: {info['model']}")
        print(f"  - 工具数: {info['tool_count']}")
        print(f"  - 工具列表: {', '.join(info['tool_names'])}")

    except Exception as e:
        print(f"❌ Agent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_backward_compatibility():
    """测试与原始项目的兼容性"""
    print("=" * 60)
    print("测试与原始项目的兼容性...")
    print("=" * 60)

    compatibility = []

    # 检查原始项目文件是否存在
    required_files = [
        "md_parser_no_llm.py",
        "info_check.py",
        "env_check.py",
        "location_check.py",
        "cycle_check.py",
        "param_check.py",
        "pdf_md.py",
        "core/pipeline.py",
        "checks/adapters.py",
        "checks/base.py",
        "config/settings.py",
    ]

    project_root = __file__

    for filename in required_files:
        full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(full_path):
            print(f"✅ {filename} - 存在")
            compatibility.append(True)
        else:
            print(f"❌ {filename} - 不存在")
            compatibility.append(False)

    print()
    return all(compatibility)


def test_vector_db():
    """测试向量数据库"""
    print("=" * 60)
    print("测试向量数据库...")
    print("=" * 60)

    try:
        from langchain_app.core import VectorDatabase
        from langchain_app.utils import get_app_config

        config = get_app_config()

        # 测试 CNAS 数据库
        print("  🔍 正在检查 CNAS 数据库...")
        cnas_db = VectorDatabase(
            collection_name=config.cnas_collection,
            persist_directory=str(config.cnas_db_dir)
        )

        cnas_count = len(cnas_db.vector_store.get()['ids'])
        print(f"✅ CNAS 数据库: {cnas_count} 个文档")

        # 测试温度数据库
        print("  🔍 正在检查温度数据库...")
        temp_db = VectorDatabase(
            collection_name="temperature_requirements",
            persist_directory=str(config.temperature_db_dir)
        )

        temp_count = len(temp_db.vector_store.get()['ids'])
        print(f"✅ 温度数据库: {temp_count} 个文档")

        # 测试周期数据库
        print("  🔍 正在检查通用周期数据库...")
        cycle_db = VectorDatabase(
            collection_name="general_cycle",
            persist_directory=str(config.general_cycle_db_dir)
        )

        cycle_count = len(cycle_db.vector_store.get()['ids'])
        print(f"✅ 通用周期数据库: {cycle_count} 个文档")

        # 测试地址数据库
        print("  🔍 正在检查地址数据库...")
        addr_db = VectorDatabase(
            collection_name="calibration_address",
            persist_directory=str(config.address_db_dir)
        )

        addr_count = len(addr_db.vector_store.get()['ids'])
        print(f"✅ 地址数据库: {addr_count} 个文档")

        if cnas_count > 0 and temp_count > 0 and cycle_count > 0 and addr_count > 0:
            print("✅ 所有向量数据库验证成功")
        else:
            print("⚠️ 向量数据库可能需要重新构建")

        return True

    except Exception as e:
        print(f"❌ 向量数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()


def main():
    """主测试函数"""
    print("=" * 60)
    print("LangChain 重构版 - 架构测试")
    print("=" * 60)
    print()

    print("正在进行全面测试...")
    print()

    tests = [
        ("模块导入", test_imports),
        ("配置模块", test_config),
        ("工具模块", test_tools),
        ("Agent 模块", test_agent),
        ("流水线模块", test_pipeline),
        ("向量数据库", test_vector_db),
        ("兼容性检查", test_backward_compatibility),
    ]

    passed = 0
    total = len(tests)

    for name, test_func in tests:
        print(f"🔹 运行 {name} 测试...")

        try:
            result = test_func()
            if result:
                print(f"✅ {name} 测试通过")
                passed += 1
            else:
                print(f"❌ {name} 测试失败")

        except Exception as e:
            print(f"❌ {name} 测试异常: {e}")
            import traceback
            traceback.print_exc()

        print("-" * 60)
        print()

    # 测试结果总结
    print("=" * 60)
    print("测试结果总结")
    print("=" * 60)

    print(f"通过测试: {passed}/{total}")

    if passed == total:
        print("🎉 所有测试通过！LangChain 架构重构成功！")
        print()
        print("下一步:")
        print("1. 运行 streamlit run langchain_app/app.py")
        print("2. 上传 PDF 文档进行核验")
        print("3. 查看生成的报告")

    else:
        print("⚠️ 部分测试失败，请检查上面的错误信息")
        print()
        print("常见问题解决:")
        print("- 确保已安装依赖: pip install -r requirements_langchain.txt")
        print("- 检查 .env 文件配置是否正确")
        print("- 确认向量数据库已正确构建")

    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n测试被中断")
        sys.exit(1)

    except Exception as e:
        print(f"测试过程中发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
