#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows runtime cache relocation helpers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_WINDOWS_AI_CACHE_ROOT = Path(r"D:\ai_cache")

_WINDOWS_CACHE_SUBDIRS = {
    "HF_HOME": "hf",
    "HF_HUB_CACHE": "hf\\hub",
    "HUGGINGFACE_HUB_CACHE": "hf\\hub",
    "TRANSFORMERS_CACHE": "hf\\transformers",
    "MODELSCOPE_CACHE": "modelscope",
    "MODELSCOPE_HOME": "modelscope",
    "TORCH_HOME": "torch",
    "PIP_CACHE_DIR": "pip",
    "CONDA_PKGS_DIRS": "conda_pkgs",
    "TMP": "temp",
    "TEMP": "temp",
    "TMPDIR": "temp",
    "TEMPDIR": "temp",
    "DOC_VERIFICATION_MINERU_TMP_DIR": "mineru_output",
}


def _is_windows_platform() -> bool:
    return sys.platform.startswith("win")


def resolve_windows_ai_cache_root() -> Path | None:
    if not _is_windows_platform():
        return None
    configured = str(os.getenv("AI_CACHE_ROOT", "") or "").strip()
    return Path(configured) if configured else DEFAULT_WINDOWS_AI_CACHE_ROOT


def apply_default_windows_ai_cache_env() -> Path | None:
    root = resolve_windows_ai_cache_root()
    if root is None:
        return None

    root.mkdir(parents=True, exist_ok=True)
    for relative in set(_WINDOWS_CACHE_SUBDIRS.values()):
        (root / relative).mkdir(parents=True, exist_ok=True)

    for env_name, relative in _WINDOWS_CACHE_SUBDIRS.items():
        os.environ.setdefault(env_name, str(root / relative))

    return root


def get_mineru_tmp_dir() -> Path | None:
    configured = str(os.getenv("DOC_VERIFICATION_MINERU_TMP_DIR", "") or "").strip()
    if configured:
        return Path(configured)
    root = resolve_windows_ai_cache_root()
    if root is None:
        return None
    return root / "mineru_output"
