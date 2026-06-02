from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from langchain_app.checks.parameter import parameter as parameter_module
from langchain_app.checks.parameter.planner import (
    PlannerDecision,
    PlannerRequestResult,
    audit_kb_capability_candidates,
    _build_planner_output_model,
    _build_planner_slot_context,
    _build_planner_slot_output_model,
    _coerce_planner_slot_decision,
    assess_replay_improvement,
    live_mode_allows_takeover,
    request_semantic_auditor_decision,
    validate_semantic_auditor_decision,
    request_planner_decision,
    should_trigger_planner,
    validate_planner_decision,
)
from langchain_app.checks.parameter.semantic import infer_kb_capability
from langchain_app.checks.parameter.semantic import SelectionAudit, SelectionResult, select_basis_with_audit
from langchain_app.core.llm_client import LLMInvocationError, describe_llm_exception
from langchain_app.utils import AppConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "parameter"


def build_config(tmp_path: Path, **overrides) -> AppConfig:
    config = AppConfig(
        root_dir=tmp_path,
        api_key="test-key",
        api_base="https://api.example.com",
        model="deepseek-chat",
        temperature=0.0,
        max_tokens=512,
        topk=20,
        batch_size=4,
        max_workers=2,
        embed_model_path=str(tmp_path / "models"),
        cnas_db_dir=str(tmp_path / "vector_db" / "cnas_calibration"),
        temperature_db_dir=str(tmp_path / "vector_db" / "temperature"),
        general_cycle_db_dir=str(tmp_path / "vector_db" / "general_cycle"),
        huawei_cycle_db_dir=str(tmp_path / "vector_db" / "huawei_cycle"),
        address_db_dir=str(tmp_path / "vector_db" / "address"),
        cnas_collection="calibration_data",
        address_collection="calibration_address",
        default_cycle="12个月",
        use_llm_verification=True,
        use_llm_location_check=True,
        must_match_threshold=0.45,
        optional_match_threshold=0.4,
        llm_temperature=0.0,
        llm_max_tokens=256,
        local_pdf_dir=tmp_path / "local_pdf",
        local_md_dir=tmp_path / "local_md",
        local_json_dir=tmp_path / "local_json",
        final_reports_dir=tmp_path / "final_reports",
        reports_dir=tmp_path / "reports",
    )
    return config.with_overrides(**overrides)


class FakePlannerLLM:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def invoke_structured(self, user_prompt, output_model, system_prompt=None):
        self.calls += 1
        payload = self.decision(user_prompt) if callable(self.decision) else self.decision
        if isinstance(payload, output_model):
            return payload
        if isinstance(payload, BaseModel):
            if hasattr(payload, "model_dump"):
                payload = payload.model_dump()
            else:
                payload = payload.dict()
        return output_model(**payload)


def _load_fixture_param(case_name: str) -> dict:
    payload = json.loads((FIXTURE_ROOT / "planner_cases.json").read_text(encoding="utf-8"))
    return deepcopy(payload[case_name])


def _make_selection_result(
    *,
    selected_candidate_id: str = "",
    rationale: str = "unknown semantic",
    semantic_target: str = "unknown",
    notes=(),
    basis_candidates=None,
    ranked_candidates=None,
    semantic_subtype: str = "",
    contract_confidence: float = 0.0,
    needs_disambiguation: bool = False,
):
    selected_candidate = object() if selected_candidate_id else None
    audit = SelectionAudit(
        task_goal="test",
        primary_quantity="test",
        unit_family="unknown",
        condition_axis=None,
        uncertainty_kind="U",
        prefiltered_candidates=[],
        selected_measured=[],
        rejected_measured=[],
        rationale=rationale,
        semantic_target=semantic_target,
        semantic_subtype=semantic_subtype,
        selected_candidate_id=selected_candidate_id or None,
        ranked_candidates=[
            getattr(candidate, "candidate_id", "")
            for candidate in (ranked_candidates or [])
            if getattr(candidate, "candidate_id", "")
        ],
        basis_candidates=[
            getattr(candidate, "candidate_id", "")
            for candidate in (basis_candidates or [])
            if getattr(candidate, "candidate_id", "")
        ],
    )
    return SelectionResult(
        selected=[],
        audit=audit,
        selected_candidate_id=selected_candidate_id or None,
        selected_candidate=selected_candidate,
        basis_candidates=list(basis_candidates or []),
        ranked_candidates=list(ranked_candidates or []),
        cert_point=SimpleNamespace(
            semantic_target=semantic_target,
            semantic_subtype=semantic_subtype,
            contract_confidence=contract_confidence,
            needs_disambiguation=needs_disambiguation,
            normalization_notes=tuple(notes),
        ),
    )


def _planner_context_for_param(param: dict) -> dict:
    point_text = str(param)
    point_value = parameter_module._extract_param_point_value(param) or "N/A"
    measure_val = parameter_module._extract_param_measure_value(param)
    reference_val = parameter_module._extract_param_reference_value(param)
    error_val = parameter_module._extract_param_error_value(param)
    selection_context = " ".join(
        part
        for part in [
            f"点位:{point_value}" if point_value and point_value != "N/A" else "",
            f"测量值:{measure_val}" if measure_val else "",
            f"标准值:{reference_val}" if reference_val else "",
            f"误差:{error_val}" if error_val else "",
            point_text,
        ]
        if part
    ).strip()
    return {
        "point_blob": point_text,
        "point_value": point_value,
        "measure_val": measure_val,
        "reference_val": reference_val,
        "error_val": error_val,
        "selection_context": selection_context,
        "normalized_fields": parameter_module._normalized_fields_for_llm(param),
        "parser_meta": parameter_module._get_parser_meta(param),
    }


def _same_basis_candidates(kb_items: list[dict], criterion: str) -> list:
    return [candidate for candidate, _ in parameter_module._planner_same_basis_candidate_pool(kb_items=kb_items, criterion=criterion)]


def _run_planner_case(
    *,
    cfg: AppConfig,
    llm_client,
    llm_client_error,
    param: dict,
    kb_items: list[dict],
    criterion: str,
    decision_rationale: str = "unknown semantic",
    decision_semantic_target: str = "unknown",
    decision_notes=(),
):
    context = _planner_context_for_param(param)
    candidates = _same_basis_candidates(kb_items, criterion)
    selection_result = _make_selection_result(
        rationale=decision_rationale,
        semantic_target=decision_semantic_target,
        notes=decision_notes,
        basis_candidates=candidates,
        ranked_candidates=candidates,
    )
    return parameter_module._run_parameter_planner(
        llm_client=llm_client,
        llm_client_error=llm_client_error,
        cfg=cfg,
        criterion=criterion,
        batch_index=1,
        param=param,
        param_name=param["param_name"],
        selection_result=selection_result,
        kb_items=kb_items,
        point_blob=context["point_blob"],
        selection_context=context["selection_context"],
        normalized_fields=context["normalized_fields"],
        parser_meta=context["parser_meta"],
        measure_val=context["measure_val"],
        reference_val=context["reference_val"],
        error_val=context["error_val"],
        point_value=context["point_value"],
    )


