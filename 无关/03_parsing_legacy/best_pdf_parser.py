#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最佳PDF解析方案 - 结合 MinerU + 规则 + LLM
在 pdf_work 环境中运行
"""

import os
import re
import json
import tempfile
import shutil
from pathlib import Path
from collections import defaultdict

# 导入你的现有模块
try:
    import pdf_md
    HAS_MINERU = True
except ImportError:
    HAS_MINERU = False
    print("警告: MinerU不可用，将使用pdfplumber备用方案")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


# ==================== 工具函数 ====================

def normalize_text(text):
    """规范化文本：统一空白、换行等"""
    if not text:
        return ""
    text = str(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_field_with_multi_patterns(text, patterns):
    """使用多个模式提取字段"""
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return normalize_text(match.group(1))
    return None


# ==================== MinerU 解析模块 ====================

def parse_with_mineru(pdf_path, output_dir="mineru_output"):
    """
    使用 MinerU 解析 PDF 为 MD (推荐方案)
    需要在 pdf_work 环境中运行
    """
    if not HAS_MINERU:
        return None, None

    pdf_path_obj = Path(pdf_path)
    file_name = pdf_path_obj.stem
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(exist_ok=True)

    try:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            safe_pdf = tdir / "input.pdf"
            shutil.copy2(pdf_path, safe_pdf)

            print(f"正在使用 MinerU 解析: {pdf_path}")
            pdf_md.parse_doc_md_only(
                path_list=[safe_pdf],
                output_dir=str(tdir),
                lang="ch",
                backend="hybrid-auto-engine",
                method="ocr"
            )

            md_path = tdir / f"input.md"
            if md_path.exists():
                md_content = md_path.read_text(encoding="utf-8", errors="ignore")
                output_md = output_dir_obj / f"{file_name}.md"
                output_md.write_text(md_content, encoding="utf-8")
                print(f"MinerU 解析完成，MD已保存至: {output_md}")
                return md_content, str(output_md)

    except Exception as e:
        print(f"MinerU 解析失败: {e}")

    return None, None


# ==================== pdfplumber 备用解析 ====================

def parse_with_pdfplumber(pdf_path):
    """
    使用 pdfplumber 作为备用方案
    """
    if not HAS_PDFPLUMBER:
        return None

    all_text = []
    all_tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
            tables = page.extract_tables()
            if tables:
                all_tables.extend(tables)

    return "\n".join(all_text), all_tables


# ==================== 证书属性提取 ====================

def extract_certificate_properties(text):
    """
    从文本中提取证书属性（适配你的JSON格式）
    """
    patterns = {
        "INSTRUMENT_NAME": [
            r"仪器名称\s*[：:]\s*([^\n]+)",
            r"设备名称\s*[：:]\s*([^\n]+)",
            r"产品名称\s*[：:]\s*([^\n]+)"
        ],
        "型号": [
            r"型号规格\s*[：:]\s*([^\n]+)",
            r"型号\s*[：:]\s*([^\n]+)"
        ],
        "制造厂": [
            r"制造商\s*[：:]\s*([^\n]+)",
            r"生产厂家\s*[：:]\s*([^\n]+)"
        ],
        "委托单位名称": [
            r"委托单位\s*[：:]\s*([^\n]+)",
            r"客户名称\s*[：:]\s*([^\n]+)"
        ],
        "客户地址": [
            r"委托方地址\s*[：:]\s*([^\n]+)",
            r"客户地址\s*[：:]\s*([^\n]+)"
        ],
        "管理号": [
            r"管理号\s*[：:]\s*([^\n]+)",
            r"设备编号\s*[：:]\s*([^\n]+)"
        ],
        "机身号": [
            r"机身号\s*[：:]\s*([^\n]+)",
            r"出厂编号\s*[：:]\s*([^\n]+)",
            r"序列号\s*[：:]\s*([^\n]+)"
        ],
        "证书编号": [
            r"证书编号\s*[：:]\s*([^\n]+)",
            r"证号\s*[：:]\s*([^\n]+)"
        ],
        "校准人": [
            r"校准\s*[：:]\s*([^\n]+)",
            r"Calibrated by\s*[：:]\s*([^\n]+)"
        ],
        "核验人": [
            r"核验\s*[：:]\s*([^\n]+)",
            r"Inspected by\s*[：:]\s*([^\n]+)"
        ],
        "签发人": [
            r"签发\s*[：:]\s*([^\n]+)",
            r"Approved by\s*[：:]\s*([^\n]+)"
        ],
        "温度": [
            r"温度\s*[：:]\s*([^\n]+)"
        ],
        "相对湿度": [
            r"相对湿度\s*[：:]\s*([^\n]+)"
        ],
        "签发日期": [
            r"签发日期\s*[：:]\s*([^\n]+)",
            r"报告日期\s*[：:]\s*([^\n]+)"
        ],
        "接收日期": [
            r"接收日期\s*[：:]\s*([^\n]+)",
            r"送检日期\s*[：:]\s*([^\n]+)"
        ],
        "校准日期": [
            r"校准日期\s*[：:]\s*([^\n]+)",
            r"检测日期\s*[：:]\s*([^\n]+)"
        ],
        "建议校准周期": [
            r"建议校准周期\s*[：:]\s*([^\n]+)"
        ],
        "校准地点": [
            r"校准地点\s*[：:]\s*([^\n]+)"
        ],
        "认可实验室": [
            r"认可实验室\s*[：:]\s*([^\n]+)"
        ],
        "证书结论": [
            r"结论\s*[：:]\s*([^\n]+)"
        ]
    }

    result = {}
    for field, field_patterns in patterns.items():
        result[field] = extract_field_with_multi_patterns(text, field_patterns)

    # 清理日期格式
    for date_field in ["签发日期", "校准日期", "接收日期"]:
        if result.get(date_field):
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", result[date_field])
            if date_match:
                result[date_field] = date_match.group(1)

    # 提取校准依据
    result["校准依据"] = []
    basis_patterns = [
        r"(JJF|JJG|GJB|GB/T|ISO|IEC)\s*[-—]?\s*\d+[^\n]*"
    ]
    for pattern in basis_patterns:
        matches = re.findall(pattern, text, re.I)
        for match in matches:
            full_match = re.search(pattern.replace("(JJF", "(JJF|"), text, re.I)
            if full_match:
                basis = normalize_text(full_match.group(0))
                if basis and basis not in result["校准依据"]:
                    result["校准依据"].append(basis)

    # CNAS标志检测
    result["是否CNAS"] = "是" if "CNAS" in text else "否"

    return result


# ==================== 依据参数_中间数据提取 ====================

def extract_middle_data(text, tables=None):
    """
    提取依据参数_中间数据
    """
    result = []

    # 1. 从文本中提取溯源声明相关数据
    traceability_patterns = [
        r"(计量溯源性声明|Metrological Traceability Declaration).*?(?=\n\n|\Z)",
        r"(溯源到|Traceability).*?(?=\n\n|\Z)",
        r"(标准器|Standard).*?(?=\n\n|\Z)"
    ]

    for pattern in traceability_patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.I)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            result.append({
                "测量值": "计量溯源性声明",
                "数据明细": {"内容": normalize_text(match)}
            })

    # 2. 从表格中提取数据
    if tables:
        for table_idx, table in enumerate(tables):
            if len(table) < 2:
                continue
            # 简单的表格数据提取
            for row_idx, row in enumerate(table):
                if not row or not any(cell for cell in row):
                    continue
                data_detail = {}
                for col_idx, cell in enumerate(row):
                    if cell:
                        data_detail[f"列{col_idx}"] = normalize_text(str(cell))
                if data_detail:
                    result.append({
                        "测量值": f"表格数据_{table_idx}_{row_idx}",
                        "数据明细": data_detail
                    })

    # 3. 提取包含数值和单位的数据
    measurement_patterns = [
        r"(\d+\.?\d*)\s*(MHz|GHz|kHz|Hz|dBm|dB|V|mV|A|mA|Ω|℃|%)",
        r"U(?:rel)?\s*=\s*[^\n]+"
    ]

    for pattern in measurement_patterns:
        matches = re.findall(pattern, text)
        for match in matches[:20]:  # 限制数量
            if isinstance(match, tuple):
                value = " ".join(match)
            else:
                value = match
            result.append({
                "测量值": normalize_text(value),
                "数据明细": {}
            })

    return result[:50]  # 限制最大条数


# ==================== 主解析函数 ====================

def parse_pdf_to_json(pdf_path, output_json_path=None):
    """
    最佳方案：MinerU → 规则解析 → JSON
    """
    pdf_path_obj = Path(pdf_path)

    if not pdf_path_obj.exists():
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    if output_json_path is None:
        output_json_path = pdf_path_obj.parent.parent / "local_json" / (pdf_path_obj.stem + ".json")
        output_json_path.parent.mkdir(exist_ok=True)

    # 步骤1: 尝试用 MinerU 解析
    md_content, md_path = parse_with_mineru(pdf_path)

    # 步骤2: 如果 MinerU 失败，用 pdfplumber
    text = ""
    tables = []
    if md_content:
        text = md_content
    else:
        print("使用 pdfplumber 作为备用方案")
        text, tables = parse_with_pdfplumber(pdf_path)

    if not text:
        raise RuntimeError("无法从PDF提取文本内容")

    # 步骤3: 提取证书属性
    properties = extract_certificate_properties(text)

    # 步骤4: 提取中间数据
    middle_data = extract_middle_data(text, tables)

    # 步骤5: 构建最终的JSON结构
    result = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        **properties,
                        "证书类型": "校准证书",
                        "证书状态": "正常",
                        "U_ATTR": None,
                        "专业": None,
                        "专业室": None,
                        "打印要求": [],
                        "客户要求": [],
                        "温度_内页": None,
                        "相对湿度_内页": None
                    }
                }
            }
        },
        "依据参数_中间数据": middle_data
    }

    # 保存JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n解析完成！结果已保存至: {output_json_path}")

    # 打印摘要
    props = result["properties"]["证书列表"]["items"]["properties"]
    print("\n=== 解析摘要 ===")
    print(f"仪器名称: {props.get('INSTRUMENT_NAME', 'N/A')}")
    print(f"型号: {props.get('型号', 'N/A')}")
    print(f"证书编号: {props.get('证书编号', 'N/A')}")
    print(f"校准依据: {props.get('校准依据', [])}")
    print(f"是否CNAS: {props.get('是否CNAS', 'N/A')}")
    print(f"依据参数_中间数据条数: {len(middle_data)}")

    return result


# ==================== 使用示例 ====================

def main():
    # 示例使用
    pdf_path = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\local_pdf\2GB24013527-0009.pdf"
    output_json = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\local_json\2GB24013527-0009_best.json"

    try:
        result = parse_pdf_to_json(pdf_path, output_json)
    except Exception as e:
        print(f"解析失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
