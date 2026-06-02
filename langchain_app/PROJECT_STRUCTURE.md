# langchain_app 项目结构说明

这份文档只覆盖 `langchain_app/` 目录内的实际代码与查找入口，不展开仓库根目录下的旧脚本、兼容层或报告产物。

目标：
- 方便快速定位 `langchain_app` 的真实执行入口
- 方便区分 UI / Graph / 节点 / 解析 / 参数核验 / 检索 / 配置
- 方便后续直接跳到相关代码，而不是每次全局搜索

## 1. 实际主链

当前 `langchain_app` 的真实核验主链是：

`parse_pdf -> parse_json -> integrity_check -> environment_check -> location_check -> cycle_check -> parameter_check -> assemble_report`

关键入口：
- UI 入口：`langchain_app/app.py`
- 运行入口：`langchain_app/core/pipeline.py`
- Graph 定义：`langchain_app/graph/verification_graph.py`
- 共享状态：`langchain_app/graph/state.py`

## 2. 快速定位索引

### UI / 启动
- `langchain_app/app.py`
  - Streamlit 页面
  - 文件上传
  - 侧边栏配置
  - 调用 `run_verification(...)`
- `langchain_app/app_example.py`
  - 示例入口，不是主链核心

### 运行编排
- `langchain_app/core/pipeline.py`
  - `PipelineHooks`
  - `load_shared_embedder(...)`
  - `run_verification(...)`
  - 是 UI 到 Graph 的主桥接层
- `langchain_app/graph/verification_graph.py`
  - 定义节点顺序
  - 编译 LangGraph
  - 执行 `run_verification_graph(...)`
- `langchain_app/graph/state.py`
  - `VerificationState`
  - 保存路径、配置、日志、报告段落、停止标记、各步骤结果

### Graph 节点
- `langchain_app/graph/nodes/parse_pdf.py`
- `langchain_app/graph/nodes/parse_json.py`
- `langchain_app/graph/nodes/integrity_check.py`
- `langchain_app/graph/nodes/environment_check.py`
- `langchain_app/graph/nodes/location_check.py`
- `langchain_app/graph/nodes/cycle_check.py`
- `langchain_app/graph/nodes/parameter_check.py`
- `langchain_app/graph/nodes/assemble_report.py`

每个节点通常只做一层薄封装，把 `state` 转给对应 `checks/` 或 `services/` 的真实逻辑。

### 解析链
- `langchain_app/services/parsing.py`
  - PDF -> MD / JSON 缓存刷新判断等流程服务
- `langchain_app/services/md_parser_pipeline.py`
  - 当前核心 MD -> 参数结构化解析链
  - 参数表、表头、合同化字段、解析修复逻辑基本都在这里
- `langchain_app/services/generic_md_parser_template.py`
  - 通用表格模板解析辅助

### 基础核验模块
- `langchain_app/checks/integrity.py`
  - 完整性 / CNAS / 基础字段
- `langchain_app/checks/environment.py`
  - 温湿度等环境条件
- `langchain_app/checks/location.py`
  - 校准地点
- `langchain_app/checks/cycle.py`
  - 校准周期

### 参数核验主链
- `langchain_app/checks/parameter/parameter.py`
  - 参数核验总入口
  - 批次执行
  - 结果汇总
  - 报表行生成
  - 各类业务规则
- `langchain_app/checks/parameter/contracts.py`
  - 参数合同化
  - 从解析结果抽出 `semantic_target / subtype / fields / axis / unit_family`
- `langchain_app/checks/parameter/semantic.py`
  - 参数语义推断
  - basis 选择审计
  - KB capability 语义归类
- `langchain_app/checks/parameter/selector.py`
  - `normalize_cert_point(...)`
  - `select_kb_candidates(...)`
  - 候选选择与兼容性判断
- `langchain_app/checks/parameter/validator.py`
  - 范围 / 误差 / 不确定度判定
- `langchain_app/checks/parameter/reporter.py`
  - 参数表格和汇总渲染辅助
- `langchain_app/checks/parameter/rules.py`
  - 语义别名、规则目录、测量项目规则
- `langchain_app/checks/parameter/retrieval.py`
  - 参数知识库检索辅助
- `langchain_app/checks/parameter/parser_core.py`
  - 值、单位、区间等底层解析
- `langchain_app/checks/parameter/parser_domain.py`
  - 频率/时间/电压等领域化解析
- `langchain_app/checks/parameter/parser_io.py`
  - I/O 辅助
- `langchain_app/checks/parameter/planner.py`
  - planner / auditor 相关逻辑

### 检索与基础设施
- `langchain_app/core/vector_db.py`
  - 向量库访问
- `langchain_app/core/llm_client.py`
  - LLM 客户端创建
  - `deepseek*` 与 `ChatOpenAI` 路径在这里分流
- `langchain_app/core/report_generator.py`
  - 报告生成辅助
- `langchain_app/retrieval/cnas.py`
  - CNAS 相关检索
- `langchain_app/retrieval/address.py`
  - 地址相关检索
- `langchain_app/retrieval/temperature.py`
  - 环境条件检索
- `langchain_app/retrieval/cycle.py`
  - 周期检索

### 配置
- `langchain_app/utils/config.py`
  - `AppConfig`
  - `from_env()`
  - `with_overrides(...)`
  - 目录与环境变量统一入口

