#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parameter contract helpers for stage-1 parser/selector refactor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .rules import (
    FREQUENCY_UNIT_PATTERN,
    LENGTH_UNIT_PATTERN,
    MOTION_UNIT_PATTERN,
    PERIOD_ACCURACY_SECTION_ALIASES,
    REFERENCE_OSCILLATOR_METRIC_TOKENS,
    REFERENCE_OSCILLATOR_OBJECT_TOKENS,
    TIME_UNIT_PATTERN,
    VOLT_POWER_UNIT_PATTERN,
)


PARAMETER_CONTRACT_SCHEMA_VERSION = 2

FREQ_UNITS = re.compile(FREQUENCY_UNIT_PATTERN, re.IGNORECASE)
TIME_UNITS = re.compile(TIME_UNIT_PATTERN, re.IGNORECASE)
VOLT_POWER_UNITS = re.compile(VOLT_POWER_UNIT_PATTERN, re.IGNORECASE)
MOTION_UNITS = re.compile(MOTION_UNIT_PATTERN, re.IGNORECASE)
LENGTH_UNITS = re.compile(LENGTH_UNIT_PATTERN, re.IGNORECASE)
_REFERENCE_OSCILLATOR_FIXED_POINTS_HZ = (1e6, 2e6, 5e6, 10e6)


def _has_strong_voltage_power_units(text: str) -> bool:
    lowered = _coerce_text(text).lower()
    if not lowered:
        return False
    return bool(
        re.search(
            r"(?:dbc/hz|db/hz|dbm|dbc\b|db\b|vpp|vrms|\b(?:uv|mv|kv|v|ua|ma|a|mw|kw|w)\b)",
            lowered,
            flags=re.IGNORECASE,
        )
    )


@dataclass(frozen=True)
class ParameterContractV2:
    schema_version: int = PARAMETER_CONTRACT_SCHEMA_VERSION
    row_shape: str = ""
    semantic_target: str = ""
    semantic_subtype: str = ""
    item_label: str = ""
    condition_axis: str = ""
    condition_value: str = ""
    nominal_value: str = ""
    reference_value: str = ""
    measure_value: str = ""
    error_value: str = ""
    limit_value: str = ""
    cert_u: str = ""
    unit_family: str = "unknown"
    source_headers: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    needs_disambiguation: bool = False