def _daily_error_selection_result():
    kb_entries = [
        {
            "file_code": "JJF 2195",
            "measured": "时间",
            "measure_range_text": "(0～10)min",
            "uncertainty": {"type": "U", "value_display": "U=0.007s"},
        },
        {
            "file_code": "JJF 2195",
            "measured": "时间",
            "measure_range_text": ">10 min～24 h",
            "uncertainty": {"type": "U", "value_display": "U=0.011s"},
        },
    ]
    return select_basis_with_audit(
        basis_code="JJF 2195-2025",
        section_label="2 日差(Error Per Day)",
        param_name="2 日差(Error Per Day)",
        point_text="日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        cert_u="0.03 s/d",
        measure_value="",
        reference_value="",
        error_value="-0.65 s/d",
        parameter_contract={
            "semantic_target": "period_accuracy",
            "error_value": "-0.65 s/d",
            "limit_value": "±4320.00 s/d",
            "cert_u": "0.03 s/d",
            "unit_family": "time",
            "confidence": 0.99,
        },
        parser_meta={
            "parse_source": "html_table",
            "section_rule": "period_accuracy",
            "section_rule_confidence": 0.99,
            "header_rules": {
                "error_value": "日差",
                "limit_value": "允许误差",
                "cert_u": "U",
            },
            "unit_inherited": True,
        },
        kb_entries=kb_entries,
    )


def _standard_parser_meta() -> dict:
    return {
        "parse_source": "html_table",
        "section_rule": "frequency_accuracy",
        "header_rules": {
            "measure_value": "Measured",
            "reference_value": "Reference",
            "error_value": "Error",
            "cert_u": "U (k=2)",
        },
        "unit_inherited": False,
    }


def test_validate_planner_decision_rejects_non_whitelist_target():
    request_result = PlannerRequestResult(
        decision=PlannerDecision(
            action="suggest",
            semantic_target="not_in_whitelist",
            confidence=0.9,
            reason="bad target",
        ),
        request_ok=True,
    )
    ok, reason, sanitized = validate_planner_decision(
        request_result=request_result,
        semantic_whitelist=("frequency_accuracy", "power_accuracy"),
        raw_field_summary=[{"header": "标准值 (Reference)", "value": "10 MHz"}],
        candidate_summaries=[],
    )

    assert not ok
    assert sanitized is None
    assert reason == "planner semantic target rejected"


def test_validate_planner_decision_rejects_unknown_candidate_id():
    request_result = PlannerRequestResult(
        decision=PlannerDecision(
            action="suggest",
            semantic_target="frequency_accuracy",
            candidate_ids=["missing-id"],
            confidence=0.9,
            reason="bad candidate",
        ),
        request_ok=True,
    )
    ok, reason, sanitized = validate_planner_decision(
        request_result=request_result,
        semantic_whitelist=("frequency_accuracy",),
        raw_field_summary=[{"header": "标准值 (Reference)", "value": "10 MHz"}],
        candidate_summaries=[{"candidate_id": "known-id"}],
    )

    assert not ok
    assert sanitized is None
    assert reason == "planner candidate ids rejected"


def test_validate_planner_decision_filters_unknown_raw_header_binding():
    request_result = PlannerRequestResult(
        decision=PlannerDecision(
            action="suggest",
            semantic_target="frequency_accuracy",
            field_bindings={"reference_value": "不存在的列"},
            confidence=0.9,
            reason="bad binding",
        ),
        request_ok=True,
    )
    ok, reason, sanitized = validate_planner_decision(
        request_result=request_result,
        semantic_whitelist=("frequency_accuracy",),
        raw_field_summary=[{"header": "标准值 (Reference)", "value": "10 MHz"}],
        candidate_summaries=[],
    )

    assert ok
    assert reason == "planner suggestion accepted"
    assert sanitized is not None
    assert sanitized.field_bindings == {}


def test_validate_planner_decision_accepts_cert_u_binding():
    request_result = PlannerRequestResult(
        decision=PlannerDecision(
            action="suggest",
            semantic_target="power_accuracy",
            field_bindings={"reference_value": "标称值 (Nominal)", "cert_u": "U (k=2)"},
            candidate_ids=["known-id"],
            confidence=0.9,
            reason="bind cert_u",
        ),
        request_ok=True,
    )
    ok, reason, sanitized = validate_planner_decision(
        request_result=request_result,
        semantic_whitelist=("power_accuracy",),
        raw_field_summary=[
            {"header": "标称值 (Nominal)", "value": "0.1 dB"},
            {"header": "U (k=2)", "value": "0.08 dB"},
        ],
        candidate_summaries=[{"candidate_id": "known-id"}],
    )

    assert ok
    assert reason == "planner suggestion accepted"
    assert sanitized is not None
    assert sanitized.field_bindings == {
        "reference_value": "标称值 (Nominal)",
        "cert_u": "U (k=2)",
    }


def test_apply_planner_field_bindings_skips_empty_optional_binding():
    ok, reason, bound_values, condition_text = parameter_module._apply_planner_field_bindings(
        decision=PlannerDecision(
            action="suggest",
            semantic_target="modulation_quality",
            field_bindings={
                "measure_value": "测量值 (Measured)",
                "error_value": "允许误差 (Limit)",
            },
            confidence=0.9,
            reason="skip empty optional binding",
        ),
        param={
            "数据明细": {
                "测量值 (Measured)": "-61.20 dB",
                "允许误差 (Limit)": "",
            }
        },
    )

    assert ok
    assert "skipped empty" in reason
    assert bound_values == {"measure_value": "-61.20 dB"}
    assert condition_text == ""


def test_apply_planner_field_bindings_skips_na_placeholder_binding():
    ok, reason, bound_values, condition_text = parameter_module._apply_planner_field_bindings(
        decision=PlannerDecision(
            action="suggest",
            semantic_target="modulation_quality",
            field_bindings={
                "measure_value": "测量值 (Measured)",
                "error_value": "允许误差 (Limit)",
            },
            confidence=0.9,
            reason="skip placeholder binding",
        ),
        param={
            "数据明细": {
                "测量值 (Measured)": "-61.20 dB",
                "允许误差 (Limit)": "N/A",
            }
        },
    )

    assert ok
    assert "skipped empty" in reason
    assert bound_values == {"measure_value": "-61.20 dB"}
    assert condition_text == ""


