#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED: 旧 LLM 客户端 - 已不再使用

此模块提供旧项目架构的 LLM 客户端接口，但新代码应该直接使用 langchain_app.core.LLMClient。

WARNING: 此模块将在未来版本中删除。
"""

import warnings

warnings.warn(
    "llm.client is deprecated and will be removed in a future version. "
    "Please use langchain_app.core.LLMClient instead.",
    DeprecationWarning,
    stacklevel=2
)

from openai import OpenAI
from llama_index.llms.openai_like import OpenAILike


def create_openai_client(
    api_key: str,
    api_base: str,
    timeout: float = 120.0,
) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=api_base, timeout=timeout)


def create_openai_like_client(
    *,
    model: str,
    api_base: str,
    api_key: str,
    temperature: float = 0.0,
    max_tokens: int = 512,
    timeout: float = 120.0,
) -> OpenAILike:
    return OpenAILike(
        model=model,
        api_base=api_base,
        api_key=api_key,
        is_chat_model=True,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
