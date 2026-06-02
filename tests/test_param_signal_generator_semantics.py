import sys
import types
from pathlib import Path


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


import md_parser_no_llm as md_parser_module

from md_parser_no_llm import parse_md_to_json, _build_measurement_row
from langchain_app.checks.parameter import parameter as parameter_module
from langchain_app.checks.parameter import rules as rules_module
from langchain_app.checks.parameter import semantic as semantic_module
from langchain_app.checks.parameter import selector as selector_module


def test_signal_generator_sections_and_point_aliases_parse_generically():
    result = parse_md_to_json(str(Path("local_md/1GA25005090-0265.md")))
    rows = result["依据参数_中间数据"]

    reference_row = rows[0]
    power_row = rows[1]

    assert reference_row["__parser_meta"]["section_rule"] == "frequency_accuracy"
    assert reference_row["__parser_meta"]["section_rule_confidence"] > 0.0
    assert reference_row["__parser_meta"]["section_alias_matched"]
    assert power_row["__parser_meta"]["section_rule"] == "power_accuracy"
    assert power_row["__parser_meta"]["section_rule_confidence"] > 0.0
    assert power_row["__parser_meta"]["section_alias_matched"] in {"power level", "功率电平"}
    assert power_row["__normalized_fields"]["point_value"] == "15 dB"


def test_parser_and_selector_share_single_section_alias_source():
    assert md_parser_module.SECTION_TITLE_ALIASES is rules_module.SECTION_TITLE_ALIASES
    assert "power resolution" in rules_module.SECTION_TITLE_ALIASES["power_accuracy"]
    assert "功率分辨力" in rules_module.SEMANTIC_RULE_REGISTRY["power_accuracy"]["section_aliases"]
    assert "signal quality" in rules_module.SECTION_TITLE_ALIASES["modulation_quality"]
    assert "signal quality" in rules_module.PARAMETER_NAME_RULES["evm"]


def test_power_level_rows_extract_generic_power_measure_point_and_error():
    result = parse_md_to_json(str(Path("local_md/1GA25005090-0265.md")))
    params = parameter_module.collect_certificate_params(result)
    power_param = next(param for param in params if "功率电平" in param["param_name"])

    assert parameter_module._extract_param_point_value(power_param) == "15 dB"
    assert power_param["__normalized_fields"]["measure_value"] == "14.93 dBm"
    assert power_param["__parameter_contract"]["measure_value"] == "14.93 dBm"
    assert power_param["__parameter_contract"]["cert_u"] == "0.40 dB"
    assert parameter_module._extract_param_measure_value(power_param) == "14.93 dBm"
    assert parameter_module._extract_param_error_value(power_param) == "-0.07 dB"


def test_kb_aliases_map_time_base_accuracy_and_level_to_generic_capabilities():
    freq_cap = semantic_module.infer_kb_capability(
        {
            "measured": "时基准确度",
            "u_text": "Urel=1×10⁻⁹",
            "measure_range_text": "10 MHz",
        }
    )
    power_cap = semantic_module.infer_kb_capability(
        {
            "measured": "电平",
            "u_text": "U=(0.04~0.18)dB",
            "measure_range_text": "(0～30)dBm(9 kHz～26.5 GHz)",
        }
    )
    deviation_cap = semantic_module.infer_kb_capability(
        {
            "measured": "功率偏差",
            "u_text": "U=(0.12～0.2)dB",
            "measure_range_text": "±(0.1～2)dB",
        }
    )

    assert freq_cap.capability_target == "frequency_accuracy"
    assert freq_cap.semantic_subtype == "timebase_accuracy"
    assert power_cap.capability_target == "power_accuracy"
    assert power_cap.result_quantity == "power_value"
    assert power_cap.semantic_subtype == "power_range"
    assert power_cap.condition_axis == "frequency_band"
    assert deviation_cap.result_quantity == "power_error"
    assert deviation_cap.semantic_subtype == "power_error"


def test_ambiguous_crystal_frequency_range_maps_to_frequency_accuracy_deterministically():
    freq_cap = semantic_module.infer_kb_capability(
        {
            "measured": "晶振频率",
            "u_text": "Urel=6.5×10⁻¹¹",
            "measure_range_text": "10 Hz～18 GHz",
            "raw": "晶振频率 频率测量误差 10 Hz～18 GHz",
        }
    )

    assert freq_cap.capability_target == "frequency_accuracy"
    assert freq_cap.condition_axis == "frequency_band"


