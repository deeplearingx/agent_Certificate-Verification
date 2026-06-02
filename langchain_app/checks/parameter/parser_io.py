#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameter parsing IO / KB helper layer.

This module owns KB metadata normalization, table building, and report-adjacent
helpers that are used by the parameter pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .parser_core import (
    extract_value_token,
    parse_range_limit,
    parse_unicode_sci_number,
    parse_value_with_unit,
    to_plain_decimal,
)

def chunk_list(data: List[Any], size: int):
    for i in range(0, len(data), size): yield data[i:i + size]


def pick_first(text: str, *patterns: str) -> Optional[str]:
    if not text: return None
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m: return m.group(1).strip()
    return None


def detect_uncertainty_info(text: str) -> Dict[str, Any]:
    """
    从 KB 文本中提取不确定度信息。
    支持：
      - U = 0.00123
      - U = 0.28%          (注意：这是“相对百分数写在U里”，不当公式)
      - Urel = 0.5 %
      - Urel=6.6×10⁻⁹
      - U = 0.1%Ux+0.04mV  (公式型)
    """
    info = {"type": "N/A", "value": "N/A", "raw": None, "value_display": None}
    if not text:
        return info

    m_rel = re.search(r"U\s*rel\s*=\s*([^，,。；;”\"]+)", text, flags=re.IGNORECASE)
    m_abs = re.search(r"\bU\s*=\s*([^，,。；;”\"]+)", text, flags=re.IGNORECASE)

    # -------- 优先 Urel --------
    if m_rel:
        raw_val = m_rel.group(1).strip()
        has_interval = any(sep in raw_val for sep in ("~", "～"))

        if has_interval:
            info["type"] = "Urel"
            info["value"] = raw_val
            info["value_display"] = raw_val
            info["raw"] = m_rel.group(0)
            return info

        has_percent = "%" in raw_val

        num = parse_unicode_sci_number(raw_val)
        if num is None:
            m_num = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw_val)
            num = float(m_num.group(1)) if m_num else None

        if num is None:
            return info

        if has_percent:
            frac = num / 100.0
            info["type"] = "Urel"
            info["value"] = frac                 # 计算用：0.0028
            info["value_display"] = f"{num}%"
            info["raw"] = m_rel.group(0)
            return info

        info["type"] = "Urel"
        info["value"] = num
        # 优化显示：使用科学计数法，保留2位有效数字
        if 1e-12 <= abs(num) < 1e-6:
            info["value_display"] = "{:.1e}".format(num)
        elif abs(num) < 1e-12:
            info["value_display"] = "{:.2e}".format(num)
        else:
            info["value_display"] = "{:.4g}".format(num)
        info["raw"] = m_rel.group(0)
        return info

    # -------- 再处理 U --------
    if m_abs:
        raw_val = m_abs.group(1).strip()

        # ✅ 只有 Ux/ux 或 + 才视为公式
        is_formula = (("Ux" in raw_val) or ("ux" in raw_val) or ("+" in raw_val))

        if is_formula:
            info["type"] = "U_FORMULA"
            info["value"] = raw_val              # 保留公式原串
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        # ✅ 非公式：允许是纯数字，也允许是百分数(如 0.28%)
        # 1) 先试 unicode 科学计数法
        num = parse_unicode_sci_number(raw_val)

        # 2) 若不是 unicode 科学计数法，尝试普通数字
        if num is None:
            m_num = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw_val)
            num = float(m_num.group(1)) if m_num else None

        if any(sep in raw_val for sep in ("~", "～")):
            info["type"] = "U"
            info["value"] = raw_val
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        # 3) 如果连数字都没有（比如 raw_val="0.28%" 其实能抓到 0.28，不会进这里）
        if num is None:
            # 兜底：把原串保留下来，后续 parse_value_with_unit(base_val) 仍可能处理
            info["type"] = "U"
            info["value"] = raw_val
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        # 4) 这里不把 % 转 fraction（因为 U 本身可能是百分数表达）
        #    让后续 parse_value_with_unit(cert_u/kb_u, base_val) 来决定是否转绝对值
        info["type"] = "U"
        info["value"] = raw_val                  # ✅ 保留原串（例如 "0.28%" 或 "0.00123"）
        info["value_display"] = raw_val
        info["raw"] = m_abs.group(0)
        return info

    # ✅ 必须兜底 return
    return info

