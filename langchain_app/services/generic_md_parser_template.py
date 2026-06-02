#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic Markdown parser template for calibration-style certificates.

This module is intentionally not wired into the runtime path yet.
It captures a staged, strategy-driven parsing design so future parser
work can extend registries and row-shape strategies instead of adding
report-specific branches to the main parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
from typing import Dict, Iterable, List, Optional, Protocol, Sequence


HEADING_RE = re.compile(r"(?m)^(#{1,6})\s*(.+?)\s*$")
TABLE_RE = re.compile(r"(?is)<table.*?</table>")
META_LINE_RE = re.compile(
    r"(接收日期|校准日期|签发日期|建议校准周期|委托单位|仪器名称|型号规格|制造厂|制造商|机身号|管理号)\s*[：:]\s*"
)
UNIT_TOKEN_RE = re.compile(
    r"(?:^|\b)(Hz|kHz|MHz|GHz|s|ms|μs|us|ns|min|h|dB|dBm|V|mV|A|mA|%|ppm|ppb|次|s/d|s/m)(?:$|\b)"
)


@dataclass
class Block:
    title: str
    content: str
    order: int


@dataclass
class Cell:
    text: str
    rowspan: int = 1
    colspan: int = 1


@dataclass
class TableGrid:
    title: str
    rows: List[List[str]]
    source_html: str


@dataclass
class RowContext:
    table_title: str
    header_rows: List[List[str]] = field(default_factory=list)
    inherited_units: Dict[int, str] = field(default_factory=dict)
    section_hints: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedRow:
    semantic_target: str
    fields: Dict[str, str]
    section_title: str
    evidence: Dict[str, str]
    confidence: float


@dataclass
class ParsedDocument:
    meta: Dict[str, str]
    rows: List[ParsedRow]
    parser_issues: List[str]