SUBTYPE_REGISTRY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "frequency_accuracy": {
        "carrier_frequency_error": {
            "text_aliases": ("载波频率偏差", "carrier frequency deviation", "rf cw frequency", "载波频率"),
            "kb_aliases": ("载波频率偏差", "carrier frequency deviation", "carrier_frequency_deviation"),
            "allowed_unit_families": {"frequency"},
            "range_probe_role": "error_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "agent_eligible": False,
        },
        "timebase_accuracy": {
            "text_aliases": ("时基准确度", "timebase accuracy", "reference frequency"),
            "kb_aliases": ("时基准确度", "timebase accuracy", "reference frequency"),
            "allowed_unit_families": {"frequency"},
            "range_probe_role": "error_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "agent_eligible": False,
        },
    },
    "period_accuracy": {
        "output_time_interval": {
            "text_aliases": (
                "输出时间间隔",
                "output time interval",
                "秒表功能输出时间间隔",
                "电秒表输出时间间隔",
            ),
            "kb_aliases": (
                "输出时间间隔",
                "output time interval",
            ),
            "allowed_unit_families": {"time", "unknown"},
            "range_probe_role": "reference_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "reference_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "limit_error",
            "agent_eligible": False,
        },
        "__default__": {
            "text_aliases": (),
            "kb_aliases": (),
            "allowed_unit_families": {"time", "unknown"},
            "range_probe_role": "reference_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "reference_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "limit_error",
            "agent_eligible": False,
        },
    },
    "period_range": {
        "__default__": {
            "text_aliases": (),
            "kb_aliases": (),
            "allowed_unit_families": {"time", "unknown"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
    },
    "input_sensitivity": {
        "__default__": {
            "text_aliases": (
                "输入灵敏度",
                "trigger sensitivity",
                "input sensitivity",
                "频率测量范围及灵敏度",
                "周期测量范围及灵敏度",
            ),
            "kb_aliases": (
                "输入灵敏度",
                "trigger sensitivity",
                "input sensitivity",
                "frequency measurement range and input sensitivity",
                "period measurement range and input sensitivity",
            ),
            "allowed_unit_families": {"voltage_power", "unknown"},
            "range_probe_role": "measure_value",
            "error_probe_role": "limit_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "threshold_measure",
            "uncertainty_policy": "representation_sensitive_skip",
            "agent_eligible": False,
        },
    },
    "dynamic_range": {
        "power_dynamic_range": {
            "text_aliases": ("功率动态范围", "power dynamic range"),
            "kb_aliases": ("功率动态范围", "power dynamic range"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
        "speed_dynamic_range": {
            "text_aliases": ("速度动态范围", "速度", "speed", "velocity"),
            "kb_aliases": ("速度动态范围",),
            "allowed_unit_families": {"motion"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
        "acceleration_dynamic_range": {
            "text_aliases": ("加速度动态范围", "加速度", "acceleration", "accelerated speed"),
            "kb_aliases": ("加速度动态范围",),
            "allowed_unit_families": {"motion"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
        "jerk_dynamic_range": {
            "text_aliases": ("加加速度动态范围", "加加速度", "jerk", "stacking velocity"),
            "kb_aliases": ("加加速度动态范围",),
            "allowed_unit_families": {"motion"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
        "pseudorange_resolution": {
            "text_aliases": ("伪距分辨力", "pseudorange resolution"),
            "kb_aliases": ("伪距分辨力", "pseudorange resolution"),
            "allowed_unit_families": {"length"},
            "range_probe_role": "error_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_error",
            "agent_eligible": False,
        },
        "pseudorange_rate_resolution": {
            "text_aliases": ("伪距率分辨力", "pseudorange rate resolution"),
            "kb_aliases": ("伪距率分辨力", "pseudorange rate resolution"),
            "allowed_unit_families": {"motion"},
            "range_probe_role": "error_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_error",
            "agent_eligible": False,
        },
    },
    "modulation_quality": {
        "evm": {
            "text_aliases": ("evm", "error vector magnitude", "误差矢量幅度"),
            "kb_aliases": ("evm", "error vector magnitude", "误差矢量幅度"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "measure_value",
            "error_probe_role": "measure_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": True,
        },
        "phase_error": {
            "text_aliases": ("phase error", "相位误差"),
            "kb_aliases": ("phase error", "相位误差"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "measure_value",
            "error_probe_role": "measure_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "limit_measure",
            "agent_eligible": True,
        },
        "iq_offset": {
            "text_aliases": ("iq offset", "iq偏移"),
            "kb_aliases": ("iq offset", "iq偏移"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "measure_value",
            "error_probe_role": "measure_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "measure_only",
            "agent_eligible": True,
        },
    },
    "reference_oscillator": {
        "timebase_accuracy": {
            "text_aliases": ("时基准确度", "timebase accuracy", "reference frequency"),
            "kb_aliases": ("时基准确度", "timebase accuracy"),
            "allowed_unit_families": {"frequency"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
        "frequency_stability": {
            "text_aliases": ("频率稳定度", "短期频率稳定度", "frequency stability", "short-term stability", "1s stability"),
            "kb_aliases": ("频率稳定度", "short-term stability", "frequency stability"),
            "allowed_unit_families": {"frequency", "unknown"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
        "comparison_uncertainty": {
            "text_aliases": ("比对不确定度", "comparison uncertainty", "compare uncertainty"),
            "kb_aliases": ("比对不确定度", "comparison uncertainty", "compare uncertainty"),
            "allowed_unit_families": {"frequency", "unknown"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
        "relative_frequency_deviation": {
            "text_aliases": ("相对频率偏差", "relative frequency deviation", "频率准确度", "frequency accuracy"),
            "kb_aliases": ("相对频率偏差", "relative frequency deviation"),
            "allowed_unit_families": {"frequency", "unknown"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
        "warmup_characteristics": {
            "text_aliases": ("开机特性", "warm-up characteristics", "warm up characteristics", "warm-up"),
            "kb_aliases": ("开机特性", "warm-up characteristics"),
            "allowed_unit_families": {"frequency", "unknown"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
        "aging_rate": {
            "text_aliases": (
                "日老化率",
                "日频率波动",
                "日频率漂移率",
                "aging rate",
                "aging",
                "ageing",
                "diurnal frequency fluctuation",
                "daily frequency drift",
                "daily frequency fluctuation",
            ),
            "kb_aliases": (
                "日老化率",
                "日频率漂移率",
                "aging",
                "daily frequency drift",
                "daily frequency fluctuation",
            ),
            "allowed_unit_families": {"frequency", "unknown"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
        "frequency_reproducibility": {
            "text_aliases": ("频率复现性", "frequency reproducibility", "reproducibility"),
            "kb_aliases": ("频率复现性", "reproducibility"),
            "allowed_unit_families": {"frequency", "unknown"},
            "range_probe_role": "condition_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "reference_metric",
            "allow_generic_candidate": True,
            "agent_eligible": False,
        },
    },
    "power_accuracy": {
        "power_resolution": {
            "text_aliases": ("功率分辨力", "power resolution", "resolution step"),
            "kb_aliases": ("功率分辨力", "power resolution"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
        "power_error": {
            "text_aliases": ("功率偏差", "power deviation", "power accuracy"),
            "kb_aliases": ("功率偏差", "power deviation", "power accuracy"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "error_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "error_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "limit_error",
            "agent_eligible": False,
        },
        "power_range": {
            "text_aliases": ("功率范围", "power range", "功率电平", "power level", "电平"),
            "kb_aliases": ("功率范围", "power range", "功率电平", "power level"),
            "allowed_unit_families": {"voltage_power"},
            "range_probe_role": "measure_value",
            "error_probe_role": "error_value",
            "uncertainty_probe_role": "measure_value",
            "axis_probe_role": "condition_value",
            "comparison_mode": "range_measure",
            "agent_eligible": False,
        },
    },
}


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_key(text: Any) -> str:
    return re.sub(r"[\s_:/()（）-]+", "", _coerce_text(text).lower())


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    lowered = _coerce_text(text).lower()
    return any(token.lower() in lowered for token in tokens)


def _extract_frequency_point_hz(text: str) -> Optional[float]:
    raw = _coerce_text(text)
    if not raw:
        return None
    match = re.search(r"([-+]?\d*\.?\d+)\s*(THz|GHz|MHz|kHz|Hz)\b", raw, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = match.group(2).lower()
    scale = {
        "thz": 1e12,
        "ghz": 1e9,
        "mhz": 1e6,
        "khz": 1e3,
        "hz": 1.0,
    }.get(unit)
    if scale is None:
        return None
    return value * scale


def _is_reference_oscillator_fixed_frequency(text: str) -> bool:
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
    project_title: str,
    item_label: str,
    unit_family: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() != "frequency":
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(title_context, ("频率准确度", "frequency accuracy")):
        return False
    if _contains_any_text(title_context, ("frequency measurement error", "频率测量误差", "frequency error", "频率误差")):
        return False
    if not error_value or not cert_u:
        return False
    if FREQ_UNITS.search(error_value) or FREQ_UNITS.search(cert_u):
        return False
    if limit_value and FREQ_UNITS.search(limit_value):
        return False
    frequency_anchor = next(
        (
            value
            for value in (nominal_value, reference_value, measure_value)
            if _is_reference_oscillator_fixed_frequency(value)
        ),
        "",
    )
    return bool(frequency_anchor)


_LIMIT_LIKE_HEADER_KEYS = {
    _normalize_key("limit"),
    _normalize_key("允许误差"),
    _normalize_key("允许范围"),
    _normalize_key("误差限值"),
}


def parameter_contract_schema_version() -> int:
    return PARAMETER_CONTRACT_SCHEMA_VERSION


def empty_parameter_contract() -> Dict[str, Any]:
    return asdict(ParameterContractV2())


def normalize_parameter_contract(raw: Any) -> Dict[str, Any]:
    payload = empty_parameter_contract()
    if isinstance(raw, Mapping):
        for key in payload:
            if key == "source_headers":
                value = raw.get(key)
                if isinstance(value, Mapping):
                    payload[key] = {str(k): _coerce_text(v) for k, v in value.items() if _coerce_text(v)}
                continue
            if key == "needs_disambiguation":
                payload[key] = bool(raw.get(key))
                continue
            if key == "confidence":
                try:
                    payload[key] = float(raw.get(key) or 0.0)
                except (TypeError, ValueError):
                    payload[key] = 0.0
                continue
            if key == "schema_version":
                try:
                    payload[key] = int(raw.get(key) or PARAMETER_CONTRACT_SCHEMA_VERSION)
                except (TypeError, ValueError):
                    payload[key] = PARAMETER_CONTRACT_SCHEMA_VERSION
                continue
            payload[key] = _coerce_text(raw.get(key))
    payload["schema_version"] = PARAMETER_CONTRACT_SCHEMA_VERSION
    return payload


def contract_source_value(contract: Mapping[str, Any], field_name: str) -> str:
    if not isinstance(contract, Mapping):
        return ""
    return _coerce_text(contract.get(field_name))


def contract_source_header(contract: Mapping[str, Any], field_name: str) -> str:
    headers = contract.get("source_headers") if isinstance(contract, Mapping) else {}
    if not isinstance(headers, Mapping):
        return ""
    return _coerce_text(headers.get(field_name))


def subtype_spec(semantic_target: str, semantic_subtype: str) -> Dict[str, Any]:
    target_specs = SUBTYPE_REGISTRY.get(_coerce_text(semantic_target), {})
    subtype_key = _coerce_text(semantic_subtype)
    if subtype_key and subtype_key in target_specs:
        return dict(target_specs.get(subtype_key, {}))
    if "__default__" in target_specs:
        return dict(target_specs.get("__default__", {}))
    return {}


def subtype_probe_role(semantic_target: str, semantic_subtype: str, role_name: str, default_role: str) -> str:
    spec = subtype_spec(semantic_target, semantic_subtype)
    return _coerce_text(spec.get(role_name)) or default_role


def subtype_comparison_mode(semantic_target: str, semantic_subtype: str, default_mode: str = "") -> str:
    spec = subtype_spec(semantic_target, semantic_subtype)
    return _coerce_text(spec.get("comparison_mode")) or default_mode


def subtype_allowed_unit_families(semantic_target: str, semantic_subtype: str) -> set[str]:
    spec = subtype_spec(semantic_target, semantic_subtype)
    allowed = spec.get("allowed_unit_families")
    if isinstance(allowed, set):
        return set(allowed)
    if isinstance(allowed, (list, tuple)):
        return {str(item) for item in allowed if str(item)}
    return set()


def subtype_agent_eligible(semantic_target: str, semantic_subtype: str) -> bool:
    spec = subtype_spec(semantic_target, semantic_subtype)
    return bool(spec.get("agent_eligible"))


def subtype_text_option(semantic_target: str, semantic_subtype: str, option_name: str, default_value: str = "") -> str:
    spec = subtype_spec(semantic_target, semantic_subtype)
    return _coerce_text(spec.get(option_name)) or default_value


def subtype_bool_option(semantic_target: str, semantic_subtype: str, option_name: str, default_value: bool = False) -> bool:
    spec = subtype_spec(semantic_target, semantic_subtype)
    if option_name not in spec:
        return default_value
    return bool(spec.get(option_name))


def infer_contract_unit_family(values: Sequence[str]) -> str:
    families = set()
    strong_voltage_power = False
    for raw in values:
        lowered = _coerce_text(raw).lower()
        if not lowered:
            continue
        is_motion = bool(MOTION_UNITS.search(lowered))
        has_impedance_unit = "ω" in lowered or "ohm" in lowered
        is_length = bool(LENGTH_UNITS.search(lowered)) and not is_motion and not has_impedance_unit
        if is_motion:
            families.add("motion")
        if is_length:
            families.add("length")
        if "dbc/hz" in lowered or "db/hz" in lowered:
            families.add("voltage_power")
        if FREQ_UNITS.search(lowered):
            families.add("frequency")
        if TIME_UNITS.search(lowered) and not is_motion:
            families.add("time")
        if VOLT_POWER_UNITS.search(lowered):
            families.add("voltage_power")
            if _has_strong_voltage_power_units(lowered):
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
    return "unknown"


def _target_from_section_rule(section_rule: str) -> str:
    lowered = _coerce_text(section_rule).lower()
    if lowered in {"dynamic_range", "modulation_quality", "reference_oscillator"}:
        return lowered
    return lowered


def _contains_any_text(text: str, tokens: Sequence[str]) -> bool:
    lowered = _coerce_text(text).lower()
    return any(_coerce_text(token).lower() in lowered for token in tokens if _coerce_text(token))


def _looks_like_accuracy_row_shape(
    *,
    row_shape: str,
    error_value: str,
    cert_u: str,
) -> bool:
    if not error_value or not cert_u:
        return False
    return row_shape in {"nominal_reference_error_u", "item_nominal_reference_error_u", "generic_structured_row"}


def _looks_like_reference_oscillator_context(
    *,
    project_title: str,
    item_label: str,
    section_rule: str,
) -> bool:
    if _coerce_text(section_rule).lower() == "reference_oscillator":
        return True
    context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if _contains_any_text(context, ("diurnal frequency fluctuation", "日频率波动")):
        return True
    return _contains_any_text(context, REFERENCE_OSCILLATOR_OBJECT_TOKENS) and _contains_any_text(
        context,
        REFERENCE_OSCILLATOR_METRIC_TOKENS,
    )


def _looks_like_input_sensitivity_context(
    *,
    project_title: str,
    item_label: str,
    section_rule: str,
    unit_family: str,
    condition_axis: str,
) -> bool:
    if _coerce_text(section_rule).lower() == "input_sensitivity":
        return True
    if _coerce_text(unit_family).lower() not in {"voltage_power", "unknown"}:
        return False
    if _coerce_text(condition_axis).lower() not in {"carrier_frequency", "period_band", "frequency_band", "gate_time"}:
        return False
    context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    return _contains_any_text(context, ("input sensitivity", "trigger sensitivity", "灵敏度", "敏度", "触发"))


def _looks_like_output_time_interval_accuracy(
    *,
    project_title: str,
    section_rule: str,
    row_shape: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
    unit_family: str,
) -> bool:
    if _coerce_text(section_rule).lower() != "period_range":
        return False
    if _coerce_text(unit_family).lower() != "time":
        return False
    if not error_value or not cert_u:
        return False

    title_lower = _coerce_text(project_title).lower()
    if "output time interval" not in title_lower and "输出时间间隔" not in title_lower:
        return False

    if row_shape in {"nominal_reference_error_u", "item_nominal_reference_error_u"}:
        return bool(reference_value and (nominal_value or limit_value or not measure_value))

    # Some real JJG601 rows occasionally drop the nominal column but still keep
    # a pure accuracy shape: reference + error + limit/U without a measure slot.
    if row_shape == "generic_structured_row":
        return bool(reference_value and limit_value and not measure_value)

    return False


def _looks_like_power_accuracy_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    measure_value: str,
    reference_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() not in {"voltage_power", "unknown"}:
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "amplitude measurement accuracy",
            "amplitude accuracy",
            "output amplitude",
            "pulse output amplitude",
            "pulse amplitude",
            "sine wave amplitude",
            "square wave amplitude",
            "triangle wave amplitude",
            "ramp wave amplitude",
            "amplitude flatness",
            "flatness",
            "dc offset accuracy",
            "dc offset",
            "offset accuracy",
            "gain",
            "maximum output power",
            "power linearity",
            "noise factor",
            "playback signal power level",
            "calibration signal",
            "幅度测量准确度",
            "幅度准确度",
            "输出幅度",
            "脉冲输出幅度",
            "脉冲幅度",
            "正弦波输出幅度",
            "方波输出幅度",
            "三角波输出幅度",
            "斜波输出幅度",
            "幅度平坦度",
            "平坦度",
            "直流偏置准确度",
            "直流偏置",
            "偏置准确度",
            "增益",
            "最大输出功率",
            "功率线性度",
            "噪声系数",
            "回放信号功率电平",
            "校准信号",
        ),
    ):
        return False
    if error_value and cert_u and (reference_value or measure_value):
        return True
    if measure_value and limit_value and cert_u:
        return True
    if cert_u and _contains_any_text(title_context, ("amplitude flatness", "flatness", "power linearity", "noise factor", "幅度平坦度", "平坦度", "功率线性度", "噪声系数")):
        return True
    if cert_u and _contains_any_text(project_title, ("calibration signal", "校准信号")) and _contains_any_text(item_label, ("amplitude", "幅度")):
        return True
    if measure_value and cert_u and _contains_any_text(title_context, ("maximum output power", "最大输出功率")):
        return True
    return False


def _looks_like_period_accuracy_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    cert_u: str,
) -> bool:
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    duty_cycle_context = _contains_any_text(title_context, ("duty cycle", "占空比"))
    allowed_families = {"time"}
    if duty_cycle_context:
        allowed_families.update({"voltage_power", "unknown"})
    if _coerce_text(unit_family).lower() not in allowed_families:
        return False
    if not _contains_any_text(
        title_context,
        (
            "time measurement accuracy",
            "delta time measurement accuracy",
            "pulse period",
            "pulse width",
            "single pulse width",
            "continuous pulse width",
            "rising edge delay time",
            "falling edge delay time",
            "time interval between two single pulses",
            "pulse repetition period",
            "duty cycle",
            "时间测量准确度",
            "△t时间测量准确度",
            "脉冲周期",
            "连续脉冲周期",
            "脉冲宽度",
            "单脉冲宽度",
            "连续脉冲宽度",
            "上升沿延迟时间",
            "下降沿延迟时间",
            "两个单脉冲间的时间间隔",
            "占空比",
        ),
    ):
        return False
    if error_value and cert_u and (reference_value or measure_value or nominal_value):
        return True
    if measure_value and cert_u:
        return True
    return False


def _looks_like_generic_time_accuracy_context(
    *,
    project_title: str,
    section_rule: str,
    row_shape: str,
    unit_family: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
) -> bool:
    if row_shape not in {"nominal_reference_error_u", "item_nominal_reference_error_u", "generic_structured_row"}:
        return False
    if _coerce_text(unit_family).lower() != "time":
        return False
    if not error_value or not cert_u:
        return False

    title_context = _coerce_text(project_title).lower()
    if any(token in title_context for token in ("time interval", "时间间隔", "pulse width", "脉冲宽度", "周期测量")):
        return False

    generic_time_title = any(
        token in title_context
        for token in (
            "time accuracy",
            "计时准确度",
            "时间准确度",
            "2 时间(time)",
            "3 时间(time)",
            "时间(time)",
            "time(delayed)",
            "time (delayed)",
        )
    )
    if not generic_time_title and _coerce_text(section_rule).lower() != "period_range":
        return False

    has_accuracy_fields = bool(nominal_value and reference_value and limit_value)
    if has_accuracy_fields and not measure_value:
        return True
    if nominal_value and reference_value and not measure_value:
        return True
    return False


def _looks_like_frequency_accuracy_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() != "frequency":
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "frequency accuracy",
            "frequency measurement accuracy",
            "frequency measurement error",
            "frequency error",
            "frequency deviation",
            "output frequency",
            "oscillator frequency",
            "time base accuracy",
            "play back the signal frequency",
            "playback signal frequency",
            "maximum input frequency offset",
            "calibration signal",
            "频率准确度",
            "频率测量准确度",
            "频率测量误差",
            "频率误差",
            "频率偏差",
            "输出频率",
            "振荡器频率",
            "回放信号频率",
            "最大输入频差",
            "校准信号",
            "时基准确度",
        ),
    ):
        return False
    if error_value and cert_u and (reference_value or measure_value or nominal_value):
        return True
    if cert_u and _contains_any_text(project_title, ("calibration signal", "校准信号")) and _contains_any_text(item_label, ("frequency", "频率")):
        return True
    return False


def _looks_like_frequency_range_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    reference_value: str,
    measure_value: str,
    limit_value: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() != "frequency":
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "frequency range",
            "frequency bandwidth",
            "acquisition bandwidth",
            "bandwidth",
            "频率范围",
            "频带宽度",
            "捕获带宽",
            "带宽",
        ),
    ):
        return False
    return bool(reference_value or measure_value or limit_value or cert_u)


def _looks_like_count_accuracy_context(
    *,
    project_title: str,
    item_label: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    cert_u: str,
) -> bool:
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "number of receiving channels",
            "receiving channels",
            "channel count",
            "count accuracy",
            "接收通道数",
            "通道数",
            "计数准确度",
            "计数准确",
            "计数精度",
        ),
    ):
        return False
    return bool(reference_value or measure_value or error_value or cert_u)


def _looks_like_vswr_accuracy_context(
    *,
    project_title: str,
    item_label: str,
    cert_u: str,
) -> bool:
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "input voltage standing wave ratio",
            "standing wave ratio",
            "vswr",
            "输入端电压驻波比",
            "驻波比",
        ),
    ):
        return False
    return bool(cert_u)


def _looks_like_impedance_accuracy_context(
    *,
    project_title: str,
    item_label: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
) -> bool:
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(title_context, ("input impedance", "impedance", "输入阻抗", "阻抗")):
        return False
    return bool(cert_u and ((reference_value and error_value) or (measure_value and limit_value)))


def _looks_like_cnr_consistency_context(
    *,
    project_title: str,
    item_label: str,
    cert_u: str,
) -> bool:
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "consistency of carrier to noise ratio",
            "carrier to noise ratio deviation",
            "carrier to noise ratio consistency",
            "载噪比一致性",
            "载噪比偏差",
        ),
    ):
        return False
    return bool(cert_u)


def _looks_like_position_consistency_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() not in {"length", "unknown"}:
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "location consistency",
            "playback deviation",
            "position consistency",
            "定位一致性",
            "回放偏差",
        ),
    ):
        return False
    return bool(cert_u)


def _looks_like_dynamic_range_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() not in {"voltage_power", "motion", "length", "unknown"}:
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "range of input power for signal acquisition",
            "input power range",
            "dynamic range",
            "采集信号输入功率范围",
            "动态范围",
        ),
    ):
        return False
    return bool(cert_u)


def _looks_like_spectral_purity_context(
    *,
    project_title: str,
    item_label: str,
    unit_family: str,
    cert_u: str,
) -> bool:
    if _coerce_text(unit_family).lower() not in {"voltage_power", "unknown"}:
        return False
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))
    if not _contains_any_text(
        title_context,
        (
            "spectral purity",
            "out of band rejection",
            "in band spurious",
            "信号纯度",
            "带外抑制",
            "带内杂散",
        ),
    ):
        return False
    return bool(cert_u)


def _infer_semantic_target_from_evidence(
    *,
    project_title: str,
    section_rule: str,
    row_shape: str,
    item_label: str,
    condition_axis: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
    unit_family: str,
) -> str:
    hinted_target = _target_from_section_rule(section_rule) or "unknown"
    title_context = " | ".join(part for part in (project_title, item_label) if _coerce_text(part))

    if _looks_like_reference_oscillator_context(
        project_title=project_title,
        item_label=item_label,
        section_rule=section_rule,
    ):
        return "reference_oscillator"

    if _looks_like_relative_frequency_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
    ):
        return "reference_oscillator"

    if _looks_like_input_sensitivity_context(
        project_title=project_title,
        item_label=item_label,
        section_rule=section_rule,
        unit_family=unit_family,
        condition_axis=condition_axis,
    ):
        return "input_sensitivity"

    if _looks_like_accuracy_row_shape(row_shape=row_shape, error_value=error_value, cert_u=cert_u):
        if (
            _coerce_text(unit_family).lower() == "time"
            and (
                _contains_any_text(title_context, PERIOD_ACCURACY_SECTION_ALIASES)
                or _looks_like_output_time_interval_accuracy(
                    project_title=project_title,
                    section_rule=section_rule,
                    row_shape=row_shape,
                    nominal_value=nominal_value,
                    reference_value=reference_value,
                    measure_value=measure_value,
                    error_value=error_value,
                    limit_value=limit_value,
                    cert_u=cert_u,
                    unit_family=unit_family,
                )
            )
        ):
            return "period_accuracy"

        if _looks_like_frequency_accuracy_context(
            project_title=project_title,
            item_label=item_label,
            unit_family=unit_family,
            nominal_value=nominal_value,
            reference_value=reference_value,
            measure_value=measure_value,
            error_value=error_value,
            cert_u=cert_u,
        ):
            return "frequency_accuracy"

    if _looks_like_power_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        measure_value=measure_value,
        reference_value=reference_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
    ):
        return "power_accuracy"

    if _looks_like_period_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        cert_u=cert_u,
    ):
        return "period_accuracy"

    if _looks_like_generic_time_accuracy_context(
        project_title=project_title,
        section_rule=section_rule,
        row_shape=row_shape,
        unit_family=unit_family,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
    ):
        return "period_accuracy"

    if _looks_like_frequency_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        cert_u=cert_u,
    ):
        return "frequency_accuracy"

    if _looks_like_frequency_range_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        reference_value=reference_value,
        measure_value=measure_value,
        limit_value=limit_value,
        cert_u=cert_u,
    ):
        return "frequency_range"

    if _looks_like_count_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        cert_u=cert_u,
    ):
        return "count_accuracy"

    if _looks_like_vswr_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        cert_u=cert_u,
    ):
        return "vswr_accuracy"

    if _looks_like_impedance_accuracy_context(
        project_title=project_title,
        item_label=item_label,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
    ):
        return "impedance_accuracy"

    if _looks_like_cnr_consistency_context(
        project_title=project_title,
        item_label=item_label,
        cert_u=cert_u,
    ):
        return "cnr_consistency"

    if _looks_like_position_consistency_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        cert_u=cert_u,
    ):
        return "position_consistency"

    if _looks_like_dynamic_range_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        cert_u=cert_u,
    ):
        return "dynamic_range"

    if _looks_like_spectral_purity_context(
        project_title=project_title,
        item_label=item_label,
        unit_family=unit_family,
        cert_u=cert_u,
    ):
        return "spectral_purity"

    return hinted_target


