# LangGraph 详细重构方案

## 1. 文档目标

本文档用于将当前项目从“LangChain 包装层 + 旧业务内核”的过渡状态，重构为“LangGraph 主流程编排 + LangChain 能力层 + 新业务模块”的正式架构。

本文档强调两个原则：

- 主流程必须是确定性工作流
- 每一步都要能具体执行、具备明确落点和验收标准

---

## 2. 重构结论

本项目更适合重构为：

- LangGraph：主流程编排层
- LangChain：模型、工具、消息、结构化输出能力层
- langchain_app/checks：业务核验层
- langchain_app/core：基础设施层
- Streamlit：交互入口
- Agent：可选解释层，不作为主流程调度层

推荐的目标架构如下：

```text
Streamlit
  -> LangGraph StateGraph
  -> checks/services
  -> LangChain model/tools/retrieval
  -> report
```

---

## 3. 当前项目存在的关键问题

当前 `langchain_app` 存在以下问题：

- 主流程仍依赖旧 `checks` 包
- 旧核验模块内部仍依赖 LlamaIndex
- 向量检索仍直接访问 `chromadb + kb/chroma_client.py`
- Agent 不是正式主链路
- 测试与依赖尚未真正闭环

这意味着当前状态还不是“已完成 LangGraph/LangChain 重构”，而是“带有 LangChain 外壳的兼容层”。

---

## 4. 总体实施路线

```text
阶段 0：冻结基线
    ->
阶段 1：P0 让工程可运行
    ->
阶段 2：引入 LangGraph 骨架
    ->
阶段 3：统一 LLM 与向量检索底座
    ->
阶段 4：将 5 个核验模块迁入 langchain_app/checks
    ->
阶段 5：让 LangGraph 成为正式主流程
    ->
阶段 6：处理 Agent 最终角色
    ->
阶段 7：下线旧兼容层
```

实施原则：

- 先让工程可运行，再迁业务
- 先统一基础设施，再拆大文件
- 先让 LangGraph 驱动流程，再逐步替换内部节点实现

---

## 5. 阶段 0：冻结基线

### 5.1 目标

在正式重构前，明确当前系统入口、依赖关系和测试状态，避免后续重构失去参照。

### 5.2 具体步骤

#### 步骤 1：记录当前入口

需要确认的入口文件：

- `app.py`
- `langchain_app/app.py`
- `run_langchain_app.py`

执行内容：

- 确认当前哪个入口是主入口
- 确认当前推荐运行方式
- 确认当前的 Streamlit 启动命令

#### 步骤 2：记录当前主流程依赖

重点文件：

- `langchain_app/core/pipeline.py`
- `checks/adapters.py`
- `checks/__init__.py`

执行内容：

- 确认 `pipeline.py` 依赖的旧模块有哪些
- 列出所有桥接导入点
- 记录 `sys.path.insert(...)` 的位置和用途

#### 步骤 3：记录当前业务入口

重点文件：

- `info_check.py`
- `env_check.py`
- `location_check.py`
- `cycle_check.py`
- `param_check.py`

执行内容：

- 列出每个模块的主函数
- 记录输入输出签名
- 记录对外部依赖的引用方式

#### 步骤 4：记录当前测试状态

重点文件：

- `test_langchain_simple.py`
- `test_langchain_setup.py`
- `test_langchain_migration.py`
- `verify_lc_architecture.py`

执行内容：

- 记录哪些测试可以运行
- 记录哪些测试失败及原因
- 生成一份“当前基线问题清单”

### 5.3 验收标准

- 形成当前入口与依赖基线
- 明确当前失败点和旧桥接层边界

---

## 6. 阶段 1：P0 让工程可运行

### 6.1 目标

让 `langchain_app` 至少具备：

- 依赖可安装
- 模块可导入
- 测试可执行
- 页面可启动

### 6.2 具体步骤

#### 步骤 1：修正依赖文件

目标文件：

- `requirements_langchain.txt`

执行内容：

- 取消注释并补全核心依赖：
  - `langchain`
  - `langchain-core`
  - `langchain-community`
  - `langchain-openai`
  - `langchain-chroma`
  - `langchain-huggingface`
  - `langgraph`
- 如有必要，锁定一组兼容版本

