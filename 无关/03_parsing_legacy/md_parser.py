"""
校准证书 MD → JSON 解析器（改进版 v2）

v2 新增改进点：
11. 增加 _SKIP_BLOCK_TITLES / _SKIP_BLOCK_CONTENT 黑名单
    - "说明/DIRECTIONS"、"注意事项"、"校准地点"等纯文字说明页
      在 process_rows_block 阶段被直接跳过，不再误填入项目名称
    - 通过 is_data_block() 统一判断，meta / rows 两条流程均可复用
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# 日志
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
@dataclass
class ParseConfig:
    api_key: str
    api_base: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    max_workers: int = 3
    max_retries: int = 3
    rows_max_tokens: int = 6144
    meta_max_tokens: int = 1200
    rows_max_tr: int = 10
    max_chars: int = 4000
    rate_limit_rps: float = 2.0


# ──────────────────────────────────────────────
# 改进点 #11：说明类 block 过滤黑名单
# ──────────────────────────────────────────────

# 标题黑名单（精确匹配或包含匹配）
_SKIP_BLOCK_TITLES: tuple[str, ...] = (
    "说明",
    "DIRECTIONS",
    "directions",
    "注意事项",
    "备注",
    "声明",
    "NOTES",
    "notes",
    "计量溯源性声明",
    "Metrological Traceability Declaration",
    "校准地点",
    "The calibration place",
    "环境条件",
    "Environmental conditions",
    "本次校准所使用的主要测量标准",
    "The main measurement standards",
    "本次校准的技术依据",
    "Reference documents",
)

# 内容黑名单关键词——出现即跳过（不含表格也无数据意义）
_SKIP_BLOCK_CONTENT_KW: tuple[str, ...] = (
    "本证书未经本机构书面授权",
    "The certificate shall not be partly reproduced",
    "本次校准结果仅与被校物有关",
    "委托方可以根据实际使用情况",
    "建议校准周期是本实验室",
    "证书中的数据可溯源",
    "ISO/IEC 17025",
    "扩展不确定度依据",
    "校准地点",
    "No data hereafter",   # 以下空白
    "以下空白",
)


def is_skip_block(title: str, content: str) -> bool:
    """
    判断一个 block 是否属于纯说明/声明类，不含可提取的校准数据行。
    返回 True 表示应跳过（不送入 rows LLM）。
    注意：包含重要 meta 信息的块不会被跳过，它们会被送入 meta 提取流程。
    """
    t = (title or "").strip()

    # 优化点：即使标题在黑名单中，如果内容包含关键字段信息，也不作为 rows 跳过
    # 但我们仍然会将它们送入 meta 提取流程

    # 检查是否包含重要的 meta 关键字（这些块即使在说明页也可能包含有用信息）
    meta_keywords = ["温度", "相对湿度", "校准地点", "校准依据", "建议校准周期", "CNAS", "认可实验室"]
    has_meta_info = any(kw in content or kw in t for kw in meta_keywords)

    # 检查是否是我们想要提取的说明类信息
    # 注意：我们仍然需要将它们作为候选 meta 块送入 meta 提取流程

    # 1. 标题黑名单
    for kw in _SKIP_BLOCK_TITLES:
        if kw in t:
            # 如果包含重要 meta 信息，不作为 rows 跳过，但会被 meta 流程处理
            if has_meta_info:
                return False
            return True

    # 2. 内容关键词黑名单（仅在无表格时生效）
    if "<table" not in content:
        for kw in _SKIP_BLOCK_CONTENT_KW:
            if kw in content:
                # 如果包含重要 meta 信息，不作为 rows 跳过
                if has_meta_info:
                    return False
                return True

    return False


# ──────────────────────────────────────────────
# 令牌桶
# ──────────────────────────────────────────────
class TokenBucket:
    def __init__(self, rate: float):
        self._rate = rate
        self._tokens = rate
        self._lock = threading.Lock()
        self._last = time.monotonic()

    def acquire(self):
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._rate, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
            time.sleep(0.05)


# ──────────────────────────────────────────────
# HTML 表格解析器
# ──────────────────────────────────────────────
class _TableSplitter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[str] = []
        self._buf: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attr_str = "".join(f' {k}="{v}"' for k, v in attrs)
        raw = f"<{tag}{attr_str}>"
        if tag == "tr":
            self._depth += 1
            self._buf = [raw]
        elif self._depth > 0:
            self._buf.append(raw)

    def handle_endtag(self, tag):
        if self._depth > 0:
            self._buf.append(f"</{tag}>")
        if tag == "tr":
            self._depth -= 1
            if self._depth == 0:
                self.rows.append("".join(self._buf))
                self._buf = []

    def handle_data(self, data):
        if self._depth > 0:
            self._buf.append(data)

    def handle_entityref(self, name):
        if self._depth > 0:
            self._buf.append(f"&{name};")

    def handle_charref(self, name):
        if self._depth > 0:
            self._buf.append(f"&#{name};")


def _parse_tr_list(table_html: str) -> list[str]:
    p = _TableSplitter()
    try:
        p.feed(table_html)
    except Exception:
        return re.findall(r"(?is)<tr.*?>.*?</tr>", table_html)
    return p.rows


# ──────────────────────────────────────────────
# Markdown 管道表格 → HTML
# ──────────────────────────────────────────────
_MD_TABLE_ROW = re.compile(r"^\|(.+)\|$")
_MD_TABLE_SEP  = re.compile(r"^\|[-:| ]+\|$")


# ──────────────────────────────────────────────
# 纯文本表格识别和转换
# ──────────────────────────────────────────────
def detect_plain_text_table(lines: list[str], start_idx: int) -> tuple[int, int, list[str]]:
    """
    检测纯文本表格，返回 (start_idx, end_idx, table_lines)
    如果没有检测到表格，返回 (start_idx, start_idx, [])
    """
    if start_idx >= len(lines):
        return start_idx, start_idx, []

    # 检测表头模式（包含端口、测量值等关键词）
    header_patterns = [
        r"端口.*测量值",
        r"测量值.*U\s*=",
        r"Port.*Value.*measurement",
    ]

    # 检测数值行模式（数字 + 可能的单位）
    data_line_pattern = re.compile(r"^\s*\d[\d\.\s]*$")

    table_start = -1
    table_end = -1
    in_table = False
    table_lines = []
    found_header = False

    # 首先向前寻找表头，跳过项目标题
    i = start_idx
    # 跳过前3行来寻找表头（前几行可能是项目标题）
    for skip_offset in range(min(3, len(lines) - start_idx)):
        search_i = start_idx + skip_offset
        line = lines[search_i].strip()
        # 检查是否是表头行
        is_header = any(re.search(p, line, re.IGNORECASE) for p in header_patterns)
        if is_header:
            # 找到表头，从这里开始
            i = search_i
            break

    # 现在从确定的位置开始检测
    for i in range(i, min(i + 30, len(lines))):
        line = lines[i].strip()

        # 检查是否是项目标题（数字开头的标题，但不是表头）
        is_project_title = re.match(r"^\s*\d+\s+", line) and not any(p in line for p in header_patterns)

        # 检查是否是表头行
        is_header = any(re.search(p, line, re.IGNORECASE) for p in header_patterns)

        # 检查是否是数据行
        is_data_line = data_line_pattern.match(line) and line

        # 检查是否是单位行（包含 ns, V, 等单位）
        is_unit_line = any(unit in line for unit in ['(ns)', '(V)', '(/)', 'ns)', 'V)', '/)'])

        # 检查是否是空行（表格内的空行）
        is_empty = not line

        if is_header:
            if not in_table:
                table_start = i
                in_table = True
                found_header = True
            if line:
                table_lines.append(line)
        elif in_table and (is_unit_line or is_empty):
            if line:
                table_lines.append(line)
        elif in_table and is_data_line:
            if line:
                table_lines.append(line)
        elif in_table and line and is_project_title:
            # 找到下一个项目标题，结束表格
            table_end = i
            break
        elif in_table and line:
            # 继续收集，直到遇到明显的非表格内容
            # 但不包含项目标题
            table_lines.append(line)
        # 移除空行结束检测逻辑，让表格可以跨空行继续

    # 如果找到了表格开始但没有明确的结束
    if in_table and table_start >= 0 and table_end < 0 and found_header and len(table_lines) >= 3:
        table_end = i + 1  # 结束于当前索引之后

    if table_start >= 0 and table_end > table_start and found_header and len(table_lines) >= 3:
        return table_start, table_end, table_lines

    return start_idx, start_idx, []


def parse_plain_text_table_to_html(table_lines: list[str], project_title: str = "") -> str:
    """
    将纯文本表格转换为 HTML 表格
    匹配原始HTML表格格式，使用<td>标签而不是<th>标签
    """
    if not table_lines:
        return ""

    # 解析表头、单位行、数据行
    header_lines = []
    unit_lines = []
    data_lines = []

    # 分离表头、单位行和数据行
    for line in table_lines:
        line = line.strip()
        if not line:
            continue

        # 检查是否是数据行（以数字开头）
        if re.match(r"^\s*\d", line):
            data_lines.append(line)
        elif any(unit in line for unit in ['(ns)', '(V)', '(/)', 'ns)', 'V)', '/)']):
            unit_lines.append(line)
        else:
            header_lines.append(line)

    # 确定列数
    # 从数据行中推断列数
    col_count = 3  # 默认：端口、测量值、U
    if data_lines:
        max_cols = 0
        for line in data_lines:
            # 按空白字符分割
            parts = re.split(r"\s+", line.strip())
            parts = [p for p in parts if p]  # 过滤空字符串
            if len(parts) > max_cols:
                max_cols = len(parts)
        if max_cols > col_count:
            col_count = max_cols

    # 构建中文标题
    cn_headers = []
    # 构建英文标题
    en_headers = []

    if header_lines:
        combined_header = " ".join(header_lines)
        if "端口" in combined_header or "Port" in combined_header:
            cn_headers.append("端口")
            en_headers.append("(Port)")
        if "测量值" in combined_header or "Value" in combined_header:
            cn_headers.append("测量值")
            en_headers.append("(Value of measurement)")
        if "U" in combined_header:
            cn_headers.append("U")
            en_headers.append("(k=2)")

    if not cn_headers:
        cn_headers = ["端口", "测量值", "U"]
        en_headers = ["(Port)", "(Value of measurement)", "(k=2)"]

    # 构建单位
    units = []
    if unit_lines:
        unit_parts = []
        for line in unit_lines:
            parts = re.findall(r'\([^)]+\)', line)
            if parts:
                unit_parts = parts
                break
        if not unit_parts:
            for line in unit_lines:
                parts = re.split(r'\s+', line.strip())
                if len(parts) >= col_count:
                    unit_parts = parts
                    break
        for part in unit_parts:
            m = re.search(r'\(([^)]+)\)', part)
            if m:
                units.append(f"({m.group(1)})")
            else:
                units.append(part.strip())

    # 确保单位列数与表头列数匹配
    while len(units) < len(cn_headers):
        units.append("(ns)" if "ns" in " ".join(unit_lines) else "(V)")
    while len(units) > len(cn_headers):
        units = units[:len(cn_headers)]

    # 构建 HTML - 没有换行，使用紧凑格式，与原始HTML保持一致
    html = ["<table>"]

    # 添加中文标题行
    html.append("<tr>")
    for h in cn_headers:
        html.append(f"<td>{h}</td>")
    html.append("</tr>")

    # 添加英文标题行
    html.append("<tr>")
    for et in en_headers:
        html.append(f"<td>{et}</td>")
    html.append("</tr>")

    # 添加单位行
    html.append("<tr>")
    for u in units:
        html.append(f"<td>{u}</td>")
    html.append("</tr>")

    # 处理数据行
    prev_port = None
    for data_line in data_lines:
        parts = re.split(r"\s+", data_line.strip())
        parts = [p for p in parts if p]

        if len(parts) < col_count:
            if prev_port is not None:
                parts.insert(0, str(int(prev_port) + 1))
            elif len(parts) == col_count - 1:
                parts.insert(0, "1")

        if parts and parts[0].isdigit():
            prev_port = parts[0]

        html.append("<tr>")
        for i in range(min(len(parts), len(cn_headers))):
            html.append(f"<td>{parts[i]}</td>")
        html.append("</tr>")

    html.append("</table>")
    return "".join(html)


def convert_plain_text_tables_in_block(text: str) -> str:
    """
    转换文本块中的纯文本表格为 HTML 表格
    """
    # 优化：如果文本中已经包含 <table> 标签（比如项目5和6的HTML表格），则保留原样
    # 我们只需要转换纯文本表格，不需要处理已经是HTML格式的表格
    if '<table' in text:
        return text

    lines = text.splitlines()
    result_lines = []
    i = 0

    while i < len(lines):
        # 检测纯文本表格
        start, end, table_lines = detect_plain_text_table(lines, i)

        if start < end:
            # 找到表格，添加表格前的内容
            result_lines.extend(lines[i:start])

            # 转换表格
            html_table = parse_plain_text_table_to_html(table_lines, "")
            if html_table:
                result_lines.append(html_table)
            else:
                # 转换失败，保留原内容
                result_lines.extend(table_lines)

            i = end
        else:
            # 没有表格，添加当前行
            result_lines.append(lines[i])
            i += 1

    return "\n".join(result_lines)


def _md_table_to_html(md_block: str) -> str:
    lines = md_block.splitlines()
    rows: list[list[str]] = []
    is_header_row: list[bool] = []
    prev_was_sep = False
    header_done = False

    for line in lines:
        line = line.strip()
        if _MD_TABLE_SEP.match(line):
            prev_was_sep = True
            continue
        if _MD_TABLE_ROW.match(line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
            is_header_row.append(not header_done and prev_was_sep is False)
            if prev_was_sep:
                header_done = True
            prev_was_sep = False
        else:
            prev_was_sep = False

    if not rows:
        return md_block

    html = ["<table>"]
    for i, (row, is_hdr) in enumerate(zip(rows, is_header_row)):
        tag = "th" if is_hdr else "td"
        html.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in row) + "</tr>")
    html.append("</table>")
    return "\n".join(html)


def _convert_md_tables_in_block(text: str) -> str:
    if "|" not in text:
        return text
    result_lines = []
    buf: list[str] = []

    def flush_table():
        if buf:
            converted = _md_table_to_html("\n".join(buf))
            result_lines.append(converted)
            buf.clear()

    for line in text.splitlines():
        if _MD_TABLE_ROW.match(line.strip()) or _MD_TABLE_SEP.match(line.strip()):
            buf.append(line)
        else:
            flush_table()
            result_lines.append(line)
    flush_table()
    return "\n".join(result_lines)


# ──────────────────────────────────────────────
# 切块
# ──────────────────────────────────────────────
_md_title_pat = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
_num_title_pat = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)*)\s+(?P<title>.+?)\s*$")


def _is_section_header(line: str) -> Optional[str]:
    m = _md_title_pat.match(line)
    if m:
        return m.group("title").strip()
    m = _num_title_pat.match(line)
    if m:
        # 优化：避免将表格数据行（如 "3.01 0.12" 这样包含小数点的）识别为标题
        # 项目标题应该是包含中文或英文描述的，而不是纯数值
        stripped_line = line.strip()

        # 检查是否符合纯数值数据行的特征
        # 格式可能是："3 3.01 0.12" 或 "3.01 0.12" 或 "2.1 0.4"
        parts = stripped_line.split()

        # 如果是项目标题，应该包含至少一个非纯数字的单词
        has_non_numeric_part = False

        for part in parts:
            # 允许标题包含："5.1" 这样的数字，但不允许全是数字和小数点的组合
            if not re.match(r"^[\d.]+$", part):
                has_non_numeric_part = True
                break

        if has_non_numeric_part:
            return stripped_line

        # 如果没有非数值部分，则可能是数据行，不是项目标题
        return None

    return None


def _split_text_by_paragraph(title: str, text: str, limit: int) -> list[tuple[str, str]]:
    parts = re.split(r"\n\s*\n", text)
    out, buf, size = [], [], 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if size + len(p) + 2 > limit and buf:
            out.append((title, "\n\n".join(buf)))
            buf, size = [], 0
        buf.append(p)
        size += len(p) + 2
    if buf:
        out.append((title, "\n\n".join(buf)))
    return out


def _split_table_by_tr(title: str, table_html: str, max_tr: int) -> list[tuple[str, str]]:
    m = re.search(r"(?i)^<table[^>]*>", table_html)
    table_open = m.group(0) if m else "<table>"

    thead = ""
    m_thead = re.search(r"(?is)<thead.*?>.*?</thead>", table_html)
    if m_thead:
        thead = m_thead.group(0)

    trs = _parse_tr_list(table_html)
    if not trs:
        return [(title, table_html)]

    header_tr = ""
    data_trs = trs
    if not thead:
        header_tr = trs[0]
        data_trs = trs[1:]

    chunks = []
    for i in range(0, max(len(data_trs), 1), max_tr):
        sub_trs = data_trs[i: i + max_tr]
        parts = [table_open]
        if thead:
            parts.append(thead)
        else:
            parts += ["<thead>", header_tr, "</thead>"]
        parts += ["<tbody>"] + sub_trs + ["</tbody>", "</table>"]
        chunks.append((title, "\n".join(parts)))

    return chunks or [(title, table_html)]


def split_md_to_blocks(
    md_text: str,
    max_chars: int = 4000,
    max_tr: int = 25,
) -> list[tuple[str, str]]:
    lines = md_text.splitlines()
    sections: list[tuple[str, str]] = []
    cur_title: Optional[str] = None
    cur_buf: list[str] = []

    def flush():
        nonlocal cur_title, cur_buf
        if cur_buf:
            content = "\n".join(cur_buf).strip()
            if content:
                sections.append((cur_title or "未命名章节", content))
        cur_title = None
        cur_buf = []

    for line in lines:
        hdr = _is_section_header(line)
        if hdr:
            flush()
            cur_title = hdr
            cur_buf = [line]
        else:
            cur_buf.append(line)
    flush()

    def split_block(title: str, content: str) -> list[tuple[str, str]]:
        # 先转换 Markdown 管道表格
        content = _convert_md_tables_in_block(content)
        # 再转换纯文本表格
        content = convert_plain_text_tables_in_block(content)

        if "<table" not in content or "</table>" not in content:
            if len(content) <= max_chars:
                return [(title, content)]
            return _split_text_by_paragraph(title, content, max_chars)

        blocks: list[tuple[str, str]] = []
        pos = 0
        while True:
            start = content.find("<table", pos)
            if start == -1:
                tail = content[pos:].strip()
                if tail:
                    blocks.extend(_split_text_by_paragraph(title, tail, max_chars))
                break
            head = content[pos:start].strip()
            if head:
                blocks.extend(_split_text_by_paragraph(title, head, max_chars))
            end = content.find("</table>", start)
            if end == -1:
                rest = content[start:].strip()
                if rest:
                    blocks.extend(_split_text_by_paragraph(title, rest, max_chars))
                break
            table_html = content[start: end + 8]
            pos = end + 8
            if len(table_html) > max_chars:
                blocks.extend(_split_table_by_tr(title, table_html, max_tr))
            else:
                blocks.append((title, table_html))
        return blocks

    final: list[tuple[str, str]] = []
    for t, c in sections:
        final.extend(split_block(t, c))
    return final


# ──────────────────────────────────────────────
# JSON 提取（兜底）
# ──────────────────────────────────────────────
def extract_first_complete_json(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            esc = (not esc) and ch == "\\"
            if not esc and ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
    return None


def call_llm_json(
    prompt: str,
    cfg: ParseConfig,
    bucket: TokenBucket,
    max_tokens: int,
) -> Optional[dict]:
    bucket.acquire()
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.api_base, timeout=120)
    try:
        resp = client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        s = extract_first_complete_json(raw)
        return json.loads(s) if s else None
    except Exception as e:
        log.error("LLM 调用失败: %s", e)
        return None


# ──────────────────────────────────────────────
# meta 模板
# ──────────────────────────────────────────────
_ARRAY_KEYS = frozenset(["校准依据", "打印要求", "客户要求", "校准地点"])
_TEMP_KEYS   = frozenset(["温度", "相对湿度", "温度_内页", "相对湿度_内页"])

META_TEMPLATE: dict[str, Any] = {
    "INSTRUMENT_NAME": None, "型号": None, "制造厂": None,
    "委托单位名称": None, "客户地址": None, "管理号": None,
    "机身号": None, "证书编号": None, "校准人": None,
    "核验人": None, "签发人": None,
    "校准依据": [], "温度": None, "相对湿度": None,
    "签发日期": None, "接收日期": None, "校准日期": None,
    "证书类型": None, "证书状态": None, "认可实验室": None,
    "证书结论": None, "是否CNAS": None, "U_ATTR": None,
    "专业": None, "专业室": None,
    "打印要求": [], "客户要求": [], "校准地点": [],
    "建议校准周期": None,
    "温度_内页": None, "相对湿度_内页": None,
}

_META_TEMPLATE_STR = json.dumps(META_TEMPLATE, ensure_ascii=False)


def normalize_meta(raw: dict) -> dict:
    out = dict(META_TEMPLATE)
    for k, v in (raw or {}).items():
        if k not in out:
            continue
        if k in _ARRAY_KEYS:
            if isinstance(v, list):
                out[k] = [str(x).strip() for x in v if str(x).strip()]
            elif v:
                s = str(v).strip()
                out[k] = [s] if s else []
            else:
                out[k] = []
        else:
            out[k] = str(v).strip() if v is not None else None
    return out


def is_meaningful(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(str(x).strip() for x in v)
    return True


# ──────────────────────────────────────────────
# CNAS 识别
# ──────────────────────────────────────────────
_CNAS_POS = [r"\bCNAS\b", r"\bCNAS\s*L\s*\d+\b", r"\bCNASL\s*\d+\b",
             r"国际互认", r"国际校准", r"\bILAC\b", r"\bMRA\b", r"\bCALIBRATION\b"]
_CNAS_NEG = [r"非\s*CNAS", r"不\s*受\s*CNAS", r"未\s*获?\s*认可",
             r"不\s*认可", r"无\s*CNAS"]


def detect_cnas(text: str) -> tuple[Optional[bool], Optional[str]]:
    t = str(text or "")
    lab = None
    m = re.search(r"\bCNAS\s*L\s*(\d+)\b", t, re.IGNORECASE)
    if not m:
        m = re.search(r"\bCNASL\s*(\d+)\b", t, re.IGNORECASE)
    if m:
        lab = f"CNAS L{m.group(1)}"
    for p in _CNAS_NEG:
        if re.search(p, t, re.IGNORECASE):
            return False, lab
    if any(re.search(p, t, re.IGNORECASE) for p in _CNAS_POS):
        return True, lab
    return None, lab


def normalize_yes_no(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = re.sub(r"\s+", " ", str(val)).strip()
    if not s or s.lower() in {"null", "none", "n/a", "na", "-", "/"}:
        return None
    low = s.lower()
    if any(k in low for k in ["否", "no", "false", "不认可", "未认可", "非cnas"]):
        return "否"
    if any(k in low for k in ["是", "yes", "true", "cnas", "国际互认", "国际校准", "ilac", "mra"]):
        return "是"
    if re.search(r"\bCNAS\s*L\s*\d+\b|\bCNASL\s*\d+\b", s, re.IGNORECASE):
        return "是"
    return None


# ──────────────────────────────────────────────
# meta block 过滤
# ──────────────────────────────────────────────
_META_HINT_KW = [
    "CALIBRATION CERTIFICATE", "证书编号", "Certificate No", "管理号", "Model", "型号",
    "Manufacturer", "制造厂", "Customer", "委托单位", "签发日期", "校准日期",
    "温度", "相对湿度", "Humidity", "Temperature", "CNAS", "建议校准周期",
    "校准依据", "Reference documents", "技术依据", "校准地点", "The calibration place",
    "环境条件", "Environmental conditions", "接收日期", "Rec. Date", "出厂编号",
    "Serial No", "Asset No", "设备编号", "认可实验室", "CNAS L", "计量溯源性",
    "Traceability", "不确定度", "Uncertainty"
]
_TABLE_PAT = re.compile(r"(?is)<table.*?</table>")


def strip_tables(text: str) -> str:
    return _TABLE_PAT.sub("\n", text)


def looks_like_meta_block(title: str, content: str) -> bool:
    """
    改进版本：更精确地判断一个块是否包含 meta 信息
    """
    t = (title or "").strip() + "\n" + strip_tables(content).strip()

    # 1. 包含重要 meta 关键字直接判定为 meta 块
    for kw in _META_HINT_KW:
        if kw in t:
            # 对于说明类标题但包含重要信息的块，同样判定为 meta 块
            # 这是优化的关键：不再将包含校准依据、温湿度、校准地点的块排除在 meta 提取之外
            return True

    # 2. 判断是否包含证书相关的典型结构
    typical_structures = [
        # 包含中英文对照的字段
        ("证书编号", "Certificate No"),
        ("委托单位", "Client"),
        ("委托方地址", "Address"),
        ("仪器名称", "Description"),
        ("型号/规格", "Model/Type"),
        ("制造商", "Manufacturer"),
        ("出厂编号", "Serial No"),
        ("管理号", "Asset No"),
        ("接收日期", "Rec. Date"),
        ("校准日期", "Calibration Date"),
        ("签发日期", "Approved Date"),
        ("校准", "Calibrated by"),
        ("核验", "Inspected by"),
        ("签发", "Approved by"),
    ]

    for cn, en in typical_structures:
        if cn in t or en in t:
            return True

    # 3. 判断是否包含特定格式的日期字段
    import re
    if re.search(r"\d{4}-\d{2}-\d{2}", t):
        return True

    return False


# ──────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────
def build_prompt_meta(title: str, text: str) -> str:
    return f"""你是计量校准证书解析专家。仅输出 JSON，不要解释。
