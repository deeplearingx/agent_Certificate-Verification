import json
from pathlib import Path

import pytest

from md_parser_no_llm import parse_md_to_json


@pytest.mark.xfail(
    strict=True,
    reason="旧 golden fixture 仍按早期解析 schema 精确比对，待解析组按当前 schema 重建。",
)
def test_golden_sample_1ga25016225_0002_matches_expected_output():
    sample_md = Path("local_md/1GA25016225-0002.md")
    expected_json = Path("tests/fixtures_expected_1GA25016225_0002.json")

    actual = parse_md_to_json(str(sample_md))
    expected = json.loads(expected_json.read_text(encoding="utf-8"))

    assert actual == expected