验收：

- 可以通过依赖安装命令完成安装

#### 步骤 2：收敛顶层导入

目标文件：

- `langchain_app/__init__.py`
- `langchain_app/core/__init__.py`

执行内容：

- 避免只导入配置模块时就拉起全部 LangChain 依赖
- 重模块改为延迟导入或最小导出

验收：

- 仅导入 `AppConfig` 时不触发 LangChain 运行时导入错误

#### 步骤 3：统一 LLMClient 构造方式

目标文件：

- `langchain_app/core/llm_client.py`
- `test_langchain_simple.py`
- `test_langchain_setup.py`
- `test_langchain_migration.py`

执行内容：

- 明确 `LLMClient` 的唯一构造方式
- 推荐保留：
  - `create_llm_client(config)`
  - 或 `LLMClient(config)`
- 清理测试中的旧调用方式

验收：

- 测试与实现签名一致

#### 步骤 4：清理测试输出编码问题

目标文件：

- `test_langchain_setup.py`
- `verify_lc_architecture.py`
- 其他测试脚本

执行内容：

- 去掉 emoji
- 避免 Windows GBK 控制台编码异常

验收：

- 测试脚本在当前 Windows 环境下可打印结果

#### 步骤 5：建立最小 smoke test

目标文件：

- 现有测试脚本或新建 `tests/langgraph/`

执行内容：

- 至少验证：
  - 配置加载
  - 核心模块导入
  - 向量库对象构建
  - 工具模块导入
  - 主应用入口启动

### 6.3 验收标准

- `python test_langchain_simple.py` 可运行
- `python verify_lc_architecture.py` 可运行
- `streamlit run langchain_app/app.py` 能起页

---

## 7. 阶段 2：引入 LangGraph 骨架

### 7.1 目标

先让 LangGraph 接管主流程编排，但节点内部仍允许调用旧兼容逻辑。

### 7.2 需要新增的目录结构

建议新增：

```text
langchain_app/
└── graph/
    ├── __init__.py
    ├── state.py
    ├── routers.py
    ├── verification_graph.py
    └── nodes/
        ├── __init__.py
        ├── init_context.py
        ├── parse_pdf.py
        ├── parse_json.py
        ├── integrity_check.py
        ├── environment_check.py
        ├── location_check.py
        ├── cycle_check.py
        ├── parameter_check.py
        └── assemble_report.py
```

### 7.3 具体步骤

#### 步骤 1：定义 `VerificationState`

目标文件：

- `langchain_app/graph/state.py`

执行内容：

- 定义统一状态对象
- 至少包含：
  - `source_pdf_path`
  - `md_path`
  - `json_path`
  - `config`
  - `runtime_cfg`
  - `embedder`
  - `llm_client`
  - `integrity_result`
  - `environment_result`
  - `location_result`
  - `cycle_result`
  - `parameter_result`
  - `final_report`
  - `logs`
  - `warnings`
  - `errors`
  - `should_stop`

验收：

- Graph 内所有节点共享同一状态模型

#### 步骤 2：定义节点函数

目标文件：

- `langchain_app/graph/nodes/*`

执行内容：

- 每个节点只负责一个明确职责
- 节点先用兼容实现，不急于全部重写

推荐节点：

- `init_context`
- `parse_pdf`
- `parse_json`
- `integrity_check`
- `environment_check`
- `location_check`
- `cycle_check`
- `parameter_check`
- `assemble_report`

验收：

- 每个节点具备明确输入输出

#### 步骤 3：构建串行 StateGraph

目标文件：

- `langchain_app/graph/verification_graph.py`

执行内容：

- 使用 `StateGraph` 构建流程
- 先按固定顺序串行：
  - `init_context`
  - `parse_pdf`
  - `parse_json`
  - `integrity_check`
  - `environment_check`
  - `location_check`
  - `cycle_check`
  - `parameter_check`
  - `assemble_report`

验收：

- `graph.invoke(initial_state)` 可以跑完整链路

#### 步骤 4：增加第一个条件路由

目标文件：

- `langchain_app/graph/routers.py`
- `langchain_app/graph/verification_graph.py`

执行内容：

- 在 `integrity_check` 后增加条件边：
  - `should_stop=True` -> `assemble_report`
  - `should_stop=False` -> 继续后续步骤

