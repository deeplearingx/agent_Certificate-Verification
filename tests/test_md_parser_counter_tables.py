from pathlib import Path

from md_parser_no_llm import _match_column_alias, parse_md_to_json


def test_match_column_alias_does_not_map_frequency_header_to_cert_u():
    assert _match_column_alias("频率 (Frequency)") == ("measure_value", "frequency")


def test_parse_md_to_json_parses_counter_sensitivity_and_accuracy_tables():
    result = parse_md_to_json(str(Path("local_md/4GC24000017-0001.md")))
    rows = result["依据参数_中间数据"]

    sensitivity_row = next(
        row for row in rows if row["测量值"] == "3 频率测量范围及灵敏度(Frequency Measurement and Sensitivity)"
    )
    frequency_rows = [
        row for row in rows if row["测量值"].startswith("4 频率测量误差(Frequency Measurement Error)")
    ]
    period_rows = [row for row in rows if row["测量值"] == "5 周期测量误差(Period Measurement Error)"]

    assert sensitivity_row["__normalized_fields"]["measure_value"] == "1 Hz"
    assert sensitivity_row["__normalized_fields"]["error_value"] == "9.1 mV"
    assert sensitivity_row["__normalized_fields"]["cert_u"] == "0.3 mV"

    assert sensitivity_row["__parser_meta"]["section_rule"] == "frequency_range"

    assert len(frequency_rows) == 11
    assert frequency_rows[0]["__parser_meta"]["section_rule"] == "frequency_accuracy"
    assert frequency_rows[0]["__normalized_fields"]["reference_value"] == "1.000000 Hz"
    assert frequency_rows[0]["__normalized_fields"]["measure_value"] == "1.0000000 Hz"
    assert frequency_rows[0]["__normalized_fields"]["error_value"] == "0.0000 mHz"
    assert frequency_rows[0]["__normalized_fields"]["cert_u"] == "0.0000 mHz"

    assert len(period_rows) == 3
    assert period_rows[0]["__parser_meta"]["section_rule"] == "period_accuracy"
    assert period_rows[0]["__normalized_fields"]["reference_value"] == "10.00000000 μs"
    assert period_rows[1]["__normalized_fields"]["reference_value"] == "100.0000000 ns"
    assert period_rows[2]["__normalized_fields"]["measure_value"] == "5.00000002 ns"


def test_parse_md_to_json_generic_time_rows_upgrade_to_period_accuracy_for_relay_report():
    result = parse_md_to_json(str(Path("local_md/2GB25002166-0005.md")))
    rows = [row for row in result["依据参数_中间数据"] if row["测量值"] == "2 时间(Time)"]

    assert rows
    assert all(row["__parameter_contract"]["semantic_target"] == "period_accuracy" for row in rows)
    assert all(row["__parameter_contract"]["unit_family"] == "time" for row in rows)


def test_parse_md_to_json_skips_structural_t1_t2_header_rows():
    result = parse_md_to_json(str(Path("local_md/2GB25000124-0002.md")))
    rows = [row for row in result["依据参数_中间数据"] if row["测量值"] == "3 时间(Time)-DHC9A"]

    assert rows
    assert all(row["__normalized_fields"].get("reference_value") != "T2" for row in rows)
    assert all(row["__normalized_fields"].get("error_value") != "T2" for row in rows)
    assert all(row["__parameter_contract"]["semantic_target"] == "period_accuracy" for row in rows)
    assert all(row["__parameter_contract"]["unit_family"] == "time" for row in rows)


def test_parse_md_to_json_time_accuracy_rows_keep_time_unit_family_even_with_percent_limit():
    result = parse_md_to_json(str(Path("local_md/2GB25025182-0012.md")))
    rows = [row for row in result["依据参数_中间数据"] if row["测量值"] == "3 计时准确度(Time Accuracy)"]

    assert rows
    assert all(row["__parameter_contract"]["semantic_target"] == "period_accuracy" for row in rows)
    assert all(row["__parameter_contract"]["unit_family"] == "time" for row in rows)