def test_plain_frequency_range_with_uncertainty_maps_to_frequency_accuracy_deterministically():
    freq_cap = semantic_module.infer_kb_capability(
        {
            "measured": "频率",
            "u_text": "Urel=6.5×10⁻¹¹",
            "measure_range_text": "10 Hz～18 GHz",
        }
    )

    assert freq_cap.capability_target == "frequency_accuracy"
    assert freq_cap.condition_axis == "frequency_band"


def test_period_range_with_relative_uncertainty_maps_to_period_accuracy_deterministically():
    period_cap = semantic_module.infer_kb_capability(
        {
            "measured": "周期",
            "kb_u": "Urel=6.5×10⁻¹¹",
            "measure_range_text": "1 ns～10 s",
        }
    )

    assert period_cap.capability_target == "period_accuracy"
    assert period_cap.condition_axis == "period_band"


def test_output_time_interval_kb_entry_carries_probe_subtype():
    cap = semantic_module.infer_kb_capability(
        {
            "measured": "输出时间间隔",
            "measure_range_text": ">1 ms～9999.9 s",
            "uncertainty": {"type": "Urel", "value_display": "Urel=8.4×10⁻⁸"},
        }
    )

    assert cap.capability_target == "period_accuracy"
    assert cap.semantic_subtype == "output_time_interval"
    assert cap.unit_family == "time"


def test_kb_aliases_capture_carrier_frequency_and_power_resolution_subtypes():
    carrier_cap = semantic_module.infer_kb_capability(
        {
            "measured": "载波频率偏差",
            "u_text": "U=4.8Hz",
            "measure_range_text": "（0～100）Hz",
        }
    )
    resolution_cap = semantic_module.infer_kb_capability(
        {
            "measured": "功率分辨力",
            "u_text": "U=0.02dB",
            "measure_range_text": "(0.1～2)dB",
        }
    )

    assert carrier_cap is not None
    assert carrier_cap.semantic_subtype == "carrier_frequency_error"
    assert resolution_cap is not None
    assert resolution_cap.semantic_subtype == "power_resolution"


def test_power_deviation_candidates_use_error_value_for_range_probe():
    kb = semantic_module.KbCapability(
        measured="功率偏差",
        capability_target="power_accuracy",
        primary_quantity="power",
        result_quantity="power_error",
        condition_axis=None,
        uncertainty_kind="U",
        source={},
    )

    assert parameter_module._resolve_range_probe_value(kb, "14.93 dBm", "-0.07 dB") == "-0.07 dB"


def test_carrier_frequency_deviation_range_probe_uses_absolute_error_with_param_context():
    kb = semantic_module.KbCapability(
        measured="载波频率偏差",
        capability_target="frequency_accuracy",
        primary_quantity="frequency",
        result_quantity="frequency_error_or_value",
        condition_axis=None,
        uncertainty_kind="U",
        semantic_subtype="carrier_frequency_error",
        source={"measure_range_text": "（0～100）Hz"},
    )
    param = {
        "__parameter_contract": {
            "semantic_target": "frequency_accuracy",
            "semantic_subtype": "carrier_frequency_error",
            "nominal_value": "1561.098 MHz",
            "reference_value": "1561.09805423 MHz",
            "error_value": "-54.23 Hz",
        }
    }

    assert (
        parameter_module._resolve_range_probe_value(
            kb,
            "1561.098 MHz",
            "-54.23 Hz",
            param=param,
            reference_val="1561.09805423 MHz",
        )
        == "54.23 Hz"
    )