def ensure_dict(x) -> Dict[str, Any]:
    """把 metadata 强制变成 dict（兼容 str / None / 乱七八糟类型）"""
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    # Chroma/LlamaIndex 有时会把 metadata 序列化成 JSON 字符串
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return {}
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}  # 其他类型一律丢弃

def ensure_uncertainty(u, doc_text: str) -> Dict[str, Any]:
    """确保 uncertainty 一定是 dict。否则回退到从 doc 里抽取。"""
    if isinstance(u, dict):
        return u
    # 如果 meta 里存的是字符串（比如 "Urel=..." 或 "0.28%"），就别信它，直接用 doc 抽
    return detect_uncertainty_info(doc_text)




def validate_kb_range(range_str: str) -> bool:
    """
    验证知识库范围的有效性
    """
    try:
        parsed = parse_range_limit(range_str)
        if parsed:
            lower, upper = parsed
            if lower > upper:
                raise ValueError(f"Invalid range: lower bound {lower} > upper bound {upper}")
            # 检查范围是否合理（例如，不能有负数下限的对称范围）
            if lower < 0 and upper > 0:
                print(f"Warning: Range crosses zero: {lower} ~ {upper}")
            return True
        return False
    except Exception as e:
        print(f"Error validating range '{range_str}': {e}")
        return False


def validate_kb_entry(entry: Dict[str, Any]) -> bool:
    """
    验证知识库条目的完整性和正确性
    """
    try:
        # 检查基本字段
        required_fields = ["file_code", "measured", "measure_range_text"]
        for field in required_fields:
            if field not in entry:
                raise KeyError(f"Missing required field: {field}")

        # 验证范围
        if not validate_kb_range(entry.get("measure_range_text", "")):
            raise ValueError(f"Invalid range in entry: {entry['measure_range_text']}")

        return True
    except Exception as e:
        print(f"Error validating KB entry: {e}")
        return False


def split_values_maybe_list(x) -> List[str]:
    if x is None: return []
    if isinstance(x, list): return [str(v) for v in x]
    return [p.strip() for p in re.split(r"[，,；;]\s*", str(x)) if p.strip()]


# def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
#     # 1. 提取仪器名称 (之前缺失的定义)
#     instrument_name = meta.get("仪器名称") or pick_first(doc, r"仪器名称[：:]\s*(.+?)[。；]") or "N/A"
#     file_code = meta.get("file_code") or meta.get("规程代号") or None

#     # 2. 提取校准依据
#     standard_name = meta.get("校准依据") or pick_first(doc, r"校准依据[：:]\s*(.+?)[。；\n]") or "N/A"

#     # 3. 提取规程编号 (优化后的正则逻辑)
#     # 匹配 JJG/JJF 开头，允许中间有空格，必须有数字
#     file_code = pick_first(doc, r"\b(JJ[GF]|GJB)\s*\d+(?:\s*-\s*\d{4})?\b")
#     if file_code:
#         # 统一标准化：只保留 前缀 + 数字，忽略年份
#         m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", file_code, re.IGNORECASE)
#         file_code = f"{m.group(1).upper()} {m.group(2)}" if m else file_code

#     # 如果正则没抓到，尝试从 standard_name 里再抓一次
#     if not file_code and standard_name != "N/A":
#         m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", standard_name, re.IGNORECASE)
#         if m:
#             file_code = f"{m.group(1).upper()} {m.group(2)}"

#     # 兜底逻辑：实在抓不到编号，就用规程名称代替，防止 N/A
#     if not file_code:
#         file_code = standard_name if standard_name != "N/A" else "未知规程"

