from pathlib import Path

from md_parser_no_llm import parse_md_to_json, parse_table_to_rows


def test_parse_table_to_rows_adds_measured_alias_from_parameter_field():
    table_data = [
        ["参数 (Parameter)", "标准值 (Reference)", "U (k=2)"],
        ["EVM", "2.26 %", "0.80 %"],
    ]

    rows = parse_table_to_rows(table_data, "信号质量")

    assert rows[0]["数据明细"]["参数 (Parameter)"] == "EVM"
    assert rows[0]["数据明细"]["被测量"] == "EVM"


def test_parse_table_to_rows_does_not_treat_signal_quality_frequency_as_measure_value():
    table_data = [
        ["频率 (Frequency)", "参数 (Parameter)", "标准值 (Reference)", "U (k=2)"],
        ["2491.75 MHz", "EVM", "4.22 %", "0.80 %"],
    ]

    rows = parse_table_to_rows(table_data, "7 信号质量(Signal Quality)")

    assert rows[0]["__parser_meta"]["section_rule"] == "modulation_quality"
    assert rows[0]["__normalized_fields"]["measure_value"] == "4.22 %"
    assert rows[0]["__parameter_contract"]["row_shape"] == "condition_measure_u"
    assert rows[0]["__parameter_contract"]["semantic_subtype"] == "evm"
    assert rows[0]["__parameter_contract"]["condition_axis"] == "carrier_frequency"
    assert rows[0]["__parameter_contract"]["condition_value"] == "2491.75 MHz"
    assert "frequency" not in rows[0]["__normalized_fields"]
    assert rows[0]["数据明细"]["参数 (Parameter)"] == "EVM"


def test_parse_table_to_rows_phase_noise_uses_reference_as_measure_when_frequency_is_condition():
    table_data = [
        ["频率(Frequency)", "偏置(Offset)", "标准值(Reference)", "U(k=2)"],
        ["2491.75 MHz", "0.1 kHz", "-81.2 dBc/Hz", "2.0 dB"],
    ]

    rows = parse_table_to_rows(table_data, "6 相位噪声(Phase Noise)")

    assert rows[0]["__parser_meta"]["section_rule"] == "phase_noise"
    assert rows[0]["__normalized_fields"]["measure_value"] == "-81.2 dBc/Hz"
    assert rows[0]["__normalized_fields"]["reference_value"] == "-81.2 dBc/Hz"


def test_parse_table_to_rows_spectral_purity_uses_reference_as_measure_when_frequency_is_condition():
    table_data = [
        ["频率 (Frequency) (MHz)", "项目 (Item)", "标准值 (Reference) (dB)", "U(k=2)"],
        ["2491.75 MHz", "二次谐波", "-44.2 dB", "1.6 dB"],
    ]

    rows = parse_table_to_rows(table_data, "8 信号纯度(Spectral Purity)")

    assert rows[0]["__parser_meta"]["section_rule"] == "spectral_purity"
    assert rows[0]["__normalized_fields"]["measure_value"] == "-44.2 dB"
    assert rows[0]["__normalized_fields"]["reference_value"] == "-44.2 dB"


def test_parse_table_to_rows_adds_measured_alias_from_item_field():
    table_data = [
        ["项目 (Item)", "标准值 (Reference)", "U (k=2)"],
        ["二次谐波", "-51.8 dB", "1.6 dB"],
    ]

    rows = parse_table_to_rows(table_data, "信号纯度")

    assert rows[0]["数据明细"]["项目 (Item)"] == "二次谐波"
    assert rows[0]["数据明细"]["被测量"] == "二次谐波"


def test_error_control_with_item_rewrites_row_title_using_item_name():
    table_data = [
        ["项目 (Item)", "标称值 (Nominal)", "标准值 (Reference)", "误差 (Error)", "U (k=2)"],
        ["伪距分辨力", "10 m", "9.92 m", "0.08 m", "0.06 m"],
    ]

    rows = parse_table_to_rows(table_data, "6 误差控制(Error Control)")

    assert "伪距分辨力" in rows[0]["项目名称"]
    assert rows[0]["__parser_meta"]["section_rule"] == "dynamic_range"
    assert rows[0]["__parameter_contract"]["row_shape"] == "item_nominal_reference_error_u"
    assert rows[0]["__parameter_contract"]["semantic_subtype"] == "pseudorange_resolution"
    assert rows[0]["__parameter_contract"]["error_value"] == "0.08 m"


def test_parse_md_to_json_adds_measured_alias_for_complex_item_parameter_sample():
    result = parse_md_to_json(str(Path("local_md/2GB25006175-0005A.md")))
    rows = result["依据参数_中间数据"]

    parameter_row = next(row for row in rows if row["测量值"] == "3.5 信号质量(Signal Quality)(@I路)")
    item_row = next(row for row in rows if row["测量值"] == "3.6 信号纯度(Spectral Purity)")

    assert "被测量" in parameter_row["数据明细"]
    assert "被测量" in item_row["数据明细"]
    assert parameter_row["__parser_meta"]["section_rule"] == "modulation_quality"
