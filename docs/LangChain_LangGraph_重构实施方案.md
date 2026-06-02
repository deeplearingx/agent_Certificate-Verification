# LangChain / LangGraph 重构实施方案

## 1. 文档目标

本文档用于将当前项目的 LangChain 重构工作拆解为一套可执行的实施方案，覆盖以下阶段：

- P0：依赖、测试、启动可用
- P1：LLM 调用迁移，去掉旧 LlamaIndex 依赖
- P1：向量检索统一收口
- P2：5 个核验模块逐个迁入 `langchain_app`
- P2：Pipeline 去旧 `checks` 依赖
- P3：决定 Agent 是否保留为正式架构

本文档默认的总体架构方向为：

- LangGraph 作为正式工作流编排层
- LangChain 作为模型和工具集成层
- `langchain_app` 作为新架构承载目录
- 旧根目录脚本作为阶段性兼容层，逐步退出

---

## 2. 当前问题概览

### 2.1 当前现状

目前 `langchain_app` 已经具备：

- 独立目录结构
- 新的配置层
- 新的 Streamlit 入口
- `tool` 包装层
- 初步的 `LLMClient`、`VectorDatabase`、`VerificationAgent`

但核心问题是：

- 主流程仍然依赖旧 `checks` 包
- 旧核验模块内部仍在使用 LlamaIndex
- 向量检索仍直接调用 `chromadb + kb/chroma_client.py`
- Agent 不是正式执行链路
- 测试与依赖还没有闭环

### 2.2 本次重构的真正目标

不是“再包一层”，而是完成以下替换：

1. 流程编排从旧 pipeline 升级为 LangGraph
2. LLM 调用统一收口到 `langchain_app/core/llm_client.py`
3. 向量检索统一收口到 `langchain_app/core/vector_db.py`
4. 5 个核验模块正式迁入 `langchain_app/checks`
5. 旧 `checks` 与根目录脚本逐步退场

---

## 3. 推荐总体实施顺序

```text
P0 基础可运行
    ->
P1 统一 LLM 与向量检索底座
    ->
P2 迁移 5 个核验模块
    ->
P2 用 LangGraph 重写主流程编排
    ->
P3 决定 Agent 的最终角色
```

实施原则：

- 先修基础设施，再迁核心业务
- 先统一底座，再拆大文件
- 先让新架构跑通，再删除旧代码

---

## 4. P0：依赖、测试、启动可用

### 4.1 目标

先把 LangChain 版从“概念上存在”变成“当前环境可启动、可导入、可测试”。

### 4.2 需要处理的问题

当前存在的问题包括：

- `langchain_openai` 等核心依赖未纳入有效安装清单
- 某些测试脚本与 `LLMClient` 接口不一致
- Windows 控制台输出含 emoji，可能触发编码错误
- `langchain_app/__init__.py` 过早导入重模块

### 4.3 具体步骤

#### 步骤 1：修正依赖文件

目标文件：

- `requirements_langchain.txt`

动作：

- 取消注释 LangChain 相关依赖
- 明确最小可运行依赖集合
- 补充 `langgraph`
- 必要时锁定一组已验证版本

建议最小集合：

- `langchain`
- `langchain-core`
- `langchain-community`
- `langchain-openai`
- `langchain-chroma`
- `langchain-huggingface`
- `langgraph`

#### 步骤 2：收敛包初始化导入

目标文件：

- `langchain_app/__init__.py`
- `langchain_app/core/__init__.py`

动作：

- 避免顶层直接导入所有重量级模块
- 允许只导入 `AppConfig` 时不强制加载 LangChain 运行时

预期收益：

- 降低导入失败面
- 更便于测试单模块

#### 步骤 3：统一 `LLMClient` 构造方式

目标文件：

- `langchain_app/core/llm_client.py`
- `test_langchain_migration.py`
- `test_langchain_setup.py`
- `test_langchain_simple.py`

动作：

- 明确 `LLMClient` 接口只保留一种构造方式
- 推荐使用 `LLMClient(config: AppConfig)` 或 `create_llm_client(config)`
- 清理测试中的过时调用写法

#### 步骤 4：清理测试输出编码风险

目标文件：

- `test_langchain_setup.py`
- `verify_lc_architecture.py`
- 其他测试脚本

动作：

- 去掉 emoji 输出
- 控制输出为 ASCII 或纯中文
- 确保 Windows GBK 控制台可执行

