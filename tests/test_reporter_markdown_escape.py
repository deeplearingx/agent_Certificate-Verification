import unittest

from langchain_app.checks.parameter.reporter import build_batch_summary_table


class ReporterMarkdownEscapeTest(unittest.TestCase):
    def test_build_batch_summary_table_escapes_pipes_in_reason(self):
        md = build_batch_summary_table(
            ['A'],
            [{'param_name': 'A', 'status': 'FAIL', 'reason': '候选ID: JJG238|时间间隔|≥1.5 μs～24 h|0.58%'}],
        )
        self.assertIn('JJG238\\|时间间隔\\|≥1.5 μs～24 h\\|0.58%', md)


if __name__ == '__main__':
    unittest.main()
