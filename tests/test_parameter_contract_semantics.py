from langchain_app.checks.parameter.contracts import build_parameter_contract


def test_build_parameter_contract_prefers_period_accuracy_for_output_time_interval_error_rows():
    contract = build_parameter_contract(
        project_title="3 秒表功能输出时间间隔(Time Interval)",
        details={
            "标称值 (Nominal)": "1 s",
            "标准值 (Reference)": "1.0000 s",
            "误差 (Error)": "0.0 ms",
            "允许范围 (Limit)": "±3.0 ms",
            "U (k=2)": "0.1 ms",
        },
        section_rule="period_range",
    )

    assert contract["row_shape"] == "nominal_reference_error_u"
    assert contract["semantic_target"] == "period_accuracy"
    assert contract["semantic_subtype"] == "output_time_interval"
    assert contract["unit_family"] == "time"


def test_build_parameter_contract_keeps_time_family_for_time_accuracy_rows_with_percent_limit():
    contract = build_parameter_contract(
        project_title="3 计时准确度(Time Accuracy)",
        details={
            "标称值 (Nominal)": "1.00 min",
            "标准值 (Reference)": "59.97 s",
            "误差 (Error)": "0.03 s",
            "相对误差 (Relative Error)": "0.05 %",
            "允许误差 (Limit)": "±1.00 %",
            "U (k=2)": "0.02 s",
        },
        section_rule="period_accuracy",
    )

    assert contract["semantic_target"] == "period_accuracy"
    assert contract["unit_family"] == "time"


def test_build_parameter_contract_upgrades_generic_time_rows_with_limit_to_period_accuracy():
    contract = build_parameter_contract(
        project_title="2 时间(Time)",
        details={
            "标称值 (Nominal)": "10.0 s",
            "标准值 (Reference)": "10.02 s",
            "误差 (Error)": "-0.02 s",
            "允许范围 (Limit)": "±0.08 s",
            "U (k=2)": "0.01 s",
        },
        section_rule="period_range",
    )

    assert contract["semantic_target"] == "period_accuracy"
    assert contract["unit_family"] == "time"


def test_build_parameter_contract_prefers_frequency_accuracy_for_frequency_error_rows():
    contract = build_parameter_contract(
        project_title="4 频率测量误差(Frequency Measurement Error)",
        details={
            "标称值 (Nominal)": "10 MHz",
            "标准值 (Reference)": "10.000000 MHz",
            "误差 (Error)": "0.0001 kHz",
            "允许范围 (Limit)": "±0.0020 kHz",
            "U (k=2)": "0.0003 kHz",
        },
        section_rule="frequency_range",
    )

    assert contract["row_shape"] == "nominal_reference_error_u"
    assert contract["semantic_target"] == "frequency_accuracy"
    assert contract["unit_family"] == "frequency"


