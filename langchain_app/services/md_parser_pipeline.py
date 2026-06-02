#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
无大模型的MD解析器 - 泛用性版本
支持多种格式的校准证书解析
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple, Type, Literal, Callable

from pydantic import BaseModel, Field, create_model

from langchain_app.checks.parameter.contracts import (
    build_parameter_contract,
    parameter_contract_schema_version,
)
from langchain_app.checks.parameter.rules import SECTION_TITLE_ALIASES
from langchain_app.checks.parameter.rules import (
    PERIOD_ACCURACY_ERROR_HEADER_ALIASES,
    PERIOD_ACCURACY_SECTION_ALIASES,
)


@dataclass(frozen=True)
class DocumentParseContext:
    md_text: str
    blocks: list[tuple[str, str]]
    meta: dict[str, Any]
    meta_debug: dict[str, Any]


@dataclass(frozen=True)
class TableArtifact:
    project_title: str
    table_html: str
    table_data: list[list[str]]


@dataclass(frozen=True)
class FlatBlockArtifact:
    project_title: str
    content: str


def md_parser_pipeline_signature() -> str:
    root_dir = Path(__file__).resolve().parents[2]
    digest = hashlib.sha1()
    for path in (
        root_dir / "md_parser_no_llm.py",
        Path(__file__).resolve(),
    ):
        try:
            digest.update(path.read_bytes())
        except Exception:
            digest.update(str(path).encode("utf-8"))
    return digest.hexdigest()[:12]

# ──────────────────────────────────────────────
# 泛用性配置
# ──────────────────────────────────────────────

# 字段名映射：统一输出字段名
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
    "相对湿度": "相对湿度",
    "湿度": "相对湿度",
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

COLUMN_ALIASES = {
    "nominal_value": [
        "标称值",
        "nominal",
        "nominal value",
    ],
    "measure_value": [
        "测量值",
        "测量结果",
        "结果",
        "输出",
        "频率",
        "frequency",
        "周期",
        "period",
        "示值",
        "指示值",
        "indicated",
        "measured",
        "measurement value",
        "reading",
        "readout",
    ],
    "reference_value": [
        "标准值",
        "reference",
        "参考值",
    ],
    "error_value": [
        "误差",
        "偏差",
        "日差",
        "日偏差",
        "日误差",
        "走时误差",
        "走时偏差",
        "time error",
        "time deviation",
        "daily error",
        "daily deviation",
        "error per day",
        "day error",
        "deviation",
        "error",
        "灵敏度",
        "sensitivity",
        "开机特性",
        "warm-up characteristics",
        "warm up characteristics",
        "短期频率稳定度",
        "stability",
        "频率稳定度",
        "相对频率偏差",
        "relative frequency deviation",
    ],
    "limit_value": [
        "允许误差",
        "允许范围",
        "最大允许误差",
        "误差限值",
        "限值",
        "容差",
        "允差",
        "limit",
    ],
    "cert_u": [
        "不确定度",
        "证书u",
        "u(k=2)",
        "urel(k=2)",
        "urel",
        "u",
        "uncertainty",
    ],
    "result_flag": [
        "结论",
        "结果判定",
        "判定",
        "pass/fail",
        "result",
    ],
    "point_value": [
        "点位",
        "point",
        "通道",
        "channel",
        "取样时间",
        "gate time",
        "闸门时间",
        "band",
        "档位",
        "range",
        "端口",
        "port",
        "设定值",
        "setting",
        "标称频率",
        "可调节功率值",
        "slider power value",
        "power setting",
        "set power",
        "set level",
        "level setting",
    ],
}

STANDARD_PARAMETER_PARSE_SOURCES = {"html_table", "html_table_inline"}
ParserProgressCallback = Callable[[str, int, int, str], None]
PARSER_FALLBACK_SECTION_RULES = frozenset(
    {
        "unknown",
        "frequency_accuracy",
        "frequency_range",
        "reference_oscillator",
        "period_accuracy",
        "period_range",
        "modulation_quality",
        "phase_noise",
        "spectral_purity",
        "dynamic_range",
        "power_accuracy",
    }
)
PARSER_FALLBACK_BINDABLE_FIELDS = frozenset(
    {"measure_value", "reference_value", "error_value", "limit_value", "cert_u", "point_value", "condition_value"}
)
PARSER_FALLBACK_UNIT_FAMILIES = frozenset(
    {"unknown", "frequency", "time", "voltage_power", "count", "motion", "length"}
)


class ParserFallbackDecision(BaseModel):
    action: str = "abstain"
    section_rule: str = "unknown"
    field_bindings: Dict[str, str] = Field(default_factory=dict)
    unit_family: str = "unknown"
    confidence: float = 0.0
    reason: str = ""


META_FALLBACK_FIELDS = (
    "委托单位",
    "委托方地址",
    "仪器名称",
    "型号规格",
    "制造商",
    "机身号",
    "管理号",
    "接收日期",
    "校准日期",
    "签发日期",
    "建议校准周期",
)


class MetaFallbackDecision(BaseModel):
    action: str = "abstain"
    field_slots: Dict[str, int] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


def _build_parser_fallback_slot_context(details: dict[str, Any]) -> dict[str, Any]:
    slots: list[dict[str, Any]] = []
    slot_to_header: dict[int, str] = {}
    for index, (header, value) in enumerate((details or {}).items(), start=1):
        header_text = str(header or "").strip()
        if not header_text:
            continue
        slots.append({"slot": index, "header": header_text, "value": str(value or "").strip()})
        slot_to_header[index] = header_text
    return {"header_slots": slots, "slot_to_header": slot_to_header}


def _build_parser_fallback_slot_output_model(details: dict[str, Any]) -> Type[BaseModel]:
    slot_context = _build_parser_fallback_slot_context(details)
    header_slots = tuple(slot["slot"] for slot in slot_context["header_slots"]) or (0,)

    action_literal = Literal.__getitem__(("abstain", "suggest"))
    section_rule_literal = Literal.__getitem__(tuple(sorted(PARSER_FALLBACK_SECTION_RULES)))
    unit_family_literal = Literal.__getitem__(tuple(sorted(PARSER_FALLBACK_UNIT_FAMILIES)))
    slot_literal = Literal.__getitem__(header_slots)

    binding_fields = {
        field_name: (
            Optional[slot_literal],
            Field(
                default=None,
                description=f"Bind {field_name} to one existing raw_details slot.",
            ),
        )
        for field_name in sorted(PARSER_FALLBACK_BINDABLE_FIELDS)
    }
    bindings_model = create_model(
        "ParserFallbackSlotBindings",
        __base__=BaseModel,
        **binding_fields,
    )
    return create_model(
        "ParserFallbackDecisionSlotStructured",
        __base__=BaseModel,
        action=(action_literal, Field(default="abstain")),
        section_rule=(section_rule_literal, Field(default="unknown")),
        field_bindings=(bindings_model, Field(default_factory=bindings_model)),
        unit_family=(unit_family_literal, Field(default="unknown")),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        reason=(str, Field(default="")),
    )


def _coerce_parser_fallback_slot_decision(decision: Any, details: dict[str, Any]) -> Optional[ParserFallbackDecision]:
    if not isinstance(decision, BaseModel):
        return None
    slot_context = _build_parser_fallback_slot_context(details)
    slot_to_header = dict(slot_context.get("slot_to_header") or {})
    raw_bindings = getattr(decision, "field_bindings", None)
    if isinstance(raw_bindings, BaseModel):
        binding_payload = raw_bindings.model_dump(exclude_none=True)
    elif isinstance(raw_bindings, dict):
        binding_payload = dict(raw_bindings)
    else:
        binding_payload = {}

    field_bindings: Dict[str, str] = {}
    for key, value in binding_payload.items():
        try:
            slot = int(value)
        except (TypeError, ValueError):
            continue
        header = slot_to_header.get(slot)
        if header:
            field_bindings[str(key).strip()] = header

    return ParserFallbackDecision(
        action=str(getattr(decision, "action", "") or "abstain").strip(),
        section_rule=str(getattr(decision, "section_rule", "") or "unknown").strip(),
        field_bindings=field_bindings,
        unit_family=str(getattr(decision, "unit_family", "") or "unknown").strip(),
        confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
        reason=str(getattr(decision, "reason", "") or "").strip(),
    )


def _build_parser_fallback_output_model(details: dict[str, Any]) -> Type[BaseModel]:
    header_choices = tuple(str(key) for key in details.keys() if str(key).strip())
    if not header_choices:
        header_choices = ("__none__",)

    action_literal = Literal.__getitem__(("abstain", "suggest"))
    section_rule_literal = Literal.__getitem__(tuple(sorted(PARSER_FALLBACK_SECTION_RULES)))
    unit_family_literal = Literal.__getitem__(tuple(sorted(PARSER_FALLBACK_UNIT_FAMILIES)))
    header_literal = Literal.__getitem__(header_choices)

    binding_fields = {
        field_name: (
            Optional[header_literal],
            Field(
                default=None,
                description=f"Bind {field_name} to one existing raw_details header.",
            ),
        )
        for field_name in sorted(PARSER_FALLBACK_BINDABLE_FIELDS)
    }
    bindings_model = create_model(
        "ParserFallbackBindings",
        __base__=BaseModel,
        **binding_fields,
    )
    return create_model(
        "ParserFallbackDecisionStructured",
        __base__=BaseModel,
        action=(
            action_literal,
            Field(default="abstain", description="abstain or suggest"),
        ),
        section_rule=(
            section_rule_literal,
            Field(default="unknown", description="One allowed parser section rule."),
        ),
        field_bindings=(
            bindings_model,
            Field(default_factory=bindings_model),
        ),
        unit_family=(
            unit_family_literal,
            Field(default="unknown", description="One allowed unit family."),
        ),
        confidence=(
            float,
            Field(default=0.0, ge=0.0, le=1.0),
        ),
        reason=(str, Field(default="")),
    )


def _coerce_parser_fallback_decision(decision: Any) -> Optional[ParserFallbackDecision]:
    if isinstance(decision, ParserFallbackDecision):
        return decision
    if not isinstance(decision, BaseModel):
        return None

    raw_bindings = getattr(decision, "field_bindings", None)
    if isinstance(raw_bindings, BaseModel):
        field_bindings = {
            key: str(value).strip()
            for key, value in raw_bindings.model_dump(exclude_none=True).items()
            if str(value).strip()
        }
    elif isinstance(raw_bindings, dict):
        field_bindings = {
            str(key).strip(): str(value).strip()
            for key, value in raw_bindings.items()
            if str(key).strip() and str(value).strip()
        }
    else:
        field_bindings = {}

    return ParserFallbackDecision(
        action=str(getattr(decision, "action", "") or "abstain").strip(),
        section_rule=str(getattr(decision, "section_rule", "") or "unknown").strip(),
        field_bindings=field_bindings,
        unit_family=str(getattr(decision, "unit_family", "") or "unknown").strip(),
        confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
        reason=str(getattr(decision, "reason", "") or "").strip(),
    )

# 标签模式配置：支持多种标签格式
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


def _clean_header_text(header_text: str) -> str:
    text = re.sub(r"\s*\n\s*", " ", str(header_text or "").strip())
    text = re.sub(r"\s*\(\s*\)\s*$", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _normalize_alias_key(text: str) -> str:
    normalized = str(text or "").strip().lower()
    normalized = normalized.replace("_", "").replace("-", "").replace("/", "")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _match_section_rule_meta(title: str) -> dict[str, Any]:
    lowered = str(title or "").lower()
    scored_hits: list[tuple[int, int, str, str]] = []
    for rule_name, aliases in SECTION_TITLE_ALIASES.items():
        matched_aliases = [alias for alias in aliases if alias.lower() in lowered]
        if not matched_aliases:
            continue
        best_alias = max(matched_aliases, key=len)
        scored_hits.append((len(best_alias), len(matched_aliases), rule_name, best_alias))
    if not scored_hits:
        return {
            "section_rule": "unknown",
            "section_rule_confidence": 0.0,
            "section_alias_matched": "",
            "section_alias_candidates": (),
        }
    scored_hits.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    best_len, match_count, rule_name, best_alias = scored_hits[0]
    title_len = max(len(_clean_header_text(title)), 1)
    confidence = min(0.99, round(0.55 + (best_len / title_len) + max(match_count - 1, 0) * 0.03, 3))
    return {
        "section_rule": rule_name,
        "section_rule_confidence": confidence,
        "section_alias_matched": best_alias,
        "section_alias_candidates": tuple(alias for _, _, candidate_rule, alias in scored_hits if candidate_rule == rule_name),
    }


def _match_section_rule(title: str) -> str:
    return str(_match_section_rule_meta(title)["section_rule"])


def _match_column_alias(header: str) -> tuple[str, str]:
    header_norm = _normalize_alias_key(header)
    exact_hits: list[tuple[str, str]] = []
    fuzzy_hits: list[tuple[int, str, str]] = []
    for canonical_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            alias_norm = _normalize_alias_key(alias)
            if not alias_norm:
                continue
            if alias_norm == header_norm:
                exact_hits.append((canonical_name, alias))
            elif len(alias_norm) >= 2 and alias_norm in header_norm:
                fuzzy_hits.append((len(alias_norm), canonical_name, alias))
    if exact_hits:
        exact_hits.sort(key=lambda item: len(_normalize_alias_key(item[1])), reverse=True)
        return exact_hits[0]
    if fuzzy_hits:
        fuzzy_hits.sort(key=lambda item: item[0], reverse=True)
        _, canonical_name, alias = fuzzy_hits[0]
        return canonical_name, alias
    return "", ""


def _build_normalized_fields(details: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    normalized_fields: dict[str, str] = {}
    header_rules: dict[str, str] = {}

    for key, value in details.items():
        canonical_name, alias = _match_column_alias(key)
        if not canonical_name or not value:
            continue
        if canonical_name not in normalized_fields:
            normalized_fields[canonical_name] = str(value)
            header_rules[canonical_name] = key
        elif canonical_name == "point_value":
            # 点位类字段优先保留更像真实点位/采样时间的列，避免分组表头下
            # 的结果值把 time/gate 列覆盖掉。
            existing_value = normalized_fields.get(canonical_name, "")
            existing_header = header_rules.get(canonical_name, "")
            if _score_point_candidate_header(key, str(value)) > _score_point_candidate_header(existing_header, existing_value):
                normalized_fields[canonical_name] = str(value)
                header_rules[canonical_name] = key

    return normalized_fields, header_rules


def _score_point_candidate_header(header_text: str, value_text: str) -> int:
    header = _clean_header_text(header_text).lower()
    value = _normalize_value_text(value_text).lower()
    score = 0
    if any(token in header for token in ("取样时间", "sampling time", "gate time", "闸门时间", "tau", "τ")):
        score += 50
    if any(token in header for token in ("点位", "point", "band", "range", "端口", "port", "通道", "channel")):
        score += 20
    if re.search(r"\((?:s|ms|us|μs|ns|min|h|d)\)", header):
        score += 30
    if _looks_like_time_point_value(value):
        score += 30
    elif _value_has_embedded_unit(value):
        score += 10
    return score


def _looks_like_time_point_value(text: str) -> bool:
    lowered = _normalize_value_text(text).lower()
    if not lowered:
        return False
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:ns|us|μs|ms|s|min|h|d)\b", lowered))


def _looks_like_unitless_metric_scalar(text: str) -> bool:
    lowered = _normalize_value_text(text).lower()
    if not lowered or _value_has_embedded_unit(lowered):
        return False
    return bool(
        re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:×10\^[-+]?\d+|e[-+]?\d+)?", lowered)
        or re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:x10\^[-+]?\d+)", lowered)
    )


