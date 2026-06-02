from types import SimpleNamespace

from langchain_app.checks.parameter.parameter import (
    _build_evaluation_record,
    ParamCheckRow,
    _build_table_row_dict,
    _extract_param_measure_value,
    _evaluate_reference_measure_error_consistency,
    _evaluate_selected_kb_results,
    _merge_param_rows,
    _record_to_param_check_row,
    _resolve_selected_kb_status,
    _summarize_structured_rows,
    _extract_kb_error_limit,
    _extract_param_condition_text,
    _format_cert_axis_for_candidate,
    _resolve_range_probe_value,
    _resolve_uncertainty_probe_value,
    _resolve_match_display_value,
    _row_to_markdown_line,
    _summarize_check_result,
    _simplify_review_reason_text,
)
from langchain_app.checks.parameter.validator import verify_error_logic


def test_extract_param_condition_text_from_power_table_detail():
    param = {
        "param_name": "3 功率电平(Power Level)(at Hight level Output 1)",
        "信号 (Signal)": "GPS_L1",
        "频率 (Frequency)": "1575.42 MHz",
        "可调节功率值 (Slider Power value)": "15 dB",
        "标准值 (Reference)": "14.93 dBm",
        "U (k=2)": "0.40 dB",
        "__normalized_fields": {
            "measure_value": "1575.42 MHz",
            "reference_value": "14.93 dBm",
            "cert_u": "0.40 dB",
        },
    }

    condition = _extract_param_condition_text(param)

    assert condition == "信号: GPS_L1; 频率: 1575.42 MHz"


def test_extract_param_condition_text_skips_plain_frequency_result_rows():
    param = {
        "param_name": "2 参考频率(Reference Frequency)",
        "标准值 (Reference)": "10 MHz",
        "误差 (Error)": "-0.226 Hz",
        "U (k=2)": "0.03 mHz",
    }

    assert _extract_param_condition_text(param) == ""


def test_markdown_row_includes_condition_column():
    row = SimpleNamespace(
        status="PASS",
        reason="ok",
        raw_row=_build_table_row_dict(
            point_value="15 dB",
            param_name="3 功率电平(Power Level)(at Hight level Output 1)",
            condition_text="信号: GPS_L1; 频率: 1575.42 MHz",
            kb_code="JJF1931",
            kb_item="电平",
            match_value="14.93 dBm",
            range_text="0～30)dBm(9 kHz～26.5 GHz",
            cert_error="-0.07 dB",
            limit_text="N/A",
            cert_u="0.40 dB",
            kb_u="U=(0.04~0.18)dB",
            status="PASS",
            reason="ok",
        ),
    )

    line = _row_to_markdown_line(1, row)

    assert "| 信号: GPS_L1; 频率: 1575.42 MHz |" in line


def test_period_range_match_display_uses_range_probe_value():
    selected_kb = SimpleNamespace(capability_target="period_range")

    assert _resolve_match_display_value(selected_kb, "0 min", "1.000000 h") == "1.000000 h"


def test_period_range_probe_uses_reference_value():
    selected_kb = SimpleNamespace(capability_target="period_range", semantic_subtype="", source={})
    param = {
        "__parameter_contract": {
            "measure_value": "0 min",
            "reference_value": "1.000000 h",
        }
    }

    assert _resolve_range_probe_value(selected_kb, "0 min", "0.02 s", param=param, reference_val="1.000000 h") == "1.000000 h"


def test_reference_oscillator_metric_range_probe_uses_error_value_when_kb_range_is_metric_interval():
    selected_kb = SimpleNamespace(
        capability_target="reference_oscillator",
        semantic_subtype="relative_frequency_deviation",
        source={"measure_range_text": "相对频率偏差：±(1×10^-5～1×10^-10)"},
    )
    param = {
        "__parameter_contract": {
            "condition_value": "10 MHz",
            "error_value": "-4.1×10^-7",
        }
    }

    assert _resolve_range_probe_value(selected_kb, "", "-4.1×10^-7", param=param, reference_val="") == "-4.1×10^-7"


def test_reference_oscillator_range_probe_can_recover_candidate_frequency_point_when_condition_missing():
    selected_kb = SimpleNamespace(
        capability_target="reference_oscillator",
        semantic_subtype="timebase_accuracy",
        source={"measure_range_text": "10 MHz"},
    )
    param = {"__parameter_contract": {"error_value": "8.9×10^-8"}}

    assert _resolve_range_probe_value(selected_kb, "", "8.9×10^-8", param=param, reference_val="") == "10 MHz"


