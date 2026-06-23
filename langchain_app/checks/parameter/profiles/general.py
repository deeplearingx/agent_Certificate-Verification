#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic profiles used when no special instrument profile matches."""

from __future__ import annotations

from .base import InstrumentProfile


GENERIC_PROFILES = (
    InstrumentProfile(
        profile_id="generic.default",
        display_name="通用参数核验",
        family="generic",
        semantic_targets=(
            "frequency_accuracy",
            "frequency_range",
            "reference_oscillator",
            "period_accuracy",
            "period_range",
            "count_accuracy",
            "input_sensitivity",
            "power_accuracy",
            "phase_noise",
            "modulation_quality",
            "dynamic_range",
            "spectral_purity",
            "cnr_consistency",
            "position_consistency",
            "vswr_accuracy",
            "impedance_accuracy",
        ),
        special_policies={
            "fallback": "仅启用通用 semantic target 与 validator，不做仪器专属字段修正。",
        },
        priority=1000,
    ),
)

