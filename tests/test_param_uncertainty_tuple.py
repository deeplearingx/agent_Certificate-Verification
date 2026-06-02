from param_check import _pick_ux_from_measure_text, parse_value_with_unit


def test_pick_ux_from_measure_text_returns_tuple_for_special_frequency_patterns():
    ux, reason, unit = _pick_ux_from_measure_text(
        "取样时间: 10s, 短期频率稳定度: 9.5×10⁻¹²"
    )
    assert ux == parse_value_with_unit("9.5×10⁻¹²", keep_sign=False)[0]
    assert reason.startswith("ux_from_special:")
    assert unit in ("", None)
