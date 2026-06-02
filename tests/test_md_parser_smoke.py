from pathlib import Path

from md_parser_no_llm import parse_md_to_json


def test_parse_md_to_json_rejects_missing_file():
    tmp_path = Path("tests/.tmp")
    tmp_path.mkdir(parents=True, exist_ok=True)
    missing = tmp_path / "missing.md"
    try:
        parse_md_to_json(str(missing), tmp_path)
    except Exception:
        assert True
    else:
        assert False, "Expected parser to fail for missing markdown input"
