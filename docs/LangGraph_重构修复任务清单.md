# LangGraph 重构修复任务清单

## 1. 文档目的

本文档用于将当前 LangGraph 重构后的遗留问题，整理为一份可直接执行的修复任务表。

适用场景：

- 开发排期
- 代码修复跟踪
- 验收清单
- 重构收尾

当前判断基于在 `langchain` conda 环境中的实际验证结果：

- `langchain`、`langgraph`、`langchain_openai` 依赖可导入
- 但核心包仍存在循环导入
- 参数核验仍为占位实现
- 新旧实现仍在并存

---

## 2. 当前主要问题概览

当前重构状态可概括为：

- 架构已成型
- 主流程已开始切换到 LangGraph
- `checks`、`graph`、`retrieval` 三层已出现
- 但代码还未收口，仍存在关键阻塞项

核心问题有 5 类：

1. `core` 与 `graph` 之间存在循环导入
2. 多个 `checks` 模块的 `LLMClient` 调用方式错误
3. `checks/__init__.py` 导入过重，影响模块化测试
4. 参数核验仍是占位实现，不能替代原版
5. `tools` 层仍在调用旧根目录模块

---

## 3. 修复优先级说明

优先级定义如下：

- P0：不修无法继续验证或运行
- P1：不修会导致业务执行异常或结果不可信
- P2：不修会造成架构漂移、维护成本增加
- P3：文档、注释、角色定位等收尾项

---

## 4. 可执行任务表

| 优先级 | 任务名称 | 目标文件 | 修改动作 | 验收命令 |
|---|---|---|---|---|
| P0 | 修复 `core <-> graph` 循环导入 | `langchain_app/core/__init__.py` `langchain_app/core/pipeline.py` `langchain_app/graph/nodes/parse_pdf.py` | 将 `parse_pdf.py` 中对 `langchain_app.core` 的顶层依赖改为具体模块依赖，或把 `pdf_to_md_first_step` 抽到独立模块；同时精简 `core/__init__.py` 默认导出 | `D:\conda_envs\langchain\python.exe test_langchain_simple.py` |
| P0 | 解除 `checks` 对全量模块的强制导入 | `langchain_app/checks/__init__.py` | 避免包初始化时导入所有检查模块，改为轻量导出或惰性导入 | `D:\conda_envs\langchain\python.exe test_checks_simple.py` |
| P1 | 修复 `LLMClient` 调用参数错误 | `langchain_app/checks/integrity.py` `langchain_app/checks/environment.py` `langchain_app/checks/cycle.py` `langchain_app/checks/location.py` | 将 `LLMClient(cfg)` 全部改成 `LLMClient(config=cfg)` 或统一改为 `create_llm_client(cfg)` | 在 `langchain` 环境下执行相关单测或最小调用 |
| P1 | 让 Graph 可独立构建 | `langchain_app/graph/verification_graph.py` `langchain_app/graph/nodes/*` | 修完循环依赖后，确保 Graph 节点导入链可闭环，`build_verification_graph().compile()` 成功 | `D:\conda_envs\langchain\python.exe -c "from langchain_app.graph.verification_graph import build_verification_graph; build_verification_graph().compile(); print('ok')"` |
| P1 | 补齐参数核验正式实现 | `langchain_app/checks/parameter/parameter.py` `langchain_app/checks/parameter/parser.py` `langchain_app/checks/parameter/retrieval.py` `langchain_app/checks/parameter/semantic.py` `langchain_app/checks/parameter/validator.py` `langchain_app/checks/parameter/reporter.py` | 删除占位说明逻辑，补齐参数采集、知识库检索、语义筛选、验证与报告汇总，确保 `run_llm_mode()` 产出真实报告 | `D:\conda_envs\langchain\python.exe test_parameter_simple.py` |
| P1 | 校验参数核验与原版一致性 | `langchain_app/checks/parameter/*` `param_check.py` | 准备固定输入样本，对比新旧输出的核心统计、失败数、通过数、关键结论 | 编写并运行对拍脚本，例如 `test_original_vs_new.py` |
| P2 | 将 `tools` 层切到新 checks | `langchain_app/tools/example_tools.py` | 把 `info_check/environment_check/location_check/cycle_check/parameter_check` 改为调用 `langchain_app.checks.*`，移除对根目录旧模块的动态导入 | `D:\conda_envs\langchain\python.exe test_langchain_simple.py` |
| P2 | 收口 `pipeline` 职责 | `langchain_app/core/pipeline.py` | 明确 `pipeline` 是 Graph 入口兼容层，不再承担新旧双重编排职责，避免报告重复拼接 | 使用一份样本 PDF 跑完整流程人工核验输出结构 |
| P2 | 收口旧桥接依赖 | `checks/adapters.py` `llm/client.py` `kb/chroma_client.py` | 标记 deprecated，确认新代码不再依赖，后续准备删除 | `rg -n "checks\\.adapters|create_openai_like_client|get_collection\\(" .` |
| P2 | 校验主入口与 Graph 一致 | `langchain_app/app.py` | 保持入口调用 `run_verification()` 可以，但文案和注释要反映“LangGraph 主编排”事实 | `streamlit run langchain_app/app.py` |
| P3 | 更新 Agent 定位 | `langchain_app/agents/verification_agent.py` | 注释与说明改成“辅助层/解释层”，不再描述为“原始 pipeline 替身” | 导入 Agent 并查看 `get_agent_info()` |
| P3 | 修复验证脚本编码问题 | `verify_lc_architecture.py` `test_langchain_setup.py` 等 | 去掉 emoji 输出，避免 Windows GBK 终端异常 | `D:\conda_envs\langchain\python.exe verify_lc_architecture.py` |
| P3 | 清理文档与命名漂移 | `README`、`docs/*` | 将“LangChain版”表述统一调整为“LangGraph 编排 + LangChain 能力层” | 文档人工审阅 |

