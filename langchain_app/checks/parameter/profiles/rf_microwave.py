#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RF/microwave profiles for signal quality and power-related checks."""

from __future__ import annotations

from .base import InstrumentProfile


RF_MICROWAVE_PROFILES = (
    InstrumentProfile(
        profile_id="rf_microwave.signal_source",
        display_name="射频/微波信号源与相关仪器",
        family="rf_microwave",
        instrument_aliases=("射频", "微波", "信号源", "信号发生器", "矢量信号", "频谱", "网络分析"),
        criterion_aliases=("JJF1471", "JJF 1471"),
        semantic_targets=(
            "frequency_accuracy",
            "power_accuracy",
            "phase_noise",
            "modulation_quality",
            "spectral_purity",
            "dynamic_range",
            "vswr_accuracy",
            "impedance_accuracy",
        ),
        special_policies={
            "power_accuracy": "功率范围、功率偏差、功率分辨力要用 subtype 区分。",
            "phase_noise": "相位噪声的频率列通常是条件轴，测量值是 dBc/Hz。",
            "modulation_quality": "EVM/相位误差/IQ 偏置不能走通用频率误差判定。",
        },
        priority=30,
    ),
)

