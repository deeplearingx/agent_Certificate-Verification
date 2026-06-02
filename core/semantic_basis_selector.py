from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Protocol


FREQ_UNITS = re.compile(r"\b(?:hz|khz|mhz|ghz)\b", re.IGNORECASE)
TIME_UNITS = re.compile(r"\b(?:s|ms|us|µs|μs|ns|ps|h)\b", re.IGNORECASE)
VOLT_POWER_UNITS = re.compile(r"\b(?:v|mv|uv|dbm|db|vpp|vrms)\b", re.IGNORECASE)

REFERENCE_OSCILLATOR_OBJECT_TOKENS = [
    "internal timebase",
    "internal time base",
    "timebase oscillator",
    "time base oscillator",
    "internal crystal",
    "crystal",
    "晶振",
    "内时基",
    "时基振荡器",
    "内部晶振",
    "内晶振",
    "内时基振荡器",
    "internal timebase oscillator",
]

REFERENCE_OSCILLATOR_METRIC_TOKENS = [
    "relative frequency deviation",
    "warm-up",
    "warm up",
    "frequency stability",
    "aging",
    "ageing",
    "reproducibility",
    "相对频率偏差",
    "开机特性",
    "频率稳定度",
    "日老化率",
    "频率复现性",
    "1s频率稳定度",
]


@dataclass(frozen=True)
class ParamSemantic:
    task_intent: str
    primary_quantity: str
    unit_family: str
    condition_axis: Optional[str]
    uncertainty_kind: str
    features: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KbCapability:
    measured: str
    capability_target: str
    primary_quantity: str
    result_quantity: str
    condition_axis: Optional[str]
    uncertainty_kind: str
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


@dataclass(frozen=True)
class SelectionResult:
    selected: List[KbCapability]
    audit: SelectionAudit


class SemanticDecider(Protocol):
    def decide(self, param: ParamSemantic, candidates: List[KbCapability]) -> Dict[str, Any]:
        ...


def _contains_any(text: str, tokens: List[str]) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in tokens)


def infer_uncertainty_kind(cert_u: str) -> str:
    text = (cert_u or "").strip().lower()
    if "urel" in text:
        return "UREL"
    if text:
        return "U"
    return "UNKNOWN"


def _parse_time_value_to_s(token: str) -> Optional[float]:
    match = re.search(r"([-+]?\d*\.?\d+)\s*(ps|ns|us|µs|μs|ms|h|s)", token, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "ps": 1e-12,
        "ns": 1e-9,
        "us": 1e-6,
        "µs": 1e-6,
        "μs": 1e-6,
        "ms": 1e-3,
        "s": 1.0,
        "h": 3600.0,
    }
    return value * multipliers.get(unit, 1.0)


def _extract_time_band_s(source: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    if not isinstance(source, dict):
        return None

    texts: List[str] = []
    for key in ("measure_range_text", "measure_range", "range", "raw", "raw_block"):
        raw_value = source.get(key, "")
        if isinstance(raw_value, (list, tuple)):
            values = [str(item).strip() for item in raw_value if str(item).strip()]
        else:
            text = str(raw_value or "").strip()
            values = [text] if text else []
        for text in values:
            if re.search(r"\d\s*(?:ps|ns|us|µs|μs|ms|h|s)\b", text, flags=re.IGNORECASE):
                texts.append(text)

    for candidate in texts:
        tokens = re.findall(r"[-+<>≤≥]?\s*\d*\.?\d+\s*(?:ps|ns|us|µs|μs|ms|h|s)", candidate, flags=re.IGNORECASE)
        if len(tokens) >= 2:
            lower = _parse_time_value_to_s(tokens[0])
            upper = _parse_time_value_to_s(tokens[1])
            if lower is not None and upper is not None:
                return lower, upper
        elif len(tokens) == 1:
            value = _parse_time_value_to_s(tokens[0])
            if value is not None:
                return value, value
    return None


def _extract_time_s_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"([-+]?\d*\.?\d+)\s*(ps|ns|us|µs|μs|ms|h|s)", text, re.IGNORECASE)
    if not match:
        return None
    return _parse_time_value_to_s(match.group(0))


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
        scored.append(((contains, -distance, -width, -idx), cap))
    if not scored:
        return candidates
    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = [cap for _, cap in scored]
    seen_ids = {id(cap) for cap in ordered}
    ordered.extend(cap for cap in candidates if id(cap) not in seen_ids)
    return ordered


