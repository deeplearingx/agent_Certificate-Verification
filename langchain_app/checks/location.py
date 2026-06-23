#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准地点核验模块 - 与原始 location_check.py 功能完全兼容

重构后的 module 特点：
1. 使用 langchain_app 配置系统
2. 使用 retrieval 服务替代原始的 chroma 客户端
3. 使用 langchain_app 的 LLMClient
4. 与 VerificationState 状态类兼容
"""

import json
import re
import os
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

try:
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - pydantic 依赖已由运行时保证
    BaseModel = object  # type: ignore[assignment]

# 本地导入
from langchain_app.utils import get_app_config, AppConfig, coerce_app_config
from langchain_app.core import LLMClient, VerificationReport
from langchain_app.retrieval import AddressRetrievalService, create_address_retrieval_service
from langchain_app.retrieval import CnasRetrievalService, create_cnas_retrieval_service
from langchain_app.services.field_normalizer import load_and_normalize_certificate_json


# ========== 配置系统 ==========

def get_config(cfg: Optional[AppConfig] = None):
    """获取配置对象"""
    return coerce_app_config(cfg)


# ========== 工具函数 ==========

def extract_basis_code(text: str) -> Optional[str]:
    """规程代号解析/归一化"""
    if not text:
        return None
    s = str(text)
    m = re.search(
        r"\b(JJ[GF]|GJB)\s*(?:[\(（][^)\）]*[\)）])?\s*(\d+)(?:\s*-\s*\d{4})?\b",
        s,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"


def norm_code(code: str) -> str:
    """归一化代码格式"""
    code = (code or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", code, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return re.sub(r"\s+", "", code).upper()


def has_star_mark(name: str) -> bool:
    """检查仪器名称是否带*"""
    return ("*" in (name or "")) or ("＊" in (name or ""))


def is_specific_location(text: str) -> bool:
    """regex：库外地点“足够具体”判定"""
    if not text:
        return False
    s = str(text).strip()

    room_pat = r"(\broom\s*\d+\b)|(\d+\s*室)|(\d+\s*房)|(\d+\s*号房)|(\d+\s*楼\s*\d+\s*室)|(\d+\s*栋\s*\d+\s*室)|([A-Za-z]\s*\d{2,4})|(\d+-\d+)"
    if re.search(room_pat, s, flags=re.IGNORECASE):
        return True

    building_pat = r"(实验楼|办公楼|楼宇|大楼|园区|厂房|A座|B座|C座|D座|[A-Z]座|\d+栋|\d+号楼|\d+楼)"
    if re.search(building_pat, s):
        return True

    facility_pat = r"(恒温恒湿|屏蔽室|暗室|洁净室|计量室|校准室|检测室|标准室|无尘室|温湿度|振动|电磁兼容|车间|生产线|厂区|工位)"
    if re.search(facility_pat, s):
        return True

    return False


class LocationSpecificityResult(BaseModel):
    """Structured output contract for location specificity checks."""

    is_specific: bool = False
    reason: str = ""
    signals: List[str] = []


def _model_dump_compat(model: Any) -> Dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return dict(model.model_dump())
    if hasattr(model, "dict"):
        return dict(model.dict())
    if isinstance(model, dict):
        return dict(model)
    return {}


# ========== LLM 调用模块 ==========

def llm_is_specific_location(llm_client: Optional[LLMClient], location_text: str) -> Dict[str, Any]:
    """
    大模型审核具体地点是否足够具体
    """
    system_prompt = (
        "你是一名计量/校准质量核验专家。\n"
        "任务：判断给定的“校准地点描述”是否足够具体。\n\n"
        "判定为【足够具体】需要至少满足以下之一：\n"
        "1) 明确到房间/门牌/编号（如203室、A-203、Room 302、9栋204室）\n"
        "2) 明确到楼层/楼栋/座/号楼（如D3栋3楼、A座、9栋）\n"
        "3) 明确到特定功能场所/设施（如恒温恒湿实验室、屏蔽室、暗室、洁净室、计量室、校准室）\n"
        "4) 明确到车间/厂房/生产线/区域（如××车间、D区、厂房1号）\n\n"
        "注意：仅有城市/区县/道路/园区名但缺少以上细节，通常判定为不具体。\n"
        "输出必须是JSON，且只输出JSON，不要输出任何多余文字。"
    )

    user_prompt = (
        f"校准地点描述：{location_text}\n\n"
        "请输出JSON，格式严格为：\n"
        '{{ "is_specific": true/false, "reason": "...", "signals": ["..."] }}\n'
        "signals里放你识别到的具体性线索类别，例如：楼层/房间/实验室/车间/楼栋/区域/编号 等。"
    )

    client = llm_client
    if client is None:
        return {"is_specific": False, "reason": "LLM客户端未初始化", "signals": []}

    try:
        result = client.invoke_structured(user_prompt, LocationSpecificityResult, system_prompt)
        payload = _model_dump_compat(result)
    except Exception:
        try:
            resp = client.invoke_text(user_prompt, system_prompt)
            txt = resp.strip()
            txt = re.sub(r"^```json\s*|\s*```$", "", txt, flags=re.IGNORECASE).strip()
            payload = json.loads(txt)
        except Exception as e:
            return {"is_specific": False, "reason": f"LLM调用/解析失败: {e}", "signals": []}

    if not isinstance(payload, dict) or "is_specific" not in payload:
        return {"is_specific": False, "reason": "LLM输出JSON结构异常", "signals": []}

    signals = payload.get("signals")
    return {
        "is_specific": bool(payload.get("is_specific")),
        "reason": str(payload.get("reason", "")).strip(),
        "signals": [str(item).strip() for item in signals if str(item).strip()] if isinstance(signals, list) else [],
    }


# ========== 检索服务调用 ==========

def search_instruments_by_basis_code(
    cfg: AppConfig,
    basis_or_criterion: str,
    use_where_document: bool = True,
    where_variants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """CNAS库检索：按规程找“仪器是否带*”"""
    basis = extract_basis_code(basis_or_criterion)
    if not basis:
        raise ValueError(f"无法从输入中解析规程代号：{basis_or_criterion}")
    basis_norm = norm_code(basis)

    cnas_service = create_cnas_retrieval_service(cfg)

    query_text = f"{basis} {basis_or_criterion}".strip()

    if where_variants is None:
        where_variants = [basis, basis_norm, basis.replace(" ", "")]

    last_res = None
    used_where = None

    search_results = cnas_service.search_calibration_data(query_text)

    raw_hits: List[Dict[str, Any]] = []
    for doc in search_results:
        metadata = doc.metadata
        fc = metadata.get("校准依据", "未知规程")
        if norm_code(fc) != basis_norm:
            continue
        inst = metadata.get("仪器名称", "N/A")
        raw_hits.append({
            "instrument_name": inst,
            "has_star": has_star_mark(inst),
            "file_code": fc,
            "distance": doc.metadata.get("distance", 0.0),
            "kb_basis_text": metadata.get("校准依据"),
        })

    # 去重：同名取最小 distance
    best: Dict[str, Dict[str, Any]] = {}
    for h in raw_hits:
        k = h["instrument_name"]
        if k not in best:
            best[k] = h
        else:
            if h["distance"] is not None and (best[k]["distance"] is None or h["distance"] < best[k]["distance"]):
                best[k] = h

    instruments = list(best.values())
    instruments.sort(key=lambda x: (x["distance"] is None, x["distance"]))

    return {
        "basis": basis,
        "basis_norm": basis_norm,
        "used_where_contains": used_where,
        "hits_total": len(raw_hits),
        "instruments": instruments,
    }


def search_address_in_db(cfg: AppConfig, location_text: str, topk: int = 5) -> List[Dict[str, Any]]:
    """地址库检索"""
    address_service = create_address_retrieval_service(cfg)
    search_results = address_service.search_addresses(location_text, topk)

    out = []
    for doc in search_results:
        metadata = doc.metadata
        out.append({
            "校准地址": metadata.get("校准地址", ""),
            "专业室": metadata.get("专业室", ""),
            "序号": metadata.get("序号", ""),
            "distance": doc.metadata.get("distance", 0.0),
            "doc": doc.page_content,
        })
    return out


# ========== 核验逻辑 ==========

def verify_calibration_location(
    cfg: AppConfig,
    location_text: str,
    has_star: bool,
    topk: int = 5,
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """校准地点核验（按*号分流）"""
    loc = (location_text or "").strip()
    if not loc:
        return {
            "status": "FAIL",
            "reason": "校准地点字段为空/缺失",
            "has_star": has_star,
            "matched_db": False,
            "contains_hit": False,
            "contains_addr": None,
            "best_dist": None,
            "threshold": None,
            "specificity_source": None,
            "specificity_detail": None,
            "db_hits": [],
        }

    hits = search_address_in_db(cfg, loc, topk=topk)
    best = hits[0] if hits else None
    best_dist = best["distance"] if best else None

    # 子串命中（更接近“是否一样”的解释）
    contains_hit = False
    contains_addr = None
    for h in hits:
        addr = (h.get("校准地址") or "").strip()
        if addr and (addr in loc or loc in addr):
            contains_hit = True
            contains_addr = addr
            break

    MUST_MATCH_THRESHOLD = getattr(cfg, "must_match_threshold", 0.45)
    OPTIONAL_MATCH_THRESHOLD = getattr(cfg, "optional_match_threshold", 0.45)
    thr = OPTIONAL_MATCH_THRESHOLD

    def matched_db(strict: bool) -> Tuple[bool, float]:
        thr = MUST_MATCH_THRESHOLD if strict else OPTIONAL_MATCH_THRESHOLD
        if contains_hit:
            return True, thr
        if best_dist is None:
            return False, thr
        return (best_dist <= thr), thr

    # ---------- 带* ----------
    if has_star:
        ok, thr = matched_db(strict=False)
        if ok:
            return {
                "status": "PASS",
                "reason": f"仪器带*：地点命中地址库（best_dist={best_dist}) 或包含库内地址",
                "has_star": True,
                "matched_db": True,
                "contains_hit": contains_hit,
                "contains_addr": contains_addr,
                "best_dist": best_dist,
                "threshold": thr,
                "specificity_source": "db",
                "specificity_detail": None,
                "db_hits": hits,
            }

        if cfg.use_llm_location_check:
            llm_judge = llm_is_specific_location(llm_client, loc)
            if llm_judge["is_specific"]:
                return {
                    "status": "PASS",
                    "reason": "仪器带*：地点未命中地址库，但LLM判定地点描述足够具体",
                    "has_star": True,
                    "matched_db": False,
                    "contains_hit": contains_hit,
                    "contains_addr": contains_addr,
                    "best_dist": best_dist,
                    "threshold": thr,
                    "specificity_source": "llm",
                    "specificity_detail": llm_judge,
                    "db_hits": hits,
                }
            else:
                return {
                    "status": "FAIL",
                    "reason": "仪器带*：地点未命中地址库，且LLM判定描述不够具体（需具体到楼栋/楼层/房间/设施/车间等）",
                    "has_star": True,
                    "matched_db": False,
                    "contains_hit": contains_hit,
                    "contains_addr": contains_addr,
                    "best_dist": best_dist,
                    "threshold": thr,
                    "specificity_source": "llm",
                    "specificity_detail": llm_judge,
                    "db_hits": hits,
                }

        # 不用LLM，走regex
        if is_specific_location(loc):
            return {
                "status": "PASS",
                "reason": "仪器带*：地点未命中地址库，但代码识别到地点描述足够具体",
                "has_star": True,
                "matched_db": False,
                "contains_hit": contains_hit,
                "contains_addr": contains_addr,
                "best_dist": best_dist,
                "threshold": thr,
                "specificity_source": "regex",
                "specificity_detail": None,
                "db_hits": hits,
            }

        return {
            "status": "FAIL",
            "reason": "仪器带*：地点未命中地址库，且代码未识别到楼栋/楼层/房间/设施/车间等",
            "has_star": True,
            "matched_db": False,
            "contains_hit": contains_hit,
            "contains_addr": contains_addr,
            "best_dist": best_dist,
            "threshold": thr,
            "specificity_source": "regex",
            "specificity_detail": None,
            "db_hits": hits,
        }

    # ---------- 不带* ----------
    ok, thr = matched_db(strict=True)
    if ok:
        return {
            "status": "PASS",
            "reason": f"仪器不带*：地点命中地址库（best_dist={best_dist}) 或包含库内地址",
            "has_star": False,
            "matched_db": True,
            "contains_hit": contains_hit,
            "contains_addr": contains_addr,
            "best_dist": best_dist,
            "threshold": thr,
            "specificity_source": "db",
            "specificity_detail": None,
            "db_hits": hits,
        }

    return {
        "status": "FAIL",
        "reason": "仪器不带*：地点必须来自地址库，但当前地点未匹配到库内校准地址",
        "has_star": False,
        "matched_db": False,
        "contains_hit": contains_hit,
        "contains_addr": contains_addr,
        "best_dist": best_dist,
        "threshold": thr,
        "specificity_source": "db",
        "specificity_detail": None,
        "db_hits": hits,
    }


# ========== JSON 解析 ==========

def read_json_props(json_file: str) -> Dict[str, Any]:
    _, props = load_and_normalize_certificate_json(json_file)
    return props


def get_json_inputs_from_props(props: Dict[str, Any]) -> Tuple[str, List[str], str]:
    instrument_name = props.get("仪器名称") or "N/A"
    criteria_list = props.get("校准依据", []) or []
    location_text = props.get("校准地点") or ""

    if isinstance(location_text, (list, dict)):
        location_text = json.dumps(location_text, ensure_ascii=False)

    return str(instrument_name), [str(x) for x in criteria_list], str(location_text)


# ========== 报告渲染 ==========

def render_cnas_instrument_table(basis_details: List[Dict[str, Any]]) -> str:
    """报告渲染：CNAS 仪器明细表"""
    lines: List[str] = []
    lines.append("## CNAS 仪器检索明细（用于*号判定）")

    flat: List[Dict[str, Any]] = []
    for out in basis_details:
        basis = out.get("basis", "N/A")
        used_where = out.get("used_where_contains", None)
        for it in out.get("instruments", []) or []:
            x = dict(it)
            x["_basis"] = basis
            x["_used_where"] = used_where
            flat.append(x)

    if not flat:
        lines.append("> CNAS 仪器库未检索到与证书依据一致的仪器记录（instruments=0）。")
        lines.append("- *号最终判定：**False**（未检到仪器，默认False）")
        return "\n".join(lines)

    lines.append("| 序号 | 依据 | used_where | 仪器名称 | 是否带* | file_code | distance |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for i, it in enumerate(flat, 1):
        dist = it.get("distance")
        dist_str = f"{dist:.4f}" if isinstance(dist, (int, float)) else "N/A"
        lines.append(
            f"| {i} | {it.get('_basis','')} | {it.get('_used_where','')} | "
            f"{it.get('instrument_name','')} | {it.get('has_star', False)} | "
            f"{it.get('file_code','')} | {dist_str} |"
        )

    is_star = any(x.get("has_star") for x in flat)
    lines.append("")
    lines.append(f"- *号最终判定：**{is_star}**（只要任意命中仪器名含*即为True）")
    return "\n".join(lines)


# ========== 主核验函数 ==========

def check_location(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    校准地点核验入口（与原始函数完全兼容）

    Args:
        json_file: JSON 文件路径
        cfg: 配置对象

    Returns:
        核验报告（Markdown 格式）
    """
    cfg = get_config(cfg)

    props = read_json_props(json_file)
    instrument_in_json, criteria_list, location_text = get_json_inputs_from_props(props)

    if not criteria_list:
        return "[错误] JSON 中未找到 '校准依据'，无法进行*号判定。"

    basis_details: List[Dict[str, Any]] = []
    for criterion in criteria_list:
        out = search_instruments_by_basis_code(
            cfg=cfg,
            basis_or_criterion=criterion,
            use_where_document=True,
        )
        basis_details.append(out)

    has_star = any(any(it["has_star"] for it in out["instruments"]) for out in basis_details)

    client = llm_client
    if client is None and cfg.use_llm_location_check:
        try:
            client = LLMClient(config=cfg)
        except Exception:
            client = None

    loc_res = verify_calibration_location(
        cfg=cfg,
        location_text=location_text,
        has_star=has_star,
        topk=5,
        llm_client=client,
    )

    # ============ 报告输出 ============
    report = VerificationReport()
    report.add_section("## [完成] 校准地点核验报告")
    report.add_section(f"- JSON: {Path(json_file).name}")
    report.add_section(f"- 仪器(证书): {instrument_in_json}")
    report.add_section(f"- 校准地点(证书): {location_text}")
    report.add_section(f"- 是否带*(来自CNAS库): {has_star}")
    report.add_section("")

    report.add_section(render_cnas_instrument_table(basis_details))
    report.add_section("")

    report.add_section("### 结论")
    report.add_section(f"- 判定: **{loc_res['status']}**")
    report.add_section(f"- 说明: {loc_res['reason']}")
    report.add_section(f"- matched_db: {loc_res.get('matched_db')}")
    report.add_section(f"- contains_hit: {loc_res.get('contains_hit')} | contains_addr: {loc_res.get('contains_addr')}")
    report.add_section(f"- best_dist: {loc_res.get('best_dist')} | threshold: {loc_res.get('threshold')}")
    report.add_section(f"- 具体性判定来源: {loc_res.get('specificity_source', 'N/A')}")
    if loc_res.get("specificity_source") == "llm":
        detail = loc_res.get("specificity_detail") or {}
        report.add_section(
            f"- LLM判定: is_specific={detail.get('is_specific')} | "
            f"signals={detail.get('signals')} | reason={detail.get('reason')}"
        )

    report.add_section("")
    report.add_section("### 地址库 Top 命中")
    report.add_section("| Top | distance | 序号 | 专业室 | 校准地址 |")
    report.add_section("| --- | --- | --- | --- | --- |")
    for i, h in enumerate(loc_res.get("db_hits", [])[:5], 1):
        dist = h.get("distance")
        dist_str = f"{dist:.4f}" if isinstance(dist, (int, float)) else "N/A"
        report.add_section(f"| {i} | {dist_str} | {h.get('序号','')} | {h.get('专业室','')} | {h.get('校准地址','')} |")

    return report.render()


# ==================== 兼容旧接口 ====================

def location_check_wrapper(json_path: str, config):
    """
    兼容性函数，用于直接调用校准地点核验

    Args:
        json_path: JSON 文件路径
        config: 配置对象（原始 AppConfig）

    Returns:
        核验报告
    """
    return check_location(json_path, config)
