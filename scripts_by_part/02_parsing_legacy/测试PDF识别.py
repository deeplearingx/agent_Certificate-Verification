#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立测试脚本 - 测试 PDF → MD → JSON 转换流程
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

# 添加当前目录到路径
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

def check_dependencies():
    """检查依赖是否安装"""
    print("=" * 60)
    print("检查依赖...")
    print("=" * 60)

    missing = []

    try:
        import pdf_md
        print("✅ pdf_md - 可用")
    except ImportError as e:
        print(f"❌ pdf_md - 导入失败: {e}")
        missing.append("pdf_md")

    try:
        import md_parser
        print("✅ md_parser - 可用")
    except ImportError as e:
        print(f"❌ md_parser - 导入失败: {e}")
        missing.append("md_parser")

    try:
        from mineru.cli.common import prepare_env
        print("✅ MinerU - 可用")
    except ImportError as e:
        print(f"❌ MinerU - 导入失败: {e}")
        missing.append("MinerU (pdf_md 依赖)")

    try:
        from openai import OpenAI
        print("✅ OpenAI SDK - 可用")
    except ImportError as e:
        print(f"❌ OpenAI SDK - 导入失败: {e}")
        missing.append("openai")

    print()
    return missing


def check_api_key():
    """检查 API Key"""
    print("=" * 60)
    print("检查 API Key...")
    print("=" * 60)

    api_key = os.getenv("DEEPSEEK_API_KEY", "")

    if api_key:
        print(f"✅ DEEPSEEK_API_KEY 已设置 (长度: {len(api_key)})")
        return api_key
    else:
        print("❌ DEEPSEEK_API_KEY 未设置")
        print()
        print("请使用以下方式设置:")
        print("  Windows CMD:   set DEEPSEEK_API_KEY=你的密钥")
        print("  Windows PowerShell:  $env:DEEPSEEK_API_KEY=\"你的密钥\"")
        print("  Linux/Mac:   export DEEPSEEK_API_KEY=你的密钥")
        return None


def find_test_pdf():
    """查找测试 PDF 文件"""
    print("\n" + "=" * 60)
    print("查找测试文件...")
    print("=" * 60)

    # 可能的路径 - 新PDF文件
    possible_paths = [
        CURRENT_DIR / "pdf" / "时间和频率证书2026" / "GNSS导航信号采集回放仪" / "2GB24013527-0009.pdf",
        CURRENT_DIR / "pdf/时间和频率证书2026/GNSS导航信号采集回放仪/2GB24013527-0009.pdf",
        CURRENT_DIR / "2GB24013527-0009.pdf",
    ]

    for path in possible_paths:
        if path.exists():
            print(f"✅ 找到文件: {path}")
            return path

    print("❌ 未找到测试文件")
    print("\n请检查以下路径是否存在:")
    for path in possible_paths:
        print(f"  - {path}")
    return None


