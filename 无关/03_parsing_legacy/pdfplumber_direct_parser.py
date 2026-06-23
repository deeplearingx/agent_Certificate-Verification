#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接使用 pdfplumber 解析 PDF 为您需要的 JSON 格式
"""

import pdfplumber
import re
import json
from pathlib import Path

PDF_PATH = r"D:\workspace\ai大模型开发课\文档核验\document-verification-master\local_pdf\2GB24013527-0009.pdf"
OUTPUT_JSON = r"D:\workspace\ai大模型开发课\文档核验\document-verification-master\local_json\2GB24013527-0009.json"


def extract_field(text, pattern):
    """使用正则表达式从文本中提取字段"""
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def parse_2GB24013527_0009(pdf_path):
    """解析特定格式的证书"""
    all_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)

    full_text = "\n".join(all_text)

    # 提取字段
    data = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        "INSTRUMENT_NAME": extract_field(full_text, r"仪器名称\s*[：:]\s*([^\n]+)"),
                        "型号": extract_field(full_text, r"型号规格\s*[：:]\s*([^\n]+)"),
                        "制造厂": extract_field(full_text, r"制造商\s*[：:]\s*([^\n]+)"),
                        "委托单位名称": extract_field(full_text, r"委托单位\s*[：:]\s*([^\n]+)"),
                        "客户地址": extract_field(full_text, r"委托方地址\s*[：:]\s*([^\n]+)"),
                        "管理号": extract_field(full_text, r"管理号\s*[：:]\s*([^\n]+)"),
                        "机身号": extract_field(full_text, r"机身号\s*[：:]\s*([^\n]+)"),
                        "证书编号": extract_field(full_text, r"证书编号\s*[：:]\s*([^\n]+)"),
                        "校准人": extract_field(full_text, r"校准\s*[：:]\s*([^\n]+)"),
                        "核验人": None,
                        "签发人": extract_field(full_text, r"签发\s*[：:]\s*([^\n]+)"),
                        "校准依据": extract_calibration_basis(full_text),
                        "温度": extract_field(full_text, r"温度\s*[：:]\s*([^\n]+)"),
                        "相对湿度": extract_field(full_text, r"相对湿度\s*[：:]\s*([^\n]+)"),
                        "签发日期": extract_field(full_text, r"签发日期\s*[：:]\s*([^\n]+)"),
                        "接收日期": extract_field(full_text, r"接收日期\s*[：:]\s*([^\n]+)"),
                        "校准日期": extract_field(full_text, r"校准日期\s*[：:]\s*([^\n]+)"),
                        "证书类型": "校准证书",
                        "证书状态": "正常",
                        "认可实验室": extract_field(full_text, r"认可实验室\s*[：:]\s*([^\n]+)") or extract_field(full_text, r"中国赛宝实验室.*检测中心"),
                        "证书结论": extract_field(full_text, r"结论\s*[：:]\s*([^\n]+)"),
                        "是否CNAS": "是" if "CNAS" in full_text else "否",
                        "U_ATTR": None,
                        "专业": None,
                        "专业室": None,
                        "打印要求": [],
                        "客户要求": [],
                        "校准地点": [extract_field(full_text, r"校准地点\s*[：:]\s*([^\n]+)")],
                        "建议校准周期": extract_field(full_text, r"建议校准周期\s*[：:]\s*([^\n]+)"),
                        "温度_内页": None,
                        "相对湿度_内页": None,
                        "依据参数_中间数据": []
                    }
                }
            }
        }
    }

    return data


def extract_calibration_basis(text):
    """提取校准依据"""
    patterns = [
        r"JJF\d+-\d+[^\n]*",
        r"JJG\d+-\d+[^\n]*",
        r"GJB\d+-\d+[^\n]*",
        r"GB/T\d+-\d+[^\n]*"
    ]

    basis = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            match = match.strip()
            if match and match not in basis:
                basis.append(match)

    return basis


if __name__ == "__main__":
    pdf_path = Path(PDF_PATH)
    if not pdf_path.exists():
        print(f"PDF文件不存在: {PDF_PATH}")
        # 尝试从其他位置查找
        other_paths = [
            r"D:\workspace\ai大模型开发课\文档核验\document-verification-master\pdf\时间和频率证书2026\脉冲分配放大器\2GB24013527-0009.pdf",
            r"D:\workspace\ai大模型开发课\文档核验\document-verification-master\pdf\2GB24013527-0009.pdf"
        ]
        for p in other_paths:
            if Path(p).exists():
                PDF_PATH = p
                break
        else:
            print("未找到目标PDF文件")
            exit(1)

    print(f"正在解析: {PDF_PATH}")
    data = parse_2GB24013527_0009(PDF_PATH)
    print("解析成功！")

    # 保存为 JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"JSON已保存至: {OUTPUT_JSON}")

    # 打印关键信息
    print("\n提取的关键信息:")
    props = data["properties"]["证书列表"]["items"]["properties"]
    key_fields = ["INSTRUMENT_NAME", "型号", "制造厂", "证书编号", "校准人", "签发人"]
    for field in key_fields:
        value = props.get(field, None)
        if value:
            print(f"{field}: {value}")
        else:
            print(f"{field}: N/A")

    print(f"校准依据: {props.get('校准依据', [])}")
    print(f"是否CNAS: {props.get('是否CNAS')}")