def _extract_detail_value(
    details: Mapping[str, Any],
    alias_groups: Sequence[Sequence[str]],
) -> Tuple[str, str]:
    if not isinstance(details, Mapping):
        return "", ""
    items = list(details.items())
    for aliases in alias_groups:
        for key, value in items:
            key_norm = _normalize_key(key)
            matched = False
            for alias in aliases:
                alias_norm = _normalize_key(alias)
                if not alias_norm:
                    continue
                if alias_norm == key_norm:
                    matched = True
                    break
                if (
                    alias_norm in {_normalize_key("error"), _normalize_key("误差"), _normalize_key("偏差")}
                    and any(limit_key in key_norm for limit_key in _LIMIT_LIKE_HEADER_KEYS)
                ):
                    continue
                # 单字符别名（尤其是裸 `u`）只能精确匹配，避免把
                # `Frequency` / `Value` 这类表头误吸到 cert_u 上。
                if len(alias_norm) >= 2 and alias_norm in key_norm:
                    matched = True
                    break
            if matched:
                text = _coerce_text(value)
                if text:
                    return text, _coerce_text(key)
    return "", ""


def _detect_condition(details: Mapping[str, Any]) -> Tuple[str, str, str]:
    if not isinstance(details, Mapping):
        return "", "", ""
    for key, value in details.items():
        key_text = _coerce_text(key)
        key_norm = _normalize_key(key_text)
        value_text = _coerce_text(value)
        if not value_text:
            continue
        if "offset" in key_norm or "偏置" in key_text:
            return "offset_frequency", value_text, key_text
        if "frequency" in key_norm or "频率" in key_text:
            return "carrier_frequency", value_text, key_text
        if "gatetime" in key_norm or "闸门时间" in key_text or "取样时间" in key_text:
            return "gate_time", value_text, key_text
    return "", "", ""


