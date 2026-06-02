#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rule table for parameter verification."""

from __future__ import annotations

from collections import OrderedDict


FREQUENCY_UNIT_PATTERN = r"(?<![A-Za-z])(?:hz|khz|mhz|ghz)\b"
TIME_UNIT_PATTERN = r"(?<![A-Za-z])(?:s/d|s/m|min|h|s|ms|us|µs|μs|ns|ps)\b"
VOLT_POWER_UNIT_PATTERN = r"(?:\b(?:v|mv|uv|dbm|db|dbc|dbc/hz|vpp|vrms|deg)\b|%|°)"
MOTION_UNIT_PATTERN = r"(?:m/s(?:2|3)?|m/s²|m/s³|m/s2|m/s3)"
LENGTH_UNIT_PATTERN = r"(?<![A-Za-z])(?:mm|cm|m)(?![A-Za-z/])"


REFERENCE_OSCILLATOR_OBJECT_TOKENS = [
    "internal timebase",
    "internal time base",
    "timebase oscillator",
    "time base oscillator",
    "internal crystal",
    "crystal",
    "晶振",
    "内时基",
    "时基振荡器",
    "内部晶振",
    "内晶振",
    "内时基振荡器",
    "internal timebase oscillator",
]


AMBIGUOUS_CRYSTAL_FREQUENCY_MEASURED_ALIASES = [
    "crystal frequency",
    "internal crystal frequency",
    "晶振频率",
    "内部晶振频率",
]


REFERENCE_OSCILLATOR_METRIC_TOKENS = [
    "relative frequency deviation",
    "frequency stability",
    "1s frequency stability",
    "1 s frequency stability",
    "daily frequency drift",
    "daily frequency fluctuation",
    "warm-up",
    "warm up",
    "warm-up characteristics",
    "warm up characteristics",
    "aging",
    "ageing",
    "diurnal frequency fluctuation",
    "reproducibility",
    "相对频率偏差",
    "开机特性",
    "频率稳定度",
    "日老化率",
    "日频率波动",
    "日频率漂移率",
    "频率复现性",
    "1s频率稳定度",
    "1 s频率稳定度",
    "1秒频率稳定度",
    "comparison uncertainty",
    "compare uncertainty",
    "比对不确定度",
]


FREQUENCY_ACCURACY_CONTEXT_TOKENS = [
    "accuracy",
    "deviation",
    "error",
    "range",
    "reference frequency",
    "time base accuracy",
    "频率准确度",
    "频率偏差",
    "频率误差",
    "频率范围",
    "时基准确度",
]


