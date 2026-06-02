#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compatibility exports for the canonical LangChain app configuration.

The real implementation lives in ``langchain_app.utils.config``. This module is
retained so legacy imports keep working without carrying a second config
implementation.
"""

from langchain_app.utils.config import (
    ROOT_DIR,
    AppConfig,
    coerce_app_config,
    get_app_config,
)

__all__ = [
    "ROOT_DIR",
    "AppConfig",
    "coerce_app_config",
    "get_app_config",
]
