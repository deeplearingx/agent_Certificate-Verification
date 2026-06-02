from types import SimpleNamespace

from langchain_app.checks.parameter import retrieval


def test_search_calibration_data_backfills_chinese_metadata_fields(monkeypatch):
    doc_text = (
        "仪器名称：石英晶体频率标准。"
        "校准依据：石英晶体频率标准校准规范 JJF 2090。"
        "规程代号：JJF2090。"
        "被测量：频率。"
        "测量范围：相对频率偏差：±(1×10⁻⁸～1×10⁻¹⁰)。"
        "不确定度：Urel=1.6×10⁻¹²。"
    )
    metadata = {
        "file_code": "JJF2090",
        "standard_name": "石英晶体频率标准校准规范 JJF 2090",
        "仪器名称": "石英晶体频率标准",
        "校准依据": "石英晶体频率标准校准规范 JJF 2090",
        "被测量": "频率",
        "测量范围": "相对频率偏差：±(1×10⁻⁸～1×10⁻¹⁰)",
        "不确定度": "Urel=1.6×10⁻¹²",
    }

    monkeypatch.setattr(retrieval, "_load_raw_records", lambda cfg: [(doc_text, metadata)])

    cfg = SimpleNamespace()
    rows = retrieval.search_calibration_data(
        query_text="JJF 2090 频率 相对频率偏差",
        cfg=cfg,
        instrument_name="石英晶体频率标准",
        topk=5,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["measured"] == "频率"
    assert row["measure_range_text"] == "相对频率偏差：±(1×10⁻⁸～1×10⁻¹⁰)"
    assert row["u_text"] == "Urel=1.6×10⁻¹²"
    assert row["FILE_CODE"] == "JJF2090"
    assert row["校准依据"] == "石英晶体频率标准校准规范 JJF 2090"
