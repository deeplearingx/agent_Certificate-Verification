#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lazy exports for the LangChain core package.
"""

__all__ = [
    "LLMClient",
    "LLMInvocationError",
    "create_llm_client",
    "VectorDatabase",
    "load_vector_db",
    "VerificationReport",
    "build_verification_report_header",
    "PipelineHooks",
    "run_verification",
    "load_shared_embedder",
    "pdf_to_md_first_step",
    "json_cache_needs_refresh",
]


def __getattr__(name):
    if name in {"LLMClient", "LLMInvocationError", "create_llm_client"}:
        from .llm_client import LLMClient, LLMInvocationError, create_llm_client

        if name == "LLMClient":
            return LLMClient
        if name == "LLMInvocationError":
            return LLMInvocationError
        return create_llm_client
    if name in {"VectorDatabase", "load_vector_db"}:
        from .vector_db import VectorDatabase, load_vector_db

        return VectorDatabase if name == "VectorDatabase" else load_vector_db
    if name in {"VerificationReport", "build_verification_report_header"}:
        from .report_generator import VerificationReport, build_verification_report_header

        return VerificationReport if name == "VerificationReport" else build_verification_report_header
    if name in {"PipelineHooks", "run_verification", "load_shared_embedder", "pdf_to_md_first_step", "json_cache_needs_refresh"}:
        from .pipeline import (
            PipelineHooks,
            run_verification,
            load_shared_embedder,
            pdf_to_md_first_step,
            json_cache_needs_refresh,
        )

        mapping = {
            "PipelineHooks": PipelineHooks,
            "run_verification": run_verification,
            "load_shared_embedder": load_shared_embedder,
            "pdf_to_md_first_step": pdf_to_md_first_step,
            "json_cache_needs_refresh": json_cache_needs_refresh,
        }
        return mapping[name]
    raise AttributeError(f"module 'langchain_app.core' has no attribute '{name}'")
