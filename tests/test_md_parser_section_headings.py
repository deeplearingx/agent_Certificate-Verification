from pathlib import Path
import unittest

from md_parser_no_llm import parse_md_to_json, split_md_to_blocks


class MdParserSectionHeadingTest(unittest.TestCase):
    def test_split_md_to_blocks_recognizes_numbered_headings_with_trailing_dots(self):
        md_text = Path("local_md/2GB24003522-0015.md").read_text(encoding="utf-8", errors="ignore")

        blocks = split_md_to_blocks(md_text)
        titles = [title for title, _ in blocks]

        self.assertTrue(any("1. 外观与工作正常性检查" in title for title in titles))
        self.assertTrue(any("2. 频率误差(Frequency Error)" in title for title in titles))

    def test_parse_md_to_json_extracts_frequency_error_rows_from_sample_2gb24003522_0015(self):
        result = parse_md_to_json(str(Path("local_md/2GB24003522-0015.md")))
        rows = result["依据参数_中间数据"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["测量值"], "2. 频率误差(Frequency Error)")
        self.assertEqual(rows[0]["项目名称"], "2. 频率误差(Frequency Error)")
        self.assertEqual(rows[0]["数据明细"]["设定值"], "10 MHz")
        self.assertEqual(rows[0]["数据明细"]["标准值"], "10.00000015 MHz")
        self.assertEqual(rows[0]["数据明细"]["误差"], "-0.15 Hz")
        self.assertEqual(rows[0]["数据明细"]["允许误差"], "±0.85 Hz")
        self.assertEqual(rows[0]["数据明细"]["结论"], "P")
        self.assertEqual(rows[0]["数据明细"]["U"], "0.35 Hz")
        self.assertEqual(rows[0]["__normalized_fields"]["point_value"], "10 MHz")
        self.assertEqual(rows[0]["__normalized_fields"]["reference_value"], "10.00000015 MHz")
        self.assertEqual(rows[0]["__normalized_fields"]["error_value"], "-0.15 Hz")
        self.assertEqual(rows[0]["__normalized_fields"]["limit_value"], "±0.85 Hz")
        self.assertEqual(rows[0]["__normalized_fields"]["cert_u"], "0.35 Hz")
        self.assertEqual(rows[0]["__normalized_fields"]["result_flag"], "P")
        self.assertEqual(rows[0]["__parser_meta"]["section_rule"], "frequency_accuracy")

    def test_parse_md_to_json_keeps_parameter_blocks_with_remarks(self):
        result = parse_md_to_json(str(Path("local_md/2GB25003297-0001.md")))
        rows = result["依据参数_中间数据"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["项目名称"], "2. 频率误差(Frequency Error)")
        self.assertEqual(rows[0]["__parser_meta"]["section_rule"], "frequency_accuracy")


if __name__ == "__main__":
    unittest.main()
