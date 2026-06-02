#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块 - LangChain重构版

与原始项目 config/settings.py 完全兼容的配置管理
"""

import os
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """应用配置类 - 与原始项目完全兼容"""
    root_dir: Path
    api_key: str
    api_base: str
    model: str
    temperature: float
    max_tokens: int
    topk: int
    batch_size: int
    max_workers: int
    embed_model_path: str
    cnas_db_dir: str
    temperature_db_dir: str
    general_cycle_db_dir: str
    huawei_cycle_db_dir: str
    address_db_dir: str
    cnas_collection: str
    address_collection: str
    default_cycle: str
    use_llm_verification: bool
    use_llm_location_check: bool
    must_match_threshold: float
    optional_match_threshold: float
    llm_temperature: float
    llm_max_tokens: int
    local_pdf_dir: Path
    local_md_dir: Path
    local_json_dir: Path
    final_reports_dir: Path
    reports_dir: Path
    parameter_planner_mode: str = "live"
    parameter_planner_confidence_threshold: float = 0.85
    parameter_planner_candidate_limit: int = 20
    parameter_semantic_auditor_mode: str = "live"
    parameter_semantic_auditor_confidence_threshold: float = 0.90
    parameter_semantic_auditor_max_calls: int = 3
    parameter_semantic_auditor_candidate_limit: int = 12
    kb_capability_auditor_mode: str = "shadow"
    kb_capability_auditor_max_items: int = 2
    llm_suspicion_min_signals: int = 2

    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量加载配置"""
        root_dir = Path(os.getenv("PROJECT_ROOT", ROOT_DIR)).resolve()
        return cls(
            root_dir=root_dir,
            api_key=_env_str("DEEPSEEK_API_KEY", ""),
            api_base=_env_str("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
            model=_env_str("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            temperature=_env_float("DEEPSEEK_TEMPERATURE", 0.1),
            max_tokens=_env_int("DEEPSEEK_MAX_TOKENS", 2048),
            topk=_env_int("TOPK", 50),
            batch_size=_env_int("BATCH_SIZE", 5),
            max_workers=_env_int("MAX_WORKERS", 5),
            embed_model_path=_env_str("EMBED_MODEL_PATH", str(root_dir / "models")),
            cnas_db_dir=_env_str("CNAS_DB_DIR", str(root_dir / "vector_db" / "cnas_calibration")),
            temperature_db_dir=_env_str("TEMPERATURE_DB_DIR", str(root_dir / "vector_db" / "temperature")),
            general_cycle_db_dir=_env_str("GENERAL_CYCLE_DB_DIR", str(root_dir / "vector_db" / "general_cycle")),
            huawei_cycle_db_dir=_env_str("HUAWEI_CYCLE_DB_DIR", str(root_dir / "vector_db" / "huawei_cycle")),
            address_db_dir=_env_str("ADDRESS_DB_DIR", str(root_dir / "vector_db" / "address")),
            cnas_collection=_env_str("CNAS_COLLECTION", "calibration_data"),
            address_collection=_env_str("ADDRESS_COLLECTION", "calibration_address"),
            default_cycle=_env_str("DEFAULT_CYCLE", "12个月"),
            use_llm_verification=_env_bool("USE_LLM_VERIFICATION", True),
            use_llm_location_check=_env_bool("USE_LLM_LOCATION_CHECK", True),
            must_match_threshold=_env_float("MUST_MATCH_THRESHOLD", 0.45),
            optional_match_threshold=_env_float("OPTIONAL_MATCH_THRESHOLD", 0.45),
            llm_temperature=_env_float("LOCATION_LLM_TEMPERATURE", 0.0),
            llm_max_tokens=_env_int("LOCATION_LLM_MAX_TOKENS", 256),
            local_pdf_dir=Path(_env_str("LOCAL_PDF_DIR", str(root_dir / "local_pdf"))),
            local_md_dir=Path(_env_str("LOCAL_MD_DIR", str(root_dir / "local_md"))),
            local_json_dir=Path(_env_str("LOCAL_JSON_DIR", str(root_dir / "local_json"))),
            final_reports_dir=Path(_env_str("FINAL_REPORTS_DIR", str(root_dir / "final_reports"))),
            reports_dir=Path(_env_str("REPORTS_DIR", str(root_dir / "reports"))),
            parameter_planner_mode=_env_str("PARAMETER_PLANNER_MODE", "live"),
            parameter_planner_confidence_threshold=_env_float("PARAMETER_PLANNER_CONFIDENCE_THRESHOLD", 0.85),
            parameter_planner_candidate_limit=_env_int("PARAMETER_PLANNER_CANDIDATE_LIMIT", 20),
            parameter_semantic_auditor_mode=_env_str("PARAMETER_SEMANTIC_AUDITOR_MODE", "live"),
            parameter_semantic_auditor_confidence_threshold=_env_float("PARAMETER_SEMANTIC_AUDITOR_CONFIDENCE_THRESHOLD", 0.90),
            parameter_semantic_auditor_max_calls=_env_int("PARAMETER_SEMANTIC_AUDITOR_MAX_CALLS", 3),
            parameter_semantic_auditor_candidate_limit=_env_int("PARAMETER_SEMANTIC_AUDITOR_CANDIDATE_LIMIT", 12),
            kb_capability_auditor_mode=_env_str("KB_CAPABILITY_AUDITOR_MODE", "shadow"),
            kb_capability_auditor_max_items=_env_int("KB_CAPABILITY_AUDITOR_MAX_ITEMS", 2),
            llm_suspicion_min_signals=_env_int("LLM_SUSPICION_MIN_SIGNALS", 2),
        )

    @classmethod
    def from_runtime_namespace(cls, runtime_cfg: Any) -> "AppConfig":
        """从旧的运行时命名空间恢复 AppConfig。"""
        if isinstance(runtime_cfg, cls):
            return runtime_cfg
        if runtime_cfg is None:
            return get_app_config()

        def _get(name: str, default: Any) -> Any:
            return getattr(runtime_cfg, name, default)

        root_dir = Path(_get("ROOT_DIR", _get("root_dir", ROOT_DIR))).resolve()

        def _path(value: Any, default: Path) -> Path:
            if value in (None, ""):
                return default
            p = Path(value)
            return p if p.is_absolute() else (root_dir / p)

        return cls(
            root_dir=root_dir,
            api_key=_get("API_KEY", _get("api_key", "")),
            api_base=_get("API_BASE", _get("api_base", "https://api.deepseek.com/v1")),
            model=_get("MODEL", _get("model", "deepseek-chat")),
            temperature=float(_get("TEMPERATURE", _get("temperature", 0.1))),
            max_tokens=int(_get("MAX_TOKENS", _get("max_tokens", 2048))),
            topk=int(_get("TOPK", _get("topk", 50))),
            batch_size=int(_get("BATCH_SIZE", _get("batch_size", 5))),
            max_workers=int(_get("MAX_WORKERS", _get("max_workers", 5))),
            embed_model_path=str(_path(_get("EMBED_MODEL_PATH", _get("embed_model_path", root_dir / "models")), root_dir / "models")),
            cnas_db_dir=str(_path(_get("CNAS_DB_DIR", _get("cnas_db_dir", root_dir / "vector_db" / "cnas_calibration")), root_dir / "vector_db" / "cnas_calibration")),
            temperature_db_dir=str(_path(_get("TEMP_DB_DIR", _get("temperature_db_dir", root_dir / "vector_db" / "temperature")), root_dir / "vector_db" / "temperature")),
            general_cycle_db_dir=str(_path(_get("GENERAL_DB_DIR", _get("general_cycle_db_dir", root_dir / "vector_db" / "general_cycle")), root_dir / "vector_db" / "general_cycle")),
            huawei_cycle_db_dir=str(_path(_get("HUAWEI_DB_DIR", _get("huawei_cycle_db_dir", root_dir / "vector_db" / "huawei_cycle")), root_dir / "vector_db" / "huawei_cycle")),
            address_db_dir=str(_path(_get("ADDR_DB_DIR", _get("address_db_dir", root_dir / "vector_db" / "address")), root_dir / "vector_db" / "address")),
            cnas_collection=str(_get("CNAS_COLLECTION", _get("cnas_collection", "calibration_data"))),
            address_collection=str(_get("ADDR_COLLECTION", _get("address_collection", "calibration_address"))),
            default_cycle=str(_get("DEFAULT_CYCLE", _get("default_cycle", "12个月"))),
            use_llm_verification=_coerce_bool(_get("USE_LLM_VERIFICATION", _get("use_llm_verification", True)), True),
            use_llm_location_check=_coerce_bool(_get("USE_LLM_LOCATION_CHECK", _get("use_llm_location_check", True)), True),
            must_match_threshold=float(_get("MUST_MATCH_THRESHOLD", _get("must_match_threshold", 0.45))),
            optional_match_threshold=float(_get("OPTIONAL_MATCH_THRESHOLD", _get("optional_match_threshold", 0.45))),
            llm_temperature=float(_get("LLM_TEMPERATURE", _get("llm_temperature", 0.0))),
            llm_max_tokens=int(_get("LLM_MAX_TOKENS", _get("llm_max_tokens", 256))),
            local_pdf_dir=_path(_get("LOCAL_PDF_DIR", _get("local_pdf_dir", root_dir / "local_pdf")), root_dir / "local_pdf"),
            local_md_dir=_path(_get("LOCAL_MD_DIR", _get("local_md_dir", root_dir / "local_md")), root_dir / "local_md"),
            local_json_dir=_path(_get("LOCAL_JSON_DIR", _get("local_json_dir", root_dir / "local_json")), root_dir / "local_json"),
            final_reports_dir=_path(_get("FINAL_REPORTS_DIR", _get("final_reports_dir", root_dir / "final_reports")), root_dir / "final_reports"),
            reports_dir=_path(_get("REPORTS_DIR", _get("reports_dir", root_dir / "reports")), root_dir / "reports"),
            parameter_planner_mode=str(
                _get("PARAMETER_PLANNER_MODE", _get("parameter_planner_mode", "live"))
            ),
            parameter_planner_confidence_threshold=float(
                _get(
                    "PARAMETER_PLANNER_CONFIDENCE_THRESHOLD",
                    _get("parameter_planner_confidence_threshold", 0.85),
                )
            ),
            parameter_planner_candidate_limit=int(
                _get(
                    "PARAMETER_PLANNER_CANDIDATE_LIMIT",
                    _get("parameter_planner_candidate_limit", 20),
                )
            ),
            parameter_semantic_auditor_mode=str(
                _get(
                    "PARAMETER_SEMANTIC_AUDITOR_MODE",
                    _get("parameter_semantic_auditor_mode", "live"),
                )
            ),
            parameter_semantic_auditor_confidence_threshold=float(
                _get(
                    "PARAMETER_SEMANTIC_AUDITOR_CONFIDENCE_THRESHOLD",
                    _get("parameter_semantic_auditor_confidence_threshold", 0.90),
                )
            ),
            parameter_semantic_auditor_max_calls=int(
                _get(
                    "PARAMETER_SEMANTIC_AUDITOR_MAX_CALLS",
                    _get("parameter_semantic_auditor_max_calls", 3),
                )
            ),
            parameter_semantic_auditor_candidate_limit=int(
                _get(
                    "PARAMETER_SEMANTIC_AUDITOR_CANDIDATE_LIMIT",
                    _get("parameter_semantic_auditor_candidate_limit", 12),
                )
            ),
            kb_capability_auditor_mode=str(
                _get(
                    "KB_CAPABILITY_AUDITOR_MODE",
                    _get("kb_capability_auditor_mode", "shadow"),
                )
            ),
            kb_capability_auditor_max_items=int(
                _get(
                    "KB_CAPABILITY_AUDITOR_MAX_ITEMS",
                    _get("kb_capability_auditor_max_items", 2),
                )
            ),
            llm_suspicion_min_signals=int(
                _get(
                    "LLM_SUSPICION_MIN_SIGNALS",
                    _get("llm_suspicion_min_signals", 2),
                )
            ),
        )

    def ensure_directories(self) -> "AppConfig":
        """确保目录存在"""
        for path in [
            self.local_pdf_dir,
            self.local_md_dir,
            self.local_json_dir,
            self.final_reports_dir,
            self.reports_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        return self

    def with_overrides(self, **overrides) -> "AppConfig":
        """覆盖配置"""
        return replace(self, **overrides)

    def apply_environment(self) -> None:
        """应用到环境变量"""
        if self.api_key:
            os.environ["DEEPSEEK_API_KEY"] = self.api_key

    def to_runtime_namespace(self) -> SimpleNamespace:
        """转换为运行时命名空间"""
        def str_path(p):
            if isinstance(p, Path):
                try:
                    rel = p.relative_to(self.root_dir)
                    return str(rel)
                except:
                    return str(p)
            return str(p)

        return SimpleNamespace(
            API_KEY=self.api_key,
            API_BASE=self.api_base,
            MODEL=self.model,
            TEMPERATURE=self.temperature,
            MAX_TOKENS=self.max_tokens,
            ROOT_DIR=str(self.root_dir),
            root_dir=str(self.root_dir),
            TOPK=self.topk,
            BATCH_SIZE=self.batch_size,
            max_workers=self.max_workers,
            EMBED_MODEL_PATH=str_path(self.embed_model_path),
            DB_DIR=str_path(self.cnas_db_dir),
            TEMP_DB_DIR=str_path(self.temperature_db_dir),
            GENERAL_DB_DIR=str_path(self.general_cycle_db_dir),
            HUAWEI_DB_DIR=str_path(self.huawei_cycle_db_dir),
            CNAS_DB_DIR=str_path(self.cnas_db_dir),
            CNAS_COLLECTION=self.cnas_collection,
            COLLECTION=self.cnas_collection,
            ADDR_DB_DIR=str_path(self.address_db_dir),
            ADDR_COLLECTION=self.address_collection,
            MUST_MATCH_THRESHOLD=self.must_match_threshold,
            OPTIONAL_MATCH_THRESHOLD=self.optional_match_threshold,
            DEFAULT_CYCLE=self.default_cycle,
            USE_LLM_VERIFICATION=self.use_llm_verification,
            USE_LLM_LOCATION_CHECK=self.use_llm_location_check,
            LLM_TEMPERATURE=self.llm_temperature,
            LLM_MAX_TOKENS=self.llm_max_tokens,
            BASE_DIR=str_path(self.local_json_dir),
            OUTPUT_DIR=str_path(self.reports_dir),
            REPORTS_DIR=str_path(self.reports_dir),
            LOCAL_PDF_DIR=str_path(self.local_pdf_dir),
            LOCAL_MD_DIR=str_path(self.local_md_dir),
            LOCAL_JSON_DIR=str_path(self.local_json_dir),
            FINAL_REPORTS_DIR=str_path(self.final_reports_dir),
            PARAMETER_PLANNER_MODE=self.parameter_planner_mode,
            PARAMETER_PLANNER_CONFIDENCE_THRESHOLD=self.parameter_planner_confidence_threshold,
            PARAMETER_PLANNER_CANDIDATE_LIMIT=self.parameter_planner_candidate_limit,
            PARAMETER_SEMANTIC_AUDITOR_MODE=self.parameter_semantic_auditor_mode,
            PARAMETER_SEMANTIC_AUDITOR_CONFIDENCE_THRESHOLD=self.parameter_semantic_auditor_confidence_threshold,
            PARAMETER_SEMANTIC_AUDITOR_MAX_CALLS=self.parameter_semantic_auditor_max_calls,
            PARAMETER_SEMANTIC_AUDITOR_CANDIDATE_LIMIT=self.parameter_semantic_auditor_candidate_limit,
            KB_CAPABILITY_AUDITOR_MODE=self.kb_capability_auditor_mode,
            KB_CAPABILITY_AUDITOR_MAX_ITEMS=self.kb_capability_auditor_max_items,
            LLM_SUSPICION_MIN_SIGNALS=self.llm_suspicion_min_signals,
        )


def get_app_config() -> AppConfig:
    """获取应用配置"""
    return AppConfig.from_env().ensure_directories()


def coerce_app_config(cfg: Optional[Any]) -> AppConfig:
    """将 AppConfig 或旧 runtime namespace 统一为 AppConfig。"""
    if isinstance(cfg, AppConfig):
        return cfg
    if cfg is None:
        return get_app_config()
    return AppConfig.from_runtime_namespace(cfg).ensure_directories()
