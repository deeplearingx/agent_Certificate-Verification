#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNAS 参数核验模块 - 重构版本
统一的参数核验系统，使用模块化设计
"""

import os
import json
import re
import time
import math
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer
from openai import OpenAI

from core.config import Config
from core.number_parser import NumberParser
from core.unit_converter import UnitConverter
from core.risk_verifier import RangeVerifier
from core.table_processor import TableProcessor
from core.report_generator import ReportGenerator

from config.settings import get_app_config
from llm.client import create_openai_client
from langchain_app.checks.parameter import (
    FirstCandidateDecider,
    infer_param_semantics,
    select_basis_with_audit,
)


# ===================== 1. 旧版本兼容函数 =====================
# 为了保持与现有代码的兼容性，我们提供对旧版本函数的访问

_parse_unicode_sci_number = NumberParser.parse_unicode_sci_number
parse_value_with_unit = NumberParser.parse_value_with_unit
to_plain_decimal = NumberParser.to_plain_decimal
_extract_value_token = NumberParser.extract_value_token
_extract_primary_unit_token = NumberParser.extract_primary_unit_token
_is_missing = NumberParser.is_missing
parse_single_sided_limit = RangeVerifier.parse_single_sided_limit
parse_range_limit = RangeVerifier.parse_range_limit
parse_symmetric_limit = RangeVerifier.parse_symmetric_limit
convert_time_unit = RangeVerifier.convert_time_unit
unit_convert_tool = UnitConverter.unit_convert_tool
_is_power_unit = UnitConverter.is_power_unit
_is_voltage_unit = UnitConverter.is_voltage_unit


# ===================== 2. 主要核验函数 =====================
def verify_range_logic(measure_val, range_str):
    """
    范围核验逻辑 - 使用新的模块化结构
    """
    from core.risk_verifier import RangeVerifier
    return json.dumps(RangeVerifier.verify_range_logic(measure_val, range_str), ensure_ascii=False)


def verify_error_logic(error_val, limit_val):
    """
    误差验证逻辑 - 兼容旧版本
    """
    from core.error_verifier import ErrorVerifier
    return ErrorVerifier.verify_error_logic(error_val, limit_val)


def verify_uncertainty_logic(measure_val, cert_u, kb_u):
    """
    不确定度验证逻辑 - 使用新的模块化结构
    """
    from core.uncertainty_verifier import UncertaintyVerifier
    return UncertaintyVerifier.verify_uncertainty_logic(measure_val, cert_u, kb_u)


def norm_code(s: str) -> str:
    """
    规范化代码
    """
    s = (s or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return re.sub(r"\s+", "", s).upper()


def extract_basis_code(criterion: str) -> Optional[str]:
    """
    提取依据代码（忽略年份后缀）
    """
    if not criterion:
        return None

    s = str(criterion)
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", s, re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"


def _pick_ux_from_measure_text(measure_val: str) -> Tuple[Optional[float], str, Optional[str]]:
    """
    从测量文本中提取 Ux
    """
    if not measure_val:
        return None, "ux_missing", None

    s = str(measure_val)

    special_patterns = [
        r"(?:开机特性|Warm-up(?:\s+Characteristics?)?)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
        r"(?:短期频率稳定度|频率稳定度|Short-Term(?:\s+Frequency)?\s+Stability)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    ]

    for pattern in special_patterns:
        m = re.search(pattern, s, flags=re.IGNORECASE)
        if m:
            token = NumberParser.extract_value_token(m.group(1))
            if token:
                v, u = NumberParser.parse_extracted_token(token, keep_sign=False)
                return v, f"ux_from_special:{token}", u

    m_ux = re.search(r"U[xX]\s*[:=]\s*([^,，;；<\n]+)", s)
    if m_ux:
        token = NumberParser.extract_value_token(m_ux.group(1))
        if token:
            v, u = NumberParser.parse_extracted_token(token, keep_sign=False)
            return v, f"ux_from_Ux:{token}", u

    return None, "ux_not_found", None


def calc_u_formula(expr: str, measure_val: str) -> Tuple[Optional[float], str]:
    """
    解析公式型不确定度
    """
    if not expr:
        return None, "expr_missing"

    s = str(expr).strip().replace(" ", "")
    s = s.replace("％", "%").replace("＋", "+").replace("﹢", "+")
    s = s.replace("—", "-").replace("−", "-")
    s = s.replace("×", "*")

    looks_like = ("u=" in s.lower()) or ("urel=" in s.lower()) or ("Ux" in s) or ("ux" in s) or ("%" in s) or ("+" in s)
    if not looks_like:
        return None, "not_formula"

    ux, ux_reason, _ux_unit_hint = _pick_ux_from_measure_text(measure_val)
    kb_u = 0.0
    parts_reason = []

    m_pct = re.search(r"([0-9]*\.?[0-9]+)%U[xX]", s)
    if m_pct:
        if ux is None:
            return None, f"need_Ux_but_missing ({ux_reason})"
        a_pct = float(m_pct.group(1)) / 100.0
        kb_u += ux * a_pct
        parts_reason.append(f"{a_pct}*Ux")

    const_found = False
    for m in re.finditer(r"\+([0-9]*\.?[0-9]+)\s*([a-zA-Z0-9μµ/²³]+)", s):
        num = m.group(1)
        unit = NumberParser.normalize_unit_text(m.group(2))
        v, _ = parse_value_with_unit(f"{num}{unit}", keep_sign=False)
        if v is None:
            return None, f"bad_add_unit:{num}{unit}"
        kb_u += v
        parts_reason.append(f"+{num}{unit}")
        const_found = True

    if not const_found:
        m_uconst = re.search(r"\bU\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z0-9μµ/²³]+)?", s, flags=re.IGNORECASE)
        if m_uconst:
            num = m_uconst.group(1)
            unit = NumberParser.normalize_unit_text(m_uconst.group(2) or "")
            v, _ = parse_value_with_unit(f"{num}{unit}", keep_sign=False)
            if v is None:
                return None, f"bad_U_const:{num}{unit}"
            kb_u += v
            parts_reason.append(f"U={num}{unit}")

    if kb_u == 0.0 and not parts_reason:
        return None, "formula_parse_empty"

    reason = f"U_formula({ux_reason}): {' '.join(parts_reason)} -> {to_plain_decimal(kb_u)}"
    return kb_u, reason


def _build_param_check_version_stamp() -> str:
    """
    生成版本戳
    """
    path = Path(__file__)
    stat = path.stat()
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return f"param_check_refactored.py | mtime={mtime} | sha1={digest}"


# ===================== 3. 辅助函数 =====================
def chunk_list(data: List[Any], size: int):
    """分块"""
    for i in range(0, len(data), size):
        yield data[i:i + size]


def pick_first(text: str, *patterns: str) -> Optional[str]:
    """第一个匹配"""
    if not text:
        return None
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def detect_uncertainty_info(text: str) -> Dict[str, Any]:
    """检测不确定度信息"""
    info = {"type": "N/A", "value": "N/A", "raw": None, "value_display": None}
    if not text:
        return info

    m_rel = re.search(r"U\s*rel\s*=\s*([^，,。；;]+)", text, flags=re.IGNORECASE)
    m_abs = re.search(r"\bU\s*=\s*([^，,。；;]+)", text, flags=re.IGNORECASE)

    if m_rel:
        raw_val = m_rel.group(1).strip()
        has_percent = "%" in raw_val
        num = NumberParser.parse_unicode_sci_number(raw_val)

        if num is None:
            m_num = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw_val)
            num = float(m_num.group(1)) if m_num else None

        if num is None:
            return info

        if has_percent:
            frac = num / 100.0
            info["type"] = "Urel"
            info["value"] = frac
            info["value_display"] = f"{num}%"
            info["raw"] = m_rel.group(0)
            return info
        else:
            info["type"] = "Urel"
            info["value"] = num
            if 1e-12 <= abs(num) < 1e-6:
                info["value_display"] = "{:.1e}".format(num)
            elif abs(num) < 1e-12:
                info["value_display"] = "{:.2e}".format(num)
            else:
                info["value_display"] = "{:.4g}".format(num)
            info["raw"] = m_rel.group(0)
            return info

    if m_abs:
        raw_val = m_abs.group(1).strip()
        is_formula = ("Ux" in raw_val) or ("ux" in raw_val) or ("+" in raw_val)

        if is_formula:
            info["type"] = "U_FORMULA"
            info["value"] = raw_val
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        num = NumberParser.parse_unicode_sci_number(raw_val)
        if num is None:
            m_num = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw_val)
            num = float(m_num.group(1)) if m_num else None

        if num is None:
            info["type"] = "U"
            info["value"] = raw_val
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        info["type"] = "U"
        info["value"] = raw_val
        info["value_display"] = raw_val
        info["raw"] = m_abs.group(0)
        return info

    return info


def ensure_dict(x) -> Dict[str, Any]:
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return {}
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def ensure_uncertainty(u, doc_text: str) -> Dict[str, Any]:
    if isinstance(u, dict):
        return u
    return detect_uncertainty_info(doc_text)


def validate_kb_range(range_str: str) -> bool:
    """验证KB范围的有效性"""
    try:
        parsed = parse_range_limit(range_str)
        if parsed:
            lower, upper = parsed
            if lower > upper:
                return False
            if lower < 0 and upper > 0:
                print(f"Warning: Range crosses zero: {lower} ~ {upper}")
            return True
        return False
    except Exception as e:
        print(f"Error validating range '{range_str}': {e}")
        return False


def validate_kb_entry(entry: Dict[str, Any]) -> bool:
    """验证知识库条目的完整性和正确性"""
    try:
        required_fields = ["file_code", "measured", "measure_range_text"]
        for field in required_fields:
            if field not in entry:
                raise KeyError(f"Missing required field: {field}")

        if not validate_kb_range(entry.get("measure_range_text", "")):
            raise ValueError(f"Invalid range in entry: {entry['measure_range_text']}")

        return True
    except Exception as e:
        print(f"Error validating KB entry: {e}")
        return False


def split_values_maybe_list(x) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x]
    return [p.strip() for p in re.split(r"[，,；;]\s*", str(x)) if p.strip()]


def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """解析KB条目"""
    meta = ensure_dict(meta)

    instrument_name = (
        meta.get("仪器名称")
        or meta.get("instrument_name")
        or pick_first(doc, r"仪器名称[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    standard_name = (
        meta.get("standard_name")
        or meta.get("校准依据")
        or pick_first(doc, r"校准依据[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    file_code = meta.get("file_code") or meta.get("规程代号") or None

    if not file_code:
        fc = pick_first(doc, r"\b(JJ[GF]|GJB)\s*\d+(?:\s*-\s*\d{4})?\b")
        if fc:
            m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", fc, re.IGNORECASE)
            file_code = f"{m.group(1).upper()} {m.group(2)}" if m else fc

    if (not file_code) and standard_name != "N/A":
        m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", standard_name, re.IGNORECASE)
        if m:
            file_code = f"{m.group(1).upper()} {m.group(2)}"

    if not file_code:
        file_code = standard_name if standard_name != "N/A" else "未知规程"

    measured = (
        meta.get("被测量")
        or meta.get("measured")
        or pick_first(doc, r"被测量[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    measure_range_text = (
        meta.get("测量范围")
        or meta.get("measure_range_text")
        or pick_first(doc, r"测量范围[：:]\s*(.+?)(?:[。；\n]|$)")
        or "-"
    )

    raw_u = meta.get("不确定度") or meta.get("uncertainty")
    uncertainty = ensure_uncertainty(raw_u, doc)

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
    """构建表格"""
    from core.report_generator import ReportGenerator
    return ReportGenerator.build_kb_table(entries, top_k)


# ===================== 4. 主要执行函数 =====================
def collect_certificate_params(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """收集证书参数"""
    params = []
    properties = data.get("properties", {})

    for key, value in properties.items():
        if key == "参数":
            params.extend(value.get("items", []))
        elif "参数" in key or "测量" in key or "指标" in key:
            if "items" in value:
                params.extend(value["items"])
            elif isinstance(value, dict) and "properties" in value:
                params.extend(value.get("items", []))

    return params


def run_agentic_batch(
        client,
        batch_params,
        kb_items,
        instrument_name,
        criterion,
        cfg
):
    """执行单个批次的 Agent 核验"""
    from llm.agent_mode import run_agent_mode_batch
    return run_agent_mode_batch(client, batch_params, kb_items, instrument_name, criterion, cfg)


def run_llm_mode(json_file: str, cfg, stop_event=None, embedder_obj=None) -> str:
    """
    LLM 模式执行入口
    """
    app_config = get_app_config()
    current_top_k = getattr(cfg, 'TOPK', app_config.topk)
    max_w = getattr(cfg, 'max_workers', app_config.max_workers)

    data = json.load(open(json_file, "r", encoding="utf-8"))
    try:
        root = data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        return "❌ JSON 结构错误"

    instrument_name = root.get("INSTRUMENT_NAME") or root.get("仪器名称") or "N/A"
    criteria_list = root.get("校准依据", []) or ["N/A"]
    all_cert_params = collect_certificate_params(data)

    if embedder_obj:
        embedder = embedder_obj
    else:
        print(f"🧠 [ParamCheck] 正在加载语义模型: {app_config.embed_model_path}")
        embedder = SentenceTransformer(app_config.embed_model_path)

    from kb.chroma_client import get_collection
    collection = get_collection(app_config.cnas_db_dir, app_config.cnas_collection)
    client = create_openai_client(api_key=app_config.api_key, api_base=app_config.api_base)

    report_lines = [
        "# CNAS 智能核验报告 (Refactored Mode)",
        f"- 证书编号: {root.get('证书编号', 'N/A')}",
        f"- 仪器: {instrument_name}",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 参数核验版本: {_build_param_check_version_stamp()}",
        ""
    ]

    for criterion in criteria_list:
        report_lines.append(f"## 依据: {criterion}")

        from kb.chroma_search import query_kb
        kb_items = query_kb(
            collection,
            embedder,
            instrument_name,
            criterion,
            topk=current_top_k
        )

        basis_code = extract_basis_code(criterion)
        basis_code_norm = norm_code(basis_code) if basis_code else None

        if basis_code_norm:
            kb_items_same_basis = [
                it for it in kb_items
                if norm_code(it.get("file_code")) == basis_code_norm
            ]

            if not kb_items_same_basis:
                for it in kb_items:
                    std_name = it.get("standard_name", "")
                    m2 = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", std_name, re.IGNORECASE)
                    if m2:
                        picked = f"{m2.group(1).upper()} {m2.group(2)}"
                        if norm_code(picked) == basis_code_norm:
                            kb_items_same_basis.append(it)

            if not kb_items_same_basis:
                report_lines.append("### ❌ 核验终止（依据一致性失败）")
                report_lines.append(
                    f"- 证书依据: {criterion}\n"
                    f"- 提取规程代号: {basis_code}\n"
                    f"- 结果: 知识库中找不到与该规程一致的条目，因此**跳过核验并返回 ERROR**。\n"
                    f"- 处理建议: 请补充/导入 {basis_code} 对应的 KB 条目后再核验。"
                )
                report_lines.append("\n---\n")
                continue

            kb_items = kb_items_same_basis
        else:
            report_lines.append("### ❌ 核验终止（依据代号无法解析）")
            report_lines.append(
                f"- 证书依据: {criterion}\n"
                f"- 结果: 无法从依据中解析 JJG/JJF 规程代号，系统不允许跨规程自动核验，因此返回 ERROR。"
            )
            report_lines.append("\n---\n")
            continue

        param_groups = {}
        for param in all_cert_params:
            param_name = param.get('param_name', 'unknown')
            if param_name not in param_groups:
                param_groups[param_name] = []
            param_groups[param_name].append(param)

        batches = []
        batch_param_names_map = {}
        current_batch = []

        for param_name, points in param_groups.items():
            if len(current_batch) + len(points) > app_config.batch_size:
                batches.append(current_batch)
                batch_param_names_map[len(batches)] = list(param_groups.keys())
                current_batch = []
            current_batch.extend(points)

        if current_batch:
            batches.append(current_batch)
            batch_param_names_map[len(batches)] = list(param_groups.keys())

        if max_w > 5:
            max_w = 5

        all_batch_contents = []
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_index = {}

            for idx, batch in enumerate(batches):
                future = executor.submit(
                    run_agentic_batch,
                    client,
                    batch,
                    kb_items,
                    instrument_name,
                    criterion,
                    cfg
                )
                future_to_index[future] = idx + 1

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    content = future.result(timeout=600)
                    content = enforce_kb_missing_fail(content)
                    content = enforce_point_id(content)
                    content = enforce_uncertainty_by_tool(content)
                    content = enforce_batch_summary_from_table(
                        content,
                        expected_param_names=batch_param_names_map.get(idx, [])
                    )
                    all_batch_contents.append(content)
                    print(f"✅ Batch {idx}/{len(batches)} 完成")
                except Exception as e:
                    print(f"🚨 Batch {idx} 失败: {e}")
                    all_batch_contents.append(f"> 任务被取消或执行异常: {e}")

        param_to_table = TableProcessor.collect_param_tables(
            all_batch_contents,
            batch_expected_params=batch_param_names_map
        )

        report_lines.append("## 📋 参数核验结果")
        for param_name, table_lines in param_to_table.items():
            report_lines.extend([
                f"### 参数：{param_name}",
                "\n".join(table_lines),
                ""
            ])

        final_stats = ReportGenerator().generate_final_statistics(param_to_table)
        report_lines.extend([
            "## 最终统计",
            f"- **通过**: {final_stats['pass']} 个测量点",
            f"- **失败**: {final_stats['fail']} 个测量点",
            f"- **需人工复核**: {final_stats['review']} 个测量点",
            f"- **KB未覆盖**: {final_stats['kb_missing_fail']} 个测量点",
            f"- **真实核验失败**: {final_stats['real_fail']} 个测量点",
            f"- **总计**: {final_stats['total']} 个测量点"
        ])

    return "\n".join(report_lines)


def main():
    """主入口函数"""
    BASE_DIR = Config._app.local_json_dir
    JSON_FILE = "1GA25003260-0015.json"
    JSON_PATH = str(BASE_DIR / JSON_FILE)

    cfg = Config()
    report = run_llm_mode(JSON_PATH, cfg)

    out_path = Path(cfg.OUTPUT_DIR) / f"Agent_Report_{Path(JSON_FILE).stem}.md"
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 完成! 报告已保存: {out_path}")


if __name__ == "__main__":
    main()
