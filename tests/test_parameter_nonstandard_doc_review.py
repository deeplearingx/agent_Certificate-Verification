import json
import sys
import types
from pathlib import Path
from unittest.mock import patch


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


from md_parser_no_llm import parse_md_to_json
from langchain_app.checks.parameter import parameter as parameter_module


def test_resolve_document_parameter_review_reason_from_parser_meta_sample():
    sample_path = Path("local_md/2GB25006390-0009.md")
    parsed = parse_md_to_json(str(sample_path))
    params = parameter_module.collect_certificate_params(parsed)

    reason = parameter_module._resolve_document_parameter_review_reason(parsed, params)

    assert reason == ""


def test_check_parameters_skips_nonstandard_document_auto_verification(tmp_path):
    payload = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        "证书编号": "TEST-001",
                        "仪器名称": "测试仪器",
                        "校准依据": ["JJF 0001"],
                    }
                }
            }
        },
        "__document_parser_meta": {
            "has_nonstandard_parameter_layout": True,
            "nonstandard_parameter_parse_sources": ["flat_text_reference_oscillator"],
            "parameter_verification_policy": "manual_review_only",
            "parameter_review_reason": (
                "参数区未按标准表格形态解析（parse_source=flat_text_reference_oscillator），"
                "为避免自动误判，建议人工核验"
            ),
        },
        "依据参数_中间数据": [
            {
                "项目名称": "2.2 开机特性",
                "测量值": "2.2 开机特性",
                "数据明细": {
                    "开机特性": "5.0×10^-11",
                    "允许误差 (Limit)": "≤1.0×10^-10",
                    "U (k=2)": "3.0×10^-12",
                },
                "__normalized_fields": {
                    "error_value": "5.0×10^-11",
                    "limit_value": "≤1.0×10^-10",
                    "cert_u": "3.0×10^-12",
                },
                "__parser_meta": {
                    "parse_source": "flat_text_reference_oscillator",
                    "section_rule": "reference_oscillator",
                    "header_rules": {"error_value": "开机特性", "cert_u": "U (k=2)"},
                    "unit_inherited": False,
                },
            }
        ],
    }
    json_path = tmp_path / "nonstandard.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with patch.object(parameter_module, "search_calibration_data", side_effect=AssertionError("should not query KB")):
        report = parameter_module.check_parameters(str(json_path))

    assert "参数核验策略: 已降级为人工核验" in report
    assert "参数自动核验已跳过" in report
    assert "待人工核验" in report
    assert "should not query KB" not in report


def test_get_parameter_contract_repairs_legacy_flat_reference_stability_unit_family():
    param = {
        "__parameter_contract": {
            "semantic_target": "reference_oscillator",
            "semantic_subtype": "frequency_stability",
            "condition_value": "1 s",
            "condition_axis": "gate_time",
            "error_value": "1.9×10^-11",
            "limit_value": "≤2.0×10^-11",
            "cert_u": "2.4×10^-12",
            "unit_family": "time",
        }
    }

    contract = parameter_module._get_parameter_contract(param)

    assert contract["unit_family"] == "frequency"


def test_extract_param_cert_u_strips_result_flag_prefix_from_legacy_json():
    param = {
        "__normalized_fields": {
            "cert_u": "P 3.0×10^-12",
        }
    }

    assert parameter_module._extract_param_cert_u(param) == "3.0×10^-12"
