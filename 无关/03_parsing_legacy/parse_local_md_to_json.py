#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
参考 md_parser_no_llm 的方法，解析 local_md 文件夹中的 MD 文件为 JSON 格式
"""

import os
import html
import json
import re
from pathlib import Path


# ──────────────────────────────────────────────
# 字段名映射：统一输出字段名
# ──────────────────────────────────────────────
FIELD_MAPPING = {
    # 证书基本信息
    "证书编号": "证书编号",
    "Certificate No": "证书编号",
    # 委托方信息
    "委托单位": "委托单位",
    "Client": "委托单位",
    "委托单位名称": "委托单位",
    # 委托方地址
    "委托方地址": "委托方地址",
    "客户地址": "委托方地址",
    "Address": "委托方地址",
    # 仪器信息
    "仪器名称": "仪器名称",
    "Description": "仪器名称",
    "INSTRUMENT_NAME": "仪器名称",
    # 型号规格
    "型号规格": "型号规格",
    "型号/规格": "型号规格",
    "型号": "型号规格",
    "Model/Type": "型号规格",
    # 制造商
    "制造商": "制造商",
    "制造厂": "制造商",
    "Manufacturer": "制造商",
    # 机身号/出厂编号
    "机身号": "机身号",
    "出厂编号": "机身号",
    "Serial No": "机身号",
    # 管理号
    "管理号": "管理号",
    "设备编号": "管理号",
    "Asset No": "管理号",
    # 日期字段
    "接收日期": "接收日期",
    "Rec. Date": "接收日期",
    "校准日期": "校准日期",
    "Cal. Date": "校准日期",
    "签发日期": "签发日期",
    "App. Date": "签发日期",
    # 周期
    "建议校准周期": "建议校准周期",
    "Reference Cal. Period": "建议校准周期",
    # 温湿度
    "温度": "温度",
    "相对湿度": "湿度",
    "湿度": "湿度",
    # 人员
    "校准人": "校准人",
    "Calibrated by": "校准人",
    "核验人": "核验人",
    "Inspected by": "核验人",
    "签发人": "签发人",
    "Approved by": "签发人",
    # 证书结论
    "结论": "结论",
    "证书结论": "结论",
    # CNAS
    "CNAS": "CNAS",
    "是否CNAS": "是否CNAS",
    "认可实验室": "认可实验室",
    # 其他
    "证书类型": "证书类型",
    "证书状态": "证书状态",
    "校准地点": "校准地点",
    "校准依据": "校准依据",
}


# ──────────────────────────────────────────────
# 标签模式配置：支持多种标签格式
# ──────────────────────────────────────────────
LABEL_PATTERNS = {
    "证书编号": [
        r"证书编号\s*[：:]\s*(\S+)",
        r"Certificate\s*No[.:]?\s*(\S+)"
    ],
    "委托单位": [
        r"委托单位\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"Client\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "委托方地址": [
        r"委托方地址\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"Address\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "仪器名称": [
        r"仪器名称\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"Description\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "型号规格": [
        r"型号规格\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"型号/规格\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"型号\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"Model/Type\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "制造商": [
        r"制造商\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"制造厂\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"Manufacturer\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "机身号": [
        r"机身号\s*[：:]\s*(\S+)",
        r"出厂编号\s*[：:]\s*(\S+)",
        r"Serial\s*No[.:]?\s*(\S+)"
    ],
    "管理号": [
        r"管理号\s*[：:]\s*(\S+)",
        r"设备编号\s*[：:]\s*(\S+)",
        r"Asset\s*No[.:]?\s*(\S+)"
    ],
    "接收日期": [
        r"接收日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})",
        r"Rec\.\s*Date\s*[：:]\s*(\d{4}-\d{2}-\d{2})"
    ],
    "校准日期": [
        r"校准日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})",
        r"Cal\.\s*Date\s*[：:]\s*(\d{4}-\d{2}-\d{2})"
    ],
    "签发日期": [
        r"签发日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})",
        r"App\.\s*Date\s*[：:]\s*(\d{4}-\d{2}-\d{2})"
    ],
    "建议校准周期": [
        r"建议校准周期\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "校准人": [
        r"校准\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "核验人": [
        r"核验\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "签发人": [
        r"签发\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
    "校准地点": [
        r"校准地点\s*[：:]\s*([^\n]+?)(?=\s*\n|$)",
        r"The calibration place\s*[：:]\s*([^\n]+?)(?=\s*\n|$)"
    ],
}


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────
def normalize_field_name(field_name: str) -> str:
    """统一字段名"""
    return FIELD_MAPPING.get(field_name, field_name)


def extract_value_by_patterns(text: str, patterns: list) -> str:
    """通过多种模式提取值"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def extract_chinese_name(text: str) -> str:
    """提取中文姓名"""
    name = re.sub(r"^[^\u4e00-\u9fa5]+", "", text)
    name_match = re.search(r"[\u4e00-\u9fa5]{2,4}", name)
    if name_match:
        return name_match.group(0)
    return None