def test_power_accuracy_error_rows_prefer_power_deviation_candidates():
    row = _build_measurement_row(
        "3.2.2 功率准确度(Power Accuracy)(前面板RF OUTPUT端口)",
        {
            "标称值 (Nominal)": "-60 dBm",
            "标准值 (Reference)": "-60.12 dBm",
            "误差 (Error)": "0.12 dB",
            "U (k=2)": "0.20 dB",
        },
        parse_source="html_table",
    )

    cert_point, param_semantic = selector_module.normalize_cert_point(
        basis_code="JJF 1471-2014",
        section_label=row["项目名称"],
        param_name=row["项目名称"],
        point_text="",
        cert_u="0.20 dB",
        measure_value=parameter_module._extract_param_measure_value(row),
        reference_value=parameter_module._extract_param_reference_value(row),
        error_value=parameter_module._extract_param_error_value(row),
        point_value=parameter_module._extract_param_point_value(row),
        parameter_contract=row.get("__parameter_contract"),
        parser_meta=row.get("__parser_meta"),
    )
    kb_entries = [
        {
            "file_code": "JJF 1471-2014",
            "measured": "功率范围",
            "measure_range_text": "(-130～-20)dBm，1000 MHz～3000 MHz",
            "uncertainty": {"type": "U", "value_display": "U=(0.12～0.2)dB"},
        },
        {
            "file_code": "JJF 1471-2014",
            "measured": "功率偏差",
            "measure_range_text": "±(0.1～2)dB",
            "uncertainty": {"type": "U", "value_display": "U=(0.12～0.2)dB"},
        },
    ]

    outcome = selector_module.select_kb_candidates(cert_point, param_semantic, kb_entries)

    assert outcome.selected_candidate is not None
    assert outcome.selected_candidate.semantic_subtype == "power_error"
    assert outcome.selected_candidate.measured == "功率偏差"


def test_pseudorange_resolution_candidates_use_error_value_for_range_probe():
    kb = semantic_module.KbCapability(
        measured="伪距分辨力",
        capability_target="dynamic_range",
        primary_quantity="dynamic_range",
        result_quantity="dynamic_range",
        condition_axis=None,
        uncertainty_kind="U",
        source={"measured": "伪距分辨力"},
    )

    assert parameter_module._resolve_range_probe_value(kb, "10 m", "0.08 m") == "0.08 m"


def test_rf_cw_frequency_row_keeps_nominal_and_reference_separate():
    row = _build_measurement_row(
        "3 射频信号载波频率(RF CW Frequency)",
        {
            "标称值 (Nominal)": "1207.140 MHz",
            "标准值 (Reference)": "1207.1399582 MHz",
            "误差 (Error)": "41.8 Hz",
            "U (k=2)": "4.5 Hz",
        },
        parse_source="html_table",
    )

    assert row is not None
    assert row["__parser_meta"]["section_rule"] == "frequency_accuracy"
    assert row["__normalized_fields"]["nominal_value"] == "1207.140 MHz"
    assert row["__normalized_fields"]["reference_value"] == "1207.1399582 MHz"
    assert row["__parameter_contract"]["nominal_value"] == "1207.140 MHz"
    assert row["__parameter_contract"]["reference_value"] == "1207.1399582 MHz"


def test_power_resolution_row_maps_reference_into_measure_for_replay():
    row = _build_measurement_row(
        "4.1 功率分辨力(Power Resolution)",
        {
            "标称值 (Nominal)": "0.1 dB",
            "标准值 (Reference)": "0.10 dB",
            "误差 (Error)": "0.00 dB",
            "允许误差 (Limit)": "≤0.20 dB",
            "U (k=2)": "0.08 dB",
        },
        parse_source="html_table",
    )

    assert row is not None
    assert row["__parser_meta"]["section_rule"] == "power_accuracy"
    assert row["__normalized_fields"]["reference_value"] == "0.10 dB"
    assert row["__normalized_fields"]["measure_value"] == "0.10 dB"
    assert row["__parser_meta"]["header_rules"]["measure_value"] == "标准值 (Reference)"


def test_phase_noise_uses_voltage_power_family_even_with_offset_frequency():
    semantic = semantic_module.infer_param_semantics(
        "3.4 相位噪声(Phase Noise)",
        "100 Hz | -83.2 dBc/Hz",
        "2.0 dB",
        structured_fields={"measure_value": "-83.2 dBc/Hz", "point_value": "100 Hz"},
    )

    assert semantic is not None
    assert semantic.primary_quantity == "phase_noise"
    assert semantic.unit_family == "voltage_power"