def test_frequency_accuracy_timebase_range_probe_uses_nominal_frequency_instead_of_error():
    selected_kb = SimpleNamespace(
        capability_target="frequency_accuracy",
        semantic_subtype="timebase_accuracy",
        source={"measure_range_text": "5 kHz～60 GHz"},
    )
    param = {
        "__parameter_contract": {
            "semantic_target": "frequency_accuracy",
            "semantic_subtype": "timebase_accuracy",
            "nominal_value": "10 MHz",
            "reference_value": "10.000000226 MHz",
            "error_value": "-0.226 Hz",
        }
    }

    assert _resolve_range_probe_value(selected_kb, "", "-0.226 Hz", param=param, reference_val="10.000000226 MHz") == "10 MHz"


def test_frequency_accuracy_timebase_range_probe_uses_single_frequency_point_for_discrete_kb():
    selected_kb = SimpleNamespace(
        capability_target="frequency_accuracy",
        semantic_subtype="timebase_accuracy",
        source={"measure_range_text": "10 MHz"},
    )
    param = {
        "__parameter_contract": {
            "semantic_target": "frequency_accuracy",
            "semantic_subtype": "timebase_accuracy",
            "nominal_value": "10 MHz",
            "error_value": "-0.226 Hz",
        }
    }

    assert _resolve_range_probe_value(selected_kb, "", "-0.226 Hz", param=param, reference_val="") == "10 MHz"


def test_reference_oscillator_without_plausible_cert_frequency_stays_review():
    candidate_source = {
        "measure_range_text": "1 MHz,2 MHz,5 MHz,10 MHz",
        "measured": "内晶振输出频率",
        "uncertainty": {"value_display": "Urel=3×10⁻¹²"},
        "file_code": "JJG238",
    }
    selected_candidate = SimpleNamespace(
        source=candidate_source,
        condition_axis="frequency_band",
        band_kind="discrete",
        discrete_points=(1_000_000.0, 2_000_000.0, 5_000_000.0, 10_000_000.0),
        capability_target="reference_oscillator",
        result_quantity="frequency_output",
    )
    selected_kb = SimpleNamespace(
        capability_target="reference_oscillator",
        semantic_subtype="",
        source=candidate_source,
        result_quantity="frequency_output",
    )
    selection_result = SimpleNamespace(
        cert_point=SimpleNamespace(
            semantic_target="reference_oscillator",
            semantic_subtype="",
        ),
        audit=SimpleNamespace(
            selected_target_relation="exact",
            used_fallback_candidate_target=False,
        ),
    )
    param = {
        "param_name": "3 时基(Time Base)",
        "__parameter_contract": {
            "nominal_value": "1 Hz",
            "reference_value": "1.00000145 Hz",
            "error_value": "-0.00000145 Hz",
            "limit_value": "±0.0000050 Hz",
        },
        "数据明细": {
            "标称值 (Nominal)": "1 Hz",
            "标准值 (Reference)": "1.00000145 Hz",
        },
    }

    evaluation = _evaluate_selected_kb_results(
        selection_result=selection_result,
        selected_candidate=selected_candidate,
        selected_kb=selected_kb,
        param=param,
        measure_val="",
        reference_val="1.00000145 Hz",
        error_val="-0.00000145 Hz",
        cert_u="0.00000039 Hz",
    )

    assert evaluation["range_result"]["status"] == "REVIEW"
    assert "证书仅给出低频显示/输出 1 Hz" in evaluation["range_result"]["reason"]
    assert evaluation["semantic_ambiguity"]["detected"] is True
    assert _resolve_selected_kb_status(
        evaluation["range_result"],
        evaluation["error_result"],
        evaluation["u_result"],
        evaluation["source_anomaly"],
        evaluation["semantic_ambiguity"],
    ) == "REVIEW"


def test_period_accuracy_output_time_interval_range_probe_uses_reference_value():
    selected_kb = SimpleNamespace(capability_target="period_accuracy", semantic_subtype="output_time_interval", source={})
    param = {
        "__parameter_contract": {
            "reference_value": "1.0000 s",
            "error_value": "0.0 ms",
        }
    }

    assert _resolve_range_probe_value(selected_kb, "", "0.0 ms", param=param, reference_val="1.0000 s") == "1.0000 s"


