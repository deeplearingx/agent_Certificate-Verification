#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证书完整性核验模块 - 与原始 info_check.py 功能完全兼容

重构后的 module 特点：
1. 使用 langchain_app 配置系统
2. 使用 langchain_app 的 LLMClient
3. 与 VerificationState 状态类兼容
"""

import json
import re
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

# 本地导入
from langchain_app.utils import get_app_config, AppConfig, coerce_app_config
from langchain_app.core import LLMClient, VerificationReport


# ========== 配置系统 ==========

def get_config(cfg: Optional[AppConfig] = None):
    """获取配置对象"""
    return coerce_app_config(cfg)


# ========== 工具函数 ==========

def normalize(value, default="N/A"):
    """将 null、空字符串、空数组 或严重乱码视为缺失"""
    if value is None:
        return default
    if isinstance(value, str):
        v = value.strip()
        if not v or v == "/":
            return default
        return v
    if isinstance(value, list) and len(value) == 0:
        return default
    return str(value)


def normalize_cnas_flag(props: Dict[str, Any]) -> str:
    cnas_value = normalize((props or {}).get("CNAS"), default="")
    if cnas_value in {"是", "否", "Yes", "No", "TRUE", "FALSE"}:
        return cnas_value

    legacy_value = normalize((props or {}).get("是否CNAS"))
    if legacy_value in {"是", "否", "Yes", "No", "TRUE", "FALSE"}:
        return legacy_value

    # 兼容旧JSON里 CNAS=L13344 这类历史值
    if cnas_value and cnas_value not in {"N/A", "/"}:
        return "是"

    return legacy_value or "N/A"


def is_explicit_non_cnas_flag(value: Any) -> bool:
    normalized = normalize(value, default="")
    return normalized in {"否", "No", "FALSE"}


def build_non_cnas_skip_report(*, source_name: str, cert_no: str, is_cnas: str) -> str:
    report_lines = [
        "# [跳过] 非CNAS文件，跳过核验",
        f"**证书文件**：{source_name}",
        f"**证书编号**：{cert_no}",
        "",
        "## [跳过] 跳过说明",
        f"> **原因**：该证书未标记为 CNAS 认可证书（'CNAS' 字段值为 '{is_cnas}'）。",
        "> **处理**：当前文件跳过后续核验流程。",
    ]
    return "\n".join(report_lines)


def generate_report_filename(file_path: str, output_dir: Optional[str] = None):
    """根据【输入文件名】生成报告文件名"""
    file_stem = Path(file_path).stem
    safe = re.sub(r"[^\w\-]", "_", file_stem)
    cfg = get_config()
    base_output_dir = output_dir or str(cfg.reports_dir)
    os.makedirs(base_output_dir, exist_ok=True)
    return os.path.join(base_output_dir, f"certificate_integrity_{safe}.md")


# ========== LLM 调用模块 ==========

def verify_with_llm(
    fields: Dict[str, Any],
    cert_no: str,
    cfg: Optional[AppConfig] = None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    使用 LangChain LLMClient 进行字段语义合理性核验。

    Args:
        fields: 需要核验的字段
        cert_no: 证书编号
        cfg: 配置对象

    Returns:
        核验结果（Markdown 格式）
    """
    cfg = get_config(cfg)
    client = llm_client
    if client is None:
        return "> **LLM核验跳过**：LLM 客户端未初始化"

    system_prompt = (
        "你是一名资深计量校准核验专家。你的任务是对校准证书的关键信息字段进行逻辑核验。\n"
        "### 核心规则\n"
        "1. **完整性**：检查字段是否有乱码、空值或“N/A”。\n"
        "2. **一致性**：检查仪器名称、型号、制造商是否逻辑匹配（如 Keysight 33511B 是合理的）。\n"
        "3. **致命缺陷判定（环境条件）**：\n"
        "   - 根据 CNAS-CL01 要求，**温度**和**相对湿度**为必须要素。\n"
        "   - 如果这两个字段缺失、为“N/A”或没有单位，**必须**在建议栏标记“严重不符合：环境数据缺失，证书无效”，并判定结果为“异常”。\n\n"
        "请直接输出 Markdown 表格，包含列：| 字段名 | 内容 | 核验结果 | 建议 |"
    )

    user_prompt = f"证书编号：{cert_no}\n待核验字段如下：\n"
    for name, val in fields.items():
        user_prompt += f"- {name}：{val}\n"

    user_prompt += "\n请根据上述规则生成核验表格。"

    try:
        return client.invoke_text(user_prompt, system_prompt)
    except Exception as exc:
        return f"> **LLM核验失败**：{exc}"


# ========== 核验证书完整性主函数 ==========