def test_should_not_trigger_planner_when_unit_family_mismatch_present():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    selection_result = _make_selection_result(
        rationale="unrelated rationale",
        semantic_target="dynamic_range",
        notes=("unit family mismatch: unknown",),
    )

    assert not should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_trigger_planner_for_same_basis_kb_subtype_gap():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    candidate = SimpleNamespace(candidate_id="candidate-iq-offset")
    selection_result = _make_selection_result(
        rationale="same basis missing kb subtype: iq_offset",
        semantic_target="modulation_quality",
        basis_candidates=[candidate],
        ranked_candidates=[candidate],
    )

    assert should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_not_trigger_planner_for_unknown_semantic_without_candidate_pool():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    selection_result = _make_selection_result(
        rationale="unknown semantic",
        semantic_target="unknown",
    )

    assert not should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_trigger_planner_for_unknown_semantic_with_candidate_pool():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    candidate = SimpleNamespace(candidate_id="candidate-unknown")
    selection_result = _make_selection_result(
        rationale="unknown semantic",
        semantic_target="unknown",
        basis_candidates=[candidate],
        ranked_candidates=[candidate],
    )

    assert should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_not_trigger_planner_for_same_basis_gap_without_candidate_pool():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    selection_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="frequency_accuracy",
    )

    assert not should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_not_trigger_planner_for_input_sensitivity_business_rule_target():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    selection_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="input_sensitivity",
    )

    assert not should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_not_trigger_planner_for_stable_selected_row():
    cfg = SimpleNamespace(parameter_planner_mode="shadow", use_llm_verification=True)
    selection_result = _make_selection_result(
        selected_candidate_id="candidate-power-level",
        rationale="selected candidate-power-level",
        semantic_target="power_accuracy",
    )

    assert not should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_not_trigger_planner_for_high_confidence_period_range_same_basis_gap():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    candidate = SimpleNamespace(candidate_id="JJG601|输出时间间隔|>1 ms～9999.9 s|Urel=8.4×10⁻⁸")
    selection_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="period_range",
        contract_confidence=0.99,
        basis_candidates=[candidate],
        ranked_candidates=[candidate],
    )

    assert not should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_should_still_trigger_planner_for_period_range_same_basis_gap_when_disambiguation_needed():
    cfg = SimpleNamespace(parameter_planner_mode="live", use_llm_verification=True)
    candidate = SimpleNamespace(candidate_id="JJG601|输出时间间隔|>1 ms～9999.9 s|Urel=8.4×10⁻⁸")
    selection_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="period_range",
        contract_confidence=0.99,
        needs_disambiguation=True,
        basis_candidates=[candidate],
        ranked_candidates=[candidate],
    )

    assert should_trigger_planner(selection_result=selection_result, cfg=cfg)


def test_semantic_auditor_does_not_trigger_for_source_field_gap_even_with_candidate_gap(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="live",
        llm_suspicion_min_signals=1,
    )
    candidate = SimpleNamespace(candidate_id="candidate-source-gap")
    selection_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="reference_oscillator",
        basis_candidates=[candidate],
        ranked_candidates=[candidate],
    )

    should_run, signals = parameter_module._should_trigger_semantic_auditor(
        selection_result=selection_result,
        parser_meta={"section_rule": "reference_oscillator"},
        cfg=cfg,
        selected_kb=None,
        range_result=None,
        error_result=None,
        u_result=None,
        source_anomaly={"detected": True, "reason": "parser/source anomaly"},
        semantic_ambiguity=None,
    )

    assert should_run is False
    assert "candidate_gap" in signals


def test_semantic_auditor_triggers_for_fallback_cross_target_review(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="live",
        llm_suspicion_min_signals=1,
    )
    selection_result = _daily_error_selection_result()

    should_run, signals = parameter_module._should_trigger_semantic_auditor(
        selection_result=selection_result,
        parser_meta={"section_rule": "period_accuracy"},
        cfg=cfg,
        selected_kb=selection_result.selected[0],
        range_result={"status": "PASS"},
        error_result={"status": "PASS"},
        u_result={"status": "REVIEW", "reason": "candidate uncertainty belongs to range capability and is not directly comparable"},
        source_anomaly={"detected": False, "reason": ""},
        semantic_ambiguity=None,
    )

    assert should_run is True
    assert "fallback_cross_target" in signals


def test_semantic_auditor_does_not_trigger_for_uncertainty_only_review_without_replayable_signal(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="live",
        llm_suspicion_min_signals=1,
    )
    selection_result = _make_selection_result(
        selected_candidate_id="candidate-exact",
        rationale="selected candidate-exact",
        semantic_target="reference_oscillator",
    )

    should_run, signals = parameter_module._should_trigger_semantic_auditor(
        selection_result=selection_result,
        parser_meta={"section_rule": "reference_oscillator"},
        cfg=cfg,
        selected_kb=SimpleNamespace(capability_target="reference_oscillator"),
        range_result={"status": "PASS"},
        error_result={"status": "PASS"},
        u_result={"status": "REVIEW", "reason": "representation mismatch"},
        source_anomaly={"detected": False, "reason": ""},
        semantic_ambiguity={"detected": True, "reason": "reference probe ambiguous"},
    )

    assert should_run is False
    assert signals == ["uncertainty_only_incompatibility"]


def test_validate_planner_decision_reports_client_missing():
    ok, reason, sanitized = validate_planner_decision(
        request_result=PlannerRequestResult(
            request_ok=False,
            error_stage="client_missing",
            error_code="MissingAPIKey",
            error_message="api key missing",
        ),
        semantic_whitelist=("frequency_accuracy",),
        raw_field_summary=[],
        candidate_summaries=[],
    )

    assert not ok
    assert sanitized is None
    assert reason == "planner client unavailable"


def test_validate_planner_decision_reports_request_failure():
    ok, reason, sanitized = validate_planner_decision(
        request_result=PlannerRequestResult(
            request_ok=False,
            error_stage="request_invoke",
            error_code="AuthenticationError",
            error_message="unauthorized",
        ),
        semantic_whitelist=("frequency_accuracy",),
        raw_field_summary=[],
        candidate_summaries=[],
    )

    assert not ok
    assert sanitized is None
    assert reason == "planner request failed"


def test_request_planner_decision_returns_client_missing_when_no_client():
    result = request_planner_decision(
        llm_client=None,
        criterion="JJF 1471-2014",
        param_name="RF CW Frequency",
        section_label="RF CW Frequency",
        parser_meta={},
        normalized_fields={},
        raw_field_summary=[],
        deterministic_rationale="unknown semantic",
        candidate_summaries=[],
        semantic_whitelist=("frequency_accuracy",),
    )

    assert not result.request_ok
    assert result.error_stage == "client_missing"
    assert result.error_code == "ClientUnavailable"


def test_request_planner_decision_captures_structured_llm_error():
    class FailingPlannerLLM:
        def invoke_structured(self, user_prompt, output_model, system_prompt=None):
            raise LLMInvocationError(
                "Error generating structured response: unauthorized",
                error_code="AuthenticationError",
                error_stage="request_invoke",
                error_type="AuthenticationError",
                error_message="unauthorized",
            )

    result = request_planner_decision(
        llm_client=FailingPlannerLLM(),
        criterion="JJF 1471-2014",
        param_name="RF CW Frequency",
        section_label="RF CW Frequency",
        parser_meta={},
        normalized_fields={},
        raw_field_summary=[],
        deterministic_rationale="unknown semantic",
        candidate_summaries=[],
        semantic_whitelist=("frequency_accuracy",),
    )

    assert not result.request_ok
    assert result.error_stage == "request_invoke"
    assert result.error_code == "AuthenticationError"