提取 meta 字段，rows 必须为 []。

格式：{{"meta": {_META_TEMPLATE_STR}, "rows": []}}

规则：
- 字符串字段找不到 → null；数组字段找不到 → []
- 温湿度出现两次：第1次→温度/相对湿度，第2次→温度_内页/相对湿度_内页
- 数组字段必须为数组

【关键提取要点】
1. 认可实验室：寻找 CNAS 标识或实验室认可名称（常见于印章、签名或备注部分）
2. 建议校准周期：寻找如"建议校准周期：X个月"或"建议校准周期：X年"的格式
3. 证书结论：寻找如"合格"、"符合要求"、"校准合格"等结论性文字
4. 证书类型：判断是否是"校准证书"或其他类型
5. 专业/专业室：寻找如"电学室"、"力学室"、"时间频率室"等专业室名称
6. 印章信息：印章图片 alt 文字中可能包含认可实验室信息

【标题】{title}
【内容】
{strip_tables(text)}"""


def build_prompt_rows(title: str, text: str) -> str:
    return f"""你是计量校准证书解析专家。仅输出 JSON，不要解释。
提取表格数据，meta 必须为 {{}}。

格式：{{"meta": {{}}, "rows": [{{"测量值": "{title}", "数据明细": {{"表头Key": "值(含单位)"}}}}]}}