def _unique_aliases(*groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for alias in group:
            normalized = str(alias or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
    return tuple(ordered)


PERIOD_ACCURACY_ERROR_HEADER_ALIASES = _unique_aliases(
    (
        "error per day",
        "day error",
        "daily error",
        "daily deviation",
        "time error",
        "time deviation",
        "time interval error",
        "time interval deviation",
        "period error",
        "period deviation",
        "monthly difference",
        "monthly error",
        "monthly deviation",
        "日差",
        "日偏差",
        "日误差",
        "月差",
        "月偏差",
        "月误差",
        "走时误差",
        "走时偏差",
        "时间间隔误差",
        "时间间隔偏差",
        "周期误差",
    ),
)


PERIOD_ACCURACY_SECTION_ALIASES = _unique_aliases(
    (
        "time accuracy",
        "period accuracy",
        "time measurement accuracy",
        "delta time measurement accuracy",
        "pulse period",
        "pulse width",
        "single pulse width",
        "continuous pulse width",
        "rising edge delay time",
        "falling edge delay time",
        "time interval between two single pulses",
        "pulse repetition period",
        "duty cycle",
        "计时准确度",
        "周期准确度",
        "周期测量误差",
        "时间测量准确度",
        "△t时间测量准确度",
        "脉冲周期",
        "连续脉冲周期",
        "脉冲宽度",
        "单脉冲宽度",
        "连续脉冲宽度",
        "上升沿延迟时间",
        "下降沿延迟时间",
        "两个单脉冲间的时间间隔",
        "占空比",
    ),
    PERIOD_ACCURACY_ERROR_HEADER_ALIASES,
)


PERIOD_ACCURACY_PARSER_SECTION_ALIASES = _unique_aliases(
    (
        "time interval",
        "period measurement error",
        "period measurement deviation",
        "time measurement accuracy",
        "delta time measurement accuracy",
        "pulse period",
        "pulse width",
        "single pulse width",
        "continuous pulse width",
        "rising edge delay time",
        "falling edge delay time",
        "duty cycle",
        "时间间隔",
        "周期",
        "时间测量准确度",
        "△t时间测量准确度",
        "脉冲周期",
        "连续脉冲周期",
        "脉冲宽度",
        "单脉冲宽度",
        "连续脉冲宽度",
        "上升沿延迟时间",
        "下降沿延迟时间",
        "占空比",
    ),
    PERIOD_ACCURACY_ERROR_HEADER_ALIASES,
)


SEMANTIC_CATALOG = OrderedDict(
    [
        (
            "frequency_accuracy",
            {
                "task_intent": "accuracy_check",
                "primary_quantity": "frequency",
                "unit_family": "frequency",
                "condition_axis": "frequency_band",
                "allowed_units": {"frequency"},
                "required_fields": ("reference_value", "error_value"),
                "column_requirements": (
                    ("reference_value", "error_value"),
                    ("measure_value", "error_value"),
                ),
                "section_aliases": (
                    "frequency error",
                    "frequency deviation",
                    "frequency measurement error",
                    "frequency measurement deviation",
                    "frequency measurement accuracy",
                    "frequency accuracy",
                    "output frequency",
                    "oscillator frequency",
                    "play back the signal frequency",
                    "playback signal frequency",
                    "maximum input frequency offset",
                    "reference frequency",
                    "reference frequency accuracy",
                    "time base accuracy",
                    "carrier frequency deviation",
                    "频率误差",
                    "频率偏差",
                    "频率测量误差",
                    "频率测量偏差",
                    "频率准确度",
                    "输出频率",
                    "振荡器频率",
                    "回放信号频率",
                    "最大输入频差",
                    "参考频率",
                    "时基准确度",
                    "载波频率偏差",
                ),
                "parser_section_aliases": (
                    "carrier frequency",
                    "rf cw frequency",
                    "载波频率",
                ),
                "kb_measured_aliases": (
                    "frequency",
                    "频率",
                    "reference_frequency",
                    "参考频率",
                    "time_base_accuracy",
                    "时基准确度",
                    "carrier_frequency_deviation",
                    "载波频率偏差",
                ),
            },
        ),
        (
            "frequency_range",
            {
                "task_intent": "range_check",
                "primary_quantity": "frequency",
                "unit_family": "frequency",
                "condition_axis": "frequency_band",
                "allowed_units": {"frequency"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",), ("reference_value",)),
                "section_aliases": (
                    "frequency measurement",
                    "frequency measurement range",
                    "frequency measurement and sensitivity",
                    "frequency measurement range and sensitivity",
                    "frequency measurement range and input sensitivity",
                    "frequency measurement and input sensitivity",
                    "frequency measurement sensitivity",
                    "frequency range",
                    "frequency bandwidth",
                    "acquisition bandwidth",
                    "频率测量",
                    "频率测量范围",
                    "频率测量范围及灵敏度",
                    "频率测量及灵敏度",
                    "频率测量范围及输入灵敏度",
                    "频率测量及输入灵敏度",
                    "频率范围",
                    "频带宽度",
                    "带宽",
                    "捕获带宽",
                ),
                "kb_measured_aliases": ("frequency", "频率"),
            },
        ),
        (
            "reference_oscillator",
            {
                "task_intent": "reference_check",
                "primary_quantity": "relative_frequency",
                "unit_family": "frequency",
                "condition_axis": "frequency_band",
                "allowed_units": {"frequency", "unknown"},
                "required_fields": (),
                "column_requirements": (
                    ("reference_value",),
                    ("measure_value",),
                    ("error_value",),
                ),
                "section_aliases": (
                    "relative frequency deviation",
                    "short-term stability",
                    "frequency stability",
                    "1s frequency stability",
                    "1 s frequency stability",
                    "warm-up characteristics",
                    "warm up characteristics",
                    "internal crystal",
                    "internal crystal output frequency",
                    "internal crystal frequency",
                    "reference oscillator",
                    "time base",
                    "timebase",
                    "晶振",
                    "晶振频率",
                    "内晶振",
                    "内晶振输出频率",
                    "内时基",
                    "时基",
                    "开机特性",
                    "频率稳定度",
                    "短期频率稳定度",
                    "1s频率稳定度",
                    "1 s频率稳定度",
                    "日老化率",
                    "日频率波动",
                    "日频率漂移率",
                    "diurnal frequency fluctuation",
                    "daily frequency drift",
                    "daily frequency fluctuation",
                    "频率复现性",
                    "comparison uncertainty",
                    "compare uncertainty",
                    "比对不确定度",
                ),
                "parser_section_aliases": (
                    "comparison uncertainty",
                    "compare uncertainty",
                    "比对不确定度",
                ),
                "kb_measured_aliases": (
                    "crystal",
                    "crystal frequency",
                    "internal crystal output frequency",
                    "internal crystal frequency",
                    "晶振",
                    "晶振频率",
                    "内晶振输出频率",
                    "内部晶振频率",
                ),
            },
        ),
        (
            "period_accuracy",
            {
                "task_intent": "accuracy_check",
                "primary_quantity": "period",
                "unit_family": "time",
                "condition_axis": "period_band",
                "allowed_units": {"time"},
                "required_fields": ("error_value",),
                "column_requirements": (
                    ("reference_value", "error_value"),
                    ("measure_value", "error_value"),
                    ("error_value", "limit_value"),
                ),
                "section_aliases": PERIOD_ACCURACY_SECTION_ALIASES,
                "parser_section_aliases": PERIOD_ACCURACY_PARSER_SECTION_ALIASES,
                "kb_measured_aliases": ("period", "周期"),
            },
        ),
        (
            "period_range",
            {
                "task_intent": "range_check",
                "primary_quantity": "period",
                "unit_family": "time",
                "condition_axis": "period_band",
                "allowed_units": {"time"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",), ("reference_value",)),
                "section_aliases": (
                    "period measurement",
                    "period measurement range",
                    "period range",
                    "time",
                    "time interval",
                    "周期测量",
                    "周期测量范围",
                    "周期测量范围及灵敏度",
                    "周期测量范围及输入灵敏度",
                    "周期测量及灵敏度",
                    "周期测量及输入灵敏度",
                    "周期范围",
                    "时间",
                    "时间间隔",
                ),
                "kb_measured_aliases": ("period", "周期", "time", "时间"),
            },
        ),
        (
            "count_accuracy",
            {
                "task_intent": "accuracy_check",
                "primary_quantity": "count",
                "unit_family": "count",
                "condition_axis": "count_axis",
                "allowed_units": {"count", "unknown"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",), ("reference_value",)),
                "section_aliases": (
                    "count accuracy",
                    "count",
                    "number of receiving channels",
                    "receiving channels",
                    "channel count",
                    "计数准确度",
                    "计数准确",
                    "计数精度",
                    "脉冲计数",
                    "接收通道数",
                    "通道数",
                ),
            },
        ),
        (
            "vswr_accuracy",
            {
                "task_intent": "accuracy_check",
                "primary_quantity": "vswr",
                "unit_family": "unknown",
                "condition_axis": "frequency_band",
                "allowed_units": {"unknown", "voltage_power"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",),),
                "section_aliases": (
                    "input voltage standing wave ratio",
                    "standing wave ratio",
                    "vswr",
                    "输入端电压驻波比",
                    "驻波比",
                ),
                "kb_measured_aliases": (
                    "input_voltage_standing_wave_ratio",
                    "standing_wave_ratio",
                    "vswr",
                    "输入端电压驻波比",
                    "驻波比",
                ),
            },
        ),
        (
            "impedance_accuracy",
            {
                "task_intent": "accuracy_check",
                "primary_quantity": "impedance",
                "unit_family": "unknown",
                "condition_axis": None,
                "allowed_units": {"unknown"},
                "required_fields": ("error_value",),
                "column_requirements": (("reference_value", "error_value"), ("measure_value", "limit_value")),
                "section_aliases": (
                    "input impedance",
                    "impedance",
                    "输入阻抗",
                    "阻抗",
                ),
                "kb_measured_aliases": (
                    "input_impedance",
                    "impedance",
                    "输入阻抗",
                    "阻抗",
                ),
            },
        ),
        (
            "input_sensitivity",
            {
                "task_intent": "sensitivity_check",
                "primary_quantity": "input_sensitivity",
                "unit_family": "voltage_power",
                "condition_axis": None,
                "allowed_units": {"voltage_power"},
                "required_fields": (),
                "column_requirements": (("error_value",), ("measure_value",)),
                "section_aliases": (
                    "input sensitivity",
                    "trigger sensitivity",
                    "sensitivity",
                    "frequency measurement and sensitivity",
                    "frequency measurement range and sensitivity",
                    "frequency measurement range and input sensitivity",
                    "frequency measurement and input sensitivity",
                    "frequency measurement sensitivity",
                    "输入灵敏度",
                    "灵敏度",
                    "触发灵敏度",
                    "频率测量范围及灵敏度",
                    "频率测量及灵敏度",
                    "频率测量范围及输入灵敏度",
                    "频率测量及输入灵敏度",
                    "周期测量范围及灵敏度",
                    "周期测量及输入灵敏度",
                ),
            },
        ),
        (
            "cnr_consistency",
            {
                "task_intent": "quality_check",
                "primary_quantity": "cnr_consistency",
                "unit_family": "voltage_power",
                "condition_axis": "frequency_band",
                "allowed_units": {"voltage_power", "unknown"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",), ("error_value",)),
                "section_aliases": (
                    "consistency of carrier to noise ratio",
                    "carrier to noise ratio deviation",
                    "carrier to noise ratio consistency",
                    "载噪比一致性",
                    "载噪比偏差",
                ),
                "kb_measured_aliases": (
                    "consistency_of_carrier_to_noise_ratio",
                    "carrier_to_noise_ratio_deviation",
                    "carrier_to_noise_ratio_consistency",
                    "载噪比一致性",
                    "载噪比偏差",
                ),
            },
        ),
        (
            "power_accuracy",
            {
                "task_intent": "accuracy_check",
                "primary_quantity": "power",
                "unit_family": "voltage_power",
                "condition_axis": None,
                "allowed_units": {"voltage_power"},
                "required_fields": ("error_value",),
                "column_requirements": (("error_value",), ("measure_value",)),
                "section_aliases": (
                    "power accuracy",
                    "amplitude measurement accuracy",
                    "amplitude accuracy",
                    "output amplitude",
                    "pulse output amplitude",
                    "pulse amplitude",
                    "sine wave amplitude",
                    "square wave amplitude",
                    "triangle wave amplitude",
                    "ramp wave amplitude",
                    "amplitude flatness",
                    "flatness",
                    "dc offset accuracy",
                    "dc offset",
                    "offset accuracy",
                    "gain",
                    "maximum output power",
                    "power linearity",
                    "noise factor",
                    "playback signal power level",
                    "power deviation",
                    "power resolution",
                    "power level",
                    "level accuracy",
                    "level deviation",
                    "幅度测量准确度",
                    "幅度准确度",
                    "输出幅度",
                    "脉冲输出幅度",
                    "脉冲幅度",
                    "正弦波输出幅度",
                    "方波输出幅度",
                    "三角波输出幅度",
                    "斜波输出幅度",
                    "幅度平坦度",
                    "平坦度",
                    "直流偏置准确度",
                    "直流偏置",
                    "偏置准确度",
                    "增益",
                    "最大输出功率",
                    "功率线性度",
                    "噪声系数",
                    "回放信号功率电平",
                    "功率准确度",
                    "功率偏差",
                    "功率分辨力",
                    "功率电平",
                    "电平准确度",
                    "电平偏差",
                ),
                "kb_measured_aliases": (
                    "power_range",
                    "功率范围",
                    "power_deviation",
                    "功率偏差",
                    "power_resolution",
                    "power resolution",
                    "功率分辨力",
                    "power_level",
                    "功率电平",
                    "level",
                    "电平",
                ),
            },
        ),
        (
            "position_consistency",
            {
                "task_intent": "quality_check",
                "primary_quantity": "position_consistency",
                "unit_family": "length",
                "condition_axis": "frequency_band",
                "allowed_units": {"length", "unknown"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",), ("error_value",)),
                "section_aliases": (
                    "location consistency",
                    "playback deviation",
                    "position consistency",
                    "定位一致性",
                    "回放偏差",
                ),
                "kb_measured_aliases": (
                    "location_consistency",
                    "playback_deviation",
                    "position_consistency",
                    "定位一致性",
                    "回放偏差",
                ),
            },
        ),
        (
            "phase_noise",
            {
                "task_intent": "noise_check",
                "primary_quantity": "phase_noise",
                "unit_family": "voltage_power",
                "condition_axis": "offset_frequency",
                "allowed_units": {"voltage_power", "unknown"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",),),
                "section_aliases": ("phase noise", "相位噪声"),
                "kb_measured_aliases": ("phase_noise", "相位噪声"),
            },
        ),
        (
            "modulation_quality",
            {
                "task_intent": "quality_check",
                "primary_quantity": "modulation_quality",
                "unit_family": "voltage_power",
                "condition_axis": None,
                "allowed_units": {"voltage_power", "unknown"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",),),
                "section_aliases": (
                    "evm",
                    "error vector magnitude",
                    "误差矢量幅度",
                    "phase error",
                    "iq offset",
                ),
                "parser_section_aliases": (
                    "modulation quality",
                    "signal quality",
                    "信号质量",
                    "相位误差",
                    "iq偏移",
                ),
                "kb_measured_aliases": (
                    "error_vector_magnitude",
                    "误差矢量幅度",
                    "evm",
                    "phase_error",
                    "phase error",
                    "iq_offset",
                    "iq offset",
                ),
            },
        ),
        (
            "dynamic_range",
            {
                "task_intent": "range_check",
                "primary_quantity": "dynamic_range",
                "unit_family": "motion",
                "condition_axis": None,
                "allowed_units": {"motion", "voltage_power", "length"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",),),
                "section_aliases": (
                    "dynamic range",
                    "range of input power for signal acquisition",
                    "input power range",
                    "动态范围",
                    "采集信号输入功率范围",
                    "pseudorange resolution",
                    "伪距分辨力",
                    "speed",
                    "velocity",
                    "accelerated speed",
                    "acceleration",
                    "stacking velocity",
                    "jerk",
                    "速度",
                    "加速度",
                    "加加速度",
                ),
                "kb_measured_aliases": (
                    "power_dynamic_range",
                    "功率动态范围",
                    "pseudorange_resolution",
                    "伪距分辨力",
                    "速度动态范围",
                    "加速度动态范围",
                    "加加速度动态范围",
                    "speed_dynamic_range",
                    "acceleration_dynamic_range",
                    "jerk_dynamic_range",
                ),
            },
        ),
        (
            "spectral_purity",
            {
                "task_intent": "quality_check",
                "primary_quantity": "spectral_purity",
                "unit_family": "voltage_power",
                "condition_axis": None,
                "allowed_units": {"voltage_power", "unknown"},
                "required_fields": ("measure_value",),
                "column_requirements": (("measure_value",),),
                "section_aliases": (
                    "spectral purity",
                    "out of band rejection",
                    "in band spurious",
                    "信号纯度",
                    "harmonic suppression",
                    "spur suppression",
                    "spurious suppression",
                    "带外抑制",
                    "带内杂散",
                    "谐波抑制",
                    "非谐波抑制",
                    "杂波抑制",
                ),
                "parser_section_aliases": ("signal purity",),
                "kb_measured_aliases": (
                    "谐波抑制",
                    "非谐波抑制",
                    "杂波抑制",
                    "harmonic_suppression",
                    "spur_suppression",
                    "non_harmonic_suppression",
                    "spurious_suppression",
                ),
            },
        ),
    ]
)


def _catalog_section_aliases(semantic_target: str, *, for_parser: bool = False) -> tuple[str, ...]:
    spec = SEMANTIC_CATALOG[semantic_target]
    aliases = tuple(spec.get("section_aliases", ()))
    parser_aliases = tuple(spec.get("parser_section_aliases", ()))
    if for_parser:
        return _unique_aliases(aliases, parser_aliases)
    return _unique_aliases(aliases)


def _catalog_param_aliases(semantic_target: str) -> tuple[str, ...]:
    spec = SEMANTIC_CATALOG[semantic_target]
    return _unique_aliases(spec.get("section_aliases", ()), spec.get("parser_section_aliases", ()))


_SECTION_TITLE_ALIASES_DATA = OrderedDict(
    (semantic_target, _catalog_section_aliases(semantic_target, for_parser=True))
    for semantic_target in SEMANTIC_CATALOG.keys()
)
if isinstance(globals().get("SECTION_TITLE_ALIASES"), OrderedDict):
    SECTION_TITLE_ALIASES = globals()["SECTION_TITLE_ALIASES"]
    SECTION_TITLE_ALIASES.clear()
    SECTION_TITLE_ALIASES.update(_SECTION_TITLE_ALIASES_DATA)
else:
    SECTION_TITLE_ALIASES = _SECTION_TITLE_ALIASES_DATA


PARAMETER_NAME_RULES = {
    "frequency_measurement_sensitivity": [
        "frequency measurement and sensitivity",
        "frequency measurement range and sensitivity",
        "frequency measurement range and input sensitivity",
        "frequency measurement and input sensitivity",
        "frequency measurement range & sensitivity",
        "frequency measurement range及灵敏度",
        "frequency measurement及灵敏度",
        "频率测量范围及灵敏度",
        "频率测量及灵敏度",
        "频率测量范围及输入灵敏度",
        "频率测量及输入灵敏度",
    ],
    "period_measurement_sensitivity": [
        "period measurement and sensitivity",
        "period measurement range and sensitivity",
        "period measurement range and input sensitivity",
        "period measurement and input sensitivity",
        "period measurement range & sensitivity",
        "period measurement range及灵敏度",
        "period measurement及灵敏度",
        "周期测量范围及灵敏度",
        "周期测量及灵敏度",
        "周期测量范围及输入灵敏度",
        "周期测量及输入灵敏度",
    ],
    "frequency_measurement_range": [
        "frequency measurement",
        "frequency measurement range",
        "frequency range",
        "频率测量",
        "频率测量范围",
        "频率范围",
    ],
    "period_measurement_range": [
        "period measurement",
        "period measurement range",
        "period range",
        "周期测量",
        "周期测量范围",
        "周期范围",
    ],
    "reference_oscillator": list(_catalog_param_aliases("reference_oscillator")),
    "vswr_accuracy": list(_catalog_param_aliases("vswr_accuracy")),
    "impedance_accuracy": list(_catalog_param_aliases("impedance_accuracy")),
    "phase_noise": list(_catalog_param_aliases("phase_noise")),
    "evm": list(_catalog_param_aliases("modulation_quality")),
    "cnr_consistency": list(_catalog_param_aliases("cnr_consistency")),
    "position_consistency": list(_catalog_param_aliases("position_consistency")),
    "dynamic_range": list(_catalog_param_aliases("dynamic_range")),
    "spectral_purity": list(_catalog_param_aliases("spectral_purity")),
    "power_accuracy": list(_catalog_param_aliases("power_accuracy")),
    "frequency_accuracy": list(_catalog_param_aliases("frequency_accuracy")),
}


KB_MEASURED_RULES = {
    "reference_oscillator": list(SEMANTIC_CATALOG["reference_oscillator"]["kb_measured_aliases"]),
    "vswr_accuracy": list(SEMANTIC_CATALOG["vswr_accuracy"]["kb_measured_aliases"]),
    "impedance_accuracy": list(SEMANTIC_CATALOG["impedance_accuracy"]["kb_measured_aliases"]),
    "frequency_range": list(SEMANTIC_CATALOG["frequency_range"]["kb_measured_aliases"]),
    "frequency_accuracy": list(SEMANTIC_CATALOG["frequency_accuracy"]["kb_measured_aliases"]),
    "period_range": list(SEMANTIC_CATALOG["period_range"]["kb_measured_aliases"]),
    "period_accuracy": list(SEMANTIC_CATALOG["period_accuracy"]["kb_measured_aliases"]),
    "input_sensitivity_frequency": [
        "frequency_measurement_range_and_input_sensitivity",
        "频率测量范围及输入灵敏度",
        "频率测量范围及灵敏度",
    ],
    "input_sensitivity_period": [
        "period_measurement_range_and_input_sensitivity",
        "周期测量范围及输入灵敏度",
        "周期测量范围及灵敏度",
    ],
    "phase_noise": list(SEMANTIC_CATALOG["phase_noise"]["kb_measured_aliases"]),
    "modulation_quality": list(SEMANTIC_CATALOG["modulation_quality"]["kb_measured_aliases"]),
    "cnr_consistency": list(SEMANTIC_CATALOG["cnr_consistency"]["kb_measured_aliases"]),
    "position_consistency": list(SEMANTIC_CATALOG["position_consistency"]["kb_measured_aliases"]),
    "dynamic_range": list(SEMANTIC_CATALOG["dynamic_range"]["kb_measured_aliases"]),
    "spectral_purity": list(SEMANTIC_CATALOG["spectral_purity"]["kb_measured_aliases"]),
    "power_accuracy": list(SEMANTIC_CATALOG["power_accuracy"]["kb_measured_aliases"]),
}


STRUCTURED_PREFILTER_TARGETS = {
    ("reference_check", "relative_frequency"): {"reference_oscillator"},
    ("sensitivity_check", "input_sensitivity"): {"input_sensitivity"},
    ("range_check", "frequency"): {"frequency_range"},
    ("range_check", "period"): {"period_range"},
    # 频率测量误差类条目既会遇到显式“频率准确度/载波频率偏差”能力，
    # 也会遇到仅以“频率 + 频段 + Urel”表达的通用频率能力。
    # 两者都纳入候选池，再由 selector 按轴/语义细化选择，避免过早过滤掉
    # JJF2196 这类以“频率 10 Hz～18 GHz”表达能力的有效候选。
    ("accuracy_check", "frequency"): {"frequency_accuracy", "frequency_range"},
    ("accuracy_check", "count"): {"period_accuracy", "period_range"},
    # 时间类“准确度核验”会同时遇到“周期”与“时间间隔”两种 KB 写法。
    # 两者都放进候选池后，再由时间轴排序挑选更贴近点位的条目，避免像 JJG238
    # 这种含双段时间范围的能力被过早过滤掉。
    ("accuracy_check", "period"): {"period_accuracy", "period_range"},
    ("accuracy_check", "power"): {"power_accuracy"},
    ("accuracy_check", "vswr"): {"vswr_accuracy"},
    ("accuracy_check", "impedance"): {"impedance_accuracy"},
    ("noise_check", "phase_noise"): {"phase_noise"},
    ("quality_check", "cnr_consistency"): {"cnr_consistency"},
    ("quality_check", "position_consistency"): {"position_consistency"},
    ("quality_check", "modulation_quality"): {"modulation_quality"},
    ("quality_check", "spectral_purity"): {"spectral_purity"},
    ("range_check", "dynamic_range"): {"dynamic_range"},
}


PLACEHOLDER_INSTRUMENT_NAMES = {
    "description",
    "model",
    "modeltype",
    "manufacturer",
    "serial",
    "asset",
    "instrument",
    "instrumentname",
    "name",
    "n/a",
    "na",
    "none",
    "unknown",
}


FALLBACK_SCORE_RULES = {
    "frequency_measurement": {
        "period_penalty": -3.5,
        "frequency_bonus": 1.5,
    },
    "period_measurement": {
        "frequency_penalty": -3.5,
        "period_bonus": 1.5,
    },
    "frequency_measurement_range": {
        "sensitivity_penalty": -2.5,
        "frequency_bonus": 1.0,
    },
    "period_measurement_range": {
        "sensitivity_penalty": -2.5,
        "period_bonus": 1.0,
    },
    "sensitivity": {
        "sensitivity_bonus": 2.5,
        "non_sensitivity_penalty": -1.5,
    },
}


SEMANTIC_RULE_REGISTRY = OrderedDict(
    (
        semantic_target,
        {
            "task_intent": spec["task_intent"],
            "primary_quantity": spec["primary_quantity"],
            "unit_family": spec["unit_family"],
            "condition_axis": spec["condition_axis"],
            "allowed_units": set(spec["allowed_units"]),
            "required_fields": tuple(spec.get("required_fields", ())),
            "section_aliases": _catalog_section_aliases(semantic_target),
            "column_requirements": tuple(spec.get("column_requirements", ())),
        },
    )
    for semantic_target, spec in SEMANTIC_CATALOG.items()
)

SEMANTIC_TARGET_WHITELIST = tuple(SEMANTIC_RULE_REGISTRY.keys())
