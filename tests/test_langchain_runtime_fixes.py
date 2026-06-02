from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest
from pydantic import BaseModel

from langchain_app.agents.verification_agent import VerificationAgent
from langchain_app.checks.cycle import verify_cycle_with_llm
from langchain_app.checks.location import is_specific_location, llm_is_specific_location
from langchain_app.core import LLMInvocationError
from langchain_app.core.pipeline import run_verification
from langchain_app.core.llm_client import LLMClient
from langchain_app.graph.nodes.location_check import location_check_node
from langchain_app.graph.state import VerificationState, create_initial_state
from langchain_app.tools import example_tools
from langchain_app.utils import AppConfig


def build_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        root_dir=tmp_path,
        api_key="test-key",
        api_base="https://api.example.com",
        model="deepseek-chat",
        temperature=0.1,
        max_tokens=1024,
        topk=12,
        batch_size=4,
        max_workers=2,
        embed_model_path=str(tmp_path / "models"),
        cnas_db_dir=str(tmp_path / "vector_db" / "cnas_calibration"),
        temperature_db_dir=str(tmp_path / "vector_db" / "temperature"),
        general_cycle_db_dir=str(tmp_path / "vector_db" / "general_cycle"),
        huawei_cycle_db_dir=str(tmp_path / "vector_db" / "huawei_cycle"),
        address_db_dir=str(tmp_path / "vector_db" / "address"),
        cnas_collection="calibration_data",
        address_collection="calibration_address",
        default_cycle="12个月",
        use_llm_verification=True,
        use_llm_location_check=True,
        must_match_threshold=0.45,
        optional_match_threshold=0.4,
        llm_temperature=0.0,
        llm_max_tokens=256,
        local_pdf_dir=tmp_path / "local_pdf",
        local_md_dir=tmp_path / "local_md",
        local_json_dir=tmp_path / "local_json",
        final_reports_dir=tmp_path / "final_reports",
        reports_dir=tmp_path / "reports",
    )


def test_runtime_namespace_round_trip(tmp_path):
    config = build_config(tmp_path)

    restored = AppConfig.from_runtime_namespace(config.to_runtime_namespace())

    assert restored.root_dir == config.root_dir
    assert restored.default_cycle == config.default_cycle
    assert restored.reports_dir == config.reports_dir
    assert restored.address_db_dir == config.address_db_dir
    assert restored.parameter_planner_mode == config.parameter_planner_mode
    assert restored.parameter_planner_candidate_limit == config.parameter_planner_candidate_limit


def test_create_initial_state_coerces_legacy_runtime_namespace(tmp_path):
    config = build_config(tmp_path)
    runtime_cfg = config.to_runtime_namespace()

    state = create_initial_state(pdf_path="sample.pdf", runtime_cfg=runtime_cfg)

    assert isinstance(state.config, AppConfig)
    assert state.config.root_dir == config.root_dir
    assert state.runtime_cfg is runtime_cfg


def test_legacy_pipeline_module_reexports_canonical_functions():
    legacy_pipeline = importlib.import_module("core.pipeline")
    canonical_pipeline = importlib.import_module("langchain_app.core.pipeline")

    assert legacy_pipeline.PipelineHooks is canonical_pipeline.PipelineHooks
    assert legacy_pipeline.run_verification is canonical_pipeline.run_verification
    assert legacy_pipeline.load_shared_embedder is canonical_pipeline.load_shared_embedder
    assert legacy_pipeline.pdf_to_md_first_step is canonical_pipeline.pdf_to_md_first_step
    assert legacy_pipeline.json_cache_needs_refresh is canonical_pipeline.json_cache_needs_refresh


def test_active_entries_use_canonical_runtime_exports():
    pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    service_api = importlib.import_module("api.app")
    cli_entry = importlib.import_module("main_pipeline")
    from langchain_app.core import PipelineHooks, load_shared_embedder, run_verification
    from langchain_app.utils import AppConfig as CanonicalAppConfig
    from langchain_app.utils import get_app_config

    assert service_api.AppConfig is CanonicalAppConfig
    assert service_api.get_app_config is get_app_config
    assert service_api.PipelineHooks is PipelineHooks
    assert service_api.load_shared_embedder is load_shared_embedder
    assert service_api.run_verification is run_verification

    assert cli_entry.get_app_config is get_app_config
    assert cli_entry.PipelineHooks is PipelineHooks
    assert cli_entry.run_verification is run_verification


