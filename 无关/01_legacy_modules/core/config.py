#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块 - 从param_check.py提取重构
统一管理所有配置参数
"""

import os
import hashlib
import time
from pathlib import Path
from typing import Any, Optional

from config.settings import get_app_config


class Config:
    """配置管理类 - 统一管理所有配置参数"""

    # 获取应用配置
    _app = get_app_config()

    # 数据库配置
    DB_DIR = _app.cnas_db_dir
    COLLECTION = _app.cnas_collection

    # 模型配置
    EMBED_MODEL_PATH = _app.embed_model_path

    # 输出配置
    OUTPUT_DIR = str(_app.reports_dir)

    # API配置
    API_KEY = _app.api_key or os.getenv("DEEPSEEK_API_KEY", "")
    API_BASE = _app.api_base.rstrip("/")
    MODEL = _app.model
    TEMPERATURE = _app.temperature
    MAX_TOKENS = _app.max_tokens

    # 查询配置
    TOPK = _app.topk
    BATCH_SIZE = _app.batch_size

    # 并发配置
    max_workers = _app.max_workers

    @classmethod
    def build_version_stamp(cls, file_path: str = __file__) -> str:
        """构建版本戳记"""
        path = Path(file_path)
        stat = path.stat()
        mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
        return f"{Path(file_path).name} | mtime={mtime} | sha1={digest}"

    @classmethod
    def get(cls, key: str, default: Optional[Any] = None) -> Any:
        """动态获取配置值"""
        if hasattr(cls, key):
            return getattr(cls, key)
        return default

    @classmethod
    def to_dict(cls) -> dict:
        """转换为字典"""
        return {
            "DB_DIR": cls.DB_DIR,
            "COLLECTION": cls.COLLECTION,
            "EMBED_MODEL_PATH": cls.EMBED_MODEL_PATH,
            "OUTPUT_DIR": cls.OUTPUT_DIR,
            "API_KEY": "***" if cls.API_KEY else "",
            "API_BASE": cls.API_BASE,
            "MODEL": cls.MODEL,
            "TEMPERATURE": cls.TEMPERATURE,
            "MAX_TOKENS": cls.MAX_TOKENS,
            "TOPK": cls.TOPK,
            "BATCH_SIZE": cls.BATCH_SIZE,
            "max_workers": cls.max_workers,
        }


# 全局状态
LAST_QUERY_ERROR: Optional[str] = None
