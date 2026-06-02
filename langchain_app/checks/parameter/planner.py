#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constrained LLM semantic planner for parameter selection."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Type

try:
    from pydantic import BaseModel, ConfigDict, Field, create_model
except ImportError:  # pragma: no cover - pydantic v1 fallback
    from pydantic import BaseModel, Field, create_model

    ConfigDict = None


PLANNER_ALLOWED_ACTIONS = frozenset({"abstain", "suggest"})
PLANNER_CANONICAL_FIELDS = frozenset(
    {
        "measure_value",
        "reference_value",
        "error_value",
        "cert_u",
        "point_value",
        "condition_value",
    }
)
PLANNER_CONDITION_SLOTS = frozenset(
    {
        "frequency_condition",
        "offset_condition",
        "signal_condition",
        "modulation_condition",
    }
)
PLANNER_BINDABLE_FIELDS = frozenset(PLANNER_CANONICAL_FIELDS | PLANNER_CONDITION_SLOTS)
PLANNER_TRIGGER_RATIONALES = frozenset(
    {
        "unknown semantic",
        "same basis but no compatible candidate",
        "same basis missing kb subtype",
        "axis extraction ambiguous",
    }
)
PLANNER_GENERIC_FAILURE_RATIONALES = frozenset(
    {
        "unknown semantic",
        "same basis but no compatible candidate",
        "same basis missing kb subtype",
        "axis extraction ambiguous",
        "no candidates for basis code",
    }
)
PLANNER_STANDARD_PARSE_SOURCES = frozenset({"html_table", "html_table_inline"})
PLANNER_TAKEOVER_SCORE_THRESHOLD = 3
PLANNER_EMPTY_HEADER_SENTINEL = "__planner_no_header__"
PLANNER_EMPTY_CANDIDATE_SENTINEL = "__planner_no_candidate__"
SEMANTIC_AUDITOR_ALLOWED_ISSUE_TYPES = frozenset(
    {
        "semantic_ambiguity",
        "cross_target_fallback",
        "unit_family_conflict",
        "uncertainty_incomparable",
        "candidate_gap",
        "other",
    }
)
SEMANTIC_AUDITOR_ALLOWED_UNIT_FAMILIES = frozenset(
    {
        "unknown",
        "time",
        "frequency",
        "count",
        "voltage_power",
        "phase_noise",
        "dynamic_range",
        "modulation_quality",
        "spectral_purity",
        "input_sensitivity",
    }
)
KB_CAPABILITY_AUDIT_RESULT_QUANTITIES = frozenset(
    {
        "",
        "unknown",
        "relative_frequency",
        "frequency",
        "frequency_error_or_value",
        "period",
        "period_error_or_value",
        "count",
        "power_value",
        "power_error",
        "input_threshold",
        "phase_noise_level",
        "evm",
        "dynamic_range",
        "spectral_purity_level",
    }
)
KB_CAPABILITY_AUDIT_U_ROLES = frozenset(
    {
        "",
        "unknown",
        "range_capability_u",
        "accuracy_result_u",
        "comparison_uncertainty",
    }
)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _normalize_key(text: Any) -> str:
    return "".join(_coerce_text(text).lower().split())


def _matches_rationale_prefix(rationale: str, prefixes: Iterable[str]) -> bool:
    lowered = _coerce_text(rationale).lower()
    return any(lowered == prefix or lowered.startswith(prefix + ":") for prefix in prefixes)


def model_dump_compat(model: Any) -> Dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return dict(model.model_dump())
    if hasattr(model, "dict"):
        return dict(model.dict())
    return {}


class PlannerDecision(BaseModel):
    action: str = "abstain"
    semantic_target: str = ""
    field_bindings: Dict[str, str] = Field(default_factory=dict)
    candidate_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    abstain_reason: str = ""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


class PlannerRequestResult(BaseModel):
    decision: Optional[PlannerDecision] = None
    request_ok: bool = False
    error_code: str = ""
    error_message: str = ""
    error_stage: str = ""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


class SemanticAuditorDecision(BaseModel):
    action: str = "abstain"
    suggested_semantic_target: str = ""
    suggested_semantic_subtype: str = ""
    suggested_unit_family: str = ""
    suggested_candidate_target_preference: str = ""
    suspected_issue_type: str = ""
    confidence: float = 0.0
    reason: str = ""
    abstain_reason: str = ""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


class SemanticAuditorRequestResult(BaseModel):
    decision: Optional[SemanticAuditorDecision] = None
    request_ok: bool = False
    error_code: str = ""
    error_message: str = ""
    error_stage: str = ""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


class KbCapabilityAuditDecision(BaseModel):
    action: str = "abstain"
    suggested_capability_target: str = ""
    suggested_result_quantity: str = ""
    suggested_u_semantic_role: str = ""
    confidence: float = 0.0
    reason: str = ""
    abstain_reason: str = ""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


class KbCapabilityAuditRequestResult(BaseModel):
    decision: Optional[KbCapabilityAuditDecision] = None
    request_ok: bool = False
    error_code: str = ""
    error_message: str = ""
    error_stage: str = ""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


class ReplayImprovementAssessment(BaseModel):
    score: int = 0
    threshold: int = PLANNER_TAKEOVER_SCORE_THRESHOLD
    parser_risk: str = "low"
    hard_blockers: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    penalties: List[str] = Field(default_factory=list)
    nominated_match: bool = False
    confidence_above_threshold: bool = False
    fallback_used: bool = False
    recommended_takeover: bool = False

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = "forbid"


def _build_planner_slot_context(
    *,
    raw_field_summary: List[Dict[str, str]],
    candidate_summaries: List[Dict[str, str]],
) -> Dict[str, Any]:
    header_slots: List[Dict[str, Any]] = []
    slot_to_header: Dict[int, str] = {}
    for index, entry in enumerate(raw_field_summary or [], start=1):
        header = _coerce_text(entry.get("header"))
        if not header:
            continue
        header_slots.append(
            {
                "slot": index,
                "header": header,
                "value": _coerce_text(entry.get("value")),
            }
        )
        slot_to_header[index] = header

    candidate_slots: List[Dict[str, Any]] = []
    slot_to_candidate_id: Dict[int, str] = {}
    for index, entry in enumerate(candidate_summaries or [], start=1):
        candidate_id = _coerce_text(entry.get("candidate_id"))
        if not candidate_id:
            continue
        candidate_slots.append(
            {
                "slot": index,
                "candidate_id": candidate_id,
                "measured": _coerce_text(entry.get("measured")),
                "capability_target": _coerce_text(entry.get("capability_target")),
            }
        )
        slot_to_candidate_id[index] = candidate_id
    return {
        "header_slots": header_slots,
        "slot_to_header": slot_to_header,
        "candidate_slots": candidate_slots,
        "slot_to_candidate_id": slot_to_candidate_id,
    }


