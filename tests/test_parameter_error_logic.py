import json
import unittest

from langchain_app.checks.parameter.validator import verify_error_logic


class ParameterErrorLogicTest(unittest.TestCase):
    def test_symmetric_error_range_fails_when_absolute_error_exceeds_upper_bound(self):
        payload = json.loads(
            verify_error_logic("1.0×10^-8", "±(2×10⁻¹⁰～1×10⁻¹¹)", "10 MHz")
        )

        self.assertEqual(payload["status"], "FAIL")
        self.assertIn("不在对称范围", payload["reason"])

    def test_symmetric_error_range_uses_absolute_value_for_negative_errors(self):
        payload = json.loads(
            verify_error_logic("-6.0×10^-11", "±(2×10⁻¹⁰～1×10⁻¹¹)", "10 MHz")
        )

        self.assertEqual(payload["status"], "PASS")
        self.assertIn("在对称范围", payload["reason"])


if __name__ == "__main__":
    unittest.main()
