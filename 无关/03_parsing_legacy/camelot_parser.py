#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 Camelot 解析 PDF 表格（比 MinerU 更简单、更快）
需要安装：pip install camelot-py[cv] opencv-python
"""

import os
import json
import camelot
import pdfplumber
from pathlib import Path


def extract_tables_with_camelot(pdf_path):
    """使用 Camelot 提取表格"""
    try:
        print(f"正在使用 Camelot 提取表格: {pdf_path}")
        # lattice 模式适合有边框的表格，stream 模式适合无边框的
        tables = camelot.read_pdf(pdf_path, pages="all", flavor="lattice")
        print(f"成功提取 {len(tables)} 个表格")
        return tables
    except Exception as e:
        print(f"Camelot 失败，尝试 stream 模式: {e}")
        try:
            tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream")
            print(f"成功提取 {len(tables)} 个表格")
            return tables
        except Exception as e2:
            print(f"Stream 模式也失败: {e2}")
            return None


def extract_text_with_pdfplumber(pdf_path):
    """使用 pdfplumber 提取文本内容"""
    all_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        return "\n".join(all_text)
    except Exception as e:
        print(f"文本提取失败: {e}")
        return ""


def parse_cnas_with_camelot(pdf_path, output_json=None):
    """
    解析 CNAS 证书
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    # 1. 提取表格
    tables = extract_tables_with_camelot(str(pdf_path))

    # 2. 提取文本内容
    full_text = extract_text_with_pdfplumber(str(pdf_path))

    # 3. 解析基础属性
    from best_pdf_parser import extract_certificate_properties
    properties = extract_certificate_properties(full_text)

    # 4. 提取中间数据（表格数据）
    middle_data = []
    if tables:
        for table_idx, table in enumerate(tables):
            for row_idx, row in table.df.iterrows():
                row_data = {}
                for col_idx, value in enumerate(row):
                    if value:
                        # 使用列名（如果有）作为 key，否则用 列{idx}
                        col_name = str(table.df.columns[col_idx]) if col_idx < len(table.df.columns) else f"列{col_idx}"
                        row_data[col_name] = value.strip()
                if row_data:
                    middle_data.append({
                        "测量值": f"表格{table_idx}_行{row_idx}",
                        "数据明细": row_data
                    })

    # 5. 构建最终结构
    result = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": properties
                }
            }
        },
        "依据参数_中间数据": middle_data
    }

    # 6. 保存结果
    if output_json is None:
        output_json = Path("local_json") / f"{pdf_path.stem}_camelot.json"
        output_json.parent.mkdir(exist_ok=True)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"解析完成！结果已保存至: {output_json}")
    return result


# ============ 使用示例 ============

if __name__ == "__main__":
    # 检测是否安装了 Camelot
    try:
        import camelot
        print("Camelot 已安装 ✅")
    except ImportError:
        print("Camelot 未安装，正在尝试安装...")
        try:
            os.system("pip install camelot-py[cv] opencv-python")
            import camelot
        except Exception as e:
            print(f"安装失败: {e}")
            print("建议在 conda 环境中安装: conda install -c conda-forge camelot-py")

    pdf_path = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\local_pdf\2GB24013527-0009.pdf"
    output_json = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\local_json\2GB24013527-0009_camelot.json"

    try:
        parse_cnas_with_camelot(pdf_path, output_json)
    except Exception as e:
        print(f"解析失败: {e}")
        import traceback
        traceback.print_exc()