#### 步骤 5：建立统一的 smoke test

目标文件：

- `tests/` 或现有 `test_langchain_*.py`

动作：

- 建立最小验证链路：
  - 配置加载
  - 核心模块导入
  - 向量库对象构建
  - 工具列表加载
  - 主应用入口可启动

建议拆成：

- `test_langchain_imports.py`
- `test_langchain_runtime.py`
- `test_langchain_smoke.py`

### 4.4 验收标准

- `pip install -r requirements_langchain.txt` 可成功
- `python test_langchain_simple.py` 可通过
- `python verify_lc_architecture.py` 可通过
- `streamlit run langchain_app/app.py` 可启动

### 4.5 风险

- 旧依赖与新依赖版本冲突
- 某些包在当前环境下需要额外系统依赖
- 启动成功不代表业务逻辑已完成迁移

---

## 5. P1：LLM 调用迁移，去掉旧 LlamaIndex 依赖

### 5.1 目标

让所有需要 LLM 的业务模块统一通过 `langchain_app/core/llm_client.py` 访问模型，不再依赖 `llm/client.py` 和 `llama_index`。

### 5.2 当前依赖点

重点文件：

- `llm/client.py`
- `env_check.py`
- `cycle_check.py`
- `location_check.py`

这些文件中当前仍存在：

- `create_openai_like_client`
- `ChatMessage`
- `MessageRole`
- `OpenAILike`

### 5.3 目标设计

在新架构中，推荐只保留一个正式 LLM 入口：

- `langchain_app/core/llm_client.py`

建议能力：

- `invoke_text(system_prompt, user_prompt)`
- `invoke_messages(messages)`
- `invoke_structured(schema, prompt)`
- 统一超时、重试、异常包装

### 5.4 具体步骤

#### 步骤 1：扩展新 `LLMClient`

目标文件：

- `langchain_app/core/llm_client.py`

动作：

- 增加消息列表调用接口
- 增加结构化输出接口
- 增加统一错误模型
- 明确模型配置从 `AppConfig` 注入

#### 步骤 2：迁移 `env_check.py`

原因：

- 逻辑相对清晰
- 检索 + LLM 判定链条较短

动作：

- 去掉 `llama_index` 导入
- 改用 `LLMClient`
- 保持输出报告格式不变

#### 步骤 3：迁移 `cycle_check.py`

动作：

- 保留业务规则
- 改写内部 LLM 对话调用
- 不改变对外函数签名，先保证兼容

#### 步骤 4：迁移 `location_check.py`

动作：

- 将地点相关 LLM 判断迁移到 `LLMClient`
- 保持检索逻辑先不大改，只先替换 LLM

#### 步骤 5：删除或冻结旧 `llm/client.py`

动作：

- 所有业务模块迁移完成后，把旧客户端标为 deprecated
- 最终仅保留兼容调用或删除

### 5.5 验收标准

- 运行路径中不再 import `llama_index`
- `env_check.py`、`cycle_check.py`、`location_check.py` 全部改走新 LLMClient
- 报告内容与旧版核心结论一致

### 5.6 风险

- LangChain 与 LlamaIndex 输出格式不同，可能导致提示词行为波动
- 某些报告文案可能会轻微变化

---

## 6. P1：向量检索统一收口

### 6.1 目标

让所有知识库访问都通过 `langchain_app/core/vector_db.py` 或其上层服务完成，不再让业务模块直接访问 `chromadb` collection。

### 6.2 当前问题

当前业务文件直接依赖：

- `kb/chroma_client.py`
- `collection.query(...)`
- `SentenceTransformer(...)`

这导致：

- 检索接口不统一
- 嵌入模型重复加载
- 查询结果结构不一致
- 难以替换底层实现

### 6.3 目标设计

建议分两层：

#### 基础层

- `langchain_app/core/vector_db.py`

职责：

- 连接 Chroma
- 统一相似度搜索接口
- 返回标准化文档对象

#### 业务层

建议新增：

- `langchain_app/retrieval/temperature.py`
- `langchain_app/retrieval/address.py`
- `langchain_app/retrieval/cycle.py`
- `langchain_app/retrieval/cnas.py`

职责：

- 封装 collection 名称
- 封装不同库的查询逻辑
- 处理特定业务过滤条件

### 6.4 具体步骤

#### 步骤 1：扩展 `VectorDatabase`

