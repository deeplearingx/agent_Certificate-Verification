#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compatibility exports for the canonical LangChain pipeline.

The real implementation lives in ``langchain_app.core.pipeline``. This module is
retained so legacy imports keep working without carrying a second execution
pipeline.
"""

from langchain_app.core.pipeline import (
    PipelineHooks,
    json_cache_needs_refresh,
    load_shared_embedder,
    pdf_to_md_first_step,
    run_verification,
)

__all__ = [
    "PipelineHooks",
    "run_verification",
    "load_shared_embedder",
    "pdf_to_md_first_step",
    "json_cache_needs_refresh",
]
