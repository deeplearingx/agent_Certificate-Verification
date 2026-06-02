import time
import os
from pathlib import Path
from typing import Any, Optional

import requests
import streamlit as st

from langchain_app.utils import get_app_config


APP_CONFIG = get_app_config()
DEFAULT_API_BASE_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")
POLL_INTERVAL_SECONDS = 2


st.set_page_config(page_title="AI 文档核验系统", page_icon="📄", layout="wide")


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def post_multipart(
    url: str,
    *,
    files: dict[str, Any],
    data: dict[str, Any],
    timeout: int = 60,
) -> dict[str, Any]:
    response = requests.post(url, files=files, data=data, timeout=timeout)
    response.raise_for_status()
    return response.json()


def post_jsonless(url: str, timeout: int = 30) -> dict[str, Any]:
    response = requests.post(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def init_state() -> None:
    defaults = {
        "running": False,
        "task_id": None,
        "last_report": None,
        "last_report_path": None,
        "last_status": None,
        "last_filename": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_task_state(keep_report: bool = True) -> None:
    st.session_state.running = False
    st.session_state.task_id = None
    st.session_state.last_status = None
    st.session_state.last_filename = None
    if not keep_report:
        st.session_state.last_report = None
        st.session_state.last_report_path = None


def render_status_panels(status_payload: dict[str, Any]) -> None:
    progress = int(status_payload.get("progress", 0))
    current_step = status_payload.get("current_step") or "queued"
    logs = status_payload.get("logs", [])
    warnings = status_payload.get("warnings", [])
    errors = status_payload.get("errors", [])

    progress_bar = st.progress(progress)
    progress_bar.progress(progress)
    st.caption(f"当前任务: `{status_payload.get('task_id', '')}`")
    st.write(f"当前状态: **{status_payload.get('status', 'unknown')}**")
    st.write(f"当前步骤: **{current_step}**")

    col1, col2, col3 = st.columns(3)
    with col1:
        with st.expander("日志", expanded=True):
            if logs:
                for item in logs[-30:]:
                    st.text(item)
            else:
                st.caption("暂无日志")
    with col2:
        with st.expander("警告", expanded=True):
            if warnings:
                for item in warnings[-30:]:
                    st.warning(item)
            else:
                st.caption("暂无警告")
    with col3:
        with st.expander("错误", expanded=True):
            if errors:
                for item in errors[-30:]:
                    st.error(item)
            else:
                st.caption("暂无错误")


def fetch_task_status(base_url: str, task_id: str) -> dict[str, Any]:
    return get_json(api_url(base_url, f"/api/v1/tasks/{task_id}"))


def fetch_task_report(base_url: str, task_id: str) -> dict[str, Any]:
    return get_json(api_url(base_url, f"/api/v1/tasks/{task_id}/report"), timeout=60)


def submit_task(
    *,
    base_url: str,
    uploaded_file,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
    topk: int,
    dry_run: bool,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": str(temperature),
        "max_tokens": str(max_tokens),
        "topk": str(topk),
        "dry_run": str(dry_run).lower(),
    }
    if api_key:
        payload["api_key"] = api_key

    file_bytes = uploaded_file.getvalue()
    files = {
        "file": (uploaded_file.name, file_bytes, uploaded_file.type or "application/pdf"),
    }
    return post_multipart(
        api_url(base_url, "/api/v1/tasks/verify"),
        files=files,
        data=payload,
        timeout=120,
    )


def cancel_task(base_url: str, task_id: str) -> dict[str, Any]:
    return post_jsonless(api_url(base_url, f"/api/v1/tasks/{task_id}/cancel"))


def main() -> None:
    init_state()

    st.title("AI 智能文档核验系统")
    st.markdown(
        "当前页面作为 **Streamlit 前端** 使用，通过 HTTP 调用 FastAPI 后端完成任务提交、状态轮询和报告获取。"
    )

    with st.sidebar:
        st.header("系统配置")
        api_base_url = st.text_input("FastAPI Base URL", value=DEFAULT_API_BASE_URL)
        api_key_input = st.text_input("DeepSeek API Key", value=APP_CONFIG.api_key, type="password")
        st.divider()

        if st.button("检查后端健康状态"):
            try:
                health = get_json(api_url(api_base_url, "/api/v1/health"))
                st.success(f"后端正常: {health['service']} {health['version']}")
            except Exception as exc:
                st.error(f"后端不可用: {exc}")

        with st.expander("LLM 参数", expanded=True):
            temperature = st.slider("Temperature", 0.0, 1.0, APP_CONFIG.temperature, 0.1)
            max_tokens = st.number_input("Max Tokens", 512, 8192, APP_CONFIG.max_tokens, 256)
            top_k = st.number_input("Top K", 1, 100, APP_CONFIG.topk)
            model_name = st.selectbox(
                "Model",
                ["deepseek-chat", "deepseek-coder"],
                index=0 if APP_CONFIG.model == "deepseek-chat" else 1,
            )

        with st.expander("服务模式", expanded=False):
            dry_run = st.checkbox("Dry Run（仅验证接口链路）", value=False)
            st.caption("开启后只验证上传 -> 创建任务 -> 轮询 -> 获取报告，不执行重型核验流程。")

    uploaded_file = st.file_uploader("请上传待核验的 PDF 文件", type=["pdf"])

    if uploaded_file:
        info_col, size_col = st.columns([3, 1])
        with info_col:
            st.write(f"文件名: **{uploaded_file.name}**")
        with size_col:
            st.write(f"大小: {uploaded_file.size / 1024:.2f} KB")

    button_col1, button_col2 = st.columns(2)
    with button_col1:
        start_clicked = st.button("开始智能核验", type="primary", disabled=st.session_state.running)
    with button_col2:
        cancel_clicked = st.button("取消当前任务", disabled=not st.session_state.running)

    if start_clicked:
        if not uploaded_file:
            st.error("请先上传 PDF 文件。")
        else:
            try:
                submission = submit_task(
                    base_url=api_base_url,
                    uploaded_file=uploaded_file,
                    api_key=api_key_input,
                    model=model_name,
                    temperature=float(temperature),
                    max_tokens=int(max_tokens),
                    topk=int(top_k),
                    dry_run=dry_run,
                )
                st.session_state.task_id = submission["task_id"]
                st.session_state.running = True
                st.session_state.last_filename = submission["filename"]
                st.session_state.last_status = submission["status"]
                st.success(f"任务已提交: {submission['task_id']}")
                st.rerun()
            except Exception as exc:
                st.error(f"任务提交失败: {exc}")

    if cancel_clicked and st.session_state.task_id:
        try:
            result = cancel_task(api_base_url, st.session_state.task_id)
            st.warning(f"取消请求已发送，当前状态: {result['status']}")
        except Exception as exc:
            st.error(f"取消任务失败: {exc}")

    if st.session_state.task_id:
        st.divider()
        st.subheader("任务执行信息")

        try:
            status_payload = fetch_task_status(api_base_url, st.session_state.task_id)
            st.session_state.last_status = status_payload
            render_status_panels(status_payload)

            current_status = status_payload.get("status", "")
            if current_status in {"completed", "cancelled"}:
                st.session_state.running = False
                if current_status == "completed":
                    try:
                        report_payload = fetch_task_report(api_base_url, st.session_state.task_id)
                        st.session_state.last_report = report_payload.get("report")
                        st.session_state.last_report_path = report_payload.get("report_path")
                    except Exception as exc:
                        st.error(f"任务已结束，但获取报告失败: {exc}")
                else:
                    st.warning("任务已取消。")
            elif current_status == "failed":
                st.session_state.running = False
                st.error("任务执行失败，请查看错误信息。")
            else:
                st.session_state.running = True
                time.sleep(POLL_INTERVAL_SECONDS)
                st.rerun()
        except Exception as exc:
            st.session_state.running = False
            st.error(f"获取任务状态失败: {exc}")

    if st.session_state.last_report:
        st.divider()
        st.success("核验完成")
        if st.session_state.last_report_path:
            st.caption(f"报告保存路径: {st.session_state.last_report_path}")

        file_name = "verification_report.md"
        if st.session_state.task_id and st.session_state.last_filename:
            stem = Path(st.session_state.last_filename).stem
            file_name = f"Report_{stem}_{st.session_state.task_id[:8]}.md"

        st.download_button(
            label="下载 Markdown 报告",
            data=st.session_state.last_report,
            file_name=file_name,
            mime="text/markdown",
            type="primary",
        )

        preview_limit = 10000
        with st.expander("报告预览", expanded=True):
            if len(st.session_state.last_report) > preview_limit:
                st.warning(f"报告较长，仅显示前 {preview_limit} 个字符。")
                st.markdown(st.session_state.last_report[:preview_limit] + "\n\n...(已截断)...")
            else:
                st.markdown(st.session_state.last_report)

        if st.button("清空当前任务记录"):
            reset_task_state(keep_report=False)
            st.rerun()


if __name__ == "__main__":
    main()
