from pathlib import Path

import pytest

from md_parser_no_llm import (
    _build_parser_fallback_output_model,
    _build_parser_fallback_slot_context,
    _build_parser_fallback_slot_output_model,
    _coerce_parser_fallback_slot_decision,
    _repair_parameter_rows_with_llm,
    parse_md_to_json,
)


class FakeRowRepairLLM:
    def invoke_structured(self, user_prompt, output_model, system_prompt=None):
        return output_model(
            action="suggest",
            section_rule="period_accuracy",
            field_bindings={
                "error_value": "日差",
                "limit_value": "允许误差",
                "cert_u": "U",
            },
            unit_family="time",
            confidence=0.95,
            reason="日差行按时间准确度修复",
        )


class FakeWrongDailyErrorLLM:
    def invoke_structured(self, user_prompt, output_model, system_prompt=None):
        return output_model(
            action="suggest",
            section_rule="frequency_accuracy",
            field_bindings={
                "measure_value": "日差",
                "error_value": "允许误差",
                "cert_u": "U",
            },
            unit_family="frequency",
            confidence=0.85,
            reason="wrong daily error repair",
        )


def _write_daily_error_md(tmp_path: Path) -> Path:
    return _write_period_accuracy_md(tmp_path, section_title="2 日差(Error Per Day)", error_header="日差")


def _write_period_accuracy_md(tmp_path: Path, *, section_title: str, error_header: str) -> Path:
    md_path = tmp_path / "daily_error.md"
    md_path.write_text(
        "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-001",
                "仪器名称：计时器",
                "校准依据：JJF 2195-2025",
                "",
                section_title,
                "<table>",
                f"<tr><th>{error_header}</th><th>允许误差</th><th>结论</th><th>U</th></tr>",
                "<tr><td>-0.65</td><td>±4320.00</td><td>P</td><td>0.03</td></tr>",
                "</table>",
            ]
        ),
        encoding="utf-8",
    )
    return md_path


def _write_monthly_difference_md(tmp_path: Path) -> Path:
    md_path = tmp_path / "monthly_difference.md"
    md_path.write_text(
        "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-003",
                "仪器名称：石英钟表测试仪",
                "校准依据：JJG 488-2018",
                "",
                "3 瞬时月差测量范围和测量误差(Instantaneous Monthly Difference Measurement Range And Measurement Error)",
                "<table>",
                "<tr><th>标准值 (Reference)</th><th>指示值 (Indicated)</th><th>误差 (Error)</th><th>允许误差 (Limit)</th><th>结论 (Pass/Fail)</th><th>U (k=2)</th></tr>",
                "<tr><td>(s/m)</td><td>(s/m)</td><td>(s/m)</td><td>(s/m)</td><td></td><td>(s/m)</td></tr>",
                "<tr><td>259.2</td><td>261</td><td>2</td><td>±13</td><td>P</td><td>1</td></tr>",
                "</table>",
            ]
        ),
        encoding="utf-8",
    )
    return md_path


def _write_period_range_md(tmp_path: Path, *, section_title: str, include_error_column: bool = False) -> Path:
    md_path = tmp_path / "time_interval_measurement.md"
    headers = ["标准值", "测量值", "允许误差", "U"]
    row = ["1.00000 min", "1.00000 min", "±0.007 s", "0.002 s"]
    if include_error_column:
        headers.insert(2, "误差")
        row.insert(2, "0.00 s")

    header_html = "".join(f"<th>{header}</th>" for header in headers)
    row_html = "".join(f"<td>{value}</td>" for value in row)
    md_path.write_text(
        "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-002",
                "仪器名称：时间间隔测量仪",
                "校准依据：JJF 2195-2025",
                "",
                section_title,
                "<table>",
                f"<tr>{header_html}</tr>",
                f"<tr>{row_html}</tr>",
                "</table>",
            ]
        ),
        encoding="utf-8",
    )
    return md_path