@pytest.mark.parametrize(
    "tool_func, checker_path, needs_embedder",
    [
        (getattr(example_tools.location_check, "func", example_tools.location_check), "langchain_app.checks.location.check_location", True),
        (getattr(example_tools.cycle_check, "func", example_tools.cycle_check), "langchain_app.checks.cycle.check_cycle_reasonableness", False),
        (getattr(example_tools.parameter_check, "func", example_tools.parameter_check), "langchain_app.checks.parameter.run_llm_mode", True),
    ],
)
def test_tools_pass_appconfig_directly(monkeypatch, tmp_path, tool_func, checker_path, needs_embedder):
    config = build_config(tmp_path)
    monkeypatch.setattr("langchain_app.utils.get_app_config", lambda: config)
    monkeypatch.setattr("langchain_app.core.load_shared_embedder", lambda path: object())

    seen = {}

    def fake_checker(json_path, cfg, *args, **kwargs):
        seen["cfg"] = cfg
        seen["json_path"] = json_path
        return "ok"

    monkeypatch.setattr(checker_path, fake_checker)

    json_content = (
        '{"properties":{"证书列表":{"items":{"properties":{'
        '"校准依据":["JJG 1234-2020"],"校准地点":"A座203室",'
        '"温度":"20℃","相对湿度":"50%"'
        '}}}}}'
    )

    result = tool_func(json_content)

    assert result == "ok"
    assert seen["cfg"] is config
    assert seen["json_path"]


def test_location_node_propagates_shared_llm_client(monkeypatch, tmp_path):
    config = build_config(tmp_path)
    sentinel_llm = object()
    seen = {}

    def fake_check_location(json_path, cfg, stop_event=None, embedder_obj=None, llm_client=None):
        seen["llm_client"] = llm_client
        seen["cfg"] = cfg
        return "location-ok"

    monkeypatch.setattr("langchain_app.graph.nodes.location_check.check_location", fake_check_location)

    state = VerificationState(
        json_path=str(tmp_path / "doc.json"),
        config=config,
        llm_client=sentinel_llm,
    )

    updated = location_check_node(state)

    assert updated.location_result == "location-ok"
    assert seen["llm_client"] is sentinel_llm
    assert isinstance(seen["cfg"], AppConfig)


def test_verification_agent_arun_verification_uses_thread(monkeypatch):
    agent = VerificationAgent(llm=object(), tools=[])
    monkeypatch.setattr(VerificationAgent, "run_verification", lambda self, pdf_path: f"done:{pdf_path}")

    result = asyncio.run(agent.arun_verification("sample.pdf"))

    assert result == "done:sample.pdf"


def test_llm_client_raises_on_invoke_failures():
    client = LLMClient.__new__(LLMClient)

    class _BadChain:
        def invoke(self, messages):
            raise ValueError("boom")

        async def ainvoke(self, messages):
            raise ValueError("boom")

    class _FakeLLM:
        def __or__(self, parser):
            return _BadChain()

        def with_structured_output(self, output_model):
            return _BadChain()

    class _OutModel:
        pass

    client.llm = _FakeLLM()

    with pytest.raises(LLMInvocationError):
        client.invoke_messages([])

    with pytest.raises(LLMInvocationError):
        asyncio.run(client.ainvoke_messages([]))

    with pytest.raises(LLMInvocationError):
        client.invoke_structured("prompt", _OutModel)


def test_llm_client_invoke_structured_falls_back_to_json_text_when_tool_choice_unavailable():
    client = LLMClient.__new__(LLMClient)

    class _OutModel(BaseModel):
        action: str
        confidence: float

    class _StructuredFail:
        def invoke(self, messages):
            raise ValueError("deepseek-reasoner does not support this tool_choice")

    class _TextChain:
        def invoke(self, messages):
            return '{"action":"abstain","confidence":0.0}'

    class _FakeLLM:
        def with_structured_output(self, output_model):
            return _StructuredFail()

        def __or__(self, parser):
            return _TextChain()

    client.llm = _FakeLLM()

    result = client.invoke_structured("prompt", _OutModel)

    assert result.action == "abstain"
    assert result.confidence == 0.0


def test_run_verification_falls_back_to_report_sections(monkeypatch, tmp_path):
    config = build_config(tmp_path)
    pdf_path = config.local_pdf_dir / "sample.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4")
    config.apply_environment()

    sentinel_state = VerificationState(
        source_pdf_path=str(pdf_path),
        config=config,
        report_sections=["# [终止] 核验终止报告\n> stop here"],
        should_stop=True,
    )

    monkeypatch.setattr("langchain_app.core.pipeline.run_verification_graph", lambda state: sentinel_state)
    monkeypatch.setattr("langchain_app.core.create_llm_client", lambda cfg: None)

    report = run_verification(pdf_path, config, hooks=None, llm_client=None)

    assert report is not None
    assert "# 全流程智能核验报告" in report
    assert "# [终止] 核验终止报告" in report