---

## 5. 分任务详细说明

### 任务 1：修复循环导入

#### 目标

解决以下导入链导致的失败：

```text
langchain_app.core
  -> pipeline
  -> graph
  -> nodes.parse_pdf
  -> langchain_app.core
```

#### 目标文件

- `langchain_app/core/__init__.py`
- `langchain_app/core/pipeline.py`
- `langchain_app/graph/nodes/parse_pdf.py`

#### 建议动作

1. `parse_pdf.py` 不再从 `langchain_app.core` 导入 `pdf_to_md_first_step`
2. 改为直接从实现模块导入，例如：
   - `from langchain_app.core.pipeline import pdf_to_md_first_step`
   - 或更推荐：抽到 `langchain_app/services/parsing.py`
3. `core/__init__.py` 不要一上来导出所有会触发 Graph 导入的对象

#### 推荐完成定义

- `langchain_app.core`
- `langchain_app.graph`
- `langchain_app.checks`

三者都能单独导入成功

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' test_langchain_simple.py
```

---

### 任务 2：解除 `checks` 的重导入

#### 目标

让参数子模块测试不再被无关模块拖垮。

#### 目标文件

- `langchain_app/checks/__init__.py`

#### 建议动作

1. 不在 `__init__.py` 顶层导入全部检查模块
2. 只保留轻量 `__all__`
3. 或改成惰性导入策略

#### 推荐完成定义

- `from langchain_app.checks.parameter import ...` 不再触发完整性/Graph 导入链

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
```

---

### 任务 3：修复 `LLMClient` 调用

#### 目标

确保所有新 checks 在真实调用 LLM 时不会把 `cfg` 误传到 `api_key` 位置参数。

#### 目标文件

- `langchain_app/checks/integrity.py`
- `langchain_app/checks/environment.py`
- `langchain_app/checks/cycle.py`
- `langchain_app/checks/location.py`

#### 建议动作

统一改成以下二选一：

```python
llm_client = LLMClient(config=cfg)
```

或

```python
llm_client = create_llm_client(cfg)
```

#### 推荐完成定义

- 四个 checks 模块的 LLM 初始化方式完全一致

#### 验收命令

建议增加最小验证脚本，或执行单模块 smoke test。

---

### 任务 4：让 Graph 真正可构建

#### 目标

在 `langchain` 环境中成功执行：

```python
build_verification_graph().compile()
```

#### 目标文件

- `langchain_app/graph/verification_graph.py`
- `langchain_app/graph/nodes/*`

#### 建议动作

1. 修复节点导入链
2. 确保每个节点只依赖必要模块
3. 不让 graph 在导入阶段触发全局重资源初始化

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.verification_graph import build_verification_graph; build_verification_graph().compile(); print('graph_ok')"
```

---

### 任务 5：补齐参数核验主实现

#### 目标

让参数核验不再是占位版，而是能输出真实业务核验结果。

#### 目标文件

- `langchain_app/checks/parameter/parameter.py`
- `langchain_app/checks/parameter/parser.py`
- `langchain_app/checks/parameter/retrieval.py`
- `langchain_app/checks/parameter/semantic.py`
- `langchain_app/checks/parameter/validator.py`
- `langchain_app/checks/parameter/reporter.py`

#### 建议动作

1. 删除“迁移中”“占位符”说明输出
2. 补齐：
   - 参数提取
   - 知识库检索
   - 依据语义筛选
   - 误差/范围/不确定度验证
   - 批次统计汇总
3. 让 `run_llm_mode()` 保持与原版入口兼容

#### 推荐完成定义

- `run_llm_mode()` 可对真实 JSON 产生完整参数核验 Markdown

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
```