#     # 4. 提取被测量
#     measured = pick_first(doc, r"被测量[：:]\s*(.+?)[。；]") or "N/A"

#     # 5. 提取测量范围
#     measure_range_text = pick_first(doc, r"测量范围[：:]\s*(.+?)[。；]") or "-"

#     # 6. 提取不确定度
#     uncertainty = detect_uncertainty_info(doc)

#     return {
#         "instrument_name": instrument_name,
#         "standard_name": standard_name,
#         "file_code": file_code,
#         "measured": measured,
#         "measure_range_text": measure_range_text,
#         "uncertainty": uncertainty,
#         "raw": doc,
#         "meta": meta or {},
#     }

def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    meta = ensure_dict(meta)  # ✅ 根治：不管传进来是啥，先变 dict

    # 1) 仪器名称
    instrument_name = (
        meta.get("仪器名称")
        or meta.get("instrument_name")
        or pick_first(doc, r"仪器名称[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    # 2) 校准依据（标准名称）
    standard_name = (
        meta.get("standard_name")
        or meta.get("校准依据")
        or pick_first(doc, r"校准依据[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    # 3) 规程代号 file_code
    file_code = meta.get("file_code") or meta.get("规程代号") or None

    # 3.1) meta 没给 -> doc 抓
    if not file_code:
        fc = pick_first(doc, r"\b(JJ[GF]|GJB)\s*\d+(?:\s*-\s*\d{4})?\b")
        if fc:
            m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", fc, re.IGNORECASE)
            file_code = f"{m.group(1).upper()} {m.group(2)}" if m else fc

    # 3.2) doc 也没抓到 -> standard_name 抓
    if (not file_code) and standard_name != "N/A":
        m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", standard_name, re.IGNORECASE)
        if m:
            file_code = f"{m.group(1).upper()} {m.group(2)}"

    # 3.3) 兜底
    if not file_code:
        file_code = standard_name if standard_name != "N/A" else "未知规程"

    # 4) 被测量
    measured = (
        meta.get("被测量")
        or meta.get("measured")
        or pick_first(doc, r"被测量[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    # 5) 测量范围
    measure_range_text = (
        meta.get("测量范围")
        or meta.get("measure_range_text")
        or pick_first(doc, r"测量范围[：:]\s*(.+?)(?:[。；\n]|$)")
        or "-"
    )

    # 6) 不确定度：强制 dict
    raw_u = meta.get("不确定度") or meta.get("uncertainty")
    uncertainty = ensure_uncertainty(raw_u, doc)  # ✅ 根治 build_table 的 .get 报错

    return {
        "instrument_name": instrument_name,
        "standard_name": standard_name,
        "file_code": file_code,
        "measured": measured,
        "measure_range_text": measure_range_text,
        "uncertainty": uncertainty,
        "raw": doc,
        "meta": meta,
    }


def build_table(entries: List[Dict[str, Any]], top_k: int = 10) -> str:
    table_lines = ["| 序号 | 仪器 | 规范(代号) | 被测量 | 测量范围摘录 | 不确定度 |",
                   "| --- | --- | --- | --- | --- | --- |"]
    for i, e in enumerate(entries[:top_k], 1):
        utype = e["uncertainty"].get("type", "N/A")
        uval = e["uncertainty"].get("value", "N/A")
        uinfo = f"{utype}={uval}" if uval != "N/A" else "N/A"
        table_lines.append(
            f"| {i} | {e['instrument_name']} | {e['standard_name']}/{e['file_code']} | {e['measured']} | {e['measure_range_text'][:60]} | {uinfo} |")
    if len(entries) > top_k:
        table_lines.append("")
        table_lines.append(
            f"> 注：上表仅预览前 {top_k} 条，实际后续核验使用的是当前依据命中的全部 {len(entries)} 条 KB 条目。"
        )
    return "\n".join(table_lines)