def _write_output_time_interval_accuracy_md(
    tmp_path: Path,
    *,
    section_title: str,
    include_nominal: bool = True,
) -> Path:
    md_path = tmp_path / "output_time_interval_accuracy.md"
    headers = []
    row = []
    if include_nominal:
        headers.append("标称值 (Nominal)")
        row.append("1 s")
    headers.extend(["标准值 (Reference)", "误差 (Error)", "允许范围 (Limit)", "U (k=2)"])
    row.extend(["1.0000 s", "0.0 ms", "±3.0 ms", "0.1 ms"])

    header_html = "".join(f"<th>{header}</th>" for header in headers)
    row_html = "".join(f"<td>{value}</td>" for value in row)
    md_path.write_text(
        "\n".join(
            [
                "# 校准证书",
                "证书编号：TEST-004",
                "仪器名称：电子秒表",
                "校准依据：JJG 601-2022",
                "",
                section_title,
                "<table>",
                f"<tr>{header_html}</tr>",
                f"<tr>{row_html}</tr>",
                "</table>",
            ]
        ),
        encoding="utf-8",
    )
    return md_path


@pytest.mark.parametrize(
    ("section_title", "error_header"),
    [
        ("2 日差(Error Per Day)", "日差"),
        ("2 日偏差(Daily Deviation)", "日偏差"),
        ("2 走时误差(Time Error)", "走时误差"),
        ("2 时间间隔误差(Time Interval Error)", "误差"),
        ("2 周期测量误差(Period Measurement Error)", "误差"),
    ],
)
def test_parse_md_to_json_period_accuracy_family_maps_to_period_accuracy(
    tmp_path,
    section_title,
    error_header,
):
    md_path = _write_period_accuracy_md(
        tmp_path,
        section_title=section_title,
        error_header=error_header,
    )

    result = parse_md_to_json(str(md_path))

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__normalized_fields"]["error_value"] == "-0.65"
    assert row["__normalized_fields"]["limit_value"] == "±4320.00"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"
    assert row["__parameter_contract"]["error_value"] == "-0.65"
    assert row["__parameter_contract"]["limit_value"] == "±4320.00"
    assert row["__parameter_contract"]["unit_family"] == "time"


@pytest.mark.parametrize("include_error_column", [False, True])
def test_parse_md_to_json_time_interval_measurement_stays_period_range(tmp_path, include_error_column):
    md_path = _write_period_range_md(
        tmp_path,
        section_title="3 时间间隔测量(Time Interval Measurement)",
        include_error_column=include_error_column,
    )

    result = parse_md_to_json(str(md_path))

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_range"
    assert row["__normalized_fields"]["reference_value"] == "1.00000 min"
    assert row["__normalized_fields"]["measure_value"] == "1.00000 min"
    assert row["__parameter_contract"]["semantic_target"] == "period_range"
    assert row["__parameter_contract"]["reference_value"] == "1.00000 min"
    assert row["__parameter_contract"]["measure_value"] == "1.00000 min"
    assert row["__parameter_contract"]["unit_family"] == "time"


@pytest.mark.parametrize("include_nominal", [True, False])
def test_parse_md_to_json_output_time_interval_error_rows_map_to_period_accuracy(tmp_path, include_nominal):
    md_path = _write_output_time_interval_accuracy_md(
        tmp_path,
        section_title="3 秒表功能输出时间间隔(Time Interval)",
        include_nominal=include_nominal,
    )

    result = parse_md_to_json(str(md_path))

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"
    assert row["__parameter_contract"]["reference_value"] == "1.0000 s"
    assert row["__parameter_contract"]["error_value"] == "0.0 ms"
    assert row["__parameter_contract"]["limit_value"] == "±3.0 ms"
    assert row["__parameter_contract"]["cert_u"] == "0.1 ms"
    assert row["__parameter_contract"]["unit_family"] == "time"


