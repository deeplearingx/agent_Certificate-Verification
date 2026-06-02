from types import SimpleNamespace

from langchain_app.checks.parameter.parameter import _audit_axis_labels_for_candidate


def test_power_accuracy_frequency_axis_uses_filter_labels():
    candidate = SimpleNamespace(
        capability_target="power_accuracy",
        result_quantity="power_value",
        condition_axis="frequency_band",
    )

    value_label, band_label = _audit_axis_labels_for_candidate(candidate)

    assert value_label == "`频率轴归一化` "
    assert band_label == "`候选频段归一化` "


def test_non_power_candidates_keep_legacy_audit_labels():
    candidate = SimpleNamespace(
        capability_target="frequency_accuracy",
        result_quantity="frequency_error_or_value",
        condition_axis="frequency_band",
    )

    value_label, band_label = _audit_axis_labels_for_candidate(candidate)

    assert value_label == "`测量点归一化` "
    assert band_label == "`KB范围归一化` "
