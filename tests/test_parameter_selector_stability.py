import json
import unittest

from langchain_app.checks.parameter.contracts import build_parameter_contract
from langchain_app.checks.parameter.parser_core import parse_range_limit
from langchain_app.checks.parameter.parser_domain import _parse_frequency_point_list, _parse_range_to_base_units
from langchain_app.checks.parameter import selector as selector_module
from langchain_app.checks.parameter.semantic import infer_kb_capability, select_basis_with_audit
from langchain_app.checks.parameter.selector import normalize_cert_point, normalize_kb_candidate, select_kb_candidates
from langchain_app.checks.parameter.validator import verify_range_logic, verify_uncertainty_logic


KB_ENTRIES = [
    {
        "file_code": "JJG 238",
        "measured": "时间间隔",
        "measure_range_text": "10ns～1.5μs",
        "uncertainty": {"type": "Urel", "value_display": "Urel=2.3%~0.58%"},
    },
    {
        "file_code": "JJG 238",
        "measured": "时间间隔",
        "measure_range_text": "≥1.5μs～24h",
        "uncertainty": {"type": "Urel", "value_display": "Urel=0.58%"},
    },
    {
        "file_code": "JJG 238",
        "measured": "内晶振输出频率",
        "measure_range_text": "1MHz,2MHz,5MHz,10MHz",
        "uncertainty": {"type": "Urel", "value_display": "Urel=3×10⁻¹²"},
    },
    {
        "file_code": "JJF 1686",
        "measured": "周期信号脉冲计数",
        "measure_range_text": "1～1000",
        "uncertainty": {"type": "U", "value_display": "U=0"},
    },
    {
        "file_code": "JJF 1686",
        "measured": "周期信号脉冲计数",
        "measure_range_text": "1001～10000",
        "uncertainty": {"type": "U", "value_display": "U=1"},
    },
    {
        "file_code": "JJF 1686",
        "measured": "周期信号脉冲计数",
        "measure_range_text": "10001～99999",
        "uncertainty": {"type": "U", "value_display": "U=3"},
    },
    {
        "file_code": "JJF 1686",
        "measured": "非周期单脉冲计数",
        "measure_range_text": "1～10000",
        "uncertainty": {"type": "U", "value_display": "U=1"},
    },
    {
        "file_code": "JJF 1957",
        "measured": "频率",
        "measure_range_text": "开机特性：±(5×10⁻¹⁰～1×10⁻¹¹)",
        "uncertainty": {"type": "Urel", "value_display": "Urel=1.4×10⁻¹²"},
    },
    {
        "file_code": "JJF 1957",
        "measured": "频率",
        "measure_range_text": "相对频率偏差：±(2×10⁻¹⁰～1×10⁻¹¹)",
        "uncertainty": {"type": "Urel", "value_display": "Urel=1.6×10⁻¹¹"},
    },
    {
        "file_code": "JJF 1957",
        "measured": "频率",
        "measure_range_text": "频率稳定度：5×10⁻¹¹～8×10⁻¹⁴",
        "uncertainty": {"type": "Urel", "value_display": "Urel=7×10⁻¹²～2×10⁻¹⁴"},
    },
    {
        "file_code": "JJF 2090",
        "measured": "频率",
        "measure_range_text": "相对频率偏差：±(1×10⁻⁸～1×10⁻¹⁰)",
        "uncertainty": {"type": "Urel", "value_display": "Urel=1.6×10⁻¹²"},
    },
    {
        "file_code": "JJF 2090",
        "measured": "频率",
        "measure_range_text": "频率稳定度：1×10⁻⁸～5×10⁻¹⁴",
        "uncertainty": {"type": "Urel", "value_display": "Urel=6×10⁻¹²～2×10⁻¹⁴"},
    },
    {
        "file_code": "JJF 2090",
        "measured": "频率",
        "measure_range_text": "频率复现性：1×10⁻⁹～1×10⁻¹²",
        "uncertainty": {"type": "Urel", "value_display": "Urel=4×10⁻¹²"},
    },
    {
        "file_code": "JJF 2090",
        "measured": "频率",
        "measure_range_text": "日老化率：±(1×10⁻⁹～1×10⁻¹²)",
        "uncertainty": {"type": "Urel", "value_display": "Urel=6.1×10⁻¹²"},
    },
    {
        "file_code": "JJF 2197",
        "measured": "频率",
        "measure_range_text": "比对不确定度：1 MHz、5 MHz、10 MHz",
        "uncertainty": {"type": "Urel", "value_display": "Urel=1.4×10⁻¹²～2×10⁻¹⁵"},
    },
]


POWER_KB_ENTRIES = [
    {
        "file_code": "JJF 1931",
        "measured": "电平",
        "measure_range_text": "0～30)dBm(9 kHz～26.5 GHz)",
        "uncertainty": {"type": "U", "value_display": "U=(0.04～0.18)dB"},
    },
    {
        "file_code": "JJF 1931",
        "measured": "电平",
        "measure_range_text": "-130～0)dBm(9 kHz～26.5 GHz)",
        "uncertainty": {"type": "U", "value_display": "U=(0.04～0.18)dB"},
    },
    {
        "file_code": "JJF 1931",
        "measured": "电平",
        "measure_range_text": "0～20)dBm(26.5 GHz～67 GHz)",
        "uncertainty": {"type": "U", "value_display": "U=(0.17～0.44)dB"},
    },
    {
        "file_code": "JJF 1931",
        "measured": "电平",
        "measure_range_text": "-35～0)dBm(26.5 GHz～67 GHz)",
        "uncertainty": {"type": "U", "value_display": "U=(0.17～0.44)dB"},
    },
]


PHASE_NOISE_KB_ENTRIES = [
    {
        "file_code": "JJF 1471",
        "measured": "相位噪声",
        "measure_range_text": "(-60～-130)dBc/Hz",
        "uncertainty": {"type": "U", "value_display": "U=1.6dB"},
    },
]


MODULATION_QUALITY_KB_ENTRIES = [
    {
        "file_code": "JJF 1471",
        "measured": "误差矢量幅度",
        "measure_range_text": "2 %～20 %",
        "uncertainty": {"type": "U", "value_display": "0.7%"},
    },
]


POWER_RESOLUTION_KB_ENTRIES = [
    {
        "file_code": "JJF 1471",
        "measured": "功率范围",
        "measure_range_text": "(-130～-20)dBm，1000 MHz～3000 MHz",
        "uncertainty": {"type": "U", "value_display": "U=(0.12～0.2)dB"},
    },
    {
        "file_code": "JJF 1471",
        "measured": "功率分辨力",
        "measure_range_text": "(0.1～2)dB",
        "uncertainty": {"type": "U", "value_display": "U=0.02dB"},
    },
]


SPECTRAL_PURITY_KB_ENTRIES = [
    {
        "file_code": "JJF 1471",
        "measured": "谐波抑制",
        "measure_range_text": "(-60～-20)dB",
        "uncertainty": {"type": "U", "value_display": "U=1.0dB"},
    },
    {
        "file_code": "JJF 1471",
        "measured": "非谐波抑制",
        "measure_range_text": "(-80～-30)dB",
        "uncertainty": {"type": "U", "value_display": "U=1.6dB"},
    },
]