def test_output_time_interval_probe_recovers_subtype_from_kb_text_when_contract_is_stale():
    selected_kb = SimpleNamespace(
        capability_target="period_accuracy",
        semantic_subtype="",
        measured="输出时间间隔",
        unit_family="time",
        source={"measured": "输出时间间隔", "measure_range_text": ">1 ms～9999.9 s"},
    )
    param = {
        "param_name": "3 秒表功能输出时间间隔(Time Interval)",
        "__parameter_contract": {
            "semantic_target": "period_accuracy",
            "semantic_subtype": "__default__",
            "reference_value": "1.0000 s",
            "error_value": "0.0 ms",
            "cert_u": "0.1 ms",
            "unit_family": "time",
        },
    }

    assert _resolve_range_probe_value(selected_kb, "", "0.0 ms", param=param, reference_val="1.0000 s") == "1.0000 s"
    assert _resolve_uncertainty_probe_value(param, "", "0.0 ms", selected_kb=selected_kb, reference_val="1.0000 s") == "1.0000 s"


def test_period_accuracy_default_probe_uses_reference_value_for_range_and_uncertainty():
    selected_kb = SimpleNamespace(
        capability_target="period_accuracy",
        semantic_subtype="__default__",
        measured="时间(延时)",
        unit_family="time",
        source={"measured": "时间(延时)", "measure_range_text": "1 ms～9999 s"},
    )
    param = {
        "param_name": "2 时间(Time)",
        "__parameter_contract": {
            "semantic_target": "period_accuracy",
            "semantic_subtype": "__default__",
            "reference_value": "10.02 s",
            "error_value": "-0.02 s",
            "cert_u": "0.01 s",
            "unit_family": "time",
        },
    }

    assert _resolve_range_probe_value(selected_kb, "", "-0.02 s", param=param, reference_val="10.02 s") == "10.02 s"
    assert _resolve_uncertainty_probe_value(
        param,
        "",
        "-0.02 s",
        selected_kb=selected_kb,
        reference_val="10.02 s",
    ) == "10.02 s"


def test_reference_oscillator_range_probe_prefers_candidate_applicability_point_over_offset_reference():
    selected_kb = SimpleNamespace(
        capability_target="reference_oscillator",
        semantic_subtype="warmup_characteristics",
        source={"measure_range_text": "10 MHz"},
    )
    param = {
        "__parameter_contract": {
            "semantic_target": "reference_oscillator",
            "semantic_subtype": "warmup_characteristics",
            "reference_value": "10.000000693 MHz",
            "error_value": "-0.693 Hz",
        }
    }

    assert _resolve_range_probe_value(selected_kb, "", "-0.693 Hz", param=param, reference_val="10.000000693 MHz") == "10 MHz"


def test_reference_oscillator_limit_extraction_ignores_metric_labels_when_strict():
    source = {
        "raw": "相对频率偏差：10 MHz",
        "measure_range_text": "相对频率偏差：10 MHz",
    }

    assert _extract_kb_error_limit(source, strict_keys_only=True) == "N/A"


def test_reference_measure_error_consistency_flags_source_anomaly():
    result = _evaluate_reference_measure_error_consistency(
        "225.000000 MHz",
        "10.00038 MHz",
        "0.38 kHz",
    )

    assert result["detected"] is True
    assert "parser/source anomaly" in result["reason"]


def test_extract_param_measure_value_does_not_reuse_range_point_for_accuracy_row():
    param = {
        "param_name": "2 计时(Time)",
        "__normalized_fields": {
            "point_value": "0.01ms~9.99999s",
            "nominal_value": "0.001 s",
            "reference_value": "0.00099 s",
            "error_value": "0.00001 s",
        },
        "__parameter_contract": {
            "row_shape": "item_nominal_reference_error_u",
            "semantic_target": "period_range",
        },
        "__parser_meta": {
            "header_rules": {
                "point_value": "量程 (Range)",
                "reference_value": "标准值 (Reference)",
                "error_value": "误差 (Error)",
            }
        },
    }

    assert _extract_param_measure_value(param) == ""


