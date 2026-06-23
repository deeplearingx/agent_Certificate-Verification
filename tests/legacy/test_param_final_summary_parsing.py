from param_check import _collect_param_tables, enforce_uncertainty_by_tool


def test_collect_param_tables_uses_expected_param_name_when_heading_missing():
    batch_contents = [
        """| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | 10 MHz | PASS | tool |
""",
        """这里是分析
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | CH1 | FAIL | tool |
| 2 | CH2 | FAIL | tool |
""",
    ]
    tables = _collect_param_tables(
        batch_contents,
        batch_expected_params={
            1: ["2.1 相对频率偏差(Relative Frequency Deviation)"],
            2: ["3 输入灵敏度检查(Input Sensitivity Check)(高灵敏度模式)"],
        },
    )

    assert "2.1 相对频率偏差" in tables
    assert "3 输入灵敏度检查" in tables


def test_collect_param_tables_uses_parameter_group_heading():
    batch_contents = [
        """## 参数组：5.1.4 加加速度动态范围 / 5.2.1 伪距分辨力
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | +10000 m/s³ | FAIL | tool |
| 2 | 10 m | FAIL | tool |
"""
    ]

    tables = _collect_param_tables(
        batch_contents,
        batch_expected_params={
            1: ["5.1.4 加加速度动态范围", "5.2.1 伪距分辨力"],
        },
    )

    assert "5.1.4 加加速度动态范围 / 5.2.1 伪距分辨力" in tables


def test_collect_param_tables_prefers_detail_table_over_batch_summary():
    batch_contents = [
        """### 参数：Batch 2
## 批次摘要
| 测量点总数 | 通过 | 失败 | 错误 | 未知 |
|---------|------|------|------|------|
| 9 | 4 | 5 | 0 | 0 |

# 全流程智能核验报告
## 参数核验详情

| 序号 | 点位 | 测量点 | 判定 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | A | B | PASS | ok |
| 2 | C | D | FAIL | bad |
""",
    ]

    tables = _collect_param_tables(batch_contents, batch_expected_params={})
    merged = "\n".join(tables["Batch 2"])

    assert "| 9 | 4 | 5 | 0 | 0 |" not in merged
    assert "| 1 | A | B | PASS | ok |" in merged
    assert "| 2 | C | D | FAIL | bad |" in merged


def test_collect_param_tables_falls_back_to_group_name_for_multi_param_batches():
    batch_contents = [
        """| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | +120000 m/s | FAIL | tool |
| 2 | -120000 m/s | FAIL | tool |
"""
    ]

    tables = _collect_param_tables(
        batch_contents,
        batch_expected_params={
            1: ["5.1.1 速度动态范围", "5.1.2 加速度动态范围"],
        },
    )

    assert "5.1.1 速度动态范围 / 5.1.2 加速度动态范围" in tables


def test_enforce_uncertainty_by_tool_updates_judgement_to_tool_status():
    md = """| 序号 | 点位 | 测量点 | KB编号 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10 MHz | 输出频率: 10 MHz, 相对频率偏差: 1.0×10⁻⁹ | JJF2196 | 相对频率偏差 | 10 MHz | 1.0×10⁻⁹ | N/A | 1×10⁻¹⁰ | Urel=1e-11 | FAIL | 原说明 |
"""
    out = enforce_uncertainty_by_tool(md)
    assert (
        "| 1 | 10 MHz | 输出频率: 10 MHz, 相对频率偏差: 1.0×10⁻⁹ | JJF2196 | 相对频率偏差 | 10 MHz | 1.0×10⁻⁹ | N/A | 1×10⁻¹⁰ | Urel=1e-11 | PASS |"
        in out
    )


def test_collect_param_tables_merges_same_param_with_and_without_english_suffix():
    batch_contents = [
        """### 参数：5.1.1 速度
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | A | PASS | tool |
""",
        """### 参数：5.1.1 速度(Speed)
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 2 | B | FAIL | tool |
""",
    ]

    tables = _collect_param_tables(batch_contents, batch_expected_params={})

    assert "5.1.1 速度" in tables
    assert "5.1.1 速度(Speed)" not in tables
    merged = "\n".join(tables["5.1.1 速度"])
    assert "| 1 | A | PASS | tool |" in merged
    assert "| 2 | B | FAIL | tool |" in merged


def test_collect_param_tables_merges_channel_suffix_into_base_param_name():
    batch_contents = [
        """### 参数：7 信号质量(Signal Quality)
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | 2491.75 MHz | PASS | tool |
""",
        """### 参数：7 信号质量(Signal Quality)(@I路)
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 2 | I路 | FAIL | tool |
""",
    ]

    tables = _collect_param_tables(batch_contents, batch_expected_params={})

    assert "7 信号质量" in tables
    assert "7 信号质量(Signal Quality)" not in tables
    assert "7 信号质量(Signal Quality)(@I路)" not in tables
    merged = "\n".join(tables["7 信号质量"])
    assert "| 1 | 2491.75 MHz | PASS | tool |" in merged
    assert "| 2 | I路 | FAIL | tool |" in merged