def test_build_parameter_contract_routes_fixed_point_frequency_accuracy_to_reference_oscillator():
    contract = build_parameter_contract(
        project_title="5 频率准确度(Frequency Accuracy)",
        details={
            "标称值 (Nominal)": "10 MHz",
            "误差 (Error)": "2×10^-9",
            "U (k=2)": "3.0×10^-12",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "reference_oscillator"
    assert contract["semantic_subtype"] == "relative_frequency_deviation"
    assert contract["unit_family"] == "frequency"


def test_build_parameter_contract_preserves_reference_oscillator_for_metric_rows():
    contract = build_parameter_contract(
        project_title="2 内时基振荡器(Internal TimeBase) 相对频率偏差(Relative Frequency Deviation)",
        details={
            "标准值 (Reference)": "8.9×10^-8",
            "U (k=2)": "1.0×10^-10",
        },
        section_rule="reference_oscillator",
    )

    assert contract["semantic_target"] == "reference_oscillator"


def test_build_parameter_contract_prefers_input_sensitivity_for_sensitivity_rows():
    contract = build_parameter_contract(
        project_title="3 输入灵敏度检查(Input Sensitivity Check)",
        details={
            "频率 (Frequency)": "100 kHz",
            "灵敏度 (Sensitivity)": "6.5 mV",
            "U (k=2)": "0.2 mV",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "input_sensitivity"
    assert contract["condition_axis"] == "carrier_frequency"


def test_build_parameter_contract_prefers_power_accuracy_for_amplitude_rows():
    contract = build_parameter_contract(
        project_title="2 幅度测量准确度(Amplitude Measurement Accuracy)(1MΩ)",
        details={
            "标准值 (Reference)": "12.000 mV",
            "指示值 (Indicated)": "11.93 mV",
            "误差 (Error)": "-0.07 mV",
            "允许误差 (Limit)": "±1.44 mV",
            "U (k=2)": "0.06 mV",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "power_accuracy"
    assert contract["unit_family"] == "voltage_power"


def test_build_parameter_contract_prefers_power_accuracy_for_dc_offset_rows_without_error_column():
    contract = build_parameter_contract(
        project_title="3 直流偏置准确度(DC Offset Accuracy)(Input Impedance:1MΩ)",
        details={
            "偏置 (Offset)": "0 mV",
            "指示值 (Indicated)": "-0.07 mV",
            "允许误差 (Limit)": "±2.20 mV",
            "U (k=2)": "0.04 mV",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "power_accuracy"


def test_build_parameter_contract_prefers_period_accuracy_for_single_pulse_width_rows():
    contract = build_parameter_contract(
        project_title="5 单脉冲宽度(Single Pulse Width)",
        details={
            "标称值 (Nominal)": "5 ns",
            "测量值 (Measurement Value)": "5.1 ns",
            "误差 (Error)": "-0.1 ns",
            "U (k=2)": "2.4 ns",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "period_accuracy"
    assert contract["unit_family"] == "time"


def test_build_parameter_contract_prefers_frequency_range_for_bandwidth_rows():
    contract = build_parameter_contract(
        project_title="4 频带宽度(Frequecy Bandwidth)(DC Coupled)",
        details={
            "频带宽度 (Bandwidth)": "150 MHz",
            "允许误差 (Limit)": "≥100 MHz",
            "U (k=2)": "2 MHz",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "frequency_range"
    assert contract["unit_family"] == "frequency"


def test_build_parameter_contract_prefers_frequency_accuracy_for_output_frequency_rows():
    contract = build_parameter_contract(
        project_title="2 输出频率(Output Frequency)",
        details={
            "标称值 (Nominal)": "10 MHz",
            "标准值 (Reference)": "9.999990 MHz",
            "误差 (Error)": "0.010 kHz",
            "允许误差 (Limit)": "±0.020 kHz",
            "U (k=2)": "0.004 kHz",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "frequency_accuracy"
    assert contract["unit_family"] == "frequency"


def test_build_parameter_contract_prefers_count_accuracy_for_receiving_channel_rows():
    contract = build_parameter_contract(
        project_title="2 接收通道数(Number of Receiving Channels)",
        details={
            "标称值 (Nominal)": "16",
            "测量值 (Measurement Value)": "16",
            "误差 (Error)": "0",
            "U (k=2)": "0",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "count_accuracy"


def test_build_parameter_contract_prefers_power_accuracy_for_amplitude_flatness_rows():
    contract = build_parameter_contract(
        project_title="7 幅度平坦度(Amplitude Flatness)(50Ω)(Sine Wave)",
        details={
            "通道 (Channel)": "CH1",
            "频率 (Frequency)": "1 kHz",
            "输出幅度 (Amplitude)": "100 mVp-p",
            "平坦度 (Flatness)": "0.00 dB",
            "U (k=2)": "0.02 dB",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "power_accuracy"


def test_build_parameter_contract_prefers_frequency_accuracy_for_playback_signal_frequency_rows():
    contract = build_parameter_contract(
        project_title="6 回放信号频率(Play Back the Signal Frequency)",
        details={
            "频点 (Frequency Point)": "BDS-B1",
            "标称值 (Nominal)": "1561.098000 MHz",
            "测量值 (Measurement Value)": "1561.098000 MHz",
            "误差 (Error)": "0.000 kHz",
            "U (k=2)": "0.055 kHz",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "frequency_accuracy"


def test_build_parameter_contract_prefers_dynamic_range_for_input_power_range_rows():
    contract = build_parameter_contract(
        project_title="3 采集信号输入功率范围(Range of Input Power for Signal Acquisition)",
        details={
            "频点(Frequency Point)": "BDS-B1",
            "频率(Frequency)": "1561.098 MHz",
            "测量值(Min.)": "-132.6 dBm",
            "测量值(Max.)": "-82.1 dBm",
            "U(k=2)": "0.7 dB",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "dynamic_range"


def test_build_parameter_contract_prefers_spectral_purity_for_out_of_band_rejection_rows():
    contract = build_parameter_contract(
        project_title="10 带外抑制(Out of Band Rejection)",
        details={
            "频点(Frequency Point)": "BDS-B1",
            "带宽(Bandwidth)": "4.092 MHz",
            "测量值(Measurement Value)": "-44.6 dBc",
            "U(k=2)": "0.9 dB",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "spectral_purity"


def test_build_parameter_contract_prefers_power_accuracy_for_pulse_amplitude_rows():
    contract = build_parameter_contract(
        project_title="9 脉冲幅度(Pulse Amplitude)",
        details={
            "标称值 (Nominal)": "1.0 V",
            "测量值 (Measurement Value)": "0.99 V",
            "误差 (Error)": "0.01 V",
            "U (k=2)": "0.02 V",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "power_accuracy"


def test_build_parameter_contract_prefers_period_accuracy_for_duty_cycle_rows():
    contract = build_parameter_contract(
        project_title="8 脉冲波占空比(Pulse Wave Duty Cycle)(50Ω、10Vpp)",
        details={
            "频率 (Frequency)": "100.00 kHz",
            "标称值 (Nominal)": "50 %",
            "标准值 (Reference)": "50.00 %",
            "误差 (Error)": "0.00 %",
            "U (k=2)": "0.12 %",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "period_accuracy"


def test_build_parameter_contract_preserves_reference_oscillator_for_diurnal_fluctuation_rows():
    contract = build_parameter_contract(
        project_title="3 日频率波动(Diurnal Frequency Fluctuation)",
        details={
            "测量值 (Measurement Value)": "1.0×10-9",
            "U (k=2)": "2.0×10-10",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "reference_oscillator"
    assert contract["semantic_subtype"] == "aging_rate"


def test_build_parameter_contract_prefers_vswr_accuracy_for_vswr_rows():
    contract = build_parameter_contract(
        project_title="6 输入端电压驻波比(Input Voltage Standing Wave Ratio)",
        details={
            "频点(Frequency Point)": "BDS-B1",
            "测量值 (Measurement Value)": "1.18",
            "U (k=2)": "0.05",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "vswr_accuracy"


def test_build_parameter_contract_prefers_impedance_accuracy_for_input_impedance_rows():
    contract = build_parameter_contract(
        project_title="5 输入阻抗(Input Impedance)(DC Coupled)",
        details={
            "标称值 (Nominal)": "1 MΩ",
            "标准值 (Reference)": "1.0016 MΩ",
            "误差 (Error)": "-1.6 kΩ",
            "允许误差 (Limit)": "±20.0 kΩ",
            "U (k=2)": "1.2 kΩ",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "impedance_accuracy"


def test_build_parameter_contract_prefers_cnr_consistency_for_carrier_to_noise_rows():
    contract = build_parameter_contract(
        project_title="11 载噪比一致性(Consistency of Carrier to Noise Ratio)",
        details={
            "频点(Frequency Point)": "BDS-B1",
            "载噪比偏差(Carrier to Noise Ratio Deviation)": "0.5 dB",
            "U(k=2)": "0.7 dB",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "cnr_consistency"


def test_build_parameter_contract_prefers_position_consistency_for_location_consistency_rows():
    contract = build_parameter_contract(
        project_title="12 定位一致性(Location consistency)",
        details={
            "频点(Frequency Point)": "BDS-B1",
            "回放偏差(Playback Deviation)": "0.5 m",
            "U(k=2)": "0.5 m",
        },
        section_rule="unknown",
    )

    assert contract["semantic_target"] == "position_consistency"