def test_planner_output_model_rejects_invalid_schema_values():
    output_model = _build_planner_output_model(
        semantic_whitelist=("frequency_accuracy", "period_accuracy"),
        raw_field_summary=[
            {"header": "标准值 (Reference)", "value": "10 MHz"},
            {"header": "U (k=2)", "value": "0.08 dB"},
        ],
        candidate_summaries=[{"candidate_id": "known-id"}],
    )

    valid = output_model(
        action="suggest",
        semantic_target="frequency_accuracy",
        field_bindings={"reference_value": "标准值 (Reference)", "cert_u": "U (k=2)"},
        candidate_slots=[1],
        confidence=0.9,
        reason="valid",
    )
    assert valid.semantic_target == "frequency_accuracy"

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            semantic_target="not_allowed",
            field_bindings={"reference_value": "标准值 (Reference)"},
            candidate_slots=[1],
            confidence=0.9,
            reason="bad semantic",
        )

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            semantic_target="frequency_accuracy",
            field_bindings={"reference_value": "不存在的列"},
            candidate_slots=[1],
            confidence=0.9,
            reason="bad header",
        )

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            semantic_target="frequency_accuracy",
            field_bindings={"reference_value": "标准值 (Reference)"},
            candidate_slots=[9],
            confidence=0.9,
            reason="bad candidate",
        )


def test_request_planner_decision_rejects_invalid_candidate_via_structured_schema():
    result = request_planner_decision(
        llm_client=FakePlannerLLM(
            {
                "action": "suggest",
                "semantic_target": "frequency_accuracy",
                "field_bindings": {"reference_value": "标准值 (Reference)"},
                "candidate_slots": [9],
                "confidence": 0.92,
                "reason": "invalid candidate",
            }
        ),
        criterion="JJF 1471-2014",
        param_name="RF CW Frequency",
        section_label="RF CW Frequency",
        parser_meta={},
        normalized_fields={},
        raw_field_summary=[{"header": "标准值 (Reference)", "value": "10 MHz"}],
        deterministic_rationale="unknown semantic",
        candidate_summaries=[{"candidate_id": "known-id"}],
        semantic_whitelist=("frequency_accuracy",),
    )

    assert not result.request_ok
    assert result.error_stage == "structured_parse"


def test_planner_slot_context_and_coercion_work_without_global_dictionary():
    raw_field_summary = [
        {"header": "标准值 (Reference)", "value": "10 MHz"},
        {"header": "U (k=2)", "value": "0.08 dB"},
    ]
    candidate_summaries = [
        {"candidate_id": "known-id", "measured": "频率", "capability_target": "frequency_accuracy"},
        {"candidate_id": "backup-id", "measured": "频率", "capability_target": "frequency_accuracy"},
    ]
    slot_context = _build_planner_slot_context(
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    assert slot_context["header_slots"] == [
        {"slot": 1, "header": "标准值 (Reference)", "value": "10 MHz"},
        {"slot": 2, "header": "U (k=2)", "value": "0.08 dB"},
    ]
    assert slot_context["candidate_slots"] == [
        {"slot": 1, "candidate_id": "known-id", "measured": "频率", "capability_target": "frequency_accuracy"},
        {"slot": 2, "candidate_id": "backup-id", "measured": "频率", "capability_target": "frequency_accuracy"},
    ]

    output_model = _build_planner_slot_output_model(
        semantic_whitelist=("frequency_accuracy",),
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    decision = output_model(
        action="suggest",
        semantic_target="frequency_accuracy",
        field_bindings={"reference_value": 1, "cert_u": 2},
        candidate_slots=[2],
        confidence=0.9,
        reason="slot based plan",
    )
    coerced = _coerce_planner_slot_decision(
        decision,
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )
    assert coerced is not None
    assert coerced.field_bindings == {
        "reference_value": "标准值 (Reference)",
        "cert_u": "U (k=2)",
    }
    assert coerced.candidate_ids == ["backup-id"]

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            semantic_target="frequency_accuracy",
            field_bindings={"reference_value": 3},
            candidate_slots=[1],
            confidence=0.9,
            reason="invalid header slot",
        )

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            semantic_target="frequency_accuracy",
            field_bindings={"reference_value": 1},
            candidate_slots=[9],
            confidence=0.9,
            reason="invalid candidate slot",
        )


def test_describe_llm_exception_classifies_structured_parse():
    details = describe_llm_exception(ValueError("JSON schema parse failed"), default_stage="request_invoke")
    assert details["error_stage"] == "structured_parse"
    assert details["error_code"] == "StructuredParseError"


def test_low_confidence_without_nominated_match_is_rejected(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live", parameter_planner_confidence_threshold=0.85)
    decision = PlannerDecision(
        action="suggest",
        semantic_target="frequency_accuracy",
        candidate_ids=["candidate-1"],
        confidence=0.6,
        reason="low confidence",
    )
    deterministic_result = _make_selection_result(rationale="unknown semantic", semantic_target="unknown")
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-other",
        rationale="selected candidate-other",
        semantic_target="frequency_accuracy",
    )

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=_standard_parser_meta(),
        validation_ok=True,
        replay_used_planner_candidates=False,
        fallback_reason="",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert not allowed
    assert reason == "planner replay fell outside nominated candidates without fallback reason"
    assert assessment.hard_blockers == ["planner replay fell outside nominated candidates without fallback reason"]
    assert assessment.recommended_takeover is False


def test_low_confidence_nominated_hit_can_still_take_over_when_replay_improves(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live", parameter_planner_confidence_threshold=0.85)
    decision = PlannerDecision(
        action="suggest",
        semantic_target="frequency_accuracy",
        candidate_ids=["candidate-carrier-frequency"],
        confidence=0.62,
        reason="formal replay confirmed the nominated carrier-frequency candidate",
    )
    deterministic_result = _make_selection_result(rationale="unknown semantic", semantic_target="unknown")
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-carrier-frequency",
        rationale="selected candidate-carrier-frequency",
        semantic_target="frequency_accuracy",
    )

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=_standard_parser_meta(),
        validation_ok=True,
        replay_used_planner_candidates=True,
        fallback_reason="",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert allowed
    assert reason == "planner live takeover allowed"
    assert assessment.score >= assessment.threshold
    assert assessment.nominated_match is True
    assert assessment.confidence_above_threshold is False


def test_nonstandard_parser_source_rejects_takeover_even_with_nominated_hit(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live", parameter_planner_confidence_threshold=0.85)
    decision = PlannerDecision(
        action="suggest",
        semantic_target="reference_oscillator",
        candidate_ids=["candidate-reference"],
        confidence=0.9,
        reason="planner found the right candidate",
    )
    deterministic_result = _make_selection_result(rationale="unknown semantic", semantic_target="unknown")
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-reference",
        rationale="selected candidate-reference",
        semantic_target="reference_oscillator",
    )
    parser_meta = _standard_parser_meta()
    parser_meta["parse_source"] = "flat_text_reference_oscillator"

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=parser_meta,
        validation_ok=True,
        replay_used_planner_candidates=True,
        fallback_reason="",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert not allowed
    assert reason == "planner replay improvement score 3 below required score 5"
    assert assessment.parser_risk == "high"
    assert "nonstandard parser source: flat_text_reference_oscillator" in assessment.penalties


