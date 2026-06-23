#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试新PDF文件 - 非交互式版本
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
            for i, item in enumerate(params[:5], 1):
                print(f"  {i}. {item.get('项目名称', '未命名')}")
                details = item.get("数据明细", {})
                for k, v in list(details.items())[:3]:
                    print(f"      {k}: {v}")

        print("-" * 40)
        return Path(json_path)

    except Exception as e:
        print(f"❌ MD→JSON 转换失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " " * 12 + "新PDF校准证书识别测试" + " " * 24 + "║")
    print("╚" + "═" * 58 + "╝")

    # 准备输出目录
    output_dir = CURRENT_DIR / "test_output_new"
    output_dir.mkdir(exist_ok=True)

    # 检查 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY 未设置")
        return
    print(f"✅ DEEPSEEK_API_KEY 已设置 (长度: {len(api_key)})")

    # PDF文件路径
    pdf_path = CURRENT_DIR / "pdf" / "时间和频率证书2026" / "GNSS导航信号采集回放仪" / "2GB24013527-0009.pdf"
    if not pdf_path.exists():
        print(f"❌ PDF文件不存在: {pdf_path}")
        return
    print(f"✅ 找到PDF文件: {pdf_path}")

    # 检查是否已有MD文件
    md_path = output_dir / (pdf_path.stem + ".md")
    if md_path.exists():
        print(f"\n✅ MD文件已存在，跳过PDF→MD转换")
    else:
        # 步骤1: PDF → MD
        md_path = test_pdf_to_md(pdf_path, output_dir)
        if not md_path:
            return

    # 检查是否已有JSON文件
    json_path = output_dir / (pdf_path.stem + ".json")
    if json_path.exists():
        print(f"\n✅ JSON文件已存在，跳过MD→JSON转换")
    else:
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