验收：

- 非 CNAS 或严重缺失时能提前结束

### 7.4 阶段验收标准

- LangGraph 已接管主流程
- 尽管节点内部仍可能是旧实现，但流程已可追踪

---

## 8. 阶段 3：统一基础设施底座

### 8.1 目标

在正式迁移业务模块前，先统一：

- LLM 调用入口
- 向量检索入口
- embedder 生命周期

### 8.2 子阶段 A：统一 LLM 调用

#### 步骤 1：扩展新 LLMClient

目标文件：

- `langchain_app/core/llm_client.py`

执行内容：

- 提供统一接口：
  - `invoke_text(system_prompt, user_prompt)`
  - `invoke_messages(messages)`
  - `invoke_structured(...)`
- 统一错误处理、超时、重试

验收：

- 新 LLMClient 能满足旧模块迁移需求

#### 步骤 2：清点旧 LlamaIndex 依赖点

重点文件：

- `llm/client.py`
- `env_check.py`
- `cycle_check.py`
- `location_check.py`

执行内容：

- 找出所有 `OpenAILike`
- 找出所有 `ChatMessage`、`MessageRole`

验收：

- 形成完整替换清单

#### 步骤 3：按顺序替换旧模块

推荐顺序：

1. `env_check.py`
2. `cycle_check.py`
3. `location_check.py`

执行内容：

- 去掉 `llama_index` 导入
- 内部改走 `langchain_app/core/llm_client.py`
- 保持输出报告格式兼容

验收：

- 运行链路里不再依赖 LlamaIndex

### 8.3 子阶段 B：统一向量检索

#### 步骤 1：扩展 VectorDatabase

目标文件：

- `langchain_app/core/vector_db.py`

执行内容：

- 增加统一构造方式
- 增加稳定的 `similarity_search` 和带分数搜索
- 增加结果标准化处理

验收：

- 可作为统一向量检索底座

#### 步骤 2：新增 retrieval 层

建议新增目录：

```text
langchain_app/
└── retrieval/
    ├── __init__.py
    ├── cnas.py
    ├── temperature.py
    ├── address.py
    └── cycle.py
```

执行内容：

- 每个业务库单独封装
- 屏蔽 collection 名称与底层查询细节

验收：

- 业务模块不再直接管理 collection

#### 步骤 3：统一 embedder 生命周期

目标文件：

- `langchain_app/core/pipeline.py`
- LangGraph `init_context`
- 旧业务模块

执行内容：

- embedder 统一在入口层初始化
- 通过 state 注入到节点
- 禁止业务模块内部自行加载 `SentenceTransformer`

验收：

- embedder 只初始化一次

#### 步骤 4：替换旧检索调用

重点文件：

- `env_check.py`
- `cycle_check.py`
- `location_check.py`
- `param_check.py`
- `kb/chroma_client.py`

执行内容：

- 用新 retrieval service 替换 `get_collection(...)`
- 替换 `collection.query(...)`

验收：

- 业务模块不再直接操作 Chroma collection

### 8.4 阶段验收标准

- 没有 LlamaIndex 运行时依赖
- 检索调用已统一收口
- embedder 生命周期统一

---

## 9. 阶段 4：5 个核验模块迁入 langchain_app/checks

### 9.1 目标

把正式业务逻辑从根目录脚本迁入 `langchain_app/checks`，为 LangGraph 节点提供正式实现。

### 9.2 目录设计

建议新增：

```text
langchain_app/
└── checks/
    ├── __init__.py
    ├── base.py
    ├── integrity.py
    ├── environment.py
    ├── location.py
    ├── cycle.py
    └── parameter/
        ├── __init__.py
        ├── parser.py
        ├── retrieval.py
        ├── matcher.py
        └── report.py
```

### 9.3 迁移顺序

#### 第一步：迁 `info_check.py`

目标文件：

- 源：`info_check.py`
- 目标：`langchain_app/checks/integrity.py`

原因：

- 依赖最少
- 不使用 LlamaIndex
- 最适合作为迁移模板

执行内容：

- 抽离字段清洗、完整性判断、终止规则
- 保持原报告格式兼容

验收：

