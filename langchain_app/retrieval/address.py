#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准地点数据库检索服务
"""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_app.core import VectorDatabase


class AddressRetrievalService:
    """校准地点数据库检索服务"""

    def __init__(
        self,
        db_dir: str,
        collection_name: str = "calibration_address",
        embedding_model: str = "BAAI/bge-m3"
    ):
        """
        初始化地址检索服务

        Args:
            db_dir: 数据库目录路径
            collection_name: 集合名称
            embedding_model: 嵌入模型名称
        """
        self.db = VectorDatabase(
            collection_name=collection_name,
            persist_directory=db_dir,
            embedding_model=embedding_model
        )
        self.db_dir = db_dir
        self.collection_name = collection_name

    def search_addresses(
        self,
        address_text: str,
        k: int = 5,
    ) -> List[Document]:
        """
        搜索校准地点

        Args:
            address_text: 地址文本
            k: 返回结果数量

        Returns:
            List[Document]: 检索结果
        """
        return self.db.similarity_search(address_text, k)

    def search_with_score(
        self,
        query: str,
        k: int = 5
    ) -> List[tuple[Document, float]]:
        """
        搜索并返回分数

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            List[tuple[Document, float]]: 检索结果和相似度分数
        """
        return self.db.similarity_search_with_score(query, k)

    def get_collection_info(self) -> Dict[str, Any]:
        """获取集合信息"""
        return self.db.get_collection_info()


# ==================== 工厂函数 ====================

def create_address_retrieval_service(config) -> AddressRetrievalService:
    """
    根据配置创建地址检索服务

    Args:
        config: 应用配置

    Returns:
        AddressRetrievalService: 地址检索服务实例
    """
    return AddressRetrievalService(
        db_dir=config.address_db_dir,
        collection_name=config.address_collection,
        embedding_model=config.embed_model_path
    )


# ==================== 业务方法 ====================

def search_address_by_text(
    address_text: str,
    config,
    k: int = 5
) -> List[Document]:
    """
    根据地址文本搜索校准地点

    Args:
        address_text: 地址文本
        config: 应用配置
        k: 返回结果数量

    Returns:
        List[Document]: 检索结果
    """
    service = create_address_retrieval_service(config)
    return service.search_addresses(address_text, k)