def test_unknown_section_rule_and_missing_bound_headers_reduce_score_below_threshold(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live", parameter_planner_confidence_threshold=0.85)
    decision = PlannerDecision(
        action="suggest",
        semantic_target="frequency_accuracy",
        field_bindings={"reference_value": "Reference"},
        candidate_ids=["candidate-reference"],
        confidence=0.9,
        reason="planner rebound the reference field",
    )
    deterministic_result = _make_selection_result(rationale="unknown semantic", semantic_target="unknown")
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-reference",
        rationale="selected candidate-reference",
        semantic_target="frequency_accuracy",
    )
    parser_meta = _standard_parser_meta()
    parser_meta["section_rule"] = "unknown"
    parser_meta["header_rules"] = {"measure_value": "Measured", "error_value": "Error"}

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=parser_meta,
        validation_ok=True,
        replay_used_planner_candidates=True,
        fallback_reason="",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert not allowed
    assert reason == "planner replay improvement score 3 below required score 4"
    assert assessment.parser_risk == "medium"
    assert any("missing parser header rules" in penalty for penalty in assessment.penalties)


def test_same_basis_fallback_can_take_over_when_score_meets_threshold(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live", parameter_planner_confidence_threshold=0.85)
    decision = PlannerDecision(
        action="suggest",
        semantic_target="frequency_accuracy",
        candidate_ids=["candidate-timebase"],
        confidence=0.9,
        reason="planner suggested a nearby same-basis candidate",
    )
    deterministic_result = _make_selection_result(rationale="unknown semantic", semantic_target="unknown")
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-carrier",
        rationale="selected candidate-carrier",
        semantic_target="frequency_accuracy",
    )

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=_standard_parser_meta(),
        validation_ok=True,
        replay_used_planner_candidates=False,
        fallback_reason="planner nominated candidates produced no compatible candidate",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert allowed
    assert reason == "planner live takeover allowed"
    assert assessment.fallback_used is True
    assert assessment.nominated_match is False
    assert assessment.score == assessment.threshold


def test_same_basis_gap_resolution_boosts_live_takeover_score(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live", parameter_planner_confidence_threshold=0.85)
    decision = PlannerDecision(
        action="suggest",
        semantic_target="frequency_accuracy",
        confidence=0.9,
        reason="planner suggested same-basis fallback",
    )
    deterministic_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="frequency_accuracy",
    )
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-carrier",
        rationale="selected candidate-carrier",
        semantic_target="frequency_accuracy",
    )

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=_standard_parser_meta(),
        validation_ok=True,
        replay_used_planner_candidates=False,
        fallback_reason="planner candidate ids unavailable",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert allowed
    assert reason == "planner live takeover allowed"
    assert "replay resolved same-basis candidate gap" in assessment.improvements
    assert assessment.score >= assessment.threshold


def test_planner_replay_derives_target_preference_from_nominated_candidates():
    criterion = "JJF 2196-2025"
    kb_items = [
        {
            "file_code": "JJF 2196-2025",
            "measured": "频率",
            "measure_range_text": "10 Hz～18 GHz",
            "uncertainty": {"type": "UREL", "value_display": "Urel=6.5×10⁻¹¹"},
        }
    ]

    same_basis_pool = parameter_module._planner_same_basis_candidate_pool(kb_items=kb_items, criterion=criterion)
    candidate_id = same_basis_pool[0][0].candidate_id

    assert (
        parameter_module._planner_candidate_target_preference(
            same_basis_pool=same_basis_pool,
            candidate_ids=[candidate_id],
        )
        == "frequency_accuracy"
    )


def test_shadow_mode_never_takes_over_but_preserves_assessment(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="shadow")
    decision = PlannerDecision(
        action="suggest",
        semantic_target="frequency_accuracy",
        candidate_ids=["candidate-carrier-frequency"],
        confidence=0.62,
        reason="formal replay confirmed the nominated carrier-frequency candidate",
    )
    deterministic_result = _make_selection_result(rationale="unknown semantic", semantic_target="unknown")
    retry_result = _make_selection_result(
        selected_candidate_id="candidate-carrier-frequency",
        rationale="selected candidate-carrier-frequency",
        semantic_target="frequency_accuracy",
    )

    assessment = assess_replay_improvement(
        selection_result=deterministic_result,
        retry_result=retry_result,
        decision=decision,
        parser_meta=_standard_parser_meta(),
        validation_ok=True,
        replay_used_planner_candidates=True,
        fallback_reason="",
        cfg=cfg,
    )
    allowed, reason, assessment = live_mode_allows_takeover(cfg=cfg, assessment=assessment)

    assert not allowed
    assert reason == "planner mode is not live"
    assert assessment.recommended_takeover is True


def test_carrier_frequency_deviation_uses_error_value_for_range_probe():
    kb_entry = {
        "file_code": "JJF 1471-2014",
        "measured": "载波频率偏差",
        "measure_range_text": "（0～100）Hz",
        "uncertainty": {"type": "U", "value_display": "U=4.8Hz"},
    }

    capability = infer_kb_capability(kb_entry)

    assert capability is not None
    assert capability.condition_axis is None
    assert parameter_module._resolve_range_probe_value(capability, "1207.14 MHz", "-41.73 Hz") == "41.73 Hz"


def test_shadow_mode_records_assessment_for_rf_cw_frequency(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="shadow")
    criterion = "JJF 1471-2014 全球导航卫星系统（GNSS）信号模拟器校准规范"
    param = _load_fixture_param("rf_cw_frequency")
    kb_items = [
        {
            "file_code": "JJF 1471-2014",
            "measured": "时基准确度",
            "measure_range_text": "10MHz",
            "uncertainty": {"type": "UREL", "value_display": "Urel=1×10⁻⁹"},
        },
        {
            "file_code": "JJF 1471-2014",
            "measured": "载波频率偏差",
            "measure_range_text": "（0～100）Hz",
            "uncertainty": {"type": "U", "value_display": "U=4.8Hz"},
        },
    ]
    candidate_ids = [candidate.candidate_id for candidate in _same_basis_candidates(kb_items, criterion)]
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "semantic_target": "frequency_accuracy",
            "candidate_slots": [1, 2],
            "confidence": 0.93,
            "reason": "RF CW Frequency is carrier frequency deviation",
        }
    )

    execution = _run_planner_case(
        cfg=cfg,
        llm_client=llm,
        llm_client_error=None,
        param=param,
        kb_items=kb_items,
        criterion=criterion,
    )

    trace = execution.trace
    assert execution.selected_candidate is None
    assert "`planner_mode` shadow" in execution.note
    assert "`planner_takeover_score`" in execution.note
    assert trace["formal_replay"]["selected_candidate_id"] == candidate_ids[1]
    assert trace["assessment"]["recommended_takeover"] is True
    assert trace["live"]["allowed"] is False
    assert trace["summary"]["planner_takeover_basis"] == "deterministic_retained"
    assert llm.calls == 1


