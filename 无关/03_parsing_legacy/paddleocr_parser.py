#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用PaddleOCR的CNAS校准证书解析器
"""

import os
import json
from pathlib import Path
import paddleocr
from PIL import Image
import io
import fitz  # PyMuPDF
import re

# 初始化PaddleOCR - 使用中英文模型
def init_ocr():
    try:
        # 使用CPU推理
        ocr = paddleocr.PaddleOCR(
            use_angle_cls=True,
            lang="ch"
        )
        return ocr
    except Exception as e:
        print(f"初始化PaddleOCR失败: {e}")
        return None


def pdf_to_images(pdf_path, dpi=300):
    """将PDF页面转换为高质量图像"""
    images = []
    try:
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            page = doc.load_page(i)
            # 转换为图像
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
        doc.close()
        print(f"成功将PDF转换为 {len(images)} 页图像")
    except Exception as e:
        print(f"PDF转图像失败: {e}")
    return images


def extract_text_with_ocr(images, ocr):
    """使用PaddleOCR提取所有文本和表格"""
    all_texts = []
    all_results = []

    for i, img in enumerate(images):
        print(f"正在识别第 {i+1} 页...")
        try:
            # OCR识别
            result = ocr.ocr(img, cls=True)

            if result and result[0]:
                # 提取文本
                page_texts = []
                page_result = []

                for line in result[0]:
                    text = line[1][0]
                    coords = line[0]
                    score = line[1][1]
                    page_texts.append(text)
                    page_result.append({
                        "text": text,
                        "bbox": coords,
                        "confidence": score
                    })

                all_texts.append("\n".join(page_texts))
                all_results.append(page_result)
                print(f"  提取到文本: {len(page_texts)} 行")
        except Exception as e:
            print(f"第 {i+1} 页识别失败: {e}")
            all_texts.append("")
            all_results.append([])

    return all_texts, all_results


def extract_properties(text, page_results, pdf_path):
    """从OCR结果中提取属性字段"""
    properties = {
        "证书编号": None,
        "委托单位": None,
        "委托方地址": None,
        "仪器名称": None,
        "型号规格": None,
        "制造商": None,
        "机身号": None,
        "管理号": None,
        "接收日期": None,
        "签发日期": None,
        "签发人": None,
        "核验人": None,
        "校准人": None,
        "温度": None,
        "湿度": None,
        "认可实验室": None,
        "CNAS": None,
        "是否CNAS": "是" if "CNAS" in text else "否",
        "校准依据": [],
        "结论": None,
        "证书类型": "校准证书",
        "证书状态": "正常",
    }

    # 提取证书编号
    cert_patterns = [
        r'证书编号\s*[：:]\s*([^\n]+)',
        r'证号\s*[：:]\s*([^\n]+)',
        r'CNAS\s*L?(\d+)\s*',
        r'L(\d{5})',
    ]
    for pattern in cert_patterns:
        match = re.search(pattern, text)
        if match:
            properties["证书编号"] = match.group(1).strip()
            break

    # 提取委托单位
    client_patterns = [
        r'委托单位\s*[：:]\s*([^\n]+)',
        r'客户名称\s*[：:]\s*([^\n]+)',
        r'送检单位\s*[：:]\s*([^\n]+)',
        r'委托单位名称\s*[：:]\s*([^\n]+)',
    ]
    for pattern in client_patterns:
        match = re.search(pattern, text)
        if match:
            properties["委托单位"] = match.group(1).strip()
            break

    # 提取委托方地址
    address_patterns = [
        r'委托方地址\s*[：:]\s*([^\n]+)',
        r'客户地址\s*[：:]\s*([^\n]+)',
    ]
    for pattern in address_patterns:
        match = re.search(pattern, text)
        if match:
            properties["委托方地址"] = match.group(1).strip()
            break

    # 提取仪器信息
    instrument_patterns = [
        r'仪器名称\s*[：:]\s*([^\n]+)',
        r'设备名称\s*[：:]\s*([^\n]+)',
        r'INSTRUMENT_NAME\s*[：:]\s*([^\n]+)',
    ]
    for pattern in instrument_patterns:
        match = re.search(pattern, text)
        if match:
            properties["仪器名称"] = match.group(1).strip()
            break

    model_patterns = [
        r'型号规格\s*[：:]\s*([^\n]+)',
        r'型号\s*[：:]\s*([^\n]+)',
    ]
    for pattern in model_patterns:
        match = re.search(pattern, text)
        if match:
            properties["型号规格"] = match.group(1).strip()
            break

    manufacturer_patterns = [
        r'制造商\s*[：:]\s*([^\n]+)',
        r'制造厂\s*[：:]\s*([^\n]+)',
    ]
    for pattern in manufacturer_patterns:
        match = re.search(pattern, text)
        if match:
            properties["制造商"] = match.group(1).strip()
            break

    # 提取机身号
    body_patterns = [
        r'机身号\s*[：:]\s*([^\n]+)',
        r'出厂编号\s*[：:]\s*([^\n]+)',
        r'序列号\s*[：:]\s*([^\n]+)',
    ]
    for pattern in body_patterns:
        match = re.search(pattern, text)
        if match:
            properties["机身号"] = match.group(1).strip()
            break

    # 提取管理号
    manage_patterns = [
        r'管理号\s*[：:]\s*([^\n]+)',
        r'设备编号\s*[：:]\s*([^\n]+)',
    ]
    for pattern in manage_patterns:
        match = re.search(pattern, text)
        if match:
            properties["管理号"] = match.group(1).strip()
            break

    # 提取日期
    date_patterns = [
        r'接收日期\s*[：:]\s*([^\n]+)',
        r'送检日期\s*[：:]\s*([^\n]+)',
        r'Rec\.?\s*Date\s*[：:]\s*([^\n]+)',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1).strip()
            date_match = re.search(r'(\d{4}[-年](?:0?[1-9]|1[0-2])[-月](?:0?[1-9]|[12][0-9]|3[01]))', date_str)
            if date_match:
                properties["接收日期"] = date_match.group(1).replace('年', '-').replace('月', '-').replace('日', '')
            else:
                properties["接收日期"] = date_str
            break

    issue_patterns = [
        r'签发日期\s*[：:]\s*([^\n]+)',
        r'报告日期\s*[：:]\s*([^\n]+)',
        r'App\.?\s*Date\s*[：:]\s*([^\n]+)',
    ]
    for pattern in issue_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1).strip()
            date_match = re.search(r'(\d{4}[-年](?:0?[1-9]|1[0-2])[-月](?:0?[1-9]|[12][0-9]|3[01]))', date_str)
            if date_match:
                properties["签发日期"] = date_match.group(1).replace('年', '-').replace('月', '-').replace('日', '')
            else:
                properties["签发日期"] = date_str
            break

    # 提取人员信息
    signer_patterns = [
        r'签发\s*[：:]\s*([^\n]+)',
        r'批准人\s*[：:]\s*([^\n]+)',
        r'Approved\s*by\s*[：:]\s*([^\n]+)',
        r'签发人\s*[：:]\s*([^\n]+)',
    ]
    for pattern in signer_patterns:
        match = re.search(pattern, text)
        if match:
            properties["签发人"] = match.group(1).strip()
            break

    inspector_patterns = [
        r'核验\s*[：:]\s*([^\n]+)',
        r'复核人\s*[：:]\s*([^\n]+)',
        r'Inspected\s*by\s*[：:]\s*([^\n]+)',
        r'核验人\s*[：:]\s*([^\n]+)',
    ]
    for pattern in inspector_patterns:
        match = re.search(pattern, text)
        if match:
            properties["核验人"] = match.group(1).strip()
            break

    calibrator_patterns = [
        r'校准\s*[：:]\s*([^\n]+)',
        r'校验员\s*[：:]\s*([^\n]+)',
        r'Calibrated\s*by\s*[：:]\s*([^\n]+)',
        r'校准人\s*[：:]\s*([^\n]+)',
    ]
    for pattern in calibrator_patterns:
        match = re.search(pattern, text)
        if match:
            properties["校准人"] = match.group(1).strip()
            break

    # 提取温度和湿度
    temp_pattern = re.search(r'温度\s*[：:]\s*([^\n]+)', text)
    if temp_pattern:
        temp_str = temp_pattern.group(1).strip()
        match = re.search(r'(\d+(?:\.\d+)?)\s*(℃|C|%|RH)', temp_str)
        if match:
            properties["温度"] = f"{match.group(1)}{'℃' if '℃' in match.group(2) or 'C' in match.group(2) else '%'}"
    else:
        temp_match = re.search(r'(\d+(?:\.\d+)?)\s*℃', text)
        if temp_match:
            properties["温度"] = temp_match.group(0)

    hum_pattern = re.search(r'湿度\s*[：:]\s*([^\n]+)', text)
    if hum_pattern:
        hum_str = hum_pattern.group(1).strip()
        match = re.search(r'(\d+(?:\.\d+)?)\s*(℃|C|%|RH)', hum_str)
        if match:
            properties["湿度"] = f"{match.group(1)}{'℃' if '℃' in match.group(2) or 'C' in match.group(2) else '%'}"
    else:
        hum_match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
        if hum_match:
            properties["湿度"] = hum_match.group(0)

    # 提取CNAS信息
    lab_pattern = re.search(r'认可实验室\s*[：:]\s*([^\n]+)', text)
    if lab_pattern:
        properties["认可实验室"] = lab_pattern.group(1).strip()

    cnas_pattern = re.search(r'CNAS\s*[：:L]*\s*([A-Z0-9]+)', text)
    if cnas_pattern:
        properties["CNAS"] = cnas_pattern.group(1).strip()
    elif properties.get("认可实验室"):
        match = re.search(r'L(\d+)', properties["认可实验室"])
        if match:
            properties["CNAS"] = match.group(1)

    if properties.get("CNAS") and not properties["CNAS"].startswith("L") and properties["CNAS"].isdigit():
        properties["CNAS"] = f"L{properties['CNAS']}"

    # 提取校准依据
    basis_patterns = [
        r'(JJF\s*\d+[-—]\d+[^\n;；]*)',
        r'(JJG\s*\d+[-—]\d+[^\n;；]*)',
        r'(IEC\s*\d+(?:\.\d+)*[^\n;；]*)',
        r'(ISO\s*\d+(?:\.\d+)*[^\n;；]*)',
    ]
    for pattern in basis_patterns:
        matches = re.findall(pattern, text, re.I)
        for match in matches:
            match = re.sub(r'\s+', ' ', match.strip())
            match = re.sub(r'\(cid:\d+\)', '', match)
            match = re.sub(r'[,;。.]*$', '', match)
            if len(match) >= 3 and match not in properties["校准依据"]:
                properties["校准依据"].append(match)

    # 提取结论
    conclusion_patterns = [
        r'结论\s*[：:]\s*([^\n]+)',
        r'证书结论\s*[：:]\s*([^\n]+)',
    ]
    for pattern in conclusion_patterns:
        match = re.search(pattern, text)
        if match:
            properties["结论"] = match.group(1).strip()
            break

    # 确保证书编号不为空
    if not properties.get("证书编号") or properties["证书编号"] == "None":
        filename = os.path.basename(pdf_path)
        match = re.search(r'([A-Z0-9-]+)\.pdf', filename)
        if match:
            properties["证书编号"] = match.group(1)

    return properties


def extract_tables(text, page_results):
    """提取表格数据 - 使用PaddleOCR的表格识别"""
    # 首先提取测量项目标题
    measurement_titles = []
    title_patterns = [
        r'(\d+\.?\s*[^\n]+测量[^\n]*)',
        r'(\d+\.?\s*[^\n]+误差[^\n]*)',
        r'(\d+\.?\s*[^\n]+\([^\)]+\))',
    ]
    for pattern in title_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            match = match.strip()
            if len(match) > 5 and match not in measurement_titles:
                measurement_titles.append(match)

    tables = []

    # 使用简单的表格识别方法 - 基于文本布局
    for title in measurement_titles:
        # 在所有页面中查找表格区域
        for page_idx, page_result in enumerate(page_results):
            page_text = "\n".join([item["text"] for item in page_result])
            if title in page_text:
                # 查找标题下方的表格区域
                title_bbox = None
                for item in page_result:
                    if item["text"] == title:
                        title_bbox = item["bbox"]
                        break

                if title_bbox:
                    # 查找标题下方的潜在表格区域（y坐标更大）
                    table_area = []
                    start_y = title_bbox[3]
                    for item in page_result:
                        if item["bbox"][1] > start_y and item["bbox"][1] < start_y + 500:
                            table_area.append(item)

                    if len(table_area) > 10:
                        tables.append({
                            "标题": title,
                            "页码": page_idx + 1,
                            "数据": table_area
                        })

    # 转换为规范格式
    final_tables = []
    for table in tables:
        # 简单的表格分析 - 按x坐标排序查找列
        cells = table["数据"]

        if cells:
            # 按y坐标分组（行）
            rows = []
            y_groups = {}
            for cell in cells:
                text = cell["text"].strip()
                if len(text) > 0:
                    y = round(cell["bbox"][1] / 20)  # 20像素的行分组公差
                    if y not in y_groups:
                        y_groups[y] = []
                    y_groups[y].append(cell)

            # 排序行并提取数据
            sorted_ys = sorted(y_groups.keys())
            for y in sorted_ys:
                row_cells = sorted(y_groups[y], key=lambda x: x["bbox"][0])
                if len(row_cells) >= 2:
                    row_data = {}
                    non_empty = 0
                    for col_idx, cell in enumerate(row_cells):
                        cell_text = cell["text"].strip()
                        if cell_text and cell_text != "nan" and len(cell_text.strip()) > 0:
                            row_data[f"列{col_idx}"] = cell_text
                            non_empty += 1
                    if non_empty >= 2:
                        final_tables.append({
                            "测量值": table["标题"],
                            "数据明细": row_data
                        })

    return final_tables


def parse_certificate(pdf_path):
    """解析CNAS校准证书主函数"""
    print(f"正在解析证书: {os.path.basename(pdf_path)}")

    # 初始化OCR
    ocr = init_ocr()
    if not ocr:
        return None

    # 步骤1: PDF转图像
    images = pdf_to_images(pdf_path)
    if not images:
        print("PDF无法转换为图像")
        return None

    # 步骤2: OCR识别
    page_texts, page_results = extract_text_with_ocr(images, ocr)
    full_text = "\n".join(page_texts)

    # 步骤3: 提取属性字段
    properties = extract_properties(full_text, page_results, pdf_path)

    # 步骤4: 提取表格数据
    tables = extract_tables(full_text, page_results)

    # 构建最终结果
    result = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": properties
                }
            }
        },
        "依据参数_中间数据": tables
    }

    print(f"解析完成！提取到 {len(tables)} 条测量数据")
    return result


def test_parser():
    """测试函数"""
    test_cases = [
        (r"pdf\时间和频率证书2026\JJG 488-2018瞬时日差测量仪\2GB25013881-0002.pdf",
         r"local_json\2GB25013881-0002_paddle.json"),
        (r"pdf\时间和频率证书2026\微波频率计数器\1GA25010883-0005.pdf",
         r"local_json\1GA25010883-0005_paddle.json"),
        (r"pdf\时间和频率证书2026\GNSS导航信号采集回放仪\2GB24013527-0009.pdf",
         r"local_json\2GB24013527-0009_paddle.json")
    ]

    for pdf_path, output_json in test_cases:
        try:
            result = parse_certificate(pdf_path)
            if result:
                with open(output_json, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"\n结果已保存至: {output_json}")

                props = result["properties"]["证书列表"]["items"]["properties"]
                print("\n=== 解析结果摘要 ===")
                print(f"证书编号: {props.get('证书编号')}")
                print(f"仪器名称: {props.get('仪器名称')}")
                print(f"型号: {props.get('型号规格')}")
                print(f"校准依据: {props.get('校准依据')}")
                print(f"测量数据条数: {len(result['依据参数_中间数据'])}")

        except Exception as e:
            print(f"\n解析 {pdf_path} 时出错: {e}")


if __name__ == "__main__":
    test_parser()
