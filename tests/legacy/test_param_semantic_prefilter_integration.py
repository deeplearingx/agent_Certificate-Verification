from param_check import _apply_semantic_basis_prefilter


def _jjg841_items():
    return [
        {"measured": "crystal", "measure_range_text": "1MHz,2MHz,5MHz,10MHz", "u_text": "Urel=3e-12"},
        {"measured": "frequency_measurement_range_and_input_sensitivity", "measure_range_text": "1mV~1V(>100kHz~20MHz)", "u_text": "U=0.5dB"},
        {"measured": "frequency", "measure_range_text": "10Hz~50GHz", "u_text": "Urel=2e-11"},
        {"measured": "period", "measure_range_text": "40ps~10s", "u_text": "Urel=2e-11"},
    ]


def _jjg601_items():
    return [
        {"measured": "output time interval", "measure_range_text": ">1ms~9999.9s", "u_text": "Urel=8.4e-8"},
        {"measured": "internal crystal output frequency", "measure_range_text": "10MHz", "u_text": "Urel=3e-12"},
        {"measured": "frequency", "measure_range_text": "relative frequency deviation: ±(1e-5~1e-10)", "u_text": "Urel=1e-11"},
    ]


def test_semantic_prefilter_keeps_frequency_for_frequency_measurement_batch():
    batch_params = [
        {
            "项目名称": "4 频率测量误差",
            "数据明细": {
                "标准值 (Reference)": "10.00000000 MHz",
                "指示值 (Indicated)": "9.99999998 MHz",
                "误差 (Error)": "-0.00002 kHz",
                "允许误差 (Limit)": "±0.0003 kHz",
                "U (k=2)": "0.00006 kHz",
            },
        }
    ]
    filtered, audit = _apply_semantic_basis_prefilter(_jjg841_items(), batch_params)
    assert [item["measured"] for item in filtered] == ["frequency"]
    assert any("accuracy_check:frequency" in line for line in audit)


def test_semantic_prefilter_keeps_crystal_for_relative_frequency_batch():
    batch_params = [
        {
            "椤圭洰鍚嶇О": "2.1 鐩稿棰戠巼鍋忓樊",
            "鏁版嵁鏄庣粏": {
                "杈撳嚭棰戠巼(Frequency)(MHz)": "10 MHz",
                "鐩稿棰戠巼鍋忓樊(Relative Frequency Deviation)": "3.2×10^-9",
                "U (k=2)": "3×10^-10",
            },
        }
    ]
    filtered, audit = _apply_semantic_basis_prefilter(_jjg841_items(), batch_params)
    assert [item["measured"] for item in filtered] == ["crystal"]
    assert any("reference_check:relative_frequency" in line for line in audit)


def test_semantic_prefilter_falls_back_when_schema_cannot_classify():
    kb_items = [
        {"measured": "phase_noise", "measure_range_text": "(-130~-60)dBc/Hz", "u_text": "U=3dB"},
        {"measured": "error_vector_magnitude", "measure_range_text": "2%~20%", "u_text": "U=0.7%"},
    ]
    batch_params = [
        {
            "项目名称": "内部通道延迟",
            "数据明细": {
                "测量值": "12 ns",
                "U (k=2)": "0.5 ns",
            },
        }
    ]
    filtered, audit = _apply_semantic_basis_prefilter(kb_items, batch_params)
    assert filtered == kb_items
    assert any("semantic prefilter skipped" in line or "fallback" in line for line in audit)


def test_semantic_prefilter_keeps_internal_crystal_candidates_for_internal_timebase_batch():
    batch_params = [
        {
            "项目名称": "2 内时基振荡器",
            "数据明细": {
                "项目 (Item)": "相对频率偏差:",
                "Reference": "5.7×10^-8",
                "U (k=2)": "3×10^-10",
            },
        }
    ]
    filtered, audit = _apply_semantic_basis_prefilter(_jjg601_items(), batch_params)
    assert [item["measured"] for item in filtered] == ["internal crystal output frequency"]
    assert any("reference_check:relative_frequency" in line for line in audit)