def extract_cnas_info(text: str, meta: dict):
    """提取CNAS相关信息"""
    # 检查是否有 CNAS 标识
    cnas_pos = [r"\bCNAS\b", r"\bCNAS\s*L\s*\d+\b", r"\bCNASL\s*\d+\b", r"国际互认"]
    has_cnas = any(re.search(p, text, re.IGNORECASE) for p in cnas_pos)

    # 只有明确说证书不是 CNAS 认可的，才标记为否
    # 对于 "非CNAS认可范围的技术依据" 这种情况，证书本身还是 CNAS 认可的
    cnas_neg = [r"本证书非CNAS认可", r"证书不获CNAS认可", r"未通过CNAS认可"]
    has_no_cnas = any(re.search(p, text, re.IGNORECASE) for p in cnas_neg)

    if has_no_cnas:
        meta["是否CNAS"] = "否"
    elif has_cnas:
        meta["是否CNAS"] = "是"

        patterns = [
            r"\bCNAS\s*L\s*(\d{5,})\b",
            r"\bCNASL(\d{5,})\b",
            r"CNAS[L\s]*(\d{5,})"
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                meta["认可实验室"] = f"CNAS L{m.group(1)}"
                meta["CNAS"] = f"L{m.group(1)}"
                break


def extract_temperature(text: str, meta: dict):
    """提取温度"""
    # 先尝试匹配数学公式格式的温度
    temp_match = re.search(r"温度[^\n]*?(?:\d+\.?\d*\s*[~-]\s*\d+\.?\d*)[^\n]*?(?:\\circC|℃|C)", text, re.IGNORECASE)
    if not temp_match:
        temp_match = re.search(r"温度[^\n]*?(?:$|\\circC|℃|C)", text, re.IGNORECASE)

    if temp_match:
        temp_line = temp_match.group(0)
        # 提取所有数字
        numbers_in_temp = re.findall(r"\d+\.?\d*", temp_line)
        if numbers_in_temp:
            # 如果是范围，取第一个值
            if len(numbers_in_temp) >= 2:
                # 检查是否是范围格式 (x ~ y)
                if "~" in temp_line or "-" in temp_line:
                    temp_val = numbers_in_temp[0]
                else:
                    # 尝试合并数字
                    temp_str = "".join(numbers_in_temp)
                    if len(temp_str) > 2 and "." not in temp_str:
                        temp_val = temp_str[:-1] + "." + temp_str[-1]
                    else:
                        temp_val = temp_str
            else:
                temp_val = numbers_in_temp[0]

            # 验证温度范围是否合理 (0-50℃)
            try:
                temp_float = float(temp_val)
                if 0 <= temp_float <= 50:
                    meta["温度"] = temp_val + "℃"
                else:
                    # 如果不合理，尝试只取前两位
                    if len(temp_val) > 2:
                        meta["温度"] = temp_val[:2] + "℃"
            except:
                meta["温度"] = temp_val + "℃"


def extract_humidity(text: str, meta: dict):
    """提取湿度"""
    # 先尝试匹配数学公式格式的湿度
    humid_match = re.search(r"相对湿度[^\n]*?(?:\d+\.?\d*\s*[~-]\s*\d+\.?\d*)[^\n]*?%", text, re.IGNORECASE)
    if not humid_match:
        humid_match = re.search(r"相对湿度[^\n]*?%", text, re.IGNORECASE)

    if humid_match:
        humid_line = humid_match.group(0)
        # 提取所有数字
        numbers_in_humid = re.findall(r"\d+\.?\d*", humid_line)
        if numbers_in_humid:
            # 如果是范围，取第一个值
            if len(numbers_in_humid) >= 2:
                # 检查是否是范围格式 (x ~ y)
                if "~" in humid_line or "-" in humid_line:
                    humid_val = numbers_in_humid[0]
                else:
                    humid_str = "".join(numbers_in_humid)
                    humid_val = humid_str
            else:
                humid_val = numbers_in_humid[0]

            # 验证湿度范围是否合理 (0-100%)
            try:
                humid_float = float(humid_val)
                if 0 <= humid_float <= 100:
                    meta["湿度"] = humid_val + "%"
                else:
                    # 如果不合理，尝试只取前两位
                    if len(humid_val) > 2:
                        meta["湿度"] = humid_val[:2] + "%"
            except:
                meta["湿度"] = humid_val + "%"


def extract_certificate_specs(text: str, meta: dict):
    """提取校准依据标准"""
    spec_patterns = [
        r"JJF\s*\d+-\d+", r"JJG\s*\d+-\d+", r"GB/T\s*\d+[.\d]*",
        r"GJB\s*\d+[.\d]*", r"ISO\s*\d+[.\d]*", r"IEC\s*\d+[.\d]*"
    ]
    specs = []
    for pat in spec_patterns:
        matches = re.findall(pat, text)
        specs.extend(matches)
    if specs:
        meta["校准依据"] = list(set(specs))


def extract_conclusion(text: str, meta: dict):
    """提取证书结论"""
    # 首先查找明确的结论文本
    if "所校准项目符合技术要求" in text:
        meta["结论"] = "所校准项目符合技术要求"
    elif "符合技术要求" in text:
        meta["结论"] = "符合技术要求"
    elif "按校准结果使用" in text:
        meta["结论"] = "按校准结果使用"
    # 避免匹配 "合格评定活动" 这种情况，只匹配作为结论的 "合格"
    # 查找 "结论" 或 "Conclusion" 之后的内容
    conclusion_match = re.search(r"结论[：:]\s*([^\n]{0,50})", text)
    if conclusion_match:
        conclusion_text = conclusion_match.group(1).strip()
        if "合格" in conclusion_text and "合格评定" not in conclusion_text:
            meta["结论"] = "合格"
        elif "不合格" in conclusion_text:
            meta["结论"] = "不合格"
    # 如果没有明确结论，不设置默认值
    # 这样就能正确反映证书中没有填写结论的情况


# ──────────────────────────────────────────────
# HTML表格解析
# ──────────────────────────────────────────────
class TableCellParser:
    """HTML表格单元格解析器"""
    def __init__(self):
        self.cells = []
        self._current_cell = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._in_cell = False
            self.cells.append("".join(self._current_cell).strip())

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)


