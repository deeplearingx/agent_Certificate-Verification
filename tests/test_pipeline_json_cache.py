import json
from pathlib import Path

from langchain_app.checks.parameter.contracts import parameter_contract_schema_version
from langchain_app.services.md_parser_pipeline import md_parser_pipeline_signature
from langchain_app.services.parsing import json_cache_needs_refresh


TMP_DIR = Path("tests/.tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)


def _wrap_cache_payload(rows):
    version = parameter_contract_schema_version()
    patched_rows = []
    for row in rows:
        row_copy = dict(row)
        row_copy.setdefault("schema_version", version)
        row_copy.setdefault("__parameter_contract", {"schema_version": version})
        patched_rows.append(row_copy)
    return {
        "__parameter_contract_schema_version": version,
        "__md_parser_pipeline_signature": md_parser_pipeline_signature(),
        "依据参数_中间数据": patched_rows,
    }


def test_json_cache_needs_refresh_for_stale_frequency_rows():
    stale = _wrap_cache_payload([
            {
                "测量值": "4 频率测量误差(Frequency Measurement Error)",
                "数据明细": {
                    "通道 (Channel)": "10.0000000",
                    "标准值 (Reference)": "10.0000000",
                    "指示值 (Indicated)": "0.0000",
                },
            }
        ])
    path = TMP_DIR / "stale_pipeline_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True


def test_json_cache_keeps_aligned_frequency_rows():
    fresh = _wrap_cache_payload([
            {
                "测量值": "4 频率测量误差(Frequency Measurement Error)",
                "数据明细": {
                    "通道 (Channel)": "1",
                    "标准值 (Reference)": "10.0000000 MHz",
                    "指示值 (Indicated)": "10.0000000 MHz",
                    "误差 (Error)": "0.0000 kHz",
                },
            }
        ])
    path = TMP_DIR / "fresh_pipeline_cache.json"
    path.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is False


def test_json_cache_needs_refresh_for_stale_motion_rows():
    stale = _wrap_cache_payload([
            {
                "测量值": "3.3.2 加速度(Accelerated Speed)",
                "数据明细": {
                    "标称值 (Nominal)": "36000",
                    "标准值 (Reference)": "36000.005",
                    "误差 (Error)": "-0.005",
                    "U (k=2)": "0.30",
                },
                "__parser_meta": {
                    "unit_inherited": False,
                },
            }
        ])
    path = TMP_DIR / "stale_motion_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True


def test_json_cache_keeps_fresh_motion_rows():
    fresh = _wrap_cache_payload([
            {
                "测量值": "3.3.2 加速度(Accelerated Speed)",
                "数据明细": {
                    "标称值 (Nominal)": "36000 m/s2",
                    "标准值 (Reference)": "36000.005 m/s2",
                    "误差 (Error)": "-0.005 m/s2",
                    "U (k=2)": "0.30 m/s2",
                },
                "__parser_meta": {
                    "unit_inherited": True,
                },
            }
        ])
    path = TMP_DIR / "fresh_motion_cache.json"
    path.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is False


def test_json_cache_needs_refresh_for_cross_labeled_meta_fields():
    stale = {
        "__parameter_contract_schema_version": parameter_contract_schema_version(),
        "__md_parser_pipeline_signature": md_parser_pipeline_signature(),
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        "委托单位": "委托单位： 元器件检测中心 委托方地址： 广东省广州市增城区朱村街朱村大道西78号",
                        "制造商": "机身号： BD190K00000015330033",
                    }
                }
            }
        },
        "依据参数_中间数据": [{
            "测量值": "placeholder",
            "数据明细": {"值": "1"},
            "schema_version": parameter_contract_schema_version(),
            "__parameter_contract": {"schema_version": parameter_contract_schema_version()},
        }],
    }
    path = TMP_DIR / "stale_meta_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True


def test_json_cache_needs_refresh_for_stale_signal_quality_condition_frequency_rows():
    stale = _wrap_cache_payload([
            {
                "测量值": "7 信号质量(Signal Quality)",
                "__normalized_fields": {
                    "measure_value": "2491.75 MHz",
                    "reference_value": "4.22 %",
                    "cert_u": "0.80 %",
                },
                "__parser_meta": {
                    "section_rule": "modulation_quality",
                },
                "数据明细": {
                    "频率(Frequency)": "2491.75 MHz",
                    "参数(Parameter)": "EVM",
                },
            }
        ])
    path = TMP_DIR / "stale_signal_quality_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True


def test_json_cache_needs_refresh_for_missing_contract_schema_version():
    stale = {
        "依据参数_中间数据": [
            {
                "测量值": "placeholder",
                "数据明细": {"值": "1"},
            }
        ]
    }
    path = TMP_DIR / "missing_contract_schema_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True


def test_json_cache_needs_refresh_for_missing_parser_pipeline_signature():
    stale = {
        "__parameter_contract_schema_version": parameter_contract_schema_version(),
        "依据参数_中间数据": [
            {
                "测量值": "placeholder",
                "数据明细": {"值": "1"},
                "schema_version": parameter_contract_schema_version(),
                "__parameter_contract": {"schema_version": parameter_contract_schema_version()},
            }
        ],
    }
    path = TMP_DIR / "missing_parser_pipeline_signature_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True


def test_json_cache_needs_refresh_for_stale_parser_pipeline_signature():
    stale = _wrap_cache_payload([
        {
            "测量值": "placeholder",
            "数据明细": {"值": "1"},
        }
    ])
    stale["__md_parser_pipeline_signature"] = "deadbeef0000"
    path = TMP_DIR / "stale_parser_pipeline_signature_cache.json"
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    assert json_cache_needs_refresh(path) is True
