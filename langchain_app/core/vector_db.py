#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vector database helper for langchain_app.

Search strategy:
1. Prefer Chroma's native vector similarity query when embeddings are available.
2. Fall back to local lexical matching when the vector query path is unavailable
   or fails on the current machine.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings
from langchain_core.documents import Document

from langchain_app.core.embedding_loader import load_sentence_transformer


class _SentenceTransformerEmbeddings:
    """Minimal embedding adapter used when LangChain embedding packages are absent."""

    def __init__(self, model_name: str):
        self.model = load_sentence_transformer(model_name)

    def embed_documents(self, texts):
        return self.model.encode(list(texts), convert_to_numpy=True).tolist()

    def embed_query(self, text):
        return self.model.encode(text, convert_to_numpy=True).tolist()


class VectorDatabase:
    """Thin wrapper around a persisted Chroma collection."""

    def __init__(
        self,
        collection_name: str = "default",
        persist_directory: Optional[str] = None,
        embedding_model: str = "BAAI/bge-m3",
        embedding_function: Optional[Any] = None,
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory

        self.embedding_model_name = embedding_model
        self.embedding_model = embedding_function

        self._fallback_cache: Optional[List[tuple[str, Dict[str, Any]]]] = None
        self._collection = None
        self._vector_store = None
        self._embedding_init_error: Optional[str] = None

        if persist_directory is None:
            if self.embedding_model is None:
                self.embedding_model = self._build_default_embedding_function()
            from langchain_chroma import Chroma
            self._vector_store = Chroma(
                collection_name=collection_name,
                embedding_function=self.embedding_model,
                persist_directory=None,
            )

    def _chroma_path(self) -> Optional[str]:
        if not self.persist_directory:
            return None

        db_path = Path(self.persist_directory).resolve()
        try:
            return os.path.relpath(str(db_path), start=str(Path.cwd()))
        except Exception:
            return str(db_path)

    def _open_raw_collection(self):
        if self._collection is not None:
            return self._collection
        chroma_path = self._chroma_path()
        if not chroma_path:
            return None
        client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = client.get_collection(self.collection_name)
        return self._collection

    def _build_default_embedding_function(self) -> Optional[Any]:
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings

            return HuggingFaceEmbeddings(
                model_name=self.embedding_model_name,
                cache_folder="./models",
            )
        except ModuleNotFoundError:
            pass

        try:
            return _SentenceTransformerEmbeddings(self.embedding_model_name)
        except ModuleNotFoundError as exc:
            self._embedding_init_error = str(exc)
            return None
        except Exception as exc:
            self._embedding_init_error = str(exc)
            return None

    def _ensure_embedding_function(self) -> Optional[Any]:
        if self.embedding_model is not None:
            return self.embedding_model

        self.embedding_model = self._build_default_embedding_function()
        return self.embedding_model

    def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        embedding_function = self._ensure_embedding_function()
        if embedding_function is None:
            return None

        if hasattr(embedding_function, "embed_query"):
            try:
                embedding = embedding_function.embed_query(query)
                return list(embedding) if embedding is not None else None
            except Exception:
                return None

        return None

    def _distance_to_similarity(self, distance: Optional[float]) -> float:
        if distance is None:
            return 0.0
        try:
            return 1.0 / (1.0 + float(distance))
        except Exception:
            return 0.0

    def _document_with_distance(
        self,
        doc_text: str,
        metadata: Optional[Dict[str, Any]],
        distance: Optional[float] = None,
    ) -> Document:
        doc_metadata = dict(metadata or {})
        if distance is not None:
            doc_metadata.setdefault("distance", distance)
        return Document(page_content=doc_text or "", metadata=doc_metadata)

    def _load_records(self) -> List[tuple[str, Dict[str, Any]]]:
        if self._fallback_cache is not None:
            return self._fallback_cache

        collection = self._open_raw_collection()
        if collection is None and self._vector_store is not None:
            collection = self._vector_store._collection
        if collection is None:
            self._fallback_cache = []
            return self._fallback_cache

        records: List[tuple[str, Dict[str, Any]]] = []
        try:
            total = collection.count()
        except Exception:
            total = None

        if total is not None:
            page_size = 1000
            for offset in range(0, total, page_size):
                data = collection.get(
                    limit=page_size,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                documents = data.get("documents") or []
                metadatas = data.get("metadatas") or []
                for doc_text, metadata in zip(documents, metadatas):
                    records.append((doc_text or "", metadata or {}))
        else:
            data = collection.peek(limit=10000)
            documents = data.get("documents") or []
            metadatas = data.get("metadatas") or []
            for doc_text, metadata in zip(documents, metadatas):
                records.append((doc_text or "", metadata or {}))

        self._fallback_cache = records
        return records

    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        if self._vector_store is None:
            raise RuntimeError("Vector store is read-only in persisted collection mode")
        documents = []
        for i, text in enumerate(texts):
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {}
            documents.append(Document(page_content=text, metadata=metadata))
        return self._vector_store.add_documents(documents)

    def add_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if self._vector_store is None:
            raise RuntimeError("Vector store is read-only in persisted collection mode")
        doc = Document(page_content=text, metadata=metadata or {})
        ids = self._vector_store.add_documents([doc])
        return ids[0] if ids else ""

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", "", (text or "").lower())

    def _lexical_score(self, query: str, doc_text: str, metadata: Dict[str, Any]) -> float:
        query_norm = self._normalize_text(query)
        if not query_norm:
            return 0.0

        doc_parts = [doc_text or ""]
        for value in metadata.values():
            if value is not None:
                doc_parts.append(str(value))
        doc_norm = self._normalize_text(" ".join(doc_parts))

        score = 0.0
        if query_norm in doc_norm:
            score += 10.0

        query_tokens = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", query_norm))
        if not query_tokens:
            return score

        doc_tokens = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", doc_norm))
        overlap = len(query_tokens & doc_tokens)
        score += float(overlap)
        return score

    def _manual_similarity_search(
        self,
        query: str,
        k: int,
        filter_condition: Optional[Dict[str, Any]] = None,
    ) -> List[tuple[Document, float]]:
        records = self._load_records()
        if not records:
            return []

        scored: List[tuple[Document, float]] = []
        for doc_text, metadata in records:
            if filter_condition:
                matched = True
                for key, expected in filter_condition.items():
                    if metadata.get(key) != expected:
                        matched = False
                        break
                if not matched:
                    continue

            score = self._lexical_score(query, doc_text, metadata)
            distance = None if score <= 0 else 1.0 / (1.0 + score)
            scored.append((self._document_with_distance(doc_text, metadata, distance), score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def _vector_similarity_search(
        self,
        query: str,
        k: int,
        filter_condition: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[tuple[Document, float]]]:
        collection = self._open_raw_collection()
        if collection is None and self._vector_store is not None:
            collection = self._vector_store._collection
        if collection is None:
            return None

        query_embedding = self._get_query_embedding(query)
        if query_embedding is None:
            return None

        try:
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=filter_condition,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return None

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        scored: List[tuple[Document, float]] = []
        for doc_text, metadata, distance in zip(documents, metadatas, distances):
            doc = self._document_with_distance(doc_text or "", metadata or {}, distance)
            scored.append((doc, self._distance_to_similarity(distance)))
        return scored

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_condition: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        scored = self._vector_similarity_search(query, k, filter_condition)
        if scored is None:
            scored = self._manual_similarity_search(query, k, filter_condition)
        return [doc for doc, _ in scored]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
    ) -> List[tuple[Document, float]]:
        scored = self._vector_similarity_search(query, k, None)
        if scored is None:
            scored = self._manual_similarity_search(query, k, None)
        return scored

    def delete_documents(self, ids: List[str]) -> None:
        if self._vector_store is None:
            raise RuntimeError("Vector store is read-only in persisted collection mode")
        self._vector_store.delete(ids=ids)

    def get_collection_info(self) -> Dict[str, Any]:
        collection = None
        if self._vector_store is not None:
            collection = self._vector_store._collection
        elif self.persist_directory:
            collection = self._open_raw_collection()

        count = None
        if collection is not None:
            try:
                count = collection.count()
            except Exception:
                count = None

        return {
            "name": getattr(collection, "name", self.collection_name),
            "count": count,
            "persist_directory": self.persist_directory,
            "vector_query_enabled": self._ensure_embedding_function() is not None,
            "embedding_init_error": self._embedding_init_error,
        }

    def clear(self) -> None:
        if self._vector_store is None:
            raise RuntimeError("Vector store is read-only in persisted collection mode")
        collection = self._vector_store._collection
        collection.delete()

    @property
    def vector_store(self):
        if self._vector_store is not None:
            return self._vector_store._collection
        return self._open_raw_collection()


def load_vector_db(
    persist_directory: str,
    collection_name: str = "default",
    embedding_model: str = "BAAI/bge-m3",
    embedding_function: Optional[Any] = None,
) -> VectorDatabase:
    return VectorDatabase(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_model=embedding_model,
        embedding_function=embedding_function,
    )
