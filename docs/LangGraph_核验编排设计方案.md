# LangGraph 核验编排设计方案

## 1. 文档目标

本文档用于说明在当前文档核验项目中，如何使用 LangGraph 作为确定性工作流编排层，替代“由 Agent 自由决定步骤执行顺序”的方案。

核心原则如下：

- 核验主流程必须是确定性的
- 5 个强规则核验步骤不能交给 Agent 自主重排
- LangGraph 负责流程编排、状态管理、分支控制、并行汇总
- LLM 只在节点内部承担语义判断、解释、补充比对等职责

---

## 2. 为什么适合用 LangGraph

当前项目的业务特点是：

- 主流程稳定：PDF -> MD -> JSON -> 5 类核验 -> 报告生成
- 核验步骤存在强约束顺序
- 某些步骤需要提前终止
- 某些步骤适合并行
- 每一步都需要保存中间状态、日志和错误信息

这类流程更像“可追踪的状态机”，而不是“开放式 Agent 对话”。

因此，推荐的定位是：

- LangGraph = 工作流编排器
- LangChain = 模型与工具调用层
- Agent = 可选增强层，不是主执行层

---

## 3. 设计目标

### 3.1 主目标

1. 保持当前核验业务顺序可控
2. 将流程状态显式化，便于调试和断点恢复
3. 为后续迁移 `info_check.py`、`env_check.py`、`location_check.py`、`cycle_check.py`、`param_check.py` 提供统一执行框架
4. 支持失败处理、条件分支和未来的并行化

### 3.2 非目标

- 不让 Agent 决定是否跳过强规则检查
- 不让模型决定主流程顺序
- 不在第一阶段引入复杂多 Agent 协作

---

## 4. 推荐总体架构

```text
Streamlit UI
    ->
LangGraph StateGraph
    ->
Node Services
    ->
LangChain LLM / Vector Retrieval / Legacy Compatibility Layer
    ->
Markdown Report
```

建议拆分为 4 层：

1. UI 层
   当前为 `langchain_app/app.py`
2. Graph 编排层
   建议新增 `langchain_app/graph/verification_graph.py`
3. Service/Check 层
   建议新增 `langchain_app/checks/*`
4. 基础设施层
   包括 `langchain_app/core/llm_client.py`、`langchain_app/core/vector_db.py`、`langchain_app/core/report_generator.py`

---

## 5. 状态模型设计

建议使用一个统一的 `VerificationState`，在图中持续传递。

```python
from typing import TypedDict, Optional, Any


class VerificationState(TypedDict, total=False):
    request_id: str
    source_pdf_path: str
    md_path: str
    json_path: str

    status: str
    progress: int

    config: Any
    runtime_cfg: Any

    embedder: Any
    llm_client: Any
    retrievers: dict

    integrity_result: dict
    environment_result: dict
    location_result: dict
    cycle_result: dict
    parameter_result: dict

    final_report: str

    logs: list[str]
    warnings: list[str]
    errors: list[str]

    should_stop: bool
    stop_reason: Optional[str]
```

### 5.1 必要字段说明

- `source_pdf_path`
  输入 PDF 路径
- `md_path` / `json_path`
  中间产物路径
- `integrity_result` 等
  各步骤结构化输出
- `should_stop`
  是否提前终止图执行
- `final_report`
  汇总生成的最终 Markdown
- `logs/warnings/errors`
  用于 UI 展示和调试追踪

### 5.2 推荐补充字段

- `instrument_type`
  用于周期/地点分支
- `certificate_meta`
  供多个节点复用的证书关键信息
- `artifacts`
  中间表格、检索命中、LLM原始输出

---

## 6. 节点设计

建议图中至少包含以下节点。

### 6.1 `init_context`

职责：

- 加载配置
- 初始化 `LLMClient`
- 加载共享 embedder
- 初始化日志容器

输入：

- `source_pdf_path`

输出：

- `config`
- `runtime_cfg`
- `embedder`
- `llm_client`
- 初始 `logs`

### 6.2 `parse_pdf`

职责：

- 执行 PDF -> MD
- 复用已有缓存逻辑

建议复用：

- `langchain_app/core/pipeline.py` 中的 `pdf_to_md_first_step`

输出：

- `md_path`

### 6.3 `parse_json`

职责：

- 执行 MD -> JSON
- 处理 JSON 缓存与刷新判定

输出：

- `json_path`
- `certificate_meta`

### 6.4 `integrity_check`

职责：

- 执行完整性检查
- 判断是否非 CNAS、字段严重缺失等
- 如果失败，设置 `should_stop = True`

输出：

