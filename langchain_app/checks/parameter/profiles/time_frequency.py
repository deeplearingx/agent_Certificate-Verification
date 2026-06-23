#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profiles derived from the current time/frequency certificate folders."""

from __future__ import annotations

from .base import InstrumentProfile


TIME_FREQUENCY_PROFILES = (
    InstrumentProfile(
        profile_id="time_frequency.counter",
        display_name="通用/微波频率计数器",
        family="time_frequency",
        instrument_aliases=("通用计数器", "频率计", "微波频率计数器", "counter"),
        pdf_category_aliases=("通用计数器", "频率计", "微波频率计数器"),
        semantic_targets=(
            "frequency_accuracy",
            "frequency_range",
            "period_accuracy",
            "period_range",
            "count_accuracy",
            "input_sensitivity",
            "reference_oscillator",
        ),
        special_policies={
            "input_sensitivity": "频率/周期测量范围与输入灵敏度需要同时看幅度轴和频率/时间条件轴。",
            "counter_modes": "同一证书可能混合频率、周期、时间间隔、计数功能，按行 contract 分派。",
        },
        verification_notes=(
            "优先使用通用范围/误差/不确定度判定器。",
            "遇到时基、晶振、相对频偏类参数时转入 reference_oscillator 规则。",
        ),
        priority=20,
    ),
    InstrumentProfile(
        profile_id="time_frequency.time_interval",
        display_name="时间间隔/脉冲类仪器",
        family="time_frequency",
        instrument_aliases=(
            "时间间隔测量仪",
            "时间间隔发生器",
            "脉冲计数器",
            "脉冲分配放大器",
            "时间检定仪",
        ),
        pdf_category_aliases=("时间间隔测量仪", "时间间隔发生器", "脉冲计数器", "脉冲分配放大器", "时间检定仪"),
        semantic_targets=("period_accuracy", "period_range", "count_accuracy", "input_sensitivity"),
        special_policies={
            "pulse_width": "脉冲宽度、周期、占空比等统一走 period_accuracy，但探针字段不同。",
            "output_time_interval": "输出时间间隔使用 subtype=output_time_interval，U 与范围探针取 reference_value。",
        },
        priority=25,
    ),
    InstrumentProfile(
        profile_id="time_frequency.stopwatch_timer",
        display_name="秒表/时间继电器/瞬时日差类",
        family="time_frequency",
        instrument_aliases=("秒表", "时间继电器", "计时器", "瞬时日差测量仪"),
        criterion_aliases=("JJG488", "JJG 488"),
        pdf_category_aliases=("秒表", "时间继电器计时器", "JJG 488-2018瞬时日差测量仪"),
        semantic_targets=("period_accuracy", "period_range", "reference_oscillator"),
        special_policies={
            "daily_error": "日差/月差/走时误差属于 period_accuracy，但比较模式通常是 limit_error。",
            "output_time_interval": "秒表输出时间间隔按特殊 subtype 处理，不能和普通时间间隔范围混淆。",
        },
        priority=15,
    ),
    InstrumentProfile(
        profile_id="time_frequency.frequency_standard",
        display_name="铷原子/石英晶体频率标准与振荡器",
        family="time_frequency",
        instrument_aliases=("铷原子频率标准", "石英晶体频率标准", "石英晶体振荡器", "频标比对器", "频率标准"),
        pdf_category_aliases=("铷原子频率标准", "石英晶体频率标准", "石英晶体振荡器", "频标比对器"),
        semantic_targets=("reference_oscillator", "frequency_accuracy", "frequency_range"),
        special_policies={
            "reference_oscillator": "开机特性、频率稳定度、日老化率、复现性等都应走 reference_oscillator。",
            "fixed_points": "1 MHz/2 MHz/5 MHz/10 MHz 晶振点需要避免误判为普通频率范围。",
        },
        priority=10,
    ),
    InstrumentProfile(
        profile_id="time_frequency.gnss",
        display_name="GNSS 信号模拟/转发/采集回放类",
        family="time_frequency",
        instrument_aliases=("GNSS", "全球导航卫星系统", "导航信号", "信号模拟器", "信号转发器", "采集回放仪"),
        pdf_category_aliases=("GNSS导航信号采集回放仪", "全球导航卫星系统", "信号模拟器", "信号转发器"),
        semantic_targets=(
            "frequency_accuracy",
            "power_accuracy",
            "phase_noise",
            "modulation_quality",
            "spectral_purity",
            "dynamic_range",
            "cnr_consistency",
            "position_consistency",
            "reference_oscillator",
        ),
        special_policies={
            "carrier_frequency": "载波频率偏差属于 frequency_accuracy/carrier_frequency_error。",
            "pseudorange": "伪距/位置一致性属于 length 族，不应套用时间频率误差单位。",
            "signal_quality": "EVM、相位误差、IQ 偏置等属于 modulation_quality，需要特殊字段映射。",
        },
        priority=5,
    ),
)