def _infer_row_shape(
    *,
    item_label: str,
    condition_axis: str,
    condition_value: str,
    nominal_value: str,
    reference_value: str,
    measure_value: str,
    error_value: str,
    limit_value: str,
    cert_u: str,
) -> str:
    has_item = bool(item_label)
    has_condition = bool(condition_axis and condition_value)
    if has_condition and measure_value and limit_value and cert_u:
        return "condition_measure_limit_u"
    if has_condition and measure_value and cert_u:
        return "condition_measure_u"
    if has_item and nominal_value and reference_value and error_value and cert_u:
        return "item_nominal_reference_error_u"
    if has_item and measure_value and limit_value and cert_u:
        return "item_measure_limit_u"
    if has_item and measure_value and cert_u:
        return "item_measure_u"
    if nominal_value and reference_value and error_value and cert_u:
        return "nominal_reference_error_u"
    return "generic_structured_row"


def infer_semantic_subtype(
    semantic_target: str,
    *,
    section_label: str = "",
    item_label: str = "",
    condition_axis: str = "",
    condition_value: str = "",
    nominal_value: str = "",
    reference_value: str = "",
    measure_value: str = "",
    error_value: str = "",
    limit_value: str = "",
    unit_family: str = "unknown",
    candidate_text: str = "",
    kb_mode: bool = False,
) -> Tuple[str, float, bool]:
    registry = SUBTYPE_REGISTRY.get(_coerce_text(semantic_target), {})
    if not registry:
        return "", 0.0, False

    text_parts = [
        section_label,
        item_label,
        condition_axis,
        condition_value,
        nominal_value,
        reference_value,
        measure_value,
        error_value,
        limit_value,
        candidate_text,
    ]
    combined = " | ".join(part for part in text_parts if _coerce_text(part)).lower()

    scored: list[tuple[int, str]] = []
    for subtype, spec in registry.items():
        aliases = spec.get("kb_aliases") if kb_mode else spec.get("text_aliases")
        alias_list = tuple(str(alias) for alias in aliases or ())
        alias_score = 0
        for alias in alias_list:
            alias_lower = alias.lower()
            if alias_lower and alias_lower in combined:
                alias_score = max(alias_score, len(alias_lower) * 10)

        # A concrete subtype must be anchored by semantic text. Unit family is
        # a compatibility check, not enough evidence to route probe roles.
        if subtype != "__default__" and alias_score <= 0:
            continue

        score = alias_score
        allowed = subtype_allowed_unit_families(semantic_target, subtype)
        if unit_family and unit_family in allowed:
            score += 5
        if score > 0:
            scored.append((score, subtype))

    if not scored:
        return "", 0.0, bool(registry)

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_subtype = scored[0]
    ambiguous = len(scored) > 1 and scored[0][0] == scored[1][0]
    confidence = min(0.99, 0.55 + best_score / 100.0)
    return best_subtype, confidence, ambiguous


