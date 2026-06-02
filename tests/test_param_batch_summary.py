from param_check import (
    _extract_param_name,
    _merge_table_lines,
    enforce_batch_summary_from_table,
)


def test_extract_param_name_supports_two_heading_styles():
    assert _extract_param_name("## 参数：相对频率偏差") == "相对频率偏差"
    assert _extract_param_name("### 参数：4 频率测量误差(Frequency Measurement Error)") == (
        "4 频率测量误差(Frequency Measurement Error)"
    )
    assert _extract_param_name("## 核验结果：5 周期测量误差(Period Measurement Error)") == (
        "5 周期测量误差(Period Measurement Error)"
    )
    assert _extract_param_name("**参数名称：5 周期测量误差(Period Measurement Error)**") == (
        "5 周期测量误差(Period Measurement Error)"
    )


def test_extract_param_name_supports_parameter_group_heading():
    assert _extract_param_name("## 参数组：5.1.4 加加速度动态范围 / 5.2.1 伪距分辨力") == (
        "5.1.4 加加速度动态范围 / 5.2.1 伪距分辨力"
    )


def test_merge_table_lines_keeps_unique_rows():
    existing = [
        "| 序号 | 判定 |",
        "| --- | --- |",
        "| 1 | PASS |",
    ]
    new_lines = [
        "| 序号 | 判定 |",
        "| --- | --- |",
        "| 1 | PASS |",
        "| 2 | FAIL |",
    ]
    merged = _merge_table_lines(existing, new_lines)
    assert merged == [
        "| 序号 | 判定 |",
        "| --- | --- |",
        "| 1 | PASS |",
        "| 2 | FAIL |",
    ]


def test_enforce_batch_summary_from_table_uses_status_column():
    md = """## 参数：相对频率偏差
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | 10MHz | FAIL | 工具结果 |

**核验总结：**
- 所有测量点均通过核验
"""
    out = enforce_batch_summary_from_table(md)
    assert "所有测量点均通过核验" not in out
    assert "PASS 0 个，FAIL 1 个" in out
    assert "总体判定：FAIL" in out
