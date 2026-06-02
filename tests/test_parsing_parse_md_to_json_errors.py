from pathlib import Path

import pytest

import md_parser_no_llm
from langchain_app.services.parsing import parse_md_to_json


def test_parse_md_to_json_raises_on_empty_result(tmp_path, monkeypatch):
    md_path = tmp_path / "sample.md"
    md_path.write_text("# sample", encoding="utf-8")

    monkeypatch.setattr(md_parser_no_llm, "parse_md_to_json", lambda *args, **kwargs: {})

    with pytest.raises(RuntimeError, match=r"MD parser returned empty result for sample\.md"):
        parse_md_to_json(str(md_path), tmp_path)


def test_parse_md_to_json_wraps_underlying_exception(tmp_path, monkeypatch):
    md_path = tmp_path / "sample.md"
    md_path.write_text("# sample", encoding="utf-8")

    def raise_parser_boom(*args, **kwargs):
        raise ValueError("parser boom")

    monkeypatch.setattr(md_parser_no_llm, "parse_md_to_json", raise_parser_boom)

    with pytest.raises(RuntimeError, match=r"MD parser failed for sample\.md: parser boom"):
        parse_md_to_json(str(md_path), tmp_path)