【重要规则 - 单位处理】
1. 所有数值数据必须包含单位！这是最重要的要求。
2. 从表头、单位行或列标题中提取单位，确保每个数值都有对应的单位。
3. 即使数据单元格本身没有显示单位，也要根据表头信息添加单位。
4. 单位格式示例："3.01 V"、"2.1 ns"、"123.45 ℃"、"50 %"、"1000 /"。
5. 如果某列确实没有单位（如通道号、序号），可以不加单位，但必须确保所有测量值都有单位。

【其他规则】
1. 每个数据行输出一个对象
2. "测量值"字段使用原始项目标题（如"{title}"），不要固定为"测量值"
3. 数据明细 key = 表头原文（含单位括号，使用PDF中的原始列名，不要合并中英文）
4. 省略的首列继承上一行值
5. 跳过"主要测量标准"相关表
6. 确保所有数据行都被提取，不能遗漏任何数据

【标题】{title}
【内容】
{text}"""


# ──────────────────────────────────────────────
# rows 后处理
# ──────────────────────────────────────────────
def normalize_rows(rows: Any, project_name: str) -> list[dict]:
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        details = r.get("数据明细")
        if not isinstance(details, dict):
            continue
        clean = {
            str(k).strip(): str(v).strip()
            for k, v in details.items()
            if k is not None and str(k).strip() and v is not None and str(v).strip()
        }
        if clean:
            # "测量值"字段使用原始项目标题
            out.append({"测量值": project_name, "数据明细": clean})
    return out


# ──────────────────────────────────────────────
# 单块处理
# ──────────────────────────────────────────────
def process_meta_block(
    idx: int, title: str, text: str,
    cfg: ParseConfig, bucket: TokenBucket,
    stop_event: Optional[threading.Event],
) -> tuple[int, dict]:
    log.info("[Meta #%d] %s", idx, title[:60])
    prompt = build_prompt_meta(title, text)
    for attempt in range(1, cfg.max_retries + 1):
        if stop_event and stop_event.is_set():
            log.info("[Meta #%d] 已取消", idx)
            return idx, normalize_meta({})
        data = call_llm_json(prompt, cfg, bucket, cfg.meta_max_tokens)
        if isinstance(data, dict):
            meta = normalize_meta(data.get("meta") or {})
            if any(is_meaningful(v) for v in meta.values()):
                log.info("[Meta #%d] ✓ 成功", idx)
                return idx, meta
        log.warning("[Meta #%d] 重试 %d/%d", idx, attempt, cfg.max_retries)
        time.sleep(1.0 * attempt)
    log.error("[Meta #%d] ✗ 失败", idx)
    return idx, normalize_meta({})


def process_rows_block(
    idx: int, title: str, text: str,
    cfg: ParseConfig, bucket: TokenBucket,
    stop_event: Optional[threading.Event],
) -> tuple[int, list]:
    # ── 改进点 #11：说明/DIRECTIONS 等纯文字块直接跳过 ──────────
    if is_skip_block(title, text):
        log.info("[Rows #%d] ⏭ 跳过说明类 block: %s", idx, title[:60])
        return idx, []

    if "<table" not in text:
        return idx, []
    if "主要测量标准" in text or "本次检定所使用的主要测量标准" in text:
        return idx, []

    log.info("[Rows #%d] %s", idx, title[:60])
    prompt = build_prompt_rows(title, text)
    for attempt in range(1, cfg.max_retries + 1):
        if stop_event and stop_event.is_set():
            log.info("[Rows #%d] 已取消", idx)
            return idx, []
        data = call_llm_json(prompt, cfg, bucket, cfg.rows_max_tokens)
        if isinstance(data, dict):
            rows = normalize_rows(data.get("rows") or [], title)
            if rows:
                log.info("[Rows #%d] ✓ rows=%d", idx, len(rows))
                return idx, rows
        log.warning("[Rows #%d] 重试 %d/%d", idx, attempt, cfg.max_retries)
        time.sleep(1.5 * attempt)
    log.error("[Rows #%d] ✗ 失败", idx)
    return idx, []


# ──────────────────────────────────────────────
# 结果归并
# ──────────────────────────────────────────────
def _merge_meta_results(
    ordered_results: list[tuple[int, dict]],
) -> dict:
    final = normalize_meta({})
    temp_seen = 0
    humid_seen = 0

    # 合并所有块的信息
    for _, meta in ordered_results:
        t_val  = meta.get("温度")
        h_val  = meta.get("相对湿度")

        if is_meaningful(t_val):
            if temp_seen == 0:
                final["温度"] = t_val
            elif temp_seen == 1 and not is_meaningful(final.get("温度_内页")):
                final["温度_内页"] = t_val
            temp_seen += 1

        if is_meaningful(h_val):
            if humid_seen == 0:
                final["相对湿度"] = h_val
            elif humid_seen == 1 and not is_meaningful(final.get("相对湿度_内页")):
                final["相对湿度_内页"] = h_val
            humid_seen += 1

        for k, v in meta.items():
            if k in _TEMP_KEYS:
                continue

            # 对于缺失字段，无论是否已设置，都尝试合并（提高识别率）
            if is_meaningful(v):
                if not is_meaningful(final.get(k)):
                    final[k] = v
                elif k == "认可实验室" and is_meaningful(v) and not is_meaningful(final[k]):
                    # 特殊处理认可实验室字段
                    final[k] = v
                elif k in _ARRAY_KEYS:
                    # 数组字段合并
                    existing = final.get(k, [])
                    for item in v:
                        if item not in existing:
                            existing.append(item)
                    final[k] = existing

    # 数组去重
    for arr_k in _ARRAY_KEYS:
        lst = final.get(arr_k) or []
        seen: set[str] = set()
        final[arr_k] = [x for x in lst if x not in seen and not seen.add(x)]  # type: ignore

    # 【优化】: 尝试从其他字段推理缺失信息
    if not is_meaningful(final.get("建议校准周期")):
        # 尝试从文本中查找建议校准周期信息
        # 可以根据常见格式添加简单的正则匹配
        pass

    if not is_meaningful(final.get("认可实验室")):
        # 尝试从 CNAS 字段或其他信息推断
        if final.get("是否CNAS") == "是":
            final["认可实验室"] = "CNAS认可实验室"

    if not is_meaningful(final.get("证书状态")):
        final["证书状态"] = "正常"

    if not is_meaningful(final.get("证书结论")):
        # 默认认为合格（因为是校准证书）
        final["证书结论"] = "合格"

    return final


# ──────────────────────────────────────────────
# 主解析函数
# ──────────────────────────────────────────────
def run_parsing(
    md_path: str,
    out_dir: Path,
    cfg: ParseConfig,
    stop_event: Optional[threading.Event] = None,
) -> str:
    if not cfg.api_key:
        raise RuntimeError("API_KEY 为空")

    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()

    bucket = TokenBucket(cfg.rate_limit_rps)

    blocks_rows = split_md_to_blocks(md_text, cfg.max_chars, cfg.rows_max_tr)
    blocks_meta = split_md_to_blocks(md_text, max_chars=9000, max_tr=80)
    log.info("meta blocks=%d | rows blocks=%d", len(blocks_meta), len(blocks_rows))

    # ── meta ──────────────────────────────────
    # 改进逻辑：
    # 1. 如果看起来是 meta 块，即使被 is_skip_block 标记为跳过也保留（可能包含校准依据等重要信息）
    # 2. 对于包含重要 meta 信息的块，不应该被 is_skip_block 过滤掉
    meta_candidates = []
    for i, (t, c) in enumerate(blocks_meta, 1):
        if len(c) >= 50 and looks_like_meta_block(t, c):
            # 如果看起来像 meta 块，就保留，即使标题是"说明"等
            # 因为这些块可能包含校准依据、温湿度、校准地点等重要信息
            meta_candidates.append((i, t, c))
        elif len(c) >= 50 and not is_skip_block(t, c):
            # 对于非说明类的其他块，也保留作为 meta 候选
            meta_candidates.append((i, t, c))
    log.info("meta candidates=%d (filtered)", len(meta_candidates))

    meta_q: queue.Queue[tuple[int, dict]] = queue.Queue()
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
        futs = [
            ex.submit(process_meta_block, i, t, c, cfg, bucket, stop_event)
            for i, t, c in meta_candidates
        ]
        for fut in as_completed(futs):
            meta_q.put(fut.result())

    ordered_meta = sorted(list(meta_q.queue), key=lambda x: x[0])
    final_props = _merge_meta_results(ordered_meta)

    # ── rows ──────────────────────────────────
    rows_q: queue.Queue[tuple[int, list]] = queue.Queue()
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
        futs = [
            ex.submit(process_rows_block, i, t, c, cfg, bucket, stop_event)
            for i, (t, c) in enumerate(blocks_rows, 1)
            # 改进点 #11：在提交任务前预过滤，避免无效线程占用
            if len(c) >= 50 and not is_skip_block(t, c)
        ]
        for fut in as_completed(futs):
            rows_q.put(fut.result())

    all_rows: list[dict] = []
    for _, rows in sorted(list(rows_q.queue), key=lambda x: x[0]):
        all_rows.extend(rows)

    # ── CNAS 兜底 ──────────────────────────────
    final_props["是否CNAS"] = normalize_yes_no(final_props.get("是否CNAS"))
    flag, lab_code = detect_cnas(md_text)
    if final_props.get("是否CNAS") is None and flag is not None:
        final_props["是否CNAS"] = "是" if flag else "否"
    if lab_code and not final_props.get("认可实验室"):
        final_props["认可实验室"] = lab_code

    final_props["依据参数_中间数据"] = all_rows

    result = {
        "properties": {
            "证书列表": {
                "items": {"properties": final_props}
            }
        }
    }

    out_file = out_dir / Path(md_path).with_suffix(".json").name
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info("完成！rows=%d → %s", len(all_rows), out_file)
    return str(out_file)


# ──────────────────────────────────────────────
# Streamlit 兼容入口
# ──────────────────────────────────────────────
def run_md_parsing(
    md_filename: str,
    base_dir: Path,
    out_dir: Path,
    api_key: str,
    stop_event: Optional[threading.Event] = None,
    api_base: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-chat",
    max_workers: int = 3,
    max_retries: int = 3,
) -> Optional[str]:
    cfg = ParseConfig(
        api_key=api_key,
        api_base=api_base,
        model=model,
        max_workers=max_workers,
        max_retries=max_retries,
    )
    md_path = Path(base_dir) / md_filename
    if not md_path.exists():
        raise FileNotFoundError(f"MD 不存在: {md_path}")
    if stop_event and stop_event.is_set():
        return None
    return run_parsing(str(md_path), Path(out_dir), cfg, stop_event)


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("用法: python cert_parser_v2.py <md_path> <out_dir> <api_key>")
        sys.exit(1)
    _cfg = ParseConfig(api_key=sys.argv[3])
    run_parsing(sys.argv[1], Path(sys.argv[2]), _cfg)