def test_period_accuracy_row_with_range_point_can_pass_without_source_anomaly():
    candidate_source = {
        "measure_range_text": "≥1.5 μs～24 h",
        "measured": "时间间隔",
        "uncertainty": {"value_display": "0.58%"},
        "file_code": "JJG238",
    }
    selected_candidate = SimpleNamespace(
        source=candidate_source,
        condition_axis="period_band",
        capability_target="period_range",
        result_quantity="time_interval",
    )
    selected_kb = SimpleNamespace(
        capability_target="period_range",
        semantic_subtype="",
        source=candidate_source,
        result_quantity="time_interval",
    )
    selection_result = SimpleNamespace(
        cert_point=SimpleNamespace(
            semantic_target="period_range",
            semantic_subtype="",
        ),
        audit=SimpleNamespace(
            selected_target_relation="exact",
            used_fallback_candidate_target=False,
        ),
    )
    param = {
        "param_name": "2 计时(Time)",
        "__normalized_fields": {
            "point_value": "0.01ms~9.99999s",
            "nominal_value": "0.001 s",
            "reference_value": "0.00099 s",
            "error_value": "0.00001 s",
            "limit_value": "±0.00001 s",
            "cert_u": "0.00001 s",
        },
        "__parameter_contract": {
            "row_shape": "item_nominal_reference_error_u",
            "semantic_target": "period_range",
            "reference_value": "0.00099 s",
            "error_value": "0.00001 s",
            "limit_value": "±0.00001 s",
            "cert_u": "0.00001 s",
        },
        "__parser_meta": {
            "header_rules": {
                "point_value": "量程 (Range)",
                "reference_value": "标准值 (Reference)",
                "error_value": "误差 (Error)",
                "cert_u": "U (k=2)",
            }
        },
    }

    measure_val = _extract_param_measure_value(param)
    assert measure_val == ""

    evaluation = _evaluate_selected_kb_results(
        selection_result=selection_result,
        selected_candidate=selected_candidate,
        selected_kb=selected_kb,
        param=param,
        measure_val=measure_val,
        reference_val="0.00099 s",
        error_val="0.00001 s",
        cert_u="0.00001 s",
    )

    assert evaluation["source_anomaly"]["detected"] is False
    assert evaluation["range_result"]["status"] == "PASS"
    assert evaluation["error_result"]["status"] == "PASS"
    assert evaluation["u_result"]["status"] == "PASS"
    assert _resolve_selected_kb_status(
        evaluation["range_result"],
        evaluation["error_result"],
        evaluation["u_result"],
        evaluation["source_anomaly"],
        evaluation["semantic_ambiguity"],
    ) == "PASS"


def test_reference_oscillator_evaluation_does_not_treat_frequency_point_as_error_limit():
    selected_kb = SimpleNamespace(
        capability_target="reference_oscillator",
        semantic_subtype="relative_frequency_deviation",
        measured="晶振频率",
        source={
            "file_code": "JJF 2196",
            "measured": "晶振频率",
            "measure_range_text": "相对频率偏差：10 MHz",
            "raw": "相对频率偏差：10 MHz",
            "uncertainty": {"type": "Urel", "value_display": "Urel=1.0×10⁻¹¹"},
        },
    )

    evaluation = _evaluate_selected_kb_results(
        selection_result=None,
        selected_candidate=None,
        selected_kb=selected_kb,
        param={
            "param_name": "2.1 相对频率偏差(Relative Frequency Deviation)",
            "__parameter_contract": {
                "item_label": "10 MHz",
                "error_value": "-4.1×10^-7",
                "cert_u": "1.0×10^-11",
            },
        },
        measure_val="",
        reference_val="10 MHz",
        error_val="-4.1×10^-7",
        cert_u="1.0×10^-11",
    )

    assert evaluation["display_limit"] == "N/A"
    assert evaluation["error_result"]["status"] == "PASS"
    assert "误差或限值缺失 -> Skip" in evaluation["error_result"]["reason"]


