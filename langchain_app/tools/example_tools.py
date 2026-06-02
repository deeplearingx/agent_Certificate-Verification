#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档核验工具 - LangChain重构版

包含与原始项目功能匹配的各项核验工具
"""

try:
    from langchain.tools import tool
except ModuleNotFoundError:
    def tool(*args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]

        def decorator(func):
            return func

        return decorator
from typing import List, Dict, Any, Optional
from pathlib import Path
import json


@tool
def parse_pdf_to_md(pdf_path: str) -> str:
    """
    将 PDF 文件转换为 Markdown 格式

    Args:
        pdf_path: PDF 文件路径

    Returns:
        str: Markdown 内容，或者错误信息
    """
    from langchain_app.core import pdf_to_md_first_step
    from langchain_app.utils import get_app_config
    import threading

    try:
        config = get_app_config()
        stop_event = threading.Event()
        from langchain_app.core import PipelineHooks

        md_path = pdf_to_md_first_step(
            Path(pdf_path),
            config,
            PipelineHooks(),
            stop_event
        )

        if md_path and md_path.exists():
            return md_path.read_text(encoding="utf-8")
        else:
            return "PDF转换MD失败：未生成输出文件"

    except Exception as e:
        return f"PDF转换MD失败：{str(e)}"


@tool
def parse_md_to_json(md_content: str, output_dir: str = None) -> str:
    """
    将 Markdown 内容解析为 JSON 格式

    Args:
        md_content: Markdown 内容
        output_dir: 输出目录（可选）

    Returns:
        str: JSON 字符串，或者错误信息
    """
    try:
        from langchain_app.utils import get_app_config
        import tempfile
        from pathlib import Path
        import importlib.util

        # 检查是否能找到 md_parser_no_llm 模块
        config = get_app_config()
        project_root = config.root_dir
        parser_path = project_root / "md_parser_no_llm.py"

        if not parser_path.exists():
            return "MD解析JSON失败：找不到 md_parser_no_llm.py"

        # 临时保存为文件
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False) as f:
            f.write(md_content)
            temp_md_path = f.name

        out_dir = output_dir or str(config.local_json_dir)

        try:
            import sys
            sys.path.insert(0, str(project_root))
            import md_parser_no_llm

            result = md_parser_no_llm.parse_md_to_json(
                md_path=temp_md_path,
                out_dir=out_dir
            )

            if result:
                json_file = Path(temp_md_path).with_suffix(".json").name
                json_path = Path(out_dir) / json_file
                if json_path.exists():
                    return json_path.read_text(encoding="utf-8")
                else:
                    return "MD解析JSON失败：未生成JSON文件"
            else:
                return "MD解析JSON失败：解析器返回空结果"

        finally:
            import os
            os.unlink(temp_md_path)

    except Exception as e:
        return f"MD解析JSON失败：{str(e)}"


@tool
def info_check(json_content: str) -> str:
    """
    信息完整性核验

    Args:
        json_content: JSON 内容

    Returns:
        str: 核验报告
    """
    try:
        from langchain_app.utils import get_app_config
        import tempfile
        import os
        from langchain_app.checks import check_certificate_integrity

        config = get_app_config()

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as f:
            f.write(json_content)
            temp_json_path = f.name

        try:
            report = check_certificate_integrity(
                temp_json_path,
                cfg=config
            )

            return report

        finally:
            os.unlink(temp_json_path)

    except Exception as e:
        return f"信息完整性核验失败：{str(e)}"


@tool
def environment_check(json_content: str) -> str:
    """
    环境条件核验

    Args:
        json_content: JSON 内容

    Returns:
        str: 核验报告
    """
    try:
        from langchain_app.utils import get_app_config
        import tempfile
        import os
        from langchain_app.checks import check_environment

        config = get_app_config()

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as f:
            f.write(json_content)
            temp_json_path = f.name

        try:
            report = check_environment(
                temp_json_path,
                config
            )

            return report

        finally:
            os.unlink(temp_json_path)

    except Exception as e:
        return f"环境条件核验失败：{str(e)}"


@tool
def location_check(json_content: str) -> str:
    """
    校准地点核验

    Args:
        json_content: JSON 内容

    Returns:
        str: 核验报告
    """
    try:
        from langchain_app.utils import get_app_config
        import tempfile
        import os
        from langchain_app.checks.location import check_location
        from langchain_app.core import load_shared_embedder

        config = get_app_config()

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as f:
            f.write(json_content)
            temp_json_path = f.name

        try:
            embedder = load_shared_embedder(str(config.embed_model_path))

            report = check_location(
                temp_json_path,
                cfg=config,
                embedder_obj=embedder
            )

            return report

        finally:
            os.unlink(temp_json_path)

    except Exception as e:
        return f"校准地点核验失败：{str(e)}"


@tool
def cycle_check(json_content: str) -> str:
    """
    校准周期核验

    Args:
        json_content: JSON 内容

    Returns:
        str: 核验报告
    """
    try:
        from langchain_app.utils import get_app_config
        import tempfile
        import os
        from langchain_app.checks.cycle import check_cycle_reasonableness

        config = get_app_config()

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as f:
            f.write(json_content)
            temp_json_path = f.name

        try:
            report = check_cycle_reasonableness(
                temp_json_path,
                config
            )

            return report

        finally:
            os.unlink(temp_json_path)

    except Exception as e:
        return f"校准周期核验失败：{str(e)}"


@tool
def parameter_check(json_content: str) -> str:
    """
    参数与不确定度核验

    Args:
        json_content: JSON 内容

    Returns:
        str: 核验报告
    """
    try:
        from langchain_app.utils import get_app_config
        import tempfile
        import os
        from langchain_app.checks.parameter import run_llm_mode
        from langchain_app.core import load_shared_embedder

        config = get_app_config()

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as f:
            f.write(json_content)
            temp_json_path = f.name

        try:
            embedder = load_shared_embedder(str(config.embed_model_path))

            report = run_llm_mode(
                temp_json_path,
                config,
                embedder_obj=embedder
            )

            return report

        finally:
            os.unlink(temp_json_path)

    except Exception as e:
        return f"参数与不确定度核验失败：{str(e)}"


def get_all_tools() -> List:
    """
    获取所有工具的列表

    Returns:
        List: 所有核验工具的列表
    """
    return [
        parse_pdf_to_md,
        parse_md_to_json,
        info_check,
        environment_check,
        location_check,
        cycle_check,
        parameter_check
    ]
