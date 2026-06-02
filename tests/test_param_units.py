import pytest


pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")
pytest.importorskip("openai")

from param_check import extract_basis_code, parse_value_with_unit


def test_extract_basis_code_normalizes_year_suffix():
    assert extract_basis_code("JJG 237-2010 频率标准") == "JJG 237"


def test_parse_value_with_unit_supports_percent_without_base():
    value, kind = parse_value_with_unit("0.5%")
    assert kind is not None
    assert value is not None
