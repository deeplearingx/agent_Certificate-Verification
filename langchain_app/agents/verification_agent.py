#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档核验 Agent - LangChain重构版

**角色定位**：辅助层/解释层
- 提供智能对话式核验入口
- 对核验过程和结果进行解释
- 支持工具调用和多步骤交互
- 可选的高级入口，非核心执行流程
"""

try:
    from langchain.agents import create_agent
except ModuleNotFoundError:
    create_agent = None

try:
    from langchain.tools import BaseTool
except ModuleNotFoundError:
    class BaseTool:  # type: ignore[no-redef]
        pass
from typing import List, Optional

from langchain_app.tools.example_tools import get_all_tools
from langchain_app.core import run_verification, PipelineHooks


class VerificationAgent:
    """文档核验 Agent - 智能对话式辅助层"""

    def __init__(
        self,
        llm,
        tools: Optional[List[BaseTool]] = None
    ):
        """初始化核验 Agent"""
        self.llm = llm
        self.tools = tools or get_all_tools()

    def run_verification(self, pdf_path: str) -> str:
        """运行完整的文档核验流程 - 辅助层入口

        注意：核心执行流程已由 LangGraph 接管，
        此函数提供智能对话式核验接口，增加解释能力。
        """
        from langchain_app.utils import get_app_config
        from pathlib import Path
        import threading

        config = get_app_config()
        stop_event = threading.Event()

        # 创建简单的 hooks
        class SimpleHooks(PipelineHooks):
            def __init__(self):
                self.logs = []

            def emit_info(self, message):
                self.logs.append(f"INFO: {message}")
            def emit_status(self, message):
                self.logs.append(f"STATUS: {message}")
            def emit_progress(self, value):
                self.logs.append(f"PROGRESS: {value}")
            def emit_warning(self, message):
                self.logs.append(f"WARN: {message}")
            def emit_error(self, message):
                self.logs.append(f"ERROR: {message}")
            def emit_success(self, message):
                self.logs.append(f"SUCCESS: {message}")

        hooks = SimpleHooks()

        try:
            report = run_verification(
                pdf_file_path=Path(pdf_path),
                config=config,
                hooks=hooks,
                stop_event=stop_event
            )

            if report:
                log_summary = "## 执行日志\n"
                for log in hooks.logs[-10:]:  # 只显示最后 10 条日志
                    log_summary += f"- {log}\n"

                return f"{report}\n{log_summary}"
            else:
                return f"核验失败。详细日志:\n" + "\n".join(hooks.logs)

        except Exception as e:
            error_log = "## 错误信息\n"
            error_log += f"- 错误类型: {type(e).__name__}\n"
            error_log += f"- 错误信息: {str(e)}\n"
            import traceback
            error_log += f"- 堆栈跟踪: {traceback.format_exc()}\n"
            return error_log

    async def arun_verification(self, pdf_path: str) -> str:
        """异步运行文档核验"""
        import asyncio

        return await asyncio.to_thread(self.run_verification, pdf_path)

    def get_agent_info(self) -> dict:
        """获取 Agent 信息"""
        return {
            "tool_count": len(self.tools),
            "tool_names": [tool.name for tool in self.tools],
            "model": str(self.llm) if hasattr(self.llm, "__str__") else "Unknown",
            "description": "智能对话式文档核验辅助层，提供工具调用和过程解释"
        }

    def create_simple_agent(self):
        """创建简单的 Agent (备用方法)"""
        if create_agent is None:
            raise ModuleNotFoundError("langchain is required to create a simple agent")
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt="""你是一个专业的文档核验专家，负责对校准证书进行全面的核验。

## 你的任务
1. 首先将PDF转换为Markdown格式进行解析
2. 将Markdown解析为JSON格式的数据
3. 对解析后的证书进行各项核验：
   - 参数核验：检查参数范围、误差、不确定度
   - 周期核验：检查校准周期是否符合标准
   - 地点核验：检查校准地点是否正确
   - 环境核验：检查温度、湿度等环境条件
   - 完整性核验：检查证书信息完整性

## 工作流程
1. 使用 parse_pdf_to_md 工具将PDF转换为Markdown
2. 使用 parse_md_to_json 工具解析Markdown为JSON
3. 依次运行 parameter_check、cycle_check、location_check、environment_check、info_check
4. 将所有结果组合成完整报告

## 重要提示
- 使用工具时要明确指定参数
- 如果工具返回错误信息，要及时报告
- 每个核验步骤完成后要进行总结
- 最终报告要清晰、结构化
""",
        )

    def run_with_agent(self, pdf_path: str) -> str:
        """使用 LangChain Agent 运行核验"""
        if not hasattr(self, 'agent') or not self.agent:
            self.create_simple_agent()

        try:
            prompt = f"请对以下文档进行全面核验：{pdf_path}"

            result = self.agent.invoke({
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            })

            return str(result)

        except Exception as e:
            return f"核验过程中发生错误: {str(e)}"


def create_verification_agent(llm):
    """创建并返回文档核验 Agent 实例"""
    return VerificationAgent(llm)
