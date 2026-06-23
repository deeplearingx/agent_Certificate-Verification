#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangChain 检索服务包初始化

提供统一的检索服务接口，支持各种业务场景的向量数据库查询
"""

from .cnas import (
    CnasRetrievalService,
    create_cnas_retrieval_service,
    search_calibration_by_criterion,
)

from .temperature import (
    TemperatureRetrievalService,
    create_temperature_retrieval_service,
    search_temperature_by_instrument,
)

from .address import (
    AddressRetrievalService,
    create_address_retrieval_service,
    search_address_by_text,
)

from .cycle import (
    CycleRetrievalService,
    create_cycle_retrieval_service,
    search_cycle_by_instrument,
)

from .types import (
    Diagnostic,
    DiagnosticCode,
    RetrievalHit,
    RetrievalResponse,
    hit_from_langchain_document,
    hit_from_legacy_dict,
    response_from_documents,
    response_from_legacy_dicts,
)

__all__ = [
    "CnasRetrievalService",
    "create_cnas_retrieval_service",
    "search_calibration_by_criterion",
    "TemperatureRetrievalService",
    "create_temperature_retrieval_service",
    "search_temperature_by_instrument",
    "AddressRetrievalService",
    "create_address_retrieval_service",
    "search_address_by_text",
    "CycleRetrievalService",
    "create_cycle_retrieval_service",
    "search_cycle_by_instrument",
    "Diagnostic",
    "DiagnosticCode",
    "RetrievalHit",
    "RetrievalResponse",
    "hit_from_langchain_document",
    "hit_from_legacy_dict",
    "response_from_documents",
    "response_from_legacy_dicts",
]
