from param_check import _count_statuses_from_table_lines, _summarize_table_statuses


def test_count_statuses_from_table_lines_uses_header_index():
    table_lines = [
        "| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |",
        "|------|------|--------|--------|------------|------|----------|----------|-------|------|------|------|",
        "| 1 | CH1 | A | JJF2196 | 频率 | 10 Hz~18 GHz | 0.000 Hz | ±0.008 Hz | 0.004 Hz | Urel=6.5e-11 | PASS | ok |",
        "| 2 | CH1 | B | 无 | 输入灵敏度检查 | N/A | N/A | N/A | N/A | N/A | FAIL | KB无对应参数 |",
    ]

    pass_count, fail_count, total_count = _count_statuses_from_table_lines(table_lines)

    assert pass_count == 1
    assert fail_count == 1
    assert total_count == 2


def test_summarize_table_statuses_splits_kb_missing_and_real_failures():
    table_lines = [
        "| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |",
        "|------|------|--------|--------|------------|------|----------|----------|-------|------|------|------|",
        "| 1 | CH1 | A | 无 | Phase Error | N/A | 0.50 ° | <=1.0 | 0.58 ° | N/A | FAIL | KB无对应参数 -> 判定FAIL |",
        "| 2 | CH2 | B | JJF1471 | 速度动态范围 | （0～36000）m/s | N/A | N/A | 0.30 m/s | U=1m/s | FAIL | 不确定度工具判定:FAIL(Cert(0.3) < KB(1)) |",
    ]

    summary = _summarize_table_statuses(table_lines)

    assert summary["fail"] == 2
    assert summary["kb_missing_fail"] == 1
    assert summary["real_fail"] == 1