### 其他
- `langchain_app/agents/verification_agent.py`
  - 代理层代码，不是当前主链核心
- `langchain_app/tools/example_tools.py`
  - 示例工具
- `langchain_app/README.md`
  - 使用说明
- `langchain_app/readme_2.md`
  - 辅助说明

## 3. 推荐查找路径

### 3.1 查“整个流程怎么跑起来”
按这个顺序看：
1. `langchain_app/app.py`
2. `langchain_app/core/pipeline.py`
3. `langchain_app/graph/verification_graph.py`
4. `langchain_app/graph/nodes/*.py`
5. `langchain_app/checks/*.py`

### 3.2 查“某个节点实际做了什么”
按这个顺序看：
1. `langchain_app/graph/nodes/<node>.py`
2. 对应 `langchain_app/checks/<module>.py` 或 `langchain_app/services/<module>.py`

示例：
- 参数核验：`graph/nodes/parameter_check.py` -> `checks/parameter/parameter.py`
- PDF 解析：`graph/nodes/parse_pdf.py` -> `services/parsing.py`
- JSON 解析：`graph/nodes/parse_json.py` -> `services/md_parser_pipeline.py`

### 3.3 查“参数为什么 PASS / FAIL / REVIEW”
按这个顺序看：
1. `langchain_app/checks/parameter/parameter.py`
2. `langchain_app/checks/parameter/contracts.py`
3. `langchain_app/checks/parameter/semantic.py`
4. `langchain_app/checks/parameter/selector.py`
5. `langchain_app/checks/parameter/validator.py`

对应逻辑链：
- 解析结构字段
- 合同化
- 语义推断
- 候选选择
- 范围 / 误差 / U 判定
- 生成说明列与最终表格

### 3.4 查“参数解析为什么抽错字段”
优先看：
1. `langchain_app/services/md_parser_pipeline.py`
2. `langchain_app/checks/parameter/contracts.py`
3. `langchain_app/checks/parameter/parser_core.py`
4. `langchain_app/checks/parameter/parser_domain.py`

### 3.5 查“模型、Key、路径配置从哪里来”
优先看：
1. `langchain_app/utils/config.py`
2. `langchain_app/app.py`
3. `langchain_app/core/llm_client.py`
4. `langchain_app/core/pipeline.py`

## 4. 参数主链细分

参数核验最值得记住的文件分工：

- `parameter.py`
  - 主入口
  - 组装每一行结果
  - 做业务规则覆写
  - 最终拼报告
- `contracts.py`
  - 把解析行转成标准合同字段
  - 适合查“为什么被识别成这个 semantic_target”
- `semantic.py`
  - 适合查“为什么同一个参数会走到这个能力族”
- `selector.py`
  - 适合查“为什么选中了这个 KB 候选 / 为什么 same basis but no compatible candidate”
- `validator.py`
  - 适合查“为什么范围不符合 / 为什么 U 不符合 / 为什么 Skip”

## 5. 推荐忽略项

为了快速找代码，通常可以先忽略这些内容：

- `langchain_app/.git/`
- `langchain_app/__pycache__/`
- 各子目录下的 `__pycache__/`
- `langchain_app/output/`
- `langchain_app/test.pdf`
- `langchain_app/app_example.py`
- `langchain_app/tools/example_tools.py`

## 6. 精简目录树

```text
langchain_app/
├─ app.py
├─ core/
│  ├─ pipeline.py
│  ├─ llm_client.py
│  ├─ report_generator.py
│  └─ vector_db.py
├─ graph/
│  ├─ state.py
│  ├─ verification_graph.py
│  ├─ routers.py
│  └─ nodes/
│     ├─ parse_pdf.py
│     ├─ parse_json.py
│     ├─ integrity_check.py
│     ├─ environment_check.py
│     ├─ location_check.py
│     ├─ cycle_check.py
│     ├─ parameter_check.py
│     └─ assemble_report.py
├─ checks/
│  ├─ integrity.py
│  ├─ environment.py
│  ├─ location.py
│  ├─ cycle.py
│  └─ parameter/
│     ├─ parameter.py
│     ├─ contracts.py
│     ├─ semantic.py
│     ├─ selector.py
│     ├─ validator.py
│     ├─ rules.py
│     ├─ retrieval.py
│     ├─ reporter.py
│     ├─ planner.py
│     ├─ parser_core.py
│     ├─ parser_domain.py
│     └─ parser_io.py
├─ services/
│  ├─ parsing.py
│  ├─ md_parser_pipeline.py
│  └─ generic_md_parser_template.py
├─ retrieval/
│  ├─ cnas.py
│  ├─ address.py
│  ├─ temperature.py
│  └─ cycle.py
├─ utils/
│  └─ config.py
├─ agents/
│  └─ verification_agent.py
└─ tools/
   └─ example_tools.py
```

## 7. 后续维护建议

后续如果继续修 `langchain_app`，建议优先从这几个文件开始：

- 改流程：`core/pipeline.py`、`graph/verification_graph.py`
- 改节点执行：`graph/nodes/*.py`
- 改参数判定：`checks/parameter/parameter.py`
- 改参数语义：`checks/parameter/contracts.py`、`semantic.py`、`selector.py`
- 改说明列/报表：`checks/parameter/parameter.py`、`reporter.py`
- 改配置/模型：`utils/config.py`、`core/llm_client.py`

