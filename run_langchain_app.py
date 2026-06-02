#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangChain 重构版 - 简单运行脚本

用于快速测试和启动应用
"""

import sys
import os
import subprocess

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def run_quick_test():
    """快速测试"""
    try:
        print("=" * 60)
        print("快速测试")
        print("=" * 60)

        # 测试导入
        from langchain_app import __version__
        print(f"✅ LangChain App v{__version__} 导入成功")

        from langchain_app.utils import get_app_config
        config = get_app_config()
        config.ensure_directories()
        print(f"✅ 配置加载成功 (API Key: {'✓' if config.api_key else '✗'})")

        from langchain_app.tools import get_all_tools
        tools = get_all_tools()
        print(f"✅ 找到 {len(tools)} 个工具")

        print()
        print("=" * 60)
        print("环境检查通过！")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_app():
    """运行应用"""
    try:
        print()
        print("=" * 60)
        print("启动 Streamlit 应用")
        print("=" * 60)

        command = [
            "streamlit",
            "run",
            os.path.join(project_root, "langchain_app", "app.py"),
            "--server.port",
            "8502"
        ]

        subprocess.run(command, check=True)

    except KeyboardInterrupt:
        print("\n应用被中断")
        return False

    except Exception as e:
        print(f"❌ 启动应用失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def run_migration_test():
    """运行完整迁移测试"""
    print("=" * 60)
    print("运行完整迁移测试")
    print("=" * 60)

    try:
        subprocess.run(
            [sys.executable, "test_langchain_migration.py"],
            check=True,
            text=True
        )
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    """主函数"""
    print("LangChain 重构版 - 智能文档核验系统")
    print()

    print("请选择操作:")
    print("1. 快速测试")
    print("2. 完整迁移测试")
    print("3. 启动应用")
    print("4. 帮助")

    choice = input("\n输入选项 (1-4): ").strip()

    if choice == "1":
        if run_quick_test():
            print("\n✅ 准备就绪！")
        return

    elif choice == "2":
        if run_migration_test():
            print("✅ 所有测试通过！")
        else:
            print("❌ 部分测试失败")
        return

    elif choice == "3":
        return run_app()

    elif choice == "4":
        print("\n使用说明:")
        print()
        print("1. 确保已安装依赖:")
        print("   pip install -r requirements_langchain.txt")
        print()
        print("2. 配置环境变量 (可选，通过 .env 文件):")
        print("   DEEPSEEK_API_KEY=your-api-key")
        print("   LLM_MODEL=deepseek-chat")
        print()
        print("3. 运行方式:")
        print("   - 快速测试: python run_langchain_app.py 1")
        print("   - 完整测试: python run_langchain_app.py 2")
        print("   - 启动应用: python run_langchain_app.py 3")
        print()
        print("4. 应用功能:")
        print("   - 文档上传")
        print("   - PDF解析")
        print("   - 信息完整性核验")
        print("   - 环境条件核验")
        print("   - 校准地点核验")
        print("   - 校准周期核验")
        print("   - 参数与不确定度核验")
        return

    else:
        print(f"❌ 无效选项: {choice}")
        return


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n应用被中断")
        sys.exit(0)