def test_live_mode_prefers_carrier_frequency_candidate_over_timebase(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live")
    criterion = "JJF 1471-2014 全球导航卫星系统（GNSS）信号模拟器校准规范"
    param = _load_fixture_param("rf_cw_frequency")
    kb_items = [
        {
            "file_code": "JJF 1471-2014",
            "measured": "时基准确度",
            "measure_range_text": "10MHz",
            "uncertainty": {"type": "UREL", "value_display": "Urel=1×10⁻⁹"},
        },
        {
            "file_code": "JJF 1471-2014",
            "measured": "载波频率偏差",
            "measure_range_text": "（0～100）Hz",
            "uncertainty": {"type": "U", "value_display": "U=4.8Hz"},
        },
    ]
    candidate_ids = [candidate.candidate_id for candidate in _same_basis_candidates(kb_items, criterion)]
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "semantic_target": "frequency_accuracy",
            "candidate_slots": [1, 2],
            "confidence": 0.94,
            "reason": "RF CW Frequency is carrier frequency deviation",
        }
    )

    execution = _run_planner_case(
        cfg=cfg,
        llm_client=llm,
        llm_client_error=None,
        param=param,
        kb_items=kb_items,
        criterion=criterion,
    )

    trace = execution.trace
    assert trace["live"]["allowed"] is True
    assert trace["assessment"]["recommended_takeover"] is True
    assert trace["formal_replay"]["used_planner_candidates"] is True
    assert trace["formal_replay"]["selected_candidate_id"] == candidate_ids[1]
    assert trace["summary"]["planner_takeover_basis"] == "nominated_replay"
    assert trace["final"]["selection_source"] == "formal_replay"
    assert execution.selected_candidate is not None


def test_live_mode_stabilizes_power_resolution_candidate(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="live")
    criterion = "JJF 1471-2014 全球导航卫星系统（GNSS）信号模拟器校准规范"
    param = _load_fixture_param("power_resolution")
    kb_items = [
        {
            "file_code": "JJF 1471-2014",
            "measured": "功率范围",
            "measure_range_text": "(-130～-20)dBm，1000MHz～3000MHz",
            "uncertainty": {"type": "U", "value_display": "U=(0.15～0.4)dB"},
        },
        {
            "file_code": "JJF 1471-2014",
            "measured": "功率分辨力",
            "measure_range_text": "(0.1～2)dB",
            "uncertainty": {"type": "U", "value_display": "U=0.02dB"},
        },
    ]
    candidate_ids = [candidate.candidate_id for candidate in _same_basis_candidates(kb_items, criterion)]
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "semantic_target": "power_accuracy",
            "candidate_slots": [1, 2],
            "confidence": 0.92,
            "reason": "Power Resolution belongs to the power capability family",
        }
    )

    execution = _run_planner_case(
        cfg=cfg,
        llm_client=llm,
        llm_client_error=None,
        param=param,
        kb_items=kb_items,
        criterion=criterion,
    )

    trace = execution.trace
    assert trace["live"]["allowed"] is True
    assert trace["assessment"]["recommended_takeover"] is True
    assert trace["formal_replay"]["used_planner_candidates"] is True
    assert trace["formal_replay"]["selected_candidate_id"] == candidate_ids[1]
    assert trace["summary"]["planner_takeover_basis"] == "nominated_replay"


def test_shadow_mode_reports_client_init_failure_reason(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="shadow")
    criterion = "JJF 1471-2014 全球导航卫星系统（GNSS）信号模拟器校准规范"
    param = _load_fixture_param("rf_cw_frequency")
    kb_items = [
        {
            "file_code": "JJF 1471-2014",
            "measured": "载波频率偏差",
            "measure_range_text": "0～100Hz",
            "uncertainty": {"type": "U", "value_display": "U=4.8Hz"},
        }
    ]

    execution = _run_planner_case(
        cfg=cfg,
        llm_client=None,
        llm_client_error={
            "error_stage": "client_init",
            "error_code": "DependencyMissing",
            "error_message": "ModuleNotFoundError(langchain_openai)",
        },
        param=param,
        kb_items=kb_items,
        criterion=criterion,
    )

    assert "planner init failed: ModuleNotFoundError(langchain_openai)" in execution.note
    assert execution.trace["client"]["init_error"]["error_stage"] == "client_init"
    assert execution.trace["request"]["error_stage"] == "client_missing"


def test_shadow_mode_reports_api_key_missing_reason(tmp_path):
    cfg = build_config(tmp_path, parameter_planner_mode="shadow", api_key="")
    criterion = "JJF 1471-2014 全球导航卫星系统（GNSS）信号模拟器校准规范"
    param = _load_fixture_param("rf_cw_frequency")
    kb_items = [
        {
            "file_code": "JJF 1471-2014",
            "measured": "载波频率偏差",
            "measure_range_text": "0～100Hz",
            "uncertainty": {"type": "U", "value_display": "U=4.8Hz"},
        }
    ]

    execution = _run_planner_case(
        cfg=cfg,
        llm_client=None,
        llm_client_error=None,
        param=param,
        kb_items=kb_items,
        criterion=criterion,
    )

    assert "planner client unavailable: api key missing" in execution.note
    assert execution.trace["client"]["init_error"]["error_code"] == "MissingAPIKey"


def test_write_planner_trace_sidecar(tmp_path):
    cfg = build_config(tmp_path)
    output_path = parameter_module._write_planner_trace_sidecar(
        json_file=str(tmp_path / "sample.json"),
        cfg=cfg,
        traces=[{"trace_id": "abc123", "summary": {"planner_action": "suggest"}}],
    )

    assert output_path is not None
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["trace_count"] == 1
    assert payload["traces"][0]["trace_id"] == "abc123"


