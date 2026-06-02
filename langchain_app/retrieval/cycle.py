#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准周期数据库检索服务
"""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_app.core import VectorDatabase


class CycleRetrievalService:
    """校准周期数据库检索服务"""

    def __init__(
        self,
        general_db_dir: str,
        huawei_db_dir: str,
        embedding_model: str = "BAAI/bge-m3"
    ):
        """
        初始化校准周期检索服务

        Args:
            general_db_dir: 通用周期数据库目录
            huawei_db_dir: 华为特定周期数据库目录
            embedding_model: 嵌入模型名称
        """
        self.general_collection_name = "general_cycle_data"
        self.huawei_collection_name = "huawei_cycle_data"
        self.general_db = VectorDatabase(
            collection_name=self.general_collection_name,
            persist_directory=general_db_dir,
            embedding_model=embedding_model
        )

        self.huawei_db = VectorDatabase(
            collection_name=self.huawei_collection_name,
            persist_directory=huawei_db_dir,
            embedding_model=embedding_model
        )

        self.general_db_dir = general_db_dir
        self.huawei_db_dir = huawei_db_dir

    def search_general_cycle(
        self,
        instrument_name: str,
        k: int = 5
    ) -> List[Document]:
        """
        搜索通用校准周期

        Args:
            instrument_name: 仪器名称
            k: 返回结果数量

        Returns:
            List[Document]: 检索结果
        """
        try:
            return self.general_db.similarity_search(instrument_name, k)
        except Exception:
            return self._search_with_fallback(self.general_db_dir, ["general_cycle_data", "general_cycle"], instrument_name, k)

    def search_huawei_cycle(
        self,
        instrument_name: str,
        k: int = 5
    ) -> List[Document]:
        """
        搜索华为特定校准周期

        Args:
            instrument_name: 仪器名称
            k: 返回结果数量

        Returns:
            List[Document]: 检索结果
        """
        try:
            return self.huawei_db.similarity_search(instrument_name, k)
        except Exception:
            return self._search_with_fallback(self.huawei_db_dir, ["huawei_cycle_data", "huawei_cycle"], instrument_name, k)

    def search_cycle_requirements(
        self,
        instrument_name: str,
        is_huawei: bool = False,
        k: int = 5
    ) -> List[Document]:
        """
        通用搜索接口

        Args:
            instrument_name: 仪器名称
            is_huawei: 是否华为特定周期
            k: 返回结果数量

        Returns:
            List[Document]: 检索结果
        """
        if is_huawei:
            return self.search_huawei_cycle(instrument_name, k)
        else:
            return self.search_general_cycle(instrument_name, k)

    def search_with_score(
        self,
        instrument_name: str,
        is_huawei: bool = False,
        k: int = 5
    ) -> List[tuple[Document, float]]:
        """
        搜索并返回分数

        Args:
            instrument_name: 仪器名称
            is_huawei: 是否华为特定周期
            k: 返回结果数量

        Returns:
            List[tuple[Document, float]]: 检索结果和相似度分数
        """
        db = self.huawei_db if is_huawei else self.general_db
        return db.similarity_search_with_score(instrument_name, k)

    def get_collection_info(self) -> Dict[str, Any]:
        """获取集合信息"""
        return {
            "general": self.general_db.get_collection_info(),
            "huawei": self.huawei_db.get_collection_info()
        }

    def _search_with_fallback(self, db_dir: str, collection_names: List[str], query: str, k: int) -> List[Document]:
        """Fallback to whichever collection name exists in the persisted DB."""
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(path=db_dir, settings=Settings(anonymized_telemetry=False))
        for collection_name in collection_names:
            try:
                collection = client.get_collection(collection_name)
            except Exception:
                continue

            try:
                data = collection.get(limit=k, offset=0, include=["documents", "metadatas"])
            except Exception:
                continue

            documents = data.get("documents") or []
            metadatas = data.get("metadatas") or []
            if not documents:
                continue

            scored = []
            for doc_text, metadata in zip(documents, metadatas):
                text = f"{doc_text or ''} {metadata or {}}"
                score = 1.0 if query and query in text else 0.5
                scored.append((Document(page_content=doc_text or "", metadata=metadata or {}), score))
            scored.sort(key=lambda item: item[1], reverse=True)
            return [doc for doc, _ in scored[:k]]

        return []


# ==================== 工厂函数 ====================

def create_cycle_retrieval_service(config) -> CycleRetrievalService:
    """
    根据配置创建校准周期检索服务

    Args:
        config: 应用配置

    Returns:
        CycleRetrievalService: 校准周期检索服务实例
    """
    return CycleRetrievalService(
        general_db_dir=config.general_cycle_db_dir,
        huawei_db_dir=config.huawei_cycle_db_dir,
        embedding_model=config.embed_model_path
    )


# ==================== 业务方法 ====================

def search_cycle_by_instrument(
    instrument_name: str,
    is_huawei: bool,
    config,
    k: int = 5
) -> List[Document]:
    """
    根据仪器名称和类型搜索校准周期

    Args:
        instrument_name: 仪器名称
        is_huawei: 是否华为特定周期
        config: 应用配置
        k: 返回结果数量

    Returns:
        List[Document]: 检索结果
    """
    service = create_cycle_retrieval_service(config)
    return service.search_cycle_requirements(instrument_name, is_huawei, k)