def test_parse_md_to_json_preserves_section_hint_when_contract_canonicalizes_target(tmp_path):
    md_path = _write_output_time_interval_accuracy_md(
        tmp_path,
        section_title="3 秒表功能输出时间间隔(Time Interval)",
        include_nominal=True,
    )

    result = parse_md_to_json(str(md_path))

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__parser_meta"]["section_hint_rule"] == "period_range"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"


def test_parse_md_to_json_daily_error_without_llm_maps_to_period_accuracy(tmp_path):
    md_path = _write_daily_error_md(tmp_path)

    result = parse_md_to_json(str(md_path))

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__normalized_fields"]["error_value"] == "-0.65"
    assert row["__normalized_fields"]["limit_value"] == "±4320.00"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"
    assert row["__parameter_contract"]["error_value"] == "-0.65"
    assert row["__parameter_contract"]["limit_value"] == "±4320.00"
    assert row["__parameter_contract"]["unit_family"] == "time"


def test_parse_md_to_json_daily_error_with_llm_keeps_deterministic_contract(tmp_path):
    md_path = _write_daily_error_md(tmp_path)

    result = parse_md_to_json(str(md_path), llm_client=FakeRowRepairLLM())

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__parser_meta"].get("llm_fallback_applied") is not True
    assert row["__normalized_fields"]["error_value"] == "-0.65"
    assert row["__normalized_fields"]["limit_value"] == "±4320.00"
    assert row["__normalized_fields"]["cert_u"] == "0.03"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"
    assert row["__parameter_contract"]["error_value"] == "-0.65"
    assert row["__parameter_contract"]["limit_value"] == "±4320.00"
    assert row["__parameter_contract"]["cert_u"] == "0.03"
    assert row["__parameter_contract"]["unit_family"] == "time"


def test_parse_md_to_json_daily_error_normalizes_wrong_llm_semantic_to_period_accuracy(tmp_path):
    md_path = _write_daily_error_md(tmp_path)

    result = parse_md_to_json(str(md_path), llm_client=FakeWrongDailyErrorLLM())

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__normalized_fields"]["error_value"] == "-0.65"
    assert row["__normalized_fields"]["limit_value"] == "±4320.00"
    assert row["__normalized_fields"]["cert_u"] == "0.03"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"
    assert row["__parameter_contract"]["error_value"] == "-0.65"
    assert row["__parameter_contract"]["limit_value"] == "±4320.00"
    assert row["__parameter_contract"]["unit_family"] == "time"
    assert row["__parser_meta"].get("llm_fallback_applied") is not True


def test_parse_md_to_json_monthly_difference_maps_to_period_accuracy_with_time_units(tmp_path):
    md_path = _write_monthly_difference_md(tmp_path)

    result = parse_md_to_json(str(md_path))

    row = result["依据参数_中间数据"][0]
    assert row["__parser_meta"]["section_rule"] == "period_accuracy"
    assert row["__normalized_fields"]["reference_value"] == "259.2 s/m"
    assert row["__normalized_fields"]["measure_value"] == "261 s/m"
    assert row["__normalized_fields"]["error_value"] == "2 s/m"
    assert row["__normalized_fields"]["limit_value"] == "±13 s/m"
    assert row["__normalized_fields"]["cert_u"] == "1 s/m"
    assert row["__parameter_contract"]["semantic_target"] == "period_accuracy"
    assert row["__parameter_contract"]["unit_family"] == "time"


def test_parser_fallback_output_model_rejects_invalid_headers_and_rules():
    output_model = _build_parser_fallback_output_model(
        {
            "日差": "-0.65",
            "允许误差": "±4320.00",
            "U": "0.03",
        }
    )

    valid = output_model(
        action="suggest",
        section_rule="period_accuracy",
        field_bindings={
            "error_value": "日差",
            "limit_value": "允许误差",
            "cert_u": "U",
        },
        unit_family="time",
        confidence=0.95,
        reason="valid repair",
    )
    assert valid.field_bindings.error_value == "日差"

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            section_rule="period_accuracy",
            field_bindings={"error_value": "不存在的列"},
            unit_family="time",
            confidence=0.95,
            reason="invalid header",
        )

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            section_rule="not_a_rule",
            field_bindings={"error_value": "日差"},
            unit_family="time",
            confidence=0.95,
            reason="invalid rule",
        )


