import pytest


chromadb = pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")
pytest.importorskip("llama_index")

from cycle_check import check_date_logic, parse_date


def test_parse_date_accepts_common_formats():
    assert parse_date("2024-01-02") is not None
    assert parse_date("2024/01/02") is not None
    assert parse_date("2024.01.02") is not None


def test_check_date_logic_flags_reverse_dates():
    result = check_date_logic("2024-01-03", "2024-01-02")
    assert result["pass"] is False
