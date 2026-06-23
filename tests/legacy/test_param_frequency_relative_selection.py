from param_check import _extract_measure_for_range_tool, _extract_value_token, parse_value_with_unit


def test_extract_measure_for_range_tool_prefers_stability_value_over_point_label():
    token = _extract_measure_for_range_tool(
        "取样时间: 10s, 短期频率稳定度: 9.5×10⁻¹²"
    )
    assert parse_value_with_unit(token, keep_sign=True)[0] == parse_value_with_unit("9.5×10⁻¹²", keep_sign=True)[0]


def test_extract_measure_for_range_tool_prefers_warmup_value():
    assert _extract_measure_for_range_tool(
        "开机特性: 1.0×10⁻⁸"
    ) == "1.0×10⁻⁸"


def test_extract_value_token_preserves_scientific_notation():
    assert _extract_value_token("开机特性: 1.0×10⁻⁸") == "1.0×10⁻⁸"
