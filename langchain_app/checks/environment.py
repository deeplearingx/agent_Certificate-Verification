#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境条件核验模块 - 与原始 env_check.py 功能完全兼容

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

# 本地导入
from langchain_app.utils import get_app_config, AppConfig, coerce_app_config
from langchain_app.core import LLMClient, VerificationReport
from langchain_app.retrieval import TemperatureRetrievalService, create_temperature_retrieval_service


# ========== 配置系统 ==========

def get_config(cfg: Optional[AppConfig] = None):
    """获取配置对象"""
    return coerce_app_config(cfg)


# ========== 工具函数 ==========

def extract_numbers_from_str(s: str):
    """提取字符串中的数值（支持范围如 20～25）"""
    if not s:
        return []
    s = s.replace("～", " ").replace("~", " ").replace("至", " ")
    matches = re.findall(r"-?\d+\.?\d*", s)
    return [float(x) for x in matches] if matches else []


def _normalize_temperature_entry(metadata: Dict[str, Any]) -> Dict[str, str]:
    return {
        "INSTRUMENT_NAME": str(metadata.get("仪器名称", "") or metadata.get("INSTRUMENT_NAME", "") or "").strip(),
        "FILE_CODE": str(metadata.get("FILE_CODE", "") or metadata.get("文件编号", "") or "").strip(),
        "FILE_NAME": str(metadata.get("FILE_NAME", "") or metadata.get("文件名称", "") or "").strip(),
        "温度要求": str(metadata.get("温度要求", "") or "").strip(),
        "相对湿度要求": str(metadata.get("相对湿度要求", "") or metadata.get("湿度要求", "") or "").strip(),
        "最大温度变化范围": str(metadata.get("最大温度变化范围", "") or metadata.get("最大温差", "") or "").strip(),
        "认可组织": str(metadata.get("认可组织", "") or metadata.get("ACCREDITATION_BODY", "") or "").strip(),
    }


def _has_meaningful_temperature_entry(entry: Dict[str, Any]) -> bool:
    return any(
        str(entry.get(key, "") or "").strip()
        for key in (
            "INSTRUMENT_NAME",
            "FILE_CODE",
            "FILE_NAME",
            "温度要求",
            "相对湿度要求",
            "最大温度变化范围",
            "认可组织",
        )
    )


def _render_environment_unavailable_table() -> str:
    return (
        "| 项目 | 要求 | 实际 | 判定 | 说明 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 温度 | 未获取到要求 | 未知 | 待定 | 环境温度知识库未返回有效要求记录，无法自动判断。 |\n"
        "| 湿度 | 未获取到要求 | 未知 | 待定 | 环境湿度知识库未返回有效要求记录，无法自动判断。 |\n"
        "| 温差 | 未获取到要求 | 未知 | 待定 | 环境温差知识库未返回有效要求记录，无法自动判断。 |"
    )


def _is_guangzhou_lab_entry(entry: Dict[str, Any]) -> bool:
    org = str(entry.get("认可组织", "") or "").strip()
    return org == "广州实验室"


# ========== LLM 调用模块 ==========

def verify_with_llm(
    llm_client: Optional[LLMClient],
    criterion: str,
    current_temp: Optional[float],
    current_hum: Optional[float],
    db_entries: List[Dict[str, Any]]
) -> str:
    """
    使用 LangChain LLMClient 进行环境条件核验。

    Args:
        llm_client: LLMClient 实例
        criterion: 校准依据
        current_temp: 当前温度
        current_hum: 当前湿度
        db_entries: 数据库匹配记录

    Returns:
        核验结果（Markdown 格式）
    """
    system_prompt = (
        "你是一名实验室质量核验专家，根据温度、湿度和温差判断环境条件是否符合校准要求。\n"
        "请严格按照下表输出：\n"
        "| 项目 | 要求 | 实际 | 判定 | 说明 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "只输出表格，不要额外文本。"
    )

    db_text = ""
    for i, rec in enumerate(db_entries, 1):
        db_text += (
            f"\n[{i}] 仪器 {rec['INSTRUMENT_NAME']}，依据编号 {rec['FILE_CODE']}，"
            f"依据名称 {rec['FILE_NAME']}，温度要求 {rec['温度要求']}，"
            f"湿度要求 {rec['相对湿度要求']}，温差 {rec['最大温度变化范围']}"
        )

    user_prompt = (
        f"校准依据：{criterion}\n"
        f"当前温度：{current_temp} ℃\n"
        f"当前湿度：{current_hum} %\n"
        f"向量数据库检索的前5条相关要求：{db_text}\n"
        f"请判断当前温度、湿度和温差是否符合要求，并在表格中说明理由。"
    )

    client = llm_client
    if client is None:
        return "> **LLM核验跳过**：LLM 客户端未初始化"

    try:
        return client.invoke_text(user_prompt, system_prompt)
    except Exception as exc:
        return f"> **LLM核验失败**：{exc}"