def test_phase_noise_extracts_offset_as_point_value_from_sample():
    result = parse_md_to_json(str(Path("local_md/2GB25006175-0005A.md")))
    params = parameter_module.collect_certificate_params(result)
    phase_noise_param = next(param for param in params if param["param_name"] == "3.4 相位噪声(Phase Noise)")

    assert parameter_module._extract_param_point_value(phase_noise_param) == "0.1 kHz"


def test_signal_quality_extracts_metric_labels_as_point_values_from_sample():
    result = parse_md_to_json(str(Path("local_md/2GB25006175-0005A.md")))
    params = parameter_module.collect_certificate_params(result)
    point_values = [
        parameter_module._extract_param_point_value(param)
        for param in params
        if param["param_name"] == "3.5 信号质量(Signal Quality)(@I路)"
    ]

    assert point_values == ["EVM", "Phase Error", "IQ Offset"]


def test_extract_param_measure_value_uses_reference_when_frequency_is_condition_for_signal_quality():
    param = {
        "param_name": "7 信号质量(Signal Quality)",
        "__normalized_fields": {
            "measure_value": "2491.75 MHz",
            "reference_value": "4.22 %",
            "cert_u": "0.80 %",
        },
        "__parser_meta": {
            "section_rule": "modulation_quality",
        },
    }

    assert parameter_module._extract_param_measure_value(param) == "4.22 %"


def test_extract_param_measure_value_uses_reference_when_frequency_is_condition_for_phase_noise():
    param = {
        "param_name": "6 相位噪声(Phase Noise)",
        "__normalized_fields": {
            "measure_value": "2491.75 MHz",
            "reference_value": "-81.2 dBc/Hz",
            "cert_u": "2.0 dB",
        },
        "__parser_meta": {
            "section_rule": "phase_noise",
        },
    }

    assert parameter_module._extract_param_measure_value(param) == "-81.2 dBc/Hz"


def test_extract_param_measure_value_uses_reference_for_spectral_purity_even_when_section_unknown():
    param = {
        "param_name": "8 信号纯度(Spectral Purity)",
        "__normalized_fields": {
            "measure_value": "2491.75 MHz",
            "reference_value": "-44.2 dB",
            "cert_u": "1.6 dB",
        },
        "__parser_meta": {
            "section_rule": "unknown",
        },
    }

    assert parameter_module._extract_param_measure_value(param) == "-44.2 dB"


def test_speed_and_acceleration_map_to_dynamic_range_motion_family():
    speed_semantic = semantic_module.infer_param_semantics(
        "3.3.1 速度(Speed)",
        "120000 m/s | -0.01 m/s",
        "1.0 m/s",
        structured_fields={"measure_value": "120000 m/s", "error_value": "-0.01 m/s"},
    )
    accel_semantic = semantic_module.infer_param_semantics(
        "3.3.2 加速度(Accelerated Speed)",
        "36000 m/s² | -0.005 m/s²",
        "0.30 m/s²",
        structured_fields={"measure_value": "36000 m/s²", "error_value": "-0.005 m/s²"},
    )

    assert speed_semantic is not None
    assert speed_semantic.primary_quantity == "dynamic_range"
    assert speed_semantic.unit_family == "motion"
    assert accel_semantic is not None
    assert accel_semantic.primary_quantity == "dynamic_range"
    assert accel_semantic.unit_family == "motion"


def test_phase_error_and_iq_offset_map_to_modulation_quality():
    phase_error = semantic_module.infer_param_semantics(
        "3.5 信号质量(Signal Quality)(@I路)",
        "Phase Error | 0.83 °",
        "0.58 °",
        structured_fields={"measure_value": "0.83 °", "point_value": "Phase Error"},
    )
    iq_offset = semantic_module.infer_param_semantics(
        "3.5 信号质量(Signal Quality)(@I路)",
        "IQ Offset | -54.80 dB",
        "2.0 dB",
        structured_fields={"measure_value": "-54.80 dB", "point_value": "IQ Offset"},
    )

    assert phase_error is not None
    assert phase_error.primary_quantity == "modulation_quality"
    assert phase_error.semantic_subtype == "phase_error"
    assert iq_offset is not None
    assert iq_offset.primary_quantity == "modulation_quality"
    assert iq_offset.semantic_subtype == "iq_offset"


