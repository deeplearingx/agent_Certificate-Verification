import json
import sys
import types
import unittest


if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")
    pydantic_stub.BaseModel = object
    sys.modules["pydantic"] = pydantic_stub

if "chromadb" not in sys.modules:
    chromadb_stub = types.ModuleType("chromadb")

    class _PersistentClient:
        def __init__(self, *args, **kwargs):
            pass

    chromadb_stub.PersistentClient = _PersistentClient
    sys.modules["chromadb"] = chromadb_stub


from langchain_app.checks.parameter import parameter as parameter_module
from langchain_app.checks.parameter.semantic import select_basis_with_audit


class ParameterUncertaintyBasisTest(unittest.TestCase):
    def test_plain_u_with_inherited_unit_uses_error_value_as_probe(self):
        param = {
            "__parser_meta": {
                "header_rules": {"cert_u": "U (k=2)"},
                "unit_inherited": True,
            }
        }

        probe = parameter_module._resolve_uncertainty_probe_value(
            param,
            "10 MHz",
            "6.0×10^-11",
        )

        self.assertEqual(probe, "6.0×10^-11")

    def test_urel_header_keeps_measure_value_probe(self):
        param = {
            "__parser_meta": {
                "header_rules": {"cert_u": "Urel (k=2)"},
                "unit_inherited": True,
            }
        }

        probe = parameter_module._resolve_uncertainty_probe_value(
            param,
            "10 MHz",
            "6.0×10^-11",
        )

        self.assertEqual(probe, "10 MHz")

    def test_reference_oscillator_plain_u_without_runtime_flag_still_uses_error_value(self):
        param = {
            "项目名称": "2 开机特性(Warm-up Characteristics)",
            "__parser_meta": {
                "section_rule": "reference_oscillator",
                "header_rules": {
                    "error_value": "开机特性",
                    "cert_u": "U",
                },
                "unit_inherited": False,
            }
        }

        probe = parameter_module._resolve_uncertainty_probe_value(
            param,
            "",
            "1.0×10^-8",
        )

        self.assertEqual(probe, "1.0×10^-8")

    def test_legacy_reference_oscillator_json_without_section_rule_still_uses_error_value(self):
        param = {
            "项目名称": "2 开机特性(Warm-up Characteristics)",
            "__parser_meta": {
                "header_rules": {"cert_u": "U"},
                "unit_inherited": False,
            },
        }

        probe = parameter_module._resolve_uncertainty_probe_value(
            param,
            "",
            "1.0×10^-8",
        )

        self.assertEqual(probe, "1.0×10^-8")

    def test_inherited_plain_u_fixes_reference_oscillator_uncertainty_comparison(self):
        param = {
            "__parser_meta": {
                "header_rules": {"cert_u": "U (k=2)"},
                "unit_inherited": True,
            }
        }

        probe = parameter_module._resolve_uncertainty_probe_value(
            param,
            "10 MHz",
            "1.0×10^-8",
        )
        result = json.loads(
            parameter_module.verify_uncertainty_logic(
                probe,
                "1.0×10^-12",
                "Urel=1.6×10⁻¹²",
            )
        )

        self.assertEqual(probe, "1.0×10^-8")
        self.assertEqual(result["status"], "PASS")

    def test_input_sensitivity_exact_match_skips_incompatible_uncertainty_representation(self):
        kb_entries = [
            {
                "file_code": "JJG 841",
                "measured": "频率测量范围及输入灵敏度",
                "measure_range_text": "1 mV～1 V(0.1 Hz～100 kHz)",
                "uncertainty": {"type": "U", "value_display": "U=0.2dB"},
            }
        ]
        selection_result = select_basis_with_audit(
            basis_code="JJG 841-2012",
            section_label="3 触发灵敏度(Trigger Sensitivity)",
            param_name="3 触发灵敏度(Trigger Sensitivity)",
            point_text="频率 0.1 MHz 灵敏度 10 mV",
            cert_u="0.1 mV",
            measure_value="0.1 MHz",
            reference_value="",
            error_value="10 mV",
            parameter_contract={
                "semantic_target": "input_sensitivity",
                "measure_value": "0.1 MHz",
                "error_value": "10 mV",
                "cert_u": "0.1 mV",
                "unit_family": "voltage_power",
                "confidence": 0.95,
            },
            parser_meta={
                "section_rule": "input_sensitivity",
                "section_rule_confidence": 0.99,
                "header_rules": {
                    "measure_value": "频率 (Frequency)",
                    "error_value": "灵敏度 (Sensitivity)",
                    "cert_u": "U (k=2)",
                },
            },
            kb_entries=kb_entries,
        )

        gate = parameter_module._resolve_uncertainty_comparability(
            selection_result,
            selection_result.selected_candidate,
            cert_u="0.1 mV",
            kb_u="U=0.2dB",
            probe_value="10 mV",
        )

        self.assertTrue(gate["comparable"] is False)
        self.assertEqual(gate["decision"], "skip_compare")
        self.assertEqual(gate["cert_repr"], "voltage_linear")
        self.assertEqual(gate["kb_repr"], "power_db")

    def test_comparison_uncertainty_uses_frequency_measure_as_uncertainty_probe(self):
        param = {
            "项目名称": "2 比对不确定度",
            "__parameter_contract": {
                "semantic_target": "reference_oscillator",
                "semantic_subtype": "comparison_uncertainty",
                "measure_value": "10 MHz",
                "condition_value": "10 MHz",
                "error_value": "4.4×10^-15",
                "cert_u": "1.0×10^-15",
                "item_label": "100 s",
            },
            "__parser_meta": {
                "section_rule": "reference_oscillator",
                "header_rules": {
                    "measure_value": "频率 (Frequency)",
                    "error_value": "比对不确定度",
                    "cert_u": "U (k=2)",
                    "point_value": "取样时间τ (Sampling Time)",
                },
                "unit_inherited": False,
            },
        }

        selected_kb = types.SimpleNamespace(
            capability_target="reference_oscillator",
            semantic_subtype="comparison_uncertainty",
            source={},
        )

        probe = parameter_module._resolve_uncertainty_probe_value(
            param,
            "10 MHz",
            "4.4×10^-15",
            selected_kb=selected_kb,
        )

        self.assertEqual(probe, "10 MHz")

        result = json.loads(
            parameter_module.verify_uncertainty_logic(
                probe,
                "1.0×10^-15",
                "Urel=1.4×10⁻¹²～2×10⁻¹⁵",
            )
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["cert_kind"], "relative")
        self.assertEqual(result["comparison_mode"], "interval_bounds")


if __name__ == "__main__":
    unittest.main()
