import json

from langchain_core.documents import Document

from langchain_app.checks import environment as environment_module


class _StubTempService:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def search_temperature_requirements(self, instrument_name, criterion=None, k=5):
        self.calls.append(
            {
                "instrument_name": instrument_name,
                "criterion": criterion,
                "k": k,
            }
        )
        return self.docs


def test_environment_check_skips_llm_when_temperature_index_only_returns_blank_rows(tmp_path, monkeypatch):
    json_path = tmp_path / "sample.json"
    payload = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        "仪器名称": "高稳定石英晶体频率标准",
                        "温度": "19.6℃",
                        "相对湿度": "47%",
                        "校准依据": ["JJF 2090-2023"],
                    }
                }
            }
        }
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    docs = [
        Document(
            page_content="仪器名称 ，依据编号 ，依据名称 ，温度要求 ，认可组织 ，相对湿度要求 ，最大温度变化范围",
            metadata={
                "INSTRUMENT_NAME": "",
                "FILE_CODE": "",
                "FILE_NAME": "",
                "温度要求": "",
                "相对湿度要求": "",
                "最大温度变化范围": "",
                "认可组织": "",
            },
        )
    ]
    stub = _StubTempService(docs)

    monkeypatch.setattr(environment_module, "create_temperature_retrieval_service", lambda cfg: stub)
    monkeypatch.setattr(
        environment_module,
        "verify_with_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    report = environment_module.check_environment(str(json_path))

    assert "温度环境知识库未返回有效记录" in report
    assert "20±5" not in report
    assert stub.calls == [
        {
            "instrument_name": "JJF 2090-2023 广州实验室",
            "criterion": None,
            "k": 50,
        }
    ]


def test_environment_check_filters_out_non_guangzhou_hits_before_llm(tmp_path, monkeypatch):
    json_path = tmp_path / "sample.json"
    payload = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": {
                        "仪器名称": "GPS时钟接收机",
                        "温度": "19.7℃",
                        "相对湿度": "47%",
                        "校准依据": ["JJF 1957-2021"],
                    }
                }
            }
        }
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    docs = [
        Document(
            page_content="光源 JJG 958-2000",
            metadata={
                "INSTRUMENT_NAME": "光源",
                "FILE_CODE": "JJG 958",
                "FILE_NAME": "JJG 958-2000 光传输用稳定光源检定规程",
                "温度要求": "15℃～25℃",
                "相对湿度要求": "≤75%",
                "最大温度变化范围": "温度变化不超过±2℃",
                "认可组织": "",
            },
        )
    ]
    stub = _StubTempService(docs)

    monkeypatch.setattr(environment_module, "create_temperature_retrieval_service", lambda cfg: stub)
    monkeypatch.setattr(
        environment_module,
        "verify_with_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    report = environment_module.check_environment(str(json_path))

    assert "温度环境知识库未返回有效记录" in report
    assert "光源" not in report
    assert stub.calls == [
        {
            "instrument_name": "JJF 1957-2021 广州实验室",
            "criterion": None,
            "k": 50,
        }
    ]
