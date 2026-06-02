#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNAS 校准数据库检索服务
"""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_app.core import VectorDatabase


class CnasRetrievalService:
    """CNAS 校准数据库检索服务"""

    def __init__(
        self,
        db_dir: str,
        collection_name: str = "calibration_data",
        embedding_model: str = "BAAI/bge-m3",
        embedding_function=None,
    ):
        """
        初始化 CNAS 检索服务

        Args:
            db_dir: 数据库目录路径
            collection_name: 集合名称
            embedding_model: 嵌入模型名称
        """
        self.db = VectorDatabase(
            collection_name=collection_name,
            persist_directory=db_dir,
            embedding_model=embedding_model,
            embedding_function=embedding_function,
        )
        self.db_dir = db_dir
        self.collection_name = collection_name

    def search_calibration_data(
        self,
        query: str,
        k: int = 5,
        filter_condition: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        搜索校准数据

        Args:
            query: 查询文本
            k: 返回结果数量
            filter_condition: 过滤条件

        Returns:
            List[Document]: 检索结果
        """
        return self.db.similarity_search(query, k, filter_condition)

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

    def search_calibration_by_criterion(
        self,
        query: str,
        k: int = 5,
        filter_condition: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """兼容旧接口名。"""
        return self.search_calibration_data(query, k, filter_condition)


# ==================== 工厂函数 ====================

def create_cnas_retrieval_service(config, embedding_function=None) -> CnasRetrievalService:
    """
    根据配置创建 CNAS 检索服务

    Args:
        config: 应用配置

    Returns:
        CnasRetrievalService: CNAS 检索服务实例
    """
    return CnasRetrievalService(
        db_dir=config.cnas_db_dir,
        collection_name=config.cnas_collection,
        embedding_model=config.embed_model_path,
        embedding_function=embedding_function,
    )


# ==================== 业务方法 ====================

def search_calibration_by_criterion(
    criterion: str,
    config,
    k: int = 3
) -> List[Document]:
    """
    根据校准依据搜索校准数据

    Args:
        criterion: 校准依据
        config: 应用配置
        k: 返回结果数量

    Returns:
        List[Document]: 检索结果
    """
    service = create_cnas_retrieval_service(config)
    return service.search_calibration_data(criterion, k)