def test_semantic_auditor_shadow_records_trace_without_mutating_selection(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="shadow",
        llm_suspicion_min_signals=2,
    )
    selection_result = _daily_error_selection_result()
    parser_meta = {
        "parse_source": "html_table",
        "section_rule": "period_accuracy",
        "header_rules": {
            "error_value": "日差",
            "limit_value": "允许误差",
            "cert_u": "U",
        },
        "unit_inherited": True,
    }
    param = {
        "param_name": "2 日差(Error Per Day)",
        "__cert_index": 1,
        "数据明细": {
            "日差": "-0.65 s/d",
            "允许误差": "±4320.00 s/d",
            "U": "0.03 s/d",
        },
        "__parameter_contract": {
            "semantic_target": "period_accuracy",
            "error_value": "-0.65 s/d",
            "limit_value": "±4320.00 s/d",
            "cert_u": "0.03 s/d",
            "unit_family": "time",
        },
    }
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_semantic_target": "period_accuracy",
            "suggested_semantic_subtype": "",
            "suggested_unit_family": "time",
            "suggested_candidate_target_preference": "period_range",
            "suspected_issue_type": "cross_target_fallback",
            "confidence": 0.94,
            "reason": "target fallback suggests capability mismatch",
        }
    )

    execution = parameter_module._run_parameter_semantic_auditor(
        llm_client=llm,
        llm_client_error=None,
        cfg=cfg,
        criterion="JJF 2195-2025",
        batch_index=1,
        param=param,
        param_name=param["param_name"],
        selection_result=selection_result,
        parser_meta=parser_meta,
        normalized_fields={
            "error_value": "-0.65 s/d",
            "limit_value": "±4320.00 s/d",
            "cert_u": "0.03 s/d",
        },
        point_blob="日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        selection_context="点位:1d 测量值:-0.65 s/d 误差:-0.65 s/d 日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        selected_kb=selection_result.selected[0],
        kb_items=[
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": "(0～10)min",
                "uncertainty": {"type": "U", "value_display": "U=0.007s"},
            },
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": ">10 min～24 h",
                "uncertainty": {"type": "U", "value_display": "U=0.011s"},
            },
        ],
        measure_val="-0.65 s/d",
        reference_val="",
        error_val="-0.65 s/d",
        point_value="1d",
        range_result={"status": "PASS"},
        error_result={"status": "PASS"},
        u_result={
            "status": "REVIEW",
            "reason": "period_accuracy fallback to period_range candidate; candidate uncertainty belongs to range capability and is not directly comparable",
        },
        budget=parameter_module.LLMAuditorBudget(max_calls=3),
    )

    assert llm.calls == 1
    assert execution.trace["trace_kind"] == "semantic_auditor"
    assert execution.selection_result.audit.selected_target_relation == "fallback_cross_target"
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_mode"] == "shadow"
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_takeover_basis"] == "shadow_retained"
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_suggested_target"] == "period_accuracy"
    assert execution.applied is False
    assert "`semantic_auditor_mode` shadow" in execution.note


def test_semantic_auditor_skips_rows_already_repaired_by_parser_fallback(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="shadow",
        llm_suspicion_min_signals=1,
    )
    selection_result = _daily_error_selection_result()
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_semantic_target": "period_accuracy",
            "suggested_unit_family": "time",
            "suggested_candidate_target_preference": "period_range",
            "suspected_issue_type": "cross_target_fallback",
            "confidence": 0.95,
            "reason": "should not be used",
        }
    )

    execution = parameter_module._run_parameter_semantic_auditor(
        llm_client=llm,
        llm_client_error=None,
        cfg=cfg,
        criterion="JJF 2195-2025",
        batch_index=1,
        param={"param_name": "2 日差(Error Per Day)", "__parameter_contract": {}},
        param_name="2 日差(Error Per Day)",
        selection_result=selection_result,
        parser_meta={"section_rule": "period_accuracy", "llm_fallback_applied": True},
        normalized_fields={},
        point_blob="日差 -0.65 s/d",
        selection_context="日差 -0.65 s/d",
        selected_kb=selection_result.selected[0],
        kb_items=[],
        measure_val="-0.65 s/d",
        reference_val="",
        error_val="-0.65 s/d",
        point_value="1d",
        range_result={"status": "PASS"},
        error_result={"status": "PASS"},
        u_result={"status": "REVIEW", "reason": "candidate uncertainty belongs to range capability and is not directly comparable"},
        budget=parameter_module.LLMAuditorBudget(max_calls=3),
    )

    assert llm.calls == 0
    assert execution.trace is None
    assert execution.note == ""


def test_semantic_auditor_live_takeover_replays_and_selects_generic_reference_oscillator(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="live",
        parameter_semantic_auditor_confidence_threshold=0.9,
        llm_suspicion_min_signals=1,
    )
    param = {
        "param_name": "2.1 相对频率偏差(Relative Frequency Deviation)",
        "__cert_index": 1,
        "__parameter_contract": {
            "semantic_target": "reference_oscillator",
            "reference_value": "10 MHz",
            "measure_value": "10 MHz",
            "error_value": "1.0×10^-12",
            "cert_u": "3.0×10^-12",
            "unit_family": "frequency",
        },
    }
    selection_result = _make_selection_result(
        rationale="same basis but no compatible candidate",
        semantic_target="reference_oscillator",
        semantic_subtype="relative_frequency_deviation",
        notes=("unit family mismatch: unknown",),
        basis_candidates=[],
        ranked_candidates=[],
    )
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_semantic_target": "reference_oscillator",
            "suggested_semantic_subtype": "relative_frequency_deviation",
            "suggested_unit_family": "frequency",
            "suggested_candidate_target_preference": "reference_oscillator",
            "suspected_issue_type": "candidate_gap",
            "confidence": 0.96,
            "reason": "generic oscillator candidate matches relative frequency deviation metric",
        }
    )
    kb_items = [
        {
            "file_code": "JJG 841-2017",
            "measured": "晶振",
            "measure_range_text": "1 MHz,2 MHz,5 MHz,10 MHz",
            "uncertainty": {"type": "Urel", "value_display": "Urel=3×10⁻¹²"},
        }
    ]

    execution = parameter_module._run_parameter_semantic_auditor(
        llm_client=llm,
        llm_client_error=None,
        cfg=cfg,
        criterion="JJG 841-2017",
        batch_index=1,
        param=param,
        param_name=param["param_name"],
        selection_result=selection_result,
        parser_meta={"section_rule": "reference_oscillator"},
        normalized_fields={
            "reference_value": "10 MHz",
            "measure_value": "10 MHz",
            "error_value": "1.0×10^-12",
            "cert_u": "3.0×10^-12",
        },
        point_blob="10 MHz 相对频率偏差 1.0×10^-12 U=3.0×10^-12",
        selection_context="点位:10 MHz 测量值:10 MHz 标准值:10 MHz 误差:1.0×10^-12 10 MHz 相对频率偏差 1.0×10^-12 U=3.0×10^-12",
        selected_kb=None,
        kb_items=kb_items,
        measure_val="10 MHz",
        reference_val="10 MHz",
        error_val="1.0×10^-12",
        point_value="10 MHz",
        range_result=None,
        error_result=None,
        u_result=None,
        budget=parameter_module.LLMAuditorBudget(max_calls=3),
    )

    assert execution.applied is True
    assert execution.selected_candidate is not None
    assert execution.selection_result.selected_candidate_id is not None
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_takeover_basis"] == "live_replay_takeover"
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_replay_selected_candidate_id"]
    assert execution.trace["live"]["allowed"] is True