def test_parser_fallback_slot_context_and_coercion_work_without_global_dictionary():
    details = {
        "日差": "-0.65",
        "允许误差": "±4320.00",
        "结论": "P",
        "U": "0.03",
    }
    slot_context = _build_parser_fallback_slot_context(details)
    assert slot_context["header_slots"] == [
        {"slot": 1, "header": "日差", "value": "-0.65"},
        {"slot": 2, "header": "允许误差", "value": "±4320.00"},
        {"slot": 3, "header": "结论", "value": "P"},
        {"slot": 4, "header": "U", "value": "0.03"},
    ]

    output_model = _build_parser_fallback_slot_output_model(details)
    decision = output_model(
        action="suggest",
        section_rule="period_accuracy",
        field_bindings={
            "error_value": 1,
            "limit_value": 2,
            "cert_u": 4,
        },
        unit_family="time",
        confidence=0.95,
        reason="slot repair",
    )
    coerced = _coerce_parser_fallback_slot_decision(decision, details)
    assert coerced is not None
    assert coerced.field_bindings == {
        "error_value": "日差",
        "limit_value": "允许误差",
        "cert_u": "U",
    }

    with pytest.raises(Exception):
        output_model(
            action="suggest",
            section_rule="period_accuracy",
            field_bindings={"error_value": 9},
            unit_family="time",
            confidence=0.95,
            reason="invalid slot",
        )


def test_repair_parameter_rows_with_llm_reports_progress():
    events = []

    class CountingLLM:
        def invoke_structured(self, user_prompt, output_model, system_prompt=None):
            return output_model(
                action="abstain",
                section_rule="unknown",
                field_bindings={},
                unit_family="unknown",
                confidence=0.0,
                reason="skip",
            )

    rows = [
        {
            "测量值": "3 输出电平(RF Level)",
            "数据明细": {"标准值": "1 dBm", "指示值": "1 dBm", "误差": "0 dB", "允许误差": "±1 dB", "U": "0.2 dB"},
            "__parser_meta": {"parse_source": "html_table", "section_rule": "unknown"},
            "__normalized_fields": {"reference_value": "1 dBm", "measure_value": "1 dBm", "error_value": "0 dB", "limit_value": "±1 dB", "cert_u": "0.2 dB"},
            "__parameter_contract": {"semantic_target": "unknown"},
        },
        {
            "测量值": "3 输出电平(RF Level)",
            "数据明细": {"标准值": "2 dBm", "指示值": "2 dBm", "误差": "0 dB", "允许误差": "±1 dB", "U": "0.2 dB"},
            "__parser_meta": {"parse_source": "html_table", "section_rule": "unknown"},
            "__normalized_fields": {"reference_value": "2 dBm", "measure_value": "2 dBm", "error_value": "0 dB", "limit_value": "±1 dB", "cert_u": "0.2 dB"},
            "__parameter_contract": {"semantic_target": "unknown"},
        },
    ]

    _repair_parameter_rows_with_llm(
        rows,
        llm_client=CountingLLM(),
        progress_callback=lambda stage, current, total, message: events.append((stage, current, total, message)),
    )

    assert events[0] == ("row_llm_fallback_start", 0, 2, "参数行 LLM 修补启动")
    assert events[1][0] == "row_llm_fallback_progress"
    assert events[1][1:3] == (1, 2)
    assert events[2][0] == "row_llm_fallback_progress"
    assert events[2][1:3] == (2, 2)
    assert events[-1] == ("row_llm_fallback_done", 2, 2, "参数行 LLM 修补完成")
