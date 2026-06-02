#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED: 旧向量数据库客户端 - 已不再使用

此模块提供旧项目架构的向量数据库接口，但新代码应该直接使用 langchain_app.core.VectorDatabase。

WARNING: 此模块将在未来版本中删除。
"""

import warnings

warnings.warn(
    "kb.chroma_client is deprecated and will be removed in a future version. "
    "Please use langchain_app.core.VectorDatabase instead.",
    DeprecationWarning,
    stacklevel=2
)

import os
import shutil
from pathlib import Path
import chromadb
from chromadb.errors import NotFoundError


def create_persistent_client(path: str) -> chromadb.PersistentClient:
    # 将路径转换为 Path 对象并确保使用绝对路径
    db_path = Path(path).resolve()
    # 转换为字符串时使用相对路径，避免 Windows 中文路径问题
    try:
        rel_path = db_path.relative_to(Path.cwd())
        use_path = str(rel_path)
    except ValueError:
        use_path = str(db_path)

    # 使用英文路径格式，避免编码问题
    return chromadb.PersistentClient(path=use_path)


def get_collection(path: str, name: str):
    client = create_persistent_client(path)
    return client.get_collection(name=name)


def try_repair_collection(db_path: str, collection_name: str, backup_dir: str = "vector_db_backup") -> bool:
    """
    尝试修复损坏的 ChromaDB 集合
    返回: 是否成功修复
    """
    try:
        client = create_persistent_client(db_path)

        # 尝试获取集合，如果失败则尝试重建
        try:
            collection = client.get_collection(collection_name)
            # 检查集合是否能正常查询
            if collection.count() > 0:
                collection.peek(1)
            return True
        except Exception as e:
            print(f"[警告] 集合损坏: {e}")

        # 备份损坏的数据库
        backup_path = Path(backup_dir)
        backup_path.mkdir(exist_ok=True)

        db_dir = Path(db_path)
        if db_dir.exists():
            timestamp = str(int(os.time()))
            backup_name = f"{db_dir.name}_{timestamp}"
            shutil.copytree(db_dir, backup_path / backup_name)
            print(f"[备份] 已备份损坏的数据库到: {backup_path / backup_name}")

        # 删除损坏的集合数据
        try:
            client.delete_collection(collection_name)
            print(f"[删除] 已删除损坏的集合")
        except:
            # 如果无法删除，尝试直接删除整个数据库目录
            if db_dir.exists():
                shutil.rmtree(db_dir)
                db_dir.mkdir(parents=True)
                print(f"[删除] 已重新创建数据库目录")

        return False

    except Exception as e:
        print(f"[错误] 修复数据库时出错: {e}")
        return False