def check_certificate_integrity(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    核验证书完整性 - 与原始函数完全兼容

    Args:
        json_file: JSON 文件路径
        cfg: 配置对象

    Returns:
        核验报告（Markdown 格式）
    """
    cfg = get_config(cfg)

    # 1. 读取 JSON
    with open(json_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 2. 路径提取 (增加容错)
    try:
        props = raw_data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        print("[警告] JSON 结构解析失败，尝试直接读取根目录...")
        props = raw_data

    # ================= 新增 CNAS 阻断逻辑 =================
    is_cnas = normalize_cnas_flag(props)

    # 只有明确识别为非 CNAS 才终止；未知/N/A 应继续后续流程。
    if is_explicit_non_cnas_flag(is_cnas):
        print(f"[跳过] 检测到非 CNAS 证书 (标记为: {is_cnas})，跳过当前文件核验。")
        report_text = build_non_cnas_skip_report(
            source_name=os.path.basename(json_file),
            cert_no=normalize(props.get("证书编号")),
            is_cnas=is_cnas,
        )

        report_path = generate_report_filename(json_file, str(cfg.reports_dir))
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        return report_text
    # ======================================================

    # 3. 提取并规范化字段 (只有通过 CNAS 检查才继续执行)
    instrument_name = normalize(props.get("INSTRUMENT_NAME") or props.get("仪器名称"))
    model_name = normalize(props.get("型号") or props.get("型号规格"))
    manufacturer = normalize(props.get("制造厂") or props.get("制造商"))
    serial_no = normalize(props.get("机身号") or props.get("序列号"))
    manage_no = normalize(props.get("管理号"))
    client_name = normalize(props.get("委托单位名称") or props.get("委托单位") or props.get("客户名称"))
    cert_no = normalize(props.get("证书编号"), default="unknown")

    temp_raw = normalize(props.get("温度"))
    hum_raw = normalize(props.get("相对湿度") or props.get("湿度"))

    report_cycle = normalize(props.get("建议校准周期"))
    criteria_list = props.get("校准依据") or []

    report = VerificationReport()
    report.set_header(
        source_name=os.path.basename(json_file),
        model=getattr(cfg, "model", ""),
        temperature=getattr(cfg, "temperature", 0.0),
        topk=getattr(cfg, "topk", 3),
    )
    report.add_section("# [报告] 校准证书完整性核验报告")
    report.add_section(f"**证书文件**：{os.path.basename(json_file)}")
    report.add_section(f"**是否CNAS**：[完成] {is_cnas}")

    report.add_section("## 一、被测仪器信息")
    report.add_section(f"- 仪器名称：{instrument_name}")
    report.add_section(f"- 型号规格：{model_name}")
    report.add_section(f"- 制造厂：{manufacturer}")
    report.add_section(f"- 机身号：{serial_no}")
    report.add_section(f"- 管理号：{manage_no}")
    report.add_section(f"- 委托单位：{client_name}")
    report.add_section(f"- 证书编号：{cert_no}")

    report.add_section("## 二、环境条件")
    report.add_section(f"- 温度：{temp_raw}")
    report.add_section(f"- 相对湿度：{hum_raw}")

    report.add_section("## 三、报告周期与依据")
    report.add_section(f"- 建议校准周期：{report_cycle}")
    if criteria_list:
        report.add_section("- 校准依据：")
        for criterion in criteria_list:
            report.add_section(f"  - {criterion}")

    if cfg.use_llm_verification:
        client = llm_client
        if client is None:
            try:
                client = LLMClient(config=cfg)
            except Exception:
                client = None
        fields_to_verify = {
            "仪器名称": instrument_name,
            "型号规格": model_name,
            "制造厂": manufacturer,
            "机身号": serial_no,
            "温度": temp_raw,
            "相对湿度": hum_raw
        }

        llm_report = verify_with_llm(fields_to_verify, cert_no, cfg, llm_client=client)
        report.add_section("## 四、语义合理性核验")
        report.add_section(llm_report)

    report.add_section("## 五、综合结论")
    all_fields = [instrument_name, model_name, manufacturer, temp_raw, hum_raw]

    if any(f in ["N/A", ""] for f in all_fields):
        report.add_section("> **状态**：[警告] 数据不完整")
        report.add_section("> **结论**：证书可能存在缺陷，建议进一步核验。")
    else:
        report.add_section("> **状态**：[完成] 信息完整")
        report.add_section("> **结论**：所有必填字段均已填写，格式符合要求。")

    final_report = report.render()

    report_path = generate_report_filename(json_file, str(cfg.reports_dir))
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    return final_report


# ==================== 兼容旧接口 ====================

def info_check_wrapper(json_path: str, config):
    """
    兼容性函数，用于直接调用完整性核验

    Args:
        json_path: JSON 文件路径
        config: 配置对象（原始 AppConfig）

    Returns:
        核验报告
    """
    return check_certificate_integrity(json_path, config)