def _build_planner_slot_output_model(
    *,
    semantic_whitelist: Sequence[str],
    raw_field_summary: List[Dict[str, str]],
    candidate_summaries: List[Dict[str, str]],
) -> Type[BaseModel]:
    slot_context = _build_planner_slot_context(
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    semantic_choices = tuple(dict.fromkeys(_coerce_text(item) for item in semantic_whitelist if _coerce_text(item)))
    if not semantic_choices:
        semantic_choices = ("",)
    else:
        semantic_choices = semantic_choices + ("",)
    header_slots = tuple(slot["slot"] for slot in slot_context["header_slots"]) or (0,)
    candidate_slots = tuple(slot["slot"] for slot in slot_context["candidate_slots"]) or (0,)

    action_literal = Literal.__getitem__(tuple(sorted(PLANNER_ALLOWED_ACTIONS)))
    semantic_literal = Literal.__getitem__(semantic_choices)
    header_slot_literal = Literal.__getitem__(header_slots)
    candidate_slot_literal = Literal.__getitem__(candidate_slots)

    binding_fields = {
        field_name: (
            Optional[header_slot_literal],
            Field(default=None, description=f"Bind {field_name} to one existing raw-field slot."),
        )
        for field_name in sorted(PLANNER_BINDABLE_FIELDS)
    }
    bindings_model = create_model(
        "PlannerDecisionSlotBindings",
        __base__=BaseModel,
        **binding_fields,
    )
    return create_model(
        "PlannerDecisionSlotStructured",
        __base__=BaseModel,
        action=(action_literal, Field(default="abstain")),
        semantic_target=(semantic_literal, Field(default="")),
        field_bindings=(bindings_model, Field(default_factory=bindings_model)),
        candidate_slots=(List[candidate_slot_literal], Field(default_factory=list)),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        reason=(str, Field(default="")),
        abstain_reason=(str, Field(default="")),
    )


def _coerce_planner_slot_decision(
    decision: Any,
    *,
    raw_field_summary: List[Dict[str, str]],
    candidate_summaries: List[Dict[str, str]],
) -> Optional[PlannerDecision]:
    if not isinstance(decision, BaseModel):
        return None
    slot_context = _build_planner_slot_context(
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    slot_to_header = dict(slot_context.get("slot_to_header") or {})
    slot_to_candidate_id = dict(slot_context.get("slot_to_candidate_id") or {})

    raw_bindings = getattr(decision, "field_bindings", None)
    if isinstance(raw_bindings, BaseModel):
        binding_payload = model_dump_compat(raw_bindings)
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
            field_bindings[_coerce_text(key)] = header

    candidate_ids: List[str] = []
    for value in (getattr(decision, "candidate_slots", None) or []):
        try:
            slot = int(value)
        except (TypeError, ValueError):
            continue
        candidate_id = slot_to_candidate_id.get(slot)
        if candidate_id and candidate_id not in candidate_ids:
            candidate_ids.append(candidate_id)

    return PlannerDecision(
        action=_coerce_text(getattr(decision, "action", "")) or "abstain",
        semantic_target=_coerce_text(getattr(decision, "semantic_target", "")),
        field_bindings=field_bindings,
        candidate_ids=candidate_ids,
        confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
        reason=_coerce_text(getattr(decision, "reason", "")),
        abstain_reason=_coerce_text(getattr(decision, "abstain_reason", "")),
    )


def _build_planner_output_model(
    *,
    semantic_whitelist: Sequence[str],
    raw_field_summary: List[Dict[str, str]],
    candidate_summaries: List[Dict[str, str]],
) -> Type[BaseModel]:
    slot_context = _build_planner_slot_context(
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    semantic_choices = tuple(dict.fromkeys(_coerce_text(item) for item in semantic_whitelist if _coerce_text(item)))
    if not semantic_choices:
        semantic_choices = ("",)
    else:
        semantic_choices = semantic_choices + ("",)

    header_choices = tuple(
        dict.fromkeys(
            _coerce_text(entry.get("header"))
            for entry in raw_field_summary
            if _coerce_text(entry.get("header"))
        )
    ) or (PLANNER_EMPTY_HEADER_SENTINEL,)
    candidate_choices = tuple(
        slot["slot"] for slot in slot_context["candidate_slots"]
    ) or (0,)

    action_literal = Literal.__getitem__(tuple(sorted(PLANNER_ALLOWED_ACTIONS)))
    semantic_literal = Literal.__getitem__(semantic_choices)
    header_literal = Literal.__getitem__(header_choices)
    candidate_literal = Literal.__getitem__(candidate_choices)

    binding_fields = {
        field_name: (
            Optional[header_literal],
            Field(
                default=None,
                description=f"Bind {field_name} to one existing raw_field_summary header.",
            ),
        )
        for field_name in sorted(PLANNER_BINDABLE_FIELDS)
    }
    bindings_model = create_model(
        "PlannerDecisionBindings",
        __base__=BaseModel,
        **binding_fields,
    )
    return create_model(
        "PlannerDecisionStructured",
        __base__=BaseModel,
        action=(action_literal, Field(default="abstain")),
        semantic_target=(semantic_literal, Field(default="")),
        field_bindings=(bindings_model, Field(default_factory=bindings_model)),
        candidate_slots=(List[candidate_literal], Field(default_factory=list)),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        reason=(str, Field(default="")),
        abstain_reason=(str, Field(default="")),
    )


def _coerce_planner_decision(
    decision: Any,
    *,
    candidate_summaries: Optional[List[Dict[str, str]]] = None,
) -> Optional[PlannerDecision]:
    if isinstance(decision, PlannerDecision):
        return decision
    if not isinstance(decision, BaseModel):
        return None

    raw_bindings = getattr(decision, "field_bindings", None)
    if isinstance(raw_bindings, BaseModel):
        binding_payload = model_dump_compat(raw_bindings)
    elif isinstance(raw_bindings, dict):
        binding_payload = dict(raw_bindings)
    else:
        binding_payload = {}
    field_bindings = {
        _coerce_text(key): _coerce_text(value)
        for key, value in binding_payload.items()
        if _coerce_text(key)
        and _coerce_text(value)
        and _coerce_text(value) != PLANNER_EMPTY_HEADER_SENTINEL
    }

    slot_context = _build_planner_slot_context(
        raw_field_summary=[],
        candidate_summaries=list(candidate_summaries or []),
    )
    slot_to_candidate_id = dict(slot_context.get("slot_to_candidate_id") or {})
    raw_candidate_slots = getattr(decision, "candidate_slots", None)
    candidate_ids: List[str] = []
    if isinstance(raw_candidate_slots, list):
        for item in raw_candidate_slots[:3]:
            try:
                slot = int(item)
            except (TypeError, ValueError):
                continue
            candidate_id = slot_to_candidate_id.get(slot)
            if candidate_id and candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)
    else:
        candidate_ids = [
            candidate_id
            for candidate_id in (_coerce_text(item) for item in (getattr(decision, "candidate_ids", None) or []))
            if candidate_id and candidate_id != PLANNER_EMPTY_CANDIDATE_SENTINEL
        ]

    return PlannerDecision(
        action=_coerce_text(getattr(decision, "action", "")) or "abstain",
        semantic_target=_coerce_text(getattr(decision, "semantic_target", "")),
        field_bindings=field_bindings,
        candidate_ids=candidate_ids,
        confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
        reason=_coerce_text(getattr(decision, "reason", "")),
        abstain_reason=_coerce_text(getattr(decision, "abstain_reason", "")),
    )


def planner_mode(cfg: Any) -> str:
    mode = _coerce_text(getattr(cfg, "parameter_planner_mode", "live")).lower()
    return mode if mode in {"off", "shadow", "live"} else "live"


def planner_confidence_threshold(cfg: Any) -> float:
    value = getattr(cfg, "parameter_planner_confidence_threshold", 0.85)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.85


def planner_candidate_limit(cfg: Any) -> int:
    value = getattr(cfg, "parameter_planner_candidate_limit", 20)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 20
    return max(1, min(parsed, 50))


def parameter_semantic_auditor_mode(cfg: Any) -> str:
    mode = _coerce_text(getattr(cfg, "parameter_semantic_auditor_mode", "live")).lower()
    return mode if mode in {"off", "shadow", "live"} else "live"


def parameter_semantic_auditor_confidence_threshold(cfg: Any) -> float:
    value = getattr(cfg, "parameter_semantic_auditor_confidence_threshold", 0.90)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.90


def parameter_semantic_auditor_max_calls(cfg: Any) -> int:
    value = getattr(cfg, "parameter_semantic_auditor_max_calls", 3)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 3
    return max(0, min(parsed, 20))


def parameter_semantic_auditor_candidate_limit(cfg: Any) -> int:
    value = getattr(cfg, "parameter_semantic_auditor_candidate_limit", 12)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 12
    return max(1, min(parsed, 30))


def kb_capability_auditor_mode(cfg: Any) -> str:
    mode = _coerce_text(getattr(cfg, "kb_capability_auditor_mode", "shadow")).lower()
    return mode if mode in {"off", "shadow"} else "shadow"


def kb_capability_auditor_max_items(cfg: Any) -> int:
    value = getattr(cfg, "kb_capability_auditor_max_items", 2)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 2
    return max(0, min(parsed, 20))


def should_trigger_planner(
    *,
    selection_result: Any,
    cfg: Any,
    llm_client: Any = None,
) -> bool:
    if planner_mode(cfg) == "off":
        return False
    if not getattr(cfg, "use_llm_verification", False):
        return False
    if selection_result is None or getattr(selection_result, "selected_candidate", None) is not None:
        return False

    audit = getattr(selection_result, "audit", None)
    cert_point = getattr(selection_result, "cert_point", None)
    rationale = _coerce_text(getattr(audit, "rationale", "")).lower()
    semantic_target = _coerce_text(getattr(cert_point, "semantic_target", "")).lower()
    notes = tuple(getattr(cert_point, "normalization_notes", ()) or ())
    has_axis_ambiguity = any("axis extraction ambiguous" in _coerce_text(note).lower() for note in notes)
    has_unit_mismatch = any("unit family mismatch" in _coerce_text(note).lower() for note in notes)
    contract_confidence = float(getattr(cert_point, "contract_confidence", 0.0) or 0.0)
    needs_disambiguation = bool(getattr(cert_point, "needs_disambiguation", False))
    basis_candidates = list(getattr(selection_result, "basis_candidates", []) or [])
    ranked_candidates = list(getattr(selection_result, "ranked_candidates", []) or [])
    has_candidate_pool = bool(basis_candidates or ranked_candidates)

    def _forbid_live_guess() -> bool:
        if semantic_target == "":
            return True
        if semantic_target == "unknown" and not has_candidate_pool:
            return True
        if semantic_target == "input_sensitivity":
            return True
        if has_axis_ambiguity or has_unit_mismatch:
            return True
        if rationale.startswith("same basis but no compatible candidate") and not has_candidate_pool:
            return True
        if rationale.startswith("same basis missing kb subtype") and not has_candidate_pool:
            return True
        return False

    def _allow_live_nomination() -> bool:
        if _forbid_live_guess():
            return False
        if semantic_target == "unknown":
            return has_candidate_pool
        if needs_disambiguation:
            return has_candidate_pool
        if rationale.startswith("same basis but no compatible candidate"):
            return has_candidate_pool
        if rationale.startswith("same basis missing kb subtype"):
            return has_candidate_pool
        return False

    if _forbid_live_guess():
        return False
    if (
        semantic_target == "period_range"
        and rationale.startswith("same basis but no compatible candidate")
        and contract_confidence >= 0.95
        and not needs_disambiguation
        and not has_axis_ambiguity
        and not has_unit_mismatch
        and has_candidate_pool
    ):
        return False
    if _allow_live_nomination():
        return True
    if _matches_rationale_prefix(rationale, PLANNER_TRIGGER_RATIONALES):
        return has_candidate_pool and not rationale.startswith("unknown semantic")
    return False


def build_raw_field_summary(raw_fields: Dict[str, Any]) -> List[Dict[str, str]]:
    summary: List[Dict[str, str]] = []
    for header, value in (raw_fields or {}).items():
        header_text = _coerce_text(header)
        value_text = _coerce_text(value)
        if not header_text or not value_text:
            continue
        summary.append({"header": header_text, "value": value_text})
    return summary


def _format_candidate_uncertainty(source: Dict[str, Any]) -> str:
    uncertainty = source.get("uncertainty")
    if isinstance(uncertainty, dict):
        for key in ("value_display", "value", "text", "raw"):
            text = _coerce_text(uncertainty.get(key))
            if text:
                return text
    return _coerce_text(source.get("u_text"))


def build_candidate_summaries(
    selection_result: Any,
    *,
    limit: int = 20,
) -> List[Dict[str, str]]:
    ranked_candidates = list(getattr(selection_result, "ranked_candidates", []) or [])
    basis_candidates = list(getattr(selection_result, "basis_candidates", []) or [])
    ordered_candidates: List[Any] = []
    seen_ids = set()

    for candidate in ranked_candidates + basis_candidates:
        candidate_id = _coerce_text(getattr(candidate, "candidate_id", ""))
        if not candidate_id or candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        ordered_candidates.append(candidate)
        if len(ordered_candidates) >= limit:
            break

    summaries: List[Dict[str, str]] = []
    for candidate in ordered_candidates:
        source = getattr(candidate, "source", {}) or {}
        summaries.append(
            {
                "candidate_id": _coerce_text(getattr(candidate, "candidate_id", "")),
                "measured": _coerce_text(getattr(candidate, "measured", "")),
                "capability_target": _coerce_text(getattr(candidate, "capability_target", "")),
                "semantic_subtype": _coerce_text(getattr(candidate, "semantic_subtype", "")),
                "unit_family": _coerce_text(getattr(candidate, "unit_family", "")),
                "result_quantity": _coerce_text(getattr(candidate, "result_quantity", "")),
                "condition_axis": _coerce_text(getattr(candidate, "condition_axis", "")),
                "measure_range_text": _coerce_text(source.get("measure_range_text")),
                "u_text": _format_candidate_uncertainty(source),
            }
        )
    return summaries


def _build_prompt(
    *,
    criterion: str,
    param_name: str,
    section_label: str,
    parser_meta: Dict[str, Any],
    normalized_fields: Dict[str, Any],
    raw_field_summary: List[Dict[str, str]],
    deterministic_rationale: str,
    candidate_summaries: List[Dict[str, str]],
    semantic_whitelist: Sequence[str],
) -> str:
    slot_context = _build_planner_slot_context(
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    return "\n".join(
        [
            "你是受约束的参数语义规划器。",
            "只能输出结构化规划，不得输出 PASS/FAIL。",
            "如果把握不足，必须 action=abstain。",
            f"依据: {criterion}",
            f"参数名: {param_name}",
            f"章节标签: {section_label}",
            f"parser_meta: {json.dumps(parser_meta, ensure_ascii=False, sort_keys=True)}",
            f"normalized_fields: {json.dumps(normalized_fields, ensure_ascii=False, sort_keys=True)}",
            f"raw_field_summary: {json.dumps(raw_field_summary, ensure_ascii=False)}",
            f"deterministic_selector_rationale: {deterministic_rationale}",
            f"candidate_summaries(topk): {json.dumps(candidate_summaries, ensure_ascii=False)}",
            f"candidate_slots(topk): {json.dumps(slot_context['candidate_slots'], ensure_ascii=False)}",
            f"semantic_target_whitelist: {json.dumps(list(semantic_whitelist), ensure_ascii=False)}",
            f"bindable_fields: {json.dumps(sorted(PLANNER_BINDABLE_FIELDS), ensure_ascii=False)}",
            "严格遵守输出 schema；如果无法可靠映射，就 abstain。",
        ]
    )


def request_planner_decision(
    *,
    llm_client: Any,
    criterion: str,
    param_name: str,
    section_label: str,
    parser_meta: Dict[str, Any],
    normalized_fields: Dict[str, Any],
    raw_field_summary: List[Dict[str, str]],
    deterministic_rationale: str,
    candidate_summaries: List[Dict[str, str]],
    semantic_whitelist: Sequence[str],
) -> PlannerRequestResult:
    if llm_client is None:
        return PlannerRequestResult(
            decision=None,
            request_ok=False,
            error_code="ClientUnavailable",
            error_message="planner client unavailable",
            error_stage="client_missing",
        )
    prompt = _build_prompt(
        criterion=criterion,
        param_name=param_name,
        section_label=section_label,
        parser_meta=parser_meta,
        normalized_fields=normalized_fields,
        raw_field_summary=raw_field_summary,
        deterministic_rationale=deterministic_rationale,
        candidate_summaries=candidate_summaries,
        semantic_whitelist=semantic_whitelist,
    )
    output_model = _build_planner_output_model(
        semantic_whitelist=semantic_whitelist,
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    try:
        decision = llm_client.invoke_structured(
            user_prompt=prompt,
            output_model=output_model,
            system_prompt=(
                "你只输出受约束的参数语义规划。"
                "不得输出 PASS/FAIL。"
            ),
        )
        if decision is None:
            return PlannerRequestResult(
                decision=None,
                request_ok=False,
                error_code="EmptyResponseError",
                error_message="planner returned empty structured response",
                error_stage="structured_parse",
            )
        coerced = _coerce_planner_decision(
            decision,
            candidate_summaries=candidate_summaries,
        )
        if coerced is None:
            return PlannerRequestResult(
                decision=None,
                request_ok=False,
                error_code="StructuredParseError",
                error_message="planner returned unsupported structured payload",
                error_stage="structured_parse",
            )
        return PlannerRequestResult(decision=coerced, request_ok=True)
    except Exception as exc:
        from langchain_app.core.llm_client import describe_llm_exception

        details = describe_llm_exception(exc)
        return PlannerRequestResult(
            decision=None,
            request_ok=False,
            error_code=details["error_code"],
            error_message=details["error_message"],
            error_stage=details["error_stage"],
        )


def validate_planner_decision(
    *,
    request_result: PlannerRequestResult,
    semantic_whitelist: Sequence[str],
    raw_field_summary: List[Dict[str, str]],
    candidate_summaries: List[Dict[str, str]],
) -> Tuple[bool, str, Optional[PlannerDecision]]:
    if request_result is None or not request_result.request_ok:
        stage = _coerce_text(getattr(request_result, "error_stage", ""))
        if stage == "client_missing":
            return False, "planner client unavailable", None
        if stage == "client_init":
            return False, "planner init failed", None
        if stage == "structured_parse":
            return False, "planner structured parse failed", None
        return False, "planner request failed", None

    decision = request_result.decision
    if decision is None:
        return False, "planner structured parse failed", None
    payload = model_dump_compat(decision)
    action = _coerce_text(payload.get("action")).lower()
    if action not in PLANNER_ALLOWED_ACTIONS:
        return False, "planner action rejected", None

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        return False, "planner confidence rejected", None
    if confidence < 0.0 or confidence > 1.0:
        return False, "planner confidence rejected", None

    raw_header_lookup = {
        _coerce_text(entry.get("header")): _coerce_text(entry.get("header"))
        for entry in raw_field_summary
        if _coerce_text(entry.get("header"))
    }
    raw_header_norm_lookup = {
        _normalize_key(header): header for header in raw_header_lookup
    }
    candidate_id_lookup = {
        _coerce_text(entry.get("candidate_id")): _coerce_text(entry.get("candidate_id"))
        for entry in candidate_summaries
        if _coerce_text(entry.get("candidate_id"))
    }

    if action == "abstain":
        sanitized = PlannerDecision(
            action="abstain",
            semantic_target="",
            field_bindings={},
            candidate_ids=[],
            confidence=confidence,
            reason=_coerce_text(payload.get("reason")),
            abstain_reason=_coerce_text(payload.get("abstain_reason")) or _coerce_text(payload.get("reason")),
        )
        return True, "planner abstained", sanitized

    semantic_target = _coerce_text(payload.get("semantic_target"))
    if semantic_target not in semantic_whitelist:
        return False, "planner semantic target rejected", None

    field_bindings: Dict[str, str] = {}
    raw_bindings = payload.get("field_bindings") or {}
    if not isinstance(raw_bindings, dict):
        raw_bindings = {}
    for target, source_header in raw_bindings.items():
        bind_target = _coerce_text(target)
        bind_source = _coerce_text(source_header)
        if bind_target not in PLANNER_BINDABLE_FIELDS:
            continue
        resolved_header = raw_header_lookup.get(bind_source)
        if resolved_header is None:
            resolved_header = raw_header_norm_lookup.get(_normalize_key(bind_source))
        if resolved_header is None:
            continue
        field_bindings[bind_target] = resolved_header

    candidate_ids: List[str] = []
    raw_candidate_ids = payload.get("candidate_ids") or []
    if not isinstance(raw_candidate_ids, list):
        return False, "planner candidate ids rejected", None
    for candidate_id in raw_candidate_ids[:3]:
        candidate_text = _coerce_text(candidate_id)
        if not candidate_text:
            continue
        resolved_candidate_id = candidate_id_lookup.get(candidate_text)
        if resolved_candidate_id is None:
            return False, "planner candidate ids rejected", None
        if resolved_candidate_id not in candidate_ids:
            candidate_ids.append(resolved_candidate_id)

    sanitized = PlannerDecision(
        action="suggest",
        semantic_target=semantic_target,
        field_bindings=field_bindings,
        candidate_ids=candidate_ids,
        confidence=confidence,
        reason=_coerce_text(payload.get("reason")),
        abstain_reason="",
    )
    return True, "planner suggestion accepted", sanitized


def _build_semantic_auditor_output_model(
    *,
    semantic_whitelist: Sequence[str],
    candidate_summaries: List[Dict[str, str]],
) -> Type[BaseModel]:
    semantic_choices = tuple(dict.fromkeys(_coerce_text(item) for item in semantic_whitelist if _coerce_text(item)))
    if not semantic_choices:
        semantic_choices = ("",)
    else:
        semantic_choices = semantic_choices + ("",)
    candidate_target_choices = tuple(
        dict.fromkeys(
            list(
                _coerce_text(entry.get("capability_target"))
                for entry in candidate_summaries
                if _coerce_text(entry.get("capability_target"))
            )
            + list(_coerce_text(item) for item in semantic_whitelist if _coerce_text(item))
        )
    )
    if not candidate_target_choices:
        candidate_target_choices = ("",)
    else:
        candidate_target_choices = candidate_target_choices + ("",)

    action_literal = Literal.__getitem__(tuple(sorted(PLANNER_ALLOWED_ACTIONS)))
    semantic_literal = Literal.__getitem__(semantic_choices)
    unit_literal = Literal.__getitem__(tuple(sorted(SEMANTIC_AUDITOR_ALLOWED_UNIT_FAMILIES)))
    target_pref_literal = Literal.__getitem__(candidate_target_choices)
    issue_literal = Literal.__getitem__(tuple(sorted(SEMANTIC_AUDITOR_ALLOWED_ISSUE_TYPES | {""})))

    return create_model(
        "SemanticAuditorDecisionStructured",
        __base__=BaseModel,
        action=(action_literal, Field(default="abstain")),
        suggested_semantic_target=(semantic_literal, Field(default="")),
        suggested_semantic_subtype=(str, Field(default="")),
        suggested_unit_family=(unit_literal, Field(default="unknown")),
        suggested_candidate_target_preference=(target_pref_literal, Field(default="")),
        suspected_issue_type=(issue_literal, Field(default="")),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        reason=(str, Field(default="")),
        abstain_reason=(str, Field(default="")),
    )


def request_semantic_auditor_decision(
    *,
    llm_client: Any,
    criterion: str,
    param_name: str,
    section_label: str,
    point_text: str,
    parser_meta: Dict[str, Any],
    normalized_fields: Dict[str, Any],
    parameter_contract: Dict[str, Any],
    selection_audit: Dict[str, Any],
    candidate_summaries: List[Dict[str, str]],
    semantic_whitelist: Sequence[str],
    suspicion_signals: Sequence[str],
) -> SemanticAuditorRequestResult:
    if llm_client is None:
        return SemanticAuditorRequestResult(
            decision=None,
            request_ok=False,
            error_code="ClientUnavailable",
            error_message="semantic auditor client unavailable",
            error_stage="client_missing",
        )
    output_model = _build_semantic_auditor_output_model(
        semantic_whitelist=semantic_whitelist,
        candidate_summaries=candidate_summaries,
    )
    prompt = "\n".join(
        [
            "你是受约束的参数语义审计器。",
            "任务：审计当前参数行是否存在语义目标、单位族或候选能力错位。",
            "只能输出结构化建议，不得输出 PASS/FAIL，不得直接选定最终 candidate。",
            f"依据: {criterion}",
            f"参数名: {param_name}",
            f"章节标签: {section_label}",
            f"point_text: {point_text}",
            f"parser_meta: {json.dumps(parser_meta, ensure_ascii=False, sort_keys=True)}",
            f"normalized_fields: {json.dumps(normalized_fields, ensure_ascii=False, sort_keys=True)}",
            f"parameter_contract: {json.dumps(parameter_contract, ensure_ascii=False, sort_keys=True)}",
            f"selection_audit: {json.dumps(selection_audit, ensure_ascii=False, sort_keys=True)}",
            f"candidate_summaries(topk): {json.dumps(candidate_summaries, ensure_ascii=False)}",
            f"semantic_target_whitelist: {json.dumps(list(semantic_whitelist), ensure_ascii=False)}",
            f"suspicion_signals: {json.dumps(list(suspicion_signals), ensure_ascii=False)}",
            "如果把握不足，必须 action=abstain。",
        ]
    )
    try:
        decision = llm_client.invoke_structured(
            user_prompt=prompt,
            output_model=output_model,
            system_prompt=(
                "你只输出受约束的参数语义审计决策。"
                "不得输出 PASS/FAIL。"
            ),
        )
        if decision is None:
            return SemanticAuditorRequestResult(
                decision=None,
                request_ok=False,
                error_code="EmptyResponseError",
                error_message="semantic auditor returned empty structured response",
                error_stage="structured_parse",
            )
        payload = model_dump_compat(decision)
        coerced = SemanticAuditorDecision(**payload)
        return SemanticAuditorRequestResult(decision=coerced, request_ok=True)
    except Exception as exc:
        from langchain_app.core.llm_client import describe_llm_exception

        details = describe_llm_exception(exc)
        return SemanticAuditorRequestResult(
            decision=None,
            request_ok=False,
            error_code=details["error_code"],
            error_message=details["error_message"],
            error_stage=details["error_stage"],
        )


def validate_semantic_auditor_decision(
    *,
    request_result: SemanticAuditorRequestResult,
    semantic_whitelist: Sequence[str],
    candidate_summaries: List[Dict[str, str]],
) -> Tuple[bool, str, Optional[SemanticAuditorDecision]]:
    if request_result is None or not request_result.request_ok:
        stage = _coerce_text(getattr(request_result, "error_stage", ""))
        if stage == "client_missing":
            return False, "semantic auditor client unavailable", None
        if stage == "client_init":
            return False, "semantic auditor init failed", None
        if stage == "structured_parse":
            return False, "semantic auditor structured parse failed", None
        return False, "semantic auditor request failed", None

    decision = request_result.decision
    if decision is None:
        return False, "semantic auditor structured parse failed", None
    payload = model_dump_compat(decision)
    action = _coerce_text(payload.get("action")).lower()
    if action not in PLANNER_ALLOWED_ACTIONS:
        return False, "semantic auditor action rejected", None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        return False, "semantic auditor confidence rejected", None
    if confidence < 0.0 or confidence > 1.0:
        return False, "semantic auditor confidence rejected", None

    if action == "abstain":
        sanitized = SemanticAuditorDecision(
            action="abstain",
            suggested_semantic_target="",
            suggested_semantic_subtype="",
            suggested_unit_family="unknown",
            suggested_candidate_target_preference="",
            suspected_issue_type="",
            confidence=confidence,
            reason=_coerce_text(payload.get("reason")),
            abstain_reason=_coerce_text(payload.get("abstain_reason")) or _coerce_text(payload.get("reason")),
        )
        return True, "semantic auditor abstained", sanitized

    semantic_target = _coerce_text(payload.get("suggested_semantic_target"))
    if semantic_target not in semantic_whitelist:
        return False, "semantic auditor semantic target rejected", None

    candidate_targets = {
        _coerce_text(entry.get("capability_target"))
        for entry in candidate_summaries
        if _coerce_text(entry.get("capability_target"))
    }
    candidate_targets.update(
        _coerce_text(item)
        for item in semantic_whitelist
        if _coerce_text(item)
    )
    target_preference = _coerce_text(payload.get("suggested_candidate_target_preference"))
    if target_preference and target_preference not in candidate_targets:
        return False, "semantic auditor candidate target preference rejected", None

    unit_family = _coerce_text(payload.get("suggested_unit_family")) or "unknown"
    if unit_family not in SEMANTIC_AUDITOR_ALLOWED_UNIT_FAMILIES:
        return False, "semantic auditor unit family rejected", None

    issue_type = _coerce_text(payload.get("suspected_issue_type"))
    if issue_type and issue_type not in SEMANTIC_AUDITOR_ALLOWED_ISSUE_TYPES:
        return False, "semantic auditor issue type rejected", None

    sanitized = SemanticAuditorDecision(
        action="suggest",
        suggested_semantic_target=semantic_target,
        suggested_semantic_subtype=_coerce_text(payload.get("suggested_semantic_subtype")),
        suggested_unit_family=unit_family,
        suggested_candidate_target_preference=target_preference,
        suspected_issue_type=issue_type,
        confidence=confidence,
        reason=_coerce_text(payload.get("reason")),
        abstain_reason="",
    )
    return True, "semantic auditor suggestion accepted", sanitized


def _build_kb_capability_audit_output_model(
    capability_target_whitelist: Sequence[str],
) -> Type[BaseModel]:
    action_literal = Literal.__getitem__(tuple(sorted(PLANNER_ALLOWED_ACTIONS)))
    capability_choices = tuple(
        dict.fromkeys(_coerce_text(item) for item in capability_target_whitelist if _coerce_text(item))
    )
    if not capability_choices:
        capability_choices = ("",)
    else:
        capability_choices = capability_choices + ("",)
    return create_model(
        "KbCapabilityAuditDecisionStructured",
        __base__=BaseModel,
        action=(action_literal, Field(default="abstain")),
        suggested_capability_target=(
            Literal.__getitem__(capability_choices),
            Field(default=""),
        ),
        suggested_result_quantity=(
            Literal.__getitem__(tuple(sorted(KB_CAPABILITY_AUDIT_RESULT_QUANTITIES))),
            Field(default=""),
        ),
        suggested_u_semantic_role=(
            Literal.__getitem__(tuple(sorted(KB_CAPABILITY_AUDIT_U_ROLES))),
            Field(default=""),
        ),
        confidence=(float, Field(default=0.0, ge=0.0, le=1.0)),
        reason=(str, Field(default="")),
        abstain_reason=(str, Field(default="")),
    )


def request_kb_capability_audit(
    *,
    llm_client: Any,
    candidate_summary: Dict[str, Any],
    hit_examples: Sequence[Dict[str, Any]],
    capability_target_whitelist: Sequence[str],
) -> KbCapabilityAuditRequestResult:
    if llm_client is None:
        return KbCapabilityAuditRequestResult(
            decision=None,
            request_ok=False,
            error_code="ClientUnavailable",
            error_message="kb capability auditor client unavailable",
            error_stage="client_missing",
        )
    output_model = _build_kb_capability_audit_output_model(capability_target_whitelist)
    prompt = "\n".join(
        [
            "你是受约束的知识库能力审计器。",
            "任务：判断当前 KB 条目的 capability_target / result_quantity / U 语义角色是否存在建模错位。",
            "只能输出结构化建议，不得输出 PASS/FAIL。",
            f"candidate_summary: {json.dumps(candidate_summary, ensure_ascii=False, sort_keys=True)}",
            f"hit_examples: {json.dumps(list(hit_examples), ensure_ascii=False)}",
            f"capability_target_whitelist: {json.dumps(list(capability_target_whitelist), ensure_ascii=False)}",
            "如果把握不足，必须 action=abstain。",
        ]
    )
    try:
        decision = llm_client.invoke_structured(
            user_prompt=prompt,
            output_model=output_model,
            system_prompt=(
                "你只输出受约束的 KB capability 审计决策。"
                "不得输出 PASS/FAIL。"
            ),
        )
        if decision is None:
            return KbCapabilityAuditRequestResult(
                decision=None,
                request_ok=False,
                error_code="EmptyResponseError",
                error_message="kb capability auditor returned empty structured response",
                error_stage="structured_parse",
            )
        payload = model_dump_compat(decision)
        coerced = KbCapabilityAuditDecision(**payload)
        return KbCapabilityAuditRequestResult(decision=coerced, request_ok=True)
    except Exception as exc:
        from langchain_app.core.llm_client import describe_llm_exception

        details = describe_llm_exception(exc)
        return KbCapabilityAuditRequestResult(
            decision=None,
            request_ok=False,
            error_code=details["error_code"],
            error_message=details["error_message"],
            error_stage=details["error_stage"],
        )


def validate_kb_capability_audit_decision(
    *,
    request_result: KbCapabilityAuditRequestResult,
    capability_target_whitelist: Sequence[str],
) -> Tuple[bool, str, Optional[KbCapabilityAuditDecision]]:
    if request_result is None or not request_result.request_ok:
        stage = _coerce_text(getattr(request_result, "error_stage", ""))
        if stage == "client_missing":
            return False, "kb capability auditor client unavailable", None
        if stage == "client_init":
            return False, "kb capability auditor init failed", None
        if stage == "structured_parse":
            return False, "kb capability auditor structured parse failed", None
        return False, "kb capability auditor request failed", None

    decision = request_result.decision
    if decision is None:
        return False, "kb capability auditor structured parse failed", None
    payload = model_dump_compat(decision)
    action = _coerce_text(payload.get("action")).lower()
    if action not in PLANNER_ALLOWED_ACTIONS:
        return False, "kb capability auditor action rejected", None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        return False, "kb capability auditor confidence rejected", None
    if confidence < 0.0 or confidence > 1.0:
        return False, "kb capability auditor confidence rejected", None

    if action == "abstain":
        sanitized = KbCapabilityAuditDecision(
            action="abstain",
            suggested_capability_target="",
            suggested_result_quantity="",
            suggested_u_semantic_role="",
            confidence=confidence,
            reason=_coerce_text(payload.get("reason")),
            abstain_reason=_coerce_text(payload.get("abstain_reason")) or _coerce_text(payload.get("reason")),
        )
        return True, "kb capability auditor abstained", sanitized

    capability_target = _coerce_text(payload.get("suggested_capability_target"))
    if capability_target and capability_target not in capability_target_whitelist:
        return False, "kb capability auditor capability target rejected", None

    result_quantity = _coerce_text(payload.get("suggested_result_quantity"))
    if result_quantity not in KB_CAPABILITY_AUDIT_RESULT_QUANTITIES:
        return False, "kb capability auditor result quantity rejected", None

    u_role = _coerce_text(payload.get("suggested_u_semantic_role"))
    if u_role not in KB_CAPABILITY_AUDIT_U_ROLES:
        return False, "kb capability auditor u semantic role rejected", None

    sanitized = KbCapabilityAuditDecision(
        action="suggest",
        suggested_capability_target=capability_target,
        suggested_result_quantity=result_quantity,
        suggested_u_semantic_role=u_role,
        confidence=confidence,
        reason=_coerce_text(payload.get("reason")),
        abstain_reason="",
    )
    return True, "kb capability auditor suggestion accepted", sanitized


def audit_kb_capability_candidates(
    *,
    llm_client: Any,
    cfg: Any,
    candidate_summaries: Sequence[Dict[str, Any]],
    hit_examples_by_candidate: Optional[Dict[str, Sequence[Dict[str, Any]]]] = None,
    capability_target_whitelist: Sequence[str],
) -> List[Dict[str, Any]]:
    if kb_capability_auditor_mode(cfg) == "off":
        return []
    audits: List[Dict[str, Any]] = []
    limit = kb_capability_auditor_max_items(cfg)
    if limit <= 0:
        return audits
    for candidate_summary in list(candidate_summaries or [])[:limit]:
        candidate_id = _coerce_text(candidate_summary.get("candidate_id"))
        hit_examples = list((hit_examples_by_candidate or {}).get(candidate_id, ()))
        request_result = request_kb_capability_audit(
            llm_client=llm_client,
            candidate_summary=dict(candidate_summary),
            hit_examples=hit_examples,
            capability_target_whitelist=capability_target_whitelist,
        )
        ok, reason, decision = validate_kb_capability_audit_decision(
            request_result=request_result,
            capability_target_whitelist=capability_target_whitelist,
        )
        audits.append(
            {
                "candidate_id": candidate_id,
                "current_capability_target": _coerce_text(candidate_summary.get("capability_target")),
                "suggested_capability_target": _coerce_text(getattr(decision, "suggested_capability_target", "")),
                "suggested_result_quantity": _coerce_text(getattr(decision, "suggested_result_quantity", "")),
                "suggested_u_semantic_role": _coerce_text(getattr(decision, "suggested_u_semantic_role", "")),
                "confidence": float(getattr(decision, "confidence", 0.0) or 0.0) if decision is not None else 0.0,
                "reason": _coerce_text(getattr(decision, "reason", "")) or reason,
                "accepted": ok,
            }
        )
    return audits


def _append_unique(items: List[str], value: str) -> None:
    text = _coerce_text(value)
    if text and text not in items:
        items.append(text)


def _result_rationale(selection_result: Any) -> str:
    return _coerce_text(getattr(getattr(selection_result, "audit", None), "rationale", "")).lower()


def _result_semantic_target(selection_result: Any) -> str:
    return _coerce_text(getattr(getattr(selection_result, "cert_point", None), "semantic_target", "")).lower()


def _result_notes(selection_result: Any) -> Tuple[str, ...]:
    notes = getattr(getattr(selection_result, "cert_point", None), "normalization_notes", ()) or ()
    return tuple(_coerce_text(note).lower() for note in notes if _coerce_text(note))


def _result_has_token(selection_result: Any, token: str) -> bool:
    lowered = _coerce_text(token).lower()
    if not lowered:
        return False
    rationale = _result_rationale(selection_result)
    if lowered in rationale:
        return True
    return any(lowered in note for note in _result_notes(selection_result))


def _parser_risk_rank(level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(_coerce_text(level).lower(), 0)


def _raise_parser_risk(current: str, target: str) -> str:
    return target if _parser_risk_rank(target) > _parser_risk_rank(current) else current


def _required_takeover_score(base_threshold: int, parser_risk: str) -> int:
    if parser_risk == "high":
        return base_threshold + 2
    if parser_risk == "medium":
        return base_threshold + 1
    return base_threshold


def assess_replay_improvement(
    *,
    selection_result: Any,
    retry_result: Any,
    decision: Optional[PlannerDecision],
    parser_meta: Dict[str, Any],
    validation_ok: bool,
    replay_used_planner_candidates: bool,
    fallback_reason: str,
    cfg: Any,
) -> ReplayImprovementAssessment:
    threshold = PLANNER_TAKEOVER_SCORE_THRESHOLD
    score = 0
    parser_risk = "low"
    hard_blockers: List[str] = []
    improvements: List[str] = []
    penalties: List[str] = []
    fallback_used = bool(_coerce_text(fallback_reason))
    confidence_above_threshold = False
    nominated_match = False

    if decision is not None:
        confidence_above_threshold = decision.confidence >= planner_confidence_threshold(cfg)

    if not validation_ok:
        _append_unique(hard_blockers, "planner suggestion unavailable")
    if decision is None or decision.action != "suggest":
        _append_unique(hard_blockers, "planner suggestion unavailable")
    if retry_result is None or getattr(retry_result, "selected_candidate", None) is None:
        _append_unique(hard_blockers, "planner replay produced no candidate")

    selected_candidate_id = _coerce_text(getattr(retry_result, "selected_candidate_id", ""))
    nominated_candidate_ids = set(getattr(decision, "candidate_ids", []) or [])
    nominated_match = bool(selected_candidate_id and selected_candidate_id in nominated_candidate_ids)

    retry_notes = _result_notes(retry_result)
    retry_rationale = _result_rationale(retry_result)
    if any("unit family mismatch" in note for note in retry_notes):
        _append_unique(hard_blockers, "planner replay introduced unit mismatch")
    if any("axis extraction ambiguous" in note for note in retry_notes):
        _append_unique(hard_blockers, "planner replay introduced axis ambiguity")
    if retry_rationale == "axis extraction ambiguous":
        _append_unique(hard_blockers, "planner replay remained axis ambiguous")
    if nominated_candidate_ids and not nominated_match and not fallback_used:
        _append_unique(hard_blockers, "planner replay fell outside nominated candidates without fallback reason")
    if replay_used_planner_candidates and not nominated_match:
        _append_unique(hard_blockers, "planner replay selected incompatible nominated candidate")

    deterministic_rationale = _result_rationale(selection_result)
    deterministic_semantic_target = _result_semantic_target(selection_result)
    replay_semantic_target = _result_semantic_target(retry_result)

    if nominated_match:
        score += 2
        improvements.append("formal replay matched planner nominated candidate")

    deterministic_unknown = deterministic_rationale == "unknown semantic" or deterministic_semantic_target == "unknown"
    replay_known = bool(replay_semantic_target and replay_semantic_target != "unknown")
    if deterministic_unknown and replay_known:
        score += 2
        improvements.append("replay resolved unknown semantic target")

    if (
        getattr(selection_result, "selected_candidate", None) is None
        and getattr(retry_result, "selected_candidate", None) is not None
        and (
            deterministic_rationale.startswith("same basis but no compatible candidate")
            or deterministic_rationale.startswith("same basis missing kb subtype")
        )
    ):
        score += 2
        improvements.append("replay resolved same-basis candidate gap")

    if _result_has_token(selection_result, "unit family mismatch") and not _result_has_token(retry_result, "unit family mismatch"):
        score += 2
        improvements.append("replay cleared unit family mismatch")

    if _result_has_token(selection_result, "axis extraction ambiguous") and not _result_has_token(retry_result, "axis extraction ambiguous"):
        score += 2
        improvements.append("replay cleared axis ambiguity")

    if _matches_rationale_prefix(deterministic_rationale, PLANNER_GENERIC_FAILURE_RATIONALES) and retry_rationale.startswith("selected "):
        score += 1
        improvements.append("replay converted generic selector failure into a concrete selection")

    if confidence_above_threshold:
        score += 1
        improvements.append("planner confidence met configured threshold")

    parse_source = _coerce_text((parser_meta or {}).get("parse_source")).lower()
    if parse_source and parse_source not in PLANNER_STANDARD_PARSE_SOURCES:
        score -= 3
        penalties.append(f"nonstandard parser source: {parse_source}")
        parser_risk = _raise_parser_risk(parser_risk, "high")

    section_rule = _coerce_text((parser_meta or {}).get("section_hint_rule") or (parser_meta or {}).get("section_rule")).lower()
    if section_rule == "unknown":
        score -= 2
        penalties.append("parser section_rule is unknown")
        parser_risk = _raise_parser_risk(parser_risk, "medium")

    header_rules = (parser_meta or {}).get("header_rules")
    if not isinstance(header_rules, dict):
        header_rules = {}
    if decision is not None:
        missing_bound_headers = sorted(
            {
                field_name
                for field_name in (decision.field_bindings or {})
                if field_name in PLANNER_CANONICAL_FIELDS and not _coerce_text(header_rules.get(field_name))
            }
        )
        if missing_bound_headers:
            score -= 1
            penalties.append("planner bound fields missing parser header rules: " + ", ".join(missing_bound_headers))
            parser_risk = _raise_parser_risk(parser_risk, "medium")

        if (parser_meta or {}).get("unit_inherited") and any(
            field_name in {"measure_value", "reference_value", "error_value"}
            for field_name in (decision.field_bindings or {})
        ):
            score -= 1
            penalties.append("unit_inherited parser rows weaken planner value-field bindings")
            parser_risk = _raise_parser_risk(parser_risk, "medium")

    if fallback_used and nominated_candidate_ids and not nominated_match:
        score -= 1
        penalties.append("same-basis fallback selected a non-nominated candidate")

    required_score = _required_takeover_score(threshold, parser_risk)
    recommended_takeover = not hard_blockers and score >= required_score
    return ReplayImprovementAssessment(
        score=score,
        threshold=threshold,
        parser_risk=parser_risk,
        hard_blockers=hard_blockers,
        improvements=improvements,
        penalties=penalties,
        nominated_match=nominated_match,
        confidence_above_threshold=confidence_above_threshold,
        fallback_used=fallback_used,
        recommended_takeover=recommended_takeover,
    )


def live_mode_allows_takeover(
    *,
    cfg: Any,
    assessment: ReplayImprovementAssessment,
) -> Tuple[bool, str, ReplayImprovementAssessment]:
    if planner_mode(cfg) != "live":
        return False, "planner mode is not live", assessment
    if assessment.hard_blockers:
        return False, assessment.hard_blockers[0], assessment
    if not assessment.recommended_takeover:
        required_score = _required_takeover_score(assessment.threshold, assessment.parser_risk)
        return (
            False,
            (
                f"planner replay improvement score {assessment.score} below required score {required_score}"
                if required_score != assessment.threshold
                else f"planner replay improvement score {assessment.score} below threshold {assessment.threshold}"
            ),
            assessment,
        )
    return True, "planner live takeover allowed", assessment
