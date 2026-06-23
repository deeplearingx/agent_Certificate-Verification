#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNAS参数核验 - 纯新API版本
完全使用新的模块化API，代码更清晰
"""

import json
from typing import Any, Dict, List, Optional, Tuple

# ===================== 直接导入新模块 =====================
from core.config import Config
from core.number_parser import NumberParser
from core.risk_verifier import RangeVerifier
from core.error_verifier import ErrorVerifier
from core.uncertainty_verifier import UncertaintyVerifier
from core.unit_converter import UnitConverter
from core.table_processor import TableProcessor
from core.report_generator import ReportGenerator

from config.settings import get_app_config
from llm.client import create_openai_client
from langchain_app.checks.parameter import (
    FirstCandidateDecider,
    infer_param_semantics,
    select_basis_with_audit,
)


# ===================== 核心核验函数 - 使用新API =====================
def verify_range_logic(measure_val, range_str):
    """范围核验 - 直接调用新API"""
    return RangeVerifier.verify_range_logic(measure_val, range_str)


def verify_error_logic(error_val, limit_val):
    """误差验证 - 直接调用新API"""
    return ErrorVerifier.verify_error_logic(error_val, limit_val)


def verify_uncertainty_logic(measure_val, cert_u, kb_u):
    """不确定度验证 - 直接调用新API"""
    return UncertaintyVerifier.verify_uncertainty_logic(measure_val, cert_u, kb_u)


# ===================== 辅助函数 - 使用新API =====================
def norm_code(s: str) -> str:
    """规范化代码"""
    import re
    s = (s or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return re.sub(r"\s+", "", s).upper()


def extract_basis_code(criterion: str) -> Optional[str]:
    """提取依据代码"""
    import re
    if not criterion:
        return None
    s = str(criterion)
    s = re.sub(r"-(?:\d{4}|[0-9]{4})(?![0-9])", "", s)
    m = re.search(r"([A-Z]{2,3}\s*\d+(?:\.\d+)?)", s, re.IGNORECASE)
    return m.group(1) if m else None


# ===================== 表格和报告处理 - 使用新API =====================
def build_param_table(entries: List[Dict], top_k: int = 10) -> str:
    """构建参数表格"""
    return ReportGenerator.build_param_table(entries, top_k)


def enforce_kb_missing_fail(md: str) -> str:
    """强制知识库缺失时失败"""
    return ReportGenerator.enforce_kb_missing_fail(md)


def enforce_uncertainty_by_tool(md: str) -> str:
    """强制按工具计算不确定度"""
    return ReportGenerator.enforce_uncertainty_by_tool(md)


def enforce_batch_summary_from_table(
    md: str, expected_param_names: Optional[List[str]] = None
) -> str:
    """强制从表格生成批次摘要"""
    return ReportGenerator.enforce_batch_summary_from_table(md, expected_param_names)


# ===================== 配置访问 =====================
LAST_QUERY_ERROR = None


def get_config():
    """获取配置"""
    return Config


# ===================== 简单测试 =====================
if __name__ == "__main__":
    print("=" * 60)
    print("Param Check - 纯新API版本")
    print("=" * 60)
    print()

    # 1. 数值解析
    print("1. 数值解析")
    value, unit, original = NumberParser.parse_value_with_unit("10.5 kHz")
    print(f"   {original} → {value} {unit}")

    # 2. 范围验证
    print("\n2. 范围验证")
    result = RangeVerifier.verify_range_logic("10.5 V", "0~20 V")
    print(f"   {result}")

    # 3. 误差验证
    print("\n3. 误差验证")
    result = ErrorVerifier.verify_error_logic("0.1 mV", "0.5 mV")
    print(f"   {result}")

    # 4. 不确定度验证
    print("\n4. 不确定度验证")
    result = UncertaintyVerifier.verify_uncertainty_logic("10.5 V", "0.1", "0.2")
    print(f"   {result}")

    print("\n" + "=" * 60)
    print("完成！使用纯新API，代码更清晰")
    print("=" * 60)