def test_run_verification_falls_back_to_integrity_result_when_final_report_missing(monkeypatch, tmp_path):
    config = build_config(tmp_path)
    pdf_path = config.local_pdf_dir / "sample.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4")
    config.apply_environment()

    sentinel_state = VerificationState(
        source_pdf_path=str(pdf_path),
        config=config,
        integrity_result="# [终止] 核验终止报告\n> integrity stop",
        should_stop=True,
    )

    monkeypatch.setattr("langchain_app.core.pipeline.run_verification_graph", lambda state: sentinel_state)
    monkeypatch.setattr("langchain_app.core.create_llm_client", lambda cfg: None)

    report = run_verification(pdf_path, config, hooks=None, llm_client=None)

    assert report is not None
    assert "# 全流程智能核验报告" in report
    assert "integrity stop" in report


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/",
        "https://api.deepseek.com/v1",
    ],
)
def test_llm_client_prefers_chat_deepseek_for_official_deepseek_endpoint(monkeypatch, base_url):
    created = {}

    class _FakeChatDeepSeek:
        def __init__(self, **kwargs):
            created["provider"] = "deepseek"
            created["kwargs"] = kwargs

    fake_module = types.ModuleType("langchain_deepseek")
    fake_module.ChatDeepSeek = _FakeChatDeepSeek
    monkeypatch.setitem(sys.modules, "langchain_deepseek", fake_module)

    client = LLMClient(
        api_key="test-key",
        base_url=base_url,
        model="deepseek-chat",
        temperature=0.2,
        max_tokens=256,
    )

    assert created["provider"] == "deepseek"
    assert client.provider_name == "deepseek"
    assert created["kwargs"]["model"] == "deepseek-chat"
    assert created["kwargs"]["api_key"] == "test-key"


def test_llm_client_falls_back_to_chat_openai_when_langchain_deepseek_missing(monkeypatch):
    created = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            created["provider"] = "openai"
            created["kwargs"] = kwargs

    fake_openai_module = types.ModuleType("langchain_openai")
    fake_openai_module.ChatOpenAI = _FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai_module)
    monkeypatch.delitem(sys.modules, "langchain_deepseek", raising=False)

    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "langchain_deepseek":
            raise ModuleNotFoundError("No module named 'langchain_deepseek'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    client = LLMClient(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        temperature=0.0,
        max_tokens=128,
    )

    assert created["provider"] == "openai"
    assert client.provider_name == "openai-compatible"
    assert created["kwargs"]["openai_api_base"] == "https://api.deepseek.com/v1"


def test_cycle_llm_uses_structured_output_first():
    class _StructuredResult:
        def __init__(self):
            self.find = 1
            self.reason = "匹配成功"
            self.table = "| a | b |"

        def model_dump(self):
            return {
                "find": self.find,
                "reason": self.reason,
                "table": self.table,
            }

    class _FakeClient:
        def invoke_structured(self, user_prompt, output_model, system_prompt=None):
            assert output_model.__name__ == "CycleLLMResult"
            return _StructuredResult()

        def invoke_text(self, user_prompt, system_prompt=None):
            raise AssertionError("structured path should be used before raw text fallback")

    result = verify_cycle_with_llm(
        _FakeClient(),
        "客户A",
        "仪器A",
        "JJF 2196-2025",
        "12个月",
        [{"仪器名称": "仪器A", "依据": "JJF 2196-2025", "建议校准周期": "12个月", "来源": "通用数据库"}],
    )

    assert result["find"] == 1
    assert result["reason"] == "匹配成功"
    assert result["table"] == "| a | b |"


def test_cycle_llm_falls_back_to_raw_json_when_structured_fails():
    class _FakeClient:
        def invoke_structured(self, user_prompt, output_model, system_prompt=None):
            raise ValueError("structured output unavailable")

        def invoke_text(self, user_prompt, system_prompt=None):
            return '{"find": 1, "reason": "fallback ok", "table": ""}'

    result = verify_cycle_with_llm(
        _FakeClient(),
        "客户A",
        "仪器A",
        "JJF 2196-2025",
        "12个月",
        [{"仪器名称": "仪器A", "依据": "JJF 2196-2025", "建议校准周期": "12个月", "来源": "通用数据库"}],
    )

    assert result["find"] == 1
    assert result["reason"] == "fallback ok"


def test_location_llm_uses_structured_output_first():
    class _StructuredResult:
        def model_dump(self):
            return {
                "is_specific": True,
                "reason": "包含房间号",
                "signals": ["房间", "编号"],
            }

    class _FakeClient:
        def invoke_structured(self, user_prompt, output_model, system_prompt=None):
            assert output_model.__name__ == "LocationSpecificityResult"
            return _StructuredResult()

        def invoke_text(self, user_prompt, system_prompt=None):
            raise AssertionError("structured path should be used before raw text fallback")

    result = llm_is_specific_location(_FakeClient(), "A座203室")

    assert result["is_specific"] is True
    assert result["reason"] == "包含房间号"
    assert result["signals"] == ["房间", "编号"]


def test_location_llm_falls_back_to_raw_json_when_structured_fails():
    class _FakeClient:
        def invoke_structured(self, user_prompt, output_model, system_prompt=None):
            raise ValueError("structured output unavailable")

        def invoke_text(self, user_prompt, system_prompt=None):
            return '{"is_specific": true, "reason": "fallback ok", "signals": ["实验室"]}'

    result = llm_is_specific_location(_FakeClient(), "恒温恒湿实验室")

    assert result["is_specific"] is True
    assert result["reason"] == "fallback ok"
    assert result["signals"] == ["实验室"]


def test_location_regex_returns_false_for_non_specific_place():
    assert is_specific_location("深圳市南山区科技园") is False
