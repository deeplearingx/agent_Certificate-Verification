#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例应用 - LangGraph 编排 + LangChain 能力层
展示如何使用 LangGraph 重构的系统
"""

import streamlit as st
from pathlib import Path

from langchain_app.utils import AppConfig
from langchain_app.core import (
    LLMClient,
    create_llm_client,
    VectorDatabase,
    VerificationReport
)
from langchain_app.agents import VerificationAgent, create_verification_agent
from langchain_app.tools.example_tools import get_all_tools


def main():
    """主函数"""
    st.set_page_config(page_title="AI 文档核验系统 - LangGraph版", page_icon="📄", layout="wide")

    st.title("AI 智能文档核验系统 - LangGraph重构版")
    st.markdown("使用 LangGraph 编排 + LangChain 能力层对校准证书执行核验。")

    # 加载配置
    config = AppConfig.from_env()

    with st.sidebar:
        st.header("系统配置")
        api_key_input = st.text_input("DeepSeek API Key", value=config.api_key, type="password")
        st.divider()

        with st.expander("LLM 参数", expanded=True):
            temperature = st.slider("Temperature", 0.0, 1.0, config.temperature, 0.1)
            max_tokens = st.number_input("Max Tokens", 512, 8192, config.max_tokens, 256)
            model_name = st.selectbox("Model", ["deepseek-chat", "deepseek-coder"], index=0)

        with st.expander("路径配置", expanded=False):
            embed_model = st.text_input("Embedding Model", value=config.embed_model_path)

    # 更新配置
    current_config = config.with_overrides(
        api_key=api_key_input,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model_name,
        embed_model_path=embed_model
    ).ensure_directories()

    # 主界面
    uploaded_file = st.file_uploader("请上传待核验的 PDF 文件", type=["pdf"])

    if uploaded_file:
        st.write(f"文件名: **{uploaded_file.name}**")
        st.write(f"大小: {uploaded_file.size / 1024:.2f} KB")

        st.divider()

        if st.button("开始智能核验 (LangGraph版)"):
            if not api_key_input:
                st.error("请先提供 API Key")
            else:
                with st.spinner("正在初始化 LangChain 组件..."):
                    try:
                        # 创建 LLM 客户端
                        llm = LLMClient(
                            api_key=api_key_input,
                            base_url="https://api.deepseek.com/v1",
                            model=model_name,
                            temperature=temperature,
                            max_tokens=max_tokens
                        )

                        st.success("[完成] LLM 客户端初始化成功")

                        # 创建 Agent
                        agent = VerificationAgent(llm.llm)
                        st.success("[完成] 核验 Agent 创建成功")

                        # 显示 Agent 信息
                        agent_info = agent.get_agent_info()
                        with st.expander("Agent 信息", expanded=True):
                            st.json(agent_info)

                        # 示例演示（不实际运行，因为需要真实文件）
                        st.info("[说明] 这是 LangGraph 编排版的演示。")
                        st.markdown("""
                        ## 重构架构优势

                        1. **简化的 LLM 集成** - 使用 LangChain 标准 ChatOpenAI
                        2. **标准工具接口** - 使用 @tool 装饰器
                        3. **灵活的 Agent 架构** - 使用 create_agent
                        4. **统一的向量数据库** - 使用 LangChain Chroma
                        5. **更好的可扩展** - 基于 LangChain 生态

                        ## 核心组件

                        - `LLMClient` - LLM 调用封装
                        - `VectorDatabase` - 向量数据库管理
                        - `VerificationAgent` - 文档核验 Agent
                        - 工具模块 - 各项核验工具
                        """)

                    except Exception as e:
                        st.error(f"初始化失败: {e}")
                        st.exception(e)

    # 架构介绍
    with st.expander("LangGraph 重构架构介绍", expanded=False):
        st.markdown("""
        ## [项目] 项目结构

        ```
        langchain_app/
        ├── __init__.py
        ├── app_example.py              # 示例应用
        ├── core/
        │   ├── __init__.py
        │   ├── llm_client.py           # LLM 客户端
        │   ├── vector_db.py            # 向量数据库
        │   └── report_generator.py      # 报告生成
        ├── tools/
        │   ├── __init__.py
        │   └── example_tools.py        # 示例工具
        ├── agents/
        │   ├── __init__.py
        │   └── verification_agent.py   # 核验 Agent
        └── utils/
            ├── __init__.py
            └── config.py               # 配置管理
        ```
        """)


if __name__ == "__main__":
    main()
