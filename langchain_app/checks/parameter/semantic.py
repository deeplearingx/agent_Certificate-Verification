#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数语义分析模块 - 负责参数语义识别和校准依据匹配

从 param_check.py 和 core/semantic_basis_selector.py 迁移
"""

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple, Protocol

from .parser_core import parse_range_limit, parse_value_with_unit
from .parser_domain import _parse_frequency_range, _parse_frequency_to_hz
from .contracts import infer_contract_unit_family, infer_semantic_subtype, normalize_parameter_contract
from .rules import (
    AMBIGUOUS_CRYSTAL_FREQUENCY_MEASURED_ALIASES,
    FALLBACK_SCORE_RULES,
    FREQUENCY_ACCURACY_CONTEXT_TOKENS,
    FREQUENCY_UNIT_PATTERN,
    KB_MEASURED_RULES,
    LENGTH_UNIT_PATTERN,
    MOTION_UNIT_PATTERN,
    PARAMETER_NAME_RULES,
    PLACEHOLDER_INSTRUMENT_NAMES,
    REFERENCE_OSCILLATOR_METRIC_TOKENS,
    REFERENCE_OSCILLATOR_OBJECT_TOKENS,
    SEMANTIC_RULE_REGISTRY,
    STRUCTURED_PREFILTER_TARGETS,
    TIME_UNIT_PATTERN,
    VOLT_POWER_UNIT_PATTERN,
)
@dataclass(frozen=True)
class ParamSemantic:
    task_intent: str
    primary_quantity: str
    unit_family: str
    condition_axis: Optional[str]
    uncertainty_kind: str
    semantic_target: str = ""
    semantic_subtype: str = ""
    contract_confidence: float = 0.0
    needs_disambiguation: bool = False
    features: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KbCapability:
    measured: str
    capability_target: str
    primary_quantity: str
    result_quantity: str
    condition_axis: Optional[str]
    uncertainty_kind: str
    semantic_subtype: str = ""
    unit_family: str = "unknown"
    contract_confidence: float = 0.0
    source: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionAudit:
    task_goal: str
    primary_quantity: str
    unit_family: str
    condition_axis: Optional[str]
    uncertainty_kind: str
    prefiltered_candidates: List[str]
    selected_measured: List[str]
    rejected_measured: List[str]
    rationale: str
    semantic_target: str = ""
    semantic_subtype: str = ""
    selected_candidate_id: Optional[str] = None
    used_fallback_candidate_target: bool = False
    selected_target_relation: str = ""
    ranked_candidates: List[str] = field(default_factory=list)
    candidate_reasons: Dict[str, str] = field(default_factory=dict)
    basis_candidates: List[str] = field(default_factory=list)
    planner_trace_id: Optional[str] = None
    planner_summary: Dict[str, Any] = field(default_factory=dict)
    semantic_auditor_trace_id: Optional[str] = None
    semantic_auditor_summary: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionResult:
    selected: List[KbCapability]
    audit: SelectionAudit
    selected_candidate_id: Optional[str] = None
    used_fallback_candidate_target: bool = False
    selected_target_relation: str = ""
    selected_candidate: Optional[Any] = None
    basis_candidates: List[Any] = field(default_factory=list)
    filtered_candidates: List[Any] = field(default_factory=list)
    ranked_candidates: List[Any] = field(default_factory=list)
    cert_point: Optional[Any] = None
    param_semantic: Optional[ParamSemantic] = None


class SemanticDecider(Protocol):
    def decide(self, param: ParamSemantic, candidates: List[KbCapability]) -> Dict[str, Any]:
        ...


FREQ_UNITS = re.compile(FREQUENCY_UNIT_PATTERN, re.IGNORECASE)
# 支持英文 u 和 Unicode 微符号 μ/µ，两者在证书和 KB 里都常见
TIME_UNITS = re.compile(TIME_UNIT_PATTERN, re.IGNORECASE)
VOLT_POWER_UNITS = re.compile(VOLT_POWER_UNIT_PATTERN, re.IGNORECASE)
MOTION_UNITS = re.compile(MOTION_UNIT_PATTERN, re.IGNORECASE)
LENGTH_UNITS = re.compile(LENGTH_UNIT_PATTERN, re.IGNORECASE)
_REFERENCE_OSCILLATOR_FIXED_POINTS_HZ = (1e6, 2e6, 5e6, 10e6)


def _contains_any(text: str, tokens: List[str]) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in tokens)


def _extract_frequency_point_hz(text: str) -> Optional[float]:
    raw = _structured_text(text)
    if not raw:
        return None
    match = re.search(r"[-+]?\d*\.?\d+\s*(?:THz|GHz|MHz|kHz|Hz)\b", raw, flags=re.IGNORECASE)
    if not match:
        return None
    return _parse_frequency_to_hz(match.group(0))


def _is_reference_oscillator_fixed_point(text: str) -> bool:
    value_hz = _extract_frequency_point_hz(text)
    if value_hz is None:
        return False
    for fixed_point in _REFERENCE_OSCILLATOR_FIXED_POINTS_HZ:
        tol = max(abs(fixed_point) * 1e-12, 1e-6)
        if abs(value_hz - fixed_point) <= tol:
            return True
    return False


def _looks_like_relative_frequency_accuracy_context(
    *,
    param_name: str,
    point_text: str,
    cert_u: str,
    structured_fields: Optional[Dict[str, Any]] = None,
) -> bool:
    title_text = " | ".join(part for part in (_structured_text(param_name), _structured_text(point_text)) if part).lower()
    if not _contains_any(title_text, ["频率准确度", "frequency accuracy"]):
        return False
    if _contains_any(title_text, ["频率误差", "frequency error", "频率测量误差", "frequency measurement error"]):
        return False
    normalized = {
        key: _structured_text(value)
        for key, value in (structured_fields or {}).items()
        if _structured_text(value)
    }
    error_text = normalized.get("error_value", "")
    if not error_text:
        return False
    if FREQ_UNITS.search(error_text) or FREQ_UNITS.search(_structured_text(cert_u)):
        return False
    limit_text = normalized.get("limit_value", "")
    if limit_text and FREQ_UNITS.search(limit_text):
        return False
    return any(
        _is_reference_oscillator_fixed_point(value)
        for value in (
            normalized.get("nominal_value", ""),
            normalized.get("reference_value", ""),
            normalized.get("measure_value", ""),
            point_text,
        )
    )


def _resolve_condition_axis_from_context(
    *,
    semantic_target: str,
    explicit_axis: Optional[str],
    section_label: str = "",
    point_text: str = "",
    structured_fields: Optional[Dict[str, Any]] = None,
    parameter_contract: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    axis_text = _structured_text(explicit_axis).lower()
    if axis_text:
        if _contains_any(axis_text, ["frequency", "freq", "频率", "carrier", "offset"]):
            return "frequency_band"
        if _contains_any(axis_text, ["period", "time", "interval", "周期", "时间"]):
            return "period_band"
        if _contains_any(axis_text, ["count", "计数"]):
            return "count_axis"

    contract = normalize_parameter_contract(parameter_contract or {})
    condition_value = _structured_text(contract.get("condition_value"))
    if FREQ_UNITS.search(condition_value):
        return "frequency_band"
    if TIME_UNITS.search(condition_value):
        return "period_band"

    context_parts: List[str] = [
        _structured_text(section_label),
        _structured_text(point_text),
        *[_structured_text(value) for value in (structured_fields or {}).values()],
    ]
    context_text = " | ".join(part for part in context_parts if part)
    if FREQ_UNITS.search(context_text):
        return "frequency_band"
    if TIME_UNITS.search(context_text):
        return "period_band"

    if semantic_target in {"frequency_accuracy", "frequency_range", "reference_oscillator"}:
        return "frequency_band"
    if semantic_target in {"period_accuracy", "period_range"}:
        return "period_band"
    return None


def _apply_dynamic_condition_axis(
    semantic: ParamSemantic,
    *,
    semantic_target: str,
    section_label: str = "",
    point_text: str = "",
    structured_fields: Optional[Dict[str, Any]] = None,
    parameter_contract: Optional[Dict[str, Any]] = None,
) -> ParamSemantic:
    resolved_axis = semantic.condition_axis or _resolve_condition_axis_from_context(
        semantic_target=semantic_target,
        explicit_axis=_structured_text((parameter_contract or {}).get("condition_axis")),
        section_label=section_label,
        point_text=point_text,
        structured_fields=structured_fields,
        parameter_contract=parameter_contract,
    )
    if resolved_axis == semantic.condition_axis:
        return semantic
    return replace(semantic, condition_axis=resolved_axis)


def infer_uncertainty_kind(cert_u: str) -> str:
    text = (cert_u or "").strip().lower()
    if "urel" in text:
        return "UREL"
    if text:
        return "U"
    return "UNKNOWN"


def norm_code(s: str) -> str:
    """规范化代码"""
    s = (s or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return re.sub(r"\s+", "", s).upper()


def extract_basis_code(criterion: str) -> Optional[str]:
    """提取依据代码"""
    if not criterion:
        return None
    s = str(criterion)
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    return None


def _structured_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _field_present(value: Any) -> bool:
    return bool(_structured_text(value))


_SEMANTIC_RULE_PRIORITY = {
    "reference_oscillator": 500,
    "input_sensitivity": 450,
    "frequency_accuracy": 420,
    "period_accuracy": 420,
    "count_accuracy": 400,
    "vswr_accuracy": 330,
    "impedance_accuracy": 330,
    "frequency_range": 300,
    "period_range": 300,
    "power_accuracy": 280,
    "phase_noise": 260,
    "modulation_quality": 260,
    "cnr_consistency": 258,
    "spectral_purity": 255,
    "position_consistency": 252,
    "dynamic_range": 240,
}


def _score_registry_rule(
    semantic_target: str,
    rule: Dict[str, Any],
    lowered_text: str,
    unit_family: str,
    normalized_fields: Dict[str, Any],
) -> Optional[Tuple[int, Tuple[str, ...]]]:
    aliases = tuple(alias.lower() for alias in rule.get("section_aliases", ()))
    if not aliases:
        return None
    matched_aliases = tuple(alias for alias in aliases if alias in lowered_text)
    if not matched_aliases:
        return None

    required_fields = tuple(rule.get("required_fields", ()))
    missing_fields = tuple(field for field in required_fields if not _field_present(normalized_fields.get(field)))
    column_requirements = tuple(rule.get("column_requirements", ()))
    column_requirements_ok = not column_requirements or any(
        all(_field_present(normalized_fields.get(field)) for field in group)
        for group in column_requirements
    )
    allowed_units = set(rule.get("allowed_units", set()))
    unit_family_ok = unit_family in allowed_units or (unit_family == "unknown" and "unknown" in allowed_units)

    specificity = max(len(alias) for alias in matched_aliases)
    alias_weight = len(matched_aliases)
    priority = _SEMANTIC_RULE_PRIORITY.get(semantic_target, 0)

    score = priority * 1000 + specificity * 10 + alias_weight * 25
    if unit_family_ok:
        score += 180
    else:
        score -= 180
    if not missing_fields:
        score += 120
    else:
        score -= 35 * len(missing_fields)
    if column_requirements_ok:
        score += 90
    else:
        score -= 45

    if semantic_target == "reference_oscillator" and _contains_any(
        lowered_text,
        REFERENCE_OSCILLATOR_METRIC_TOKENS,
    ):
        score += 140
    if semantic_target in {"frequency_accuracy", "period_accuracy"} and _contains_any(
        lowered_text,
        ["error", "deviation", "误差", "偏差"],
    ):
        score += 120
    if semantic_target in {"frequency_range", "period_range"} and _contains_any(
        lowered_text,
        ["range", "范围"],
    ):
        score += 20
    if semantic_target == "input_sensitivity" and _contains_any(
        lowered_text,
        ["sensitivity", "灵敏度", "触发"],
    ):
        score += 110

    if any(alias == lowered_text.strip() for alias in matched_aliases):
        score += 60
    if len(matched_aliases) > 1:
        score += 15 * (len(matched_aliases) - 1)
    return score, matched_aliases


def _infer_unit_family_from_structured_fields(
    text: str,
    structured_fields: Optional[Dict[str, Any]] = None,
) -> str:
    normalized = {
        key: _structured_text(value)
        for key, value in (structured_fields or {}).items()
        if _structured_text(value)
    }

    families = set()
    strong_voltage_power = False
    for value in normalized.values():
        lowered = value.lower()
        is_motion_value = bool(MOTION_UNITS.search(lowered))
        is_phase_noise_value = "dbc/hz" in lowered or "db/hz" in lowered
        is_length_value = bool(LENGTH_UNITS.search(lowered)) and not is_motion_value
        if is_motion_value:
            families.add("motion")
        if is_length_value:
            families.add("length")
        if is_phase_noise_value:
            families.add("voltage_power")
        if "dbc/hz" in lowered or "db/hz" in lowered:
            families.add("voltage_power")
        if FREQ_UNITS.search(lowered):
            families.add("frequency")
        if TIME_UNITS.search(lowered) and not is_motion_value:
            families.add("time")
        if VOLT_POWER_UNITS.search(lowered):
            families.add("voltage_power")
            if re.search(
                r"(?:dbc/hz|db/hz|dbm|dbc\b|db\b|vpp|vrms|\b(?:uv|mv|kv|v|ua|ma|a|mw|kw|w)\b)",
                lowered,
                flags=re.IGNORECASE,
            ):
                strong_voltage_power = True

    if families == {"motion"}:
        return "motion"
    if families == {"length"}:
        return "length"
    if families == {"voltage_power"}:
        return "voltage_power"
    if families == {"frequency", "voltage_power"}:
        return "voltage_power"
    if families == {"time", "voltage_power"}:
        if not strong_voltage_power:
            return "time"
        return "voltage_power"
    if families == {"motion", "voltage_power"}:
        return "motion"
    if families == {"motion", "frequency"}:
        return "motion"
    if families == {"length", "frequency"}:
        return "length"
    if families == {"length", "voltage_power"}:
        if not strong_voltage_power:
            return "length"
        return "length"
    if "frequency" in families and "time" not in families:
        return "frequency"
    if "time" in families and "frequency" not in families:
        return "time"

    lowered_text = (text or "").lower()
    if MOTION_UNITS.search(lowered_text):
        return "motion"
    if LENGTH_UNITS.search(lowered_text):
        return "length"
    if "dbc/hz" in lowered_text or "db/hz" in lowered_text:
        return "voltage_power"
    if FREQ_UNITS.search(lowered_text):
        return "frequency"
    if TIME_UNITS.search(lowered_text):
        return "time"
    if VOLT_POWER_UNITS.search(lowered_text):
        return "voltage_power"
    return "unknown"


def _build_registry_semantic(
    semantic_target: str,
    rule: Dict[str, Any],
    cert_u: str,
    unit_family: str,
    structured_fields: Optional[Dict[str, Any]] = None,
) -> ParamSemantic:
    normalized_fields = {
        key: _structured_text(value)
        for key, value in (structured_fields or {}).items()
        if _structured_text(value)
    }
    required_fields = tuple(rule.get("required_fields", ()))
    missing_fields = tuple(field for field in required_fields if not _field_present(normalized_fields.get(field)))
    column_requirements = tuple(rule.get("column_requirements", ()))
    column_requirements_ok = not column_requirements or any(
        all(_field_present(normalized_fields.get(field)) for field in group)
        for group in column_requirements
    )
    allowed_units = set(rule.get("allowed_units", set()))
    unit_family_ok = unit_family in allowed_units or (unit_family == "unknown" and "unknown" in allowed_units)

    normalization_notes: List[str] = []
    if missing_fields:
        normalization_notes.append(f"missing required fields: {', '.join(missing_fields)}")
    if not column_requirements_ok:
        normalization_notes.append("column requirements not satisfied")
    if not unit_family_ok:
        normalization_notes.append(f"unit family mismatch: {unit_family}")
    structured_ok = (not missing_fields) and column_requirements_ok and unit_family_ok

    return ParamSemantic(
        task_intent=str(rule.get("task_intent", "unknown")),
        primary_quantity=str(rule.get("primary_quantity", "unknown")),
        unit_family=unit_family,
        condition_axis=rule.get("condition_axis"),
        uncertainty_kind=infer_uncertainty_kind(cert_u),
        semantic_target=semantic_target,
        features={
            "semantic_target": semantic_target,
            "semantic_registry_rule": semantic_target,
            "semantic_registry_matched": True,
            "required_fields": required_fields,
            "missing_required_fields": missing_fields,
            "required_fields_ok": structured_ok,
            "column_requirements_ok": column_requirements_ok,
            "unit_family_ok": unit_family_ok,
            "normalization_notes": tuple(normalization_notes),
            "structured_fields": normalized_fields,
        },
    )


def build_semantic_from_target_hint(
    *,
    semantic_target: str,
    section_label: str,
    point_text: str,
    cert_u: str,
    structured_fields: Optional[Dict[str, Any]] = None,
    parameter_contract: Optional[Dict[str, Any]] = None,
    hint_confidence: float = 0.0,
    hint_alias: str = "",
) -> Optional[ParamSemantic]:
    rule = SEMANTIC_RULE_REGISTRY.get(semantic_target)
    if rule is None:
        return None

    contract = normalize_parameter_contract(parameter_contract or {})
    contract_unit_family = _structured_text(contract.get("unit_family"))
    explicit_unit_family = contract_unit_family if contract_unit_family else ""
    semantic = _build_registry_semantic(
        semantic_target=semantic_target,
        rule=rule,
        cert_u=cert_u,
        unit_family=explicit_unit_family or _infer_unit_family_from_structured_fields(
            " | ".join(
                part for part in (
                    _structured_text(section_label),
                    _structured_text(point_text),
                    _structured_text(cert_u),
                    *[_structured_text(value) for value in (structured_fields or {}).values()],
                ) if part
            ),
            structured_fields,
        ),
        structured_fields=structured_fields,
    )
    semantic = _apply_dynamic_condition_axis(
        semantic,
        semantic_target=semantic_target,
        section_label=section_label,
        point_text=point_text,
        structured_fields=structured_fields,
        parameter_contract=contract,
    )
    semantic_subtype, subtype_confidence, subtype_ambiguous = infer_semantic_subtype(
        semantic_target,
        section_label=section_label,
        item_label=_structured_text(contract.get("item_label")) or _structured_text((structured_fields or {}).get("point_value")),
        condition_axis=_structured_text(contract.get("condition_axis")),
        condition_value=_structured_text(contract.get("condition_value")),
        nominal_value=_structured_text(contract.get("nominal_value")),
        reference_value=_structured_text(contract.get("reference_value")) or _structured_text((structured_fields or {}).get("reference_value")),
        measure_value=_structured_text(contract.get("measure_value")) or _structured_text((structured_fields or {}).get("measure_value")),
        error_value=_structured_text(contract.get("error_value")) or _structured_text((structured_fields or {}).get("error_value")),
        unit_family=semantic.unit_family,
    )
    return replace(
        semantic,
        semantic_subtype=semantic_subtype,
        contract_confidence=max(float(contract.get("confidence") or 0.0), subtype_confidence, float(hint_confidence or 0.0)),
        needs_disambiguation=bool(contract.get("needs_disambiguation")) or subtype_ambiguous,
        features={
            **semantic.features,
            "semantic_subtype": semantic_subtype,
            "contract_confidence": max(float(contract.get("confidence") or 0.0), subtype_confidence, float(hint_confidence or 0.0)),
            "needs_disambiguation": bool(contract.get("needs_disambiguation")) or subtype_ambiguous,
            "parser_hint_target": semantic_target,
            "parser_hint_alias": _structured_text(hint_alias),
            "parser_hint_confidence": float(hint_confidence or 0.0),
        },
    )


def _infer_semantics_from_registry(
    *,
    param_name: str,
    section_label: str,
    point_text: str,
    cert_u: str,
    structured_fields: Optional[Dict[str, Any]] = None,
    parameter_contract: Optional[Dict[str, Any]] = None,
) -> Optional[ParamSemantic]:
    text_parts = [
        _structured_text(section_label),
        _structured_text(param_name),
        _structured_text(point_text),
        _structured_text(cert_u),
    ]
    for value in (structured_fields or {}).values():
        text = _structured_text(value)
        if text:
            text_parts.append(text)
    combined_text = " | ".join(part for part in text_parts if part)
    lowered = combined_text.lower()
    contract = normalize_parameter_contract(parameter_contract or {})
    contract_unit_family = _structured_text(contract.get("unit_family"))
    unit_family = (
        contract_unit_family
        if contract_unit_family and contract_unit_family != "unknown"
        else _infer_unit_family_from_structured_fields(combined_text, structured_fields)
    )
    normalized_fields = {
        key: _structured_text(value)
        for key, value in (structured_fields or {}).items()
        if _structured_text(value)
    }

    if _looks_like_relative_frequency_accuracy_context(
        param_name=param_name,
        point_text=combined_text,
        cert_u=cert_u,
        structured_fields=normalized_fields,
    ):
        semantic = ParamSemantic(
            task_intent="reference_check",
            primary_quantity="relative_frequency",
            unit_family="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            semantic_target="reference_oscillator",
            semantic_subtype="relative_frequency_deviation",
            contract_confidence=max(float(contract.get("confidence") or 0.0), 0.8),
            needs_disambiguation=bool(contract.get("needs_disambiguation")),
            features={
                "semantic_target": "reference_oscillator",
                "semantic_registry_rule": "reference_oscillator_relative_frequency_accuracy",
                "semantic_registry_matched": True,
                "required_fields_ok": True,
                "normalization_notes": (),
                "structured_fields": normalized_fields,
            },
        )
        return semantic

    scored_candidates: List[Tuple[int, str, Dict[str, Any], Tuple[str, ...]]] = []
    for semantic_target, rule in SEMANTIC_RULE_REGISTRY.items():
        scored = _score_registry_rule(
            semantic_target=semantic_target,
            rule=rule,
            lowered_text=lowered,
            unit_family=unit_family,
            normalized_fields=normalized_fields,
        )
        if scored is None:
            continue
        score, matched_aliases = scored
        scored_candidates.append((score, semantic_target, rule, matched_aliases))

    if not scored_candidates:
        return None

    scored_candidates.sort(
        key=lambda item: (
            item[0],
            len(max(item[3], key=len)) if item[3] else 0,
            len(item[3]),
            item[1],
        ),
        reverse=True,
    )
    best_score, best_target, best_rule, best_aliases = scored_candidates[0]
    semantic = _build_registry_semantic(
        semantic_target=best_target,
        rule=best_rule,
        cert_u=cert_u,
        unit_family=unit_family,
        structured_fields=structured_fields,
    )
    semantic = _apply_dynamic_condition_axis(
        semantic,
        semantic_target=best_target,
        section_label=section_label,
        point_text=point_text,
        structured_fields=structured_fields,
        parameter_contract=contract,
    )
    semantic_subtype, subtype_confidence, subtype_ambiguous = infer_semantic_subtype(
        best_target,
        section_label=section_label,
        item_label=_structured_text(contract.get("item_label")) or _structured_text(normalized_fields.get("point_value")),
        condition_axis=_structured_text(contract.get("condition_axis")),
        condition_value=_structured_text(contract.get("condition_value")),
        nominal_value=_structured_text(contract.get("nominal_value")),
        reference_value=_structured_text(contract.get("reference_value")) or _structured_text(normalized_fields.get("reference_value")),
        measure_value=_structured_text(contract.get("measure_value")) or _structured_text(normalized_fields.get("measure_value")),
        error_value=_structured_text(contract.get("error_value")) or _structured_text(normalized_fields.get("error_value")),
        limit_value=_structured_text(contract.get("limit_value")),
        unit_family=unit_family,
    )
    return replace(
        semantic,
        semantic_subtype=semantic_subtype,
        contract_confidence=max(float(contract.get("confidence") or 0.0), subtype_confidence),
        needs_disambiguation=bool(contract.get("needs_disambiguation")) or subtype_ambiguous,
        features={
            **semantic.features,
            "registry_match_score": best_score,
            "registry_matched_aliases": best_aliases,
            "registry_candidate_count": len(scored_candidates),
            "registry_candidate_targets": tuple(target for _, target, _, _ in scored_candidates),
            "semantic_subtype": semantic_subtype,
            "contract_confidence": max(float(contract.get("confidence") or 0.0), subtype_confidence),
            "needs_disambiguation": bool(contract.get("needs_disambiguation")) or subtype_ambiguous,
        },
    )


def infer_param_semantics(
    param_name: str,
    point_text: str,
    cert_u: str = "",
    *,
    structured_fields: Optional[Dict[str, Any]] = None,
    section_label: str = "",
    parameter_contract: Optional[Dict[str, Any]] = None,
) -> ParamSemantic:
    """
    推断参数语义（与原始 semantic_basis_selector.py 完全一致）
    """
    registry_semantic = _infer_semantics_from_registry(
        param_name=param_name,
        section_label=section_label or param_name,
        point_text=point_text,
        cert_u=cert_u,
        structured_fields=structured_fields,
        parameter_contract=parameter_contract,
    )
    if registry_semantic is not None:
        return registry_semantic

    param_name_text = str(param_name or "")
    text = f"{param_name_text} | {point_text} | {cert_u}".lower()
    param_name_lower = param_name_text.lower()
    has_reference = "reference" in text or "标准值" in text or "鏍囧噯鍊?" in text
    has_indicated = "indicated" in text or "指示值" in text or "鎸囩ず鍊?" in text
    has_error = "error" in text or "误差" in text or "璇樊" in text
    has_limit = "limit" in text or "允许误差" in text or "鍏佽璇樊" in text
    has_sensitivity = _contains_any(text, PARAMETER_NAME_RULES["frequency_measurement_sensitivity"] + PARAMETER_NAME_RULES["period_measurement_sensitivity"] + ["sensitivity", "trigger", "灵敏度", "灵敏", "触发", "敏度"])

    unit_family = "unknown"
    if FREQ_UNITS.search(text):
        unit_family = "frequency"
    elif TIME_UNITS.search(text):
        unit_family = "time"
    elif VOLT_POWER_UNITS.search(text):
        unit_family = "voltage_power"

    condition_axis = None
    if has_sensitivity:
        if FREQ_UNITS.search(text):
            condition_axis = "frequency_band"
        elif TIME_UNITS.search(text):
            condition_axis = "period_band"

    if _contains_any(text, REFERENCE_OSCILLATOR_OBJECT_TOKENS) and _contains_any(text, REFERENCE_OSCILLATOR_METRIC_TOKENS):
        return ParamSemantic(
            task_intent="reference_check",
            primary_quantity="relative_frequency",
            unit_family="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
                "reference_oscillator_context": True,
            },
        )

    if _looks_like_relative_frequency_accuracy_context(
        param_name=param_name_text,
        point_text=point_text,
        cert_u=cert_u,
        structured_fields=structured_fields,
    ):
        return ParamSemantic(
            task_intent="reference_check",
            primary_quantity="relative_frequency",
            unit_family="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            semantic_target="reference_oscillator",
            semantic_subtype="relative_frequency_deviation",
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
                "reference_oscillator_context": True,
            },
        )

    if has_sensitivity and _contains_any(param_name_lower, PARAMETER_NAME_RULES["frequency_measurement_sensitivity"]):
        return ParamSemantic(
            task_intent="sensitivity_check",
            primary_quantity="input_sensitivity",
            unit_family="voltage_power",
            condition_axis="frequency_band" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if has_sensitivity and _contains_any(param_name_lower, PARAMETER_NAME_RULES["period_measurement_sensitivity"]):
        return ParamSemantic(
            task_intent="sensitivity_check",
            primary_quantity="input_sensitivity",
            unit_family="voltage_power",
            condition_axis="period_band" if TIME_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(param_name_lower, PARAMETER_NAME_RULES["frequency_measurement_range"]):
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="frequency",
            unit_family="frequency",
            condition_axis="frequency_band" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["frequency_accuracy"]):
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="frequency",
            unit_family="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    has_pulse_period = _contains_any(
        text,
        [
            "脉冲周期",
            "连续脉冲周期",
            "脉冲宽度",
            "连续脉冲宽度",
            "单脉冲宽度",
            "脉冲上升",
            "脉冲下降",
            "脉冲上升、下降时间",
            "脉冲上升/下降时间",
            "延迟时间",
            "两个单脉冲间的时间间隔",
        ],
    )
    if has_pulse_period and unit_family == "time":
        if has_error or has_limit or has_reference or has_indicated:
            return ParamSemantic(
                task_intent="accuracy_check",
                primary_quantity="period",
                unit_family="time",
                condition_axis="period_band",
                uncertainty_kind=infer_uncertainty_kind(cert_u),
                features={
                    "has_reference": has_reference,
                    "has_indicated": has_indicated,
                    "has_error": has_error,
                    "has_limit": has_limit,
                },
            )
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="period",
            unit_family="time",
            condition_axis="period_band" if TIME_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(param_name_lower, PARAMETER_NAME_RULES["period_measurement_range"]):
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="period",
            unit_family="time",
            condition_axis="period_band" if TIME_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["reference_oscillator"]):
        return ParamSemantic(
            task_intent="reference_check",
            primary_quantity="relative_frequency",
            unit_family="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["phase_noise"]):
        return ParamSemantic(
            task_intent="noise_check",
            primary_quantity="phase_noise",
            unit_family="voltage_power",
            condition_axis="offset_frequency" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["vswr_accuracy"]):
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="vswr",
            unit_family="unknown",
            condition_axis="frequency_band" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["impedance_accuracy"]):
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="impedance",
            unit_family="unknown",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["evm"]):
        return ParamSemantic(
            task_intent="quality_check",
            primary_quantity="modulation_quality",
            unit_family=unit_family if unit_family != "unknown" else "unknown",
            condition_axis="carrier_frequency" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["cnr_consistency"]):
        return ParamSemantic(
            task_intent="quality_check",
            primary_quantity="cnr_consistency",
            unit_family="voltage_power",
            condition_axis="frequency_band" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["position_consistency"]):
        return ParamSemantic(
            task_intent="quality_check",
            primary_quantity="position_consistency",
            unit_family="length" if unit_family == "length" else "unknown",
            condition_axis="frequency_band" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["spectral_purity"]):
        return ParamSemantic(
            task_intent="quality_check",
            primary_quantity="spectral_purity",
            unit_family=unit_family if unit_family != "unknown" else "unknown",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["dynamic_range"]):
        dynamic_unit_family = unit_family if unit_family in {"motion", "length", "voltage_power"} else "unknown"
        if dynamic_unit_family == "unknown":
            dynamic_unit_family = "motion" if MOTION_UNITS.search(text) else "voltage_power"
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="dynamic_range",
            unit_family=dynamic_unit_family,
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, PARAMETER_NAME_RULES["power_accuracy"]):
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="power",
            unit_family="voltage_power",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["phase noise", "相位噪声", "鐩镐綅鍣０"]):
        return ParamSemantic(
            task_intent="noise_check",
            primary_quantity="phase_noise",
            unit_family="voltage_power",
            condition_axis="offset_frequency" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["evm", "error vector magnitude", "误差矢量幅度", "璇樊鐭㈤噺骞呭害"]):
        return ParamSemantic(
            task_intent="quality_check",
            primary_quantity="modulation_quality",
            unit_family=unit_family if unit_family != "unknown" else "unknown",
            condition_axis="carrier_frequency" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["spectral purity", "信号纯度", "谐波抑制", "非谐波抑制", "杂波抑制"]):
        return ParamSemantic(
            task_intent="quality_check",
            primary_quantity="spectral_purity",
            unit_family=unit_family if unit_family != "unknown" else "unknown",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["dynamic range", "动态范围", "鍔ㄦ€佽寖鍥?"]):
        dynamic_unit_family = unit_family if unit_family in {"motion", "length", "voltage_power"} else "unknown"
        if dynamic_unit_family == "unknown":
            dynamic_unit_family = "motion" if MOTION_UNITS.search(text) else "voltage_power"
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="dynamic_range",
            unit_family=dynamic_unit_family,
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["count accuracy", "计数准确度", "计数准确", "计数精度"]):
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="count",
            unit_family="unknown",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["power accuracy", "power deviation", "功率准确度", "功率偏差", "鍔熺巼鍑嗙‘搴?", "鍔熺巼鍋忓樊"]):
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="power",
            unit_family="voltage_power",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if has_sensitivity:
        return ParamSemantic(
            task_intent="sensitivity_check",
            primary_quantity="input_sensitivity",
            unit_family="voltage_power",
            condition_axis=condition_axis,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(
        text,
        [
            "frequency measurement range",
            "frequency range",
            "频率测量范围",
            "频率范围",
        ],
    ) and not has_sensitivity:
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="frequency",
            unit_family="frequency",
            condition_axis="frequency_band" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if has_reference and has_indicated and has_error and has_limit and unit_family == "frequency":
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="frequency",
            unit_family="frequency",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if has_reference and has_error and has_limit and unit_family == "frequency":
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="frequency",
            unit_family="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if has_reference and has_indicated and has_error and has_limit and unit_family == "time":
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="period",
            unit_family="time",
            condition_axis="period_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if unit_family == "time" and has_reference and has_error and has_limit:
        if _contains_any(text, ["计时", "时基", "time base", "timebase", "time interval"]):
            return ParamSemantic(
                task_intent="accuracy_check",
                primary_quantity="period",
                unit_family="time",
                condition_axis="period_band",
                uncertainty_kind=infer_uncertainty_kind(cert_u),
                features={
                    "has_reference": has_reference,
                    "has_indicated": has_indicated,
                    "has_error": has_error,
                    "has_limit": has_limit,
                },
            )

    has_time_interval = (
        "????" in text
        or "time interval" in text
        or "??" in text
        or "?" in text
        or "??" in text
    )
    if has_time_interval and unit_family == "time":
        return ParamSemantic(
            task_intent="accuracy_check",
            primary_quantity="period",
            unit_family="time",
            condition_axis="period_band",
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    return ParamSemantic(
        task_intent="unknown",
        primary_quantity="unknown",
        unit_family=unit_family,
        condition_axis=condition_axis,
        uncertainty_kind=infer_uncertainty_kind(cert_u),
        features={
            "has_reference": has_reference,
            "has_indicated": has_indicated,
            "has_error": has_error,
            "has_limit": has_limit,
        },
    )


def infer_kb_capability(entry: Dict[str, Any]) -> KbCapability:
    """推断知识库能力"""
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    measured = str(
        entry.get("measured")
        or metadata.get("???")
        or metadata.get("???")
        or metadata.get("??")
        or entry.get("????")
        or entry.get("??")
        or entry.get("??")
        or ""
    ).strip()
    measure_range_text = str(
        entry.get("measure_range_text")
        or metadata.get("????")
        or entry.get("??")
        or entry.get("measure_range")
        or ""
    ).lower()
    u_text = str(
        entry.get("u_text")
        or metadata.get("????")
        or entry.get("kb_u")
        or entry.get("error_limit_text")
        or ""
    ).strip()
    if not u_text:
        uncertainty = entry.get("uncertainty")
        if isinstance(uncertainty, dict):
            u_text = str(
                uncertainty.get("value_display")
                or uncertainty.get("value")
                or uncertainty.get("text")
                or uncertainty.get("raw")
                or ""
            ).strip()
        elif uncertainty is not None:
            u_text = str(uncertainty).strip()
    context_text = " ".join(
        part for part in [measured.lower(), measure_range_text, u_text.lower(), str(entry.get("raw", "") or "").lower()]
        if part
    )
    measured_lower = measured.lower()
    is_reference_oscillator_metric = _contains_any(measure_range_text, REFERENCE_OSCILLATOR_METRIC_TOKENS)
    inferred_unit_family = infer_contract_unit_family([measured, measure_range_text, u_text, context_text])

    def _make_capability(
        *,
        capability_target: str,
        primary_quantity: str,
        result_quantity: str,
        condition_axis: Optional[str],
        unit_family: str,
        semantic_subtype: str = "",
    ) -> KbCapability:
        inferred_semantic_subtype, subtype_confidence, _ = infer_semantic_subtype(
            capability_target,
            section_label=measured,
            item_label=measured,
            reference_value=measure_range_text,
            measure_value=measure_range_text,
            error_value=measure_range_text,
            unit_family=unit_family,
            candidate_text=context_text,
            kb_mode=True,
        )
        if (
            capability_target == "reference_oscillator"
            and _contains_any(measured_lower, REFERENCE_OSCILLATOR_OBJECT_TOKENS)
            and not _contains_any(context_text, REFERENCE_OSCILLATOR_METRIC_TOKENS)
        ):
            inferred_semantic_subtype = ""
            subtype_confidence = max(float(subtype_confidence or 0.0), 0.55)
        return KbCapability(
            measured=measured,
            capability_target=capability_target,
            primary_quantity=primary_quantity,
            result_quantity=result_quantity,
            condition_axis=condition_axis,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            semantic_subtype=semantic_subtype or inferred_semantic_subtype,
            unit_family=unit_family,
            contract_confidence=subtype_confidence,
            source=entry,
        )

    if measured_lower in AMBIGUOUS_CRYSTAL_FREQUENCY_MEASURED_ALIASES:
        if is_reference_oscillator_metric:
            return _make_capability(
                capability_target="reference_oscillator",
                primary_quantity="relative_frequency",
                result_quantity="relative_frequency",
                condition_axis=None,
                unit_family="frequency",
            )
        if _contains_any(context_text, FREQUENCY_ACCURACY_CONTEXT_TOKENS) or _parse_frequency_range(measure_range_text):
            return _make_capability(
                capability_target="frequency_accuracy",
                primary_quantity="frequency",
                result_quantity="frequency_error_or_value",
                condition_axis="frequency_band",
                unit_family="frequency",
            )
        return _make_capability(
            capability_target="reference_oscillator",
            primary_quantity="relative_frequency",
            result_quantity="relative_frequency",
            condition_axis=None,
            unit_family="frequency",
        )

    if measured_lower in KB_MEASURED_RULES["reference_oscillator"]:
        return _make_capability(
            capability_target="reference_oscillator",
            primary_quantity="relative_frequency",
            result_quantity="relative_frequency",
            condition_axis=None,
            unit_family="frequency",
        )

    if _is_count_accuracy_measured_label(measured_lower):
        return KbCapability(
            measured=measured,
            capability_target="count_accuracy",
            primary_quantity="count",
            result_quantity="count",
            condition_axis="count_axis",
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in KB_MEASURED_RULES["vswr_accuracy"]:
        return _make_capability(
            capability_target="vswr_accuracy",
            primary_quantity="vswr",
            result_quantity="vswr",
            condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
            unit_family="unknown",
        )

    if measured_lower in KB_MEASURED_RULES["impedance_accuracy"]:
        return _make_capability(
            capability_target="impedance_accuracy",
            primary_quantity="impedance",
            result_quantity="impedance",
            condition_axis=None,
            unit_family="unknown",
        )

    if measured_lower in KB_MEASURED_RULES["frequency_range"] and is_reference_oscillator_metric:
        return _make_capability(
            capability_target="reference_oscillator",
            primary_quantity="relative_frequency",
            result_quantity="relative_frequency",
            condition_axis=None,
            unit_family="frequency",
        )

    if measured_lower in KB_MEASURED_RULES["frequency_range"]:
        if _contains_any(context_text, PARAMETER_NAME_RULES["frequency_measurement_sensitivity"] + ["sensitivity", "灵敏度", "trigger", "触发"]):
            return KbCapability(
                measured=measured,
                capability_target="input_sensitivity",
                primary_quantity="input_sensitivity",
                result_quantity="input_threshold",
                condition_axis="frequency_band",
                uncertainty_kind=infer_uncertainty_kind(u_text),
                source=entry,
            )
        # JJF2196 这类条目常用“频率 + 频段 + Urel”表达频率测量能力，
        # 没有显式写出“准确度/误差”字样。若这里仍落到 frequency_range，
        # deterministic selector 会把真实 accuracy 候选过早过滤掉。
        if (
            measured_lower in {"frequency", "频率", "棰戠巼"}
            and str(u_text or "").strip()
            and _parse_frequency_range(measure_range_text)
        ):
            return KbCapability(
                measured=measured,
                capability_target="frequency_accuracy",
                primary_quantity="frequency",
                result_quantity="frequency_error_or_value",
                condition_axis="frequency_band",
                uncertainty_kind=infer_uncertainty_kind(u_text),
                source=entry,
            )
        if _contains_any(context_text, ["accuracy", "deviation", "偏差", "误差", "频率准确度", "频率偏差"]):
            return KbCapability(
                measured=measured,
                capability_target="frequency_accuracy",
                primary_quantity="frequency",
                result_quantity="frequency_error_or_value",
                condition_axis="frequency_band",
                uncertainty_kind=infer_uncertainty_kind(u_text),
                source=entry,
            )
        return KbCapability(
            measured=measured,
            capability_target="frequency_range",
            primary_quantity="frequency",
            result_quantity="frequency",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in KB_MEASURED_RULES["phase_noise"]:
        return KbCapability(
            measured=measured,
            capability_target="phase_noise",
            primary_quantity="phase_noise",
            result_quantity="phase_noise_level",
            condition_axis="offset_frequency" if FREQ_UNITS.search(measure_range_text) else None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in KB_MEASURED_RULES["modulation_quality"]:
        return _make_capability(
            capability_target="modulation_quality",
            primary_quantity="modulation_quality",
            result_quantity="evm",
            condition_axis="carrier_frequency" if FREQ_UNITS.search(measure_range_text) else None,
            unit_family="voltage_power",
        )

    if measured_lower in KB_MEASURED_RULES["cnr_consistency"]:
        return _make_capability(
            capability_target="cnr_consistency",
            primary_quantity="cnr_consistency",
            result_quantity="cnr_consistency",
            condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
            unit_family="voltage_power",
        )

    if measured_lower in KB_MEASURED_RULES["position_consistency"]:
        return _make_capability(
            capability_target="position_consistency",
            primary_quantity="position_consistency",
            result_quantity="position_consistency",
            condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
            unit_family="length",
        )

    if measured_lower in KB_MEASURED_RULES["dynamic_range"]:
        return _make_capability(
            capability_target="dynamic_range",
            primary_quantity="dynamic_range",
            result_quantity="dynamic_range",
            condition_axis=None,
            unit_family=inferred_unit_family,
        )

    if measured_lower in KB_MEASURED_RULES["spectral_purity"]:
        return KbCapability(
            measured=measured,
            capability_target="spectral_purity",
            primary_quantity="spectral_purity",
            result_quantity="spectral_purity_level",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in KB_MEASURED_RULES["power_accuracy"]:
        if measured_lower in {"power_resolution", "功率分辨力"}:
            return _make_capability(
                capability_target="power_accuracy",
                primary_quantity="power",
                result_quantity="power_value",
                condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
                unit_family="voltage_power",
                semantic_subtype="power_resolution",
            )
        power_context = " ".join(part for part in [measured_lower, context_text] if part)
        power_axis = "frequency_band" if _extract_frequency_band_hz(entry) else None
        if _contains_any(power_context, ["power deviation", "功率偏差", "偏差", "deviation", "accuracy", "准确度", "误差"]):
            result_quantity = "power_error"
        elif _contains_any(
            power_context,
            ["range", "范围", "power range", "功率范围", "power level", "功率电平", "level", "电平"],
        ):
            result_quantity = "power_value"
        else:
            result_quantity = "power_value"
        return KbCapability(
            measured=measured,
            capability_target="power_accuracy",
            primary_quantity="power",
            result_quantity=result_quantity,
            condition_axis=power_axis,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            semantic_subtype="power_error" if result_quantity == "power_error" else "power_range",
            source=entry,
        )

    if measured_lower in {"frequency", "频率", "棰戠巼"}:
        return KbCapability(
            measured=measured,
            capability_target="frequency_accuracy",
            primary_quantity="frequency",
            result_quantity="frequency_error_or_value",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {"carrier_frequency_deviation", "载波频率偏差"}:
        return _make_capability(
            capability_target="frequency_accuracy",
            primary_quantity="frequency",
            result_quantity="frequency_error_or_value",
            condition_axis=None,
            unit_family="frequency",
            semantic_subtype="carrier_frequency_error",
        )

    if measured_lower in {"reference_frequency", "参考频率", "time_base_accuracy", "时基准确度"}:
        return KbCapability(
            measured=measured,
            capability_target="frequency_accuracy",
            primary_quantity="frequency",
            result_quantity="frequency_error_or_value",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(u_text),
            semantic_subtype="timebase_accuracy",
            source=entry,
        )

    if measured_lower in {"period", "周期"}:
        if _looks_like_period_accuracy_kb_entry(
            measured_lower=measured_lower,
            measure_range_text=measure_range_text,
            u_text=u_text,
            inferred_unit_family=inferred_unit_family,
            context_text=context_text,
        ):
            return _make_capability(
                capability_target="period_accuracy",
                primary_quantity="period",
                result_quantity="period_error_or_value",
                condition_axis="period_band",
                unit_family="time",
            )
        if _is_time_difference_accuracy_context(context_text):
            return _make_capability(
                capability_target="period_accuracy",
                primary_quantity="period",
                result_quantity="period_error_or_value",
                condition_axis="period_band",
                unit_family="time",
            )
        return _make_capability(
            capability_target="period_range",
            primary_quantity="period",
            result_quantity="period",
            condition_axis=None,
            unit_family="time",
        )

    # 显式的时间间隔/延迟类条目，优先视为准确度能力。
    if _is_explicit_period_accuracy_measured_label(measured_lower):
        return _make_capability(
            capability_target="period_accuracy",
            primary_quantity="period",
            result_quantity="period_error_or_value",
            condition_axis="period_band",
            unit_family="time",
        )

    if _is_pulse_period_measured_label(measured_lower):
        if _contains_any(context_text, ["accuracy", "deviation", "偏差", "误差", "准确度", "精度"]):
            return _make_capability(
                capability_target="period_accuracy",
                primary_quantity="period",
                result_quantity="period_error_or_value",
                condition_axis="period_band",
                unit_family="time",
            )
        return _make_capability(
            capability_target="period_range",
            primary_quantity="period",
            result_quantity="period",
            condition_axis="period_band",
            unit_family="time",
        )

    if _contains_any(measured_lower, ["延时", "延迟", "time delay", "time-delay", "time delay accuracy"]):
        return _make_capability(
            capability_target="period_accuracy",
            primary_quantity="period",
            result_quantity="period_error_or_value",
            condition_axis="period_band",
            unit_family="time",
        )

    if measured_lower in KB_MEASURED_RULES["period_range"] or "时间间隔" in measured_lower or "time interval" in measured_lower:
        if _is_time_difference_accuracy_context(context_text):
            return _make_capability(
                capability_target="period_accuracy",
                primary_quantity="period",
                result_quantity="period_error_or_value",
                condition_axis="period_band",
                unit_family="time",
            )
        if _contains_any(context_text, PARAMETER_NAME_RULES["period_measurement_sensitivity"] + ["sensitivity", "灵敏度", "trigger", "触发"]):
            return _make_capability(
                capability_target="input_sensitivity",
                primary_quantity="input_sensitivity",
                result_quantity="input_threshold",
                condition_axis="period_band",
                unit_family="voltage_power",
            )
        if (
            _contains_any(context_text, ["accuracy", "deviation", "偏差", "误差", "周期准确度", "周期偏差"])
            or _looks_like_period_accuracy_kb_entry(
                measured_lower=measured_lower,
                measure_range_text=measure_range_text,
                u_text=u_text,
                inferred_unit_family=inferred_unit_family,
                context_text=context_text,
            )
        ):
            return _make_capability(
                capability_target="period_accuracy",
                primary_quantity="period",
                result_quantity="period_error_or_value",
                condition_axis="period_band",
                unit_family="time",
            )
        return _make_capability(
            capability_target="period_range",
            primary_quantity="period",
            result_quantity="period",
            condition_axis="period_band",
            unit_family="time",
        )

    if measured_lower in {"power_range", "功率范围", "鍔熺巼鑼冨洿"}:
        return KbCapability(
            measured=measured,
            capability_target="power_accuracy",
            primary_quantity="power",
            result_quantity="power_value",
            condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            semantic_subtype="power_range",
            source=entry,
        )

    if measured_lower in {"power_deviation", "功率偏差", "鍔熺巼鍋忓樊"}:
        return KbCapability(
            measured=measured,
            capability_target="power_accuracy",
            primary_quantity="power",
            result_quantity="power_error",
            condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            semantic_subtype="power_error",
            source=entry,
        )

    if measured_lower in {"power_level", "功率电平", "level", "电平"}:
        return KbCapability(
            measured=measured,
            capability_target="power_accuracy",
            primary_quantity="power",
            result_quantity="power_value",
            condition_axis="frequency_band" if _extract_frequency_band_hz(entry) else None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            semantic_subtype="power_range",
            source=entry,
        )

    if measured_lower in {"phase_noise", "相位噪声", "鐩镐綅鍣０"}:
        return KbCapability(
            measured=measured,
            capability_target="phase_noise",
            primary_quantity="phase_noise",
            result_quantity="phase_noise_level",
            condition_axis="offset_frequency" if FREQ_UNITS.search(measure_range_text) else None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {"error_vector_magnitude", "误差矢量幅度", "璇樊鐭㈤噺骞呭害", "evm"}:
        return _make_capability(
            capability_target="modulation_quality",
            primary_quantity="modulation_quality",
            result_quantity="evm",
            condition_axis="carrier_frequency" if FREQ_UNITS.search(measure_range_text) else None,
            unit_family="voltage_power",
        )

    if measured_lower in {"power_dynamic_range", "功率动态范围", "鍔熺巼鍔ㄦ€佽寖鍥?"}:
        return _make_capability(
            capability_target="dynamic_range",
            primary_quantity="dynamic_range",
            result_quantity="dynamic_range",
            condition_axis=None,
            unit_family="voltage_power",
        )

    if measured_lower in {"速度动态范围", "加速度动态范围", "加加速度动态范围", "谐波抑制", "非谐波抑制", "杂波抑制"}:
        if "动态范围" in measured_lower:
            return _make_capability(
                capability_target="dynamic_range",
                primary_quantity="dynamic_range",
                result_quantity="dynamic_range",
                condition_axis=None,
                unit_family=inferred_unit_family,
            )
        return KbCapability(
            measured=measured,
            capability_target="spectral_purity",
            primary_quantity="spectral_purity",
            result_quantity="spectral_purity_level",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in KB_MEASURED_RULES["input_sensitivity_frequency"]:
        return KbCapability(
            measured=measured,
            capability_target="input_sensitivity",
            primary_quantity="input_sensitivity",
            result_quantity="input_threshold",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in KB_MEASURED_RULES["input_sensitivity_period"]:
        return KbCapability(
            measured=measured,
            capability_target="input_sensitivity",
            primary_quantity="input_sensitivity",
            result_quantity="input_threshold",
            condition_axis="period_band",
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    return KbCapability(
        measured=measured,
        capability_target="unknown",
        primary_quantity="unknown",
        result_quantity="unknown",
        condition_axis=None,
        uncertainty_kind=infer_uncertainty_kind(u_text),
        source=entry,
    )


def _extract_frequency_hz_from_text(text: str) -> Optional[float]:
    if not text:
        return None

    patterns = [
        r"(?:频率|Frequency)[^0-9+\-]*([-+]?\d*\.?\d+\s*(?:THz|GHz|MHz|kHz|Hz))",
        r"([-+]?\d*\.?\d+\s*(?:THz|GHz|MHz|kHz|Hz))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        parsed = _parse_frequency_to_hz(match.group(1))
        if parsed is not None:
            return parsed
    return None


def _extract_time_s_from_text(text: str) -> Optional[float]:
    if not text:
        return None

    preferred_patterns = [
        r"(?:标称值|Nominal|标准值|Reference|指示值|Indicated|测量值|Measured|值|Value)[^:：=]*[:：=]\s*([-+]?\d*\.?\d+\s*(?:ps|ns|us|µs|μs|ms|h|s))",
        r"([-+]?\d*\.?\d+\s*(?:ps|ns|us|µs|μs|ms|h|s))",
    ]
    for pattern in preferred_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        parsed, _ = parse_value_with_unit(match.group(1), keep_sign=True)
        if parsed is not None:
            return parsed
    return None


def _extract_frequency_band_hz(source: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    if not isinstance(source, dict):
        return None

    parenthesized_texts: List[str] = []
    fallback_texts: List[str] = []
    for key in (
        "measure_range_segments",
        "measure_range_segments_text",
        "measure_range_text",
        "measure_range",
        "range",
        "Range",
        "raw",
        "raw_block",
    ):
        raw_value = source.get(key, "")
        if isinstance(raw_value, (list, tuple)):
            values = [str(item).strip() for item in raw_value if str(item).strip()]
        else:
            text = str(raw_value or "").strip()
            values = [text] if text else []

        for text in values:
            parenthesized = re.findall(r"\(([^()]*(?:THz|GHz|MHz|kHz|Hz)[^()]*)\)", text)
            parenthesized_texts.extend(parenthesized)
            if any(unit in text for unit in ("THz", "GHz", "MHz", "kHz", "Hz")):
                fallback_texts.append(text)

    freq_pattern = re.compile(r"([-+]?\d*\.?\d+)\s*(THz|GHz|MHz|kHz|Hz)", re.IGNORECASE)

    for candidate in parenthesized_texts + fallback_texts:
        matches = freq_pattern.findall(candidate)
        if len(matches) >= 2:
            lower = _parse_frequency_to_hz(f"{matches[0][0]} {matches[0][1]}")
            upper = _parse_frequency_to_hz(f"{matches[1][0]} {matches[1][1]}")
            if lower is not None and upper is not None:
                return lower, upper
        elif len(matches) == 1:
            single = _parse_frequency_to_hz(f"{matches[0][0]} {matches[0][1]}")
            if single is not None:
                return single, single

        single = _parse_frequency_to_hz(candidate)
        if single is not None:
            return single, single
    return None


def _extract_time_band_s(source: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    if not isinstance(source, dict):
        return None

    parenthesized_texts: List[str] = []
    fallback_texts: List[str] = []
    for key in (
        "measure_range_segments",
        "measure_range_segments_text",
        "measure_range_text",
        "measure_range",
        "range",
        "Range",
        "raw",
        "raw_block",
    ):
        raw_value = source.get(key, "")
        if isinstance(raw_value, (list, tuple)):
            values = [str(item).strip() for item in raw_value if str(item).strip()]
        else:
            text = str(raw_value or "").strip()
            values = [text] if text else []

        for text in values:
            parenthesized = re.findall(r"\(([^()]*(?:ps|ns|us|µs|μs|ms|h|s)[^()]*)\)", text, flags=re.IGNORECASE)
            parenthesized_texts.extend(parenthesized)
            if re.search(r"\d\s*(?:ps|ns|us|µs|μs|ms|h|s)\b", text, flags=re.IGNORECASE):
                fallback_texts.append(text)

    for candidate in parenthesized_texts + fallback_texts:
        parsed = parse_range_limit(candidate)
        if parsed is not None:
            lower, upper = parsed
            if lower is not None and upper is not None:
                return lower, upper

        single, _ = parse_value_with_unit(candidate, keep_sign=True)
        if single is not None:
            return single, single
    return None


def _rank_frequency_candidates(point_freq_hz: float, candidates: List[KbCapability]) -> List[KbCapability]:
    scored: List[Tuple[Tuple[int, float, float, int], KbCapability]] = []
    for idx, cap in enumerate(candidates):
        band = _extract_frequency_band_hz(cap.source or {})
        if not band:
            continue

        lower, upper = band
        contains = int(lower <= point_freq_hz <= upper)
        distance = 0.0 if contains else min(abs(point_freq_hz - lower), abs(point_freq_hz - upper))
        width = max(upper - lower, 1.0)
        score = (contains, -distance, -width, -idx)
        scored.append((score, cap))

    if not scored:
        return candidates

    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = [cap for _, cap in scored]
    seen_ids = {id(cap) for cap in ordered}
    ordered.extend(cap for cap in candidates if id(cap) not in seen_ids)
    return ordered


def _rank_time_candidates(point_time_s: float, candidates: List[KbCapability]) -> List[KbCapability]:
    scored: List[Tuple[Tuple[int, float, float, int], KbCapability]] = []
    for idx, cap in enumerate(candidates):
        band = _extract_time_band_s(cap.source or {})
        if not band:
            continue

        lower, upper = band
        contains = int(lower <= point_time_s <= upper)
        distance = 0.0 if contains else min(abs(point_time_s - lower), abs(point_time_s - upper))
        width = max(upper - lower, 1e-18)
        score = (contains, -distance, -width, -idx)
        scored.append((score, cap))

    if not scored:
        return candidates

    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = [cap for _, cap in scored]
    seen_ids = {id(cap) for cap in ordered}
    ordered.extend(cap for cap in candidates if id(cap) not in seen_ids)
    return ordered


def _rank_condition_axis_candidates(point_value: float, candidates: List[KbCapability], condition_axis: Optional[str]) -> List[KbCapability]:
    axis = (condition_axis or "").strip().lower()
    if axis == "frequency_band":
        return _rank_frequency_candidates(point_value, candidates)
    if axis == "period_band":
        return _rank_time_candidates(point_value, candidates)
    return candidates


def _rank_period_label_candidates(param: ParamSemantic, candidates: List[KbCapability]) -> List[KbCapability]:
    """在 period 族候选中优先选择“周期”而不是“时间间隔”。

    这样可以让“周期测量误差/周期测量范围”这类参数更稳定地命中
    语义上更贴近的 KB 条目，而不是被“时间间隔”条目抢先。
    """
    if not candidates:
        return candidates
    if param.primary_quantity != "period":
        return candidates

    def _priority(cap: KbCapability) -> tuple[int, int]:
        measured = _contains_any(cap.measured, ["周期", "period"])
        time_interval = _contains_any(cap.measured, ["时间间隔", "time interval"])
        if measured and not time_interval:
            return (0, 0)
        if time_interval and not measured:
            return (1, 0)
        return (2, 0)

    return sorted(candidates, key=_priority)


def _is_pulse_period_measured_label(measured_lower: str) -> bool:
    return _contains_any(
        measured_lower,
        [
            "脉冲周期",
            "连续脉冲周期",
            "脉冲宽度",
            "连续脉冲宽度",
            "单脉冲宽度",
            "脉冲上升",
            "脉冲下降",
            "脉冲上升、下降时间",
            "脉冲上升/下降时间",
            "延迟时间",
            "两个单脉冲间的时间间隔",
        ],
    )


def _is_explicit_period_accuracy_measured_label(measured_lower: str) -> bool:
    return _contains_any(
        measured_lower,
        [
            "输出时间间隔",
            "时间间隔测量",
            "两个单脉冲间的时间间隔",
            "延迟时间",
        ],
    )


def _is_time_difference_accuracy_context(context_text: str) -> bool:
    return _contains_any(context_text, ["s/d", "s/m"])


def _is_count_accuracy_measured_label(measured_lower: str) -> bool:
    return _contains_any(
        measured_lower,
        [
            "周期信号脉冲计数",
            "非周期单脉冲计数",
            "脉冲计数",
            "计数准确度",
            "计数精度",
            "count accuracy",
        ],
    )


def _looks_like_period_accuracy_kb_entry(
    *,
    measured_lower: str,
    measure_range_text: str,
    u_text: str,
    inferred_unit_family: str,
    context_text: str,
) -> bool:
    if "周期" not in measured_lower and "period" not in measured_lower:
        return False
    if inferred_unit_family != "time":
        return False
    if not parse_range_limit(measure_range_text):
        return False
    if infer_uncertainty_kind(u_text) == "UREL":
        return True
    return _contains_any(context_text, ["urel", "相对", "relative uncertainty"])


def structured_prefilter(param: ParamSemantic, kb_entries: List[Dict[str, Any]]) -> List[KbCapability]:
    """结构化预过滤"""
    wanted_targets = STRUCTURED_PREFILTER_TARGETS.get((param.task_intent, param.primary_quantity), set())

    candidates: List[KbCapability] = []
    for entry in kb_entries:
        cap = infer_kb_capability(entry)
        if cap.capability_target not in wanted_targets:
            continue
        if param.condition_axis and cap.condition_axis and param.condition_axis != cap.condition_axis:
            continue
        candidates.append(cap)
    return candidates


class FirstCandidateDecider:
    """兼容旧接口的占位 Decider。

    新链路不再依赖“first candidate wins”。保留该类仅为兼容旧调用方。
    """
    def decide(self, param: ParamSemantic, candidates: List[KbCapability]) -> Dict[str, Any]:
        if not candidates:
            return {"selected_measured": [], "rationale": "No compatible candidates after structured prefilter."}
        return {
            "selected_measured": [candidates[0].measured],
            "rationale": "Legacy decider placeholder; deterministic selector ignores this choice.",
        }


def select_basis_with_audit(
    param_name: str,
    point_text: str,
    cert_u: str,
    kb_entries: List[Dict[str, Any]],
    decider: Optional[SemanticDecider] = None,
    *,
    basis_code: str = "",
    section_label: str = "",
    measure_value: str = "",
    reference_value: str = "",
    error_value: str = "",
    point_value: str = "",
    parameter_contract: Optional[Dict[str, Any]] = None,
    parser_meta: Optional[Dict[str, Any]] = None,
    semantic_target_override: str = "",
    semantic_subtype_hint: str = "",
    candidate_target_preference: str = "",
    override_note: str = "",
) -> SelectionResult:
    """
    根据语义分析选择最佳校准依据。

    新实现走确定性 selector，按候选唯一键返回结果；旧 decider 参数仅保留兼容性。
    """
    from .selector import normalize_cert_point, select_kb_candidates

    cert_point, param = normalize_cert_point(
        basis_code=basis_code,
        section_label=section_label or param_name,
        param_name=param_name,
        point_text=point_text,
        cert_u=cert_u,
        measure_value=measure_value,
        reference_value=reference_value,
        error_value=error_value,
        point_value=point_value,
        parameter_contract=parameter_contract,
        parser_meta=parser_meta,
    )
    if semantic_target_override:
        notes = [note for note in (cert_point.normalization_notes or ()) if note != "unknown semantic"]
        if override_note:
            notes.append(override_note)
        subtype_hint = _structured_text(semantic_subtype_hint)
        cert_subtype = _structured_text(cert_point.semantic_subtype)
        resolved_subtype = cert_subtype
        if subtype_hint and (not cert_subtype or cert_subtype == subtype_hint):
            resolved_subtype = subtype_hint
        cert_point = replace(
            cert_point,
            semantic_target=semantic_target_override,
            semantic_subtype=resolved_subtype,
            required_fields_ok=True,
            normalization_notes=tuple(dict.fromkeys(note for note in notes if note)),
        )
    outcome = select_kb_candidates(
        cert_point,
        param,
        kb_entries,
        candidate_target_preference=candidate_target_preference,
    )

    selected_capabilities: List[KbCapability] = []
    selected_measured: List[str] = []
    if outcome.selected_candidate is not None:
        selected_capability = KbCapability(
            measured=outcome.selected_candidate.measured,
            capability_target=outcome.selected_candidate.capability_target,
            primary_quantity=outcome.selected_candidate.primary_quantity,
            result_quantity=outcome.selected_candidate.result_quantity,
            condition_axis=outcome.selected_candidate.condition_axis,
            uncertainty_kind=outcome.selected_candidate.u_kind,
            semantic_subtype=outcome.selected_candidate.semantic_subtype,
            unit_family=outcome.selected_candidate.unit_family,
            contract_confidence=outcome.selected_candidate.contract_confidence,
            source=outcome.selected_candidate.source or {},
        )
        selected_capabilities = [selected_capability]
        selected_measured = [selected_capability.measured]

    ranked_measured = [candidate.measured for candidate in outcome.ranked_candidates]
    rejected_measured = [
        candidate.measured
        for candidate in outcome.filtered_candidates
        if outcome.selected_candidate is None or candidate.candidate_id != outcome.selected_candidate.candidate_id
    ]

    audit = SelectionAudit(
        task_goal=f"{param.task_intent}:{param.primary_quantity}",
        primary_quantity=param.primary_quantity,
        unit_family=param.unit_family,
        condition_axis=param.condition_axis,
        uncertainty_kind=param.uncertainty_kind,
        prefiltered_candidates=[candidate.measured for candidate in outcome.filtered_candidates],
        selected_measured=selected_measured,
        rejected_measured=rejected_measured,
        semantic_target=outcome.cert_point.semantic_target,
        semantic_subtype=outcome.cert_point.semantic_subtype,
        selected_candidate_id=outcome.selected_candidate.candidate_id if outcome.selected_candidate else None,
        used_fallback_candidate_target=outcome.used_fallback_candidate_target,
        selected_target_relation=outcome.selected_target_relation,
        ranked_candidates=[candidate.candidate_id for candidate in outcome.ranked_candidates],
        candidate_reasons=dict(outcome.candidate_reasons),
        basis_candidates=[candidate.candidate_id for candidate in outcome.basis_candidates],
        rationale=outcome.rationale,
    )
    return SelectionResult(
        selected=selected_capabilities,
        audit=audit,
        selected_candidate_id=outcome.selected_candidate.candidate_id if outcome.selected_candidate else None,
        used_fallback_candidate_target=outcome.used_fallback_candidate_target,
        selected_target_relation=outcome.selected_target_relation,
        selected_candidate=outcome.selected_candidate,
        basis_candidates=outcome.basis_candidates,
        filtered_candidates=outcome.filtered_candidates,
        ranked_candidates=outcome.ranked_candidates,
        cert_point=outcome.cert_point,
        param_semantic=outcome.param_semantic,
    )


def semantic_filter_basis_entries(
    basis_entries: List[Dict],
    param_semantics: ParamSemantic,
    criterion_list: List[str],
    top_k: int = 5,
) -> List[Dict]:
    """
    根据语义分析过滤基础依据条目
    """
    if not basis_entries:
        return []

    # 第一阶段：精确匹配
    exact_matches = []
    exact_code_matches = []

    for entry in basis_entries:
        entry_code = extract_basis_code(entry.get("依据编号", entry.get("校准依据", "")))
        entry_name = entry.get("依据名称", entry.get("FILE_NAME", ""))

        # 精确匹配
        for criterion in criterion_list:
            criterion_code = extract_basis_code(criterion)
            if entry_code and criterion_code and norm_code(entry_code) == norm_code(criterion_code):
                exact_code_matches.append(entry)
                continue

            if str(entry_name).lower() in str(criterion).lower():
                exact_matches.append(entry)
                continue

    if exact_code_matches:
        return exact_code_matches[:top_k]

    if exact_matches:
        return exact_matches[:top_k]

    # 第二阶段：语义匹配
    candidate_scores = []

    for entry in basis_entries:
        score = 0.0
        entry_category = entry.get("category", "unknown")

        # 语义权重
        if hasattr(param_semantics, "unit_family") and param_semantics.unit_family == entry_category:
            score += 0.5

        entry_name = entry.get("依据名称", entry.get("FILE_NAME", "")).lower()
        if "电压" in entry_name and param_semantics.unit_family == "voltage_power":
            score += 0.2
        if "电流" in entry_name and param_semantics.unit_family == "voltage_power":
            score += 0.2
        if "频率" in entry_name and param_semantics.unit_family == "frequency":
            score += 0.2
        if "功率" in entry_name and param_semantics.unit_family == "voltage_power":
            score += 0.2

        candidate_scores.append((score, entry))

    candidate_scores.sort(key=lambda x: x[0], reverse=True)
    return [entry for score, entry in candidate_scores[:top_k]]
