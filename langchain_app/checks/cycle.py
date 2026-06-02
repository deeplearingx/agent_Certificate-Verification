#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准周期核验模块 - 与原始 cycle_check.py 功能完全兼容

重构后的 module 特点：
1. 使用 langchain_app 配置系统
2. 使用 retrieval 服务替代原始的 chroma 客户端
3. 使用 langchain_app 的 LLMClient
4. 与 VerificationState 状态类兼容
"""

import json
import re
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

# 本地导入
from langchain_app.utils import get_app_config, AppConfig, coerce_app_config
from langchain_app.core import LLMClient, VerificationReport
from langchain_app.retrieval import CycleRetrievalService, create_cycle_retrieval_service

try:
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - pydantic v1/v2兼容层已由依赖保证
    BaseModel = object  # type: ignore[assignment]


# ========== 配置系统 ==========

def get_config(cfg: Optional[AppConfig] = None):
    """获取配置对象"""
    return coerce_app_config(cfg)


# ========== 工具函数 ==========

def parse_date(date_str: str):
    """尝试解析常见日期格式，失败返回 None"""
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _normalize_common(s: str) -> str:
    """通用归一化：去首尾空白、统一全角符号、移除所有空格"""
    if s is None:
        return ""
    s = str(s).strip()

    s = (s.replace("（", "(").replace("）", ")")
           .replace("～", "~").replace("〜", "~")
           .replace("－", "-").replace("–", "-").replace("—", "-"))

    s = re.sub(r"\s+", "", s)
    return s


def normalize_temperature_value(temp_str: str) -> str:
    """温度归一化"""
    s = _normalize_common(temp_str)

    s = s.replace("°C", "℃").replace("°c", "℃")

    if s.startswith("(") and s.endswith("℃") and ")" in s:
        inner = s[1:s.rfind(")")]
        tail = s[s.rfind(")")+1:]
        s = inner + tail
    elif s.startswith("(") and s.endswith(")") and len(s) > 2:
        s = s[1:-1]

    s = re.sub(r"(?<=\d)-(?=\d)", "~", s)

    return s


def normalize_humidity_value(rh_str: str) -> str:
    """湿度归一化"""
    s = _normalize_common(rh_str)
    s = s.replace("％", "%")
    return s


class CycleLLMResult(BaseModel):
    """LLM 周期核验输出的结构化结果。"""

    find: int = 0
    reason: str = ""
    table: str = ""


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


# ========== 日期校准逻辑 ==========

def check_date_logic(receive_date_str: str, calibrate_date_str: str):
    """判断接收日期是否早于校准日期"""
    receive_date = parse_date(receive_date_str)
    calibrate_date = parse_date(calibrate_date_str)

    if not receive_date or not calibrate_date:
        return {
            "pass": False,
            "reason": "接收日期或校准日期缺失或格式无法识别"
        }

    if receive_date <= calibrate_date:
        return {
            "pass": True,
            "reason": f"接收日期({receive_date_str}) 早于或等于 校准日期({calibrate_date_str})，日期逻辑正确"
        }
    else:
        return {
            "pass": False,
            "reason": f"接收日期({receive_date_str}) 晚于 校准日期({calibrate_date_str})，日期逻辑错误"
        }


def check_env_consistency(temp: str, rh: str, temp_in: str, rh_in: str):
    """比较温度/湿度与内页是否一致"""
    def _is_empty(x):
        return x is None or str(x).strip() == ""

    if any(_is_empty(x) for x in [temp, rh, temp_in, rh_in]):
        return {
            "enabled": False,
            "pass": False,
            "reason": "温度/湿度字段存在空值，跳过一致性比对。",
            "detail": {}
        }

    t1 = normalize_temperature_value(temp)
    t2 = normalize_temperature_value(temp_in)
    h1 = normalize_humidity_value(rh)
    h2 = normalize_humidity_value(rh_in)

    temp_same = (t1 == t2)
    rh_same = (h1 == h2)

    overall = temp_same and rh_same

    detail = {
        "温度_raw": temp,
        "温度_内页_raw": temp_in,
        "温度_norm": t1,
        "温度_内页_norm": t2,
        "相对湿度_raw": rh,
        "相对湿度_内页_raw": rh_in,
        "相对湿度_norm": h1,
        "相对湿度_内页_norm": h2,
        "温度一致": temp_same,
        "湿度一致": rh_same,
    }

    if overall:
        reason = "温度与温度_内页一致，且相对湿度与相对湿度_内页一致。"
    else:
        parts = []
        if not temp_same:
            parts.append("温度不一致")
        if not rh_same:
            parts.append("湿度不一致")
        reason = "；".join(parts) + "（基于归一化后对比）"

    return {
        "enabled": True,
        "pass": overall,
        "reason": reason,
        "detail": detail
    }


# ========== LLM 调用模块 ==========

def verify_cycle_with_llm(
    llm_client: Optional[LLMClient],
    client_name: str,
    instrument_name: str,
    criterion: str,
    report_cycle: str,
    db_entries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """调用 LLM 判断证书记录周期是否合理"""
    system_prompt = (
        "你是一名实验室质量核验专家。任务是：判断证书中记录的校准周期是否与建议周期一致。\n"
        "输出必须严格遵守 JSON 格式，不允许有其他文字。\n"
        "JSON 字段要求：\n"
        "- find: 0表示数据库没有匹配, 1表示有匹配(包括使用了默认标准)\n"
        "- reason: 核验说明文字\n"
        "- table: Markdown 表格字符串，如无匹配可为空\n"
        "如果数据库建议周期为空且无默认标准，请返回 find:0。\n"
        "如果有匹配记录（或默认标准），请返回 find:1，并生成表格对比证书值与建议值。\n"
    )

    db_text = ""
    for i, rec in enumerate(db_entries, 1):
        db_text += (
            f"\n[{i}] 仪器名称：{rec.get('仪器名称', '')}，依据：{rec.get('依据', '')}，"
            f"建议校准周期：{rec.get('建议校准周期', '')}，来源：{rec.get('来源', '')}"
        )

    user_prompt = (
        f"客户：{client_name}\n"
        f"仪器名称：{instrument_name}\n"
        f"校准依据：{criterion}\n"
        f"证书记录的周期：{report_cycle}\n"
        f"参考建议周期：{db_text}\n"
        "请判断证书记录的校准周期是否合理，并严格返回 JSON。"
    )

    client = llm_client
    if client is None:
        return {
            "find": 0,
            "reason": "LLM客户端未初始化",
            "table": "",
        }

    structured_result: Optional[Dict[str, Any]] = None
    try:
        result = client.invoke_structured(user_prompt, CycleLLMResult, system_prompt)
        structured_result = _model_dump_compat(result)
        result_json = {
            "find": int(structured_result.get("find", 0) or 0),
            "reason": str(structured_result.get("reason", "") or ""),
            "table": str(structured_result.get("table", "") or ""),
        }
    except Exception as e:
        print(f"[错误] LLM 结构化解析失败: {e}")
        try:
            resp = client.invoke_text(user_prompt, system_prompt)
            content = resp.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            result_json = json.loads(content)
        except Exception as fallback_exc:
            print(f"[错误] LLM JSON 解析失败: {fallback_exc}")
            result_json = {
                "find": 0,
                "reason": f"LLM输出无法解析: {str(fallback_exc)}",
                "table": "",
            }

    return result_json


# ========== 主核验函数 ==========

def check_cycle_reasonableness(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    校准周期合理性核验（与原始函数完全兼容）

    Args:
        json_file: JSON 文件路径
        cfg: 配置对象

    Returns:
        核验报告（Markdown 格式）
    """
    cfg = get_config(cfg)

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    props = data["properties"]["证书列表"]["items"]["properties"]

    receive_date = props.get("接收日期", "")
    calibrate_date = props.get("校准日期", "")

    client_name = props.get("委托单位名称", "") or props.get("委托单位", "") or props.get("客户名称", "未知客户")
    instrument_name = props.get("仪器名称", "")
    model_name = props.get("型号规格", "")
    criterion_list = props.get("校准依据", [])
    report_cycle = props.get("建议校准周期", "")

    date_check_result = check_date_logic(receive_date, calibrate_date)

    temp = props.get("温度", "")
    rh = props.get("相对湿度") or props.get("湿度", "")
    temp_in = props.get("温度_内页", "")
    rh_in = props.get("相对湿度_内页") or props.get("湿度_内页", "")

    env_consistency_result = check_env_consistency(temp, rh, temp_in, rh_in)

    client = llm_client
    if client is None:
        try:
            client = LLMClient(config=cfg)
        except Exception:
            client = None
    cycle_service = create_cycle_retrieval_service(cfg)

    all_db_entries = []
    llm_results = []
    is_huawei = "华为" in client_name

    for criterion in criterion_list:
        llm_result = {"find": 0}

        if is_huawei:
            huawei_results = cycle_service.search_huawei_cycle(f"{model_name} {criterion}")

            db_entries = []
            for doc in huawei_results:
                metadata = doc.metadata
                db_entries.append({
                    "仪器名称": metadata.get("仪器名称", "") or metadata.get("INSTRUMENT_NAME", ""),
                    "依据": metadata.get("依据", "") or metadata.get("FILE_NAME", ""),
                    "建议校准周期": metadata.get("建议校准周期", ""),
                    "来源": "华为数据库"
                })

            if db_entries:
                llm_result = verify_cycle_with_llm(client, client_name, instrument_name, criterion, report_cycle,
                                                   db_entries)
                if llm_result.get("find", 0) == 1:
                    all_db_entries.extend(db_entries)

        if llm_result.get("find", 0) == 0:
            general_results = cycle_service.search_general_cycle(f"{instrument_name} {criterion}")

            db_entries = []
            for doc in general_results:
                metadata = doc.metadata
                db_entries.append({
                    "仪器名称": metadata.get("仪器名称", "") or metadata.get("INSTRUMENT_NAME", ""),
                    "依据": metadata.get("依据", "") or metadata.get("FILE_NAME", ""),
                    "建议校准周期": metadata.get("建议校准周期", ""),
                    "来源": "通用数据库"
                })

            if db_entries:
                llm_result = verify_cycle_with_llm(client, client_name, instrument_name, criterion, report_cycle,
                                                   db_entries)
                if llm_result.get("find", 0) == 1:
                    all_db_entries.extend(db_entries)

        if llm_result.get("find", 0) == 0:
            default_cycle = cfg.default_cycle
            default_entry = [{
                "仪器名称": instrument_name,
                "依据": "通用计量常规要求 (无特定规程匹配)",
                "建议校准周期": default_cycle,
                "来源": "默认标准(兜底)"
            }]

            llm_result = verify_cycle_with_llm(client, client_name, instrument_name, criterion, report_cycle,
                                               default_entry)

            if llm_result.get("find", 0) == 1:
                all_db_entries.extend(default_entry)
            else:
                llm_result["find"] = 1
                all_db_entries.extend(default_entry)

        llm_results.append(llm_result)

    seen = set()
    merged_entries = []
    for rec in all_db_entries:
        key = (rec["仪器名称"], rec["依据"], rec["来源"])
        if key not in seen:
            merged_entries.append(rec)
            seen.add(key)

    report = VerificationReport()
    report.set_header(
        source_name=Path(json_file).name,
        model=getattr(cfg, "model", ""),
        temperature=getattr(cfg, "temperature", 0.0),
        topk=getattr(cfg, "topk", 3),
    )
    report.add_section("# [报告] 校准周期合理性核验报告")
    report.add_section("")
    report.add_section(f"**客户名称：** {client_name}")
    report.add_section(f"**仪器名称：** {instrument_name}")
    report.add_section(f"**型号：** {model_name}")
    report.add_section(f"**校准依据：** {', '.join(criterion_list)}")
    report.add_section(f"**证书记录周期：** {report_cycle}")
    report.add_section("")
    report.add_section("## [参考] 参考标准来源")
    report.add_section("")
    report.add_section("| 序号 | 仪器/依据 | 建议校准周期 | 数据来源 |")
    report.add_section("| ---- | ---------- | ---------------- | ---------- |")

    for idx, rec in enumerate(merged_entries, 1):
        report.add_section(
            f"| {idx} | {rec['仪器名称']} / {rec['依据']} | {rec['建议校准周期']} | {rec['来源']} |"
        )

    report.add_section("\n## [智能] 智能核验结论\n")

    matched_results = [r for r in llm_results if r.get("find", 0) == 1]
    if not matched_results:
        report.add_section("> [警告] 系统异常：未能生成有效核验结论。\n")
    else:
        for i, r in enumerate(matched_results, 1):
            reason = r.get("reason", "").strip()
            table = r.get("table", "").strip()

            report.add_section(f"### [完成] 核验项 {i}\n")
            report.add_section(f"> **分析说明：** {reason}\n")
            if table:
                report.add_section("\n" + table + "\n")
            else:
                report.add_section("\n> (无详细对比表)\n")

    report.add_section("## [日期] 日期逻辑核验")
    report.add_section("")
    report.add_section(f"- **接收日期：** {receive_date or '未提供'}")
    report.add_section(f"- **校准日期：** {calibrate_date or '未提供'}")
    report.add_section("")

    if date_check_result["pass"]:
        report.add_section(f"> [完成] {date_check_result['reason']}\n")
    else:
        report.add_section(f"> [错误] {date_check_result['reason']}\n")

    report.add_section("## [温湿度] 温湿度一致性核验")
    report.add_section("")
    report.add_section(f"- **温度：** {temp or '未提供'}")
    report.add_section(f"- **相对湿度：** {rh or '未提供'}")
    report.add_section(f"- **温度_内页：** {temp_in or '未提供'}")
    report.add_section(f"- **相对湿度_内页：** {rh_in or '未提供'}")
    report.add_section("")

    if not env_consistency_result["enabled"]:
        report.add_section(f"> [警告] {env_consistency_result['reason']}\n")
    else:
        if env_consistency_result["pass"]:
            report.add_section(f"> [完成] {env_consistency_result['reason']}\n")
        else:
            report.add_section(f"> [错误] {env_consistency_result['reason']}\n")

        d = env_consistency_result["detail"]
        report.add_section("| 项目 | 原始值 | 归一化后 |")
        report.add_section("| --- | --- | --- |")
        report.add_section(f"| 温度 | {d['温度_raw']} | {d['温度_norm']} |")
        report.add_section(f"| 温度_内页 | {d['温度_内页_raw']} | {d['温度_内页_norm']} |")
        report.add_section(f"| 相对湿度 | {d['相对湿度_raw']} | {d['相对湿度_norm']} |")
        report.add_section(f"| 相对湿度_内页 | {d['相对湿度_内页_raw']} | {d['相对湿度_内页_norm']} |")
        report.add_section("")

    return report.render()


# ==================== 兼容旧接口 ====================

def cycle_check_wrapper(json_path: str, config):
    """
    兼容性函数，用于直接调用校准周期核验

    Args:
        json_path: JSON 文件路径
        config: 配置对象（原始 AppConfig）

    Returns:
        核验报告
    """
    return check_cycle_reasonableness(json_path, config)