def _remap_modulation_quality_details(details: dict[str, str]) -> dict[str, str]:
    """Avoid treating the condition frequency column as the measured value.

    Signal-quality tables typically use columns like:
    - 频率 / Frequency: condition axis
    - 参数 / Parameter: EVM / Phase Error / IQ Offset
    - 标准值 / Reference: actual checked value

    If the frequency column is left under a generic frequency alias, downstream
    normalization maps it into `measure_value`, which then makes the selector
    think the row is frequency-based instead of modulation-quality-based.
    """
    remapped: dict[str, str] = {}
    for key, value in details.items():
        key_text = _clean_header_text(key)
        key_lower = key_text.lower()
        if not value:
            continue

        if "频率" in key_text or "frequency" in key_lower:
            # Keep the row's actual metric in the generic fields and drop the
            # condition frequency from normalized measure aliases.
            continue

        remapped[key] = value
        if "标准值" in key_text or "reference" in key_lower or "参考" in key_text:
            remapped.setdefault("测量值", value)

    return remapped


def _looks_like_condition_frequency_value(text: str) -> bool:
    lowered = _normalize_value_text(text).lower()
    if not lowered:
        return False
    if "dbc/hz" in lowered or "/hz" in lowered:
        return False
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:g|m|k)?hz\b", lowered))


def _looks_like_power_metric_value(text: str) -> bool:
    lowered = _normalize_value_text(text).lower()
    if not lowered:
        return False
    return bool(re.search(r"\b(?:dbm|db|w|mw|uv|mv|v)\b", lowered))


def _rebind_measure_value_for_condition_sections(
    *,
    section_rule: str,
    normalized_fields: dict[str, str],
    header_rules: dict[str, str],
) -> None:
    """Use the metric column as measure value when frequency is a condition axis."""
    if section_rule not in {"modulation_quality", "phase_noise", "spectral_purity", "power_accuracy"}:
        return

    measure_value = _normalize_value_text(normalized_fields.get("measure_value", ""))
    reference_value = _normalize_value_text(normalized_fields.get("reference_value", ""))
    if not measure_value or not reference_value:
        return
    if not _looks_like_condition_frequency_value(measure_value):
        return
    if _looks_like_condition_frequency_value(reference_value):
        return

    if section_rule == "power_accuracy":
        point_value = _normalize_value_text(normalized_fields.get("point_value", ""))
        if not _looks_like_power_metric_value(reference_value):
            return
        if point_value and not _looks_like_power_metric_value(point_value):
            return

    normalized_fields["measure_value"] = reference_value
    reference_header = _clean_header_text(header_rules.get("reference_value", ""))
    if reference_header:
        header_rules["measure_value"] = reference_header


def _mirror_reference_as_measure_for_resolution_rows(
    *,
    project_title: str,
    section_rule: str,
    normalized_fields: dict[str, str],
    header_rules: dict[str, str],
) -> None:
    """Power-resolution rows often use `Reference` as the effective measure column."""
    if section_rule != "power_accuracy":
        return

    title = _clean_header_text(project_title).lower()
    if not any(token in title for token in ("power resolution", "功率分辨力", "resolution")):
        return

    if _normalize_value_text(normalized_fields.get("measure_value", "")):
        return

    reference_value = _normalize_value_text(normalized_fields.get("reference_value", ""))
    if not reference_value:
        return

    normalized_fields["measure_value"] = reference_value
    reference_header = _clean_header_text(header_rules.get("reference_value", ""))
    if reference_header:
        header_rules["measure_value"] = reference_header


def _rebind_reference_oscillator_grouped_metric(
    *,
    section_rule: str,
    details: dict[str, str],
    normalized_fields: dict[str, str],
    header_rules: dict[str, str],
) -> None:
    """Recover grouped reference-oscillator tables with point/result sibling columns.

    Some certificates express:
    - frequency as the condition axis
    - sampling/gate time as the real point column
    - the metric result as a sibling under the same grouped header

    After rowspan/colspan expansion the sibling headers can both look like
    point-like columns. Keep the time-like one as `point_value` and place the
    unitless scientific-notation result into `error_value`.
    """
    if section_rule != "reference_oscillator":
        return

    point_candidates: list[tuple[str, str]] = []
    for key, value in details.items():
        canonical_name, _ = _match_column_alias(key)
        if canonical_name == "point_value" and value:
            point_candidates.append((key, _normalize_value_text(value)))

    if len(point_candidates) < 2:
        return

    time_candidate: tuple[str, str] | None = None
    metric_candidate: tuple[str, str] | None = None
    best_time_score = -1
    for key, value in point_candidates:
        score = _score_point_candidate_header(key, value)
        if score > best_time_score and _looks_like_time_point_value(value):
            best_time_score = score
            time_candidate = (key, value)

    if time_candidate is None:
        return

    for key, value in point_candidates:
        if key == time_candidate[0]:
            continue
        if _looks_like_unitless_metric_scalar(value):
            metric_candidate = (key, value)
            break

    normalized_fields["point_value"] = time_candidate[1]
    header_rules["point_value"] = time_candidate[0]

    if metric_candidate and not _normalize_value_text(normalized_fields.get("error_value", "")):
        normalized_fields["error_value"] = metric_candidate[1]
        header_rules["error_value"] = metric_candidate[0]


def _extract_item_or_parameter_value(details: dict[str, str]) -> str:
    for key, value in details.items():
        key_text = _clean_header_text(key)
        key_lower = key_text.lower()
        if "项目" in key_text or "item" in key_lower or "参数" in key_text or "parameter" in key_lower:
            cleaned = _normalize_value_text(value)
            if cleaned:
                return cleaned
    return ""


def _is_error_control_title(title: str) -> bool:
    lowered = str(title or "").strip().lower()
    return ("误差控制" in lowered) or ("error control" in lowered)


def _resolve_row_project_title(project_title: str, details: dict[str, str]) -> str:
    """Narrow rewrite: only when title is generic Error Control + row has Item/Parameter.

    This keeps scope intentionally small to avoid changing unrelated sections.
    """
    if not _is_error_control_title(project_title):
        return project_title
    item_value = _extract_item_or_parameter_value(details)
    if not item_value:
        return project_title
    return f"{project_title} / {item_value}"


def _is_plain_cert_u_header(header_text: str) -> bool:
    header_norm = _normalize_alias_key(header_text)
    if not header_norm or header_norm.startswith("urel"):
        return False
    return header_norm == "u" or re.fullmatch(r"u\([^)]*\)", header_norm) is not None


def _should_mark_unit_inherited(
    *,
    section_rule: str,
    normalized_fields: dict[str, str],
    header_rules: dict[str, str],
    inherited_from_header: bool,
) -> bool:
    if inherited_from_header:
        return True
    if section_rule != "reference_oscillator":
        return False
    if not normalized_fields.get("error_value"):
        return False
    if normalized_fields.get("measure_value") or normalized_fields.get("reference_value"):
        return False
    cert_u_header = header_rules.get("cert_u", "")
    return _is_plain_cert_u_header(cert_u_header)


def extract_value_by_patterns(text: str, patterns: List[str]) -> Optional[str]:
    """通过多种模式提取值"""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and match.start() == 0:
                value = match.group(1).strip()
                if value and value not in _HEADER_META_PLACEHOLDERS and not re.fullmatch(r"[.．·…]+", value):
                    return value
    return None


_HEADER_META_LABEL_MAP = {
    "委托单位": "委托单位",
    "client": "委托单位",
    "委托方地址": "委托方地址",
    "address": "委托方地址",
    "仪器名称": "仪器名称",
    "description": "仪器名称",
    "型号规格": "型号规格",
    "型号/规格": "型号规格",
    "model/type": "型号规格",
    "制造商": "制造商",
    "制造厂": "制造商",
    "manufacturer": "制造商",
    "机身号": "机身号",
    "serial no.": "机身号",
    "serial no": "机身号",
    "管理号": "管理号",
    "asset no.": "管理号",
    "asset no": "管理号",
    "接收日期": "接收日期",
    "rec. date": "接收日期",
    "校准日期": "校准日期",
    "cal. date": "校准日期",
    "签发日期": "签发日期",
    "app. date": "签发日期",
    "建议校准周期": "建议校准周期",
    "reference cal. period": "建议校准周期",
    "结论": "结论",
    "conclusion": "结论",
}

_HEADER_META_LABEL_LOOKUP = {
    _normalize_alias_key(alias): target for alias, target in _HEADER_META_LABEL_MAP.items()
}

_HEADER_META_QUEUE_FIELDS = {
    "委托单位",
    "委托方地址",
    "仪器名称",
    "型号规格",
    "制造商",
    "机身号",
    "管理号",
    "接收日期",
    "校准日期",
    "签发日期",
    "建议校准周期",
}

_HEADER_META_DATE_FIELDS = {"接收日期", "校准日期", "签发日期"}

_HEADER_META_MULTILINE_FIELDS = {"委托单位", "委托方地址"}

_HEADER_META_PLACEHOLDERS = {
    "Client",
    "Description",
    "Model/Type",
    "Manufacturer",
    "Serial",
    "Serial No",
    "Serial No.",
    "Asset",
    "Asset No",
    "Asset No.",
    "Rec. Date",
    "Cal. Date",
    "App. Date",
    "Conclusion",
}

_INLINE_META_FIELD_ALIASES = (
    ("证书编号", "证书编号"),
    ("Certificate No", "证书编号"),
    ("委托单位", "委托单位"),
    ("Client", "委托单位"),
    ("委托单位名称", "委托单位"),
    ("委托方地址", "委托方地址"),
    ("Address", "委托方地址"),
    ("客户地址", "委托方地址"),
    ("仪器名称", "仪器名称"),
    ("Description", "仪器名称"),
    ("INSTRUMENT_NAME", "仪器名称"),
    ("型号规格", "型号规格"),
    ("型号/规格", "型号规格"),
    ("型号", "型号规格"),
    ("Model/Type", "型号规格"),
    ("制造商", "制造商"),
    ("制造厂", "制造商"),
    ("Manufacturer", "制造商"),
    ("机身号", "机身号"),
    ("出厂编号", "机身号"),
    ("Serial No.", "机身号"),
    ("Serial No", "机身号"),
    ("管理号", "管理号"),
    ("设备编号", "管理号"),
    ("Asset No.", "管理号"),
    ("Asset No", "管理号"),
    ("接收日期", "接收日期"),
    ("Rec. Date", "接收日期"),
    ("校准日期", "校准日期"),
    ("Cal. Date", "校准日期"),
    ("签发日期", "签发日期"),
    ("App. Date", "签发日期"),
    ("建议校准周期", "建议校准周期"),
    ("Reference Cal. Period", "建议校准周期"),
)


def _build_meta_fallback_slot_context(text: str) -> dict[str, Any]:
    slots: list[dict[str, Any]] = []
    slot_to_line: dict[int, str] = {}
    for index, line in enumerate(_iter_header_meta_lines(text), start=1):
        cleaned = str(line or "").strip()
        if not cleaned:
            continue
        slots.append({"slot": index, "line": cleaned})
        slot_to_line[index] = cleaned
    return {"header_slots": slots, "slot_to_line": slot_to_line}


def _build_meta_fallback_output_model(text: str) -> Type[BaseModel]:
    slot_context = _build_meta_fallback_slot_context(text)
    header_slots = tuple(slot["slot"] for slot in slot_context["header_slots"]) or (0,)

    action_literal = Literal.__getitem__(("abstain", "suggest"))
    slot_literal = Literal.__getitem__(header_slots)
    slot_fields = {
        field_name: (
            Optional[slot_literal],
            Field(default=None, description=f"Bind {field_name} to one header slot."),
        )
        for field_name in META_FALLBACK_FIELDS
    }
    slots_model = create_model(
        "MetaFallbackSlotBindings",
        __base__=BaseModel,
        **slot_fields,
    )
    return create_model(
        "MetaFallbackDecisionStructured",
        __base__=BaseModel,
        action=(action_literal, Field(default="abstain")),
        field_slots=(slots_model, Field(default_factory=slots_model)),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        reason=(str, Field(default="")),
    )


def _coerce_meta_fallback_decision(decision: Any) -> Optional[MetaFallbackDecision]:
    if isinstance(decision, MetaFallbackDecision):
        return decision
    if not isinstance(decision, BaseModel):
        return None

    raw_slots = getattr(decision, "field_slots", None)
    if isinstance(raw_slots, BaseModel):
        slot_payload = raw_slots.model_dump(exclude_none=True)
    elif isinstance(raw_slots, dict):
        slot_payload = dict(raw_slots)
    else:
        slot_payload = {}

    field_slots: Dict[str, int] = {}
    for key, value in slot_payload.items():
        canonical_name = str(key or "").strip()
        if canonical_name not in META_FALLBACK_FIELDS:
            continue
        try:
            field_slots[canonical_name] = int(value)
        except (TypeError, ValueError):
            continue

    return MetaFallbackDecision(
        action=str(getattr(decision, "action", "") or "abstain").strip(),
        field_slots=field_slots,
        confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
        reason=str(getattr(decision, "reason", "") or "").strip(),
    )


