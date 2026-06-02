from core.semantic_basis_selector import (
    FirstCandidateDecider,
    infer_kb_capability,
    infer_param_semantics,
    select_basis_with_audit,
    structured_prefilter,
)


def _jjg841_items():
    return [
        {"measured": "crystal", "measure_range_text": "1MHz,2MHz,5MHz,10MHz", "u_text": "Urel=3e-12"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(0.1Hz~100kHz)", "u_text": "U=0.2dB"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>100kHz~20MHz)", "u_text": "U=0.5dB"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>20MHz~2GHz)", "u_text": "U=1.0dB"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>2GHz~50GHz)", "u_text": "U=2dB"},
        {"measured": "frequency", "measure_range_text": "10Hz~50GHz", "u_text": "Urel=2e-11"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(10s~10us)", "u_text": "U=0.2dB"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(<10us~50ns)", "u_text": "U=0.5dB"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(<50ns~0.5ns)", "u_text": "U=1.0dB"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(<0.5ns~40ps)", "u_text": "U=1.5dB"},
        {"measured": "period", "measure_range_text": "40ps~10s", "u_text": "Urel=2e-11"},
    ]


def _jjg601_items():
    return [
        {"measured": "internal crystal output frequency", "measure_range_text": "10MHz", "u_text": "Urel=3e-12"},
        {"measured": "frequency", "measure_range_text": "relative frequency deviation: ±(1e-5~1e-10)", "u_text": "Urel=1e-11"},
        {"measured": "frequency", "measure_range_text": "warm-up characteristics: 1e-6~1e-11", "u_text": "Urel=7e-11"},
        {"measured": "output time interval", "measure_range_text": ">1ms~9999.9s", "u_text": "Urel=8.4e-8"},
    ]


def _jjg238_items():
    return [
        {"measured": "time interval", "measure_range_text": "10ns~1.5us", "u_text": "Urel=2.3%~0.58%"},
        {"measured": "time interval", "measure_range_text": ">=1.5us~24h", "u_text": "Urel=0.58%"},
        {"measured": "internal crystal output frequency", "measure_range_text": "1MHz,2MHz,5MHz,10MHz", "u_text": "Urel=3e-12"},
    ]


def _jjf1471_items():
    return [
        {"measured": "power_range", "measure_range_text": "(-130~-20)dBm", "u_text": "U=0.12dB"},
        {"measured": "power_deviation", "measure_range_text": "+/-(0.1~2)dB", "u_text": "U=0.12dB"},
        {"measured": "phase_noise", "measure_range_text": "(-130~-60)dBc/Hz", "u_text": "U=3dB"},
        {"measured": "error_vector_magnitude", "measure_range_text": "2%~20%", "u_text": "U=0.7%"},
        {"measured": "power_dynamic_range", "measure_range_text": "60dB~100dB", "u_text": "U=1dB"},
    ]


class ExactMatchDecider:
    def __init__(self, selected):
        self.selected = selected

    def decide(self, param, candidates):
        return {
            "selected_measured": list(self.selected),
            "rationale": f"Selected by mocked semantic judge for {param.task_intent}.",
        }


def test_layer1_structured_prefilter_routes_frequency_accuracy_to_frequency_only():
    param = infer_param_semantics(
        "frequency measurement error",
        "Reference: 10.00000000 MHz, Indicated: 9.99999998 MHz, Error: -0.00002 kHz, Limit: +/-0.0003 kHz",
        "0.00006 kHz",
    )
    candidates = structured_prefilter(param, _jjg841_items())
    assert [c.measured for c in candidates] == ["frequency"]


def test_layer1_structured_prefilter_routes_trigger_sensitivity_to_frequency_band_sensitivity_only():
    param = infer_param_semantics(
        "trigger sensitivity check",
        "Channel A, frequency 10 MHz, sensitivity 10 mV",
        "0.1 mV",
    )
    candidates = structured_prefilter(param, _jjg841_items())
    assert {c.measured for c in candidates} == {"frequency_measurement_range_and_input_sensitivity"}


def test_layer2_llm_decider_interface_can_choose_within_prefiltered_candidates():
    result = select_basis_with_audit(
        "relative frequency deviation",
        "relative frequency deviation at output frequency 10 MHz",
        "3e-10",
        _jjg841_items(),
        decider=ExactMatchDecider(["crystal"]),
    )
    assert [c.measured for c in result.selected] == ["crystal"]
    assert result.audit.prefiltered_candidates == ["crystal"]


def test_layer3_audit_contains_required_reasoning_dimensions():
    result = select_basis_with_audit(
        "period measurement error",
        "Reference: 0.1 us, Indicated: 0.1000000002 us, Error: 0.0000002 ns, Limit: +/-0.000003 ns",
        "0.0000006 ns",
        _jjg841_items(),
        decider=ExactMatchDecider(["period"]),
    )
    audit = result.audit
    assert audit.task_goal == "accuracy_check:period"
    assert audit.primary_quantity == "period"
    assert audit.unit_family == "time"
    assert audit.condition_axis is None
    assert audit.uncertainty_kind == "U"
    assert audit.selected_measured == ["period"]
    assert audit.rejected_measured == []
    assert "mocked semantic judge" in audit.rationale


