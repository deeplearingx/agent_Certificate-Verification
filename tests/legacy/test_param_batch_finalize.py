from param_check import enforce_batch_summary_from_table


def test_enforce_batch_summary_removes_legacy_summary_block():
    md = """## 参数：相对频率偏差
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | 10MHz | PASS | 工具结果 |
**核验总结：**
- 本批次共 1 个测量点，PASS 1 个，FAIL 0 个
- 总体判定：PASS

**核验总结**：1. 依据一致性 2. KB选择

所有核验点均通过，整体判定为PASS。
---
"""
    out = enforce_batch_summary_from_table(md)
    assert "所有核验点均通过" not in out
    assert "1. 依据一致性" not in out
    assert out.count("**核验总结：**") == 1


def test_enforce_batch_summary_removes_plain_summary_block():
    md = """## 参数：电秒表输出时间间隔
| 序号 | 点位 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1 | 100 s | FAIL | 工具结果 |

**总结：** 所有14个测量点均通过核验。
后续说明也应当被跳过。
---
"""
    out = enforce_batch_summary_from_table(md)
    assert "所有14个测量点均通过核验" not in out
    assert "后续说明也应当被跳过" not in out
    assert "PASS 0 个，FAIL 1 个" in out
