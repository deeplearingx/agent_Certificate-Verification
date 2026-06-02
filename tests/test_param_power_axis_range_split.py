import json
from types import SimpleNamespace

from langchain_app.checks.parameter.validator import verify_range_logic


def _payload(result: str) -> dict:
    return json.loads(result)


def test_power_range_with_frequency_axis_uses_power_interval_for_final_check():
    selected_candidate = SimpleNamespace(
        capability_target="power_accuracy",
        result_quantity="power_value",
        condition_axis="frequency_band",
        band_kind="range",
        band_lower=9_000.0,
        band_upper=26_500_000_000.0,
    )

    payload = _payload(
        verify_range_logic(
            "14.93 dBm",
            "0～30)dBm(9 kHz～26.5 GHz)",
            selected_candidate=selected_candidate,
        )
    )

    assert payload["status"] == "PASS"
    assert "14.93 dBm" in payload["reason"]
    assert "[9000 Hz" not in payload["reason"]


def test_power_range_with_frequency_axis_keeps_negative_power_range_failures_meaningful():
    selected_candidate = SimpleNamespace(
        capability_target="power_accuracy",
        result_quantity="power_value",
        condition_axis="frequency_band",
        band_kind="range",
        band_lower=1_000_000_000.0,
        band_upper=3_000_000_000.0,
    )

    payload = _payload(
        verify_range_logic(
            "14.93 dBm",
            "(-130～-20)dBm，1000 MHz～3000 MHz",
            selected_candidate=selected_candidate,
        )
    )

    assert payload["status"] == "FAIL"
    assert "[1000000000 Hz" not in payload["reason"]
    assert "(-130～-20)dBm" in payload["reason"]