---

### 任务 6：做新旧参数核验对拍

#### 目标

验证新参数核验不是“能跑就行”，而是关键逻辑与原版一致。

#### 目标文件

- 新增对拍脚本，例如 `test_original_vs_new.py`

#### 建议动作

对固定样本执行：

- 原版 `param_check.py`
- 新版 `langchain_app.checks.parameter.run_llm_mode`

比对以下指标：

- PASS 数量
- FAIL 数量
- REVIEW 数量
- 核心结论
- 依据匹配结果

#### 推荐完成定义

- 核心统计一致
- 差异可解释

---

### 任务 7：让 tools 层切到新 checks

#### 目标

避免 `tools` 继续调用根目录旧模块，导致新旧双轨长期共存。

#### 目标文件

- `langchain_app/tools/example_tools.py`

#### 建议动作

将以下逻辑全部改为调用新模块：

- `info_check`
- `environment_check`
- `location_check`
- `cycle_check`
- `parameter_check`

删除：

- `sys.path.insert(...)`
- 对 `info_check/env_check/location_check/cycle_check/param_check` 的动态导入

#### 推荐完成定义

- `example_tools.py` 只依赖 `langchain_app` 包内模块

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' test_langchain_simple.py
```

---

### 任务 8：收口 pipeline

#### 目标

明确 `pipeline.py` 的角色，避免同时承担：

- Graph 入口
- 旧式流程控制
- 报告拼接

#### 目标文件

- `langchain_app/core/pipeline.py`

#### 建议动作

1. 保留 `PDF -> MD` 和 `MD -> JSON` 的兼容层可以
2. 但 Graph 之后的结果汇总要避免与 `final_state.final_report` 重复拼装
3. 明确 `run_verification()` 是：
   - Graph 兼容入口
   - 还是真正 orchestrator

#### 推荐完成定义

- `pipeline` 职责单一
- 不重复拼装报告

---

### 任务 9：更新 Agent 角色

#### 目标

让 Agent 的描述与当前架构一致。

#### 目标文件

- `langchain_app/agents/verification_agent.py`

#### 建议动作

1. 注释中去掉“原始项目 pipeline”的表述
2. 明确 Agent 当前角色：
   - 辅助层
   - 解释层
   - 可选入口
3. 如果不是正式主流程，不要继续让文档暗示它是核心入口

---

### 任务 10：修复验证脚本

#### 目标

让验证脚本在 Windows + conda `langchain` 环境里稳定输出。

#### 目标文件

- `verify_lc_architecture.py`
- `test_langchain_setup.py`
- 其他含 emoji 输出的脚本

#### 建议动作

1. 去掉 emoji
2. 输出改为 ASCII 或普通中文
3. 增加 graph 构建与 checks 导入断言

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' verify_lc_architecture.py
```

---

## 6. 推荐修改顺序

建议严格按以下顺序推进：

1. 修循环导入
2. 修 `LLMClient(config=cfg)` 调用
3. 让 `checks/__init__.py` 变轻
4. 跑通 Graph 构建
5. 改 tools 到新 checks
6. 补齐参数核验
7. 做参数核验对拍
8. 收口 pipeline
9. 更新 Agent 角色
10. 清理验证脚本与旧桥接层

原因：

- 前 4 步解决“不能导入、不能运行”的阻塞
- 中间 3 步解决“业务不完整”的问题
- 最后 3 步解决“架构不收口”的问题

---

## 7. 最终完成标准

当以下条件全部满足时，可以认为这次 LangGraph 重构进入“可交付完成”状态：

1. `langchain` 环境下核心测试可通过
2. Graph 可编译、可执行
3. `checks` 模块可独立导入和测试
4. 参数核验不再是占位实现
5. `tools` 不再依赖根目录旧模块
6. 主流程正式由 LangGraph 驱动
7. Agent 角色与文档描述一致
8. 旧桥接层不再参与主执行链路

---

## 8. 建议验收命令汇总

```powershell
& 'D:\conda_envs\langchain\python.exe' test_langchain_simple.py
& 'D:\conda_envs\langchain\python.exe' test_checks_simple.py
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
& 'D:\conda_envs\langchain\python.exe' verify_lc_architecture.py
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.verification_graph import build_verification_graph; build_verification_graph().compile(); print('graph_ok')"
```

---

## 9. 结论

当前重构不是方向错误，而是典型的“主架构已经立起来，但代码收尾还没有完成”。

所以这份任务清单的重点不是推翻重做，而是：

- 先解开导入死结
- 再修正运行缺陷
- 再补齐参数核验
- 最后收口新旧双轨

只要按这个顺序推进，当前这版 LangGraph 重构是可以收敛成一版稳定交付结果的。
