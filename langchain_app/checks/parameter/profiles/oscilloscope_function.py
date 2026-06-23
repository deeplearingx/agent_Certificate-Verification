#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profiles for oscilloscope/function-generator samples in the PDF tree."""

from __future__ import annotations

from .base import InstrumentProfile


OSCILLOSCOPE_FUNCTION_PROFILES = (
    InstrumentProfile(
        profile_id="scope_function.oscilloscope",
        display_name="示波器",
        family="scope_function",
        instrument_aliases=("示波器", "oscilloscope"),
        pdf_category_aliases=("示波器",),
        semantic_targets=("frequency_accuracy", "period_accuracy", "dynamic_range"),
        special_policies={
            "gap": "幅度、垂直偏转、时基等示波器专属目标尚未在 SEMANTIC_CATALOG 中完整建模。",
        },
        verification_notes=("第一版只纳入已存在的通用 frequency/period/dynamic_range 目标。",),
        priority=60,
    ),
    InstrumentProfile(
        profile_id="scope_function.function_generator",
        display_name="函数/任意波形发生器",
        family="scope_function",
        instrument_aliases=("函数", "函数发生器", "任意波形", "function generator"),
        pdf_category_aliases=("函数",),
        semantic_targets=("frequency_accuracy", "period_accuracy", "power_accuracy"),
        special_policies={
            "gap": "幅度准确度、失真、波形参数等后续应新增专属 semantic target。",
        },
        priority=65,
    ),
)

