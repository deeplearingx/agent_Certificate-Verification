import json

from param_check import (
    _extract_measure_for_range_tool,
    _convert_sensitivity_token_for_range,
    _normalize_match_item_for_row,
    _select_range_measure_value,
    verify_range_logic,
)


def _status(payload: str) -> str:
    return json.loads(payload)["status"]


def test_extract_measure_for_range_tool_ignores_section_prefix_before_colon():
    assert _extract_measure_for_range_tool(
        "5.4 Phase Noise: -84.5 dBc/Hz"
    ) == "-84.5 dBc/Hz"


def test_phase_noise_range_uses_actual_measurement_not_section_number():
    range_measure = _select_range_measure_value(
        "5.4 Phase Noise: -84.5 dBc/Hz",
        "(-130～-60)dBc/Hz",
        match_item="相位噪声",
    )
    assert range_measure == "-84.5 dBc/Hz"
    assert _status(verify_range_logic(range_measure, "(-130～-60)dBc/Hz")) == "PASS"


def test_power_accuracy_match_item_prefers_power_range_for_dbm_range():
    assert _normalize_match_item_for_row(
        "功率偏差",
        "Nominal: -130 dBm, Reference: -130.40 dBm",
        "(-130～20)dBm",
        error_val="0.40 dB",
    ) == "功率范围"


def test_power_accuracy_match_item_prefers_power_deviation_for_db_range():
    assert _normalize_match_item_for_row(
        "功率范围",
        "Nominal: -130 dBm, Reference: -130.40 dBm",
        "±(0.1～2)dB",
        error_val="0.40 dB",
    ) == "功率偏差"


def test_time_interval_range_prefers_nominal_over_error_value():
    range_measure = _select_range_measure_value(
        "标称值: 100 s, 标准值: 99.999992 s",
        ">1 ms～9999.9 s",
        error_val="0.008 ms",
        match_item="输出时间间隔",
    )
    assert range_measure == "100 s"


def test_reversed_time_range_is_normalized_before_verification():
    payload = json.loads(verify_range_logic("0.1 us", "<10 us～50 ns"))
    assert payload["status"] == "PASS"


def test_power_sensitivity_is_converted_against_mixed_voltage_outer_range():
    converted, notes = _convert_sensitivity_token_for_range("-38 dBm", "1 mV～1 V")
    assert converted.endswith("Vpp")
    assert notes