- `integrity_result`
- `should_stop`
- `stop_reason`

### 6.5 `environment_check`

职责：

- 执行环境温湿度核验
- 查询温度向量库
- 在必要时调用 LLM 进行语义判定

输出：

- `environment_result`

### 6.6 `location_check`

职责：

- 校验地点是否在 CNAS 范围内
- 校验地址匹配情况

输出：

- `location_result`

### 6.7 `cycle_check`

职责：

- 根据仪器类型选择华为周期库或通用周期库
- 判断建议校准周期是否合理

输出：

- `cycle_result`

### 6.8 `parameter_check`

职责：

- 查询 CNAS 向量库
- 做参数、范围、误差、不确定度核验
- 生成最复杂的一部分结构化结果

输出：

- `parameter_result`

### 6.9 `assemble_report`

职责：

- 汇总所有节点结果
- 调用 `report_generator`
- 产出 `final_report`

输出：

- `final_report`

### 6.10 `persist_artifacts`

职责：

- 将报告和必要中间产物落盘
- 可选保存 graph state snapshot

---

## 7. 推荐图结构

### 7.1 第一阶段：确定性串行版

```text
START
  -> init_context
  -> parse_pdf
  -> parse_json
  -> integrity_check
  -> route_after_integrity
      -> environment_check
      -> location_check
      -> cycle_check
      -> parameter_check
  -> assemble_report
  -> persist_artifacts
  -> END
```

### 7.2 第二阶段：条件分支版

```text
START
  -> init_context
  -> parse_pdf
  -> parse_json
  -> integrity_check
      -> if should_stop: assemble_report
      -> else: environment_check
  -> location_check
  -> cycle_check
  -> parameter_check
  -> assemble_report
  -> END
```

### 7.3 第三阶段：部分并行版

```text
START
  -> init_context
  -> parse_pdf
  -> parse_json
  -> integrity_check
      -> if should_stop: assemble_report
      -> else:
           -> environment_check
           -> location_check
           -> cycle_check
  -> join_checks
  -> parameter_check
  -> assemble_report
  -> END
```

说明：

- `environment_check`、`location_check`、`cycle_check` 理论上可并行
- `parameter_check` 建议先保持串行，因为它复杂度最高、依赖字段较多

---

## 8. 推荐路由规则

### 8.1 完整性检查后的路由

规则：

- 如果证书不是 CNAS
- 如果关键字段缺失导致无法继续
- 如果 JSON 结构损坏

则：

- 设置 `should_stop = True`
- 直接跳转到 `assemble_report`

### 8.2 周期核验的分支

规则：

- 如果仪器命中华为专用类别，走 `huawei_cycle`
- 否则走 `general_cycle`

说明：

- 这个分支应该由确定性规则控制
- 不建议让模型来决定走哪个库

### 8.3 参数核验的内部子图

未来可以把 `parameter_check` 单独做成子图：

- `extract_rows`
- `query_kb`
- `normalize_units`
- `range_check`
- `error_check`
- `uncertainty_check`
- `merge_parameter_result`

这样可以降低 `param_check.py` 的迁移风险。

---

## 9. 状态更新规范

每个节点都建议遵守统一输出规范：

```python
return {
    "status": "Processing [3/6]: Environment check",
    "progress": 50,
    "environment_result": result,
    "logs": state.get("logs", []) + ["environment_check completed"],
}
```

统一约定：

- 节点只更新自己负责的字段
- 失败信息写入 `errors`
- 可继续但不阻断的异常写入 `warnings`
- 不直接拼接最终报告内容，尽量保留结构化结果

---

## 10. 节点返回结构建议

建议每个核验节点输出统一结构，便于报告生成和 UI 展示：

```python
{
    "name": "environment",
    "success": True,
    "should_stop": False,
    "summary": "环境条件符合要求",
    "report_markdown": "...",
    "artifacts": {
        "retrieved_docs": [...],
        "llm_response": "...",
    },
}
```

统一后有几个好处：

- `assemble_report` 简单
- UI 可以做分模块展示
- 测试只需要校验结构，不必只比对长文本

---

## 11. 推荐目录结构

```text
langchain_app/
├── app.py
├── graph/
│   ├── __init__.py
│   ├── state.py
│   ├── verification_graph.py
│   ├── routers.py
│   └── nodes/
│       ├── __init__.py
│       ├── init_context.py
│       ├── parse_pdf.py
│       ├── parse_json.py
│       ├── integrity_check.py
│       ├── environment_check.py
│       ├── location_check.py
│       ├── cycle_check.py
│       ├── parameter_check.py
│       ├── assemble_report.py
│       └── persist_artifacts.py
├── checks/
│   ├── integrity.py
│   ├── environment.py
│   ├── location.py
│   ├── cycle.py
│   └── parameter/
└── core/
    ├── llm_client.py
    ├── vector_db.py
    └── report_generator.py
```

