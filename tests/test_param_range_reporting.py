import json

from param_check import parse_symmetric_limit, verify_range_logic


def _payload(result: str) -> dict:
    return json.loads(result)


def test_parse_symmetric_limit_supports_symmetric_range():
    parsed = parse_symmetric_limit("±(0.1～2)dB")
    assert parsed == ("range", 0.1, 2.0)


def test_verify_range_logic_reports_units_for_regular_range():
    payload = _payload(verify_range_logic("-130 dBm", "(-130～-20)dBm"))
    assert payload["status"] == "PASS"
    assert "dBm" in payload["reason"]


def test_verify_range_logic_supports_symmetric_range_semantics():
    payload = _payload(verify_range_logic("0.40 dB", "±(0.1～2)dB"))
    assert payload["status"] == "PASS"
    assert "对称范围" in payload["reason"]


def test_verify_range_logic_supports_symmetric_single_limit():
    payload = _payload(verify_range_logic("-0.08 dB", "±0.1 dB"))
    assert payload["status"] == "PASS"
    assert "|测量值|" in payload["reason"]