- LangGraph 中 `integrity_check` 节点可调用新模块

#### 第二步：迁 `env_check.py`

目标文件：

- 源：`env_check.py`
- 目标：`langchain_app/checks/environment.py`

执行内容：

- 替换成统一的 retrieval + LLMClient
- 保持环境核验 Markdown 输出兼容

验收：

- 不再依赖旧 `env_check.py`

#### 第三步：迁 `cycle_check.py`

目标文件：

- 源：`cycle_check.py`
- 目标：`langchain_app/checks/cycle.py`

执行内容：

- 抽离仪器类型判断
- 统一华为周期与通用周期检索路径

验收：

- 不再依赖旧 `cycle_check.py`

#### 第四步：迁 `location_check.py`

目标文件：

- 源：`location_check.py`
- 目标：`langchain_app/checks/location.py`

执行内容：

- 拆分为：
  - CNAS 范围匹配
  - 地址匹配
  - LLM 语义判定

验收：

- 不再依赖旧 `location_check.py`

#### 第五步：迁 `param_check.py`

目标文件：

- 源：`param_check.py`
- 目标：`langchain_app/checks/parameter/*`

执行内容：

- 不整体平移
- 先拆成子模块：
  - `parser.py`
  - `retrieval.py`
  - `matcher.py`
  - `report.py`

验收：

- 参数核验可以模块化测试

### 9.4 兼容策略

迁移期间，旧根目录文件可暂时保留为 wrapper：

```python
from langchain_app.checks.environment import check_environment
```

### 9.5 阶段验收标准

- 5 个核验模块正式位于 `langchain_app/checks`
- 根目录旧文件只剩 wrapper 或已删除

---

## 10. 阶段 5：让 LangGraph 成为正式主流程

### 10.1 目标

由 LangGraph 正式接管 Streamlit 入口后的完整执行链路。

### 10.2 具体步骤

#### 步骤 1：重写 pipeline 的角色

目标文件：

- `langchain_app/core/pipeline.py`

执行内容：

- 不再作为“旧流程 + 兼容桥接”的主实现
- 改成：
  - graph 入口封装
  - 或纯兼容入口

推荐方式：

- `run_verification(...)` 内部调用 `build_graph().invoke(initial_state)`

验收：

- pipeline 不再 import 旧 `checks`

#### 步骤 2：移除动态路径桥接

目标文件：

- `langchain_app/core/pipeline.py`

执行内容：

- 去掉 `sys.path.insert(...)`
- 去掉根目录动态导入

验收：

- 所有依赖都来自正式 Python 包路径

#### 步骤 3：让 Streamlit 正式接入 Graph

目标文件：

- `langchain_app/app.py`

执行内容：

- UI 不再直接调用旧式 pipeline 串行逻辑
- 改为调用 Graph 入口

验收：

- `Streamlit -> Graph -> checks -> report` 全流程跑通

#### 步骤 4：把 Graph 状态映射到 UI

目标文件：

- `langchain_app/app.py`
- Graph 节点实现

执行内容：

- 将 state 中的 `status/progress/logs/warnings/errors` 映射到 UI
- 支持更清晰的步骤展示

验收：

- 用户可看到明确阶段进度和错误位置

#### 步骤 5：第二轮引入并行

可考虑并行的节点：

- `environment_check`
- `location_check`
- `cycle_check`

保守策略：

- 第一轮图保持串行
- 第二轮再做局部并行

### 10.3 阶段验收标准

- 正式入口由 LangGraph 驱动
- 不再依赖旧 `checks/adapters.py`
- Graph 成为唯一主流程实现

---

## 11. 阶段 6：处理 Agent 最终角色

### 11.1 目标

明确 Agent 在新架构中的职责，防止继续出现“文档说 Agent 是核心，代码主流程不用 Agent”的不一致问题。

### 11.2 推荐结论

推荐：

- 保留 Agent
- 但不作为正式主流程执行器

推荐定位：

- LangGraph：正式编排层
- checks/services：正式业务层
- Agent：可选解释层

### 11.3 具体步骤

#### 步骤 1：降级 VerificationAgent 的职责

目标文件：

- `langchain_app/agents/verification_agent.py`

执行内容：

