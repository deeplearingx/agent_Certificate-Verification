import json

from param_check import verify_uncertainty_logic


def _status_and_reason(result: str):
    payload = json.loads(result)
    return payload["status"], payload["reason"]


def test_uncertainty_same_kind_urel_compares_directly():
    status, reason = _status_and_reason(
        verify_uncertainty_logic(
            "输出频率：10 MHz，相对频率偏差：1.0×10⁻⁹",
            "1×10⁻¹⁰",
            "Urel=1e-11",
        )
    )

    assert status == "PASS"
    assert "KB(0.00000000001)" in reason


def test_uncertainty_mixed_kb_urel_cert_u_converts_kb_to_absolute():
    status, reason = _status_and_reason(
        verify_uncertainty_logic(
            "标准值:10.0000000 MHz, 指示值:10.0000000 MHz",
            "0.0002 Hz",
            "Urel=1e-11",
        )
    )

    assert status == "PASS"
    assert "KB(0.0001)" in reason


def test_uncertainty_mixed_cert_urel_kb_u_converts_cert_to_absolute():
    status, reason = _status_and_reason(
        verify_uncertainty_logic(
            "标准值:10.0000000 MHz, 指示值:10.0000000 MHz",
            "Urel=2e-11",
            "0.0001 Hz",
        )
    )

    assert status == "PASS"
    assert "Cert(0.0002)" in reason


def test_uncertainty_absolute_percentages_compare_directly_for_evm():
    status, reason = _status_and_reason(
        verify_uncertainty_logic(
            "棰戠巼: 2491.75 MHz, 鍙傛暟: EVM, 鏍囧噯鍊?Reference): 4.22 %",
            "0.80 %",
            "U=0.7%",
        )
    )

    assert status == "PASS"
    assert "Cert(0.008)" in reason
    assert "KB(0.007)" in reason


def test_uncertainty_relative_display_uses_measurement_value_for_conversion_summary():
    payload = json.loads(
        verify_uncertainty_logic(
            "标准值:0.001 s, 指示值:0.001 s",
            "1e-05 s",
            "0.58%",
        )
    )

    assert payload["status"] == "PASS"
    assert payload["kb_u_display"] == "5.8e-06 (折算值)"
    assert "KB=5.8e-06" in payload["conversion_summary"]