def parse_table_cells(html: str) -> list:
    """解析HTML表格为二维列表"""
    trs = re.findall(r"(?is)<tr.*?>.*?</tr>", html)
    table_data = []
    for tr in trs:
        parser = TableCellParser()
        # 简单的HTML解析
        in_tag = False
        tag = []
        for char in tr:
            if char == '<':
                in_tag = True
                tag = []
            elif char == '>':
                in_tag = False
                tag_str = ''.join(tag)
                if tag_str.startswith('/'):
                    parser.handle_endtag(tag_str[1:])
                else:
                    parser.handle_starttag(tag_str.split()[0], [])
            elif in_tag:
                tag.append(char)
            else:
                parser.handle_data(char)
        if parser.cells:
            table_data.append(parser.cells)
    return table_data


def parse_table_to_rows(table_data: list, project_title: str) -> list:
    """将表格数据解析为rows格式"""
    if len(table_data) < 2:
        return []

    rows = []
    data_start_idx = 1

    for i, row in enumerate(table_data):
        if i < 1:
            continue
        if row and re.match(r"^\d+", row[0]):
            data_start_idx = i
            break

    headers = table_data[0]

    for row in table_data[data_start_idx:]:
        if not row or all(not cell.strip() for cell in row):
            continue

        details = {}
        for i, cell in enumerate(row):
            key = headers[i] if i < len(headers) else f"列{i+1}"
            if cell.strip():
                details[key] = cell.strip()

        if details:
            rows.append({
                "测量值": project_title,
                "数据明细": details
            })

    return rows


