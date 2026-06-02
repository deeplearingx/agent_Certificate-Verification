#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared SentenceTransformer loading helpers.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

from langchain_app.utils.runtime_cache import apply_default_windows_ai_cache_env

logger = logging.getLogger(__name__)

_CUDA_OOM_MARKERS = (
    "cuda out of memory",
    "cublas_status_alloc_failed",
    "cuda error: out of memory",
)


def configure_torch_cuda_allocator() -> None:
    if sys.platform.startswith("win"):
        return
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


def resolve_sentence_transformer_device() -> Optional[str]:
    for env_name in ("LANGCHAIN_APP_EMBED_DEVICE", "SENTENCE_TRANSFORMERS_DEVICE"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value
    return "cpu"


def is_cuda_oom_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _CUDA_OOM_MARKERS)


def load_sentence_transformer(model_ref: str, *, offline: bool = False) -> Any:
    from sentence_transformers import SentenceTransformer

    apply_default_windows_ai_cache_env()

    if offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    configure_torch_cuda_allocator()

    preferred_device = resolve_sentence_transformer_device()
    init_kwargs = {"device": preferred_device} if preferred_device else {}

    try:
        return SentenceTransformer(model_ref, **init_kwargs)
    except Exception as exc:
        if not is_cuda_oom_error(exc):
            raise
        if preferred_device == "cpu":
            raise
        logger.warning(
            "SentenceTransformer load hit CUDA OOM for %s; retrying on CPU",
            model_ref,
        )
        return SentenceTransformer(model_ref, device="cpu")
