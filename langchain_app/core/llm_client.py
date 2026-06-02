#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM client wrapper for the LangChain-based app.
"""

from __future__ import annotations

import os
import json
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Type

from pydantic import BaseModel


_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


class LLMInvocationError(RuntimeError):
    """Raised when the wrapped LLM call fails."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "",
        error_stage: str = "",
        error_type: str = "",
        error_message: str = "",
    ):
        super().__init__(message)
        self.error_code = error_code
        self.error_stage = error_stage
        self.error_type = error_type
        self.error_message = error_message or message


def _short_exception_message(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    return text[:300]


def describe_llm_exception(exc: BaseException, *, default_stage: str = "request_invoke") -> Dict[str, str]:
    error_type = type(exc).__name__
    if isinstance(exc, LLMInvocationError):
        return {
            "error_code": exc.error_code or error_type or "LLMInvocationError",
            "error_stage": exc.error_stage or default_stage,
            "error_type": exc.error_type or error_type,
            "error_message": exc.error_message or _short_exception_message(exc),
        }

    message = _short_exception_message(exc)
    lower = f"{error_type} {message}".lower()
    error_stage = default_stage
    error_code = error_type or "LLMInvocationError"

    if isinstance(exc, ModuleNotFoundError) or "no module named" in lower:
        error_stage = "client_init"
        error_code = "DependencyMissing"
    elif any(token in lower for token in ("authentication", "unauthorized", "invalid api key", "api key", "401", "permission denied", "forbidden")):
        error_code = "AuthenticationError"
    elif any(token in lower for token in ("timeout", "timed out", "max retries", "connection", "dns", "network", "proxy", "unreachable", "connecterror", "connectionerror")):
        error_code = "NetworkError"
    elif any(token in lower for token in ("validationerror", "schema", "structured", "json", "parse", "parser")):
        error_stage = "structured_parse"
        error_code = "StructuredParseError"
    elif any(token in lower for token in ("empty response", "no response", "empty output", "null response")):
        error_stage = "structured_parse"
        error_code = "EmptyResponseError"

    return {
        "error_code": error_code,
        "error_stage": error_stage,
        "error_type": error_type,
        "error_message": message or error_type,
    }


def _is_official_deepseek_base_url(base_url: str) -> bool:
    text = (base_url or "").strip().lower()
    if not text:
        return False
    normalized = text.rstrip("/")
    return normalized == "https://api.deepseek.com" or normalized.startswith("https://api.deepseek.com/")


def _is_deepseek_model(model: str) -> bool:
    return (model or "").strip().lower().startswith("deepseek")


def _should_fallback_structured_output(exc: BaseException) -> bool:
    lower = f"{type(exc).__name__} {exc}".lower()
    return (
        "response_format type is unavailable" in lower
        or "does not support this tool_choice" in lower
        or "tool_choice" in lower and "invalid_request_error" in lower
    )


def _extract_json_payload(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
        stripped = stripped.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    match = re.search(r"(\{.*\}|\[.*\])", stripped, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


@contextmanager
def _temporarily_disable_proxy_environment() -> Iterator[None]:
    """Temporarily remove proxy variables while constructing the client."""
    original = {key: os.environ[key] for key in _PROXY_ENV_KEYS if key in os.environ}
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(original)


class LLMClient:
    """Unified LLM client wrapper."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        config: Optional[Any] = None,
    ):
        if config is not None:
            api_key = config.api_key
            base_url = config.api_base
            model = config.model
            temperature = config.temperature
            max_tokens = config.max_tokens

        raw_api_key = api_key
        api_key = api_key or ""
        base_url = base_url or "https://api.deepseek.com/v1"
        model = model or "deepseek-chat"
        self.provider_name = "openai-compatible"

        prefer_chat_deepseek = _is_deepseek_model(model) and _is_official_deepseek_base_url(base_url)
        if prefer_chat_deepseek:
            try:
                from langchain_deepseek import ChatDeepSeek

                client_kwargs = {
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                # Let ChatDeepSeek read DEEPSEEK_API_KEY from the environment when
                # the caller did not explicitly pass a non-empty key.
                if raw_api_key:
                    client_kwargs["api_key"] = raw_api_key
                with _temporarily_disable_proxy_environment():
                    self.llm = ChatDeepSeek(**client_kwargs)
                self.provider_name = "deepseek"
                return
            except ModuleNotFoundError:
                # Fall back to the OpenAI-compatible wrapper when the dedicated
                # DeepSeek package is not installed in the target runtime.
                pass

        try:
            from langchain_openai import ChatOpenAI
        except ModuleNotFoundError as exc:
            if prefer_chat_deepseek:
                raise ModuleNotFoundError(
                    "langchain_deepseek is preferred for deepseek-chat on the official DeepSeek endpoint, "
                    "and langchain_openai is required as the compatibility fallback"
                ) from exc
            raise ModuleNotFoundError(
                "langchain_openai is required to instantiate LLMClient"
            ) from exc

        client_kwargs = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "openai_api_key": api_key,
            "openai_api_base": base_url,
            "openai_proxy": "",
        }
        with _temporarily_disable_proxy_environment():
            try:
                self.llm = ChatOpenAI(**client_kwargs)
            except TypeError:
                client_kwargs.pop("openai_proxy", None)
                self.llm = ChatOpenAI(**client_kwargs)

    def invoke_text(self, user_prompt: str, system_prompt: Optional[str] = None) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: List[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_prompt))
        return self.invoke_messages(messages)

    def invoke_messages(self, messages: List[Any]) -> str:
        from langchain_core.output_parsers import StrOutputParser

        chain = self.llm | StrOutputParser()
        try:
            return chain.invoke(messages)
        except Exception as exc:
            details = describe_llm_exception(exc)
            raise LLMInvocationError(
                f"Error generating response: {details['error_message']}",
                error_code=details["error_code"],
                error_stage=details["error_stage"],
                error_type=details["error_type"],
                error_message=details["error_message"],
            ) from exc

    async def ainvoke_messages(self, messages: List[Any]) -> str:
        from langchain_core.output_parsers import StrOutputParser

        chain = self.llm | StrOutputParser()
        try:
            return await chain.ainvoke(messages)
        except Exception as exc:
            details = describe_llm_exception(exc)
            raise LLMInvocationError(
                f"Error generating response: {details['error_message']}",
                error_code=details["error_code"],
                error_stage=details["error_stage"],
                error_type=details["error_type"],
                error_message=details["error_message"],
            ) from exc

    def invoke_structured(
        self,
        user_prompt: str,
        output_model: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: List[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_prompt))

        try:
            model_with_structure = self.llm.with_structured_output(output_model)
            return model_with_structure.invoke(messages)
        except Exception as exc:
            if _should_fallback_structured_output(exc):
                from langchain_core.messages import HumanMessage

                schema = output_model.model_json_schema()
                fallback_messages = list(messages)
                fallback_messages.append(
                    HumanMessage(
                        content=(
                            "上一个结构化输出请求失败。"
                            "现在请直接返回一个 JSON 对象，且必须严格满足下面的 JSON Schema。"
                            "不要输出解释、不要输出 Markdown 代码块外的额外文本。\n"
                            f"JSON Schema: {json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
                        )
                    )
                )
                try:
                    raw_text = self.invoke_messages(fallback_messages)
                    payload_text = _extract_json_payload(raw_text)
                    try:
                        return output_model.model_validate_json(payload_text)
                    except Exception:
                        return output_model.model_validate(json.loads(payload_text))
                except Exception as fallback_exc:
                    exc = fallback_exc
            details = describe_llm_exception(exc)
            raise LLMInvocationError(
                f"Error generating structured response: {details['error_message']}",
                error_code=details["error_code"],
                error_stage=details["error_stage"],
                error_type=details["error_type"],
                error_message=details["error_message"],
            ) from exc

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        return self.invoke_text(prompt, system_prompt)

    async def agenerate_response(self, prompt: str, system_prompt: str = "") -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: List[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        return await self.ainvoke_messages(messages)

    def get_model_info(self) -> dict:
        return {
            "model": getattr(self.llm, "model_name", ""),
            "temperature": getattr(self.llm, "temperature", 0.0),
            "max_tokens": getattr(self.llm, "max_tokens", 0),
        }


def create_llm_client(config) -> LLMClient:
    return LLMClient(config=config)
