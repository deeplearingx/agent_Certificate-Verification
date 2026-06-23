from param_check import (
    _should_auto_pass_input_sensitivity_row,
    _should_fail_input_sensitivity_row_for_garble,
    enforce_uncertainty_by_tool,
)


def test_input_sensitivity_row_should_auto_pass_when_text_is_readable():
    assert _should_auto_pass_input_sensitivity_row(
        "3 输入灵敏度检查",
        "Channel A, Frequency 10 MHz, 输入灵敏度 40 mV",
        cert_u="0.5 mV",
    )


def test_trigger_sensitivity_param_should_also_auto_pass_when_text_is_readable():
    assert _should_auto_pass_input_sensitivity_row(
        "3 触发灵敏度",
        "Channel A, Frequency 10 MHz, 灵敏度 40 mV",
        cert_u="0.5 mV",
    )


def test_frequency_measurement_and_sensitivity_param_should_also_auto_pass_when_text_is_readable():
    assert _should_auto_pass_input_sensitivity_row(
        "3 频率测量范围及灵敏度",
        "Channel C, Frequency 15 GHz, 灵敏度 -35 dBm",
        cert_u="0.5 dB",
    )


def test_input_sensitivity_row_should_not_auto_pass_when_text_is_garbled():
    assert not _should_auto_pass_input_sensitivity_row(
        "3 输入灵敏度检查",
        "Channel A, Frequency 10 MHz, 鐏垫晱搴?40 mV",
        cert_u="0.5 mV",
    )


def test_input_sensitivity_row_should_fail_when_text_is_garbled():
    assert _should_fail_input_sensitivity_row_for_garble(
        "3 输入灵敏度检查",
        "Channel A, Frequency 10 MHz, 鐏垫晱搴?40 mV",
        cert_u="0.5 mV",
    )


def test_input_sensitivity_row_should_ignore_garbled_cert_u_error_and_limit_when_measure_text_is_readable():
    assert _should_auto_pass_input_sensitivity_row(
        "3 周期测量范围及灵敏度",
        "Channel A, Period 10 ns, 灵敏度 40 mV",
        cert_u="鐏垫晱搴?0.5 mV",
        error_val="鐏垫晱搴?40 mV",
        limit_val="鐏垫晱搴?±1 mV",
    )


def test_enforce_uncertainty_by_tool_auto_passes_readable_input_sensitivity_row():
    md = """
## 参数：3 输入灵敏度检查
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CH1 | 通道A, 频率10 MHz, 输入灵敏度40 mV | 无 | 输入灵敏度检查 | N/A | N/A | N/A | 0.5 mV | N/A | FAIL | 初始说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | CH1 | 通道A, 频率10 MHz, 输入灵敏度40 mV | N/A | N/A | N/A | N/A | N/A | 0.5 mV | N/A | PASS |" in out
    assert "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS" in out


def test_enforce_uncertainty_by_tool_marks_garbled_input_sensitivity_row_as_fail():
    md = """
## 参数：3 输入灵敏度检查
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CH1 | 通道A, 频率10 MHz, 鐏垫晱搴?40 mV | 无 | 输入灵敏度检查 | N/A | N/A | N/A | 0.5 mV | N/A | PASS | 初始说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | CH1 | 通道A, 频率10 MHz, 鐏垫晱搴?40 mV | N/A | N/A | N/A | N/A | N/A | 0.5 mV | N/A | FAIL |" in out
    assert "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前检测到乱码或异常文本，跳过依据核验并判定FAIL" in out


def test_enforce_uncertainty_by_tool_auto_passes_trigger_sensitivity_row():
    md = """
## 参数：3 触发灵敏度
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CH1 | 通道A, 频率10 MHz, 灵敏度40 mV | 无 | 频率 | 10 Hz～18 GHz | N/A | N/A | 0.5 mV | U=0.5dB | REVIEW | 初始说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | CH1 | 通道A, 频率10 MHz, 灵敏度40 mV | N/A | N/A | N/A | N/A | N/A | 0.5 mV | N/A | PASS |" in out
    assert "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS" in out


def test_enforce_uncertainty_by_tool_ignores_garbled_aux_fields_for_input_sensitivity_row():
    md = """
## 参数：5 周期测量范围及灵敏度
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 1 | CH1 | 通道A, 周期10 ns, 灵敏度40 mV | 无 | 周期测量范围及输入灵敏度 | N/A | 鐏垫晱搴?40 mV | 鐏垫晱搴?±1 mV | 鐏垫晱搴?0.5 mV | N/A | REVIEW | 初始说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | CH1 | 通道A, 周期10 ns, 灵敏度40 mV | N/A | N/A | N/A | 鐏垫晱搴?40 mV | 鐏垫晱搴?±1 mV | 鐏垫晱搴?0.5 mV | N/A | PASS |" in out
    assert "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS" in out


def test_enforce_uncertainty_by_tool_auto_passes_input_sensitivity_row_without_param_heading():
    md = """
这是批次说明文字，没有参数标题。

| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CH1 | 3 输入灵敏度检查(Input Sensitivity Check)(高灵敏度模式) 频率: 100 kHz 灵敏度: 4 mV | 无 | 灵敏度 4 mV | N/A | N/A | N/A | N/A | N/A | FAIL | KB无对应参数 -> 判定FAIL |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | CH1 | 3 输入灵敏度检查(Input Sensitivity Check)(高灵敏度模式) 频率: 100 kHz 灵敏度: 4 mV | N/A | N/A | N/A | N/A | N/A | N/A | N/A | PASS |" in out
    assert "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS" in out