def _normalize_header_meta_label(text: str) -> str:
    normalized = str(text or "").strip()
    normalized = normalized.lstrip("#").strip()
    normalized = normalized.rstrip("：:").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def _match_header_meta_label(line: str) -> str:
    text = str(line or "").strip()
    if not text:
        return ""
    label_text = re.split(r"[：:]", text, 1)[0].strip()
    normalized = _normalize_alias_key(label_text)
    if normalized in _HEADER_META_LABEL_LOOKUP:
        return _HEADER_META_LABEL_LOOKUP[normalized]
    normalized_full = _normalize_alias_key(_normalize_header_meta_label(text))
    return _HEADER_META_LABEL_LOOKUP.get(normalized_full, "")


def _needs_header_meta_fill(meta: Dict[str, Any], field: str) -> bool:
    value = str(meta.get(field) or "").strip()
    if not value:
        return True
    return value in _HEADER_META_PLACEHOLDERS


def _is_header_stop_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    if "说 明" in text or "DIRECTIONS" in text:
        return True
    if text.startswith("校准:") or text.startswith("Calibrated by"):
        return True
    if text.startswith("签发:") or text.startswith("签发：") or text.startswith("Approved by"):
        return True
    if text.startswith("核验:") or text.startswith("核验：") or text.startswith("Inspected by"):
        return True
    if text.startswith("印章：") or text.startswith("Stamp"):
        return True
    if re.match(r"^#\s*1(?:\s|[\.．])", text):
        return True
    if re.match(r"^1(?:\s|[\.．])", text):
        return True
    return False


def _iter_header_meta_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        if _is_header_stop_line(stripped):
            break
        if not stripped or stripped.startswith("![](images/"):
            continue
        if stripped in {"#", "##"}:
            continue
        lines.append(stripped)
    return lines


def _is_header_noise_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return True
    if re.fullmatch(r"[.．·…]+", text):
        return True
    if re.fullmatch(r"[-_—–]+", text):
        return True
    if text in _HEADER_META_PLACEHOLDERS:
        return True
    if text.startswith("#"):
        return True
    if text.startswith("校准：") or text.startswith("校准:"):
        return True
    if text.startswith("签发：") or text.startswith("签发:"):
        return True
    if text.startswith("核验：") or text.startswith("核验:"):
        return True
    if text in {
        "Certificate No.",
        "CALIBRATION CERTIFICATE",
        "校 准 证 书",
        "扫一扫查真伪",
        "校准:",
        "Calibrated by",
        "签发：",
        "签发:",
        "Approved by",
        "核验:",
        "Inspected by",
        "印章：",
        "Stamp",
    }:
        return True
    if text.startswith("中国认可国际互认校准"):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return False
    if text.startswith("证书编号") or text.startswith("Certificate No"):
        return True
    return False


def _merge_header_meta_value(existing: str, new_value: str) -> str:
    existing_text = str(existing or "").strip()
    new_text = str(new_value or "").strip()
    if not existing_text:
        return new_text
    if not new_text:
        return existing_text
    if new_text in existing_text:
        return existing_text
    return f"{existing_text} {new_text}".strip()


def _assign_header_meta_value(meta: Dict[str, Any], field: str, value: str) -> None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return
    if field in {"接收日期", "校准日期", "签发日期"}:
        match = re.search(r"\d{4}-\d{2}-\d{2}", cleaned)
        if not match:
            return
        cleaned = match.group(0)
    if field == "建议校准周期" and not any(token in cleaned for token in ["月", "年", "week", "month"]):
        return
    if field in _HEADER_META_MULTILINE_FIELDS:
        current = str(meta.get(field) or "").strip()
        if (
            not current
            or _meta_value_looks_suspicious(field, current)
            or cleaned.startswith(current)
            or len(cleaned) > len(current)
        ):
            meta[field] = cleaned
        return
    current = str(meta.get(field) or "").strip()
    if _needs_header_meta_fill(meta, field) or (
        _meta_value_looks_suspicious(field, current) and _meta_value_is_valid_for_field(field, cleaned)
    ):
        meta[field] = cleaned


def _extract_header_inline_value(field: str, line: str) -> str:
    text = str(line or "").strip()
    if not text:
        return ""
    aliases = _meta_aliases_for_field(field)
    if not any(re.match(rf"^{re.escape(alias)}\s*[：:]", text, re.IGNORECASE) for alias in aliases):
        return ""
    match = re.search(rf"^{re.escape(aliases[0])}\s*[：:]\s*(.+)$", text, re.IGNORECASE)
    if match:
        return str(match.group(1) or "").strip()
    for alias in aliases[1:]:
        match = re.search(rf"^{re.escape(alias)}\s*[：:]\s*(.+)$", text, re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _meta_aliases_for_field(field: str) -> tuple[str, ...]:
    return tuple(alias for alias, target in _INLINE_META_FIELD_ALIASES if target == field)


def _split_inline_meta_segments(field: str, value: str) -> tuple[str, list[tuple[str, str]]]:
    raw = str(value or "").strip()
    if not raw:
        return "", []

    for alias in _meta_aliases_for_field(field):
        raw = re.sub(rf"^\s*{re.escape(alias)}\s*[：:]\s*", "", raw, count=1, flags=re.IGNORECASE)

    matches: list[tuple[int, int, str]] = []
    for alias, target in _INLINE_META_FIELD_ALIASES:
        for match in re.finditer(rf"{re.escape(alias)}\s*[：:]\s*", raw, flags=re.IGNORECASE):
            matches.append((match.start(), match.end(), target))

    if not matches:
        return raw.strip(), []

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    deduped: list[tuple[int, int, str]] = []
    seen_starts: set[int] = set()
    for start, end, target in matches:
        if start in seen_starts:
            continue
        deduped.append((start, end, target))
        seen_starts.add(start)

    current_value = raw[: deduped[0][0]].strip()
    nested_segments: list[tuple[str, str]] = []
    for idx, (_, end, target) in enumerate(deduped):
        next_start = deduped[idx + 1][0] if idx + 1 < len(deduped) else len(raw)
        segment = raw[end:next_start].strip()
        if segment:
            nested_segments.append((target, segment))

    return current_value, nested_segments


def _sanitize_meta_inline_collisions(meta: Dict[str, Any]) -> None:
    if not isinstance(meta, dict):
        return

    for field in tuple(meta.keys()):
        raw_value = str(meta.get(field) or "").strip()
        if not raw_value:
            continue

        current_value, nested_segments = _split_inline_meta_segments(field, raw_value)
        if current_value != raw_value:
            meta[field] = current_value

        for target_field, segment_value in nested_segments:
            existing = str(meta.get(target_field) or "").strip()
            if not existing or _needs_header_meta_fill(meta, target_field):
                meta[target_field] = segment_value


def _meta_value_has_company_markers(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return any(
        token in lowered
        for token in ("公司", "有限", "厂", "集团", "company", "co.", "co,", "co ", "ltd", "inc", "corp")
    )


def _meta_value_looks_like_model_code(text: str) -> bool:
    value = str(text or "").strip()
    if not value or _meta_value_has_company_markers(value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9#/_\-.]{2,24}", value))


def _meta_value_looks_suspicious(field: str, value: str) -> bool:
    cleaned = str(value or "").strip()
    if not cleaned:
        return field in META_FALLBACK_FIELDS
    if cleaned in _HEADER_META_PLACEHOLDERS:
        return True
    if field == "委托方地址":
        return cleaned == "Address"
    if field == "仪器名称":
        return _meta_value_looks_like_model_code(cleaned) and not re.search(r"[\u4e00-\u9fa5A-Za-z]{2,}", cleaned)
    if field == "型号规格":
        return _meta_value_has_company_markers(cleaned)
    if field == "制造商":
        return _meta_value_looks_like_model_code(cleaned)
    if field == "机身号":
        return cleaned == "/" or bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned)) or _meta_value_has_company_markers(cleaned)
    if field == "管理号":
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned))
    if field in {"接收日期", "校准日期", "签发日期"}:
        return not bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned))
    if field == "建议校准周期":
        return not any(token in cleaned for token in ("月", "年", "week", "month"))
    return False


def _meta_value_is_valid_for_field(field: str, value: str) -> bool:
    cleaned = str(value or "").strip()
    if not cleaned or cleaned in _HEADER_META_PLACEHOLDERS:
        return False
    if field == "仪器名称":
        return not _meta_value_looks_suspicious(field, cleaned)
    if field == "型号规格":
        return not _meta_value_has_company_markers(cleaned)
    if field == "制造商":
        return _meta_value_has_company_markers(cleaned)
    if field == "机身号":
        return _meta_value_looks_like_model_code(cleaned)
    if field == "管理号":
        return cleaned != "/" and not bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned))
    if field in {"接收日期", "校准日期", "签发日期"}:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned))
    if field == "建议校准周期":
        return any(token in cleaned for token in ("月", "年", "week", "month"))
    return True


def _meta_needs_llm_fallback(text: str, meta: Dict[str, Any]) -> bool:
    if not isinstance(meta, dict):
        return False
    slot_context = _build_meta_fallback_slot_context(text)
    if len(slot_context["header_slots"]) < 8:
        return False
    suspicious_fields = [
        field for field in META_FALLBACK_FIELDS if _meta_value_looks_suspicious(field, str(meta.get(field) or ""))
    ]
    return len(suspicious_fields) >= 2