def _strip_html_tags(text: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", str(text or ""))
    text = re.sub(r"(?is)<.*?>", "", text)
    return html.unescape(text).strip()


def _parse_span_attr(attrs_text: str, attr_name: str) -> int:
    match = re.search(rf'{attr_name}\s*=\s*["\']?(\d+)["\']?', attrs_text or "", flags=re.IGNORECASE)
    if not match:
        return 1
    try:
        return max(1, int(match.group(1)))
    except ValueError:
        return 1


def parse_table_cells(html: str) -> list:
    """Override HTML table parsing with rowspan/colspan expansion."""
    trs = re.findall(r"(?is)<tr\b.*?>.*?</tr>", html)
    table_data = []
    pending_spans = {}

    for tr in trs:
        row = []
        col_idx = 0

        def fill_pending():
            nonlocal col_idx
            while col_idx in pending_spans and pending_spans[col_idx]["rows_left"] > 0:
                row.append(str(pending_spans[col_idx]["text"]))
                pending_spans[col_idx]["rows_left"] -= 1
                if pending_spans[col_idx]["rows_left"] <= 0:
                    del pending_spans[col_idx]
                col_idx += 1

        fill_pending()
        cells = re.findall(r"(?is)<(td|th)\b([^>]*)>(.*?)</\1>", tr)
        for _, attrs_text, inner_html in cells:
            fill_pending()
            cell_text = _strip_html_tags(inner_html)
            rowspan = _parse_span_attr(attrs_text, "rowspan")
            colspan = _parse_span_attr(attrs_text, "colspan")

            for offset in range(colspan):
                row.append(cell_text)
                if rowspan > 1:
                    pending_spans[col_idx + offset] = {
                        "text": cell_text,
                        "rows_left": rowspan - 1,
                    }
            col_idx += colspan

        fill_pending()
        if row:
            table_data.append(row)

    max_len = max((len(r) for r in table_data), default=0)
    for row in table_data:
        if len(row) < max_len:
            row.extend([""] * (max_len - len(row)))
    return table_data


def _normalize_unit_text(unit_text: str) -> str:
    text = str(unit_text or "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return text


def _extract_row_units(row: list[str]) -> list[str]:
    units = []
    for cell in row:
        text = str(cell or "").strip()
        if text.startswith("(") and text.endswith(")"):
            units.append(_normalize_unit_text(text))
        else:
            units.append("")
    return units


def _is_pure_unit_row(row: list[str]) -> bool:
    non_empty_cells = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
    return bool(non_empty_cells) and all(cell.startswith("(") and cell.endswith(")") for cell in non_empty_cells)


def _is_effective_unit_row(row: list[str]) -> bool:
    non_empty_cells = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
    if len(non_empty_cells) < 2:
        return False
    tail = non_empty_cells[1:]
    return bool(tail) and all(cell.startswith("(") and cell.endswith(")") for cell in tail)


def _value_has_embedded_unit(value: str) -> bool:
    return bool(re.search(r"[A-Za-z\u00B5\u03BC\u03A9%℃℉°/]+", str(value or "").strip()))


def _should_attach_unit(value: str) -> bool:
    text = str(value or "").strip()
    if not text or _value_has_embedded_unit(text):
        return False
    if text in {"P", "F", "Pass", "Fail", "N/A", "/", "--"}:
        return False
    return bool(re.fullmatch(r"[+\-−±卤]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?", text))


def _should_skip_unit_for_key(key: str) -> bool:
    text = str(key or "").lower()
    return "通道" in text or "channel" in text or "结论" in text or "pass/fail" in text


def _attach_unit(value: str, unit: str, key: str = "") -> str:
    text = str(value or "").strip()
    clean_unit = _normalize_unit_text(unit)
    if _should_skip_unit_for_key(key):
        return text
    if not clean_unit or not _should_attach_unit(text):
        return text
    return f"{text} {clean_unit}"


def parse_table_to_rows(table_data: list, project_title: str) -> list:
    """Override table parsing to carry forward unit rows into numeric cells."""
    if len(table_data) < 2:
        return []

    rows = []
    data_start_idx = 1

    for i, row in enumerate(table_data):
        if i < 1:
            continue
        if row and re.match(r"^\d+", row[0]):
            data_start_idx = i
            break

    headers = table_data[0]
    current_units = [""] * len(headers)

    for row in table_data[data_start_idx:]:
        if not row or all(not cell.strip() for cell in row):
            continue

        if _is_pure_unit_row(row) or _is_effective_unit_row(row):
            current_units = _extract_row_units(row)
            continue

        details = {}
        for i, cell in enumerate(row):
            key = headers[i] if i < len(headers) else f"列{i+1}"
            cell_value = cell.strip()
            if not cell_value:
                continue
            unit = current_units[i] if i < len(current_units) else ""
            details[key] = _attach_unit(cell_value, unit, key)

        if details:
            rows.append({
                "测量值": project_title,
                "数据明细": details
            })

    return rows


# ──────────────────────────────────────────────
# MD文件分块和解析
# ──────────────────────────────────────────────
def split_md_to_blocks(md_text: str) -> list:
    """将MD切分为块"""
    lines = md_text.splitlines()
    sections = []
    cur_title = None
    cur_buf = []

    def flush():
        nonlocal cur_title, cur_buf
        if cur_buf:
            content = "\n".join(cur_buf).strip()
            if content:
                sections.append((cur_title or "未命名章节", content))
        cur_title = None
        cur_buf = []

    for line in lines:
        if line.startswith('#'):
            flush()
            cur_title = line.lstrip('#').strip()
            cur_buf = [line]
        else:
            cur_buf.append(line)
    flush()
    return sections


def is_skip_block(title: str, content: str) -> bool:
    """判断是否是需要跳过的块"""
    skip_keywords = [
        "说明", "DIRECTIONS", "备注", "注：", "注:", "注意",
        "Warning", "警告", "合格证", "附录", "附件", "References"
    ]
    return any(keyword in title or keyword in content for keyword in skip_keywords)


# ──────────────────────────────────────────────
# 通用格式解析
# ──────────────────────────────────────────────
def extract_meta_generic(text: str) -> dict:
    """通用格式解析"""
    meta = {
        "证书类型": "校准证书",
        "证书状态": "正常"
    }

    for field, patterns in LABEL_PATTERNS.items():
        value = extract_value_by_patterns(text, patterns)
        if value:
            if field in ["校准人", "核验人", "签发人"]:
                name = extract_chinese_name(value)
                if name:
                    meta[field] = name
            elif field == "建议校准周期":
                if any(keyword in value for keyword in ["个月", "年", "周"]):
                    meta[field] = value
            else:
                meta[field] = value

    extract_temperature(text, meta)
    extract_humidity(text, meta)
    extract_cnas_info(text, meta)
    extract_certificate_specs(text, meta)
    extract_conclusion(text, meta)

    return meta


def parse_md_to_json(md_path: str, out_dir: str = None) -> dict:
    """解析MD文件为JSON"""
    md_file = Path(md_path)
    md_text = md_file.read_text(encoding='utf-8', errors='ignore')

    blocks = split_md_to_blocks(md_text)
    final_meta = extract_meta_generic(md_text)

    all_rows = []

    for title, content in blocks:
        if is_skip_block(title, content):
            continue

        if "<table" in content:
            table_pattern = re.compile(r'(?is)<table.*?</table>')
            tables = table_pattern.findall(content)

            for table_html in tables:
                if "主要测量标准" in title:
                    continue

                table_data = parse_table_cells(table_html)
                if table_data:
                    rows = parse_table_to_rows(table_data, title)
                    all_rows.extend(rows)

    result = {
        "properties": {
            "证书列表": {
                "items": {"properties": final_meta}
            }
        },
        "依据参数_中间数据": all_rows
    }

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / md_file.with_suffix(".json").name
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"已保存: {out_file}")

    return result


def main():
    """主函数"""
    local_md_dir = Path("local_md")
    if not local_md_dir.exists():
        print("local_md 文件夹不存在")
        return

    out_dir = Path("local_json")
    out_dir.mkdir(exist_ok=True)

    md_files = list(local_md_dir.glob("*.md"))

    print(f"找到 {len(md_files)} 个 MD 文件")
    for md_file in md_files:
        print(f"解析: {md_file.name}")
        try:
            parse_md_to_json(md_file, out_dir)
        except Exception as e:
            print(f"解析 {md_file.name} 失败: {e}")

    print(f"\nJSON 文件已保存到: {out_dir}")


if __name__ == "__main__":
    main()