class RowShapeStrategy(Protocol):
    name: str

    def matches(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> bool:
        ...

    def bind(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> ParsedRow:
        ...


class _SimpleHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: List[List[List[Cell]]] = []
        self._current_table: List[List[Cell]] | None = None
        self._current_row: List[Cell] | None = None
        self._current_cell: Cell | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_map = {key.lower(): value for key, value in attrs}
        if tag == "table":
            self._current_table = []
            self.tables.append(self._current_table)
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
            self._current_table.append(self._current_row)
        elif tag in {"td", "th"} and self._current_row is not None:
            rowspan = int(attrs_map.get("rowspan", "1") or "1")
            colspan = int(attrs_map.get("colspan", "1") or "1")
            self._current_cell = Cell(text="", rowspan=rowspan, colspan=colspan)
            self._current_row.append(self._current_cell)

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.text += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self._current_cell = None
        elif tag == "tr":
            self._current_row = None
        elif tag == "table":
            self._current_table = None


def normalize_text(text: str) -> str:
    text = unescape(str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_blocks(md_text: str) -> List[Block]:
    matches = list(HEADING_RE.finditer(md_text))
    if not matches:
        return [Block(title="__document__", content=md_text, order=0)]
    blocks: List[Block] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(md_text)
        blocks.append(Block(title=normalize_text(match.group(2)), content=md_text[start:end], order=index))
    return blocks


def extract_meta(md_text: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for line in md_text.splitlines():
        if not META_LINE_RE.search(line):
            continue
        parts = re.split(r"(?=(?:接收日期|校准日期|签发日期|建议校准周期|委托单位|仪器名称|型号规格|制造厂|制造商|机身号|管理号)\s*[：:])", line)
        for part in parts:
            match = re.match(
                r"\s*(接收日期|校准日期|签发日期|建议校准周期|委托单位|仪器名称|型号规格|制造厂|制造商|机身号|管理号)\s*[：:]\s*(.+?)\s*$",
                part,
            )
            if match:
                meta[match.group(1)] = normalize_text(match.group(2))
    return meta


def extract_tables(block: Block) -> List[TableGrid]:
    tables: List[TableGrid] = []
    for html in TABLE_RE.findall(block.content):
        parser = _SimpleHTMLTableParser()
        parser.feed(html)
        for table in parser.tables:
            tables.append(TableGrid(title=block.title, rows=expand_spans(table), source_html=html))
    return tables


def expand_spans(rows: List[List[Cell]]) -> List[List[str]]:
    grid: List[List[str]] = []
    carry: Dict[tuple[int, int], str] = {}
    width = max((sum(cell.colspan for cell in row) for row in rows), default=0)
    for row_index, row in enumerate(rows):
        out_row = [""] * width
        col = 0
        while (row_index, col) in carry:
            out_row[col] = carry[(row_index, col)]
            col += 1
        for cell in row:
            text = normalize_text(cell.text)
            while col < width and out_row[col]:
                col += 1
            for dx in range(cell.colspan):
                if col + dx < width:
                    out_row[col + dx] = text
                    for dy in range(1, cell.rowspan):
                        carry[(row_index + dy, col + dx)] = text
            col += cell.colspan
            while (row_index, col) in carry:
                out_row[col] = carry[(row_index, col)]
                col += 1
        grid.append(out_row)
    return trim_empty_columns(grid)


def trim_empty_columns(rows: List[List[str]]) -> List[List[str]]:
    if not rows:
        return rows
    keep_indices = [
        idx for idx in range(max(len(row) for row in rows))
        if any(normalize_text(row[idx]) for row in rows if idx < len(row))
    ]
    return [[normalize_text(row[idx]) if idx < len(row) else "" for idx in keep_indices] for row in rows]


def classify_row(row: Sequence[str]) -> str:
    normalized = [normalize_text(cell) for cell in row if normalize_text(cell)]
    if not normalized:
        return "empty"
    joined = " | ".join(normalized)
    if all(UNIT_TOKEN_RE.search(cell) or cell in {"()", "(k=2)", "P", "F", "Pass", "Fail"} for cell in normalized):
        return "unit"
    if any(token in joined for token in ("Nominal", "Reference", "Error", "Limit", "Indicated", "U", "标称值", "标准值", "误差", "允许误差", "测量值", "指示值")):
        return "header"
    if all(re.fullmatch(r"[A-Za-z0-9_.+\-×/%() ]+", cell) for cell in normalized) and len(normalized) <= 3:
        return "structural_header"
    return "data"


def merge_header_rows(header_rows: Sequence[Sequence[str]]) -> List[str]:
    if not header_rows:
        return []
    width = max(len(row) for row in header_rows)
    merged: List[str] = []
    for col in range(width):
        parts: List[str] = []
        for row in header_rows:
            if col < len(row):
                text = normalize_text(row[col])
                if text and text not in parts:
                    parts.append(text)
        merged.append(" ".join(parts))
    return merged


def looks_like_measurement_table(headers: Sequence[str]) -> bool:
    joined = " | ".join(headers)
    tokens = ("Nominal", "Reference", "Error", "Limit", "Indicated", "U", "标称值", "标准值", "误差", "允许误差", "指示值")
    return sum(1 for token in tokens if token in joined) >= 2


class NominalReferenceErrorLimitUStrategy:
    name = "nominal_reference_error_limit_u"

    def matches(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> bool:
        joined = " | ".join(headers)
        return all(
            token in joined
            for token in ("Nominal", "Reference", "Error")
        ) or all(
            token in joined
            for token in ("标称值", "标准值", "误差")
        )

    def bind(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> ParsedRow:
        field_map = bind_by_header_alias(headers, row)
        semantic_target = infer_semantic_target(context.table_title, headers, field_map)
        return ParsedRow(
            semantic_target=semantic_target,
            fields=field_map,
            section_title=context.table_title,
            evidence={
                "row_shape": self.name,
                "header_bundle": " | ".join(headers),
            },
            confidence=0.9,
        )


class ReferenceIndicatedErrorLimitUStrategy:
    name = "reference_indicated_error_limit_u"

    def matches(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> bool:
        joined = " | ".join(headers)
        return all(
            token in joined
            for token in ("Reference", "Indicated", "Error")
        ) or all(
            token in joined
            for token in ("标准值", "指示值", "误差")
        )

    def bind(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> ParsedRow:
        field_map = bind_by_header_alias(headers, row)
        semantic_target = infer_semantic_target(context.table_title, headers, field_map)
        return ParsedRow(
            semantic_target=semantic_target,
            fields=field_map,
            section_title=context.table_title,
            evidence={
                "row_shape": self.name,
                "header_bundle": " | ".join(headers),
            },
            confidence=0.9,
        )


class CountAccuracyStrategy:
    name = "count_accuracy"

    def matches(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> bool:
        joined_title = normalize_text(context.table_title).lower()
        joined_headers = " | ".join(headers)
        return (
            "count" in joined_title or "计数" in joined_title
        ) and (
            "Reference" in joined_headers or "标准值" in joined_headers
        ) and (
            "Indicated" in joined_headers or "指示值" in joined_headers
        )

    def bind(self, headers: Sequence[str], row: Sequence[str], context: RowContext) -> ParsedRow:
        field_map = bind_by_header_alias(headers, row)
        return ParsedRow(
            semantic_target="count_accuracy",
            fields=field_map,
            section_title=context.table_title,
            evidence={
                "row_shape": self.name,
                "header_bundle": " | ".join(headers),
            },
            confidence=0.95,
        )


DEFAULT_STRATEGIES: Sequence[RowShapeStrategy] = (
    CountAccuracyStrategy(),
    NominalReferenceErrorLimitUStrategy(),
    ReferenceIndicatedErrorLimitUStrategy(),
)


def bind_by_header_alias(headers: Sequence[str], row: Sequence[str]) -> Dict[str, str]:
    alias_map = {
        "measure_value": ("Measurement", "Measured", "测量值"),
        "indicated_value": ("Indicated", "指示值"),
        "nominal_value": ("Nominal", "标称值", "Set Value", "设定值"),
        "reference_value": ("Reference", "标准值"),
        "error_value": ("Error", "误差"),
        "limit_value": ("Limit", "允许误差", "允许范围"),
        "cert_u": ("U", "U(k=2)", "U (k=2)"),
        "result_flag": ("Pass/Fail", "结论", "Conclusion"),
        "condition_value": ("Range", "量程", "Gate", "Gate Time", "Sample time", "取样时间", "闸门时间"),
    }
    bound: Dict[str, str] = {}
    for header, value in zip(headers, row):
        header_text = normalize_text(header)
        value_text = normalize_text(value)
        for field_name, aliases in alias_map.items():
            if any(alias in header_text for alias in aliases):
                bound[field_name] = value_text
                break
    return bound


def infer_semantic_target(title: str, headers: Sequence[str], field_map: Dict[str, str]) -> str:
    lowered_title = normalize_text(title).lower()
    header_text = " | ".join(headers)
    if "count" in lowered_title or "计数" in lowered_title:
        return "count_accuracy"
    if ("relative error" in header_text.lower() or "相对误差" in header_text) and "nominal_value" in field_map:
        return "period_accuracy"
    if "limit_value" in field_map and "error_value" in field_map and "reference_value" in field_map:
        return "period_accuracy"
    if "error_value" in field_map and "cert_u" in field_map:
        return "period_range"
    return "unknown"


def parse_measurement_table(table: TableGrid, strategies: Sequence[RowShapeStrategy]) -> tuple[List[ParsedRow], List[str]]:
    issues: List[str] = []
    parsed_rows: List[ParsedRow] = []
    context = RowContext(table_title=table.title)
    for raw_row in table.rows:
        row_kind = classify_row(raw_row)
        if row_kind in {"empty", "structural_header"}:
            continue
        if row_kind == "unit":
            for idx, cell in enumerate(raw_row):
                text = normalize_text(cell)
                if text:
                    context.inherited_units[idx] = text
            continue
        if row_kind == "header":
            context.header_rows.append(raw_row)
            continue

        headers = merge_header_rows(context.header_rows)
        if not looks_like_measurement_table(headers):
            issues.append(f"{table.title}: skip row without stable measurement headers -> {raw_row}")
            continue

        matched = False
        for strategy in strategies:
            if strategy.matches(headers, raw_row, context):
                parsed_rows.append(strategy.bind(headers, raw_row, context))
                matched = True
                break
        if not matched:
            issues.append(f"{table.title}: unclassified data row -> {raw_row}")
    return parsed_rows, issues


def parse_markdown_document(md_text: str, strategies: Sequence[RowShapeStrategy] = DEFAULT_STRATEGIES) -> ParsedDocument:
    meta = extract_meta(md_text)
    rows: List[ParsedRow] = []
    issues: List[str] = []
    for block in split_blocks(md_text):
        for table in extract_tables(block):
            parsed, table_issues = parse_measurement_table(table, strategies)
            rows.extend(parsed)
            issues.extend(table_issues)
    return ParsedDocument(meta=meta, rows=rows, parser_issues=issues)


__all__ = [
    "Block",
    "Cell",
    "ParsedDocument",
    "ParsedRow",
    "RowContext",
    "RowShapeStrategy",
    "TableGrid",
    "DEFAULT_STRATEGIES",
    "extract_meta",
    "extract_tables",
    "parse_markdown_document",
    "split_blocks",
]