EXTRA_KB_ENTRIES = [
    {
        "file_code": "JJF EXTRA",
        "measured": "输入端电压驻波比",
        "measure_range_text": "1.0～2.0",
        "uncertainty": {"type": "U", "value_display": "U=0.05"},
    },
    {
        "file_code": "JJF EXTRA",
        "measured": "输入阻抗",
        "measure_range_text": "1 MΩ",
        "uncertainty": {"type": "U", "value_display": "U=1.2 kΩ"},
    },
    {
        "file_code": "JJF EXTRA",
        "measured": "载噪比一致性",
        "measure_range_text": "0 dB～1 dB",
        "uncertainty": {"type": "U", "value_display": "U=0.7 dB"},
    },
    {
        "file_code": "JJF EXTRA",
        "measured": "定位一致性",
        "measure_range_text": "0 m～1 m",
        "uncertainty": {"type": "U", "value_display": "U=0.5 m"},
    },
]


DYNAMIC_RANGE_KB_ENTRIES = [
    {
        "file_code": "JJF 1471",
        "measured": "功率动态范围",
        "measure_range_text": "≥60 dB",
        "uncertainty": {"type": "U", "value_display": "U=2dB"},
    },
    {
        "file_code": "JJF 1471",
        "measured": "伪距分辨力",
        "measure_range_text": "(0.01～0.1)m",
        "uncertainty": {"type": "U", "value_display": "U=0.02m"},
    },
    {
        "file_code": "JJF 1471",
        "measured": "速度动态范围",
        "measure_range_text": "（0～36000）m/s",
        "uncertainty": {"type": "U", "value_display": "U=1m/s"},
    },
    {
        "file_code": "JJF 1471",
        "measured": "加速度动态范围",
        "measure_range_text": "（0～2000）m/s2",
        "uncertainty": {"type": "U", "value_display": "U=0.3m/s2"},
    },
    {
        "file_code": "JJF 1471",
        "measured": "加加速度动态范围",
        "measure_range_text": "（0～2000）m/s3",
        "uncertainty": {"type": "U", "value_display": "U=0.6m/s3"},
    },
]


def _select(
    section: str,
    measure: str,
    *,
    basis_code: str = "时间间隔测量仪检定规程 JJG 238",
    cert_u: str = "U=0.01 s",
    extra: str = "",
    reference_value: str = "",
):
    point_text = f"测量值:{measure} {extra}".strip()
    cert_point, semantic = normalize_cert_point(
        basis_code=basis_code,
        section_label=section,
        param_name=section,
        point_text=point_text,
        cert_u=cert_u,
        measure_value=measure,
        reference_value=reference_value,
    )
    return select_kb_candidates(cert_point, semantic, KB_ENTRIES)


