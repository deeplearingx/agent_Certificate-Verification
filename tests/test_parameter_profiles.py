from langchain_app.checks.parameter.profiles import (
    best_profile,
    enabled_semantic_targets,
    match_profiles,
)


def test_gnss_profile_matches_pdf_category_and_enables_signal_targets():
    matches = match_profiles(pdf_category="全球导航卫星系统(GNSS) 信号模拟器")
    assert matches[0].profile.profile_id == "time_frequency.gnss"

    targets = enabled_semantic_targets(match.profile for match in matches)
    assert "modulation_quality" in targets
    assert "position_consistency" in targets


def test_frequency_standard_prefers_specific_profile():
    profile = best_profile(instrument_name="铷原子频率标准")
    assert profile is not None
    assert profile.profile_id == "time_frequency.frequency_standard"
    assert "reference_oscillator" in profile.semantic_targets


def test_unknown_instrument_falls_back_to_generic_profile():
    profile = best_profile(instrument_name="未知仪器")
    assert profile is not None
    assert profile.profile_id == "generic.default"

