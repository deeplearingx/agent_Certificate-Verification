#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic KB selector for parameter verification."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .contracts import normalize_parameter_contract, subtype_allowed_unit_families, subtype_bool_option
from .parser_core import extract_basis_code, norm_code, parse_range_limit, parse_value_with_unit
from .parser_domain import (
    _parse_frequency_point_list,
    _parse_frequency_range,
    _parse_frequency_to_hz,
    _parse_range_to_base_units,
)
from .rules import REFERENCE_OSCILLATOR_OBJECT_TOKENS, STRUCTURED_PREFILTER_TARGETS
from .semantic import (
    KbCapability,
    ParamSemantic,
    build_semantic_from_target_hint,
    infer_kb_capability,
    infer_param_semantics,
)


@dataclass(frozen=True)
class NormalizedKbCandidate:
    candidate_id: str
    basis_code: str
    measured: str
    capability_target: str
    primary_quantity: str
    result_quantity: str
    condition_axis: Optional[str]
    band_kind: str
    band_lower: Optional[float]
    band_upper: Optional[float]
    discrete_points: Tuple[float, ...]
    u_kind: str
    u_interval: Optional[Tuple[float, float]]
    semantic_subtype: str = ""
    unit_family: str = "unknown"
    contract_confidence: float = 0.0
    required_fields_ok: bool = True
    normalization_notes: Tuple[str, ...] = field(default_factory=tuple)
    source: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedCertPoint:
    basis_code: str
    section_label: str
    param_name: str
    measure_value: str
    reference_value: str
    error_value: str
    point_value: str
    cert_u: str
    semantic_target: str
    semantic_subtype: str
    axis_value: Optional[float]
    axis_family: Optional[str]
    contract_confidence: float
    needs_disambiguation: bool
    required_fields_ok: bool
    parameter_contract: Dict[str, Any] = field(default_factory=dict)
    normalization_notes: Tuple[str, ...] = field(default_factory=tuple)
    semantic_source: str = ""


@dataclass(frozen=True)
class SelectorOutcome:
    cert_point: NormalizedCertPoint
    param_semantic: ParamSemantic
    basis_candidates: List[NormalizedKbCandidate]
    filtered_candidates: List[NormalizedKbCandidate]
    ranked_candidates: List[NormalizedKbCandidate]
    selected_candidate: Optional[NormalizedKbCandidate]
    candidate_reasons: Dict[str, str]
    rationale: str
    used_fallback_candidate_target: bool = False
    selected_target_relation: str = ""


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "; ".join(_coerce_text(item) for item in value if _coerce_text(item))
    return str(value).strip()


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(token.lower() in lowered for token in tokens)


def _normalize_uncertainty_kind(u_text: str) -> str:
    lowered = (u_text or "").lower()
    if "urel" in lowered or "%" in lowered:
        return "UREL"
    if lowered:
        return "U"
    return "UNKNOWN"


def _split_interval_text(text: str) -> Optional[Tuple[str, str]]:
    if not text or not any(sep in text for sep in ("~", "～")):
        return None
    parts = [part.strip() for part in re.split(r"[~～]", text) if part.strip()]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _parse_uncertainty_token(token: str, u_kind: str) -> Optional[float]:
    if not token:
        return None
    if u_kind == "UREL":
        parsed, _ = parse_value_with_unit(token, base_val=None, keep_sign=True)
        return abs(parsed) if parsed is not None else None
    parsed, _ = parse_value_with_unit(token, keep_sign=True)
    return abs(parsed) if parsed is not None else None


def _normalize_uncertainty_interval(u_text: str, u_kind: str) -> Optional[Tuple[float, float]]:
    if not u_text or u_kind == "UNKNOWN":
        return None
    interval = _split_interval_text(u_text)
    if not interval:
        single = _parse_uncertainty_token(u_text, u_kind)
        if single is None:
            return None
        return (single, single)

    left = _parse_uncertainty_token(interval[0], u_kind)
    right = _parse_uncertainty_token(interval[1], u_kind)
    if left is None or right is None:
        return None
    return (min(left, right), max(left, right))


def _stable_candidate_id(basis_code: str, measured: str, measure_range_text: str, u_text: str) -> str:
    return "|".join(
        [
            norm_code(basis_code or "") or "UNKNOWN",
            measured.strip() or "UNKNOWN",
            (measure_range_text or "").strip() or "N/A",
            (u_text or "").strip() or "N/A",
        ]
    )


def _entry_basis_code(entry: Dict[str, Any]) -> str:
    candidates = [
        _coerce_text(entry.get("file_code")),
        _coerce_text(entry.get("FILE_CODE")),
        _coerce_text(entry.get("依据编号")),
        _coerce_text(entry.get("standard_name")),
        _coerce_text(entry.get("FILE_NAME")),
        _coerce_text(entry.get("校准依据")),
        _coerce_text(entry.get("依据名称")),
    ]
    for candidate in candidates:
        code = extract_basis_code(candidate)
        if code:
            return code
    return _coerce_text(entry.get("file_code")) or _coerce_text(entry.get("FILE_CODE"))