class ParameterSelectorStabilityTest(unittest.TestCase):
    def test_parse_range_limit_handles_unicode_prefix_range(self):
        lower, upper = parse_range_limit("≥1.5μs～24h")
        self.assertEqual(lower, 1.5e-6)
        self.assertEqual(upper, 86400.0)

    def test_parse_range_limit_propagates_shared_suffix_unit_across_interval(self):
        lower, upper = parse_range_limit("(-100～100)s/d")
        self.assertAlmostEqual(lower, -100.0 / 86400.0)
        self.assertAlmostEqual(upper, 100.0 / 86400.0)

    def test_parse_range_limit_propagates_shared_suffix_unit_for_monthly_difference(self):
        lower, upper = parse_range_limit("(-100～100)s/m")
        self.assertAlmostEqual(lower, -100.0 / (30.0 * 86400.0))
        self.assertAlmostEqual(upper, 100.0 / (30.0 * 86400.0))

    def test_selector_prefers_long_time_band_for_millisecond_and_second_points(self):
        for measure in ["0.001 s", "0.01 s", "1 s", "9.9 s", "80 s", "800 s", "1000 s", "9000 s"]:
            with self.subTest(measure=measure):
                outcome = _select("2 计时(Time)", measure)
                self.assertIsNotNone(outcome.selected_candidate)
                self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "≥1.5μs～24h")

    def test_selector_prefers_short_time_band_for_submicro_points(self):
        outcome = _select("2 计时(Time)", "100 ns", cert_u="U=0.00001 s")
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "10ns～1.5μs")

    def test_time_base_routes_to_reference_oscillator_candidate(self):
        outcome = _select(
            "3 时基(Time Base)",
            "1 Hz",
            cert_u="U=0.00000039 Hz",
            extra="内晶振 输出频率 10MHz",
            reference_value="10 MHz",
        )
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "内晶振输出频率")

    def test_reference_oscillator_metric_labels_map_to_reference_oscillator(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1984-2022",
            section_label="2.1 开机特性(Warm-up Characteristics)",
            param_name="2.1 开机特性(Warm-up Characteristics)",
            point_text="10 MHz 1×10^-11",
            cert_u="Urel=7×10^-11",
            measure_value="10 MHz",
            reference_value="10 MHz",
        )
        self.assertEqual(cert_point.semantic_target, "reference_oscillator")
        self.assertEqual(semantic.task_intent, "reference_check")
        self.assertEqual(cert_point.semantic_subtype, "warmup_characteristics")

    def test_reference_oscillator_warmup_can_select_metric_candidate_without_axis(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1957-2021",
            section_label="2 开机特性(Warm-up Characteristics)",
            param_name="2 开机特性(Warm-up Characteristics)",
            point_text="开机特性 1.0×10^-8",
            cert_u="Urel=3.0×10^-12",
            error_value="1.0×10^-8",
        )
        outcome = select_kb_candidates(cert_point, semantic, KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertIn("开机特性", outcome.selected_candidate.source["measure_range_text"])

    def test_reference_oscillator_warmup_does_not_fallback_to_aging_metric(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 2090-2023",
            section_label="2 开机特性(Warm-up Characteristics)",
            param_name="2 开机特性(Warm-up Characteristics)",
            point_text="开机特性 1.0×10^-8",
            cert_u="Urel=3.0×10^-12",
            error_value="1.0×10^-8",
        )
        outcome = select_kb_candidates(cert_point, semantic, KB_ENTRIES)
        self.assertIsNone(outcome.selected_candidate)
        self.assertEqual(outcome.rationale, "same basis but no compatible candidate")

    def test_reference_oscillator_relative_frequency_prefers_matching_metric_candidate(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1957-2021",
            section_label="4 相对频率偏差(Relative Frequency Deviation)",
            param_name="4 相对频率偏差(Relative Frequency Deviation)",
            point_text="10 MHz 1.0×10^-8",
            cert_u="Urel=1.0×10^-12",
            measure_value="10 MHz",
            error_value="1.0×10^-8",
        )
        outcome = select_kb_candidates(cert_point, semantic, KB_ENTRIES)
        self.assertEqual(cert_point.semantic_subtype, "relative_frequency_deviation")
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertIn("相对频率偏差", outcome.selected_candidate.source["measure_range_text"])

    def test_reference_oscillator_relative_frequency_accepts_generic_oscillator_candidate(self):
        kb_entries = [
            {
                "file_code": "JJG 841",
                "measured": "晶振",
                "measure_range_text": "1 MHz,2 MHz,5 MHz,10 MHz",
                "uncertainty": {"type": "Urel", "value_display": "Urel=3×10⁻¹²"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 841-2012",
            section_label="2.1 相对频率偏差(Relative Frequency Deviation)",
            param_name="2.1 相对频率偏差(Relative Frequency Deviation)",
            point_text="输出频率 10 MHz 相对频率偏差 -4.0×10^-7",
            cert_u="4×10^-8",
            measure_value="10 MHz",
            error_value="-4.0×10^-7",
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertEqual(cert_point.semantic_subtype, "relative_frequency_deviation")
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "晶振")

    def test_frequency_accuracy_title_on_fixed_mhz_point_routes_to_relative_frequency_deviation(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 2090-2023",
            section_label="5 频率准确度(Frequency Accuracy)",
            param_name="5 频率准确度(Frequency Accuracy)",
            point_text="标称值 10 MHz 误差 2×10^-9",
            cert_u="U=3.0×10^-12",
            measure_value="10 MHz",
            error_value="2×10^-9",
            point_value="10 MHz",
        )
        outcome = select_kb_candidates(cert_point, semantic, KB_ENTRIES)

        self.assertEqual(cert_point.semantic_target, "reference_oscillator")
        self.assertEqual(cert_point.semantic_subtype, "relative_frequency_deviation")
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertIn("相对频率偏差", outcome.selected_candidate.source["measure_range_text"])

    def test_frequency_measurement_error_can_select_generic_frequency_accuracy_band(self):
        kb_entries = [
            {
                "file_code": "JJF 2196",
                "measured": "晶振频率",
                "measure_range_text": "相对频率偏差：10 MHz",
                "uncertainty": {"type": "Urel", "value_display": "Urel=1.0×10⁻¹¹"},
            },
            {
                "file_code": "JJF 2196",
                "measured": "频率",
                "measure_range_text": "10 Hz～18 GHz",
                "uncertainty": {"type": "Urel", "value_display": "Urel=6.5×10⁻¹¹"},
            },
        ]
        outcome = select_basis_with_audit(
            basis_code="JJF 2196-2025",
            section_label="4 频率测量误差(Frequency Measurement Error)",
            param_name="4 频率测量误差(Frequency Measurement Error)",
            point_text="标准值 10.000017 MHz 测量值 10.000017 MHz 误差 0.017 kHz 允许误差 ±0.030 kHz",
            cert_u="0.0006 kHz",
            measure_value="10.000017 MHz",
            reference_value="10.000017 MHz",
            error_value="0.017 kHz",
            point_value="10.000017 MHz",
            kb_entries=kb_entries,
        )

        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "频率")
        self.assertEqual(outcome.audit.selected_target_relation, "exact")

    def test_period_accuracy_prefers_period_candidate_over_time_interval_fallback(self):
        kb_entries = [
            {
                "file_code": "JJF 2196",
                "measured": "周期",
                "measure_range_text": "1 ns～10 s",
                "uncertainty": {"type": "Urel", "value_display": "Urel=6.5×10⁻¹¹"},
            },
            {
                "file_code": "JJF 2196",
                "measured": "时间间隔",
                "measure_range_text": "1 ns～1 s",
                "uncertainty": {"type": "U", "value_display": "U=3ns"},
            },
        ]
        outcome = select_basis_with_audit(
            basis_code="JJF 2196-2025",
            section_label="5 周期测量误差(Period Measurement Error)",
            param_name="5 周期测量误差(Period Measurement Error)",
            point_text="标准值 10.00000 min 测量值 10.00000 min 误差 0.02 s 允许误差 ±0.10 s",
            cert_u="0.01 s",
            measure_value="10.00000 min",
            reference_value="10.00000 min",
            error_value="0.02 s",
            point_value="10.00000 min",
            kb_entries=kb_entries,
        )

        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "周期")
        self.assertEqual(outcome.selected_candidate.capability_target, "period_accuracy")
        self.assertEqual(outcome.selected[0].capability_target, "period_accuracy")
        self.assertEqual(outcome.audit.selected_target_relation, "exact")

    def test_period_accuracy_kb_u_entry_is_exact_not_cross_target_fallback(self):
        kb_entries = [
            {
                "file_code": "JJF 2196",
                "measured": "周期",
                "measure_range_text": "1 ns～10 s",
                "kb_u": "Urel=6.5×10⁻¹¹",
            },
        ]
        outcome = select_basis_with_audit(
            basis_code="JJF 2196-2025",
            section_label="5 周期测量误差(Period Measurement Error)",
            param_name="5 周期测量误差(Period Measurement Error)",
            point_text="标准值 100.0000000 ns 测量值 100.0000000 ns 误差 -0.00005 ns 允许误差 ±0.00020 ns",
            cert_u="0.00001 ns",
            measure_value="100.0000000 ns",
            reference_value="100.0000000 ns",
            error_value="-0.00005 ns",
            point_value="100.0000000 ns",
            kb_entries=kb_entries,
        )

        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "周期")
        self.assertEqual(outcome.selected_candidate.capability_target, "period_accuracy")
        self.assertEqual(outcome.audit.selected_target_relation, "exact")

    def test_reference_oscillator_short_term_stability_uses_frequency_axis_from_title(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1957-2021",
            section_label="3 短期频率稳定度(Short-Term Stability)(at 10MHz)",
            param_name="3 短期频率稳定度(Short-Term Stability)(at 10MHz)",
            point_text="1 s 6.0×10^-11",
            cert_u="Urel=2.4×10^-12",
            measure_value="10 MHz",
            point_value="1 s",
            error_value="6.0×10^-11",
        )
        outcome = select_kb_candidates(cert_point, semantic, KB_ENTRIES)
        self.assertEqual(cert_point.axis_family, "frequency_band")
        self.assertEqual(cert_point.axis_value, 10_000_000.0)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertIn("频率稳定度", outcome.selected_candidate.source["measure_range_text"])

    def test_reference_oscillator_comparison_uncertainty_selects_matching_metric_candidate(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 2197-2025",
            section_label="2 比对不确定度",
            param_name="2 比对不确定度",
            point_text="10 MHz 3.5×10^-13",
            cert_u="1.0×10^-13",
            measure_value="10 MHz",
            point_value="3.5×10^-13",
        )
        outcome = select_kb_candidates(cert_point, semantic, KB_ENTRIES)
        self.assertEqual(cert_point.semantic_target, "reference_oscillator")
        self.assertEqual(cert_point.semantic_subtype, "comparison_uncertainty")
        self.assertEqual(cert_point.axis_family, "frequency_band")
        self.assertEqual(cert_point.axis_value, 10_000_000.0)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertIn("比对不确定度", outcome.selected_candidate.source["measure_range_text"])

    def test_diurnal_frequency_fluctuation_maps_to_aging_rate_and_selects_daily_drift_candidate(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1957-2021",
            section_label="3 日频率波动(Diurnal Frequency Fluctuation)",
            param_name="3 日频率波动(Diurnal Frequency Fluctuation)",
            point_text="日频率波动 (Diurnal Frequency Fluctuation): 3.2×10^-9",
            cert_u="3.0×10^-12",
            measure_value="3.2×10^-9",
            point_value="3.2×10^-9",
        )
        kb_entries = [
            {
                "file_code": "JJF 1957",
                "measured": "频率",
                "measure_range_text": "开机特性：±(5×10⁻¹⁰～1×10⁻¹¹)",
                "uncertainty": {"type": "Urel", "value_display": "Urel=1.4×10⁻¹²"},
            },
            {
                "file_code": "JJF 1957",
                "measured": "频率",
                "measure_range_text": "日频率漂移率：±(1×10⁻¹¹～1×10⁻¹³)/d",
                "uncertainty": {"type": "Urel", "value_display": "Urel=6.1×10⁻¹²"},
            },
        ]

        self.assertEqual(cert_point.semantic_target, "reference_oscillator")
        self.assertEqual(cert_point.semantic_subtype, "aging_rate")

        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertIn("日频率漂移率", outcome.selected_candidate.source["measure_range_text"])
        self.assertEqual(outcome.selected_candidate.capability_target, "reference_oscillator")

    def test_daily_frequency_drift_kb_entry_is_reference_oscillator_aging_rate(self):
        capability = infer_kb_capability(
            {
                "file_code": "JJF 1957",
                "measured": "频率",
                "measure_range_text": "日频率漂移率：±(1×10⁻¹¹～1×10⁻¹³)/d",
                "uncertainty": {"type": "Urel", "value_display": "Urel=6.1×10⁻¹²"},
            }
        )

        self.assertEqual(capability.capability_target, "reference_oscillator")
        self.assertEqual(capability.semantic_subtype, "aging_rate")

    def test_time_measured_kb_entries_map_to_period_range(self):
        capability = infer_kb_capability(
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": "(0～10)min",
                "uncertainty": {"type": "U", "value_display": "U=0.007s"},
            }
        )
        self.assertEqual(capability.capability_target, "period_range")
        self.assertEqual(capability.primary_quantity, "period")

    def test_period_range_prefers_reference_axis_over_indicated_value(self):
        kb_entries = [
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": "(0～10)min",
                "uncertainty": {"type": "U", "value_display": "U=0.007s"},
            },
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": ">10 min～24 h",
                "uncertainty": {"type": "U", "value_display": "U=0.011s"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 2195-2025",
            section_label="2 时间间隔测量(Time Interval Measurement)",
            param_name="2 时间间隔测量(Time Interval Measurement)",
            point_text="标准值 1.000000 h 指示值 0 min 误差 0.02 s",
            cert_u="U=0.02 s",
            measure_value="0 min",
            reference_value="1.000000 h",
            error_value="0.02 s",
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertEqual(cert_point.axis_family, "period_band")
        self.assertEqual(cert_point.axis_value, 3600.0)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], ">10 min～24 h")

    def test_period_accuracy_without_axis_can_still_select_same_basis_candidate(self):
        kb_entries = [
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": "(0～10)min",
                "uncertainty": {"type": "U", "value_display": "U=0.007s"},
            },
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": ">10 min～24 h",
                "uncertainty": {"type": "U", "value_display": "U=0.011s"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 2195-2025",
            section_label="2 日差(Error Per Day)",
            param_name="2 日差(Error Per Day)",
            point_text="日差 -0.65 允许误差 ±4320.00",
            cert_u="0.03",
            error_value="-0.65",
            parameter_contract={
                "semantic_target": "period_accuracy",
                "error_value": "-0.65",
                "limit_value": "±4320.00",
                "cert_u": "0.03",
                "unit_family": "time",
                "confidence": 0.95,
            },
            parser_meta={
                "section_rule": "period_accuracy",
                "section_rule_confidence": 0.95,
                "header_rules": {
                    "error_value": "日差",
                    "limit_value": "允许误差",
                    "cert_u": "U",
                },
            },
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertTrue(cert_point.required_fields_ok)
        self.assertIsNone(cert_point.axis_value)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "(0～10)min")

    def test_period_accuracy_fallback_to_period_range_marks_cross_target_relation(self):
        kb_entries = [
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": "(0～10)min",
                "uncertainty": {"type": "U", "value_display": "U=0.007s"},
            },
            {
                "file_code": "JJF 2195",
                "measured": "时间",
                "measure_range_text": ">10 min～24 h",
                "uncertainty": {"type": "U", "value_display": "U=0.011s"},
            },
        ]
        result = select_basis_with_audit(
            basis_code="JJF 2195-2025",
            section_label="2 日差(Error Per Day)",
            param_name="2 日差(Error Per Day)",
            point_text="日差 -0.65 s/d 允许误差 ±4320.00 s/d",
            cert_u="0.03 s/d",
            measure_value="",
            reference_value="",
            error_value="-0.65 s/d",
            parameter_contract={
                "semantic_target": "period_accuracy",
                "error_value": "-0.65 s/d",
                "limit_value": "±4320.00 s/d",
                "cert_u": "0.03 s/d",
                "unit_family": "time",
                "confidence": 0.99,
            },
            parser_meta={
                "section_rule": "period_accuracy",
                "section_rule_confidence": 0.99,
                "header_rules": {
                    "error_value": "日差",
                    "limit_value": "允许误差",
                    "cert_u": "U",
                },
                "unit_inherited": True,
            },
            kb_entries=kb_entries,
        )
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.capability_target, "period_range")
        self.assertTrue(result.audit.used_fallback_candidate_target)
        self.assertEqual(result.audit.selected_target_relation, "fallback_cross_target")

    def test_parse_frequency_point_list_handles_chinese_enumeration_marks(self):
        points = _parse_frequency_point_list("比对不确定度：1 MHz、5 MHz、10 MHz")
        self.assertEqual(points, [1_000_000.0, 5_000_000.0, 10_000_000.0])

    def test_extract_time_axis_from_text_handles_minute_units(self):
        self.assertEqual(selector_module._extract_time_axis_from_text("10 min"), 600.0)
        self.assertEqual(selector_module._extract_time_axis_from_text("10.00000 min"), 600.0)

    def test_extract_time_axis_from_text_only_accepts_bare_numeric_when_period_context_is_explicit(self):
        self.assertIsNone(selector_module._extract_time_axis_from_text("10.0"))
        self.assertEqual(selector_module._extract_time_axis_from_text("10.0", allow_bare_numeric=True), 10.0)

    def test_parse_range_to_base_units_handles_reversed_nested_time_ranges(self):
        self.assertEqual(
            _parse_range_to_base_units("1 mV～1 V(<10 μs～50 ns)", "time"),
            (5.0000000000000004e-08, 9.999999999999999e-06),
        )

    def test_period_measurement_sensitivity_prefers_shorter_period_band_candidate(self):
        kb_entries = [
            {
                "file_code": "JJG 841",
                "measured": "周期测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(10 μs～10 s)",
                "uncertainty": {"type": "U", "value_display": "U=0.2dB"},
            },
            {
                "file_code": "JJG 841",
                "measured": "周期测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(<10 μs～50 ns)",
                "uncertainty": {"type": "U", "value_display": "U=0.5dB"},
            },
            {
                "file_code": "JJG 841",
                "measured": "周期测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(<50 ns～0.5 ns)",
                "uncertainty": {"type": "U", "value_display": "U=1.0dB"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 841",
            section_label="5 周期测量范围及灵敏度(Period Measurement and Sensitivity)",
            param_name="5 周期测量范围及灵敏度(Period Measurement and Sensitivity)",
            point_text="周期 0.1 μs 灵敏度 12.0 mV",
            cert_u="0.3 mV",
            measure_value="0.1 μs",
            error_value="12.0 mV",
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(
            outcome.selected_candidate.source["measure_range_text"],
            "1 mV～1 V(<10 μs～50 ns)",
        )

    def test_period_measurement_with_bare_numeric_reference_still_gets_axis_value(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 841-2012",
            section_label="5 周期测量(Period Measurement)",
            param_name="5 周期测量(Period Measurement)",
            point_text="A 10.0 9.999999780 -0.000220 ±0.0003 0.000006",
            cert_u="0.000006",
            measure_value="9.999999780",
            reference_value="10.0",
            error_value="-0.000220",
            point_value="A",
            parameter_contract={
                "semantic_target": "period_range",
                "reference_value": "10.0",
                "measure_value": "9.999999780",
                "error_value": "-0.000220",
                "limit_value": "±0.0003",
                "cert_u": "0.000006",
                "unit_family": "time",
                "confidence": 0.8,
            },
            parser_meta={
                "section_rule": "period_range",
                "section_rule_confidence": 0.8,
                "header_rules": {
                    "point_value": "通道 (Channel)",
                    "reference_value": "标准值 (Reference)",
                    "measure_value": "指示值 (Indicated)",
                    "error_value": "误差 (Error)",
                    "limit_value": "允许误差 (Limit)",
                    "cert_u": "U (k=2)",
                },
                "unit_inherited": False,
            },
        )
        self.assertEqual(semantic.semantic_target, "period_range")
        self.assertEqual(cert_point.axis_family, "period_band")
        self.assertEqual(cert_point.axis_value, 10.0)

    def test_reference_oscillator_detects_compact_frequency_units_without_spaces(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1957-2021",
            section_label="4 相对频率偏差(Relative Frequency Deviation)",
            param_name="4 相对频率偏差(Relative Frequency Deviation)",
            point_text="10MHz 1.0×10^-8",
            cert_u="Urel=1.0×10^-12",
            measure_value="10MHz",
            error_value="1.0×10^-8",
        )
        self.assertEqual(semantic.unit_family, "frequency")
        self.assertEqual(cert_point.axis_family, "frequency_band")
        self.assertEqual(cert_point.axis_value, 10_000_000.0)

    def test_frequency_measurement_sensitivity_maps_to_input_sensitivity(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 841",
            section_label="3 频率测量范围及输入灵敏度",
            param_name="3 频率测量范围及输入灵敏度",
            point_text="1mV～1V(0.1Hz～100kHz)",
            cert_u="U=0.2dB",
            measure_value="1mV～1V",
        )
        self.assertEqual(semantic.features["semantic_target"], "input_sensitivity")
        self.assertEqual(semantic.task_intent, "sensitivity_check")

    def test_input_sensitivity_parser_hint_preserves_frequency_axis_from_condition_value(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 2196-2025",
            section_label="3 输入灵敏度检查(Input Sensitivity Check)",
            param_name="3 输入灵敏度检查(Input Sensitivity Check)",
            point_text="通道 1 频率 100 kHz 灵敏度 6.5 mV",
            cert_u="N/A",
            error_value="6.5 mV",
            point_value="1",
            parameter_contract={
                "semantic_target": "input_sensitivity",
                "item_label": "1",
                "condition_axis": "频率 (Frequency)",
                "condition_value": "100 kHz",
                "error_value": "6.5 mV",
                "unit_family": "voltage_power",
                "confidence": 0.99,
            },
            parser_meta={
                "section_rule": "input_sensitivity",
                "section_rule_confidence": 0.99,
                "header_rules": {
                    "point_value": "通道 (Channel)",
                    "condition_value": "频率 (Frequency)",
                    "error_value": "灵敏度 (Sensitivity)",
                },
            },
        )
        self.assertTrue(semantic.features.get("parser_hint_accepted"))
        self.assertEqual(semantic.condition_axis, "frequency_band")
        self.assertEqual(cert_point.axis_family, "frequency_band")
        self.assertEqual(cert_point.axis_value, 100_000.0)

    def test_contract_semantic_target_overrides_parser_hint_for_cert_point(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 601-2022",
            section_label="3 秒表功能输出时间间隔(Time Interval)",
            param_name="3 秒表功能输出时间间隔(Time Interval)",
            point_text="标称值 1 s | 标准值 1.0000 s | 误差 0.0 ms | U 0.1 ms",
            cert_u="0.1 ms",
            reference_value="1.0000 s",
            error_value="0.0 ms",
            parameter_contract={
                "semantic_target": "period_accuracy",
                "reference_value": "1.0000 s",
                "error_value": "0.0 ms",
                "cert_u": "0.1 ms",
                "unit_family": "time",
                "confidence": 0.98,
            },
            parser_meta={
                "section_rule": "period_range",
                "section_hint_rule": "period_range",
                "section_rule_confidence": 0.99,
                "section_alias_matched": "time interval",
            },
        )

        self.assertEqual(cert_point.semantic_target, "period_accuracy")
        self.assertEqual(cert_point.semantic_source, "parameter_contract")
        self.assertEqual(semantic.features.get("semantic_source"), "parameter_contract")
        self.assertFalse(semantic.features.get("parser_hint_accepted"))
        self.assertEqual(semantic.features.get("parser_hint_target"), "period_range")

    def test_input_sensitivity_prefers_closest_high_frequency_band_when_point_exceeds_top_band(self):
        kb_entries = [
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(0.1 Hz～100 kHz)",
                "uncertainty": {"type": "U", "value_display": "U=0.2dB"},
            },
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(>100 kHz～20 MHz)",
                "uncertainty": {"type": "U", "value_display": "U=0.5dB"},
            },
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(>20 MHz～2 GHz)",
                "uncertainty": {"type": "U", "value_display": "U=1.0dB"},
            },
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(>2 GHz～50 GHz)",
                "uncertainty": {"type": "U", "value_display": "U=2dB"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 841-2012",
            section_label="3 触发灵敏度(Trigger Sensitivity)",
            param_name="3 触发灵敏度(Trigger Sensitivity)",
            point_text="频率 (Frequency): 60000 MHz -10 dBm",
            cert_u="2.0 dB",
            measure_value="60000 MHz",
            error_value="-10 dBm",
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(
            outcome.selected_candidate.source["measure_range_text"],
            "1 mV～1 V(>2 GHz～50 GHz)",
        )

    def test_input_sensitivity_high_frequency_point_does_not_fall_back_to_lowest_band(self):
        kb_entries = [
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(0.1 Hz～100 kHz)",
                "uncertainty": {"type": "U", "value_display": "U=0.2dB"},
            },
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(>2 GHz～50 GHz)",
                "uncertainty": {"type": "U", "value_display": "U=2dB"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 841-2012",
            section_label="3 触发灵敏度(Trigger Sensitivity)",
            param_name="3 触发灵敏度(Trigger Sensitivity)",
            point_text="频率 (Frequency): 60000 MHz -10 dBm",
            cert_u="2.0 dB",
            measure_value="60000 MHz",
            error_value="-10 dBm",
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertNotIn("0.1 Hz～100 kHz", outcome.selected_candidate.source["measure_range_text"])

    def test_frequency_measurement_error_maps_to_frequency_accuracy(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1984-2022",
            section_label="4 频率测量误差(Frequency Measurement Error)",
            param_name="4 频率测量误差(Frequency Measurement Error)",
            point_text="10 MHz 10.00000015 MHz -0.15 Hz ±0.85 Hz",
            cert_u="U=0.35 Hz",
            measure_value="10 MHz",
            reference_value="10.00000015 MHz",
            error_value="-0.15 Hz",
        )
        self.assertEqual(semantic.features["semantic_target"], "frequency_accuracy")
        self.assertEqual(semantic.task_intent, "accuracy_check")

    def test_period_measurement_error_maps_to_period_accuracy(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 238",
            section_label="5 周期测量误差(Period Measurement Error)",
            param_name="5 周期测量误差(Period Measurement Error)",
            point_text="1 ns 10 ns 0.2 ns ±0.5 ns",
            cert_u="U=0.1 ns",
            measure_value="1 ns",
            reference_value="10 ns",
            error_value="0.2 ns",
        )
        self.assertEqual(semantic.features["semantic_target"], "period_accuracy")
        self.assertEqual(semantic.task_intent, "accuracy_check")

    def test_monthly_difference_in_s_per_month_selects_daily_candidate_and_range_passes(self):
        kb_entries = [
            {
                "file_code": "JJG 488",
                "measured": "时间",
                "measure_range_text": "(-100～100)s/d",
                "uncertainty": {"type": "U", "value_display": "U=0.011s/d"},
            },
        ]
        cert_point, semantic = normalize_cert_point(
            basis_code="JJG 488-2018",
            section_label="3 瞬时月差测量范围和测量误差(Instantaneous Monthly Difference Measurement Range And Measurement Error)",
            param_name="3 瞬时月差测量范围和测量误差(Instantaneous Monthly Difference Measurement Range And Measurement Error)",
            point_text="259.2 s/m 261 s/m 2 s/m ±13 s/m",
            cert_u="1 s/m",
            measure_value="261 s/m",
            reference_value="259.2 s/m",
            error_value="2 s/m",
            parameter_contract={
                "semantic_target": "period_accuracy",
                "reference_value": "259.2 s/m",
                "measure_value": "261 s/m",
                "error_value": "2 s/m",
                "limit_value": "±13 s/m",
                "cert_u": "1 s/m",
                "unit_family": "time",
                "confidence": 0.95,
            },
            parser_meta={
                "section_rule": "period_accuracy",
                "section_rule_confidence": 0.95,
                "header_rules": {
                    "reference_value": "标准值 (Reference)",
                    "measure_value": "指示值 (Indicated)",
                    "error_value": "误差 (Error)",
                    "limit_value": "允许误差 (Limit)",
                    "cert_u": "U (k=2)",
                },
            },
        )
        outcome = select_kb_candidates(cert_point, semantic, kb_entries)
        self.assertEqual(semantic.features["semantic_target"], "period_accuracy")
        self.assertEqual(semantic.unit_family, "time")
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.capability_target, "period_accuracy")
        self.assertFalse(outcome.used_fallback_candidate_target)
        self.assertEqual(outcome.selected_target_relation, "exact")
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "(-100～100)s/d")
        payload = json.loads(
            verify_range_logic(
                "259.2 s/m",
                outcome.selected_candidate.source["measure_range_text"],
                selected_candidate=outcome.selected_candidate,
            )
        )
        self.assertEqual(payload["status"], "PASS")
        self.assertIn("8.64 s/d", payload["reason"])
        self.assertIn("[-100 s/d, 100 s/d]", payload["reason"])

    def test_time_measured_with_seconds_per_day_is_inferred_as_period_accuracy(self):
        capability = infer_kb_capability(
            {
                "file_code": "JJG 488",
                "measured": "时间",
                "measure_range_text": "(-100～100)s/d",
                "uncertainty": {"type": "U", "value_display": "U=0.011s/d"},
            }
        )
        self.assertEqual(capability.capability_target, "period_accuracy")
        self.assertEqual(capability.primary_quantity, "period")

    def test_daily_difference_range_in_seconds_per_day_keeps_both_bounds_in_same_unit(self):
        payload = json.loads(verify_range_logic("8.64 s/d", "(-100～100)s/d"))
        self.assertEqual(payload["status"], "PASS")
        self.assertIn("[-100 s/d, 100 s/d]", payload["reason"])

    def test_time_base_axis_prefers_reference_value_when_present(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="时间间隔测量仪检定规程 JJG 238",
            section_label="3 时基(Time Base)",
            param_name="3 时基(Time Base)",
            point_text="3 时基(Time Base), 1 Hz, 10 MHz",
            cert_u="U=0.00000039 Hz",
            measure_value="1 Hz",
            reference_value="10 MHz",
        )
        self.assertEqual(cert_point.axis_family, "frequency_band")
        self.assertEqual(cert_point.axis_value, 10_000_000.0)

    def test_frequency_error_section_is_recognized_as_frequency_axis(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1984-2022",
            section_label="2. 频率误差(Frequency Error)",
            param_name="2. 频率误差(Frequency Error)",
            point_text="10 MHz 10.00000015 MHz -0.15 Hz ±0.85 Hz",
            cert_u="U=0.35 Hz",
            measure_value="10 MHz",
            reference_value="10.00000015 MHz",
            error_value="-0.15 Hz",
        )
        self.assertEqual(semantic.task_intent, "accuracy_check")
        self.assertEqual(semantic.primary_quantity, "frequency")
        self.assertEqual(cert_point.axis_family, "frequency_band")
        self.assertEqual(cert_point.axis_value, 10_000_000.0)

    def test_time_axis_extractor_does_not_misread_hz_as_hours(self):
        from langchain_app.checks.parameter.selector import _extract_time_axis_from_text

        self.assertIsNone(_extract_time_axis_from_text("0.35 Hz"))
        self.assertIsNone(_extract_time_axis_from_text("-0.15 Hz"))

    def test_time_base_out_of_range_reference_frequency_still_selects_candidate(self):
        outcome = _select("3 时基(Time Base)", "1 Hz", cert_u="U=0.00000039 Hz")
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "内晶振输出频率")

    def test_verify_range_logic_returns_fail_when_selected_candidate_is_out_of_range(self):
        outcome = _select(
            "3 时基(Time Base)",
            "1 Hz",
            cert_u="U=0.00000039 Hz",
            reference_value="10 MHz",
        )
        payload = json.loads(
            verify_range_logic(
                "1 Hz",
                outcome.selected_candidate.source["measure_range_text"],
                selected_candidate=outcome.selected_candidate,
            )
        )
        self.assertEqual(payload["status"], "FAIL")

    def test_count_accuracy_selects_count_candidate_by_integer_range(self):
        outcome = _select(
            "2 计数准确度(Count Accuracy)",
            "1",
            basis_code="JJF 1686-2018",
            cert_u="U=1",
        )
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "1～1000")

    def test_count_accuracy_selects_middle_count_band_for_boundary_value(self):
        outcome = _select(
            "2 计数准确度(Count Accuracy)",
            "10000",
            basis_code="JJF 1686-2018",
            cert_u="U=1",
        )
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "1001～10000")

    def test_count_accuracy_selects_narrower_band_for_shared_boundary_value(self):
        outcome = _select(
            "2 计数准确度(Count Accuracy)",
            "1000",
            basis_code="JJF 1686-2018",
            cert_u="U=1",
        )
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "1～1000")

    def test_count_accuracy_out_of_range_still_selects_nearest_count_band(self):
        outcome = _select(
            "2 计数准确度(Count Accuracy)",
            "10001",
            basis_code="JJF 1686-2018",
            cert_u="U=1",
        )
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "10001～99999")

    def test_verify_range_logic_uses_selected_candidate_bounds(self):
        outcome = _select("2 计时(Time)", "1 s")
        payload = json.loads(
            verify_range_logic(
                "1 s",
                outcome.selected_candidate.source["measure_range_text"],
                selected_candidate=outcome.selected_candidate,
            )
        )
        self.assertEqual(payload["status"], "PASS")
        self.assertIn("原始范围=≥1.5μs～24h", payload["reason"])

    def test_verify_range_logic_marks_evm_below_capability_lower_bound_as_review(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="8 信号质量(Signal Quality)(@I路)",
            param_name="8 信号质量(Signal Quality)(@I路)",
            point_text="EVM | 1.38 %",
            cert_u="U=0.80 %",
            measure_value="1.38 %",
            point_value="EVM",
        )
        outcome = select_kb_candidates(cert_point, semantic, MODULATION_QUALITY_KB_ENTRIES)
        payload = json.loads(
            verify_range_logic(
                "1.38 %",
                outcome.selected_candidate.source["measure_range_text"],
                selected_candidate=outcome.selected_candidate,
            )
        )
        self.assertEqual(payload["status"], "REVIEW")
        self.assertIn("低于能力下界", payload["reason"])

    def test_verify_uncertainty_logic_handles_minute_units(self):
        payload = json.loads(verify_uncertainty_logic("1.00 min", "U=0.02 s", "Urel=1×10⁻⁵"))
        self.assertEqual(payload["status"], "PASS")

    def test_verify_uncertainty_logic_keeps_relative_intervals_in_coefficient_space(self):
        payload = json.loads(
            verify_uncertainty_logic("10 MHz", "Urel=2.4×10^-12", "Urel=7×10⁻¹²～2×10⁻¹⁴")
        )
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["comparison_mode"], "interval_bounds")
        self.assertEqual(payload["cert_u_display"], "2.4e-12 (系数)")
        self.assertEqual(payload["kb_u_display"], "Urel=7×10⁻¹²～2×10⁻¹⁴")

    def test_verify_uncertainty_logic_treats_unitless_scientific_frequency_u_as_relative(self):
        payload = json.loads(
            verify_uncertainty_logic("10 MHz", "1.0×10^-13", "Urel=1.4×10⁻¹²～2×10⁻¹⁵")
        )
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["cert_kind"], "relative")
        self.assertEqual(payload["comparison_mode"], "interval_bounds")

    def test_verify_uncertainty_logic_parses_absolute_kb_u_with_prefix_for_seconds_per_day(self):
        payload = json.loads(verify_uncertainty_logic("8.64 s/d", "0.02 s/d", "U=0.011s/d"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["cert_kind"], "absolute")
        self.assertEqual(payload["kb_kind"], "absolute")
        self.assertIn("KB=1.27315e-07", payload["conversion_summary"])

    def test_verify_uncertainty_logic_compares_monthly_difference_against_daily_kb_u(self):
        payload = json.loads(verify_uncertainty_logic("259.2 s/m", "1 s/m", "U=0.011s/d"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["cert_kind"], "absolute")
        self.assertEqual(payload["kb_kind"], "absolute")

    def test_selector_is_stable_across_repeated_runs(self):
        candidate_ids = []
        for _ in range(10):
            outcome = _select("2 计时(Time)", "1 s")
            self.assertIsNotNone(outcome.selected_candidate)
            candidate_ids.append(outcome.selected_candidate.candidate_id)
        self.assertEqual(len(set(candidate_ids)), 1)

    def test_power_level_prefers_positive_range_candidate_for_positive_setpoints(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1931-2021",
            section_label="3 功率电平(Power Level)",
            param_name="3 功率电平(Power Level)",
            point_text="1575.42 MHz 15 dB 14.93 dBm -0.07 dB",
            cert_u="U=0.40 dB",
            measure_value="14.93 dBm",
            reference_value="14.93 dBm",
            error_value="-0.07 dB",
            point_value="15 dB",
        )
        outcome = select_kb_candidates(cert_point, semantic, POWER_KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "0～30)dBm(9 kHz～26.5 GHz)")

    def test_power_level_prefers_negative_range_candidate_for_negative_setpoints(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1931-2021",
            section_label="3 功率电平(Power Level)",
            param_name="3 功率电平(Power Level)",
            point_text="1575.42 MHz -10 dB -10.06 dBm -0.06 dB",
            cert_u="U=0.50 dB",
            measure_value="-10.06 dBm",
            reference_value="-10.06 dBm",
            error_value="-0.06 dB",
            point_value="-10 dB",
        )
        outcome = select_kb_candidates(cert_point, semantic, POWER_KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measure_range_text"], "-130～0)dBm(9 kHz～26.5 GHz)")

    def test_phase_noise_keeps_offset_frequency_axis_and_selects_candidate(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="3.4 相位噪声(Phase Noise)",
            param_name="3.4 相位噪声(Phase Noise)",
            point_text="100 Hz | -83.2 dBc/Hz",
            cert_u="U=2.0 dB",
            measure_value="-83.2 dBc/Hz",
            point_value="100 Hz",
        )

        self.assertEqual(cert_point.axis_family, "offset_frequency")
        self.assertEqual(cert_point.semantic_target, "phase_noise")

        outcome = select_kb_candidates(cert_point, semantic, PHASE_NOISE_KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "相位噪声")

    def test_power_resolution_selects_matching_resolution_candidate(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="4.1 功率分辨力(Power Resolution)",
            param_name="4.1 功率分辨力(Power Resolution)",
            point_text="0.10 dB | 0.00 dB | ≤0.20 dB",
            cert_u="U=0.08 dB",
            measure_value="0.10 dB",
            reference_value="0.10 dB",
            error_value="0.00 dB",
        )

        self.assertEqual(cert_point.semantic_target, "power_accuracy")
        self.assertEqual(cert_point.semantic_subtype, "power_resolution")

        outcome = select_kb_candidates(cert_point, semantic, POWER_RESOLUTION_KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "功率分辨力")

    def test_selector_accepts_valid_parser_section_rule_hint_before_fallback_inference(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="4.1 测试项",
            param_name="4.1 测试项",
            point_text="0.10 dB | 0.00 dB | ≤0.20 dB",
            cert_u="U=0.08 dB",
            measure_value="0.10 dB",
            reference_value="0.10 dB",
            error_value="0.00 dB",
            parser_meta={
                "section_rule": "power_accuracy",
                "section_rule_confidence": 0.99,
                "section_alias_matched": "power resolution",
            },
        )

        self.assertEqual(cert_point.semantic_target, "power_accuracy")
        self.assertTrue(semantic.features.get("parser_hint_accepted"))

    def test_modulation_quality_prefers_matching_metric_and_rejects_cross_metric_candidate(self):
        evm_point, evm_semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="3.5 信号质量(Signal Quality)(@I路)",
            param_name="3.5 信号质量(Signal Quality)(@I路)",
            point_text="EVM | 1.92 %",
            cert_u="U=0.80 %",
            measure_value="1.92 %",
            point_value="EVM",
        )
        evm_outcome = select_kb_candidates(evm_point, evm_semantic, MODULATION_QUALITY_KB_ENTRIES)
        self.assertEqual(evm_point.semantic_subtype, "evm")
        self.assertIsNotNone(evm_outcome.selected_candidate)
        self.assertEqual(evm_outcome.selected_candidate.source["measured"], "误差矢量幅度")

        iq_point, iq_semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="3.5 信号质量(Signal Quality)(@I路)",
            param_name="3.5 信号质量(Signal Quality)(@I路)",
            point_text="IQ Offset | -54.80 dB",
            cert_u="U=2.0 dB",
            measure_value="-54.80 dB",
            point_value="IQ Offset",
        )
        iq_outcome = select_kb_candidates(iq_point, iq_semantic, MODULATION_QUALITY_KB_ENTRIES)
        self.assertEqual(iq_point.semantic_subtype, "iq_offset")
        self.assertIsNone(iq_outcome.selected_candidate)
        self.assertEqual(iq_outcome.rationale, "same basis missing kb subtype: iq_offset")

    def test_dynamic_range_prefers_matching_motion_metric(self):
        speed_point, speed_semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="3.3.1 速度(Speed)",
            param_name="3.3.1 速度(Speed)",
            point_text="120000 m/s | -0.01 m/s",
            cert_u="U=1.0 m/s",
            measure_value="120000 m/s",
        )
        speed_outcome = select_kb_candidates(speed_point, speed_semantic, DYNAMIC_RANGE_KB_ENTRIES)
        self.assertIsNotNone(speed_outcome.selected_candidate)
        self.assertEqual(speed_outcome.selected_candidate.source["measured"], "速度动态范围")

        accel_point, accel_semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="3.3.2 加速度(Accelerated Speed)",
            param_name="3.3.2 加速度(Accelerated Speed)",
            point_text="36000 m/s² | -0.005 m/s²",
            cert_u="U=0.30 m/s²",
            measure_value="36000 m/s²",
        )
        accel_outcome = select_kb_candidates(accel_point, accel_semantic, DYNAMIC_RANGE_KB_ENTRIES)
        self.assertIsNotNone(accel_outcome.selected_candidate)
        self.assertEqual(accel_outcome.selected_candidate.source["measured"], "加速度动态范围")

        jerk_point, jerk_semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="3.3.3 加加速度(Stacking Velocity)",
            param_name="3.3.3 加加速度(Stacking Velocity)",
            point_text="10000 m/s³ | 0.001 m/s³",
            cert_u="U=0.60 m/s³",
            measure_value="10000 m/s³",
        )
        jerk_outcome = select_kb_candidates(jerk_point, jerk_semantic, DYNAMIC_RANGE_KB_ENTRIES)
        self.assertIsNotNone(jerk_outcome.selected_candidate)
        self.assertEqual(jerk_outcome.selected_candidate.source["measured"], "加加速度动态范围")

    def test_dynamic_range_does_not_fallback_from_power_to_pseudorange(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="4.3 功率动态范围(Power Dynamic Range)",
            param_name="4.3 功率动态范围(Power Dynamic Range)",
            point_text="标准值 82 dB 允许误差 ≥60 dB",
            cert_u="U=2 dB",
            measure_value="82 dB",
            reference_value="82 dB",
        )
        outcome = select_kb_candidates(cert_point, semantic, DYNAMIC_RANGE_KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "功率动态范围")

    def test_dynamic_range_reports_power_kb_gap_when_same_basis_lacks_power_metric(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="4.3 功率动态范围(Power Dynamic Range)",
            param_name="4.3 功率动态范围(Power Dynamic Range)",
            point_text="标准值 82 dB 允许误差 ≥60 dB",
            cert_u="U=2 dB",
            measure_value="82 dB",
            reference_value="82 dB",
        )
        outcome = select_kb_candidates(cert_point, semantic, DYNAMIC_RANGE_KB_ENTRIES[1:])
        self.assertIsNone(outcome.selected_candidate)
        self.assertEqual(outcome.rationale, "same basis missing kb subtype: power_dynamic_range")

    def test_dynamic_range_pseudorange_candidate_uses_length_family(self):
        candidate = normalize_kb_candidate(
            {
                "file_code": "JJF 1471-2014",
                "measured": "伪距分辨力",
                "measure_range_text": "(0.01～0.1)m",
                "uncertainty": {"type": "U", "value_display": "U=0.02m"},
            }
        )
        self.assertEqual(selector_module._candidate_unit_family(candidate), "length")

    def test_spectral_purity_prefers_spurious_candidate_for_spurious_rows(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF 1471-2014",
            section_label="8 信号纯度(Spectral Purity)",
            param_name="8 信号纯度(Spectral Purity)",
            point_text="杂波抑制 -76.1 dB",
            cert_u="U=1.6 dB",
            measure_value="-76.1 dB",
            reference_value="-76.1 dB",
            point_value="杂波抑制",
        )
        outcome = select_kb_candidates(cert_point, semantic, SPECTRAL_PURITY_KB_ENTRIES)
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.source["measured"], "非谐波抑制")

    def test_infer_kb_capability_supports_new_vswr_and_impedance_targets(self):
        vswr_cap = infer_kb_capability(EXTRA_KB_ENTRIES[0])
        self.assertEqual(vswr_cap.capability_target, "vswr_accuracy")

        imp_cap = infer_kb_capability(EXTRA_KB_ENTRIES[1])
        self.assertEqual(imp_cap.capability_target, "impedance_accuracy")

    def test_infer_kb_capability_supports_new_consistency_targets(self):
        cnr_cap = infer_kb_capability(EXTRA_KB_ENTRIES[2])
        self.assertEqual(cnr_cap.capability_target, "cnr_consistency")

        pos_cap = infer_kb_capability(EXTRA_KB_ENTRIES[3])
        self.assertEqual(pos_cap.capability_target, "position_consistency")

    def test_selector_exact_matches_new_vswr_target(self):
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF EXTRA",
            section_label="6 输入端电压驻波比(Input Voltage Standing Wave Ratio)",
            param_name="6 输入端电压驻波比(Input Voltage Standing Wave Ratio)",
            point_text="BDS-B1 1.18",
            cert_u="U=0.05",
            measure_value="1.18",
            point_value="BDS-B1",
        )
        outcome = select_kb_candidates(cert_point, semantic, [EXTRA_KB_ENTRIES[0]])
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.capability_target, "vswr_accuracy")

    def test_selector_exact_matches_new_impedance_target(self):
        contract = build_parameter_contract(
            project_title="5 输入阻抗(Input Impedance)",
            details={
                "标称值 (Nominal)": "1 MΩ",
                "标准值 (Reference)": "1.0016 MΩ",
                "误差 (Error)": "-1.6 kΩ",
                "允许误差 (Limit)": "±20.0 kΩ",
                "U (k=2)": "1.2 kΩ",
            },
            section_rule="unknown",
        )
        cert_point, semantic = normalize_cert_point(
            basis_code="JJF EXTRA",
            section_label="5 输入阻抗(Input Impedance)",
            param_name="5 输入阻抗(Input Impedance)",
            point_text="1 MΩ 误差 -1.6 kΩ",
            cert_u="U=1.2 kΩ",
            parameter_contract=contract,
        )
        outcome = select_kb_candidates(cert_point, semantic, [EXTRA_KB_ENTRIES[1]])
        self.assertIsNotNone(outcome.selected_candidate)
        self.assertEqual(outcome.selected_candidate.capability_target, "impedance_accuracy")


if __name__ == "__main__":
    unittest.main()