def test_power_resolution_maps_to_power_accuracy_and_resolution_subtype():
    semantic = semantic_module.infer_param_semantics(
        "4.1 功率分辨力(Power Resolution)",
        "0.1 dB | 0.00 dB | ≤0.20 dB",
        "0.08 dB",
        structured_fields={
            "reference_value": "0.10 dB",
            "measure_value": "0.10 dB",
            "error_value": "0.00 dB",
            "limit_value": "≤0.20 dB",
        },
    )

    assert semantic is not None
    assert semantic.primary_quantity == "power"
    assert semantic.semantic_subtype == "power_resolution"


def test_modulation_quality_percentage_and_degree_values_use_voltage_power_family():
    evm = semantic_module.infer_param_semantics(
        "7 信号质量(Signal Quality)",
        "EVM | 4.22 %",
        "0.80 %",
        structured_fields={"measure_value": "4.22 %", "point_value": "EVM", "cert_u": "0.80 %"},
    )
    phase_error = semantic_module.infer_param_semantics(
        "7 信号质量(Signal Quality)",
        "Phase Error | 1.05 °",
        "0.58 °",
        structured_fields={"measure_value": "1.05 °", "point_value": "Phase Error", "cert_u": "0.58 °"},
    )

    assert evm.unit_family == "voltage_power"
    assert evm.semantic_subtype == "evm"
    assert phase_error.unit_family == "voltage_power"
    assert phase_error.semantic_subtype == "phase_error"


def test_pseudorange_resolution_maps_to_dynamic_range():
    semantic = semantic_module.infer_param_semantics(
        "6 误差控制(Error Control) / 伪距分辨力",
        "伪距分辨力 | 标称值 10 m | 标准值 9.92 m | 误差 0.08 m",
        "0.06 m",
        structured_fields={"measure_value": "10 m", "error_value": "0.08 m"},
    )

    assert semantic is not None
    assert semantic.primary_quantity == "dynamic_range"
    assert semantic.task_intent == "range_check"
    assert semantic.unit_family == "length"
    assert semantic.semantic_subtype == "pseudorange_resolution"


def test_reference_oscillator_metrics_get_subtypes():
    warmup = semantic_module.infer_param_semantics(
        "2 开机特性(Warm-up Characteristics)",
        "开机特性 1.0×10^-8",
        "Urel=3.0×10^-12",
        structured_fields={"error_value": "1.0×10^-8", "reference_value": "10 MHz"},
    )
    stability = semantic_module.infer_param_semantics(
        "3 短期频率稳定度(Short-Term Stability)(at 10MHz)",
        "短期频率稳定度 6.0×10^-11",
        "Urel=2.4×10^-12",
        structured_fields={"error_value": "6.0×10^-11", "reference_value": "10 MHz"},
    )
    relative = semantic_module.infer_param_semantics(
        "4 相对频率偏差(Relative Frequency Deviation)",
        "相对频率偏差 1.0×10^-8",
        "Urel=1.0×10^-12",
        structured_fields={"error_value": "1.0×10^-8", "reference_value": "10 MHz"},
    )

    assert warmup.semantic_subtype == "warmup_characteristics"
    assert stability.semantic_subtype == "frequency_stability"
    assert relative.semantic_subtype == "relative_frequency_deviation"


def test_spectral_purity_and_motion_kb_candidates_gain_capabilities():
    spectral_cap = semantic_module.infer_kb_capability(
        {
            "measured": "谐波抑制",
            "u_text": "U=1.0dB",
            "measure_range_text": "(-60～-20)dB",
        }
    )
    speed_cap = semantic_module.infer_kb_capability(
        {
            "measured": "速度动态范围",
            "u_text": "U=1m/s",
            "measure_range_text": "（0～36000）m/s",
        }
    )

    assert spectral_cap.capability_target == "spectral_purity"
    assert speed_cap.capability_target == "dynamic_range"

    normalized = selector_module.normalize_kb_candidate(
        {
            "file_code": "JJF 1471-2014",
            "measured": "速度动态范围",
            "measure_range_text": "（0～36000）m/s",
            "uncertainty": {"type": "U", "value_display": "U=1m/s"},
        }
    )
    assert selector_module._candidate_unit_family(normalized) == "motion"
