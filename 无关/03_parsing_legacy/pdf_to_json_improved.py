#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改进的PDF解析方案 - 结合pdfplumber和Mineru的优势
"""

import os
import re
import json
from pathlib import Path
import pdfplumber

# 尝试导入mineru（如果有）
try:
    from pdf_md import parse_doc_md_only
    HAS_MINERU = True
except ImportError:
    HAS_MINERU = False


def extract_field(text, patterns):
    """
    使用多个正则表达式模式提取字段，提高匹配成功率
    """
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            # 清理值（去除多余的空格、换行等）
            value = re.sub(r'\s+', ' ', value)
            return value
    return None


def parse_pdf_with_pdfplumber(pdf_path):
    """
    使用pdfplumber解析PDF - 轻量级方案
    """
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

    full_text = "\n".join(all_text)

    # 通用字段提取模式 - 支持中英文
    field_patterns = {
        "INSTRUMENT_NAME": [
            r"仪器名称\s*[：:]\s*([^\n]+)",
            r"设备名称\s*[：:]\s*([^\n]+)",
            r"产品名称\s*[：:]\s*([^\n]+)",
            r"名称\s*[：:]\s*([^\n]+)",
            r"Description\s*[：:]\s*([^\n]+)"
        ],
        "型号": [
            r"型号规格\s*[：:]\s*([^\n]+)",
            r"型号\s*[：:]\s*([^\n]+)",
            r"Model\s*[：:]\s*([^\n]+)"
        ],
        "制造厂": [
            r"制造商\s*[：:]\s*([^\n]+)",
            r"生产厂家\s*[：:]\s*([^\n]+)",
            r"Manufacturer\s*[：:]\s*([^\n]+)"
        ],
        "委托单位名称": [
            r"委托单位\s*[：:]\s*([^\n]+)",
            r"客户名称\s*[：:]\s*([^\n]+)",
            r"送检单位\s*[：:]\s*([^\n]+)",
            r"Client\s*[：:]\s*([^\n]+)"
        ],
        "证书编号": [
            r"证书编号\s*[：:]\s*([^\n]+)",
            r"证号\s*[：:]\s*([^\n]+)",
            r"Certificate No.\s*[：:]\s*([^\n]+)"
        ],
        "校准人": [
            r"校准\s*[：:]\s*([^\n]+)",
            r"校验员\s*[：:]\s*([^\n]+)",
            r"Calibrated by\s*[：:]\s*([^\n]+)"
        ],
        "核验人": [
            r"核验\s*[：:]\s*([^\n]+)",
            r"复核人\s*[：:]\s*([^\n]+)",
            r"Inspected by\s*[：:]\s*([^\n]+)"
        ],
        "签发人": [
            r"签发\s*[：:]\s*([^\n]+)",
            r"批准人\s*[：:]\s*([^\n]+)",
            r"Approved by\s*[：:]\s*([^\n]+)"
        ],
        "签发日期": [
            r"签发日期\s*[：:]\s*([^\n]+)",
            r"报告日期\s*[：:]\s*([^\n]+)",
            r"App\. Date\s*[：:]\s*([^\n]+)"
        ],
        "校准日期": [
            r"校准日期\s*[：:]\s*([^\n]+)",
            r"检测日期\s*[：:]\s*([^\n]+)",
            r"Cal\. Date\s*[：:]\s*([^\n]+)"
        ],
        "接收日期": [
            r"接收日期\s*[：:]\s*([^\n]+)",
            r"送检日期\s*[：:]\s*([^\n]+)",
            r"Rec\. Date\s*[：:]\s*([^\n]+)"
        ],
        "校准依据": [
            r"校准依据\s*[：:]\s*([^\n]+)",
            r"依据标准\s*[：:]\s*([^\n]+)",
            r"Reference Standard\s*[：:]\s*([^\n]+)"
        ],
        "建议校准周期": [
            r"建议校准周期\s*[：:]\s*([^\n]+)",
            r"校准周期\s*[：:]\s*([^\n]+)",
            r"Reference Cal\. Period\s*[：:]\s*([^\n]+)"
        ]
    }

    # 提取属性字段
    properties = {}
    for field_name, patterns in field_patterns.items():
        properties[field_name] = extract_field(full_text, patterns)

    # 处理日期字段 - 提取标准格式的日期
    for date_field in ["签发日期", "校准日期", "接收日期"]:
        if properties.get(date_field):
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", properties[date_field])
            if date_match:
                properties[date_field] = date_match.group(1)

    # 提取校准依据（支持多个标准）
    calibration_basis = []
    basis_patterns = [
        r"JJF\s*\d+-\d+[^\n]*",
        r"JJG\s*\d+-\d+[^\n]*",
        r"GJB\s*\d+-\d+[^\n]*",
        r"GB/T\s*\d+-\d+[^\n]*",
        r"IEC\s*\d+[^\n]*",
        r"ISO\s*\d+[^\n]*"
    ]

    for pattern in basis_patterns:
        matches = re.findall(pattern, full_text)
        for match in matches:
            match = re.sub(r"\s+", " ", match.strip())
            if match and match not in calibration_basis:
                calibration_basis.append(match)

    # 提取是否CNAS认可
    is_cnas = "是" if "CNAS" in full_text else "否"

    # 提取依据参数_中间数据（从表格和文本中提取）
    middle_data = extract_middle_data(full_text, all_tables)

    # 构建最终的JSON结构
    result = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        **properties,
                        "校准依据": calibration_basis,
                        "是否CNAS": is_cnas,
                        "证书类型": "校准证书",
                        "证书状态": "正常",
                        "客户地址": None,
                        "管理号": None,
                        "机身号": None,
                        "温度": None,
                        "相对湿度": None,
                        "温度_内页": None,
                        "相对湿度_内页": None,
                        "认可实验室": None,
                        "证书结论": None,
                        "U_ATTR": None,
                        "专业": None,
                        "专业室": None,
                        "打印要求": [],
                        "客户要求": [],
                        "校准地点": []
                    }
                }
            }
        },
        "依据参数_中间数据": middle_data
    }

    return result


def extract_middle_data(text, tables):
    """
    从文本和表格中提取依据参数_中间数据
    """
    result = []

    # 1. 从表格中提取数据
    for table_idx, table in enumerate(tables):
        for row_idx, row in enumerate(table):
            if row and len(row) > 1:
                # 提取有意义的数据行
                meaningful_cells = [cell.strip() for cell in row if cell and cell.strip()]
                if len(meaningful_cells) >= 2:
                    result.append({
                        "测量值": f"表格数据_{table_idx}_{row_idx}",
                        "数据明细": {
                            f"列{idx}": cell for idx, cell in enumerate(meaningful_cells)
                        }
                    })

    # 2. 从文本中提取测量数据
    # 提取包含数值和单位的数据
    measurement_patterns = [
        r"(\d+\.?\d*)\s*(MHz|GHz|kHz|Hz|dBm|dB|V|A|W|Ω|℃|%)",
        r"([-+]?\d+\.?\d*)\s*([-+]?\d+\.?\d*)\s*([-+]?\d+\.?\d*)",
        r"标准值\s*[：:]\s*([^\n]+)",
        r"测量值\s*[：:]\s*([^\n]+)",
        r"误差\s*[：:]\s*([^\n]+)",
        r"极限\s*[：:]\s*([^\n]+)"
    ]

    for pattern in measurement_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple):
                value = " ".join([str(x) for x in match if x])
            else:
                value = match
            result.append({
                "测量值": value,
                "数据明细": {}
            })

    return result


def parse_with_mineru(pdf_path, output_dir="output"):
    """
    使用Mineru进行高级解析（需要在pdf_work环境中运行）
    """
    if not HAS_MINERU:
        return None

    try:
        from pathlib import Path
        pdf_path_obj = Path(pdf_path)
        file_name = pdf_path_obj.stem

        # 创建输出目录
        output_dir_obj = Path(output_dir)
        output_dir_obj.mkdir(exist_ok=True)

        # 调用Mineru解析
        parse_doc_md_only(
            path_list=[pdf_path_obj],
            output_dir=str(output_dir_obj),
            lang="ch",
            backend="hybrid-auto-engine",
            method="ocr"
        )

        md_path = output_dir_obj / f"{file_name}.md"
        if md_path.exists():
            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            return {
                "mineru_output": {
                    "md_path": str(md_path),
                    "md_content": md_content[:500] + "..." if len(md_content) > 500 else md_content
                }
            }
        else:
            print(f"Mineru解析失败，未找到生成的MD文件: {md_path}")
            return None

    except Exception as e:
        print(f"Mineru解析失败: {e}")
        return None


def main():
    """主函数"""
    pdf_path = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\local_pdf\2GB24013527-0009.pdf"
    output_path = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\local_json\2GB24013527-0009_improved.json"

    print("正在解析PDF文件...")
    result = parse_pdf_with_pdfplumber(pdf_path)

    # 尝试使用Mineru解析（可选）
    # mineru_result = parse_with_mineru(pdf_path)
    # if mineru_result:
    #     result["mineru_info"] = mineru_result

    # 保存为JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"解析完成！结果已保存至: {output_path}")
    print("\n解析的主要字段:")
    print(f"仪器名称: {result['properties']['证书列表']['items']['properties']['INSTRUMENT_NAME']}")
    print(f"型号: {result['properties']['证书列表']['items']['properties']['型号']}")
    print(f"证书编号: {result['properties']['证书列表']['items']['properties']['证书编号']}")
    print(f"校准依据: {result['properties']['证书列表']['items']['properties']['校准依据']}")
    print(f"是否CNAS: {result['properties']['证书列表']['items']['properties']['是否CNAS']}")
    print(f"依据参数_中间数据条数: {len(result['依据参数_中间数据'])}")


if __name__ == "__main__":
    main()