def test_kb_capability_model_marks_frequency_band_axis():
    cap = infer_kb_capability(
        {
            "measured": "frequency_measurement_range_and_input_sensitivity",
            "measure_range_text": "1mV~1V(>20MHz~2GHz)",
            "u_text": "U=1.0dB",
        }
    )
    assert cap.capability_target == "input_sensitivity"
    assert cap.condition_axis == "frequency_band"


def test_first_candidate_decider_is_safe_default_for_prototype():
    result = select_basis_with_audit(
        "frequency measurement error",
        "Reference: 10.00000000 MHz, Indicated: 9.99999998 MHz, Error: -0.00002 kHz, Limit: +/-0.0003 kHz",
        "0.00006 kHz",
        _jjg841_items(),
        decider=FirstCandidateDecider(),
    )
    assert [c.measured for c in result.selected] == ["frequency"]


def test_cross_domain_prefilter_keeps_power_accuracy_family_together():
    param = infer_param_semantics(
        "power accuracy",
        "Nominal: -80 dBm, Reference: -80.17 dBm, Error: -0.17 dB, Limit: +/-0.2 dB",
        "0.5 dB",
    )
    candidates = structured_prefilter(param, _jjf1471_items())
    assert [c.measured for c in candidates] == ["power_range", "power_deviation"]


def test_cross_domain_prefilter_routes_phase_noise_to_phase_noise_only():
    param = infer_param_semantics(
        "phase noise",
        "Phase Noise: -84.5 dBc/Hz @ 10 kHz",
        "3 dB",
    )
    candidates = structured_prefilter(param, _jjf1471_items())
    assert [c.measured for c in candidates] == ["phase_noise"]


def test_cross_domain_prefilter_routes_evm_to_modulation_quality_only():
    param = infer_param_semantics(
        "signal quality",
        "EVM: 4.22 %, carrier frequency 2491.75 MHz",
        "0.80 %",
    )
    candidates = structured_prefilter(param, _jjf1471_items())
    assert [c.measured for c in candidates] == ["error_vector_magnitude"]


def test_cross_domain_prefilter_routes_dynamic_range_to_dynamic_range_only():
    param = infer_param_semantics(
        "power dynamic range",
        "Dynamic Range: 82 dB",
        "1 dB",
    )
    candidates = structured_prefilter(param, _jjf1471_items())
    assert [c.measured for c in candidates] == ["power_dynamic_range"]


def test_unknown_quantity_does_not_select_unrelated_candidates():
    param = infer_param_semantics(
        "internal channel delay",
        "Delay: 12 ns",
        "0.5 ns",
    )
    candidates = structured_prefilter(param, _jjf1471_items())
    assert candidates == []


def test_reference_oscillator_context_routes_internal_timebase_metrics_to_reference_check():
    param = infer_param_semantics(
        "2 内时基振荡器",
        "项目: 开机特性, Reference: 6.9×10^-9, U(k=2): 3×10^-10",
        "Urel=3×10^-10",
    )
    assert param.task_intent == "reference_check"
    assert param.primary_quantity == "relative_frequency"


def test_internal_crystal_output_frequency_is_treated_as_reference_oscillator_capability():
    cap = infer_kb_capability(
        {
            "measured": "internal crystal output frequency",
            "measure_range_text": "10MHz",
            "u_text": "Urel=3e-12",
        }
    )
    assert cap.capability_target == "reference_oscillator"
    assert cap.primary_quantity == "relative_frequency"


def test_frequency_entries_with_relative_frequency_metric_are_reclassified_as_reference_oscillator():
    cap = infer_kb_capability(
        {
            "measured": "frequency",
            "measure_range_text": "relative frequency deviation: ±(1e-5~1e-10)",
            "u_text": "Urel=1e-11",
        }
    )
    assert cap.capability_target == "reference_oscillator"


def test_structured_prefilter_prefers_reference_oscillator_for_internal_timebase_batch():
    param = infer_param_semantics(
        "2 内时基振荡器",
        "项目: 相对频率偏差, Reference: 5.7×10^-8, U(k=2): 3×10^-10",
        "Urel=3×10^-10",
    )
    candidates = structured_prefilter(param, _jjg601_items())
    assert {c.measured for c in candidates} == {"internal crystal output frequency", "frequency"}


def test_time_range_ranking_prefers_the_longer_jjg238_band_for_millisecond_points():
    result = select_basis_with_audit(
        "2 计时(Time)",
        "Reference: 0.001 s, Indicated: 0.00099 s, Error: 0.00001 s, Limit: ±0.00001 s",
        "U=0.00001 s",
        _jjg238_items(),
        decider=FirstCandidateDecider(),
    )
    assert result.selected
    assert result.selected[0].source["measure_range_text"] == ">=1.5us~24h"
