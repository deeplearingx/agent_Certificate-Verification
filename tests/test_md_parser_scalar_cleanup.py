from pathlib import Path

from md_parser_no_llm import parse_md_to_json


def test_parse_md_to_json_cleans_scalar_warmup_and_uncertainty_fields():
    result = parse_md_to_json(str(Path("local_md/2GB25001291-0036.md")))
    rows = result["依据参数_中间数据"]

    warmup_row = next(row for row in rows if row["测量值"] == "2 开机特性(Warm-up Characteristics)")

    assert warmup_row["数据明细"]["开机特性"] == "1.0×10^-8"
    assert warmup_row["数据明细"]["U"] == "3.0×10^-12"
    assert warmup_row["__parser_meta"]["section_rule"] == "reference_oscillator"
    assert warmup_row["__parser_meta"]["unit_inherited"] is True
    assert warmup_row["__normalized_fields"]["error_value"] == "1.0×10^-8"


def test_parse_md_to_json_keeps_stability_scalar_values_clean():
    result = parse_md_to_json(str(Path("local_md/2GB25001291-0036.md")))
    rows = result["依据参数_中间数据"]

    stability_rows = [
        row
        for row in rows
        if row["测量值"] == "3 短期频率稳定度(Short-Term Stability)(at 10MHz)"
    ]

    assert stability_rows[0]["数据明细"]["短期频率稳定度 (Stability)"] == "6.0×10^-11"
    assert stability_rows[0]["数据明细"]["U (k=2)"] == "2.4×10^-12"
    assert stability_rows[0]["__parser_meta"]["section_rule"] == "reference_oscillator"
    assert stability_rows[0]["__normalized_fields"]["point_value"] == "1 s"
    assert stability_rows[0]["__normalized_fields"]["error_value"] == "6.0×10^-11"


def test_parse_md_to_json_removes_trailing_empty_parentheses_from_headers():
    result = parse_md_to_json(str(Path("local_md/2GB25001291-0036.md")))
    rows = result["依据参数_中间数据"]

    relative_row = next(row for row in rows if row["测量值"] == "4 相对频率偏差(Relative Frequency Deviation)")

    assert "相对频率偏差 (Relative Frequency Deviation)" in relative_row["数据明细"]
    assert "U (k=2)" in relative_row["数据明细"]
    assert relative_row["__parser_meta"]["section_rule"] == "reference_oscillator"


def test_parse_md_to_json_strips_pass_flag_prefix_from_uncertainty_cells():
    result = parse_md_to_json(str(Path("local_md/2GB25026824-0010.md")))
    rows = result["依据参数_中间数据"]

    relative_row = next(row for row in rows if row["测量值"] == "4 相对频率偏差(Relative Frequency Deviation)")

    assert relative_row["数据明细"]["U(k=2)"] == "3.0×10^-12"
    assert relative_row["__normalized_fields"]["cert_u"] == "3.0×10^-12"
