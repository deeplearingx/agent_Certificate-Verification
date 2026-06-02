from langchain_app.checks.parameter import parameter as parameter_module


def _make_row(*, basis_code: str, status: str, reason: str) -> parameter_module.ParamCheckRow:
    raw_row = {
        "点位": "N/A",
        "测量点": "示例参数",
        "测试条件": "N/A",
        "KB编号": "无",
        "KB条目": "N/A",
        "证书匹配项": "N/A",
        "范围": "N/A",
        "证书误差": "N/A",
        "允许误差": "N/A",
        "证书U": "N/A",
        "KB_U": "N/A",
        "判定": status,
        "说明": reason,
    }
    return parameter_module.ParamCheckRow(
        basis_code=basis_code,
        batch_label="示例参数",
        batch_index=1,
        row_index=1,
        cert_index=1,
        param_name="示例参数",
        point_key="示例参数|N/A|N/A",
        match_value="N/A",
        point_value="N/A",
        status=status,
        reason=reason,
        kb_code="无",
        kb_item="N/A",
        range_text="N/A",
        cert_error="N/A",
        limit_text="N/A",
        cert_u="N/A",
        kb_u="N/A",
        raw_row=raw_row,
    )


def test_summarize_structured_rows_splits_review_categories():
    rows = [
        _make_row(basis_code="JJF 1471-2014", status="REVIEW", reason="`待人工核验` same basis missing kb subtype: iq_offset"),
        _make_row(basis_code="JJF 1931-2021", status="REVIEW", reason="`待人工核验` missing required fields: error_value"),
        _make_row(basis_code="JJF 9999-2024", status="REVIEW", reason="`待人工核验` unknown semantic"),
    ]

    summary = parameter_module._summarize_structured_rows(rows)

    assert summary["review"] == 3
    assert summary["kb_missing_review"] == 1
    assert summary["field_gap_review"] == 1
    assert summary["semantic_review"] == 1
    assert summary["other_review"] == 0


def test_build_merged_reason_reports_review_categories():
    rows = [
        _make_row(basis_code="JJF 1471-2014", status="REVIEW", reason="`待人工核验` same basis missing kb subtype: power_dynamic_range"),
        _make_row(basis_code="JJF 1931-2021", status="REVIEW", reason="`待人工核验` missing required fields: error_value"),
    ]

    merged_reason = parameter_module._build_merged_reason(
        rows,
        final_status="REVIEW",
        final_rationale="没有 PASS，但存在 REVIEW，因此最终按 REVIEW 归并",
    )

    assert "`REVIEW分类`" in merged_reason
    assert "KB覆盖缺口:1" in merged_reason
    assert "源字段缺口:1" in merged_reason
    assert "`REVIEW原因`" in merged_reason
    assert "同规程下没有可直接匹配的KB条目，需人工核验" in merged_reason