def test_reference_oscillator_metric_interval_uses_metric_probe_for_range_check():
    selected_kb = SimpleNamespace(
        capability_target="reference_oscillator",
        semantic_subtype="relative_frequency_deviation",
        measured="频率",
        source={
            "file_code": "JJF 1984",
            "measured": "频率",
            "measure_range_text": "相对频率偏差：±(1×10^-5～1×10^-10)",
            "raw": "相对频率偏差：±(1×10^-5～1×10^-10)",
            "uncertainty": {"type": "Urel", "value_display": "Urel=1.0×10⁻¹¹"},
        },
    )

    evaluation = _evaluate_selected_kb_results(
        selection_result=None,
        selected_candidate=None,
        selected_kb=selected_kb,
        param={
            "param_name": "2.3 相对频率偏差(Relative Frequency Deviation)",
            "__parameter_contract": {
                "condition_value": "10 MHz",
                "measure_value": "10 MHz",
                "error_value": "4×10^-10",
                "cert_u": "1.0×10^-10",
            },
        },
        measure_val="10 MHz",
        reference_val="10 MHz",
        error_val="4×10^-10",
        cert_u="1.0×10^-10",
    )

    assert evaluation["range_probe_value"] == "4×10^-10"
    assert evaluation["range_result"]["status"] == "PASS"


def test_allowable_error_display_and_check_use_certificate_limit_only():
    selected_kb = SimpleNamespace(
        capability_target="frequency_accuracy",
        semantic_subtype="",
        measured="频率",
        source={
            "file_code": "JJF 2196",
            "measured": "频率",
            "measure_range_text": "10 Hz～18 GHz",
            "raw": "频率 10 Hz～18 GHz 允许误差 ±0.0020 kHz",
            "uncertainty": {"type": "Urel", "value_display": "Urel=6.5×10⁻¹¹"},
        },
    )

    evaluation = _evaluate_selected_kb_results(
        selection_result=None,
        selected_candidate=None,
        selected_kb=selected_kb,
        param={
            "param_name": "4 频率测量误差(Frequency Measurement Error)",
            "__parameter_contract": {
                "measure_value": "10.00005 MHz",
                "error_value": "0.005 kHz",
                "cert_u": "0.0006 kHz",
            },
        },
        measure_val="10.00005 MHz",
        reference_val="",
        error_val="0.005 kHz",
        cert_u="0.0006 kHz",
    )

    assert evaluation["kb_error"] == "±0.0020 kHz"
    assert evaluation["display_limit"] == "N/A"
    assert evaluation["error_result"]["status"] == "PASS"
    assert "误差或限值缺失 -> Skip" in evaluation["error_result"]["reason"]


def test_symmetric_error_limit_reason_uses_greater_than_when_over_limit():
    result = verify_error_logic("0.005 kHz", "±0.0020 kHz", "10.00005 MHz")

    assert '"status": "FAIL"' in result
    assert "abs(0.005 kHz) > ±0.0020 kHz" in result


def test_source_anomaly_does_not_override_real_fail():
    status = _resolve_selected_kb_status(
        {"status": "PASS"},
        {"status": "FAIL"},
        {"status": "PASS"},
        {"detected": True, "reason": "parser/source anomaly"},
    )

    assert status == "FAIL"


def test_summarize_check_result_prefers_short_human_readable_text():
    assert (
        _summarize_check_result("范围", {"status": "PASS", "reason": "范围核验:PASS(10 MHz 在 [1 MHz, 20 MHz])"})
        == "范围符合（对比值: 10 MHz；允许区间: [1 MHz, 20 MHz]）"
    )
    assert _summarize_check_result("误差", {"status": "PASS", "reason": "误差或限值缺失 -> Skip"}) == "误差项缺少证书允许误差，已跳过"
    assert (
        _summarize_check_result(
            "不确定度",
            {
                "status": "FAIL",
                "reason": "证书不确定度(1) < 知识库要求(2)",
                "cert_u_display": "1.0×10^-12",
                "kb_u_display": "Urel=1.6×10^-11",
            },
        )
        == "不确定度不满足要求（证书U: 1.0×10^-12；要求: Urel=1.6×10^-11）"
    )


def test_summarize_check_result_uses_metric_interval_wording_for_symmetric_range_fail():
    assert (
        _summarize_check_result(
            "范围",
            {
                "status": "FAIL",
                "reason": "对称范围核验:FAIL(1.0×10^-8 不在 [1×10^-11, 2×10^-10])",
            },
        )
        == "指标值超出允许区间（指标值: 1.0×10^-8；允许区间: [1×10^-11, 2×10^-10]）"
    )


def test_simplify_review_reason_text_uses_short_chinese_summary():
    text = _simplify_review_reason_text("same basis but no compatible candidate")

    assert text == "同规程下没有可直接匹配的KB条目，需人工核验"


