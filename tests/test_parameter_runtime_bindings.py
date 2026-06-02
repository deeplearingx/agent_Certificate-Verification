import re
import sys
import types
import unittest
from types import SimpleNamespace


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


class ParameterRuntimeBindingsTest(unittest.TestCase):
    def test_refresh_runtime_dependency_bindings_rebinds_validator_symbol(self):
        sentinel = object()
        parameter_module.verify_uncertainty_logic = sentinel

        parameter_module._refresh_runtime_dependency_bindings(force=True)

        self.assertIs(
            parameter_module.verify_uncertainty_logic,
            parameter_module._RUNTIME_DEPENDENCY_MODULES["validator"].verify_uncertainty_logic,
        )

    def test_param_check_version_stamp_covers_dependency_bundle(self):
        stamp = parameter_module._build_param_check_version_stamp()

        self.assertIn("bundle", stamp)
        match = re.search(r"files=(\d+)", stamp)
        self.assertIsNotNone(match)
        self.assertGreater(int(match.group(1)), 1)

    def test_input_sensitivity_business_rule_is_available_in_langchain_main_chain(self):
        selection_result = SimpleNamespace(
            cert_point=SimpleNamespace(semantic_target="input_sensitivity")
        )

        decision = parameter_module._resolve_input_sensitivity_business_override(
            param_name="3 输入灵敏度检查(Input Sensitivity Check)",
            selection_result=selection_result,
            measure_val="频率 100 kHz 灵敏度 6.5 mV",
            cert_u="N/A",
            error_val="6.5 mV",
            limit_val="",
        )

        self.assertEqual(
            decision,
            (
                "PASS",
                "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS",
            ),
        )


if __name__ == "__main__":
    unittest.main()