# ========== 核验逻辑 ==========

def check_environment(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    核验环境条件 - 与原始函数完全兼容

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

    instrument_name = props.get("仪器名称", "")
    temp_text = props.get("温度", "")
    humidity_text = props.get("相对湿度") or props.get("湿度", "")
    criteria_list = props.get("校准依据", [])

    current_temp = extract_numbers_from_str(temp_text)
    current_temp = current_temp[0] if current_temp else None
    current_hum = extract_numbers_from_str(humidity_text)
    current_hum = current_hum[0] if current_hum else None

    temp_service = create_temperature_retrieval_service(cfg)
    client = llm_client
    if client is None:
        try:
            client = LLMClient(config=cfg)
        except Exception:
            client = None

    report = VerificationReport()
    report.set_header(
        source_name=Path(json_file).name,
        model=getattr(cfg, "model", ""),
        temperature=getattr(cfg, "temperature", 0.0),
        topk=getattr(cfg, "topk", 3),
    )
    report.add_section("# 第二步：环境条件核验")

    for criterion in criteria_list:
        code_match = re.match(r"([A-Z]{2,}\s*\d{3,4}-\d{4})", criterion)

        if not code_match:
            report.add_section(f"⚠️ 未识别的依据格式：{criterion}")
            continue

        code = code_match.group(1).strip()

        db_entries = []

        search_results = temp_service.search_temperature_requirements(
            instrument_name=f"{criterion} 广州实验室",
            criterion=None,
            k=getattr(cfg, "topk", 5),
        )

        for doc in search_results:
            db_entries.append(_normalize_temperature_entry(doc.metadata))

        db_entries = [entry for entry in db_entries if _has_meaningful_temperature_entry(entry)]
        db_entries = [entry for entry in db_entries if _is_guangzhou_lab_entry(entry)]

        if not db_entries:
            report.add_section(f"## 依据 {code} 向量数据库检索结果：")
            report.add_section("| 仪器名称 | 文件编号 | 文件名称 | 温度要求 | 湿度要求 | 最大温差 | 认可组织 |")
            report.add_section("| --- | --- | --- | --- | --- | --- | --- |")
            report.add_section("|  |  |  |  |  |  |  |")
            report.add_section("")
            report.add_section(
                f"## 依据 {code} 核验结果：\n"
                "> 温度环境知识库未返回有效记录；当前索引可能为空白占位数据，已停止自动环境判定。\n"
                + _render_environment_unavailable_table()
                + "\n"
            )
            continue

        report.add_section(f"## 依据 {code} 向量数据库检索结果：")
        report.add_section("| 仪器名称 | 文件编号 | 文件名称 | 温度要求 | 湿度要求 | 最大温差 | 认可组织 |")
        report.add_section("| --- | --- | --- | --- | --- | --- | --- |")

        for rec in db_entries:
            report.add_section(
                f"| {rec['INSTRUMENT_NAME']} | {rec['FILE_CODE']} | {rec['FILE_NAME']} | "
                f"{rec['温度要求']} | {rec['相对湿度要求']} | {rec['最大温度变化范围']} | {rec['认可组织']} |"
            )

        llm_result = verify_with_llm(client, criterion, current_temp, current_hum, db_entries)
        report.add_section(f"\n## 依据 {code} 核验结果：\n{llm_result}\n")

    return report.render()


# ==================== 兼容旧接口 ====================

def environment_check_wrapper(json_path: str, config):
    """
    兼容性函数，用于直接调用环境条件核验

    Args:
        json_path: JSON 文件路径
        config: 配置对象（原始 AppConfig）

    Returns:
        核验报告
    """
    return check_environment(json_path, config)
