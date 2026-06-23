#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical retrieval response types.

Single contract for all knowledge-base retrieval entry points. Replaces the
historical dual-track shape (LangChain Document list vs. Chinese-keyed dict
list) so downstream checks can read one structure unconditionally.

Diagnostic codes are first-class: callers can distinguish "knowledge base
missing" from "no hits" without inspecting log strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class DiagnosticCode(str, Enum):
    OK = "OK"
    DB_MISSING = "DB_MISSING"
    COLLECTION_MISSING = "COLLECTION_MISSING"
    EMBEDDING_UNAVAILABLE = "EMBEDDING_UNAVAILABLE"
    EMPTY_COLLECTION = "EMPTY_COLLECTION"
    NO_SAME_BASIS = "NO_SAME_BASIS"
    LOW_SIMILARITY = "LOW_SIMILARITY"
    METADATA_INCOMPLETE = "METADATA_INCOMPLETE"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"

    @property
    def is_ok(self) -> bool:
        return self is DiagnosticCode.OK

    @property
    def is_system_error(self) -> bool:
        return self in {
            DiagnosticCode.DB_MISSING,
            DiagnosticCode.COLLECTION_MISSING,
            DiagnosticCode.EMBEDDING_UNAVAILABLE,
            DiagnosticCode.UNEXPECTED_ERROR,
        }


@dataclass
class Diagnostic:
    code: DiagnosticCode = DiagnosticCode.OK
    message: str = ""
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "fallback_used": self.fallback_used,
        }


@dataclass
class RetrievalHit:
    """Single knowledge-base hit, format-agnostic.

    page_content: human-readable body (mandatory).
    metadata: structured fields. Mandatory keys: collection, db_dir, distance|score.
    """

    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def distance(self) -> Optional[float]:
        for key in ("distance", "score"):
            value = self.metadata.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"page_content": self.page_content, "metadata": dict(self.metadata)}


@dataclass
class RetrievalResponse:
    """Canonical retrieval response.

    Callers should branch on `diagnostic.code`, not on `len(hits)`.
    """

    query: str
    hits: List[RetrievalHit] = field(default_factory=list)
    diagnostic: Diagnostic = field(default_factory=Diagnostic)
    db_dir: str = ""
    collection: str = ""
    topk: int = 0

    @property
    def ok(self) -> bool:
        return self.diagnostic.code.is_ok

    @property
    def items_count(self) -> int:
        return len(self.hits)

    def __bool__(self) -> bool:
        return bool(self.hits)

    def __iter__(self):
        return iter(self.hits)

    def __len__(self) -> int:
        return len(self.hits)

    def __getitem__(self, idx):
        return self.hits[idx]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "query": self.query,
            "db_dir": self.db_dir,
            "collection": self.collection,
            "topk": self.topk,
            "items_count": self.items_count,
            "hits": [hit.to_dict() for hit in self.hits],
            "diagnostic": self.diagnostic.to_dict(),
        }


def hit_from_legacy_dict(item: Dict[str, Any]) -> RetrievalHit:
    """Bridge for legacy dict-shaped hits (Chinese keys)."""
    if not isinstance(item, dict):
        return RetrievalHit(page_content=str(item or ""), metadata={})
    page_content = (
        item.get("page_content")
        or item.get("文档内容")
        or item.get("doc")
        or item.get("content")
        or ""
    )
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {k: v for k, v in item.items() if k not in {"page_content", "文档内容", "doc", "content", "metadata"}}
    return RetrievalHit(page_content=str(page_content or ""), metadata=dict(metadata))


def hit_from_langchain_document(doc: Any) -> RetrievalHit:
    """Bridge for LangChain Document objects."""
    page_content = getattr(doc, "page_content", "") or ""
    metadata = getattr(doc, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return RetrievalHit(page_content=str(page_content), metadata=dict(metadata))


def response_from_documents(
    query: str,
    documents: Iterable[Any],
    *,
    db_dir: str = "",
    collection: str = "",
    topk: int = 0,
    diagnostic: Optional[Diagnostic] = None,
) -> RetrievalResponse:
    hits = [hit_from_langchain_document(doc) for doc in documents]
    if diagnostic is None:
        diagnostic = Diagnostic(code=DiagnosticCode.OK) if hits else Diagnostic(
            code=DiagnosticCode.LOW_SIMILARITY, message="no hits returned"
        )
    return RetrievalResponse(
        query=query,
        hits=hits,
        diagnostic=diagnostic,
        db_dir=db_dir,
        collection=collection,
        topk=topk or len(hits),
    )


def response_from_legacy_dicts(
    query: str,
    items: Iterable[Dict[str, Any]],
    *,
    db_dir: str = "",
    collection: str = "",
    topk: int = 0,
    diagnostic: Optional[Diagnostic] = None,
) -> RetrievalResponse:
    hits = [hit_from_legacy_dict(item) for item in items]
    if diagnostic is None:
        diagnostic = Diagnostic(code=DiagnosticCode.OK) if hits else Diagnostic(
            code=DiagnosticCode.LOW_SIMILARITY, message="no hits returned"
        )
    return RetrievalResponse(
        query=query,
        hits=hits,
        diagnostic=diagnostic,
        db_dir=db_dir,
        collection=collection,
        topk=topk or len(hits),
    )


__all__ = [
    "Diagnostic",
    "DiagnosticCode",
    "RetrievalHit",
    "RetrievalResponse",
    "hit_from_langchain_document",
    "hit_from_legacy_dict",
    "response_from_documents",
    "response_from_legacy_dicts",
]
