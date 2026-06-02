import re


def classify_certificate_param(param_name: str, point_text: str, cert_u: str = "") -> dict:
    text = f"{param_name} | {point_text} | {cert_u}".lower()

    has_reference = "reference" in text
    has_indicated = "indicated" in text
    has_error = "error" in text
    has_limit = "limit" in text
    has_sensitivity = any(token in text for token in ["sensitivity", "trigger"])

    if any(token in text for token in ["relative frequency deviation", "crystal"]):
        return {
            "task_intent": "reference_check",
            "primary_quantity": "relative_frequency",
            "point_unit_family": "frequency",
        }

    if has_sensitivity:
        return {
            "task_intent": "sensitivity_check",
            "primary_quantity": "input_sensitivity",
            "point_unit_family": "voltage_power",
        }

    if has_reference and has_indicated and has_error and has_limit:
        if re.search(r"\b(?:hz|khz|mhz|ghz)\b", text):
            return {
                "task_intent": "accuracy_check",
                "primary_quantity": "frequency",
                "point_unit_family": "frequency",
            }
        if re.search(r"\b(?:s|ms|us|ns|ps)\b", text):
            return {
                "task_intent": "accuracy_check",
                "primary_quantity": "period",
                "point_unit_family": "time",
            }

    return {
        "task_intent": "unknown",
        "primary_quantity": "unknown",
        "point_unit_family": "unknown",
    }


def test_relative_frequency_deviation_is_reference_check_not_frequency_accuracy():
    result = classify_certificate_param(
        "relative frequency deviation",
        "relative frequency deviation at output frequency 10 MHz",
        "3e-10",
    )
    assert result["task_intent"] == "reference_check"
    assert result["primary_quantity"] == "relative_frequency"


def test_trigger_sensitivity_is_sensitivity_check():
    result = classify_certificate_param(
        "trigger sensitivity check",
        "Channel A, frequency 10 MHz, sensitivity 10 mV",
        "0.1 mV",
    )
    assert result["task_intent"] == "sensitivity_check"
    assert result["primary_quantity"] == "input_sensitivity"


def test_frequency_measurement_error_is_frequency_accuracy_not_input_sensitivity():
    result = classify_certificate_param(
        "frequency measurement error",
        "Reference: 10.00000000 MHz, Indicated: 9.99999998 MHz, Error: -0.00002 kHz, Limit: +/-0.0003 kHz",
        "0.00006 kHz",
    )
    assert result["task_intent"] == "accuracy_check"
    assert result["primary_quantity"] == "frequency"


def test_period_measurement_error_is_period_accuracy():
    result = classify_certificate_param(
        "period measurement error",
        "Reference: 0.1 us, Indicated: 0.1000000002 us, Error: 0.0000002 ns, Limit: +/-0.000003 ns",
        "0.0000006 ns",
    )
    assert result["task_intent"] == "accuracy_check"
    assert result["primary_quantity"] == "period"
