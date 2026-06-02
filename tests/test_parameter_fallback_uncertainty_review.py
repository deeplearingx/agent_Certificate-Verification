import sys
import types
from types import SimpleNamespace


if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")
    pydantic_stub.BaseModel = object
    sys.modules["pydantic"] = pydantic_stub

if "chromadb" not in sys.modules:
    chromadb_stub = types.ModuleType("chromadb")

    class _PersistentClient:
        def __init__(self, *args, **kwargs):
            pass

    chromadb_stub.PersistentClient = _PersistentClient
    sys.modules["chromadb"] = chromadb_stub


from langchain_app.checks.parameter import parameter as parameter_module
from langchain_app.checks.parameter.semantic import select_basis_with_audit


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


def test_period_accuracy_fallback_period_range_skips_uncertainty_by_policy_when_numeric_checks_pass():
    selection_result = SimpleNamespace(
        cert_point=SimpleNamespace(semantic_target="period_accuracy", semantic_subtype=""),
        audit=SimpleNamespace(
            used_fallback_candidate_target=True,
            selected_target_relation="fallback_cross_target",
        ),
    )
    selected_kb = SimpleNamespace(
        capability_target="period_range",
        semantic_subtype="",
        source={
            "file_code": "JJF 2195",
            "measured": "时间间隔",
            "measure_range_text": ">10 min～24 h",
            "uncertainty": {"type": "U", "value_display": "U=0.007s"},
        },
    )

    gate = parameter_module._resolve_uncertainty_comparability(
        selection_result,
        selected_kb,
        cert_u="0.03 s/d",
        kb_u="U=0.007s",
        probe_value="24 h",
    )

    assert gate["comparable"] is False
    assert gate["decision"] == "review_skip"
    assert "candidate uncertainty belongs to range capability and is not directly comparable" in gate["reason"]

    evaluation = parameter_module._evaluate_selected_kb_results(
        selection_result=selection_result,
        selected_candidate=None,
        selected_kb=selected_kb,
        param={
            "param_name": "2 日差(Error Per Day)",
            "__parameter_contract": {
                "measure_value": "24 h",
                "reference_value": "24 h",
                "error_value": "-0.65 s/d",
                "limit_value": "±4320.00 s/d",
                "cert_u": "0.03 s/d",
            },
        },
        measure_val="24 h",
        reference_val="24 h",
        error_val="-0.65 s/d",
        cert_u="0.03 s/d",
    )

    assert evaluation["range_result"]["status"] == "PASS"
    assert evaluation["error_result"]["status"] == "PASS"
    assert evaluation["u_result"]["status"] == "PASS"
    assert evaluation["u_result"]["comparison_mode"] == "skip_compare_by_policy"
    assert "fallback_cross_target accepted by policy" in evaluation["u_result"]["reason"]


def test_period_accuracy_fallback_uncertainty_reason_still_classifies_as_semantic_ambiguity():
    reason = (
        "period_accuracy fallback to period_range candidate; "
        "candidate uncertainty belongs to range capability and is not directly comparable"
    )

    assert parameter_module._classify_review_reason(reason) == "semantic_ambiguity"
