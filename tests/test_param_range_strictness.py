import json

from param_check import verify_range_logic


def _payload(result: str) -> dict:
    return json.loads(result)


def test_verify_range_logic_treats_unparseable_range_as_error():
    payload = _payload(verify_range_logic("1 Hz", "not-a-range"))
    assert payload["status"] == "ERROR"


def test_verify_range_logic_does_not_treat_zero_as_missing():
    payload = _payload(verify_range_logic("0 Hz", "(0~100)Hz"))
    assert payload["status"] == "PASS"
