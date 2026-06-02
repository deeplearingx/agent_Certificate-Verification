#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph pipeline that reproduces the original verification flow inside langchain_app.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable, Optional

from langchain_app.core.embedding_loader import load_sentence_transformer
from langchain_app.core.report_generator import build_verification_report_header
from langchain_app.graph import create_initial_state, run_verification_graph
from langchain_app.services.parsing import (
    json_cache_needs_refresh as json_cache_needs_refresh_service,
    pdf_to_md_first_step as pdf_to_md_first_step_service,
)
from langchain_app.utils.config import AppConfig


@dataclass
class PipelineHooks:
    set_status: Optional[Callable[[str], None]] = None
    set_progress: Optional[Callable[[int], None]] = None
    info: Optional[Callable[[str], None]] = None
    warning: Optional[Callable[[str], None]] = None
    error: Optional[Callable[[str], None]] = None
    success: Optional[Callable[[str], None]] = None

    def emit_status(self, message: str) -> None:
        if self.set_status:
            self.set_status(message)

    def emit_progress(self, value: int) -> None:
        if self.set_progress:
            self.set_progress(value)

    def emit_info(self, message: str) -> None:
        if self.info:
            self.info(message)

    def emit_warning(self, message: str) -> None:
        if self.warning:
            self.warning(message)

    def emit_error(self, message: str) -> None:
        if self.error:
            self.error(message)

    def emit_success(self, message: str) -> None:
        if self.success:
            self.success(message)


@dataclass
class SentenceTransformerAdapter:
    """Wrap SentenceTransformer with the LangChain embedding interface."""

    model: Any

    def embed_documents(self, texts):
        return self.model.encode(list(texts), convert_to_numpy=True).tolist()

    def embed_query(self, text):
        return self.model.encode(text, convert_to_numpy=True).tolist()


def load_shared_embedder(model_path: str) -> Any:
    try:
        import sentence_transformers  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("sentence_transformers is required to load the shared embedder") from exc

    model_path_obj = Path(model_path)
    if model_path_obj.exists():
        return SentenceTransformerAdapter(load_sentence_transformer(str(model_path_obj)))

    local_models = Path(__file__).resolve().parents[2] / "models"
    if local_models.exists():
        return SentenceTransformerAdapter(
            load_sentence_transformer(str(local_models), offline=True)
        )

    return SentenceTransformerAdapter(load_sentence_transformer(model_path))


def pdf_to_md_first_step(
    pdf_path: Path,
    config: AppConfig,
    hooks: Optional[PipelineHooks],
    stop_event,
    lang: str = "ch",
):
    return pdf_to_md_first_step_service(pdf_path, config, hooks or PipelineHooks(), stop_event, lang=lang)


def json_cache_needs_refresh(json_path: Path) -> bool:
    return json_cache_needs_refresh_service(json_path)


def _build_fallback_report(final_state, config: AppConfig) -> Optional[str]:
    sections = list(final_state.report_sections or [])
    if not sections:
        for result in (
            final_state.integrity_result,
            final_state.environment_result,
            final_state.location_result,
            final_state.cycle_result,
            final_state.parameter_result,
        ):
            if result:
                sections.append(str(result).strip())

    if final_state.errors:
        sections.append(
            "## 流程异常\n"
            + "\n".join(f"- {message}" for message in final_state.errors if message)
        )

    if not sections:
        return None

    report = build_verification_report_header(
        source_name=Path(final_state.source_pdf_path).name if final_state.source_pdf_path else "",
        verified_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        model=getattr(config, "model", ""),
        temperature=getattr(config, "temperature", 0.0),
        topk=getattr(config, "topk", 3),
    )
    for idx, section in enumerate(sections):
        report.add_section(section, prepend_divider=idx > 0)
    return report.render()


def run_verification(
    pdf_file_path: Path,
    config: AppConfig,
    hooks: Optional[PipelineHooks] = None,
    stop_event=None,
    embedder: Optional[Any] = None,
    llm_client: Optional[Any] = None,
) -> Optional[str]:
    """
    Run the LangGraph verification flow and return the final report.
    """
    hooks = hooks or PipelineHooks()
    config.apply_environment()

    shared_embedder = embedder
    shared_llm_client = llm_client
    if shared_llm_client is None:
        try:
            from langchain_app.core import create_llm_client

            shared_llm_client = create_llm_client(config)
        except Exception:
            shared_llm_client = None

    initial_state = create_initial_state(
        pdf_path=str(pdf_file_path),
        config=config,
        embedder=shared_embedder,
        llm_client=shared_llm_client,
        hooks=hooks,
        stop_event=stop_event,
    )

    final_state = run_verification_graph(initial_state)
    if final_state.final_report:
        return final_state.final_report

    fallback_report = _build_fallback_report(final_state, config)
    if fallback_report:
        hooks.emit_warning("Primary flow returned no final report; fallback report assembled")
        final_state.final_report = fallback_report
        return fallback_report

    return None
