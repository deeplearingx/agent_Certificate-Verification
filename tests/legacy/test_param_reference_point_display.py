from param_check import enforce_uncertainty_by_tool


def test_relative_frequency_discrete_frequency_point_should_not_stay_in_range_column():
    md = """
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10 MHz | 输出频率: 10 MHz, 相对频率偏差: 1.0×10^-9 | JJF2196 | 晶振频率 - 相对频率偏差：10 MHz | 10 MHz | 1.0×10^-9 | N/A | 1×10^-10 | Urel=1.0e-11 | PASS | 原说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | 10 MHz | 输出频率: 10 MHz, 相对频率偏差: 1.0×10^-9 | JJF2196 | 晶振频率 - 相对频率偏差：10 MHz | N/A | 1.0×10^-9 | N/A | 1×10^-10 | Urel=1.0e-11 | PASS |" in out
    assert "适用点:10 MHz" in out


def test_relative_frequency_prefixed_frequency_point_should_move_to_applicable_point_note():
    md = """
| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10 MHz | 输出频率: 10 MHz, 相对频率偏差: 1.0×10^-9 | JJF2196 | 晶振频率 | 相对频率偏差：10 MHz | 1.0×10^-9 | N/A | 1×10^-10 | Urel=1.0e-11 | PASS | 原说明 |
""".strip()

    out = enforce_uncertainty_by_tool(md)
    assert "| 1 | 10 MHz | 输出频率: 10 MHz, 相对频率偏差: 1.0×10^-9 | JJF2196 | 晶振频率 | N/A | 1.0×10^-9 | N/A | 1×10^-10 | Urel=1.0e-11 | PASS |" in out
    assert "适用点:10 MHz" in out
