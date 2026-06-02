#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 智能文档核验系统 - LangGraph 编排 + LangChain 能力层

与原始 app.py 功能相同，但使用 LangGraph 架构
"""

import os
import sys
import threading
from pathlib import Path
from typing import List

import streamlit as st

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from langchain_app.utils.runtime_cache import apply_default_windows_ai_cache_env

apply_default_windows_ai_cache_env()

from langchain_app.utils.config import AppConfig, get_app_config
from langchain_app.core import (
    PipelineHooks,
    run_verification,
    load_shared_embedder,
)


@st.cache_resource
def load_global_model(model_path: str):
    """加载全局嵌入模型 (缓存)"""
    return load_shared_embedder(model_path)


def _render_execution_panels(info_placeholder, logs_list, warnings_list, errors_list):
    with info_placeholder:
        columns = st.columns(3)
        with columns[0]:
            with st.expander("[日志] 日志", expanded=True):
                for log in logs_list:
                    st.text(log)
        with columns[1]:
            with st.expander("[警告] 警告", expanded=True):
                for warn in warnings_list:
                    st.warning(warn)
        with columns[2]:
            with st.expander("[错误] 错误", expanded=bool(errors_list)):
                for err in errors_list:
                    st.error(err)


def main():
    """主函数 - 与原始 app.py 功能相同"""
    st.set_page_config(
        page_title="AI 文档核验系统 - LangGraph版",
        page_icon="📄",
        layout="wide"
    )

    st.title("AI 智能文档核验系统")
    st.markdown("对校准证书执行完整性、准确性和合规性检查。")

    # 初始化配置
    APP_CONFIG = get_app_config()

    # 初始化会话状态
    if "running" not in st.session_state:
        st.session_state.running = False
    if "stop_event" not in st.session_state:
        st.session_state.stop_event = threading.Event()
    if "batch_reports" not in st.session_state:
        st.session_state.batch_reports = []
    if "batch_failures" not in st.session_state:
        st.session_state.batch_failures = []

    # 侧边栏配置
    with st.sidebar:
        st.header("系统配置")

        api_key_input = st.text_input(
            "DeepSeek API Key",
            value=APP_CONFIG.api_key,
            type="password"
        )

        with st.expander("LLM 参数", expanded=True):
            temperature = st.slider("Temperature", 0.0, 1.0, APP_CONFIG.temperature, 0.1)
            max_tokens = st.number_input("Max Tokens", 512, 8192, APP_CONFIG.max_tokens, 256)
            top_k = st.number_input("Top K", 1, 100, APP_CONFIG.topk, 5)
            model_name = st.selectbox(
                "Model",
                ["deepseek-v4-flash", "deepseek-v4-pro"],
                index=0 if APP_CONFIG.model == "deepseek-v4-flash" else 1
            )

        with st.expander("路径配置", expanded=False):
            embed_model = st.text_input("Embedding Model Path", value=str(APP_CONFIG.embed_model_path))

    # 更新配置
    current_config = APP_CONFIG.with_overrides(
        api_key=api_key_input,
        temperature=temperature,
        max_tokens=max_tokens,
        topk=top_k,
        model=model_name,
        embed_model_path=embed_model
    ).ensure_directories()

    # 主界面
    uploaded_files = st.file_uploader("请上传待核验的 PDF 文件", type=["pdf"], accept_multiple_files=True)

    if uploaded_files:
        if len(uploaded_files) == 1:
            uploaded_file = uploaded_files[0]
            st.write(f"文件名: **{uploaded_file.name}**")
            st.write(f"大小: {uploaded_file.size / 1024:.2f} KB")
        else:
            st.write(f"待核验文件数: **{len(uploaded_files)}**")
            for index, uploaded_file in enumerate(uploaded_files, start=1):
                st.write(f"{index}. `{uploaded_file.name}` ({uploaded_file.size / 1024:.2f} KB)")

        st.divider()

        button_placeholder = st.empty()
        start_label = "开始智能核验 (LangGraph版)" if len(uploaded_files) == 1 else "开始批量智能核验 (LangGraph版)"

        if st.session_state.running:
            if button_placeholder.button("正在核验中... 点击终止"):
                st.session_state.stop_event.set()
                st.rerun()
        else:
            if button_placeholder.button(start_label):
                if not api_key_input:
                    st.error("请先提供 API Key")
                else:
                    st.session_state.batch_reports = []
                    st.session_state.batch_failures = []
                    st.session_state.running = True
                    st.rerun()

    # 执行核验流程
    if st.session_state.running and uploaded_files:
        files_to_process = list(uploaded_files)
        total_files = len(files_to_process)

        # 初始化进度和状态显示
        result_container = st.container()
        progress_bar = result_container.progress(0)
        status_text = result_container.empty()

        # 新增：执行信息显示区域
        with result_container:
            st.divider()
            st.subheader("执行信息")

            # 使用占位符来实时更新信息
            info_placeholder = st.empty()

        # 收集日志、警告、错误的列表
        logs_list = []
        warnings_list = []
        errors_list = []
        progress_context = {"index": 0, "name": ""}

        # 初始化Hook机制，增强版
        def log_info(msg):
            prefix = f"[{progress_context['index'] + 1}/{total_files}] {progress_context['name']}"
            logs_list.append(f"{prefix} {msg}")
            _render_execution_panels(info_placeholder, logs_list, warnings_list, errors_list)
            st.info(msg)

        def log_warning(msg):
            prefix = f"[{progress_context['index'] + 1}/{total_files}] {progress_context['name']}"
            warnings_list.append(f"{prefix} {msg}")
            _render_execution_panels(info_placeholder, logs_list, warnings_list, errors_list)
            st.warning(msg)

        def log_error(msg):
            prefix = f"[{progress_context['index'] + 1}/{total_files}] {progress_context['name']}"
            errors_list.append(f"{prefix} {msg}")
            _render_execution_panels(info_placeholder, logs_list, warnings_list, errors_list)
            st.error(msg)

        def set_status(message: str):
            status_text.text(f"[{progress_context['index'] + 1}/{total_files}] {progress_context['name']} | {message}")

        def set_progress(value: int):
            normalized = max(0, min(100, int(value)))
            overall = int(((progress_context["index"] + normalized / 100.0) / max(total_files, 1)) * 100)
            progress_bar.progress(min(overall, 100))

        hooks = PipelineHooks(
            set_status=set_status,
            set_progress=set_progress,
            info=log_info,
            warning=log_warning,
            error=log_error,
            success=st.success,
        )

        # 执行核验
        try:
            shared_embedder = load_global_model(str(current_config.embed_model_path))
            batch_reports = []
            batch_failures = []

            for file_index, uploaded_file in enumerate(files_to_process):
                if st.session_state.stop_event.is_set():
                    batch_failures.append({"name": uploaded_file.name, "error": "用户终止批量处理"})
                    break

                progress_context["index"] = file_index
                progress_context["name"] = uploaded_file.name
                log_info("开始处理当前文件")

                target_pdf_path = current_config.local_pdf_dir / uploaded_file.name
                target_pdf_path.write_bytes(uploaded_file.getbuffer())

                final_report = run_verification(
                    pdf_file_path=target_pdf_path,
                    config=current_config,
                    hooks=hooks,
                    stop_event=st.session_state.stop_event,
                    embedder=shared_embedder,
                )

                if not final_report:
                    failure_message = "run_verification returned no final report"
                    batch_failures.append({"name": uploaded_file.name, "error": failure_message})
                    log_error(failure_message)
                    continue

                report_path = current_config.final_reports_dir / f"Report_{target_pdf_path.stem}.md"
                report_path.write_text(final_report, encoding="utf-8")
                batch_reports.append(
                    {
                        "name": uploaded_file.name,
                        "report_path": str(report_path),
                        "report_text": final_report,
                    }
                )
                if "# [终止]" in final_report or "# [跳过]" in final_report:
                    log_warning("当前文件为非 CNAS，已输出跳过报告并继续下一文件")
                else:
                    log_info("当前文件核验完成，继续下一文件")
                st.session_state["last_report"] = final_report

            st.session_state.batch_reports = batch_reports
            st.session_state.batch_failures = batch_failures

            if batch_reports and not batch_failures:
                st.success(f"批量核验完成，共 {len(batch_reports)} 份报告")
            elif batch_reports:
                st.warning(f"批量核验完成，但有失败项。成功 {len(batch_reports)} 份，失败 {len(batch_failures)} 份")
            elif batch_failures:
                st.error("批量核验未生成任何成功报告")

        except Exception as e:
            st.error(f"核验过程中出错: {e}")
            import traceback
            st.exception(e)
        finally:
            st.session_state.running = False
            st.session_state.stop_event.clear()

    if st.session_state.get("batch_failures") and not st.session_state.running:
        with st.expander("查看批量失败项", expanded=False):
            for failure in st.session_state.batch_failures:
                st.error(f"{failure['name']}: {failure['error']}")

    if st.session_state.get("batch_reports") and not st.session_state.running:
        st.subheader("批量核验结果")
        for index, item in enumerate(st.session_state.batch_reports, start=1):
            report_name = Path(item["report_path"]).name
            with st.expander(f"{index}. {item['name']}", expanded=False):
                st.caption(item["report_path"])
                st.download_button(
                    f"下载 {report_name}",
                    item["report_text"],
                    file_name=report_name,
                    mime="text/markdown",
                    key=f"download_{report_name}_{index}",
                )
                st.markdown(item["report_text"])

    # 显示最后一份报告
    if "last_report" in st.session_state and not st.session_state.running and not st.session_state.get("batch_reports"):
        with st.expander("查看最后一份核验报告", expanded=False):
            st.markdown(st.session_state["last_report"])


if __name__ == "__main__":
    main()