def test_semantic_auditor_live_rejects_replay_without_material_improvement(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="live",
        parameter_semantic_auditor_confidence_threshold=0.9,
        llm_suspicion_min_signals=2,
    )
    selection_result = _daily_error_selection_result()
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_semantic_target": "period_accuracy",
            "suggested_semantic_subtype": "",
            "suggested_unit_family": "time",
            "suggested_candidate_target_preference": "period_range",
            "suspected_issue_type": "cross_target_fallback",
            "confidence": 0.95,
            "reason": "same fallback target remains the best available choice",
        }
    )
    kb_items = [
        {
            "file_code": "JJF 2195",
            "measured": "时间",
            "measure_range_text": "(0～10)min",
            "uncertainty": {"type": "U", "value_display": "U=0.007s"},
        },
        {
            "file_code": "JJF 2195",
            "measured": "时间",
            "measure_range_text": ">10 min～24 h",
            "uncertainty": {"type": "U", "value_display": "U=0.011s"},
        },
    ]

    execution = parameter_module._run_parameter_semantic_auditor(
        llm_client=llm,
        llm_client_error=None,
        cfg=cfg,
        criterion="JJF 2195-2025",
        batch_index=1,
        param={"param_name": "2 日差(Error Per Day)", "__cert_index": 1, "__parameter_contract": {"semantic_target": "period_accuracy"}},
        param_name="2 日差(Error Per Day)",
        selection_result=selection_result,
        parser_meta={"section_rule": "period_accuracy"},
        normalized_fields={"error_value": "-0.65 s/d", "limit_value": "±4320.00 s/d", "cert_u": "0.03 s/d"},
        point_blob="日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        selection_context="点位:1d 测量值:-0.65 s/d 误差:-0.65 s/d 日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        selected_kb=selection_result.selected[0],
        kb_items=kb_items,
        measure_val="-0.65 s/d",
        reference_val="",
        error_val="-0.65 s/d",
        point_value="1d",
        range_result={"status": "PASS"},
        error_result={"status": "PASS"},
        u_result={"status": "REVIEW", "reason": "candidate uncertainty belongs to range capability and is not directly comparable"},
        budget=parameter_module.LLMAuditorBudget(max_calls=3),
    )

    assert execution.applied is False
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_takeover_basis"] == "live_replay_rejected"
    assert execution.trace["live"]["allowed"] is False


def test_semantic_auditor_live_low_confidence_does_not_attempt_takeover(tmp_path):
    cfg = build_config(
        tmp_path,
        parameter_semantic_auditor_mode="live",
        parameter_semantic_auditor_confidence_threshold=0.9,
        llm_suspicion_min_signals=2,
    )
    selection_result = _daily_error_selection_result()
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_semantic_target": "period_accuracy",
            "suggested_semantic_subtype": "",
            "suggested_unit_family": "time",
            "suggested_candidate_target_preference": "period_range",
            "suspected_issue_type": "cross_target_fallback",
            "confidence": 0.70,
            "reason": "confidence too low for takeover",
        }
    )

    execution = parameter_module._run_parameter_semantic_auditor(
        llm_client=llm,
        llm_client_error=None,
        cfg=cfg,
        criterion="JJF 2195-2025",
        batch_index=1,
        param={"param_name": "2 日差(Error Per Day)", "__cert_index": 1, "__parameter_contract": {"semantic_target": "period_accuracy"}},
        param_name="2 日差(Error Per Day)",
        selection_result=selection_result,
        parser_meta={"section_rule": "period_accuracy"},
        normalized_fields={"error_value": "-0.65 s/d", "limit_value": "±4320.00 s/d", "cert_u": "0.03 s/d"},
        point_blob="日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        selection_context="点位:1d 测量值:-0.65 s/d 误差:-0.65 s/d 日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        selected_kb=selection_result.selected[0],
        kb_items=[],
        measure_val="-0.65 s/d",
        reference_val="",
        error_val="-0.65 s/d",
        point_value="1d",
        range_result={"status": "PASS"},
        error_result={"status": "PASS"},
        u_result={"status": "REVIEW", "reason": "candidate uncertainty belongs to range capability and is not directly comparable"},
        budget=parameter_module.LLMAuditorBudget(max_calls=3),
    )

    assert execution.applied is False
    assert execution.selection_result.audit.semantic_auditor_summary["semantic_auditor_takeover_basis"] == "shadow_retained"


def test_request_semantic_auditor_accepts_suggested_target_within_whitelist():
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_semantic_target": "period_accuracy",
            "suggested_semantic_subtype": "",
            "suggested_unit_family": "time",
            "suggested_candidate_target_preference": "period_range",
            "suspected_issue_type": "cross_target_fallback",
            "confidence": 0.91,
            "reason": "target mismatch suspected",
        }
    )
    request_result = request_semantic_auditor_decision(
        llm_client=llm,
        criterion="JJF 2195-2025",
        param_name="2 日差(Error Per Day)",
        section_label="2 日差(Error Per Day)",
        point_text="日差 -0.65 s/d 允许误差 ±4320.00 s/d",
        parser_meta={"section_rule": "period_accuracy"},
        normalized_fields={"error_value": "-0.65 s/d"},
        parameter_contract={"semantic_target": "period_accuracy"},
        selection_audit={"selected_target_relation": "fallback_cross_target"},
        candidate_summaries=[{"candidate_id": "c1", "capability_target": "period_range"}],
        semantic_whitelist=("period_accuracy", "period_range"),
        suspicion_signals=("fallback_cross_target", "uncertainty_only_incompatibility"),
    )
    ok, reason, sanitized = validate_semantic_auditor_decision(
        request_result=request_result,
        semantic_whitelist=("period_accuracy", "period_range"),
        candidate_summaries=[{"candidate_id": "c1", "capability_target": "period_range"}],
    )

    assert ok
    assert reason == "semantic auditor suggestion accepted"
    assert sanitized is not None
    assert sanitized.suggested_semantic_target == "period_accuracy"


def test_kb_capability_auditor_shadow_returns_structured_suggestion(tmp_path):
    cfg = build_config(tmp_path, kb_capability_auditor_mode="shadow", kb_capability_auditor_max_items=1)
    llm = FakePlannerLLM(
        {
            "action": "suggest",
            "suggested_capability_target": "period_accuracy",
            "suggested_result_quantity": "period_error_or_value",
            "suggested_u_semantic_role": "accuracy_result_u",
            "confidence": 0.93,
            "reason": "s/d candidate behaves like time accuracy capability",
        }
    )

    audits = audit_kb_capability_candidates(
        llm_client=llm,
        cfg=cfg,
        candidate_summaries=[
            {
                "candidate_id": "JJG488|时间|(-100～100)s/d|U=0.011s/d",
                "measured": "时间",
                "capability_target": "period_range",
                "measure_range_text": "(-100～100)s/d",
                "u_text": "U=0.011s/d",
            }
        ],
        hit_examples_by_candidate={
            "JJG488|时间|(-100～100)s/d|U=0.011s/d": [
                {"param_name": "2 日差(Error Per Day)", "semantic_target": "period_accuracy"}
            ]
        },
        capability_target_whitelist=("period_accuracy", "period_range"),
    )

    assert llm.calls == 1
    assert audits[0]["accepted"] is True
    assert audits[0]["suggested_capability_target"] == "period_accuracy"
    assert audits[0]["suggested_u_semantic_role"] == "accuracy_result_u"
