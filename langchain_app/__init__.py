#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI智能文档核验系统 - LangChain重构版

这是基于 LangChain 框架重构的 AI 智能文档核验系统，
实现了从 PDF 上传到生成核验报告的完整流程。系统结合了
OCR 技术、大语言模型（LLM）和向量数据库检索，能够对校准证书
进行完整性、准确性和合规性检查。

主要功能：
- PDF → MD 转换 (MinerU OCR)
- MD → JSON 解析 (规则解析器)
- 信息完整性核验
- 环境条件核验
- 校准地点核验
- 校准周期核验
- 参数与不确定度核验

核心技术栈：
- LangChain: LLM 应用开发框架
- DeepSeek: 大语言模型
- BAAI/bge-m3: 文本嵌入模型
- Chroma DB: 向量数据库
- MinerU: PDF 解析
- Streamlit: Web 界面
"""

__version__ = "2.0.0"
__author__ = "AI智能文档核验系统开发团队"

"""
公共 API 导出

为了避免在导入配置时触发所有核心依赖的加载，
我们使用延迟导入策略，只在需要时加载特定组件。
"""

def __dir__():
    return [
        "AppConfig",
        "LLMClient",
        "VectorDatabase",
        "VerificationReport",
        "VerificationAgent",
        "get_all_tools",
        "get_app_config"
    ]

def __getattr__(name):
    if name == "AppConfig":
        from langchain_app.utils import AppConfig
        return AppConfig
    elif name == "get_app_config":
        from langchain_app.utils import get_app_config
        return get_app_config
    elif name == "LLMClient":
        from langchain_app.core import LLMClient
        return LLMClient
    elif name == "VectorDatabase":
        from langchain_app.core import VectorDatabase
        return VectorDatabase
    elif name == "VerificationReport":
        from langchain_app.core import VerificationReport
        return VerificationReport
    elif name == "VerificationAgent":
        from langchain_app.agents import VerificationAgent
        return VerificationAgent
    elif name == "get_all_tools":
        from langchain_app.tools import get_all_tools
        return get_all_tools
    else:
        raise AttributeError(f"module 'langchain_app' has no attribute '{name}'")