def infer_param_semantics(param_name: str, point_text: str, cert_u: str = "") -> ParamSemantic:
    text = f"{param_name} | {point_text} | {cert_u}".lower()
    has_reference = "reference" in text or "标准值" in text or "鏍囧噯鍊?" in text
    has_indicated = "indicated" in text or "指示值" in text or "鎸囩ず鍊?" in text
    has_error = "error" in text or "误差" in text or "璇樊" in text
    has_limit = "limit" in text or "允许误差" in text or "鍏佽璇樊" in text
    has_sensitivity = _contains_any(text, ["sensitivity", "trigger", "灵敏度", "触发", "鐏垫晱搴?", "瑙﹀彂"])

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
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
                "reference_oscillator_context": True,
            },
        )

    if _contains_any(text, ["relative frequency deviation", "相对频率偏差", "crystal", "晶振", "鏅舵尟"]):
        return ParamSemantic(
            task_intent="reference_check",
            primary_quantity="relative_frequency",
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
            unit_family="voltage_power",
            condition_axis="carrier_frequency" if FREQ_UNITS.search(text) else None,
            uncertainty_kind=infer_uncertainty_kind(cert_u),
            features={
                "has_reference": has_reference,
                "has_indicated": has_indicated,
                "has_error": has_error,
                "has_limit": has_limit,
            },
        )

    if _contains_any(text, ["dynamic range", "动态范围", "鍔ㄦ€佽寖鍥?"]):
        return ParamSemantic(
            task_intent="range_check",
            primary_quantity="dynamic_range",
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

    # 额外处理：对于"输出时间间隔"类参数，即使不满足完整条件也进行识别
    # 匹配"时间间隔"、"Time Interval"、"电秒表"、"秒表功能"等关键词
    has_time_interval = (
        "时间间隔" in text
        or "time interval" in text
        or "电秒表" in text
        or "秒表功能" in text
        or "电秒表功能" in text
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
    measured = str(entry.get("measured", "")).strip()
    measure_range_text = str(entry.get("measure_range_text", "")).lower()
    u_text = str(entry.get("u_text", "") or entry.get("kb_u", "")).strip()
    measured_lower = measured.lower()
    is_reference_oscillator_metric = _contains_any(measure_range_text, REFERENCE_OSCILLATOR_METRIC_TOKENS)

    if measured_lower in {
        "crystal",
        "crystal frequency",
        "internal crystal output frequency",
        "internal crystal frequency",
        "晶振",
        "晶振频率",
        "内晶振输出频率",
        "内部晶振频率",
    }:
        return KbCapability(
            measured=measured,
            capability_target="reference_oscillator",
            primary_quantity="relative_frequency",
            result_quantity="relative_frequency",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {"frequency", "频率", "棰戠巼"} and is_reference_oscillator_metric:
        return KbCapability(
            measured=measured,
            capability_target="reference_oscillator",
            primary_quantity="relative_frequency",
            result_quantity="relative_frequency",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
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

    if measured_lower in {"period", "周期", "鍛ㄦ湡"} or "时间间隔" in measured_lower or "time interval" in measured_lower:
        return KbCapability(
            measured=measured,
            capability_target="period_accuracy",
            primary_quantity="period",
            result_quantity="period_error_or_value",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {"power_range", "功率范围", "鍔熺巼鑼冨洿"}:
        return KbCapability(
            measured=measured,
            capability_target="power_accuracy",
            primary_quantity="power",
            result_quantity="power_value",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {"power_deviation", "功率偏差", "鍔熺巼鍋忓樊"}:
        return KbCapability(
            measured=measured,
            capability_target="power_accuracy",
            primary_quantity="power",
            result_quantity="power_error",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
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
        return KbCapability(
            measured=measured,
            capability_target="modulation_quality",
            primary_quantity="modulation_quality",
            result_quantity="evm",
            condition_axis="carrier_frequency" if FREQ_UNITS.search(measure_range_text) else None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {"power_dynamic_range", "功率动态范围", "鍔熺巼鍔ㄦ€佽寖鍥?"}:
        return KbCapability(
            measured=measured,
            capability_target="dynamic_range",
            primary_quantity="dynamic_range",
            result_quantity="dynamic_range",
            condition_axis=None,
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {
        "frequency_measurement_range_and_input_sensitivity",
        "频率测量范围及输入灵敏度",
        "棰戠巼娴嬮噺鑼冨洿鍙婅緭鍏ョ伒鏁忓害",
    }:
        return KbCapability(
            measured=measured,
            capability_target="input_sensitivity",
            primary_quantity="input_sensitivity",
            result_quantity="input_threshold",
            condition_axis="frequency_band",
            uncertainty_kind=infer_uncertainty_kind(u_text),
            source=entry,
        )

    if measured_lower in {
        "period_measurement_range_and_input_sensitivity",
        "周期测量范围及输入灵敏度",
        "鍛ㄦ湡娴嬮噺鑼冨洿鍙婅緭鍏ョ伒鏁忓害",
    }:
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


def structured_prefilter(param: ParamSemantic, kb_entries: List[Dict[str, Any]]) -> List[KbCapability]:
    wanted_targets = {
        ("reference_check", "relative_frequency"): {"reference_oscillator"},
        ("sensitivity_check", "input_sensitivity"): {"input_sensitivity"},
        ("accuracy_check", "frequency"): {"frequency_accuracy"},
        # 时间类准确度核验既会遇到“时间间隔”，也会遇到“周期”，
        # 先放宽候选池，再由时间轴排序挑选更贴近点位的条目。
        ("accuracy_check", "period"): {"period_accuracy", "period_range"},
        ("accuracy_check", "power"): {"power_accuracy"},
        ("noise_check", "phase_noise"): {"phase_noise"},
        ("quality_check", "modulation_quality"): {"modulation_quality"},
        ("range_check", "dynamic_range"): {"dynamic_range"},
    }.get((param.task_intent, param.primary_quantity), set())

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
    def decide(self, param: ParamSemantic, candidates: List[KbCapability]) -> Dict[str, Any]:
        if not candidates:
            return {"selected_measured": [], "rationale": "No compatible candidates after structured prefilter."}
        return {
            "selected_measured": [candidates[0].measured],
            "rationale": "Selected the first compatible candidate after structured prefilter.",
        }


def select_basis_with_audit(
    param_name: str,
    point_text: str,
    cert_u: str,
    kb_entries: List[Dict[str, Any]],
    decider: SemanticDecider,
) -> SelectionResult:
    param = infer_param_semantics(param_name, point_text, cert_u)
    prefiltered = structured_prefilter(param, kb_entries)

    if param.condition_axis == "period_band":
        point_time_s = _extract_time_s_from_text(point_text)
        if point_time_s is not None:
            prefiltered = _rank_time_candidates(point_time_s, prefiltered)

    decision = decider.decide(param, prefiltered)
    selected_measured = list(decision.get("selected_measured", []))

    selected = [cap for cap in prefiltered if cap.measured in selected_measured]
    rejected = [cap.measured for cap in prefiltered if cap.measured not in selected_measured]

    audit = SelectionAudit(
        task_goal=f"{param.task_intent}:{param.primary_quantity}",
        primary_quantity=param.primary_quantity,
        unit_family=param.unit_family,
        condition_axis=param.condition_axis,
        uncertainty_kind=param.uncertainty_kind,
        prefiltered_candidates=[cap.measured for cap in prefiltered],
        selected_measured=selected_measured,
        rejected_measured=rejected,
        rationale=str(decision.get("rationale", "")),
    )
    return SelectionResult(selected=selected, audit=audit)
