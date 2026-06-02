from pathlib import Path

from md_parser_no_llm import parse_md_to_json


def test_parse_md_to_json_recovers_flattened_rubidium_reference_sections():
    result = parse_md_to_json(str(Path("local_md/2GB25006390-0009.md")))
    rows = result["依据参数_中间数据"]
    document_meta = result["__document_parser_meta"]

    assert rows
    assert document_meta["has_nonstandard_parameter_layout"] is False
    assert document_meta["parameter_verification_policy"] == "standard_auto_check"
    assert document_meta["nonstandard_parameter_parse_sources"] == []

    warmup_rows = [row for row in rows if row["测量值"] == "2.2 开机特性"]
    stability_rows = [row for row in rows if row["测量值"] == "3 短期频率稳定度"]
    relative_rows = [row for row in rows if row["测量值"] == "4 相对频率偏差(Relative Frequency Deviation)"]

    assert len(warmup_rows) == 2
    assert warmup_rows[0]["数据明细"]["点位"] == "2 h"
    assert warmup_rows[0]["数据明细"]["标称值 (Nominal) (MHz)"] == "10 MHz"
    assert warmup_rows[0]["数据明细"]["开机特性"] == "5.0×10^-11"

    assert len(stability_rows) == 2
    assert stability_rows[0]["数据明细"]["取样时间 (Gate Time)"] == "1 s"
    assert stability_rows[0]["数据明细"]["短期频率稳定度 (Stability)"] == "1.9×10^-11"
    assert stability_rows[1]["数据明细"]["允许范围 (Limit)"] == "≤1.0×10^-11"

    assert len(relative_rows) == 1
    assert relative_rows[0]["数据明细"]["输出频率 (Frequency) (MHz)"] == "10 MHz"
    assert relative_rows[0]["数据明细"]["相对频率偏差 (Relative Frequency Deviation)"] == "5.0×10^-11"
    assert relative_rows[0]["数据明细"]["U (k=2)"] == "3.0×10^-12"


def test_parse_md_to_json_marks_standard_html_table_layout_as_auto_check():
    result = parse_md_to_json(str(Path("local_md/2GB25026824-0010.md")))
    document_meta = result["__document_parser_meta"]

    assert document_meta["has_nonstandard_parameter_layout"] is False
    assert document_meta["parameter_verification_policy"] == "standard_auto_check"
    assert document_meta["nonstandard_parameter_parse_sources"] == []