def test_review_summary_uses_structured_reason_type_instead_of_reason_text_guessing():
    row = ParamCheckRow(
        basis_code="JJF2196",
        batch_label="Batch 1",
        batch_index=1,
        row_index=1,
        cert_index=1,
        param_name="4 频率测量误差(Frequency Measurement Error)",
        point_key="k1",
        match_value="10.00005 MHz",
        point_value="1",
        status="REVIEW",
        reason="truncated summary text",
        kb_code="JJF2196",
        kb_item="频率",
        range_text="10 Hz～18 GHz",
        cert_error="0.005 kHz",
        limit_text="±0.020 kHz",
        cert_u="0.001 kHz",
        kb_u="Urel=6.5×10⁻¹¹",
        raw_row={"判定": "REVIEW", "说明": "truncated summary text"},
        review_reason_type="source_field_gap",
    )

    summary = _summarize_structured_rows([row])
    merged = _merge_param_rows([row])

    assert summary["field_gap_review"] == 1
    assert summary["other_review"] == 0
    assert merged[0].review_reason_type == "source_field_gap"


def test_review_summary_prefers_evaluation_record_over_reason_text():
    row_dict = _build_table_row_dict(
        point_value="1",
        param_name="4 频率测量误差(Frequency Measurement Error)",
        condition_text="N/A",
        kb_code="JJF2196",
        kb_item="频率",
        match_value="10.00038 MHz",
        range_text="10 Hz～18 GHz",
        cert_error="0.38 kHz",
        limit_text="±0.68 kHz",
        cert_u="0.003 kHz",
        kb_u="Urel=6.5×10⁻¹¹",
        status="REVIEW",
        reason="truncated summary text",
    )
    record = _build_evaluation_record(
        basis_code="JJF2196",
        batch_label="Batch 1",
        batch_index=1,
        row_index=1,
        cert_index=1,
        param_name="4 频率测量误差(Frequency Measurement Error)",
        point_key="k2",
        match_value="10.00038 MHz",
        point_value="1",
        status="REVIEW",
        reason="truncated summary text",
        anomaly_flags=("source_anomaly",),
        display_fields=row_dict,
    )

    row = _record_to_param_check_row(record)
    summary = _summarize_structured_rows([row])
    merged = _merge_param_rows([row])

    assert summary["field_gap_review"] == 1
    assert summary["other_review"] == 0
    assert merged[0].review_reason_type == "source_field_gap"


def test_evaluation_record_maps_fallback_cross_target_review_to_semantic_ambiguity():
    row_dict = _build_table_row_dict(
        point_value="10.00000 min",
        param_name="5 周期测量误差(Period Measurement Error)",
        condition_text="N/A",
        kb_code="JJF2196",
        kb_item="周期",
        match_value="10.00000 min",
        range_text="1 ns～10 s",
        cert_error="0.02 s",
        limit_text="±0.10 s",
        cert_u="0.01 s",
        kb_u="Urel=6.5×10⁻¹¹",
        status="REVIEW",
        reason="short note",
    )
    record = _build_evaluation_record(
        basis_code="JJF2196",
        batch_label="Batch 1",
        batch_index=1,
        row_index=1,
        cert_index=1,
        param_name="5 周期测量误差(Period Measurement Error)",
        point_key="k3",
        match_value="10.00000 min",
        point_value="10.00000 min",
        status="REVIEW",
        reason="short note",
        anomaly_flags=("fallback_cross_target",),
        selected_target_relation="fallback_cross_target",
        display_fields=row_dict,
    )

    assert record.review_reason_type == "semantic_ambiguity"


def test_period_range_axis_display_prefers_reference_value():
    candidate = SimpleNamespace(condition_axis="period_band", capability_target="period_range")

    assert _format_cert_axis_for_candidate(candidate, "0 min", "1.000000 h", "", "") == "3600 s"


def test_period_range_axis_display_ignores_noisy_point_text():
    candidate = SimpleNamespace(condition_axis="period_band", capability_target="period_range")
    noisy_point_text = "{\"schema_version\": 2, \"reference_value\": \"10.00000 min\", \"error_value\": \"0.02 s\"}"

    assert _format_cert_axis_for_candidate(candidate, "10 min", "10.00000 min", "", noisy_point_text) == "600 s"