目标文件：

- `langchain_app/core/vector_db.py`

动作：

- 增加按 collection 构建实例的方法
- 增加统一 `similarity_search_with_score`
- 增加标准化结果转换函数

#### 步骤 2：统一 embedder 生命周期

目标文件：

- `langchain_app/core/pipeline.py`
- 各业务模块

动作：

- 统一由 pipeline 或 graph 初始化共享 embedder
- 禁止业务模块内部自行 new `SentenceTransformer`

#### 步骤 3：封装业务 retriever

目标文件：

- 新建 `langchain_app/retrieval/*`

动作：

- 对温度库、地址库、周期库、CNAS库分别封装
- 业务层只调用 retriever，不直接访问 collection

#### 步骤 4：替换现有查询入口

目标文件：

- `env_check.py`
- `cycle_check.py`
- `location_check.py`
- `param_check.py`

动作：

- 删除 `get_collection(...)`
- 删除 `collection.query(...)`
- 改为调用新 retrieval service

### 6.5 验收标准

- 核验模块不再直接 import `kb.chroma_client`
- 核验模块不再直接执行 `collection.query(...)`
- 嵌入模型只初始化一次

### 6.6 风险

- 不同 collection 的原始数据格式不完全一致
- `param_check.py` 对底层结果结构依赖最深，改动风险最大

---

## 7. P2：5 个核验模块逐个迁入 `langchain_app`

### 7.1 目标

将 5 个核心核验模块正式迁入新架构目录，不再长期依赖根目录脚本。

### 7.2 目标目录

建议新建：

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

### 7.3 迁移顺序建议

#### 第一优先级：完整性核验

源文件：

- `info_check.py`

原因：

- 依赖最少
- 不依赖 LlamaIndex
- 适合作为迁移模板

目标：

- 产出 `langchain_app/checks/integrity.py`

#### 第二优先级：环境核验

源文件：

- `env_check.py`

原因：

- 可以作为“LLM + 检索迁移”的标准样板

目标：

- 产出 `langchain_app/checks/environment.py`

#### 第三优先级：周期核验

源文件：

- `cycle_check.py`

目标：

- 产出 `langchain_app/checks/cycle.py`

#### 第四优先级：地点核验

源文件：

- `location_check.py`

目标：

- 产出 `langchain_app/checks/location.py`

建议拆分：

- CNAS 范围匹配
- 地址匹配
- LLM 判定

#### 第五优先级：参数核验

源文件：

- `param_check.py`

原因：

- 文件体量大
- 规则复杂
- 检索耦合深

建议：

- 不直接平移
- 先拆再迁

### 7.4 迁移方法

每个模块迁移时遵循以下步骤：

1. 保留旧入口函数签名
2. 把纯规则逻辑先抽成内部函数
3. 把 LLM 调用替换为 `LLMClient`
4. 把检索调用替换为 retriever
5. 定义统一结果结构
6. 保持 Markdown 输出兼容

### 7.5 兼容策略

迁移期间，根目录旧文件可以暂时保留为 wrapper：

```python
from langchain_app.checks.environment import check_environment
```

这样可以降低一次性切换风险。

### 7.6 验收标准

- 5 个主核验实现都位于 `langchain_app/checks/`
- 根目录脚本仅做兼容转发或已删除
- 模块可独立单测

---

## 8. P2：Pipeline 去旧 `checks` 依赖

### 8.1 目标

让 `langchain_app/core/pipeline.py` 不再依赖旧 `checks` 包和根目录核验脚本，而是直接编排新架构中的 check/service。

### 8.2 当前问题

当前 pipeline 中还存在：

- `sys.path.insert(...)`
- 动态导入旧模块
- `from checks import ...`
- 调用旧 `runner.run(...)`

这说明目前的 pipeline 仍是桥接层，不是正式实现。

### 8.3 具体步骤

#### 步骤 1：建立新的 check registry

目标文件：

- `langchain_app/core/pipeline.py`
- `langchain_app/checks/__init__.py`

动作：

- 直接导入新 `integrity/environment/location/cycle/parameter` 模块
- 不再依赖旧 runner

#### 步骤 2：移除旧 `checks` 适配器

目标文件：

- `checks/adapters.py`
- `checks/__init__.py`

动作：

- 在新 pipeline 完成后逐步废弃旧 adapters

#### 步骤 3：分离编排和业务