def test_pdf_to_md(pdf_path, output_dir):
    """测试 PDF → MD 转换"""
    print("\n" + "=" * 60)
    print("步骤 1/2: PDF → MD (MinerU)")
    print("=" * 60)

    import pdf_md

    tmpdir = tempfile.mkdtemp()

    try:
        print(f"正在解析: {pdf_path.name}")
        print(f"输出目录: {tmpdir}")

        pdf_md.parse_doc_md_only(
            path_list=[pdf_path],
            output_dir=tmpdir,
            lang="ch",
            backend="hybrid-auto-engine",
            method="ocr"
        )

        # 查找生成的 MD 文件
        md_files = list(Path(tmpdir).rglob("*.md"))

        if not md_files:
            print("❌ 未找到 MD 文件！")
            print(f"输出目录内容: {list(Path(tmpdir).iterdir())}")
            return None

        md_file = md_files[0]
        print(f"✅ MD 生成成功: {md_file}")
        print(f"   文件大小: {md_file.stat().st_size:,} 字节")

        # 复制到输出目录
        target_md = output_dir / f"{pdf_path.stem}.md"
        shutil.copy(md_file, target_md)

        print(f"   已复制到: {target_md}")

        # 显示预览
        print("\nMD 内容预览 (前 500 字符):")
        print("-" * 40)
        with open(md_file, encoding="utf-8") as f:
            preview = f.read(500)
            print(preview)
        print("-" * 40)

        return target_md

    except Exception as e:
        print(f"❌ PDF→MD 转换失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(tmpdir)
        except:
            pass


def test_md_to_json(md_path, output_dir, api_key):
    """测试 MD → JSON 转换"""
    print("\n" + "=" * 60)
    print("步骤 2/2: MD → JSON (DeepSeek LLM)")
    print("=" * 60)

    import md_parser

    try:
        print(f"正在解析: {md_path.name}")
        print(f"API 端点: https://api.deepseek.com/v1")

        json_path = md_parser.run_md_parsing(
            md_filename=md_path.name,
            base_dir=md_path.parent,
            out_dir=output_dir,
            api_key=api_key,
            api_base="https://api.deepseek.com/v1",
            model="deepseek-chat"
        )

        if not json_path:
            print("❌ JSON 生成失败！")
            return None

        print(f"✅ JSON 生成成功: {json_path}")

        # 读取并显示结果
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        properties = data.get("properties", {}).get("证书列表", {}).get("items", {}).get("properties", {})

        print("\n解析结果摘要:")
        print("-" * 40)

        # 统计字段
        total = len(properties)
        filled = sum(1 for v in properties.values() if v not in (None, "", []))
        print(f"总字段数: {total}")
        print(f"已填充: {filled} ({filled/total*100:.1f}%)")

        print("\n关键信息:")
        key_fields = ["INSTRUMENT_NAME", "型号", "制造厂", "证书编号", "温度", "相对湿度", "建议校准周期", "是否CNAS"]
        for field in key_fields:
            value = properties.get(field)
            if value:
                if isinstance(value, list):
                    value = ", ".join(value)
                print(f"  {field:15}: {value}")
            else:
                print(f"  {field:15}: ❌")

        # 参数表
        params = properties.get("依据参数_中间数据", [])
        if params:
            print(f"\n参数表行数: {len(params)}")
            for i, item in enumerate(params[:3], 1):
                print(f"  {i}. {item.get('项目名称', '未命名')}")

        print("-" * 40)
        return Path(json_path)

    except Exception as e:
        print(f"❌ MD→JSON 转换失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "PDF 校准证书识别测试工具" + " " * 22 + "║")
    print("╚" + "═" * 58 + "╝")

    # 准备输出目录 - 专门用于新PDF测试
    output_dir = CURRENT_DIR / "test_output_new"
    output_dir.mkdir(exist_ok=True)

    # 检查依赖
    missing = check_dependencies()
    if missing:
        print(f"\n❌ 缺少依赖: {', '.join(missing)}")
        print("请运行: pip install -r requirements.txt")
        return

    # 检查 API Key
    api_key = check_api_key()
    if not api_key:
        return

    # 查找测试文件
    pdf_path = find_test_pdf()
    if not pdf_path:
        return

    # 确认开始
    print("\n" + "=" * 60)
    print("准备就绪！")
    print("=" * 60)
    print(f"输出目录: {output_dir}")

    input("\n按回车键开始测试...")

    # 步骤1: PDF → MD
    md_path = test_pdf_to_md(pdf_path, output_dir)
    if not md_path:
        return

    # 步骤2: MD → JSON
    json_path = test_md_to_json(md_path, output_dir, api_key)
    if not json_path:
        return

    # 完成
    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print(f"\n生成的文件:")
    print(f"  MD:  {md_path}")
    print(f"  JSON: {json_path}")


if __name__ == "__main__":
    main()