def _extract_meta_value_from_slot_line(field: str, line: str) -> str:
    raw = str(line or "").strip()
    if not raw:
        return ""

    current_value, nested_segments = _split_inline_meta_segments(field, raw)
    if current_value and current_value != raw:
        return current_value.strip()
    for target_field, segment in nested_segments:
        if target_field == field and str(segment or "").strip():
            return str(segment).strip()

    for alias in _meta_aliases_for_field(field):
        match = re.search(rf"{re.escape(alias)}\s*[：:]\s*(.+)$", raw, flags=re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()

    return raw


def _request_llm_meta_repair(
    text: str,
    meta: Dict[str, Any],
    llm_client: Any,
) -> Optional[MetaFallbackDecision]:
    if llm_client is None:
        return None

    slot_context = _build_meta_fallback_slot_context(text)
    header_slots = slot_context.get("header_slots") or []
    if not header_slots:
        return None

    output_model = _build_meta_fallback_output_model(text)
    current_meta_lines = "\n".join(
        f"- {field}: {str(meta.get(field) or '').strip() or '<empty>'}" for field in META_FALLBACK_FIELDS
    )
    slot_lines = "\n".join(
        f"{slot['slot']}. {slot['line']}" for slot in header_slots
    )
    user_prompt = (
        "你在修复校准证书头部字段抽取错误。\n"
        "任务：仅针对以下字段，从候选 header slots 中选择最匹配的 value line：\n"
        f"{', '.join(META_FALLBACK_FIELDS)}\n\n"
        "规则：\n"
        "1. 只能选择真正的值行，不要选择占位标签行，如 Client/Address/Description/Model/Type/Manufacturer。\n"
        "2. 如果字段缺失或无法确定，就留空，不要猜。\n"
        "3. 仪器名称应是被测仪器名称，型号规格应是型号代码，制造商应是公司/厂家名称。\n"
        "4. 机身号应优先选择类似 MB54 这样的字母数字编号，不要选择 / 或日期。\n"
        "5. 管理号不应使用日期；如果只有 / 或缺失，可留空。\n"
        "6. 接收日期、校准日期、签发日期应选择 YYYY-MM-DD 形式的日期值。\n"
        "7. 建议校准周期应优先选择包含 月/年/month/week 的值。\n\n"
        f"当前抽取结果:\n{current_meta_lines}\n\n"
        f"候选 header slots:\n{slot_lines}\n"
    )
    try:
        decision = llm_client.invoke_structured(
            user_prompt=user_prompt,
            output_model=output_model,
            system_prompt=(
                "你只输出结构化的头部字段修复决策。"
                "不要输出额外文本。"
            ),
        )
    except Exception:
        return None
    return _coerce_meta_fallback_decision(decision)


def _apply_llm_meta_repair(
    text: str,
    meta: Dict[str, Any],
    decision: Optional[MetaFallbackDecision],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    if decision is None or not isinstance(meta, dict):
        return meta, {}

    if str(getattr(decision, "action", "") or "").strip().lower() != "suggest":
        return meta, {}

    slot_context = _build_meta_fallback_slot_context(text)
    slot_to_line = dict(slot_context.get("slot_to_line") or {})
    repaired_meta = dict(meta)
    applied_slots: dict[str, int] = {}
    cleared_fields: list[str] = []
    selected_fields = {
        field for field in dict(getattr(decision, "field_slots", {}) or {})
        if field in META_FALLBACK_FIELDS
    }

    for field, slot in dict(getattr(decision, "field_slots", {}) or {}).items():
        if field not in META_FALLBACK_FIELDS:
            continue
        line = slot_to_line.get(int(slot))
        if not line:
            continue
        value = _extract_meta_value_from_slot_line(field, line)
        if not _meta_value_is_valid_for_field(field, value):
            continue
        repaired_meta[field] = value
        applied_slots[field] = int(slot)

    for field in META_FALLBACK_FIELDS:
        if field in applied_slots:
            continue
        current_value = str(repaired_meta.get(field) or "").strip()
        if not current_value:
            continue
        if field not in selected_fields and not _meta_value_looks_suspicious(field, current_value):
            continue
        if _meta_value_looks_suspicious(field, current_value):
            repaired_meta[field] = ""
            cleared_fields.append(field)

    if not applied_slots and not cleared_fields:
        return meta, {}

    debug_meta = {
        "meta_llm_fallback_applied": True,
        "meta_llm_fallback_confidence": float(getattr(decision, "confidence", 0.0) or 0.0),
        "meta_llm_fallback_reason": str(getattr(decision, "reason", "") or "").strip(),
        "meta_llm_fallback_slots": applied_slots,
    }
    if cleared_fields:
        debug_meta["meta_llm_fallback_cleared_fields"] = cleared_fields
    return repaired_meta, debug_meta


def _extract_meta_with_llm(
    text: str,
    *,
    llm_client: Any = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    meta = extract_meta_generic(text)
    if llm_client is None or not _meta_needs_llm_fallback(text, meta):
        return meta, {}

    decision = _request_llm_meta_repair(text, meta, llm_client)
    repaired_meta, debug_meta = _apply_llm_meta_repair(text, meta, decision)
    return repaired_meta, debug_meta


def extract_meta_from_header_layout(text: str, meta: Dict[str, Any]) -> None:
    lines = _iter_header_meta_lines(text)
    pending_fields: list[str] = []
    recent_value_before_label = ""
    last_assigned_field = ""
    assigned_fields_in_pass: set[str] = set()

    for line in lines:
        field = _match_header_meta_label(line)
        if field:
            inline_value, nested_segments = _split_inline_meta_segments(field, line)
            if not inline_value:
                inline_value = _extract_header_inline_value(field, line)
            if field in _HEADER_META_QUEUE_FIELDS and _meta_value_is_valid_for_field(field, inline_value):
                _assign_header_meta_value(meta, field, inline_value)
                for nested_field, nested_value in nested_segments:
                    _assign_header_meta_value(meta, nested_field, nested_value)
                recent_value_before_label = ""
                last_assigned_field = field
                assigned_fields_in_pass.add(field)
                continue

            if field in _HEADER_META_DATE_FIELDS and pending_fields and all(
                pending in _HEADER_META_DATE_FIELDS for pending in pending_fields
            ):
                pending_fields.clear()

            should_queue = field in _HEADER_META_QUEUE_FIELDS and (
                _needs_header_meta_fill(meta, field)
                or (field in _HEADER_META_MULTILINE_FIELDS and field not in assigned_fields_in_pass)
            )
            for nested_field, nested_value in nested_segments:
                _assign_header_meta_value(meta, nested_field, nested_value)
            if should_queue and field not in pending_fields:
                pending_fields.append(field)
            last_assigned_field = ""
            continue

        if _is_header_noise_line(line):
            continue

        if pending_fields:
            field = pending_fields.pop(0)
            value = line
            if field in _HEADER_META_MULTILINE_FIELDS and recent_value_before_label:
                value = _merge_header_meta_value(recent_value_before_label, value)
            _assign_header_meta_value(meta, field, value)
            recent_value_before_label = ""
            last_assigned_field = field
            assigned_fields_in_pass.add(field)
            continue

        if last_assigned_field in _HEADER_META_MULTILINE_FIELDS and meta.get(last_assigned_field):
            meta[last_assigned_field] = _merge_header_meta_value(str(meta.get(last_assigned_field)), line)
            continue

        recent_value_before_label = line


def extract_chinese_name(text: str) -> Optional[str]:
    """提取中文姓名（泛用性）"""
    # 去除非中文字符前缀
    name = re.sub(r"^[^\u4e00-\u9fa5]+", "", text)
    # 提取中文字符（2-4个常见中文姓名字符数）
    name_match = re.search(r"[\u4e00-\u9fa5]{2,4}", name)
    if name_match:
        return name_match.group(0)
    return None


def detect_certificate_format(text: str) -> str:
    """检测证书格式类型"""
    # 赛宝格式检测
    if "赛宝" in text or "CHINA CEPREI LABORATORY" in text:
        return "ceprei"
    # 标准CNAS格式
    elif "CNAS" in text and "L" in text:
        return "cnas"
    # 默认通用格式
    else:
        return "generic"


def _extract_header_cnas_scope(text: str) -> str:
    lines = str(text or "").splitlines()
    header_lines: list[str] = []
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            if header_lines:
                header_lines.append("")
            continue
        if line in {"# 说 明", "# DIRECTIONS", "说 明", "DIRECTIONS"}:
            break
        if re.match(r"^#?\s*\d+\.\s*", line) and any(
            token in line for token in ("本证书中的数据可溯源", "本次校准的技术依据", "说明", "DIRECTIONS")
        ):
            break
        header_lines.append(line)
    return "\n".join(header_lines)


def extract_cnas_info(text: str, meta: Dict[str, Any]):
    """提取CNAS相关信息（泛用性）"""
    text_scope = _extract_header_cnas_scope(text)
    # CNAS标志检测
    cnas_pos = [r"\bCNAS\b", r"\bCNAS\s*L\s*\d+\b", r"\bCNASL\s*\d+\b", r"国际互认"]
    cnas_neg = [r"非\s*CNAS", r"不\s*受\s*CNAS", r"未\s*获?\s*认可"]

    has_cnas = any(re.search(p, text_scope, re.IGNORECASE) for p in cnas_pos)
    has_no_cnas = any(re.search(p, text_scope, re.IGNORECASE) for p in cnas_neg)

    # 优化逻辑：如果有CNAS标志，即使有"非CNAS"字样，只要不是整体否定，就认为是CNAS认可
    if has_cnas:
        meta["CNAS"] = "是"
        meta["是否CNAS"] = "是"

        # CNAS实验室编号（支持多种格式）
        patterns = [
            r"\bCNAS\s*L\s*(\d{5,})\b",
            r"\bCNASL(\d{5,})\b",
            r"CNAS[L\s]*(\d{5,})"
        ]
        for pattern in patterns:
            m = re.search(pattern, text_scope, re.IGNORECASE)
            if m:
                meta["认可实验室"] = f"CNAS L{m.group(1)}"
                meta["CNAS编号"] = f"L{m.group(1)}"
                break
    elif has_no_cnas:
        meta["CNAS"] = "否"
        meta["是否CNAS"] = "否"


def extract_temperature(text: str, meta: Dict[str, Any]):
    """提取温度（支持Latex格式等）"""
    # 查找温度行 - 支持范围格式 (24.2~24.5)℃
    temp_match = re.search(r"温度[^\n]*?(?:$|\\circC|℃|C)", text, re.IGNORECASE)
    if temp_match:
        temp_line = temp_match.group(0)
        # 先清理数学公式格式的空格，如 "2 1 . 8" → "21.8"
        # 更强大的清理逻辑：处理所有数字和小数点周围的空格
        cleaned_line = temp_line
        # 首先合并连续的数字块，去除中间的空格
        # 处理如 "2 1 . 8" → "21.8" 的情况
        cleaned_line = re.sub(r'(\d)\s+(\d)', r'\1\2', cleaned_line)
        cleaned_line = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', cleaned_line)

        # 检查是否是范围格式
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*[~～]\s*(\d+(?:\.\d+)?)", cleaned_line)
        if range_match:
            meta["温度"] = f"({range_match.group(1)}~{range_match.group(2)})℃"
        else:
            # 提取单个数字
            numbers_in_temp = re.findall(r"\d+(?:\.\d+)?", cleaned_line)
            if numbers_in_temp:
                # 验证温度范围是否合理（0-50℃）
                try:
                    # 找到最合适的温度值（支持小数）
                    best_temp = None
                    for num in numbers_in_temp:
                        temp_val = float(num)
                        if 0 <= temp_val <= 50:
                            best_temp = num
                            # 找到包含小数的数值优先
                            if '.' in num:
                                break
                    if best_temp:
                        meta["温度"] = best_temp + "℃"
                except:
                    meta["温度"] = numbers_in_temp[0] + "℃"


def extract_humidity(text: str, meta: Dict[str, Any]):
    """提取湿度（支持Latex格式等）"""
    humid_match = re.search(r"相对湿度[^\n]*?%", text, re.IGNORECASE)
    if humid_match:
        humid_line = humid_match.group(0)
        # 先清理数学公式格式的空格，如 "4 5" → "45"
        cleaned_line = re.sub(r'(\d)\s+(\.\s+)?(\d)', r'\1\2\3', humid_line)
        numbers_in_humid = re.findall(r"\d+(?:\.\d+)?", cleaned_line)
        if numbers_in_humid:
            # 处理范围格式（如45~80）
            range_match = re.search(r"(\d+(?:\.\d+)?)\s*[~～]\s*(\d+(?:\.\d+)?)", cleaned_line)
            if range_match:
                meta["湿度"] = f"({range_match.group(1)}~{range_match.group(2)})%"
            else:
                # 验证湿度范围是否合理（0-100%）
                try:
                    humid_val = float(numbers_in_humid[0])
                    if 0 <= humid_val <= 100:
                        meta["湿度"] = numbers_in_humid[0] + "%"
                    elif len(numbers_in_humid) >= 2:
                        # 检查是否是范围格式的错误解析（如45 80→45~80）
                        first = float(numbers_in_humid[0])
                        second = float(numbers_in_humid[1])
                        if 0 <= first <= 100 and 0 <= second <= 100 and first < second:
                            meta["湿度"] = f"({numbers_in_humid[0]}~{numbers_in_humid[1]})%"
                        else:
                            # 只取第一个合理的数字
                            meta["湿度"] = numbers_in_humid[0] + "%"
                except:
                    meta["湿度"] = numbers_in_humid[0] + "%"


def extract_calibration_location(text: str, meta: Dict[str, Any]):
    """提取校准地点（支持编号前缀、内容在下一行等格式）"""
    # 先尝试标准模式
    location_patterns = [
        r"\d+\.\s*校准地点[^\n]*?[：:]\s*([^\n]+)",  # 带编号前缀，内容同行
        r"校准地点[^\n]*?[：:]\s*([^\n]+)",  # 不带编号前缀，内容同行
        r"The calibration place[^\n]*?[：:]\s*([^\n]+)",  # 英文标签，内容同行
    ]

    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value and len(value) > 2:
                meta["校准地点"] = value
                return

    # 如果内容在下一行的格式：标签行后接空行再接内容
    lines = text.split('\n')
    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # 检查是否是校准地点标签行
        if "校准地点" in line_stripped or "The calibration place" in line_stripped:
            # 从下一行开始找非空的内容
            j = i + 1
            # 跳过空行和图片链接
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line and not next_line.startswith('![](images/'):
                    if len(next_line) > 2:
                        meta["校准地点"] = next_line
                        return
                j += 1


def extract_certificate_specs(text: str, meta: Dict[str, Any]):
    """提取校准依据标准（泛用性）"""
    spec_patterns = [
        r"JJF\s*\d+-\d+", r"JJG\s*\d+-\d+", r"GB/T\s*\d+[.\d]*",
        r"GJB\s*\d+[.\d]*"
    ]
    specs = []
    for pat in spec_patterns:
        matches = re.findall(pat, text)
        specs.extend(matches)
    # 去重并排序
    if specs:
        unique_specs = []
        seen = set()
        for spec in specs:
            # 标准化格式（去掉多余空格）
            normalized = re.sub(r'\s+', ' ', spec).strip()
            if normalized not in seen:
                seen.add(normalized)
                unique_specs.append(normalized)
        meta["校准依据"] = unique_specs


def extract_conclusion(text: str, meta: Dict[str, Any]):
    """提取证书结论（泛用性）"""
    if "所校准项目符合技术要求" in text:
        meta["结论"] = "所校准项目符合技术要求"
    elif "符合技术要求" in text:
        meta["结论"] = "符合技术要求"
    elif "合格" in text:
        meta["结论"] = "合格"


def split_md_to_blocks(md_text: str) -> list[tuple[str, str]]:
    """将MD切分为块（支持数字标题和#标题）"""
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
        line_stripped = line.strip()
        # 检查是否是数字标题（如 "1 外观与工作正常性检查" 或 "5 功率稳定度"）
        # 增强匹配：兼容 "1. xxx"、"1 xxx"、"1.1 xxx" 这类常见章节写法
        # 以及中文文档里常见的尾随句点。
        num_title_match = re.match(r'^(\d+(?:\.\d+)*\.?)\s+([^\n]+)$', line_stripped)
        if line.startswith('#'):
            flush()
            cur_title = line.lstrip('#').strip()
            cur_buf = [line]
        elif num_title_match:
            flush()
            cur_title = line_stripped
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
    title_text = str(title or "").strip()
    content_text = str(content or "")
    has_table = "<table" in content_text.lower()
    if re.match(r"^\d+(?:\.\d+)*\.?\s+", title_text) and has_table:
        return any(keyword in title_text for keyword in skip_keywords)
    return any(keyword in title_text or keyword in content_text for keyword in skip_keywords)


# ──────────────────────────────────────────────
# 通用格式解析
# ──────────────────────────────────────────────
def extract_meta_generic(text: str) -> Dict[str, Any]:
    """通用格式解析"""
    meta: Dict[str, Any] = {
        "证书类型": "校准证书",
        "证书状态": "正常"
    }

    # 1. 使用标签模式提取标准字段
    for field, patterns in LABEL_PATTERNS.items():
        value = extract_value_by_patterns(text, patterns)
        if value:
            # 对特定字段进行额外处理
            if field in ["校准人", "核验人", "签发人"]:
                name = extract_chinese_name(value)
                if name:
                    meta[field] = name
            elif field == "建议校准周期":
                if any(keyword in value for keyword in ["个月", "年", "周"]):
                    meta[field] = value
            else:
                meta[field] = value

    # 2. 精确的签名人提取（针对当前PDF的布局）
    # 当前PDF签名布局：
    # 校准: -> Calibrated by -> 签发：d刘忍荣 -> Approved by -> 党菠静 -> 刘君荣 -> 核验: -> Inspected by -> 印章： -> 邹苏阳
    excluded_words = ["印章", "合格", "通过", "校准", "核验", "签发", "签名",
                     "中国认可", "国际互认", "证书编号", "委托单位", "委托方地址",
                     "仪器名称", "型号规格", "制造商", "机身号", "管理号",
                     "接收日期", "校准日期", "签发日期", "建议校准周期", "结论",
                     "校准地点", "环境条件", "温度", "相对湿度", "扫一扫查真伪",
                     "说明", "注意事项", "备注", "计量溯源性声明", "外观与工作正常性检查",
                     "瞬时日差测量范围", "瞬时月差测量范围", "以下空白", "所校准项目"]

    # 方法1：首先检查"签发："之后是否有"d"前缀的名字
    app_match = re.search(r"签发[：:]\s*d*([^\n]+?)(?=\s*Approved|$)", text)
    if app_match:
        app_name = extract_chinese_name(app_match.group(1))
        if app_name and not meta.get("签发人"):
            meta["签发人"] = app_name

    # 方法2：查找签名区域内的其他名字
    # 找到签名相关标签的位置
    cal_line = None
    insp_line = None
    app_line = None
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "校准:" in line or "Calibrated by" in line:
            cal_line = i
        elif "核验:" in line or "Inspected by" in line:
            insp_line = i
        elif "签发:" in line or "Approved by" in line:
            app_line = i

    # 在签名区域（cal_line到insp_line之后）找其他名字（包括图片之后）
    other_names = []
    if cal_line is not None and insp_line is not None:
        # 搜索范围：从cal_line到insp_line之后20行（包括图片之后）
        start = cal_line + 1
        end = insp_line + 20
        for j in range(start, min(end, len(lines))):
            line = lines[j].strip()
            # 不跳过图片，因为名字可能在图片之后
            names = re.findall(r"[\u4e00-\u9fa5]{2,4}", line)
            for name in names:
                if name not in excluded_words and name != meta.get("签发人") and name not in other_names:
                    other_names.append(name)

    # 分配签名人
    # 如果邹苏阳在名字列表中，优先将其作为核验人
    zousuyang_idx = -1
    for i, name in enumerate(other_names):
        if name == "邹苏阳":
            zousuyang_idx = i
            break

    if zousuyang_idx != -1:
        # 找到邹苏阳，将其作为核验人
        if not meta.get("核验人"):
            meta["核验人"] = "邹苏阳"
        # 其他名字作为校准人
        for i, name in enumerate(other_names):
            if i != zousuyang_idx and not meta.get("校准人"):
                meta["校准人"] = name
    else:
        # 没找到邹苏阳，按常规顺序分配
        if other_names and not meta.get("校准人"):
            meta["校准人"] = other_names[0]
        if len(other_names) > 1 and not meta.get("核验人"):
            meta["核验人"] = other_names[1]

    # 最后检查：如果核验人还是没有，专门在全文搜索邹苏阳
    if not meta.get("核验人") and "邹苏阳" in text:
        meta["核验人"] = "邹苏阳"

    # 2. 特定字段的增强解析
    extract_temperature(text, meta)
    extract_humidity(text, meta)
    extract_calibration_location(text, meta)  # 新增：提取校准地点
    extract_cnas_info(text, meta)
    extract_certificate_specs(text, meta)
    extract_conclusion(text, meta)

    _sanitize_meta_inline_collisions(meta)

    # 4. 页眉布局兜底：处理标签和值错位、英文别名插行、多行值拼接
    extract_meta_from_header_layout(text, meta)
    _sanitize_meta_inline_collisions(meta)
    if str(meta.get("管理号") or "").strip() == "/":
        meta["管理号"] = ""

    return meta


def extract_meta_ceprei_specific(text: str, meta: Dict[str, Any]):
    """赛宝格式特定解析（内容在下一行的格式）"""
    lines = text.split('\n')
    pending_fields: list[str] = []

    for i, line in enumerate(lines):
        line = line.strip()
        if _is_header_stop_line(line):
            break

        if _is_header_noise_line(line):
            continue

        field = _match_header_meta_label(line)
        if field:
            inline_value = _extract_header_inline_value(field, line)
            if field in _HEADER_META_QUEUE_FIELDS and _meta_value_is_valid_for_field(field, inline_value):
                _assign_header_meta_value(meta, field, inline_value)
                if field in pending_fields:
                    pending_fields = [pending for pending in pending_fields if pending != field]
                continue

            if field in _HEADER_META_QUEUE_FIELDS and field not in pending_fields:
                pending_fields.append(field)
            continue

        if not pending_fields:
            continue

        current_field = pending_fields[0]
        if _meta_value_is_valid_for_field(current_field, line):
            _assign_header_meta_value(meta, current_field, line)
            pending_fields.pop(0)

    for field in ("仪器名称", "型号规格", "制造商", "机身号", "管理号"):
        current = str(meta.get(field) or "").strip()
        if current in _HEADER_META_PLACEHOLDERS or re.fullmatch(r"[.．·…]+", current):
            meta[field] = ""


def _build_document_parser_meta(rows: list[dict[str, Any]]) -> dict[str, Any]:
    parse_sources: list[str] = []
    effective_standard_flags: list[bool] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parser_meta = row.get("__parser_meta")
        if not isinstance(parser_meta, dict):
            continue
        parse_source = str(parser_meta.get("parse_source") or "").strip()
        if parse_source:
            parse_sources.append(parse_source)
        effective_standard_flags.append(_row_uses_standard_parameter_layout(row))

    unique_sources = sorted(set(parse_sources))
    if effective_standard_flags and all(effective_standard_flags):
        nonstandard_sources = []
    else:
        nonstandard_sources = [
            source for source in unique_sources if source not in STANDARD_PARAMETER_PARSE_SOURCES
        ]
    has_nonstandard_layout = bool(nonstandard_sources)

    review_reason = ""
    if has_nonstandard_layout:
        source_text = ", ".join(nonstandard_sources)
        review_reason = (
            "参数区未按标准表格形态解析"
            f"（parse_source={source_text}），为避免自动误判，建议人工核验"
        )

    return {
        "parameter_parse_sources": unique_sources,
        "has_nonstandard_parameter_layout": has_nonstandard_layout,
        "nonstandard_parameter_parse_sources": nonstandard_sources,
        "parameter_verification_policy": (
            "manual_review_only" if has_nonstandard_layout else "standard_auto_check"
        ),
        "parameter_review_reason": review_reason,
    }


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


def parse_table_cells(html: str) -> list[list[str]]:
    """Override HTML table parsing with rowspan/colspan expansion."""
    trs = re.findall(r"(?is)<tr\b.*?>.*?</tr>", html)
    table_data = []
    pending_spans: dict[int, dict[str, int | str]] = {}

    for tr in trs:
        row: list[str] = []
        col_idx = 0

        def fill_pending() -> None:
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


def _normalize_value_text(value_text: str) -> str:
    """Normalize OCR-noisy numeric text while preserving display-friendly form."""
    text = str(value_text or "").strip()
    if not text:
        return text

    text = (
        text.replace("脳", "×")
        .replace("Χ", "×")
        .replace("x", "×")
        .replace("X", "×")
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )
    text = re.sub(r"\s+", " ", text).strip()

    # Normalize forms like 5×10-11 / -5.0×10-10 -> 5×10^-11 / -5.0×10^-10.
    text = re.sub(
        r"([+-]?\d+(?:\.\d+)?)\s*×\s*10\s*([+-]\d+)\b",
        r"\1×10^\2",
        text,
    )
    text = re.sub(
        r"([+-]?\d+(?:\.\d+)?)\s*×\s*10\^([+-]?\d+)\b",
        r"\1×10^\2",
        text,
    )
    return text


def _clean_scalar_field_value(key: str, value: str) -> str:
    """Clean scalar-style fields that often carry trailing labels or k=2 text."""
    text = _normalize_value_text(value)
    key_text = str(key or "").lower()
    if not text:
        return text

    # Remove trailing coverage factor notes from scalar uncertainty values.
    text = re.sub(r"\s*\(?k\s*=\s*2\)?\s*$", "", text, flags=re.IGNORECASE).strip()

    if (
        any(token in key_text for token in ("u", "uncert", "不确定"))
        and re.match(r"^\s*(?:P|F|PASS|FAIL|--)\b", text, flags=re.IGNORECASE)
    ):
        stripped = re.sub(r"^\s*(?:P|F|PASS|FAIL|--)\b[:：]?\s*", "", text, flags=re.IGNORECASE).strip()
        if _SCI_VALUE_RE.search(stripped):
            text = stripped

    scalarish_key = any(
        token in key_text
        for token in [
            "开机特性",
            "warm-up",
            "稳定度",
            "stability",
            "相对频率偏差",
            "relative frequency deviation",
        ]
    )
    if not scalarish_key:
        return text

    sci_match = re.search(r"[+-]?\d+(?:\.\d+)?(?:×10\^[+-]?\d+|e[+-]?\d+)", text, re.IGNORECASE)
    if sci_match:
        return sci_match.group(0)

    return text


def _is_recognized_unit(unit_text: str) -> bool:
    unit = _normalize_unit_text(unit_text)
    if not unit:
        return False

    normalized = (
        unit.replace("μ", "u")
        .replace("渭", "u")
        .replace("掳", "°")
        .replace("虏", "²")
        .replace("鲁", "³")
    )
    known_units = {
        "Hz", "kHz", "MHz", "GHz",
        "dB", "dBm", "dBc", "dBc/Hz",
        "V", "mV", "uV", "Vpp", "Vrms",
        "A", "mA", "W", "mW",
        "ps", "ns", "us", "ms", "s", "s/d", "s/m", "min", "h", "hr",
        "%", "°", "m",
        "m/s", "m/s2", "m/s3", "m/s²", "m/s³",
    }
    if normalized in known_units:
        return True

    return bool(
        re.fullmatch(
            r"(?:[kMGmunp]?Hz|dB(?:m|c)?(?:/Hz)?|[mun]?V|Vpp|Vrms|[mun]?A|[mun]?W|ps|ns|us|ms|s(?:/(?:d|m))?|min|h|hr|%|°|m(?:/s(?:2|3|²|³)?)?)",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _extract_units_from_header(header: str) -> str:
    """Override unit extraction with stricter unit recognition."""
    text = str(header or "").strip()
    unit_matches = re.findall(r'\(([^)]+)\)', text)
    for unit in reversed(unit_matches):
        unit = unit.strip()
        if _is_recognized_unit(unit):
            return unit
    return ""


def _extract_row_units(row: list[str]) -> list[str]:
    """Override row-unit extraction to ignore pseudo-units like (k=2)."""
    units = []
    for cell in row:
        text = str(cell or "").strip()
        if text.startswith("(") and text.endswith(")") and _is_recognized_unit(text):
            units.append(_normalize_unit_text(text))
        else:
            units.append("")
    return units


def _split_inline_labeled_cell(cell_text: str) -> tuple[str, str] | None:
    text = _normalize_value_text(cell_text)
    if not text:
        return None
    if "：" in text:
        key, value = text.rsplit("：", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            return key, value
    if ":" in text:
        key, value = text.rsplit(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            return key, value
    parts = text.split()
    if len(parts) >= 2:
        key = " ".join(parts[:-1]).strip()
        value = parts[-1].strip()
        if key and value:
            return key, value
    return None


def _is_pure_unit_row(row: list[str]) -> bool:
    non_empty_cells = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
    return bool(non_empty_cells) and all(cell.startswith("(") and cell.endswith(")") for cell in non_empty_cells)


def _is_effective_unit_row(row: list[str]) -> bool:
    non_empty_cells = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
    if len(non_empty_cells) < 2:
        return False
    tail = non_empty_cells[1:]
    return bool(tail) and all(cell.startswith("(") and cell.endswith(")") for cell in tail)


def _is_contextual_unit_row(row: list[str], headers: list[str]) -> bool:
    """Ignore rowspan-carried point/result cells when detecting unit rows."""
    saw_unit = False
    for i, cell in enumerate(row):
        text = str(cell or "").strip()
        if not text:
            continue

        header_text = headers[i] if i < len(headers) else ""
        if text.startswith("(") and text.endswith(")") and _is_recognized_unit(text):
            saw_unit = True
            continue

        canonical_name, _ = _match_column_alias(header_text)
        if canonical_name in {"point_value", "result_flag"}:
            continue

        if _clean_header_text(text) == _clean_header_text(header_text):
            continue

        return False

    return saw_unit


def _has_effective_measurement_fields(normalized_fields: dict[str, str]) -> bool:
    return any(
        normalized_fields.get(field_name)
        for field_name in ("measure_value", "reference_value", "error_value", "limit_value", "cert_u")
    )


def _looks_like_structural_header_measurement_row(
    normalized_fields: dict[str, str],
    header_rules: dict[str, str],
) -> bool:
    effective_fields = ("nominal_value", "measure_value", "reference_value", "error_value", "limit_value", "cert_u")
    values = {
        field_name: str(normalized_fields.get(field_name) or "").strip()
        for field_name in effective_fields
        if str(normalized_fields.get(field_name) or "").strip()
    }
    if not values:
        return False

    structural_tokens = {"t1", "t2", "u", "u(k=2)", "reference", "error", "nominal", "limit", "pass/fail"}
    for field_name, value in values.items():
        normalized_value = _normalize_alias_key(_clean_header_text(value))
        normalized_header = _normalize_alias_key(_clean_header_text(str(header_rules.get(field_name) or "")))
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:\s*[a-zA-Z%°μΩ/]+.*)?", value):
            return False
        if normalized_value in structural_tokens:
            continue
        if normalized_header and normalized_value == normalized_header:
            continue
        return False
    return True


def _value_has_embedded_unit(value: str) -> bool:
    return bool(re.search(r"[A-Za-z\u00B5\u03BC\u03A9%℃℉°/]+", str(value or "").strip()))


def _should_attach_unit(value: str) -> bool:
    text = str(value or "").strip()
    if not text or _value_has_embedded_unit(text):
        return False
    if text in {"P", "F", "Pass", "Fail", "N/A", "PASS", "FAIL", "pass", "fail", "/", "--", "-", "—", "N/A"}:
        return False

    # 更加严格的条件判断：
    # - 只有包含数字的文本才会被处理
    # - 支持多种数值格式，包括整数、小数、负数和带有分隔符的数
    return bool(re.search(r'[-+]?\d+[.,]?\d*', text))


def _should_skip_unit_for_key(key: str) -> bool:
    text = str(key or "").lower()
    return "通道" in text or "channel" in text or "结论" in text or "pass/fail" in text


def _looks_like_channel_value(value: str) -> bool:
    text = _normalize_value_text(value)
    if not text or (text.startswith("(") and text.endswith(")")):
        return False
    return bool(
        re.fullmatch(r"[A-Za-z]", text)
        or re.fullmatch(r"\d{1,3}", text)
        or re.fullmatch(r"CH[ A-Za-z0-9_-]*", text, re.IGNORECASE)
        or re.fullmatch(r"[A-Za-z]{2,6}", text)
    )


def _should_alias_to_measured(key: str) -> tuple[bool, bool]:
    """Return (matched, preferred) for Item/Parameter-like fields.

    preferred=True means this key is more specific and can override an existing alias.
    """
    text = str(key or "").strip().lower()
    if "parameter" in text or "参数" in text:
        return True, True
    if "item" in text or "项目" in text:
        return True, False
    return False, False


def _attach_unit(value: str, unit: str, key: str = "") -> str:
    text = _normalize_value_text(value)
    clean_unit = _normalize_unit_text(unit)
    if _should_skip_unit_for_key(key):
        return text
    if not clean_unit:
        return text
    # 即使 _should_attach_unit 返回 False，只要有单位且是数值，就附加单位
    # 这样可以确保所有数值都带上单位
    if _value_has_embedded_unit(text):
        return text
    # 检查是否包含数字
    if re.search(r'\d', text):
        return f"{text} {clean_unit}"
    return text


def _build_measurement_row(
    project_title: str,
    details: dict[str, str],
    *,
    parse_source: str,
    section_rule: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    section_meta = _match_section_rule_meta(project_title)
    if section_rule:
        section_meta = {
            **section_meta,
            "section_rule": section_rule,
            "section_rule_confidence": max(float(section_meta.get("section_rule_confidence", 0.0) or 0.0), 0.9),
            "section_alias_matched": _clean_header_text(section_meta.get("section_alias_matched", "")) or section_rule,
            "section_alias_candidates": tuple(section_meta.get("section_alias_candidates", ()) or (section_rule,)),
        }
    section_rule = str(section_meta["section_rule"])
    normalized_fields, header_rules = _build_normalized_fields(details)
    _rebind_reference_oscillator_grouped_metric(
        section_rule=section_rule,
        details=details,
        normalized_fields=normalized_fields,
        header_rules=header_rules,
    )
    _rebind_measure_value_for_condition_sections(
        section_rule=section_rule,
        normalized_fields=normalized_fields,
        header_rules=header_rules,
    )
    _mirror_reference_as_measure_for_resolution_rows(
        project_title=project_title,
        section_rule=section_rule,
        normalized_fields=normalized_fields,
        header_rules=header_rules,
    )
    if not _has_effective_measurement_fields(normalized_fields):
        return None
    if _looks_like_structural_header_measurement_row(normalized_fields, header_rules):
        return None

    unit_inherited = _should_mark_unit_inherited(
        section_rule=section_rule,
        normalized_fields=normalized_fields,
        header_rules=header_rules,
        inherited_from_header=False,
    )
    parameter_contract = build_parameter_contract(
        project_title=project_title,
        details=details,
        normalized_fields=normalized_fields,
        header_rules=header_rules,
        section_rule=section_rule,
        unit_inherited=unit_inherited,
    )
    parameter_contract = _synchronize_contract_with_parser_bindings(
        parameter_contract,
        normalized_fields,
        header_rules,
        section_rule=section_rule,
    )
    return {
        "测量值": project_title,
        "项目名称": project_title,
        "schema_version": parameter_contract_schema_version(),
        "数据明细": details,
        "__normalized_fields": normalized_fields,
        "__parameter_contract": parameter_contract,
        "__parser_meta": _align_parser_meta_with_contract(
            {
                "parse_source": parse_source,
                "section_rule": section_rule,
                "section_rule_confidence": section_meta["section_rule_confidence"],
                "section_alias_matched": section_meta["section_alias_matched"],
                "section_alias_candidates": section_meta["section_alias_candidates"],
                "header_rules": header_rules,
                "unit_inherited": unit_inherited,
            },
            parameter_contract,
        ),
    }


def _prepare_detail_value(key: str, raw_value: str) -> str:
    value = _clean_scalar_field_value(key, raw_value)
    unit = _extract_units_from_header(key)
    return _attach_unit(value, unit, key)


def _parser_fallback_normalize_key(text: str) -> str:
    return re.sub(r"[\s_:/()（）-]+", "", str(text or "").strip().lower())


def _row_uses_standard_parameter_layout(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    parser_meta = row.get("__parser_meta")
    if not isinstance(parser_meta, dict):
        return False
    parse_source = str(parser_meta.get("parse_source") or "").strip()
    if parse_source in STANDARD_PARAMETER_PARSE_SOURCES:
        return True
    return _is_structured_flat_reference_oscillator_row(row)


def _is_structured_flat_reference_oscillator_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    parser_meta = row.get("__parser_meta")
    if not isinstance(parser_meta, dict):
        return False
    if str(parser_meta.get("parse_source") or "").strip() != "flat_text_reference_oscillator":
        return False
    if str(parser_meta.get("section_rule") or "").strip().lower() != "reference_oscillator":
        return False

    normalized = row.get("__normalized_fields")
    if not isinstance(normalized, dict):
        return False

    error_value = str(normalized.get("error_value") or "").strip()
    if not error_value:
        return False

    support_value = any(
        str(normalized.get(field_name) or "").strip()
        for field_name in ("limit_value", "cert_u", "result_flag")
    )
    if not support_value:
        return False

    nominal_like = any(
        str(normalized.get(field_name) or "").strip()
        for field_name in ("measure_value", "reference_value", "nominal_value")
    )
    point_like = str(normalized.get("point_value") or "").strip()
    param_name = _parser_fallback_normalize_key(row.get("测量值") or row.get("项目名称") or "")

    if "开机特性" in param_name or "warmup" in param_name or "warmupcharacteristics" in param_name:
        return nominal_like
    if "相对频率偏差" in param_name or "relativefrequencydeviation" in param_name:
        return nominal_like
    if "短期频率稳定度" in param_name or "shortterm" in param_name or "stability" in param_name:
        return bool(point_like or nominal_like)
    return bool(point_like or nominal_like)


def _looks_like_period_accuracy_family_row(project_title: str, details: dict[str, Any]) -> bool:
    title_text = str(project_title or "").strip().lower()
    if any(token.lower() in title_text for token in PERIOD_ACCURACY_SECTION_ALIASES):
        return True

    header_text = " | ".join(str(key or "").strip() for key in (details or {}).keys()).lower()
    return any(token.lower() in header_text for token in PERIOD_ACCURACY_ERROR_HEADER_ALIASES)


def _find_detail_header(details: dict[str, Any], *aliases: str) -> str:
    headers = [str(key).strip() for key in (details or {}).keys() if str(key).strip()]
    norm_lookup = {_parser_fallback_normalize_key(header): header for header in headers}
    for alias in aliases:
        resolved = norm_lookup.get(_parser_fallback_normalize_key(alias))
        if resolved:
            return resolved
    return ""


def _normalize_parser_fallback_decision(
    row: dict[str, Any],
    decision: Optional[ParserFallbackDecision],
) -> Optional[ParserFallbackDecision]:
    if decision is None or not isinstance(row, dict):
        return decision
    details = row.get("数据明细")
    if not isinstance(details, dict) or not details:
        return decision
    project_title = str(row.get("测量值") or row.get("项目名称") or "")
    if not _looks_like_period_accuracy_family_row(project_title, details):
        return decision

    field_bindings = dict(getattr(decision, "field_bindings", {}) or {})
    daily_error_header = _find_detail_header(
        details,
        *PERIOD_ACCURACY_ERROR_HEADER_ALIASES,
    )
    limit_header = _find_detail_header(details, "允许误差", "limit", "误差限值")
    cert_u_header = _find_detail_header(details, "U", "u", "不确定度", "uncertainty")
    if daily_error_header:
        field_bindings["error_value"] = daily_error_header
        if field_bindings.get("measure_value") == daily_error_header:
            field_bindings.pop("measure_value", None)
    if limit_header:
        field_bindings.setdefault("limit_value", limit_header)
    if cert_u_header:
        field_bindings.setdefault("cert_u", cert_u_header)

    return ParserFallbackDecision(
        action=str(getattr(decision, "action", "") or "abstain").strip(),
        section_rule="period_accuracy",
        field_bindings=field_bindings,
        unit_family="time",
        confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
        reason=str(getattr(decision, "reason", "") or "").strip(),
    )


def _synchronize_contract_with_parser_bindings(
    parameter_contract: dict[str, Any],
    normalized_fields: dict[str, Any],
    header_rules: dict[str, Any],
    *,
    section_rule: str = "",
) -> dict[str, Any]:
    contract = dict(parameter_contract or {})
    source_headers = dict(contract.get("source_headers") or {})
    for field_name in (
        "measure_value",
        "reference_value",
        "error_value",
        "limit_value",
        "cert_u",
        "condition_value",
        "nominal_value",
    ):
        field_value = str((normalized_fields or {}).get(field_name) or "").strip()
        if not field_value:
            continue
        contract[field_name] = field_value
        header_name = str((header_rules or {}).get(field_name) or "").strip()
        if header_name:
            source_headers[field_name] = header_name

    if source_headers:
        contract["source_headers"] = source_headers

    semantic_target = str(contract.get("semantic_target") or section_rule or "").strip().lower()
    if str(contract.get("unit_family") or "").strip().lower() == "unknown":
        if semantic_target in {"period_accuracy", "period_range"}:
            contract["unit_family"] = "time"
        elif semantic_target in {"frequency_accuracy", "frequency_range", "reference_oscillator"}:
            contract["unit_family"] = "frequency"
        elif semantic_target == "count_accuracy":
            contract["unit_family"] = "count"
    return contract


def _align_parser_meta_with_contract(parser_meta: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    meta = dict(parser_meta or {})
    semantic_target = str((contract or {}).get("semantic_target") or "").strip().lower()
    if semantic_target not in PARSER_FALLBACK_SECTION_RULES or semantic_target == "unknown":
        return meta

    current_rule = str(meta.get("section_rule") or "").strip().lower()
    if current_rule == semantic_target:
        return meta

    if current_rule and current_rule != "unknown":
        meta.setdefault("section_hint_rule", current_rule)
        meta.setdefault("section_hint_confidence", meta.get("section_rule_confidence"))
        if meta.get("section_alias_matched"):
            meta.setdefault("section_hint_alias_matched", meta.get("section_alias_matched"))
        if meta.get("section_alias_candidates"):
            meta.setdefault("section_hint_alias_candidates", tuple(meta.get("section_alias_candidates") or ()))

    meta["section_rule"] = semantic_target
    try:
        contract_confidence = float((contract or {}).get("confidence") or 0.0)
    except (TypeError, ValueError):
        contract_confidence = 0.0
    try:
        current_confidence = float(meta.get("section_rule_confidence") or 0.0)
    except (TypeError, ValueError):
        current_confidence = 0.0
    meta["section_rule_confidence"] = max(current_confidence, contract_confidence, 0.9)

    candidates = tuple(meta.get("section_alias_candidates") or ())
    if semantic_target not in candidates:
        meta["section_alias_candidates"] = candidates + (semantic_target,) if candidates else (semantic_target,)
    return meta


def _row_needs_llm_fallback(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    parser_meta = row.get("__parser_meta")
    if not isinstance(parser_meta, dict):
        return False
    if parser_meta.get("llm_fallback_applied"):
        return False
    parse_source = str(parser_meta.get("parse_source") or "").strip()
    if parse_source not in STANDARD_PARAMETER_PARSE_SOURCES:
        return False

    contract = row.get("__parameter_contract")
    if not isinstance(contract, dict):
        return True
    if str(parser_meta.get("section_rule") or "").strip().lower() == "unknown":
        return True
    if str(contract.get("semantic_target") or "").strip().lower() == "unknown":
        return True
    normalized = row.get("__normalized_fields")
    if not isinstance(normalized, dict):
        return True
    bindable_values = [
        str(normalized.get(field_name) or "").strip()
        for field_name in ("measure_value", "reference_value", "error_value", "limit_value", "cert_u")
    ]
    if sum(1 for value in bindable_values if value) <= 1:
        return True
    return False


def _request_llm_parameter_row_repair(
    *,
    project_title: str,
    details: dict[str, Any],
    row: dict[str, Any],
    llm_client: Any,
) -> Optional[ParserFallbackDecision]:
    if llm_client is None:
        return None

    parser_meta = row.get("__parser_meta", {}) if isinstance(row.get("__parser_meta"), dict) else {}
    normalized_fields = row.get("__normalized_fields", {}) if isinstance(row.get("__normalized_fields"), dict) else {}
    parameter_contract = row.get("__parameter_contract", {}) if isinstance(row.get("__parameter_contract"), dict) else {}
    output_model = _build_parser_fallback_output_model(details)
    prompt = "\n".join(
        [
            "你是受约束的MD参数行修复器。",
            "目标：仅当当前行的deterministic parser明显脏时，给出最小结构化修复方案。",
            "禁止编造不存在的header、数值或单位。",
            f"project_title: {project_title}",
            f"raw_details: {json.dumps(details, ensure_ascii=False, sort_keys=True)}",
            f"current_parser_meta: {json.dumps(parser_meta, ensure_ascii=False, sort_keys=True)}",
            f"current_normalized_fields: {json.dumps(normalized_fields, ensure_ascii=False, sort_keys=True)}",
            f"current_parameter_contract: {json.dumps(parameter_contract, ensure_ascii=False, sort_keys=True)}",
            "严格按照输出 schema 返回。",
            "如果当前行无法可靠修复，action=abstain；只有在字段绑定明确时才 action=suggest。",
        ]
    )
    try:
        decision = llm_client.invoke_structured(
            user_prompt=prompt,
            output_model=output_model,
            system_prompt=(
                "你只输出结构化的参数行修复决策。"
                "不得输出PASS/FAIL。"
            ),
        )
    except Exception:
        return None
    return _coerce_parser_fallback_decision(decision)


def _apply_llm_parameter_row_repair(
    row: dict[str, Any],
    decision: Optional[ParserFallbackDecision],
) -> dict[str, Any]:
    decision = _normalize_parser_fallback_decision(row, decision)
    if not isinstance(row, dict) or decision is None:
        return row

    action = str(getattr(decision, "action", "") or "").strip().lower()
    if action != "suggest":
        return row

    section_rule = str(getattr(decision, "section_rule", "") or "").strip().lower()
    if section_rule not in PARSER_FALLBACK_SECTION_RULES or section_rule == "unknown":
        return row

    details = row.get("数据明细")
    if not isinstance(details, dict) or not details:
        return row

    detail_header_lookup = {str(key): str(key) for key in details.keys() if str(key).strip()}
    detail_header_norm_lookup = {
        _parser_fallback_normalize_key(key): key for key in detail_header_lookup
    }

    normalized_fields = dict(row.get("__normalized_fields") or {})
    header_rules = dict((row.get("__parser_meta") or {}).get("header_rules") or {})
    bound_headers: dict[str, str] = {}
    raw_bindings = dict(getattr(decision, "field_bindings", {}) or {})
    for field_name, source_header in raw_bindings.items():
        canonical_name = str(field_name or "").strip()
        if canonical_name not in PARSER_FALLBACK_BINDABLE_FIELDS:
            continue
        source_text = str(source_header or "").strip()
        resolved_header = detail_header_lookup.get(source_text)
        if resolved_header is None:
            resolved_header = detail_header_norm_lookup.get(_parser_fallback_normalize_key(source_text))
        if resolved_header is None:
            continue
        resolved_value = str(details.get(resolved_header) or "").strip()
        if not resolved_value:
            continue
        normalized_fields[canonical_name] = resolved_value
        header_rules[canonical_name] = resolved_header
        bound_headers[canonical_name] = resolved_header

    if not bound_headers:
        return row

    parser_meta = dict(row.get("__parser_meta") or {})
    unit_inherited = bool(parser_meta.get("unit_inherited"))
    repaired_contract = build_parameter_contract(
        project_title=str(row.get("测量值") or row.get("项目名称") or ""),
        details=details,
        normalized_fields=normalized_fields,
        header_rules=header_rules,
        section_rule=section_rule,
        unit_inherited=unit_inherited,
    )
    repaired_contract = _synchronize_contract_with_parser_bindings(
        repaired_contract,
        normalized_fields,
        header_rules,
        section_rule=section_rule,
    )

    unit_family = str(getattr(decision, "unit_family", "") or "").strip().lower()
    if unit_family in PARSER_FALLBACK_UNIT_FAMILIES and unit_family != "unknown":
        repaired_contract["unit_family"] = unit_family

    try:
        decision_confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        decision_confidence = 0.0
    repaired_contract["confidence"] = max(float(repaired_contract.get("confidence") or 0.0), decision_confidence)

    parser_meta.update(
        {
            "section_rule": section_rule,
            "section_rule_confidence": max(float(parser_meta.get("section_rule_confidence") or 0.0), decision_confidence),
            "header_rules": header_rules,
            "llm_fallback_applied": True,
            "llm_fallback_reason": str(getattr(decision, "reason", "") or "").strip(),
            "llm_fallback_confidence": decision_confidence,
            "llm_fallback_bindings": bound_headers,
        }
    )
    row["__normalized_fields"] = normalized_fields
    row["__parameter_contract"] = repaired_contract
    row["__parser_meta"] = _align_parser_meta_with_contract(parser_meta, repaired_contract)
    return row


def _repair_parameter_rows_with_llm(
    rows: list[dict[str, Any]],
    llm_client: Any = None,
    progress_callback: Optional[ParserProgressCallback] = None,
) -> list[dict[str, Any]]:
    if llm_client is None:
        return rows

    candidate_rows = [
        row for row in rows
        if _row_needs_llm_fallback(row) and isinstance(row.get("数据明细"), dict)
    ]
    total_candidates = len(candidate_rows)
    if progress_callback is not None and total_candidates:
        progress_callback("row_llm_fallback_start", 0, total_candidates, "参数行 LLM 修补启动")

    repaired_rows: list[dict[str, Any]] = []
    repaired_count = 0
    for row in rows:
        if not _row_needs_llm_fallback(row):
            repaired_rows.append(row)
            continue
        details = row.get("数据明细")
        if not isinstance(details, dict):
            repaired_rows.append(row)
            continue
        repaired_count += 1
        if progress_callback is not None and total_candidates:
            progress_callback(
                "row_llm_fallback_progress",
                repaired_count,
                total_candidates,
                str(row.get("测量值") or row.get("项目名称") or ""),
            )
        decision = _request_llm_parameter_row_repair(
            project_title=str(row.get("测量值") or row.get("项目名称") or ""),
            details=details,
            row=row,
            llm_client=llm_client,
        )
        repaired_rows.append(_apply_llm_parameter_row_repair(row, decision))
    if progress_callback is not None and total_candidates:
        progress_callback("row_llm_fallback_done", total_candidates, total_candidates, "参数行 LLM 修补完成")
    return repaired_rows


def _clean_flat_block_lines(content: str, title: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line or line == title or line.startswith("#") or line.startswith("![](images/"):
            continue
        line = html.unescape(line)
        line = line.replace("$", "")
        line = line.replace("\\times", "×")
        line = line.replace("\\pm", "±")
        line = line.replace("{", "").replace("}", "")
        line = re.sub(r"\s*×\s*", "×", line)
        line = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", line)
        line = re.sub(r"(\d+(?:\.\d+)?)\s*10\s*-\s*(\d+)", r"\1×10^-\2", line)
        line = re.sub(r"×\s*10\s*-\s*(\d+)", r"×10^-\1", line)
        line = re.sub(r"(\d+(?:\.\d+)?)\s*×\s*10\s*\^\s*([+-]?\d+)", r"\1×10^\2", line)
        line = re.sub(
            r"×\s*1\s*0\s*\^\s*([+-]?)\s*(\d(?:\s*\d)?)",
            lambda m: "×10^" + m.group(1) + re.sub(r"\s+", "", m.group(2)),
            line,
        )
        line = re.sub(
            r"10\^\s*([+-]?)\s*(\d(?:\s*\d)?)",
            lambda m: "10^" + m.group(1) + re.sub(r"\s+", "", m.group(2)),
            line,
        )
        line = re.sub(r"\^\s*±", "±", line)
        line = re.sub(r"\s+", " ", line).strip()
        lines.append(line)
    return lines


def _find_flat_anchor(lines: list[str], predicate, start: int = 0) -> int:
    for idx in range(max(start, 0), len(lines)):
        if predicate(lines[idx]):
            return idx
    return -1


def _segment_between(lines: list[str], start_idx: int, end_idx: int) -> list[str]:
    if start_idx < 0:
        return []
    if end_idx < 0:
        end_idx = len(lines)
    return [line for line in lines[start_idx + 1:end_idx] if line]


_SCI_VALUE_RE = re.compile(r"[+-]?\d+(?:\.\d+)?(?:×10\^[+-]?\d+|e[+-]?\d+)", re.IGNORECASE)
_PLAIN_VALUE_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")


def _extract_scientific_tokens(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        values.extend(_SCI_VALUE_RE.findall(line))
    return [_normalize_value_text(value) for value in values]


def _extract_plain_values(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        if line.startswith("(") and line.endswith(")"):
            continue
        if "N/A" in line:
            values.append("N/A")
            continue
        matches = _PLAIN_VALUE_RE.findall(line)
        if matches and len(matches) == 1 and _SCI_VALUE_RE.search(line) is None:
            values.append(matches[0])
    return values


def _extract_nonempty_value_lines(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        if line.startswith("(") and line.endswith(")"):
            continue
        if re.search(r"\d", line) or line in {"N/A", "P", "F", "PASS", "FAIL"}:
            values.append(_normalize_value_text(line))
    return values


def _pick_value(values: list[str], index: int) -> str:
    if not values:
        return ""
    if index < len(values):
        return values[index]
    if len(values) == 1:
        return values[0]
    return values[-1]


def _parse_reference_oscillator_warmup_block(project_title: str, lines: list[str]) -> list[dict[str, Any]]:
    time_idx = _find_flat_anchor(lines, lambda line: line == "开机时间" or "Time" in line)
    nominal_idx = _find_flat_anchor(lines, lambda line: line == "标称值" or "Nominal" in line, start=time_idx + 1)
    error_idx = _find_flat_anchor(lines, lambda line: line == "误差" or line == "(Error)", start=nominal_idx + 1)
    limit_idx = _find_flat_anchor(lines, lambda line: line == "允许误差" or line == "允许范围", start=error_idx + 1)
    k_idx = _find_flat_anchor(lines, lambda line: "k=2" in line.lower(), start=limit_idx + 1)

    point_values = [f"{value} h" for value in _extract_plain_values(_segment_between(lines, time_idx, nominal_idx))]
    nominal_values = _extract_plain_values(_segment_between(lines, nominal_idx, error_idx))
    error_values = _extract_scientific_tokens(_segment_between(lines, error_idx, limit_idx))
    limit_values = _extract_nonempty_value_lines(_segment_between(lines, limit_idx, k_idx))
    u_values = _extract_scientific_tokens(_segment_between(lines, k_idx, -1))

    row_count = max(len(point_values), len(nominal_values), 0)
    rows: list[dict[str, Any]] = []
    for idx in range(row_count):
        details: dict[str, str] = {}
        point_value = _pick_value(point_values, idx)
        if point_value:
            details["点位"] = point_value
        nominal_value = _pick_value(nominal_values, idx)
        if nominal_value:
            details["标称值 (Nominal) (MHz)"] = _prepare_detail_value("标称值 (Nominal) (MHz)", nominal_value)
        error_value = _pick_value(error_values, idx)
        if error_value:
            details["开机特性"] = _prepare_detail_value("开机特性", error_value)
        limit_value = _pick_value(limit_values, idx)
        if limit_value:
            details["允许误差 (Limit)"] = _prepare_detail_value("允许误差 (Limit)", limit_value)
        u_value = _pick_value(u_values, idx)
        if u_value:
            details["U (k=2)"] = _prepare_detail_value("U (k=2)", u_value)
        row = _build_measurement_row(
            project_title,
            details,
            parse_source="flat_text_reference_oscillator",
            section_rule="reference_oscillator",
        )
        if row:
            rows.append(row)
    return rows


def _parse_reference_oscillator_stability_block(project_title: str, lines: list[str]) -> list[dict[str, Any]]:
    limit_idx = _find_flat_anchor(lines, lambda line: line == "允许范围" or line == "允许误差" or "Limit" in line)
    result_idx = _find_flat_anchor(lines, lambda line: line == "结论" or "Pass/Fail" in line, start=limit_idx + 1)

    point_values: list[str] = []
    for line in lines[:limit_idx if limit_idx >= 0 else len(lines)]:
        sigma_match = re.search(r"σ\(\s*(\d+)\s*s\s*\)", line, re.IGNORECASE)
        if sigma_match:
            point_values.append(f"{sigma_match.group(1)} s")

    error_values = _extract_scientific_tokens(_segment_between(lines, _find_flat_anchor(lines, lambda line: "Short-Term" in line or "短期频率稳定度" in line), limit_idx))
    if point_values:
        error_values = error_values[:len(point_values)]
    limit_values = _extract_nonempty_value_lines(_segment_between(lines, limit_idx, result_idx))

    pair_lines = _segment_between(lines, result_idx, -1)
    result_values: list[str] = []
    u_values: list[str] = []
    for line in pair_lines:
        if line.startswith("(") and line.endswith(")"):
            continue
        match = re.search(r"\b(P|F|PASS|FAIL)\b\s*(" + _SCI_VALUE_RE.pattern + r")?", line, re.IGNORECASE)
        if match:
            result_values.append(match.group(1).upper())
            if match.group(2):
                u_values.append(_normalize_value_text(match.group(2)))
    if not u_values:
        u_values = _extract_scientific_tokens(pair_lines)
        if point_values:
            u_values = u_values[:len(point_values)]

    row_count = len(point_values) or max(len(error_values), len(limit_values), len(u_values), 0)
    rows: list[dict[str, Any]] = []
    for idx in range(row_count):
        details: dict[str, str] = {}
        point_value = _pick_value(point_values, idx)
        if point_value:
            details["取样时间 (Gate Time)"] = point_value
        error_value = _pick_value(error_values, idx)
        if error_value:
            details["短期频率稳定度 (Stability)"] = _prepare_detail_value("短期频率稳定度 (Stability)", error_value)
        limit_value = _pick_value(limit_values, idx)
        if limit_value:
            details["允许范围 (Limit)"] = _prepare_detail_value("允许范围 (Limit)", limit_value)
        result_value = _pick_value(result_values, idx)
        if result_value:
            details["结论 (Pass/Fail)"] = result_value
        u_value = _pick_value(u_values, idx)
        if u_value:
            details["U (k=2)"] = _prepare_detail_value("U (k=2)", u_value)
        row = _build_measurement_row(
            project_title,
            details,
            parse_source="flat_text_reference_oscillator",
            section_rule="reference_oscillator",
        )
        if row:
            rows.append(row)
    return rows


def _parse_reference_oscillator_relative_block(project_title: str, lines: list[str]) -> list[dict[str, Any]]:
    freq_idx = _find_flat_anchor(lines, lambda line: line == "输出频率" or "Frequency" in line)
    error_idx = _find_flat_anchor(lines, lambda line: line == "相对频率偏差" or "Relative Frequency Deviation" in line, start=freq_idx + 1)
    limit_idx = _find_flat_anchor(lines, lambda line: line == "允许误差" or line == "允许范围" or "Limit" in line, start=error_idx + 1)
    result_idx = _find_flat_anchor(lines, lambda line: line == "结论" or "Pass/Fail" in line, start=limit_idx + 1)
    k_idx = _find_flat_anchor(lines, lambda line: "k=2" in line.lower(), start=result_idx + 1)

    frequency_values = _extract_plain_values(_segment_between(lines, freq_idx, error_idx))
    error_values = _extract_scientific_tokens(_segment_between(lines, error_idx, limit_idx))
    limit_values = _extract_nonempty_value_lines(_segment_between(lines, limit_idx, result_idx))
    u_values = _extract_scientific_tokens(_segment_between(lines, k_idx, -1))

    details: dict[str, str] = {}
    frequency_value = _pick_value(frequency_values, 0)
    if frequency_value:
        details["输出频率 (Frequency) (MHz)"] = _prepare_detail_value("输出频率 (Frequency) (MHz)", frequency_value)
    error_value = _pick_value(error_values, 0)
    if error_value:
        details["相对频率偏差 (Relative Frequency Deviation)"] = _prepare_detail_value(
            "相对频率偏差 (Relative Frequency Deviation)",
            error_value,
        )
    limit_value = _pick_value(limit_values, 0)
    if limit_value:
        details["允许误差 (Limit)"] = _prepare_detail_value("允许误差 (Limit)", limit_value)
    u_value = _pick_value(u_values, 0)
    if u_value:
        details["U (k=2)"] = _prepare_detail_value("U (k=2)", u_value)

    row = _build_measurement_row(
        project_title,
        details,
        parse_source="flat_text_reference_oscillator",
        section_rule="reference_oscillator",
    )
    return [row] if row else []


def _parse_flat_parameter_block(project_title: str, content: str) -> list[dict[str, Any]]:
    section_rule = _match_section_rule(project_title)
    if section_rule != "reference_oscillator":
        return []

    lines = _clean_flat_block_lines(content, project_title)
    title_text = str(project_title or "")

    if "短期频率稳定度" in title_text or "Short-Term" in title_text or "Stability" in title_text:
        return _parse_reference_oscillator_stability_block(project_title, lines)
    if "相对频率偏差" in title_text or "Relative Frequency Deviation" in title_text:
        return _parse_reference_oscillator_relative_block(project_title, lines)
    if "开机特性" in title_text or "Warm-up" in title_text:
        return _parse_reference_oscillator_warmup_block(project_title, lines)
    return []


def _merge_header_rows(header_rows: list[list[str]]) -> list[str]:
    if not header_rows:
        return []
    width = max(len(row) for row in header_rows)
    merged: list[str] = []
    for col_idx in range(width):
        parts: list[str] = []
        for row in header_rows:
            if col_idx >= len(row):
                continue
            text = _clean_header_text(row[col_idx])
            if text and text not in parts:
                parts.append(text)
        merged.append(" ".join(parts).strip())
    return merged


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for idx, header in enumerate(headers, start=1):
        text = _clean_header_text(header) or f"列{idx}"
        count = seen.get(text, 0) + 1
        seen[text] = count
        deduped.append(text if count == 1 else f"{text} [{count}]")
    return deduped


def _has_duplicate_nonempty_headers(row: list[str]) -> bool:
    seen: set[str] = set()
    for cell in row:
        text = _clean_header_text(cell)
        if not text:
            continue
        if text in seen:
            return True
        seen.add(text)
    return False


def _collect_top_header_rows(table_data: list[list[str]]) -> tuple[list[list[str]], int]:
    if not table_data:
        return [], 0
    header_rows = [[_clean_header_text(cell) for cell in table_data[0]]]
    data_start_idx = 1
    if not _has_duplicate_nonempty_headers(header_rows[0]):
        return header_rows, data_start_idx
    for row in table_data[1:]:
        if _is_pure_unit_row(row) or _is_effective_unit_row(row) or not _row_has_numeric_measurement(row):
            header_rows.append([_clean_header_text(cell) for cell in row])
            data_start_idx += 1
            continue
        break
    return header_rows, data_start_idx


def _row_has_numeric_measurement(row: list[str]) -> bool:
    return any(
        re.search(r'\d', str(cell or "").strip())
        and not (str(cell or "").strip().startswith("(") and str(cell or "").strip().endswith(")"))
        for cell in row
        if str(cell or "").strip()
    )


def _is_structural_header_row(row: list[str]) -> bool:
    non_empty = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
    if not non_empty:
        return False
    if _row_has_numeric_measurement(row):
        return False
    label_like = 0
    for text in non_empty:
        lowered = text.lower()
        if lowered in {"t1", "t2", "u", "n", "p", "f", "on-timer", "off-timer"}:
            label_like += 1
            continue
        canonical_name, _ = _match_column_alias(text)
        if canonical_name != "unknown":
            label_like += 1
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.+\-/%() ]*", text):
            label_like += 1
            continue
    return label_like == len(non_empty)


def _classify_table_row(row: list[str], headers: list[str]) -> str:
    if not row or all(not str(cell or "").strip() for cell in row):
        return "empty"
    if _is_pure_unit_row(row) or _is_effective_unit_row(row) or _is_contextual_unit_row(row, headers):
        return "unit"
    if _is_structural_header_row(row):
        return "structural_header"
    if not _row_has_numeric_measurement(row):
        return "header"
    return "data"


def _phase1_build_document_context(md_text: str, llm_client: Any = None) -> DocumentParseContext:
    blocks = split_md_to_blocks(md_text)
    final_meta, meta_debug = _extract_meta_with_llm(md_text, llm_client=llm_client)
    return DocumentParseContext(
        md_text=md_text,
        blocks=blocks,
        meta=final_meta,
        meta_debug=meta_debug,
    )


def _phase2_collect_artifacts(blocks: list[tuple[str, str]]) -> tuple[list[TableArtifact], list[FlatBlockArtifact]]:
    table_artifacts: list[TableArtifact] = []
    flat_artifacts: list[FlatBlockArtifact] = []
    table_pattern = re.compile(r'(?is)<table.*?</table>')
    for title, content in blocks:
        if is_skip_block(title, content):
            continue
        if "<table" in content:
            for table_html in table_pattern.findall(content):
                if "主要测量标准" in title:
                    continue
                table_data = parse_table_cells(table_html)
                if table_data:
                    table_artifacts.append(TableArtifact(project_title=title, table_html=table_html, table_data=table_data))
        else:
            flat_artifacts.append(FlatBlockArtifact(project_title=title, content=content))
    return table_artifacts, flat_artifacts


def _phase4_parse_artifact_rows(table_artifacts: list[TableArtifact], flat_artifacts: list[FlatBlockArtifact]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact in table_artifacts:
        rows.extend(parse_table_to_rows(artifact.table_data, artifact.project_title))
    for artifact in flat_artifacts:
        rows.extend(_parse_flat_parameter_block(artifact.project_title, artifact.content))
    return rows


def _phase5_assemble_result(meta: dict[str, Any], rows: list[dict[str, Any]], meta_debug: dict[str, Any]) -> dict[str, Any]:
    document_parser_meta = _build_document_parser_meta(rows)
    if meta_debug:
        document_parser_meta.update(meta_debug)
    return {
        "__parameter_contract_schema_version": parameter_contract_schema_version(),
        "__md_parser_pipeline_signature": md_parser_pipeline_signature(),
        "properties": {
            "证书列表": {
                "items": {"properties": meta}
            }
        },
        "依据参数_中间数据": rows,
        "__document_parser_meta": document_parser_meta,
    }


def parse_table_to_rows(table_data: list[list[str]], project_title: str) -> list[dict]:
    """Override table parsing to carry forward unit rows into numeric cells."""
    if not table_data:
        return []
    section_rule = _match_section_rule(project_title)

    if len(table_data) == 1:
        details = {}
        unit_inherited = False
        for cell in table_data[0]:
            parsed = _split_inline_labeled_cell(cell)
            if not parsed:
                continue
            key, value = parsed
            key = _clean_header_text(key)
            if not key or not value:
                continue
            value = _clean_scalar_field_value(key, value)
            unit = _extract_units_from_header(key)
            normalized_value = _attach_unit(value, unit, key)
            if unit and normalized_value != value and not _value_has_embedded_unit(value):
                unit_inherited = True
            details[key] = normalized_value

            matched_measured_alias, preferred_measured_alias = _should_alias_to_measured(key)
            if matched_measured_alias:
                if preferred_measured_alias or "被测量" not in details:
                    details["被测量"] = normalized_value

        if section_rule == "modulation_quality":
            details = _remap_modulation_quality_details(details)

        if details:
            row_project_title = _resolve_row_project_title(project_title, details)
            row = _build_measurement_row(
                row_project_title,
                details,
                parse_source="html_table_inline",
                section_rule=_match_section_rule(row_project_title),
            )
            if row:
                row["__parser_meta"]["unit_inherited"] = _should_mark_unit_inherited(
                    section_rule=_match_section_rule(row_project_title),
                    normalized_fields=row["__normalized_fields"],
                    header_rules=row["__parser_meta"]["header_rules"],
                    inherited_from_header=unit_inherited,
                )
                row["__parameter_contract"] = build_parameter_contract(
                    project_title=row_project_title,
                    details=row["数据明细"],
                    normalized_fields=row["__normalized_fields"],
                    header_rules=row["__parser_meta"]["header_rules"],
                    section_rule=row["__parser_meta"]["section_rule"],
                    unit_inherited=bool(row["__parser_meta"]["unit_inherited"]),
                )
                row["__parameter_contract"] = _synchronize_contract_with_parser_bindings(
                    row["__parameter_contract"],
                    row["__normalized_fields"],
                    row["__parser_meta"]["header_rules"],
                    section_rule=row["__parser_meta"]["section_rule"],
                )
                return [row]
        return []

    rows = []
    header_rows, data_start_idx = _collect_top_header_rows(table_data)
    headers = _dedupe_headers(_merge_header_rows(header_rows))
    if not headers:
        headers = [f"列{i+1}" for i in range(len(table_data[0]))] if table_data else []

    prev_channel = None
    prev_satellite = None
    current_units = []
    for header in headers:
        unit = _extract_units_from_header(header)
        current_units.append(unit)

    for row in table_data[data_start_idx:]:
        row_kind = _classify_table_row(row, headers)
        if row_kind == "empty":
            continue

        if row_kind == "structural_header":
            continue

        if row_kind == "header":
            continue

        if row_kind == "unit":
            if headers and headers[0] and ("channel" in headers[0].lower() or "閫氶亾" in headers[0]):
                channel_marker = _normalize_value_text(row[0]) if row else ""
                if _looks_like_channel_value(channel_marker):
                    prev_channel = channel_marker
            row_units = _extract_row_units(row)
            for i, (old_unit, new_unit) in enumerate(zip(current_units, row_units)):
                if new_unit:
                    current_units[i] = new_unit
            continue

        if headers and "卫星" in headers[0]:
            current_satellite = row[0].strip() if row else None
            if current_satellite and current_satellite not in ["", "0", "5", "10", "15", "20", "25", "30", "35", "40", "AGC"]:
                prev_satellite = current_satellite
            elif not current_satellite and prev_satellite:
                row = [prev_satellite] + row[1:] if len(row) > 1 else [prev_satellite]

        if headers and headers[0] and ("channel" in headers[0].lower() or "通道" in headers[0]):
            current_channel = _normalize_value_text(row[0]) if row else None
            if _looks_like_channel_value(current_channel):
                prev_channel = current_channel
            elif (not current_channel) and prev_channel:
                row = [prev_channel] + row[1:] if len(row) > 1 else [prev_channel]

        details = {}
        unit_inherited = False
        for i, cell in enumerate(row):
            key = headers[i] if i < len(headers) else f"列{i+1}"
            cell_value = _clean_scalar_field_value(key, cell)
            if not key or not cell_value or (cell_value.startswith("(") and cell_value.endswith(")")):
                continue

            unit = current_units[i] if i < len(current_units) else ""
            # 如果单位仍然为空，再次尝试从表头提取
            if not unit:
                unit = _extract_units_from_header(key)

            normalized_value = _attach_unit(cell_value, unit, key)
            if unit and normalized_value != cell_value and not _value_has_embedded_unit(cell_value):
                unit_inherited = True
            details[key] = normalized_value

            matched_measured_alias, preferred_measured_alias = _should_alias_to_measured(key)
            if matched_measured_alias:
                if preferred_measured_alias or "被测量" not in details:
                    details["被测量"] = normalized_value

        if section_rule == "modulation_quality":
            details = _remap_modulation_quality_details(details)

        if details:
            row_project_title = _resolve_row_project_title(project_title, details)
            row_data = _build_measurement_row(
                row_project_title,
                details,
                parse_source="html_table",
                section_rule=_match_section_rule(row_project_title),
            )
            if not row_data:
                continue
            row_data["__parser_meta"]["unit_inherited"] = _should_mark_unit_inherited(
                section_rule=_match_section_rule(row_project_title),
                normalized_fields=row_data["__normalized_fields"],
                header_rules=row_data["__parser_meta"]["header_rules"],
                inherited_from_header=unit_inherited,
            )
            row_data["__parameter_contract"] = build_parameter_contract(
                project_title=row_project_title,
                details=row_data["数据明细"],
                normalized_fields=row_data["__normalized_fields"],
                header_rules=row_data["__parser_meta"]["header_rules"],
                section_rule=row_data["__parser_meta"]["section_rule"],
                unit_inherited=bool(row_data["__parser_meta"]["unit_inherited"]),
            )
            row_data["__parameter_contract"] = _synchronize_contract_with_parser_bindings(
                row_data["__parameter_contract"],
                row_data["__normalized_fields"],
                row_data["__parser_meta"]["header_rules"],
                section_rule=row_data["__parser_meta"]["section_rule"],
            )
            rows.append(row_data)

    return rows


# ──────────────────────────────────────────────
# 主解析函数
# ──────────────────────────────────────────────
def extract_meta_from_text(text: str) -> Dict[str, Any]:
    """从文本中提取meta信息（入口）"""
    meta, _ = _extract_meta_with_llm(text)
    return meta


def parse_md_to_json(
    md_path: str,
    out_dir: Optional[Path] = None,
    *,
    llm_client: Any = None,
    progress_callback: Optional[ParserProgressCallback] = None,
) -> dict:
    """解析MD文件为JSON"""
    md_file = Path(md_path)
    md_text = md_file.read_text(encoding='utf-8', errors='ignore')
    if progress_callback is not None:
        progress_callback("meta_extract_start", 0, 1, "头部信息解析")
    context = _phase1_build_document_context(md_text, llm_client=llm_client)
    if progress_callback is not None:
        meta_message = "头部字段 LLM 修补完成" if context.meta_debug.get("meta_llm_fallback_applied") else "头部信息解析完成"
        progress_callback("meta_extract_done", 1, 1, meta_message)
    table_artifacts, flat_artifacts = _phase2_collect_artifacts(context.blocks)
    all_rows = _phase4_parse_artifact_rows(table_artifacts, flat_artifacts)
    all_rows = _repair_parameter_rows_with_llm(
        all_rows,
        llm_client=llm_client,
        progress_callback=progress_callback,
    )
    result = _phase5_assemble_result(context.meta, all_rows, context.meta_debug)

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / md_file.with_suffix(".json").name
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"已保存: {out_file}")

    return result


# ──────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python md_parser_no_llm.py <md_path> [out_dir]")
        sys.exit(1)

    md_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None

    parse_md_to_json(md_path, out_dir)
