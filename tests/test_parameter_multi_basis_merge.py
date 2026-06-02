import unittest
import sys
import types


if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")
    pydantic_stub.BaseModel = object
    sys.modules["pydantic"] = pydantic_stub

if "chromadb" not in sys.modules:
    chromadb_stub = types.ModuleType("chromadb")

    class _Settings:
        def __init__(self, *args, **kwargs):
            pass

    class _PersistentClient:
        def __init__(self, *args, **kwargs):
            pass

    chromadb_stub.PersistentClient = _PersistentClient
    chromadb_stub.config = types.SimpleNamespace(Settings=_Settings)
    sys.modules["chromadb"] = chromadb_stub

from langchain_app.checks.parameter.parameter import (
    ParamCheckRow,
    _build_point_key,
    _merge_param_rows,
)


def _make_row(
    *,
    basis_code: str,
    status: str,
    point_key: str,
    cert_index: int = 1,
    param_name: str = "频率",
) -> ParamCheckRow:
    raw_row = {
        "点位": "N/A",
        "测量点": param_name,
        "KB编号": basis_code,
        "KB条目": "KB条目",
        "证书匹配项": "10 MHz",
        "范围": "10 Hz～18 GHz",
        "证书误差": "N/A",
        "允许误差": "N/A",
        "证书U": "U=1",
        "KB_U": "U=1",
        "判定": status,
        "说明": f"{basis_code}:{status}",
    }
    return ParamCheckRow(
        basis_code=basis_code,
        batch_label="Batch 1",
        batch_index=1,
        row_index=1,
        cert_index=cert_index,
        param_name=param_name,
        point_key=point_key,
        match_value="10 MHz",
        point_value="N/A",
        status=status,
        reason=f"{basis_code}:{status}",
        kb_code=basis_code,
        kb_item="KB条目",
        range_text="10 Hz～18 GHz",
        cert_error="N/A",
        limit_text="N/A",
        cert_u="U=1",
        kb_u="U=1",
        raw_row=raw_row,
    )


class ParameterMultiBasisMergeTest(unittest.TestCase):
    def test_merge_prefers_pass_over_fail(self):
        rows = [
            _make_row(basis_code="JJF1282", status="PASS", point_key="p1"),
            _make_row(basis_code="JJF1686", status="FAIL", point_key="p1"),
        ]
        merged = _merge_param_rows(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].status, "PASS")

    def test_merge_prefers_review_over_fail(self):
        rows = [
            _make_row(basis_code="JJF1282", status="REVIEW", point_key="p1"),
            _make_row(basis_code="JJF1686", status="FAIL", point_key="p1"),
        ]
        merged = _merge_param_rows(rows)
        self.assertEqual(merged[0].status, "REVIEW")

    def test_merge_all_fail_stays_fail(self):
        rows = [
            _make_row(basis_code="JJF1282", status="FAIL", point_key="p1"),
            _make_row(basis_code="JJF1686", status="FAIL", point_key="p1"),
        ]
        merged = _merge_param_rows(rows)
        self.assertEqual(merged[0].status, "FAIL")

    def test_merge_all_error_stays_error(self):
        rows = [
            _make_row(basis_code="JJF1282", status="ERROR", point_key="p1"),
            _make_row(basis_code="JJF1686", status="ERROR", point_key="p1"),
        ]
        merged = _merge_param_rows(rows)
        self.assertEqual(merged[0].status, "ERROR")

    def test_merge_fail_and_error_falls_back_to_review(self):
        rows = [
            _make_row(basis_code="JJF1282", status="FAIL", point_key="p1"),
            _make_row(basis_code="JJF1686", status="ERROR", point_key="p1"),
        ]
        merged = _merge_param_rows(rows)
        self.assertEqual(merged[0].status, "REVIEW")

    def test_build_point_key_keeps_duplicate_text_points_distinct_by_cert_index(self):
        key1 = _build_point_key(
            param={"param_name": "频率", "__cert_index": 1},
            param_name="频率",
            match_value="10 MHz",
            point_value="N/A",
            measure_value="10 MHz",
        )
        key2 = _build_point_key(
            param={"param_name": "频率", "__cert_index": 2},
            param_name="频率",
            match_value="10 MHz",
            point_value="N/A",
            measure_value="10 MHz",
        )
        self.assertNotEqual(key1, key2)


if __name__ == "__main__":
    unittest.main()