目标文件：

- `langchain_app/core/pipeline.py`

动作：

- pipeline 只负责调用顺序、状态推进、错误处理
- 业务模块只负责核验逻辑

#### 步骤 4：迁移到 LangGraph

建议：

- 不要在当前 pipeline 上继续累积复杂性
- P2 后半段直接让 `pipeline.py` 变成 graph 的兼容入口

例如：

- `run_verification(...)` 内部调用 `build_graph().invoke(state)`

### 8.4 验收标准

- `pipeline.py` 不再 import `checks`
- `pipeline.py` 不再有 `sys.path.insert(...)` 形式的桥接导入
- 主流程完全跑在 `langchain_app` 新模块上

---

## 9. P3：决定 Agent 是否保留为正式架构

### 9.1 目标

明确 Agent 在新系统中的角色，避免继续出现“文档里写 Agent 是核心，实际主流程却不用 Agent”的架构偏差。

### 9.2 推荐结论

推荐保留 Agent，但不让它成为正式主流程执行器。

更准确的定位是：

- LangGraph = 正式编排层
- Check/Service = 正式业务层
- Agent = 可选增强层

### 9.3 Agent 适合做什么

适合的职责：

- 对核验结果做自然语言解释
- 在某一步异常时给出诊断建议
- 为用户提供交互式问答
- 对最终报告做总结或重写

### 9.4 Agent 不适合做什么

不建议承担：

- 决定 5 个强规则核验步骤是否执行
- 决定主流程顺序
- 决定是否跳过参数核验
- 替代硬规则流程控制

### 9.5 两种可选方案

#### 方案 A：保留为 experimental

做法：

- 保留 `VerificationAgent`
- 在 README 中标注为实验能力
- 不作为主入口

适用：

- 需要演示 LangChain Agent 能力
- 需要保留灵活问答接口

#### 方案 B：正式保留为解释层

做法：

- 在 Graph 执行完成后调用 Agent
- Agent 接收结构化核验结果
- 只负责解释与总结

适用：

- 希望保留更好的交互体验
- 但又不影响主流程稳定性

### 9.6 不推荐方案

不推荐把 Agent 作为主执行器：

- 不稳定
- 不利于追责
- 不利于测试
- 不适合强规则核验业务

### 9.7 验收标准

- 架构文档中明确 Agent 角色
- 主代码中主执行入口与文档描述一致
- `VerificationAgent` 不再回调旧 pipeline

---

## 10. 推荐里程碑

### 里程碑 M1：可运行

完成内容：

- P0 全部完成

产出：

- 新环境可启动
- 基础测试通过

### 里程碑 M2：底座统一

完成内容：

- P1 LLM
- P1 检索

产出：

- 不再依赖 LlamaIndex
- 不再直接碰旧 Chroma 客户端

### 里程碑 M3：业务迁移

完成内容：

- 5 个核验模块迁入 `langchain_app`

产出：

- 新旧业务边界清晰

### 里程碑 M4：流程升级

完成内容：

- LangGraph 主流程替换旧 pipeline

产出：

- 正式编排层上线

### 里程碑 M5：架构收口

完成内容：

- 明确 Agent 定位
- 清理旧兼容层

产出：

- 架构稳定版本

---

## 11. 推荐交付物

建议每个阶段至少交付以下内容：

### P0

- 依赖文件
- 可执行测试
- 启动说明

### P1

- 新版 `LLMClient`
- 新版 retrieval services
- 对应模块迁移说明

### P2

- `langchain_app/checks/*`
- 基于 LangGraph 的执行入口
- 兼容层清理记录

### P3

- Agent 定位说明
- README 更新

---

## 12. 最终建议

建议按下面的顺序执行，不要并行大面积改造：

1. 先完成 P0，确保工程可运行
2. 再完成 P1，把模型与检索底座统一
3. 然后完成 P2，把 5 个核验模块逐步迁入
4. 在 P2 后半段正式切到 LangGraph
5. 最后在 P3 处理 Agent 角色与旧代码清理

如果执行顺序反过来，例如先做 Agent 或先大改参数核验，会明显提高返工概率。

对当前项目而言，最稳妥的路线不是“直接做一个万能 Agent”，而是：

- 用 LangGraph 固化流程
- 用 LangChain 统一能力接入
- 用模块化重构逐步替换旧实现

这条路线可控、可测，也最符合现有业务特点。