- 不再让它承担主流程执行
- 只保留：
  - 结果解释
  - 核验摘要
  - 异常诊断问答
  - 报告重写

#### 步骤 2：如保留 `create_agent(...)`，只放在结果层

执行内容：

- 让 Agent 消费 Graph 产生的结构化结果
- 不让 Agent 决定主流程顺序

#### 步骤 3：更新 README 和文档

执行内容：

- 明确写清：
  - 主流程是 LangGraph
  - Agent 是增强层

### 11.4 阶段验收标准

- Agent 不再被误认为主流程
- 文档与代码角色一致

---

## 12. 阶段 7：下线旧兼容层

### 12.1 目标

在新架构稳定后，清理旧桥接逻辑和重复实现。

### 12.2 具体步骤

#### 步骤 1：清理旧桥接层

重点文件：

- `checks/adapters.py`
- `checks/__init__.py`
- `llm/client.py`
- `kb/chroma_client.py`

执行内容：

- 标记 deprecated
- 然后删除或归档

#### 步骤 2：清理旧业务入口

重点文件：

- `info_check.py`
- `env_check.py`
- `location_check.py`
- `cycle_check.py`
- `param_check.py`

执行内容：

- 若仍需兼容，保留薄包装
- 否则删除

#### 步骤 3：清理过时文档

重点文件：

- `langchain_refactor_plan.md`
- `langchain_migration_plan.md`
- `langchain_refactor_guide.md`

执行内容：

- 明确废弃状态
- 统一到最新 LangGraph 文档体系

### 12.3 阶段验收标准

- 新架构目录是唯一正式实现
- 旧桥接层不再参与主执行链路

---

## 13. 推荐排期

### 第 1 周

- 完成阶段 0
- 完成阶段 1
- 建立 LangGraph 骨架

### 第 2 周

- 完成阶段 3
- 统一 LLM 与检索底座

### 第 3 周

- 迁移 `integrity.py`
- 迁移 `environment.py`

### 第 4 周

- 迁移 `cycle.py`
- 迁移 `location.py`

### 第 5-6 周

- 拆分并迁移 `parameter/*`

### 第 7 周

- 让 LangGraph 成为正式主流程

### 第 8 周

- 明确 Agent 最终角色
- 清理旧兼容层

---

## 14. 每个阶段的完成定义

### 阶段 1 完成

- 工程能安装、导入、启动、运行最小测试

### 阶段 2 完成

- LangGraph 已正式接管流程编排骨架

### 阶段 3 完成

- 无 LlamaIndex 运行时依赖
- 无散落的直接 Chroma 查询

### 阶段 4 完成

- 5 个核验模块迁入 `langchain_app/checks`

### 阶段 5 完成

- Streamlit 正式走 LangGraph 主流程

### 阶段 6 完成

- Agent 只承担增强职责

### 阶段 7 完成

- 旧桥接层退出主执行链路

---

## 15. 风险与控制建议

### 风险 1：参数核验迁移成本极高

原因：

- `param_check.py` 体量大
- 检索、规则、报告耦合严重

控制建议：

- 最后迁
- 先拆再迁
- 不直接整体搬运

### 风险 2：LLM 迁移后行为波动

原因：

- LangChain 与原 LlamaIndex 的消息组织可能不同

控制建议：

- 先迁简单模块
- 固定提示词
- 做基线对比

### 风险 3：双系统长期并存

原因：

- 如果兼容层保留过久，新旧实现会持续漂移

控制建议：

- 每完成一块就明确下线旧入口

### 风险 4：过早引入 Agent 复杂度

原因：

- 主流程本来就是强规则流程

控制建议：

- Agent 延后
- 优先保证 Graph 主流程稳定

---

## 16. 最终建议

最稳妥的重构路径不是“直接做一个万能 Agent”，而是：

1. 先让工程可运行
2. 再让 LangGraph 接管流程骨架
3. 再统一 LLM 与检索底座
4. 再逐步迁移 5 个核验模块
5. 最后处理 Agent 和旧兼容层

对本项目而言，正式目标应该是：

- 用 LangGraph 固化流程
- 用 LangChain 统一能力接入
- 用模块化重构逐步替换旧实现

这条路线最可控、最可测，也最符合当前证书核验业务的强规则特点。
