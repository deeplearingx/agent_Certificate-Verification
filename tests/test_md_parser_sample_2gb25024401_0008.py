from pathlib import Path

from md_parser_no_llm import parse_md_to_json, parse_table_to_rows


def test_parse_table_to_rows_inherits_letter_channel_values():
    table_data = [
        ["通道 (Channel)", "频率 (Frequency)", "灵敏度 (Sensitivity)", "U (k=2)"],
        ["A", "0.01 kHz", "11 mV", "0.3 mV"],
        ["", "0.1 kHz", "12 mV", "0.3 mV"],
        ["", "1 kHz", "11 mV", "0.3 mV"],
    ]

    rows = parse_table_to_rows(table_data, "3 频率测量范围及灵敏度(Frequency Measurement and Sensitivity)")

    assert rows[1]["数据明细"]["通道 (Channel)"] == "A"
    assert rows[2]["数据明细"]["通道 (Channel)"] == "A"


def test_parse_md_to_json_normalizes_scientific_notation_for_relative_frequency_sample():
    result = parse_md_to_json(str(Path("local_md/2GB25024401-0008.md")))
    rows = result["依据参数_中间数据"]

    relative_row = next(
        row for row in rows if row["测量值"] == "2.1 相对频率偏差(Relative Frequency Deviation)"
    )

    assert relative_row["数据明细"]["相对频率偏差(Relative Frequency Deviation)"] == "-5.0×10^-10"
    assert relative_row["数据明细"]["Urel(k=2)"] == "5×10^-11"


def test_parse_md_to_json_keeps_period_measurement_rows_for_sample():
    result = parse_md_to_json(str(Path("local_md/2GB25024401-0008.md")))
    rows = result["依据参数_中间数据"]

    period_rows = [row for row in rows if row["测量值"] == "6 周期测量(Period Measurement)"]

    assert len(period_rows) == 2
    assert period_rows[0]["数据明细"]["闸门时间 (Gate)"] == "1 s"
    assert period_rows[0]["数据明细"]["标准值 (Reference)"] == "100.0 ms"
    assert period_rows[1]["数据明细"]["误差 (Error)"] == "-0.00016 μs"


def test_parse_md_to_json_inherits_channel_for_ab_frequency_sensitivity_sample():
    result = parse_md_to_json(str(Path("local_md/2GB25024401-0008.md")))
    rows = result["依据参数_中间数据"]

    sensitivity_rows = [
        row
        for row in rows
        if row["测量值"] == "3 频率测量范围及灵敏度(Frequency Measurement and Sensitivity)"
    ]

    assert sensitivity_rows[0]["数据明细"]["通道 (Channel)"] == "A"
    assert sensitivity_rows[1]["数据明细"]["通道 (Channel)"] == "A"
    assert sensitivity_rows[9]["数据明细"]["通道 (Channel)"] == "B"
    assert sensitivity_rows[-1]["数据明细"]["通道 (Channel)"] == "B"
