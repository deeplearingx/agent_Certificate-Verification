from md_parser_no_llm import parse_table_cells, parse_table_to_rows


def test_parse_table_to_rows_attaches_units_from_unit_rows():
    table_data = [
        ["通道 (Channel)", "频率 (Frequency)", "灵敏度 (Sensitivity)"],
        ["", "(kHz)", "(mV)"],
        ["1", "100", "4"],
        ["", "(MHz)", "(mV)"],
        ["", "10", "4"],
    ]

    rows = parse_table_to_rows(table_data, "输入灵敏度检查")

    assert rows[0]["数据明细"]["频率 (Frequency)"] == "100 kHz"
    assert rows[0]["数据明细"]["灵敏度 (Sensitivity)"] == "4 mV"
    assert rows[1]["数据明细"]["通道 (Channel)"] == "1"
    assert rows[1]["数据明细"]["频率 (Frequency)"] == "10 MHz"


def test_parse_table_to_rows_keeps_non_numeric_status_without_units():
    table_data = [
        ["通道 (Channel)", "结论 (Pass/Fail)", "U (k=2)"],
        ["", "", "(Hz)"],
        ["1", "P", "0.004"],
    ]

    rows = parse_table_to_rows(table_data, "频率测量误差")

    assert rows[0]["数据明细"]["结论 (Pass/Fail)"] == "P"
    assert rows[0]["数据明细"]["U (k=2)"] == "0.004 Hz"


def test_parse_table_to_rows_does_not_attach_units_to_channel_column():
    table_data = [
        ["通道 (Channel)", "参考值 (Reference)"],
        ["(kHz)", "(kHz)"],
        ["1", "100.000000"],
    ]

    rows = parse_table_to_rows(table_data, "频率测量误差")

    assert rows[0]["数据明细"]["通道 (Channel)"] == "1"
    assert rows[0]["数据明细"]["参考值 (Reference)"] == "100.000000 kHz"


def test_parse_table_cells_expands_rowspan_and_preserves_column_alignment():
    html = """
    <table>
      <tr><td rowspan="2">1</td><td>100.000000</td><td>100.000000</td></tr>
      <tr><td>10.0000000</td><td>10.0000000</td></tr>
    </table>
    """

    table = parse_table_cells(html)

    assert table == [
        ["1", "100.000000", "100.000000"],
        ["1", "10.0000000", "10.0000000"],
    ]


def test_parse_table_to_rows_skips_unit_rows_with_rowspan_carryover():
    table_data = [
        ["通道 (Channel)", "标准值 (Reference)", "指示值 (Indicated)"],
        ["1", "100.000000", "100.000000"],
        ["1", "(MHz)", "(MHz)"],
        ["1", "10.0000000", "10.0000000"],
    ]

    rows = parse_table_to_rows(table_data, "频率测量误差")

    assert len(rows) == 2
    assert rows[1]["数据明细"]["通道 (Channel)"] == "1"
    assert rows[1]["数据明细"]["标准值 (Reference)"] == "10.0000000 MHz"


def test_parse_table_to_rows_preserves_sampling_time_from_grouped_reference_oscillator_table():
    html = """
    <table>
      <tr><td>频率(Frequency)</td><td colspan="2">取样时间τ(Sampling Time)</td><td>U(k=2)</td></tr>
      <tr><td>(MHz)</td><td>(s)</td><td>()</td><td>()</td></tr>
      <tr><td>10</td><td>1</td><td>3.5×10-13</td><td>1.0×10-13</td></tr>
    </table>
    """

    table_data = parse_table_cells(html)
    rows = parse_table_to_rows(table_data, "2 比对不确定度")

    assert rows[0]["数据明细"]["频率(Frequency) (MHz)"] == "10 MHz"
    assert rows[0]["数据明细"]["取样时间τ(Sampling Time) (s)"] == "1 s"
    assert rows[0]["数据明细"]["取样时间τ(Sampling Time)"] == "3.5×10^-13"
    assert rows[0]["__normalized_fields"]["point_value"] == "1 s"
    assert rows[0]["__normalized_fields"]["error_value"] == "3.5×10^-13"
    assert rows[0]["__parameter_contract"]["item_label"] == "1 s"
    assert rows[0]["__parameter_contract"]["error_value"] == "3.5×10^-13"


def test_parse_table_to_rows_attaches_ascii_motion_units_from_unit_rows():
    table_data = [
        ["标称值 (Nominal)", "标准值 (Reference)", "误差 (Error)", "U (k=2)"],
        ["(m/s2)", "(m/s2)", "(m/s2)", "(m/s2)"],
        ["36000", "36000.005", "-0.005", "0.30"],
    ]

    rows = parse_table_to_rows(table_data, "3.3.2 加速度(Accelerated Speed)")

    assert rows[0]["数据明细"]["标称值 (Nominal)"] == "36000 m/s2"
    assert rows[0]["数据明细"]["标准值 (Reference)"] == "36000.005 m/s2"
    assert rows[0]["数据明细"]["误差 (Error)"] == "-0.005 m/s2"
    assert rows[0]["数据明细"]["U (k=2)"] == "0.30 m/s2"