def _candidate_texts(source: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
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
        value = source.get(key)
        if isinstance(value, (list, tuple)):
            texts.extend(_coerce_text(item) for item in value if _coerce_text(item))
        else:
            text = _coerce_text(value)
            if text:
                texts.append(text)
    # 保持顺序同时去重
    ordered: List[str] = []
    seen = set()
    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _extract_frequency_axis_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    for pattern in (
        r"(?:频率|Frequency|标准值|Reference|标称值|Nominal|值|Value)[^:：=]*[:：=]\s*([-+]?\d*\.?\d+\s*(?:THz|GHz|MHz|kHz|Hz))",
        r"([-+]?\d*\.?\d+\s*(?:THz|GHz|MHz|kHz|Hz))",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        parsed = _parse_frequency_to_hz(match.group(1))
        if parsed is not None:
            return parsed
    return None


def _extract_time_axis_from_text(text: str, *, allow_bare_numeric: bool = False) -> Optional[float]:
    if not text:
        return None

    # 避免把 Hz / kHz / MHz 等频率单位中的尾部 "h" 误识别成小时。
    if re.search(r"\b(?:THz|GHz|MHz|kHz|Hz)\b", text, flags=re.IGNORECASE):
        return None

    for pattern in (
        r"(?:标准值|Reference|标称值|Nominal|指示值|Indicated|测量值|Measured|值|Value)[^:：=]*[:：=]\s*([-+]?\d*\.?\d+\s*(?:ps|ns|us|µs|μs|ms|min|h|s)\b)",
        r"([-+]?\d*\.?\d+\s*(?:ps|ns|us|µs|μs|ms|min|h|s)\b)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        parsed, _ = parse_value_with_unit(match.group(1), keep_sign=True)
        if parsed is not None:
            return parsed

    stripped = text.strip()
    # 周期/时间表里首行常把轴值写成裸数字，单位由表头或上下文隐含。
    # 仅在明确处于时间/周期语境时接受，避免把通道号 1/2/3 误当作 1/2/3 s。
    if allow_bare_numeric and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", stripped):
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _extract_count_axis_from_text(text: str) -> Optional[float]:
    if not text:
        return None

    for pattern in (
        r"(?:计数|Count|值|Value)[^:：=]*[:：=]\s*([-+]?\d*\.?\d+)",
        r"([-+]?\d*\.?\d+)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        parsed, _ = parse_value_with_unit(match.group(1), keep_sign=True)
        if parsed is not None:
            return parsed
    return None


def _extract_axis_interval(axis_family: Optional[str], text: str) -> Optional[Tuple[float, float]]:
    if not axis_family or not text:
        return None
    if axis_family == "period_band":
        parsed = parse_range_limit(text)
        if parsed is not None:
            lower, upper = parsed
            if lower is not None and upper is not None:
                return (min(lower, upper), max(lower, upper))
        return None

    if axis_family == "frequency_band":
        parsed = _parse_frequency_range(text)
        if not parsed:
            return None
        lower, upper = parsed
        if lower is None or upper is None:
            return None
        return (min(lower, upper), max(lower, upper))
    return None


def _infer_section_group(section_label: str, param_name: str) -> str:
    text = " ".join(part for part in [section_label, param_name] if part).lower()
    if _contains_any(text, ["时基", "time base", "timebase"]):
        return "time_base"
    if _contains_any(text, ["计时", "time interval", "时间间隔", "周期", "period"]):
        return "timing"
    return "generic"


def _derive_semantic_target(
    param_semantic: ParamSemantic,
    section_group: str,
    axis_family: Optional[str],
    point_text: str,
) -> str:
    registry_target = _coerce_text(param_semantic.features.get("semantic_target"))
    if registry_target:
        return registry_target
    if section_group == "time_base" and axis_family == "frequency_band":
        return "reference_oscillator"

    if param_semantic.task_intent == "reference_check":
        return "reference_oscillator"
    if param_semantic.task_intent == "sensitivity_check":
        return "input_sensitivity"
    if param_semantic.task_intent == "noise_check":
        return "phase_noise"
    if param_semantic.task_intent == "quality_check":
        if param_semantic.primary_quantity == "cnr_consistency":
            return "cnr_consistency"
        if param_semantic.primary_quantity == "position_consistency":
            return "position_consistency"
        if param_semantic.primary_quantity == "spectral_purity":
            return "spectral_purity"
        return "modulation_quality"

    if param_semantic.primary_quantity == "period":
        if param_semantic.task_intent == "accuracy_check":
            return "period_accuracy"
        return "period_range"
    if param_semantic.primary_quantity == "count":
        return "count_accuracy"
    if param_semantic.primary_quantity == "vswr":
        return "vswr_accuracy"
    if param_semantic.primary_quantity == "impedance":
        return "impedance_accuracy"
    if param_semantic.primary_quantity == "frequency":
        if param_semantic.task_intent == "accuracy_check":
            return "frequency_accuracy"
        return "frequency_range"
    if param_semantic.primary_quantity == "power":
        return "power_accuracy"

    if section_group == "timing":
        return "period_accuracy"
    if axis_family == "frequency_band" and _contains_any(point_text, REFERENCE_OSCILLATOR_OBJECT_TOKENS):
        return "reference_oscillator"
    return "unknown"


def _normalize_parser_meta(parser_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    meta = dict(parser_meta or {})
    confidence = meta.get("section_rule_confidence", 0.0)
    try:
        meta["section_rule_confidence"] = float(confidence or 0.0)
    except (TypeError, ValueError):
        meta["section_rule_confidence"] = 0.0
    meta["section_rule"] = _coerce_text(meta.get("section_rule"))
    meta["section_hint_rule"] = _coerce_text(meta.get("section_hint_rule"))
    meta["section_alias_matched"] = _coerce_text(meta.get("section_alias_matched"))
    return meta


def _select_param_semantic(
    *,
    param_name: str,
    section_label: str,
    point_blob: str,
    cert_u: str,
    structured_fields: Dict[str, Any],
    parameter_contract: Dict[str, Any],
    parser_meta: Optional[Dict[str, Any]] = None,
) -> ParamSemantic:
    normalized_meta = _normalize_parser_meta(parser_meta)
    parser_section_rule = normalized_meta.get("section_rule", "")
    parser_section_hint = normalized_meta.get("section_hint_rule", "")
    hint_confidence = float(normalized_meta.get("section_rule_confidence", 0.0) or 0.0)
    hint_alias = normalized_meta.get("section_alias_matched", "")
    parser_target = parser_section_hint or parser_section_rule
    contract_target = _coerce_text(parameter_contract.get("semantic_target")).lower()
    contract_confidence = float(parameter_contract.get("confidence") or 0.0)
    if contract_target and contract_target != "unknown":
        hinted_semantic = build_semantic_from_target_hint(
            semantic_target=contract_target,
            section_label=section_label or param_name,
            point_text=point_blob,
            cert_u=cert_u,
            structured_fields=structured_fields,
            parameter_contract=parameter_contract,
            hint_confidence=contract_confidence,
            hint_alias="",
        )
        if hinted_semantic is not None:
            return replace(
                hinted_semantic,
                features={
                    **hinted_semantic.features,
                    "semantic_source": "parameter_contract",
                    "canonical_semantic_target": contract_target,
                    "contract_target_accepted": True,
                    "parser_hint_accepted": bool(parser_target and parser_target == contract_target),
                    "parser_hint_target": parser_target,
                    "parser_hint_alias": hint_alias,
                    "parser_hint_confidence": float(hint_confidence or 0.0),
                },
            )
    if parser_section_rule and parser_section_rule != "unknown":
        hinted_semantic = build_semantic_from_target_hint(
            semantic_target=parser_section_rule,
            section_label=section_label or param_name,
            point_text=point_blob,
            cert_u=cert_u,
            structured_fields=structured_fields,
            parameter_contract=parameter_contract,
            hint_confidence=hint_confidence,
            hint_alias=hint_alias,
        )
        if hinted_semantic is not None and bool(hinted_semantic.features.get("required_fields_ok", False)):
            return replace(
                hinted_semantic,
                features={
                    **hinted_semantic.features,
                    "semantic_source": "parser_hint",
                    "canonical_semantic_target": parser_section_rule,
                    "contract_target_accepted": False,
                    "parser_hint_accepted": True,
                },
            )

    inferred = infer_param_semantics(
        param_name or section_label,
        point_blob,
        cert_u,
        structured_fields=structured_fields,
        section_label=section_label or param_name,
        parameter_contract=parameter_contract,
    )
    if parser_section_rule and parser_section_rule != "unknown":
        return replace(
            inferred,
            features={
                **inferred.features,
                "semantic_source": "semantic_inference",
                "canonical_semantic_target": _coerce_text(inferred.features.get("semantic_target")),
                "contract_target_accepted": False,
                "parser_hint_accepted": False,
                "parser_hint_target": parser_target,
                "parser_hint_alias": hint_alias,
                "parser_hint_confidence": hint_confidence,
            },
        )
    return replace(
        inferred,
        features={
            **inferred.features,
            "semantic_source": "semantic_inference",
            "canonical_semantic_target": _coerce_text(inferred.features.get("semantic_target")),
            "contract_target_accepted": False,
        },
    )


def normalize_cert_point(
    *,
    basis_code: str = "",
    section_label: str = "",
    param_name: str,
    point_text: str,
    cert_u: str,
    measure_value: str = "",
    reference_value: str = "",
    error_value: str = "",
    point_value: str = "",
    parameter_contract: Optional[Dict[str, Any]] = None,
    parser_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[NormalizedCertPoint, ParamSemantic]:
    contract = normalize_parameter_contract(parameter_contract or {})
    measure_value = measure_value or _coerce_text(contract.get("measure_value"))
    reference_value = reference_value or _coerce_text(contract.get("reference_value"))
    error_value = error_value or _coerce_text(contract.get("error_value"))
    limit_value = _coerce_text(contract.get("limit_value"))
    point_value = point_value or _coerce_text(contract.get("item_label"))
    cert_u = cert_u or _coerce_text(contract.get("cert_u"))
    contract_condition_value = _coerce_text(contract.get("condition_value"))

    point_blob_parts = [
        f"section:{section_label}" if section_label else "",
        f"point:{point_value}" if point_value else "",
        f"measure:{measure_value}" if measure_value else "",
        f"reference:{reference_value}" if reference_value else "",
        f"error:{error_value}" if error_value else "",
        f"limit:{limit_value}" if limit_value else "",
        f"condition:{contract_condition_value}" if contract_condition_value else "",
        point_text,
    ]
    point_blob = " ".join(part for part in point_blob_parts if part).strip()
    structured_fields = {
        "measure_value": measure_value,
        "reference_value": reference_value,
        "error_value": error_value,
        "limit_value": limit_value,
        "point_value": point_value,
        "cert_u": cert_u,
    }
    param_semantic = _select_param_semantic(
        param_name=param_name,
        section_label=section_label or param_name,
        point_blob=point_blob,
        cert_u=cert_u,
        structured_fields=structured_fields,
        parameter_contract=contract,
        parser_meta=parser_meta,
    )
    section_group = _infer_section_group(section_label, param_name)

    freq_axis = None
    time_axis = None
    axis_texts = tuple(
        text for text in (contract_condition_value, measure_value, reference_value, point_value, point_text) if text
    )
    if (
        section_group == "time_base"
        or param_semantic.task_intent == "reference_check"
        or (param_semantic.primary_quantity == "period" and param_semantic.task_intent != "accuracy_check")
    ):
        axis_texts = tuple(
            text for text in (contract_condition_value, reference_value, measure_value, point_value, point_text) if text
        )
    for candidate_text in axis_texts:
        if freq_axis is None:
            freq_axis = _extract_frequency_axis_from_text(candidate_text)
        if time_axis is None:
            time_axis = _extract_time_axis_from_text(
                candidate_text,
                allow_bare_numeric=(
                    param_semantic.condition_axis == "period_band"
                    or param_semantic.primary_quantity == "period"
                    or section_group == "timing"
                ),
            )

    axis_family: Optional[str] = None
    axis_value: Optional[float] = None
    if section_group == "time_base" and freq_axis is not None:
        axis_family = "frequency_band"
        axis_value = freq_axis
    elif param_semantic.task_intent == "reference_check" and freq_axis is not None:
        axis_family = "frequency_band"
        axis_value = freq_axis
    elif param_semantic.primary_quantity == "count":
        count_axis = None
        for candidate_text in axis_texts:
            count_axis = _extract_count_axis_from_text(candidate_text)
            if count_axis is not None:
                break
        if count_axis is not None:
            axis_family = "count_axis"
            axis_value = count_axis
    elif param_semantic.condition_axis == "offset_frequency" and freq_axis is not None:
        axis_family = "offset_frequency"
        axis_value = freq_axis
    elif param_semantic.condition_axis == "period_band" or (param_semantic.primary_quantity == "period" and time_axis is not None):
        axis_family = "period_band"
        axis_value = time_axis
    elif param_semantic.condition_axis == "frequency_band" or (param_semantic.primary_quantity == "frequency" and freq_axis is not None):
        axis_family = "frequency_band"
        axis_value = freq_axis
    elif section_group == "timing" and time_axis is not None:
        axis_family = "period_band"
        axis_value = time_axis
    elif freq_axis is not None:
        axis_family = "frequency_band"
        axis_value = freq_axis
    elif time_axis is not None:
        axis_family = "period_band"
        axis_value = time_axis

    contract_target = _coerce_text(contract.get("semantic_target")).lower()
    semantic_target = contract_target or _derive_semantic_target(param_semantic, section_group, axis_family, point_blob)
    normalization_notes: List[str] = list(param_semantic.features.get("normalization_notes", ()) or ())
    required_fields_ok = bool(param_semantic.features.get("required_fields_ok", semantic_target != "unknown"))
    if semantic_target == "unknown":
        normalization_notes.append("unknown semantic")
        required_fields_ok = False
    if param_semantic.unit_family == "unknown" and semantic_target not in {
        "count_accuracy",
        "reference_oscillator",
        "modulation_quality",
        "vswr_accuracy",
        "impedance_accuracy",
    }:
        normalization_notes.append("unit family mismatch")
        required_fields_ok = False
    if semantic_target in {"frequency_accuracy", "frequency_range", "period_range", "count_accuracy"} and axis_value is None:
        normalization_notes.append("axis extraction ambiguous")
        required_fields_ok = False

    cert_point = NormalizedCertPoint(
        basis_code=extract_basis_code(basis_code) or basis_code or "",
        section_label=section_label or param_name,
        param_name=param_name,
        measure_value=measure_value,
        reference_value=reference_value,
        error_value=error_value,
        point_value=point_value,
        cert_u=cert_u,
        semantic_target=semantic_target,
        semantic_subtype=_coerce_text(param_semantic.semantic_subtype) or _coerce_text(contract.get("semantic_subtype")),
        axis_value=axis_value,
        axis_family=axis_family,
        contract_confidence=float(param_semantic.contract_confidence or contract.get("confidence") or 0.0),
        needs_disambiguation=bool(param_semantic.needs_disambiguation or contract.get("needs_disambiguation")),
        required_fields_ok=required_fields_ok,
        parameter_contract=contract,
        normalization_notes=tuple(dict.fromkeys(note for note in normalization_notes if note)),
        semantic_source=_coerce_text(param_semantic.features.get("semantic_source")),
    )
    return cert_point, param_semantic


def _normalize_candidate_band(capability: KbCapability) -> Tuple[str, Optional[float], Optional[float], Tuple[float, ...]]:
    source = capability.source or {}
    texts = _candidate_texts(source)

    if capability.capability_target == "reference_oscillator":
        points: List[float] = []
        for text in texts:
            points.extend(_parse_frequency_point_list(text))
        if points:
            deduped = tuple(sorted({float(point) for point in points}))
            return "discrete", None, None, deduped

    if capability.condition_axis == "frequency_band":
        for text in texts:
            points = _parse_frequency_point_list(text)
            if points:
                deduped = tuple(sorted({float(point) for point in points}))
                return "discrete", None, None, deduped
            parsed = _parse_frequency_range(text)
            if parsed:
                lower, upper = parsed
                if lower is not None and upper is not None:
                    return "range", min(lower, upper), max(lower, upper), tuple()

    if capability.capability_target == "count_accuracy":
        for text in texts:
            parsed = parse_range_limit(text)
            if parsed is not None:
                lower, upper = parsed
                if lower is not None and upper is not None:
                    return "range", min(lower, upper), max(lower, upper), tuple()
            single, _ = parse_value_with_unit(text, keep_sign=True)
            if single is not None and re.search(r"\d", text):
                return "range", single, single, tuple()

    if capability.condition_axis == "period_band":
        for text in texts:
            parsed = _parse_range_to_base_units(text, "time")
            if parsed is not None:
                lower, upper = parsed
                if lower is not None and upper is not None:
                    return "range", min(lower, upper), max(lower, upper), tuple()
            single, _ = parse_value_with_unit(text, keep_sign=True)
            if single is not None and re.search(r"(?:ps|ns|us|µs|μs|ms|h|s)", text, flags=re.IGNORECASE):
                return "range", single, single, tuple()

    return "none", None, None, tuple()


def normalize_kb_candidate(entry: Dict[str, Any]) -> NormalizedKbCandidate:
    capability = infer_kb_capability(entry)
    source = capability.source or entry
    measured = _coerce_text(source.get("measured") or capability.measured)
    basis_code = _entry_basis_code(source)
    measure_range_text = _coerce_text(source.get("measure_range_text") or source.get("measure_range"))
    u_text = _coerce_text(source.get("u_text")) or _coerce_text(source.get("kb_u"))
    if not u_text:
        uncertainty = source.get("uncertainty")
        if isinstance(uncertainty, dict):
            u_text = _coerce_text(uncertainty.get("value_display") or uncertainty.get("value") or uncertainty.get("raw"))
        else:
            u_text = _coerce_text(uncertainty)

    band_kind, band_lower, band_upper, discrete_points = _normalize_candidate_band(capability)
    effective_axis = capability.condition_axis
    if capability.capability_target == "reference_oscillator" and discrete_points:
        effective_axis = "frequency_band"
    if capability.capability_target == "count_accuracy":
        effective_axis = "count_axis"

    u_kind = _normalize_uncertainty_kind(u_text)
    u_interval = _normalize_uncertainty_interval(u_text, u_kind)
    candidate_id = _stable_candidate_id(basis_code, measured, measure_range_text, u_text)

    return NormalizedKbCandidate(
        candidate_id=candidate_id,
        basis_code=basis_code,
        measured=measured,
        capability_target=capability.capability_target,
        primary_quantity=capability.primary_quantity,
        result_quantity=capability.result_quantity,
        condition_axis=effective_axis,
        band_kind=band_kind,
        band_lower=band_lower,
        band_upper=band_upper,
        discrete_points=discrete_points,
        u_kind=u_kind,
        u_interval=u_interval,
        semantic_subtype=_coerce_text(capability.semantic_subtype),
        unit_family=_coerce_text(capability.unit_family) or "unknown",
        contract_confidence=float(capability.contract_confidence or 0.0),
        required_fields_ok=True,
        normalization_notes=tuple(),
        source=source,
    )


def _candidate_unit_family(candidate: NormalizedKbCandidate) -> str:
    if candidate.unit_family and candidate.unit_family != "unknown":
        return candidate.unit_family
    target = candidate.capability_target
    if target in {"frequency_accuracy", "frequency_range", "reference_oscillator"}:
        return "frequency"
    if target in {"period_accuracy", "period_range"}:
        return "time"
    if target == "count_accuracy":
        return "count"
    if target == "position_consistency":
        return "length"
    if target == "dynamic_range":
        source = candidate.source or {}
        text = " ".join(
            part
            for part in (
                _coerce_text(candidate.measured),
                _coerce_text(source.get("measure_range_text")),
                _coerce_text(source.get("raw")),
                _coerce_text(source.get("raw_block")),
            )
            if part
        ).lower()
        if any(token in text for token in ("m/s", "m/s2", "m/s3", "m/s²", "m/s³", "速度", "加速度")):
            return "motion"
        if any(token in text for token in ("伪距分辨力", "pseudorange resolution", "(0.01～0.1)m", "(0.01~0.1)m")):
            return "length"
        return "voltage_power"
    if target in {
        "input_sensitivity",
        "power_accuracy",
        "phase_noise",
        "modulation_quality",
        "spectral_purity",
        "vswr_accuracy",
        "impedance_accuracy",
        "cnr_consistency",
    }:
        return "voltage_power"
    return "unknown"


def _resolve_target_set(cert_point: NormalizedCertPoint, param_semantic: ParamSemantic) -> List[str]:
    base_targets = list(STRUCTURED_PREFILTER_TARGETS.get((param_semantic.task_intent, param_semantic.primary_quantity), set()))
    if cert_point.semantic_target == "reference_oscillator":
        return ["reference_oscillator"]
    if cert_point.semantic_target == "input_sensitivity":
        return ["input_sensitivity"]
    if cert_point.semantic_target == "count_accuracy":
        return ["count_accuracy"]
    if cert_point.semantic_target == "phase_noise":
        return ["phase_noise"]
    if cert_point.semantic_target == "modulation_quality":
        return ["modulation_quality"]
    if cert_point.semantic_target == "vswr_accuracy":
        return ["vswr_accuracy"]
    if cert_point.semantic_target == "impedance_accuracy":
        return ["impedance_accuracy"]
    if cert_point.semantic_target == "cnr_consistency":
        return ["cnr_consistency"]
    if cert_point.semantic_target == "position_consistency":
        return ["position_consistency"]
    if cert_point.semantic_target == "spectral_purity":
        return ["spectral_purity"]
    if cert_point.semantic_target == "power_accuracy":
        return ["power_accuracy"]
    if cert_point.semantic_target == "period_accuracy" and not base_targets:
        return ["period_accuracy", "period_range"]
    if cert_point.semantic_target == "count_accuracy" and not base_targets:
        return ["count_accuracy"]
    if cert_point.semantic_target == "period_range" and not base_targets:
        return ["period_range"]
    if cert_point.semantic_target == "frequency_accuracy" and not base_targets:
        return ["frequency_accuracy"]
    if cert_point.semantic_target == "frequency_range" and not base_targets:
        return ["frequency_range"]
    return base_targets or ([cert_point.semantic_target] if cert_point.semantic_target != "unknown" else [])


def _merge_candidate_target_preference(
    *,
    semantic_target: str,
    target_set: List[str],
    candidate_target_preference: str,
) -> List[str]:
    preferred_target = _coerce_text(candidate_target_preference)
    if not preferred_target or preferred_target in target_set:
        return target_set

    compatible_fallbacks = {
        "frequency_accuracy": {"frequency_range"},
        "period_accuracy": {"period_range"},
    }
    allowed_targets = compatible_fallbacks.get(_coerce_text(semantic_target), set())
    if preferred_target not in allowed_targets:
        return target_set
    return [*target_set, preferred_target]


def _period_accuracy_candidate_priority(
    cert_point: NormalizedCertPoint,
    candidate: NormalizedKbCandidate,
) -> Tuple[int, int]:
    if cert_point.semantic_target != "period_accuracy":
        return (0, 0)

    target_rank = 0 if candidate.capability_target == "period_accuracy" else 1
    measured_text = _coerce_text(candidate.measured).lower()
    period_label = _contains_any(measured_text, ["周期", "period"])
    time_interval_label = _contains_any(measured_text, ["时间间隔", "time interval"])
    if period_label and not time_interval_label:
        measured_rank = 0
    elif time_interval_label and not period_label:
        measured_rank = 1
    else:
        measured_rank = 2
    return target_rank, measured_rank


def _axis_match_score(
    cert_point: NormalizedCertPoint,
    candidate: NormalizedKbCandidate,
    point_interval: Optional[Tuple[float, float]],
) -> Tuple[Optional[int], str]:
    candidate_axis = candidate.condition_axis
    if candidate_axis and cert_point.axis_family and candidate_axis != cert_point.axis_family:
        return None, f"axis mismatch: cert={cert_point.axis_family}, kb={candidate_axis}"

    if not candidate_axis:
        return 160, "semantic match without axis"

    axis_value = cert_point.axis_value
    if candidate_axis == "count_axis":
        if axis_value is None:
            return 160, "axis missing, keep count candidate"
        lower = candidate.band_lower
        upper = candidate.band_upper
        if lower is None or upper is None:
            return 160, "count candidate without normalized bounds"
        tol = max(abs(upper - lower) * 1e-12, 1e-12)
        if lower - tol <= axis_value <= upper + tol:
            return 300, f"contains [{lower:.12g}, {upper:.12g}]"
        return 100, f"same semantic but out of range [{lower:.12g}, {upper:.12g}]"

    if candidate.band_kind == "discrete":
        if axis_value is None:
            return 160, "axis missing, keep discrete candidate"
        for point in candidate.discrete_points:
            tol = max(abs(point) * 1e-12, 1e-12)
            if abs(axis_value - point) <= tol:
                return 300, f"discrete hit @ {point:.12g}"
        return 100, "same semantic, discrete point miss"

    if candidate.band_kind == "range":
        lower = candidate.band_lower
        upper = candidate.band_upper
        if lower is None or upper is None:
            return 160, "range candidate without normalized bounds"
        tol = max(abs(upper - lower) * 1e-12, 1e-12)
        if axis_value is not None:
            if lower - tol <= axis_value <= upper + tol:
                if abs(axis_value - lower) <= tol or abs(axis_value - upper) <= tol:
                    return 280, f"boundary hit [{lower:.12g}, {upper:.12g}]"
                return 300, f"contains [{lower:.12g}, {upper:.12g}]"
            return 100, f"same semantic but out of range [{lower:.12g}, {upper:.12g}]"
        if point_interval is not None:
            interval_lower, interval_upper = point_interval
            if max(interval_lower, lower) <= min(interval_upper, upper) + tol:
                return 220, f"interval overlap [{lower:.12g}, {upper:.12g}]"
            return 100, f"same semantic but no overlap [{lower:.12g}, {upper:.12g}]"
        return 160, "axis missing, keep ranged candidate"

    return 160, "semantic match without normalized band"


def _axis_proximity(cert_point: NormalizedCertPoint, candidate: NormalizedKbCandidate) -> float:
    axis_value = cert_point.axis_value
    if axis_value is None:
        return float("inf")

    if candidate.band_kind == "discrete":
        if not candidate.discrete_points:
            return float("inf")
        return min(abs(axis_value - point) for point in candidate.discrete_points)

    if candidate.band_kind == "range":
        lower = candidate.band_lower
        upper = candidate.band_upper
        if lower is None or upper is None:
            return float("inf")
        if lower <= axis_value <= upper:
            return 0.0
        if axis_value < lower:
            return lower - axis_value
        return axis_value - upper

    return float("inf")


def _specificity(candidate: NormalizedKbCandidate) -> float:
    if candidate.band_kind == "discrete":
        return 0.0
    if candidate.band_kind == "range" and candidate.band_lower is not None and candidate.band_upper is not None:
        return max(candidate.band_upper - candidate.band_lower, 0.0)
    return float("inf")


_POWER_RANGE_UNITS = re.compile(r"(?:dbm|db|mw|uw|µw|μw|w)\b", re.IGNORECASE)


def _parse_power_probe_value(text: str) -> Optional[float]:
    raw = _coerce_text(text)
    if not raw or not _POWER_RANGE_UNITS.search(raw):
        return None
    parsed, _ = parse_value_with_unit(raw, keep_sign=True)
    return parsed


def _candidate_power_interval(candidate: NormalizedKbCandidate) -> Optional[Tuple[float, float]]:
    if candidate.result_quantity != "power_value":
        return None
    for text in _candidate_texts(candidate.source):
        raw = _coerce_text(text)
        if not raw or not _POWER_RANGE_UNITS.search(raw):
            continue
        parsed = parse_range_limit(raw)
        if parsed is None:
            continue
        lower, upper = parsed
        if lower is None or upper is None:
            continue
        return (min(lower, upper), max(lower, upper))
    return None


def _power_range_priority(cert_point: NormalizedCertPoint, candidate: NormalizedKbCandidate) -> int:
    if cert_point.semantic_target != "power_accuracy":
        return 1

    probe_value = None
    for text in (cert_point.point_value, cert_point.reference_value, cert_point.measure_value):
        probe_value = _parse_power_probe_value(text)
        if probe_value is not None:
            break
    if probe_value is None:
        return 1

    interval = _candidate_power_interval(candidate)
    if interval is None:
        return 1

    lower, upper = interval
    tol = max(abs(upper - lower) * 1e-12, 1e-12)
    return 0 if lower - tol <= probe_value <= upper + tol else 2


def _power_range_specificity(candidate: NormalizedKbCandidate) -> float:
    interval = _candidate_power_interval(candidate)
    if interval is None:
        return float("inf")
    lower, upper = interval
    return max(upper - lower, 0.0)


def _section_match_priority(cert_point: NormalizedCertPoint, candidate: NormalizedKbCandidate) -> int:
    section_group = _infer_section_group(cert_point.section_label, cert_point.param_name)
    if section_group == "time_base":
        return 0 if candidate.capability_target == "reference_oscillator" else 1
    if section_group == "timing":
        return 0 if candidate.capability_target in {"period_accuracy", "period_range"} else 1
    if cert_point.semantic_target == "count_accuracy":
        return 0 if candidate.capability_target == "count_accuracy" else 1
    return 1


def _reference_metric_priority(cert_point: NormalizedCertPoint, candidate: NormalizedKbCandidate) -> int:
    if cert_point.semantic_target not in {"reference_oscillator", "modulation_quality", "dynamic_range"}:
        return 1

    metric_match = _reference_metric_matches(cert_point, candidate)
    if metric_match is True:
        return 0
    if metric_match is False:
        return 1
    return 1


def _reference_metric_matches(cert_point: NormalizedCertPoint, candidate: NormalizedKbCandidate) -> Optional[bool]:
    section_text = " ".join(
        part for part in [cert_point.section_label, cert_point.param_name, cert_point.point_value] if _coerce_text(part)
    ).lower()
    candidate_text = " ".join(
        part
        for part in [
            _coerce_text(candidate.measured),
            _coerce_text(candidate.source.get("measure_range_text")),
            _coerce_text(candidate.source.get("measure_range")),
            _coerce_text(candidate.source.get("raw")),
        ]
        if part
    ).lower()

    if cert_point.semantic_target == "reference_oscillator":
        allow_generic_candidate = subtype_bool_option(
            cert_point.semantic_target,
            cert_point.semantic_subtype,
            "allow_generic_candidate",
            False,
        )
        metric_groups = [
            (
                ("开机特性", "warm-up", "warm up", "warm-up characteristics", "warm up characteristics"),
                ("开机特性", "warm-up", "warm up"),
            ),
            (
                ("相对频率偏差", "relative frequency deviation", "频率准确度", "frequency accuracy"),
                ("相对频率偏差", "relative frequency deviation"),
            ),
            (
                ("频率复现性", "reproducibility"),
                ("频率复现性", "reproducibility"),
            ),
            (
                (
                    "日老化率",
                    "日频率波动",
                    "日频率漂移率",
                    "aging",
                    "ageing",
                    "diurnal frequency fluctuation",
                    "daily frequency drift",
                    "daily frequency fluctuation",
                ),
                (
                    "日老化率",
                    "日频率漂移率",
                    "aging",
                    "ageing",
                    "daily frequency drift",
                    "daily frequency fluctuation",
                ),
            ),
            (
                ("短期频率稳定度", "short-term stability", "frequency stability", "频率稳定度", "1s频率稳定度", "1 s频率稳定度"),
                ("频率稳定度", "1s频率稳定度", "1 s频率稳定度", "short-term stability", "frequency stability"),
            ),
            (
                ("比对不确定度", "comparison uncertainty", "compare uncertainty"),
                ("比对不确定度", "comparison uncertainty", "compare uncertainty"),
            ),
        ]

        for section_tokens, candidate_tokens in metric_groups:
            if any(token in section_text for token in section_tokens):
                if any(token in candidate_text for token in candidate_tokens):
                    return True
                if allow_generic_candidate and candidate.capability_target == "reference_oscillator":
                    return None
                return False
        return None

    if cert_point.semantic_target == "modulation_quality":
        def _modulation_metric(text: str) -> Optional[str]:
            metric_groups = [
                ("iq_offset", ("iq offset", "iq偏移", "iq 偏移")),
                ("phase_error", ("phase error", "相位误差")),
                ("evm", ("evm", "error vector magnitude", "误差矢量幅度")),
            ]
            for metric_name, tokens in metric_groups:
                if any(token in text for token in tokens):
                    return metric_name
            return None

        cert_metric = _modulation_metric(section_text)
        if cert_metric is None:
            return None
        candidate_metric = _modulation_metric(candidate_text)
        return cert_metric == candidate_metric

    if cert_point.semantic_target == "spectral_purity":
        def _spectral_metric(text: str) -> Optional[str]:
            metric_groups = [
                ("spurious", ("杂波抑制", "非谐波抑制", "spur suppression", "spurious suppression")),
                ("harmonic", ("二次谐波", "谐波抑制", "harmonic suppression")),
            ]
            for metric_name, tokens in metric_groups:
                if any(token in text for token in tokens):
                    return metric_name
            return None

        cert_metric = _spectral_metric(section_text)
        if cert_metric is None:
            return None
        candidate_metric = _spectral_metric(candidate_text)
        return cert_metric == candidate_metric

    if cert_point.semantic_target == "dynamic_range":
        def _dynamic_metric(text: str) -> Optional[str]:
            metric_groups = [
                ("power", ("功率动态范围", "power dynamic range")),
                ("pseudorange", ("伪距分辨力", "pseudorange resolution")),
                ("pseudorange_rate", ("伪距率分辨力", "pseudorange rate resolution")),
                ("jerk", ("加加速度", "stacking velocity", "jerk")),
                ("acceleration", ("加速度", "accelerated speed", "acceleration")),
                ("speed", ("速度", "speed", "velocity")),
            ]
            for metric_name, tokens in metric_groups:
                if any(token in text for token in tokens):
                    return metric_name
            return None

        cert_metric = _dynamic_metric(section_text)
        if cert_metric is None:
            return None
        candidate_metric = _dynamic_metric(candidate_text)
        return cert_metric == candidate_metric
    return None


def _same_basis_gap_rationale(
    cert_point: NormalizedCertPoint,
    basis_candidates: List[NormalizedKbCandidate],
) -> str:
    semantic_target = _coerce_text(cert_point.semantic_target)
    semantic_subtype = _coerce_text(cert_point.semantic_subtype)
    if semantic_target == "modulation_quality" and semantic_subtype in {"phase_error", "iq_offset"}:
        same_target_candidates = [
            candidate for candidate in basis_candidates if candidate.capability_target == "modulation_quality"
        ]
        if same_target_candidates and not any(candidate.semantic_subtype == semantic_subtype for candidate in same_target_candidates):
            return f"same basis missing kb subtype: {semantic_subtype}"
    if semantic_target == "dynamic_range" and semantic_subtype == "power_dynamic_range":
        same_target_candidates = [
            candidate for candidate in basis_candidates if candidate.capability_target == "dynamic_range"
        ]
        if same_target_candidates and not any(candidate.semantic_subtype == semantic_subtype for candidate in same_target_candidates):
            return "same basis missing kb subtype: power_dynamic_range"
    return "same basis but no compatible candidate"


def select_kb_candidates(
    cert_point: NormalizedCertPoint,
    param_semantic: ParamSemantic,
    kb_entries: List[Dict[str, Any]],
    *,
    candidate_target_preference: str = "",
) -> SelectorOutcome:
    target_set = _merge_candidate_target_preference(
        semantic_target=cert_point.semantic_target,
        target_set=_resolve_target_set(cert_point, param_semantic),
        candidate_target_preference=candidate_target_preference,
    )
    all_candidates = [normalize_kb_candidate(entry) for entry in kb_entries]
    candidate_reasons: Dict[str, str] = {}

    basis_code_norm = norm_code(cert_point.basis_code) if cert_point.basis_code else ""
    basis_candidates: List[NormalizedKbCandidate] = []
    if basis_code_norm:
        for candidate in all_candidates:
            candidate_code_norm = norm_code(candidate.basis_code) if candidate.basis_code else ""
            if candidate_code_norm == basis_code_norm:
                basis_candidates.append(candidate)
            else:
                candidate_reasons[candidate.candidate_id] = f"basis mismatch: {candidate.basis_code or 'N/A'}"
    else:
        basis_candidates = all_candidates[:]

    notes = list(cert_point.normalization_notes or ())

    def _primary_note() -> str:
        priority = [
            "unknown semantic",
            "unit family mismatch",
            "missing required fields",
            "column requirements not satisfied",
            "axis extraction ambiguous",
        ]
        for token in priority:
            for note in notes:
                if token in note:
                    return note
        return notes[0] if notes else "required fields missing"

    if cert_point.semantic_target == "unknown":
        rationale = "unknown semantic"
        return SelectorOutcome(
            cert_point=cert_point,
            param_semantic=param_semantic,
            basis_candidates=basis_candidates,
            filtered_candidates=[],
            ranked_candidates=[],
            selected_candidate=None,
            candidate_reasons=candidate_reasons,
            rationale=rationale,
        )
    if not cert_point.required_fields_ok:
        rationale = _primary_note()
        return SelectorOutcome(
            cert_point=cert_point,
            param_semantic=param_semantic,
            basis_candidates=basis_candidates,
            filtered_candidates=[],
            ranked_candidates=[],
            selected_candidate=None,
            candidate_reasons=candidate_reasons,
            rationale=rationale,
        )

    filtered_candidates: List[NormalizedKbCandidate] = []
    cert_subtype = _coerce_text(cert_point.semantic_subtype or param_semantic.semantic_subtype)
    target_preference = _coerce_text(candidate_target_preference)
    for candidate in basis_candidates:
        if target_set and candidate.capability_target not in target_set:
            candidate_reasons[candidate.candidate_id] = f"target mismatch: {candidate.capability_target} not in {target_set}"
            continue
        cert_unit_family = param_semantic.unit_family or "unknown"
        candidate_unit_family = _candidate_unit_family(candidate)
        if cert_subtype and candidate.semantic_subtype and candidate.semantic_subtype != cert_subtype:
            candidate_reasons[candidate.candidate_id] = (
                f"semantic subtype mismatch: cert={cert_subtype}, kb={candidate.semantic_subtype}"
            )
            continue
        allowed_families = subtype_allowed_unit_families(cert_point.semantic_target, cert_subtype) if cert_subtype else set()
        if allowed_families and candidate_unit_family not in {"unknown", *allowed_families}:
            candidate_reasons[candidate.candidate_id] = (
                f"unit family mismatch: cert_subtype={cert_subtype}, kb={candidate_unit_family}"
            )
            continue
        if (
            cert_unit_family not in {"unknown", "count"}
            and candidate_unit_family not in {"unknown", cert_unit_family}
        ):
            candidate_reasons[candidate.candidate_id] = (
                f"unit family mismatch: cert={cert_unit_family}, kb={candidate_unit_family}"
            )
            continue
        metric_match = _reference_metric_matches(cert_point, candidate)
        if metric_match is False:
            candidate_reasons[candidate.candidate_id] = "reference metric mismatch"
            continue
        filtered_candidates.append(candidate)

    point_interval = None
    for interval_text in (cert_point.measure_value, cert_point.reference_value, cert_point.section_label):
        point_interval = _extract_axis_interval(cert_point.axis_family, interval_text)
        if point_interval is not None:
            break

    scored: List[Tuple[Tuple[int, int, int, float, float, int, int, str], NormalizedKbCandidate, str]] = []
    for candidate in filtered_candidates:
        axis_score, axis_reason = _axis_match_score(cert_point, candidate, point_interval)
        if axis_score is None:
            candidate_reasons[candidate.candidate_id] = axis_reason
            continue
        candidate_reasons[candidate.candidate_id] = axis_reason
        period_target_rank, period_measured_rank = _period_accuracy_candidate_priority(cert_point, candidate)
        discrete_rank = 0 if candidate.band_kind == "discrete" else 1
        subtype_rank = 0 if cert_subtype and candidate.semantic_subtype == cert_subtype else 1
        target_preference_rank = 0 if target_preference and candidate.capability_target == target_preference else 1
        tie_break = (
            period_target_rank,
            period_measured_rank,
            subtype_rank,
            target_preference_rank,
            -axis_score,
            _reference_metric_priority(cert_point, candidate),
            _axis_proximity(cert_point, candidate),
            _power_range_priority(cert_point, candidate),
            _power_range_specificity(candidate),
            _specificity(candidate),
            discrete_rank,
            _section_match_priority(cert_point, candidate),
            candidate.candidate_id,
        )
        scored.append((tie_break, candidate, axis_reason))

    scored.sort(key=lambda item: item[0])
    ranked_candidates = [candidate for _, candidate, _ in scored]
    selected_candidate = ranked_candidates[0] if ranked_candidates else None
    used_fallback_candidate_target = bool(
        selected_candidate
        and cert_point.semantic_target
        and selected_candidate.capability_target
        and selected_candidate.capability_target != cert_point.semantic_target
    )
    selected_target_relation = (
        "fallback_cross_target"
        if used_fallback_candidate_target
        else ("exact" if selected_candidate is not None else "")
    )

    if selected_candidate is not None:
        rationale = f"selected {selected_candidate.candidate_id}: {candidate_reasons.get(selected_candidate.candidate_id, '')}"
    elif basis_candidates and filtered_candidates:
        if any("axis extraction ambiguous" in note for note in notes):
            rationale = "axis extraction ambiguous"
        else:
            rationale = _same_basis_gap_rationale(cert_point, basis_candidates)
    elif basis_candidates:
        rationale = _same_basis_gap_rationale(cert_point, basis_candidates)
    else:
        rationale = "no candidates for basis code"

    return SelectorOutcome(
        cert_point=cert_point,
        param_semantic=param_semantic,
        basis_candidates=basis_candidates,
        filtered_candidates=filtered_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate=selected_candidate,
        candidate_reasons=candidate_reasons,
        rationale=rationale,
        used_fallback_candidate_target=used_fallback_candidate_target,
        selected_target_relation=selected_target_relation,
    )
