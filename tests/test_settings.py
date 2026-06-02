from config.settings import AppConfig as LegacyAppConfig
from config.settings import get_app_config as legacy_get_app_config
from langchain_app.utils import AppConfig as CanonicalAppConfig
from langchain_app.utils import get_app_config as canonical_get_app_config


def test_legacy_config_exports_canonical_symbols(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))

    assert LegacyAppConfig is CanonicalAppConfig
    assert legacy_get_app_config is canonical_get_app_config

    cfg = legacy_get_app_config()
    assert isinstance(cfg, CanonicalAppConfig)
    assert cfg.root_dir == tmp_path


def test_app_config_uses_defaults_when_env_missing(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    cfg = CanonicalAppConfig.from_env()
    assert cfg.api_base == "https://api.deepseek.com/v1"
    assert cfg.model == "deepseek-v4-flash"
    assert cfg.local_pdf_dir.name == "local_pdf"
    assert cfg.parameter_semantic_auditor_mode == "live"


def test_app_config_runtime_namespace_round_trip():
    cfg = CanonicalAppConfig.from_env()
    restored = CanonicalAppConfig.from_runtime_namespace(cfg.to_runtime_namespace())
    assert restored.api_base == cfg.api_base
    assert restored.cnas_db_dir == cfg.cnas_db_dir
    assert restored.local_json_dir == cfg.local_json_dir