---

## 12. 代码骨架示例

```python
from langgraph.graph import StateGraph, START, END
from langchain_app.graph.state import VerificationState
from langchain_app.graph.nodes import (
    init_context,
    parse_pdf,
    parse_json,
    integrity_check,
    environment_check,
    location_check,
    cycle_check,
    parameter_check,
    assemble_report,
)


def route_after_integrity(state: VerificationState) -> str:
    if state.get("should_stop"):
        return "assemble_report"
    return "environment_check"


def build_graph():
    graph = StateGraph(VerificationState)

    graph.add_node("init_context", init_context)
    graph.add_node("parse_pdf", parse_pdf)
    graph.add_node("parse_json", parse_json)
    graph.add_node("integrity_check", integrity_check)
    graph.add_node("environment_check", environment_check)
    graph.add_node("location_check", location_check)
    graph.add_node("cycle_check", cycle_check)
    graph.add_node("parameter_check", parameter_check)
    graph.add_node("assemble_report", assemble_report)

    graph.add_edge(START, "init_context")
    graph.add_edge("init_context", "parse_pdf")
    graph.add_edge("parse_pdf", "parse_json")
    graph.add_edge("parse_json", "integrity_check")

    graph.add_conditional_edges(
        "integrity_check",
        route_after_integrity,
        {
            "assemble_report": "assemble_report",
            "environment_check": "environment_check",
        },
    )

    graph.add_edge("environment_check", "location_check")
    graph.add_edge("location_check", "cycle_check")
    graph.add_edge("cycle_check", "parameter_check")
    graph.add_edge("parameter_check", "assemble_report")
    graph.add_edge("assemble_report", END)

    return graph.compile()
```

---

## 13. 与当前项目的结合方式

### 13.1 第一阶段

先不重写所有业务逻辑，只把 LangGraph 包在现有 pipeline 外层。

做法：

- `parse_pdf` 节点复用 `pdf_to_md_first_step`
- `parse_json` 节点复用 `md_parser_no_llm.parse_md_to_json`
- 核验节点先调用兼容层

目的：

- 先把流程编排和状态观测跑通
- 降低一次性大改的风险

### 13.2 第二阶段

逐步将旧核验逻辑迁入 `langchain_app/checks`

做法：

- `integrity_check` 先迁
- `environment_check` 和 `cycle_check` 再迁
- `location_check` 和 `parameter_check` 最后迁

### 13.3 第三阶段

增加并行执行、重试、子图和 checkpoint

---

## 14. 为什么不建议用 Agent 决定主顺序

如果让 Agent 决定 5 个强规则核验步骤的执行顺序，会带来以下问题：

1. 可预测性差
2. 很难保证不跳步骤
3. 重试行为不可控
4. 排查线上问题困难
5. 与现有核验业务规则冲突

因此更推荐：

- Graph 决定“流程”
- Service 决定“业务”
- LLM 决定“语义判断”

---

## 15. 推荐实施顺序

1. 新建 `graph/` 目录与 `VerificationState`
2. 实现串行版 StateGraph
3. 将 `langchain_app/app.py` 的执行入口切到 graph
4. 保持节点内部仍调用兼容层，先验证图正常
5. 再逐步迁移各核验模块
6. 最后决定是否在某些节点内部嵌入 Agent

---

## 16. 验收标准

### 16.1 第一阶段验收

- 可以从 `Streamlit -> Graph -> Report` 完整跑通
- 完整性失败时可以提前结束
- 所有节点状态可追踪
- 报告生成不退化

### 16.2 第二阶段验收

- 图中节点不再依赖旧 `checks` 包
- LLM 调用统一经过 `langchain_app/core/llm_client.py`
- 向量检索统一经过 `langchain_app/core/vector_db.py`

### 16.3 第三阶段验收

- 支持部分并行
- 支持 checkpoint 或中断恢复
- 节点结果可单测

---

## 17. 最终建议

对本项目而言，LangGraph 适合作为正式编排层，并且优先级较高。

推荐结论：

- 使用 LangGraph
- 不让 Agent 决定主核验顺序
- 先用 LangGraph 固化流程，再迁移业务模块
- Agent 仅作为补充能力，而不是核心执行器

这会比“直接做一个会自主决定流程的 Agent”更稳、更容易调试，也更符合当前证书核验业务的强规则特点。
