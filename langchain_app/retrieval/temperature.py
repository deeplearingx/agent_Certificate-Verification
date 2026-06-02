#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
温度条件数据库检索服务
"""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_app.core import VectorDatabase


class TemperatureRetrievalService:
    """温度条件数据库检索服务"""

    def __init__(
        self,
        db_dir: str,
        collection_name: str = "temperature_data",
        embedding_model: str = "BAAI/bge-m3"
    ):
        """
        初始化温度检索服务

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

    def search_temperature_requirements(
        self,
        instrument_name: str,
        criterion: Optional[str] = None,
        k: int = 5,
    ) -> List[Document]:
        """
        搜索温度条件要求

        Args:
            instrument_name: 仪器名称
            criterion: 校准依据（可选）
            k: 返回结果数量

        Returns:
            List[Document]: 检索结果
        """
        query = instrument_name
        if criterion:
            query = f"{instrument_name} {criterion}"

        return self.db.similarity_search(query, k)

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

def create_temperature_retrieval_service(config) -> TemperatureRetrievalService:
    """
    根据配置创建温度检索服务

    Args:
        config: 应用配置

    Returns:
        TemperatureRetrievalService: 温度检索服务实例
    """
    return TemperatureRetrievalService(
        db_dir=config.temperature_db_dir,
        collection_name="temperature_data",
        embedding_model=config.embed_model_path
    )


# ==================== 业务方法 ====================

def search_temperature_by_instrument(
    instrument_name: str,
    criterion: Optional[str],
    config,
    k: int = 5
) -> List[Document]:
    """
    根据仪器名称搜索温度条件

    Args:
        instrument_name: 仪器名称
        criterion: 校准依据
        config: 应用配置
        k: 返回结果数量

    Returns:
        List[Document]: 检索结果
    """
    service = create_temperature_retrieval_service(config)
    return service.search_temperature_requirements(instrument_name, criterion, k)
