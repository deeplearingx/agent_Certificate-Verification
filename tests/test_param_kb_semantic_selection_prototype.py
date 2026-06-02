import re


def classify_certificate_param(param_name: str, point_text: str) -> dict:
    text = f"{param_name} | {point_text}".lower()
    has_reference = "reference" in text
    has_indicated = "indicated" in text
    has_error = "error" in text
    has_limit = "limit" in text
    has_frequency_units = bool(re.search(r"\b(?:hz|khz|mhz|ghz)\b", text))
    has_time_units = bool(re.search(r"\b(?:s|ms|us|ns|ps)\b", text))

    if "relative frequency deviation" in text or "crystal" in text:
        return {
            "task_intent": "reference_check",
            "primary_quantity": "relative_frequency",
            "condition_axis": None,
        }
    if "sensitivity" in text or "trigger" in text:
        return {
            "task_intent": "sensitivity_check",
            "primary_quantity": "input_sensitivity",
            "condition_axis": "frequency_band" if has_frequency_units else "period_band" if has_time_units else None,
        }
    if has_reference and has_indicated and has_error and has_limit and has_frequency_units:
        return {
            "task_intent": "accuracy_check",
            "primary_quantity": "frequency",
            "condition_axis": None,
        }
    if has_reference and has_indicated and has_error and has_limit and has_time_units:
        return {
            "task_intent": "accuracy_check",
            "primary_quantity": "period",
            "condition_axis": None,
        }
    return {"task_intent": "unknown", "primary_quantity": "unknown", "condition_axis": None}


def classify_kb_capability(measured: str, measure_range_text: str, u_text: str) -> dict:
    if measured == "crystal":
        return {
            "capability_target": "reference_oscillator",
            "primary_quantity": "relative_frequency",
            "condition_axis": None,
        }
    if measured == "frequency":
        return {
            "capability_target": "frequency_accuracy",
            "primary_quantity": "frequency",
            "condition_axis": None,
        }
    if measured == "period":
        return {
            "capability_target": "period_accuracy",
            "primary_quantity": "period",
            "condition_axis": None,
        }
    if measured == "frequency_measurement_range_and_input_sensitivity":
        return {
            "capability_target": "input_sensitivity",
            "primary_quantity": "input_sensitivity",
            "condition_axis": "frequency_band",
        }
    if measured == "period_measurement_range_and_input_sensitivity":
        return {
            "capability_target": "input_sensitivity",
            "primary_quantity": "input_sensitivity",
            "condition_axis": "period_band",
        }
    return {
        "capability_target": "unknown",
        "primary_quantity": "unknown",
        "condition_axis": None,
    }


def select_kb_candidates(param_name: str, point_text: str, kb_items: list[dict]) -> list[dict]:
    param_sem = classify_certificate_param(param_name, point_text)
    wanted = {
        ("reference_check", "relative_frequency"): {"reference_oscillator"},
        ("sensitivity_check", "input_sensitivity"): {"input_sensitivity"},
        ("accuracy_check", "frequency"): {"frequency_accuracy"},
        ("accuracy_check", "period"): {"period_accuracy"},
    }.get((param_sem["task_intent"], param_sem["primary_quantity"]), set())

    selected = []
    for item in kb_items:
        kb_sem = classify_kb_capability(item["measured"], item["measure_range_text"], item["u_text"])
        if kb_sem["capability_target"] not in wanted:
            continue
        if param_sem["condition_axis"] and kb_sem["condition_axis"] and param_sem["condition_axis"] != kb_sem["condition_axis"]:
            continue
        selected.append(item)
    return selected


def _jjg841_items() -> list[dict]:
    return [
        {"measured": "crystal", "measure_range_text": "1MHz,2MHz,5MHz,10MHz", "u_text": "Urel=3e-12"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(0.1Hz~100kHz)", "u_text": "U=0.2dB"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>100kHz~20MHz)", "u_text": "U=0.5dB"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>20MHz~2GHz)", "u_text": "U=1.0dB"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>2GHz~50GHz)", "u_text": "U=2dB"},
        {"measured": "frequency", "measure_range_text": "10Hz~50GHz", "u_text": "Urel=2e-11"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(10s~10us)", "u_text": "U=0.2dB"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(<10us~50ns)", "u_text": "U=0.5dB"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(<50ns~0.5ns)", "u_text": "U=1.0dB"},
        {"measured": "period_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(<0.5ns~40ps)", "u_text": "U=1.5dB"},
        {"measured": "period", "measure_range_text": "40ps~10s", "u_text": "Urel=2e-11"},
    ]


def test_frequency_measurement_should_route_to_frequency_capability():
    selected = select_kb_candidates(
        "frequency measurement error",
        "Reference: 10.00000000 MHz, Indicated: 9.99999998 MHz, Error: -0.00002 kHz, Limit: +/-0.0003 kHz",
        _jjg841_items(),
    )
    assert [item["measured"] for item in selected] == ["frequency"]


def test_trigger_sensitivity_should_route_to_frequency_band_input_sensitivity():
    selected = select_kb_candidates(
        "trigger sensitivity check",
        "Channel A, frequency 10 MHz, sensitivity 10 mV",
        _jjg841_items(),
    )
    assert {item["measured"] for item in selected} == {"frequency_measurement_range_and_input_sensitivity"}
    assert any(">100kHz~20MHz" in item["measure_range_text"] for item in selected)


def test_period_measurement_should_route_to_period_capability():
    selected = select_kb_candidates(
        "period measurement error",
        "Reference: 0.1 us, Indicated: 0.1000000002 us, Error: 0.0000002 ns, Limit: +/-0.000003 ns",
        _jjg841_items(),
    )
    assert [item["measured"] for item in selected] == ["period"]


def test_relative_frequency_deviation_should_route_to_crystal_capability():
    selected = select_kb_candidates(
        "relative frequency deviation",
        "relative frequency deviation at output frequency 10 MHz",
        _jjg841_items(),
    )
    assert [item["measured"] for item in selected] == ["crystal"]
