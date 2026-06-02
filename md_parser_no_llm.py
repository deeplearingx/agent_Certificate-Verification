#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compatibility facade for the shared Markdown parser pipeline.

The runtime implementation lives in ``langchain_app.services.md_parser_pipeline``.
This module preserves the legacy import path used by tests and downstream code.
"""

from __future__ import annotations

from langchain_app.services import md_parser_pipeline as _pipeline

FIELD_MAPPING = _pipeline.FIELD_MAPPING
COLUMN_ALIASES = _pipeline.COLUMN_ALIASES
SECTION_TITLE_ALIASES = _pipeline.SECTION_TITLE_ALIASES

parse_md_to_json = _pipeline.parse_md_to_json
extract_meta_from_text = _pipeline.extract_meta_from_text
split_md_to_blocks = _pipeline.split_md_to_blocks
parse_table_cells = _pipeline.parse_table_cells
parse_table_to_rows = _pipeline.parse_table_to_rows
md_parser_pipeline_signature = _pipeline.md_parser_pipeline_signature

_match_column_alias = _pipeline._match_column_alias
_build_measurement_row = _pipeline._build_measurement_row
_build_parser_fallback_output_model = _pipeline._build_parser_fallback_output_model
_build_parser_fallback_slot_context = _pipeline._build_parser_fallback_slot_context
_build_parser_fallback_slot_output_model = _pipeline._build_parser_fallback_slot_output_model
_coerce_parser_fallback_slot_decision = _pipeline._coerce_parser_fallback_slot_decision


def __getattr__(name: str):
    return getattr(_pipeline, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_pipeline)))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python md_parser_no_llm.py <md_path> [out_dir]")
        raise SystemExit(1)

    md_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    parse_md_to_json(md_path, out_dir)
