import json

from param_check import (
    _extract_measure_for_range_tool,
    _select_range_measure_value,
    calc_u_formula,
    enforce_uncertainty_by_tool,
    parse_value_with_unit,
    verify_error_logic,
    verify_range_logic,
)


def _status(payload: str) -> str:
    return json.loads(payload)["status"]


def test_verify_range_logic_supports_frequency_ranges_with_mixed_units():
    assert _status(verify_range_logic("100.0000000 kHz", "10 Hz～18 GHz")) == "PASS"
    assert _status(verify_range_logic("10.00000000 MHz", "10 Hz～18 GHz")) == "PASS"
    assert _status(verify_range_logic("350.0000000 MHz", "10 Hz～18 GHz")) == "PASS"


def test_parse_value_with_unit_preserves_compound_engineering_units():
    assert parse_value_with_unit("1 m/s") == (1.0, "abs")
    assert parse_value_with_unit("10 m") == (10.0, "abs")
    assert parse_value_with_unit("900 m/s²") == (900.0, "abs")


def test_verify_range_logic_supports_negative_db_ranges():
    assert _status(verify_range_logic("-81.2 dBc/Hz", "(-130～-60)dBc/Hz")) == "PASS"
    assert _status(verify_range_logic("-47.2 dB", "(-60～20)dB")) == "PASS"


def test_extract_measure_for_range_tool_prefers_parameter_value_over_reference():
    assert _extract_measure_for_range_tool(
        "Frequency: 2491.75 MHz, Parameter: EVM, Reference: 4.22 %"
    ) == "4.22 %"
    assert _extract_measure_for_range_tool(
        "Frequency: 2491.75 MHz, Offset: 0.1 kHz, Reference: -81.2 dBc/Hz"
    ) == "-81.2 dBc/Hz"
    assert _extract_measure_for_range_tool("Phase Error: 0.50 deg") == "0.50 deg"


def test_extract_measure_for_range_tool_prefers_nominal_over_reference():
    assert _extract_measure_for_range_tool(
        "Nominal: -130 dBm, Reference: -130.40 dBm"
    ) == "-130 dBm"


def test_extract_measure_for_range_tool_ignores_section_prefix_before_colon():
    assert _extract_measure_for_range_tool(
        "5.4 Phase Noise: -84.5 dBc/Hz"
    ) == "-84.5 dBc/Hz"


def test_power_accuracy_range_should_use_nominal_and_error_should_use_error_column():
    range_measure = _extract_measure_for_range_tool(
        "Nominal: -130 dBm, Reference: -130.40 dBm"
    )
    assert range_measure == "-130 dBm"
    assert _status(verify_range_logic(range_measure, "(-130～-20)dBm")) == "PASS"
    assert _status(verify_error_logic("0.40 dB", "0.2 dB")) == "FAIL"


def test_percentage_error_limit_should_use_relative_error_against_measurement_value():
    assert _status(verify_error_logic("0.03 s", "±1.00 %", "1.00 min")) == "PASS"
    assert _status(verify_error_logic("0.52 s", "±1.00 %", "15.00 min")) == "PASS"


def test_symmetric_error_range_should_fail_when_absolute_error_exceeds_upper_bound():
    payload = json.loads(verify_error_logic("1.0×10^-8", "±(2×10⁻¹⁰～1×10⁻¹¹)", "10 MHz"))
    assert payload["status"] == "FAIL"
    assert "不在对称范围" in payload["reason"]


def test_symmetric_error_range_should_use_absolute_value_for_negative_errors():
    payload = json.loads(verify_error_logic("-6.0×10^-11", "±(2×10⁻¹⁰～1×10⁻¹¹)", "10 MHz"))
    assert payload["status"] == "PASS"
    assert "在对称范围" in payload["reason"]


def test_calc_u_formula_keeps_compound_units_intact():
    value, reason = calc_u_formula("U=1m/s", "Reference: 1.01 m/s")
    assert value == 1.0
    assert "U=1m/s" in reason


def test_error_like_kb_range_should_use_absolute_error_value():
    range_measure = _select_range_measure_value(
        "Nominal: -130 dBm, Reference: -130.40 dBm",
        "±(0.1～2)dB",
        error_val="0.40 dB",
        match_item="功率偏差",
    )
    assert range_measure == "0.4 dB"
    assert _status(verify_range_logic(range_measure, "±(0.1～2)dB")) == "PASS"


def test_carrier_frequency_deviation_range_should_use_error_magnitude():
    range_measure = _select_range_measure_value(
        "Nominal: 1561.098 MHz, Reference: 1561.09805423 MHz",
        "(0～100)Hz",
        error_val="-54.23 Hz",
        match_item="载波频率偏差",
    )
    assert range_measure == "54.23 Hz"
    assert _status(verify_range_logic(range_measure, "(0～100)Hz")) == "PASS"


def test_input_sensitivity_composite_range_should_end_as_pass_under_business_rule():
    md = """
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CHA | 通道A, 频率0.1 MHz, 灵敏度10 mV | JJG841 | 频率测量范围及输入灵敏度 | 1 mV～1 V(>100 kHz～20 MHz) | N/A | N/A | 0.1 mV | U=0.5dB | FAIL | 初始说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | CHA | 通道A, 频率0.1 MHz, 灵敏度10 mV | JJG841 | 频率测量范围及输入灵敏度 | 1 mV～1 V(>100 kHz～20 MHz) | N/A | N/A | 0.1 mV | U=0.5dB | REVIEW |" in out
    assert "频率范围核验:PASS" in out
    assert "电平范围核验:PASS" in out
    assert "不确定度工具判定:REVIEW" in out