def build_parameter_contract(
    *,
    project_title: str,
    details: Mapping[str, Any],
    normalized_fields: Optional[Mapping[str, Any]] = None,
    header_rules: Optional[Mapping[str, Any]] = None,
    section_rule: str = "",
    unit_inherited: bool = False,
) -> Dict[str, Any]:
    normalized = dict(normalized_fields or {})
    headers = {str(k): _coerce_text(v) for k, v in (header_rules or {}).items() if _coerce_text(v)}

    item_label, item_header = _extract_detail_value(
        details,
        (
            ("parameter", "参数"),
            ("item", "项目"),
            ("measured", "被测量"),
        ),
    )
    nominal_value, nominal_header = _extract_detail_value(details, (("nominal", "标称值"),))
    reference_value, reference_header = _extract_detail_value(details, (("reference", "标准值", "参考值"),))
    measure_value, measure_header = _extract_detail_value(
        details,
        (("measure", "测量值"), ("indicated", "指示值", "显示值", "示值")),
    )
    error_value, error_header = _extract_detail_value(details, (("error", "误差", "偏差", "开机特性", "稳定度", "老化率", "复现性"),))
    limit_value, limit_header = _extract_detail_value(details, (("limit", "允许误差", "允许范围"),))
    cert_u, cert_u_header = _extract_detail_value(details, (("u(k=2)", "u", "不确定度"),))
    condition_axis, condition_value, condition_header = _detect_condition(details)

    if not measure_value:
        measure_value = _coerce_text(normalized.get("measure_value"))
        measure_header = measure_header or headers.get("measure_value", "")
    if not reference_value:
        reference_value = _coerce_text(normalized.get("reference_value"))
        reference_header = reference_header or headers.get("reference_value", "")
    if not error_value:
        error_value = _coerce_text(normalized.get("error_value"))
        error_header = error_header or headers.get("error_value", "")
    if not limit_value:
        limit_value = _coerce_text(normalized.get("limit_value"))
        limit_header = limit_header or headers.get("limit_value", "")
    if not cert_u:
        cert_u = _coerce_text(normalized.get("cert_u"))
        cert_u_header = cert_u_header or headers.get("cert_u", "")
    if not item_label:
        item_label = _coerce_text(normalized.get("point_value"))
        item_header = item_header or headers.get("point_value", "")

    unit_family = infer_contract_unit_family(
        [
            nominal_value,
            reference_value,
            measure_value,
            error_value,
            limit_value,
            cert_u,
            condition_value,
            project_title,
        ]
    )
    row_shape = _infer_row_shape(
        item_label=item_label,
        condition_axis=condition_axis,
        condition_value=condition_value,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
    )
    semantic_target = _infer_semantic_target_from_evidence(
        project_title=project_title,
        section_rule=section_rule,
        row_shape=row_shape,
        item_label=item_label,
        condition_axis=condition_axis,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
        unit_family=unit_family,
    )
    semantic_subtype, subtype_confidence, subtype_ambiguous = infer_semantic_subtype(
        semantic_target,
        section_label=project_title,
        item_label=item_label,
        condition_axis=condition_axis,
        condition_value=condition_value,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        unit_family=unit_family,
    )

    confidence = 0.7
    if row_shape != "generic_structured_row":
        confidence += 0.1
    if semantic_target in SUBTYPE_REGISTRY:
        confidence = max(confidence, subtype_confidence or 0.65)
    if unit_inherited:
        confidence = min(0.99, confidence + 0.05)

    contract = ParameterContractV2(
        row_shape=row_shape,
        semantic_target=semantic_target,
        semantic_subtype=semantic_subtype,
        item_label=item_label,
        condition_axis=condition_axis,
        condition_value=condition_value,
        nominal_value=nominal_value,
        reference_value=reference_value,
        measure_value=measure_value,
        error_value=error_value,
        limit_value=limit_value,
        cert_u=cert_u,
        unit_family=unit_family,
        source_headers={
            key: value
            for key, value in {
                "item_label": item_header,
                "condition_value": condition_header,
                "nominal_value": nominal_header,
                "reference_value": reference_header,
                "measure_value": measure_header,
                "error_value": error_header,
                "limit_value": limit_header,
                "cert_u": cert_u_header,
            }.items()
            if value
        },
        confidence=confidence,
        needs_disambiguation=subtype_ambiguous or not semantic_subtype,
    )
    return asdict(contract)
