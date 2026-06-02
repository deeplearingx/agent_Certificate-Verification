import json
import os

import pytest
from openai import OpenAI

from config.settings import get_app_config


def _client_and_model():
    cfg = get_app_config()
    api_key = cfg.api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过 LLM 语义选择原型测试")
    client = OpenAI(api_key=api_key, base_url=cfg.api_base, timeout=60)
    return client, cfg.model


def llm_classify_certificate_param(param_name: str, point_text: str, cert_u: str = "") -> dict:
    client, model = _client_and_model()
    prompt = f"""
你是校准能力语义分析器。请只根据下面这条证书参数，判断它的物理测量任务本质。

要求：
1. 只输出 JSON，不要输出解释。
2. task_intent 只能是：
   - reference_check
   - sensitivity_check
   - accuracy_check
   - unknown
3. primary_quantity 只能是：
   - relative_frequency
   - input_sensitivity
   - frequency
   - period
   - unknown
4. point_unit_family 只能是：
   - frequency
   - time
   - voltage_power
   - unknown

证书参数：
- param_name: {param_name}
- point_text: {point_text}
- cert_u: {cert_u}

输出示例：
{{"task_intent":"accuracy_check","primary_quantity":"frequency","point_unit_family":"frequency"}}
""".strip()

    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "你只输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def llm_select_kb_candidates(param_name: str, point_text: str, kb_items: list[dict]) -> dict:
    client, model = _client_and_model()
    prompt = f"""
你是校准依据选择器。请先理解证书参数的物理测量任务，再从候选 KB 条目中选出“物理本质最匹配”的条目。

要求：
1. 只输出 JSON，不要输出解释。
2. allowed_measured 必须是数组，元素只能来自候选 KB 的 measured 字段。
3. rationale 必须是一句短句。
4. 选择原则：
   - 如果证书是在做 Reference/Indicated/Error/Limit 的频率值比对，则优先选 frequency，而不是 frequency_measurement_range_and_input_sensitivity。
   - 如果证书是在做 period 的 Reference/Indicated/Error/Limit 比对，则优先选 period，而不是 period_measurement_range_and_input_sensitivity。
   - 如果证书是在做 sensitivity/trigger 门限检查，则选 input sensitivity 类条目。
   - 如果证书是在做 relative frequency deviation / crystal 检查，则选 crystal。

证书参数：
- param_name: {param_name}
- point_text: {point_text}

KB 候选：
{json.dumps(kb_items, ensure_ascii=False)}

输出示例：
{{"allowed_measured":["frequency"],"rationale":"This row measures frequency indication accuracy."}}
""".strip()

    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "你只输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
    )
    return json.loads(resp.choices[0].message.content)


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


@pytest.mark.integration
def test_llm_can_classify_frequency_measurement_as_accuracy():
    result = llm_classify_certificate_param(
        "frequency measurement error",
        "Reference: 10.00000000 MHz, Indicated: 9.99999998 MHz, Error: -0.00002 kHz, Limit: +/-0.0003 kHz",
        "0.00006 kHz",
    )
    assert result["task_intent"] == "accuracy_check"
    assert result["primary_quantity"] == "frequency"


@pytest.mark.integration
def test_llm_can_classify_trigger_sensitivity_as_sensitivity_check():
    result = llm_classify_certificate_param(
        "trigger sensitivity check",
        "Channel A, frequency 10 MHz, sensitivity 10 mV",
        "0.1 mV",
    )
    assert result["task_intent"] == "sensitivity_check"
    assert result["primary_quantity"] == "input_sensitivity"


@pytest.mark.integration
def test_llm_selects_frequency_not_input_sensitivity_for_frequency_measurement():
    result = llm_select_kb_candidates(
        "frequency measurement error",
        "Reference: 10.00000000 MHz, Indicated: 9.99999998 MHz, Error: -0.00002 kHz, Limit: +/-0.0003 kHz",
        _jjg841_items(),
    )
    assert result["allowed_measured"] == ["frequency"]


@pytest.mark.integration
def test_llm_selects_period_for_period_measurement():
    result = llm_select_kb_candidates(
        "period measurement error",
        "Reference: 0.1 us, Indicated: 0.1000000002 us, Error: 0.0000002 ns, Limit: +/-0.000003 ns",
        _jjg841_items(),
    )
    assert result["allowed_measured"] == ["period"]


@pytest.mark.integration
def test_llm_selects_crystal_for_relative_frequency_deviation():
    result = llm_select_kb_candidates(
        "relative frequency deviation",
        "relative frequency deviation at output frequency 10 MHz",
        _jjg841_items(),
    )
    assert result["allowed_measured"] == ["crystal"]
