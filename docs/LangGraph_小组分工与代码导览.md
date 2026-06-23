# LangGraph 版本小组分工与代码导览

本文档只面向当前最新的 `langchain_app/` LangGraph 版本，不讨论仓库根目录下的旧版脚本和历史实验代码。

## 1. 项目主线

当前系统的目标是对校准证书 PDF 做自动核验，主流程是：

```text
PDF
-> Markdown
-> JSON 结构化数据
-> 完整性核验
-> 环境条件核验
-> 校准地点核验
-> 校准周期核验
-> 参数与不确定度核验
-> 最终报告
```

最新版 LangGraph 主链在：

- `langchain_app/graph/verification_graph.py`
- `langchain_app/graph/state.py`
- `langchain_app/core/pipeline.py`

Graph 节点本身主要做流程编排和状态传递，真正复杂的业务逻辑集中在：

- `langchain_app/services/`
- `langchain_app/retrieval/`
- `langchain_app/checks/`

因此分工不建议按 Graph 节点平均分，而应按“输入输出契约”和“业务能力边界”分。

## 2. 推荐分工结论

如果小组有 4 人，推荐分为 4 个方向：

| 角色 | 推荐负责人 | 主要职责 |
| --- | --- | --- |
| 解析与结构化负责人 | 成员 A | PDF -> MD -> JSON，保证后续核验输入稳定 |
| 知识库/RAG 负责人 | 成员 B | Chroma 向量库、检索服务、知识库字段质量、查不到的诊断 |
| 核验与集成负责人 | 成员 C | 完整性、环境、地点、周期、参数规则、接口验收、最终报告口径 |

如果小组只有 3 人，推荐这样压缩：

| 角色 | 推荐负责人 | 主要职责 |
| --- | --- | --- |
| 解析与结构化负责人 | 成员 A | PDF -> MD -> JSON |
| RAG 与基础核验负责人 | 成员 B | 向量库检索、环境/地点/周期核验支持 |
| 核验与参数规则负责人 | 成员 C | 参数核验、规则验收、集成协调、最终报告口径 |

当前你提出的“一个人解析、一个人 RAG、一个人和你一起做参数核验”总体合理。需要补充的是：基础核验和 RAG 高度相关，参数核验和 JSON 结构化高度相关，所以必须明确接口边界，否则后期会出现互相等待。

## 3. 各角色详细职责

### 3.1 核验与集成负责人

负责范围：

- 确定整体流程是否仍按 `parse_pdf -> parse_json -> checks -> assemble_report` 执行。
- 管理模块之间的输入输出契约。
- 维护验收样例和回归测试清单。
- 决定 PASS / FAIL / REVIEW / ERROR 的统一口径。
- 负责最终报告结构和演示材料。

重点文件：

- `langchain_app/core/pipeline.py`
- `langchain_app/graph/verification_graph.py`
- `langchain_app/graph/state.py`
- `langchain_app/graph/routers.py`
- `langchain_app/graph/nodes/*.py`
- `langchain_app/core/report_generator.py`

交付物：

- 一份稳定的全流程运行说明。
- 一份典型证书样例清单。
- 一份最终报告格式说明。
- 每轮修改后的集成测试结果。

验收标准：

- 上传 PDF 后能完整走到最终报告。
- 某个节点失败时，报告里能说明失败原因。
- 各模块负责人能清楚知道自己需要提供什么输入和输出。

### 3.2 解析与结构化负责人

负责范围：

- PDF -> Markdown。
- Markdown -> JSON。
- JSON 缓存刷新判断。
- 参数表、证书基础信息、环境信息、依据列表等字段结构化。
- 维护 `__parameter_contract`、`__normalized_fields`、`__parser_meta` 等参数核验依赖字段。

重点文件：

- `langchain_app/services/parsing.py`
- `langchain_app/services/md_parser_pipeline.py`
- `langchain_app/services/generic_md_parser_template.py`
- `langchain_app/graph/nodes/parse_pdf.py`
- `langchain_app/graph/nodes/parse_json.py`
- `md_parser_no_llm.py`
- `pdf_md.py`

关键输出：

```text
local_md/<证书名>.md
local_json/<证书名>.json
```

JSON 中后续核验重点依赖：

- `properties.证书列表.items.properties`
- `仪器名称`
- `型号规格`
- `制造厂`
- `证书编号`
- `温度`
- `相对湿度`
- `校准地点`
- `建议校准周期`
- `校准依据`
- `依据参数_中间数据`

参数核验重点依赖每一行参数中的：

- `项目名称`
- `数据明细`
- `__normalized_fields`
- `__parameter_contract`
- `__parser_meta`

交付物：

- 至少 5 份 PDF 的 JSON 解析结果。
- 解析字段说明表。
- 对解析失败、乱码、表格错列、字段缺失的记录。

验收标准：

- 基础核验字段可以稳定读取。
- 参数表能稳定抽出多行测量点。
- JSON 缓存过期时能自动刷新。
- 参数核验不需要再从原始 Markdown 猜字段。

注意事项：

- 解析负责人不是只负责“PDF 能转成 Markdown”，而是负责到“核验可用 JSON”。
- 参数核验中很多误判来自解析结构不稳定，解析组需要和参数规则组保持样例同步。

### 3.3 知识库/RAG 负责人

负责范围：

- Chroma 向量库读取。
- Embedding 加载。
- CNAS 能力库检索。
- 环境温湿度库检索。
- 地址库检索。
- 周期库检索。
- 参数核验专用 CNAS 检索。
- 检索失败的诊断和报告。

重点文件：

- `langchain_app/core/vector_db.py`
- `langchain_app/core/embedding_loader.py`
- `langchain_app/retrieval/cnas.py`
- `langchain_app/retrieval/temperature.py`
- `langchain_app/retrieval/address.py`
- `langchain_app/retrieval/cycle.py`
- `langchain_app/checks/parameter/retrieval.py`
- `langchain_app/utils/config.py`

涉及的知识库目录：

- `vector_db/cnas_calibration`
- `vector_db/temperature`
- `vector_db/general_cycle`
- `vector_db/huawei_cycle`
- `vector_db/address`

交付物：

- 各知识库 collection 名称和字段说明。
- 每个检索服务的输入、输出示例。
- 空库、错库、collection 不存在、embedding 加载失败时的诊断说明。
- 每类核验的 topk 建议值和阈值建议。

验收标准：

- 能说明“查不到”到底是哪一种原因：
  - 向量库路径不存在。
  - collection 名称不匹配。
  - 知识库记录字段缺失。
  - 规程号不匹配。
  - 相似度太低。
  - embedding 不可用，退化到词法检索。
- 检索结果必须带足够 metadata，供核验模块解释原因。
- 参数核验中同一规程过滤必须稳定。

注意事项：

- RAG 不是独立功能，它被环境、地点、周期、参数多个核验模块共同依赖。
- RAG 负责人需要和规则负责人约定返回字段，而不是只返回纯文本。

### 3.4 基础核验负责人

负责范围：

- 证书完整性核验。
- CNAS 标识判断。
- 环境条件核验。
- 校准地点核验。
- 校准周期核验。
- 日期逻辑核验。
- 温湿度内外页一致性核验。

重点文件：

- `langchain_app/checks/integrity.py`
- `langchain_app/checks/environment.py`
- `langchain_app/checks/location.py`
- `langchain_app/checks/cycle.py`
- `langchain_app/graph/nodes/integrity_check.py`
- `langchain_app/graph/nodes/environment_check.py`
- `langchain_app/graph/nodes/location_check.py`
- `langchain_app/graph/nodes/cycle_check.py`

交付物：

- 每个核验项的规则表。
- 每个核验项的 PASS / FAIL / REVIEW 条件。
- 每个核验项的报告模板。
- 与 RAG 负责人确认的检索字段需求。

验收标准：

- 非 CNAS 证书能提前跳过并生成说明报告。
- 环境、地点、周期核验能够解释检索依据。
- 规则失败和系统异常能区分：
  - 规则失败是证书不符合。
  - 系统异常是无法自动判定。

### 3.5 参数核验负责人

负责范围：

- 参数合同化。
- 参数语义识别。
- KB 候选选择。
- 范围判定。
- 误差判定。
- 不确定度判定。
- 参数报告输出。
- 参数核验回归样例。

重点文件：

- `langchain_app/checks/parameter/parameter.py`
- `langchain_app/checks/parameter/contracts.py`
- `langchain_app/checks/parameter/semantic.py`
- `langchain_app/checks/parameter/selector.py`
- `langchain_app/checks/parameter/validator.py`
- `langchain_app/checks/parameter/rules.py`
- `langchain_app/checks/parameter/retrieval.py`
- `langchain_app/checks/parameter/reporter.py`
- `langchain_app/checks/parameter/planner.py`
- `langchain_app/checks/parameter/parser_core.py`
- `langchain_app/checks/parameter/parser_domain.py`
- `langchain_app/checks/parameter/parser_io.py`

建议内部再拆成两块：

| 子方向 | 负责人 | 内容 |
| --- | --- | --- |
| 语义与规则目录 | 核验组 | `rules.py`、`contracts.py`、`semantic.py` |
| 选择与判定执行 | 成员 C | `selector.py`、`validator.py`、`reporter.py`、`parameter.py` |

参数核验主流程：

```text
读取 JSON
-> collect_certificate_params
-> 按参数分组和 batch
-> 按校准依据检索 CNAS 知识库
-> 筛选同一规程条目
-> 参数语义识别
-> 候选 KB 条目选择
-> 范围/误差/不确定度判定
-> 生成参数明细表和汇总表
```

交付物：

- 参数类型清单。
- 每类参数的字段需求。
- 每类参数的 KB 匹配规则。
- 每类参数的判定规则。
- 至少 5 到 10 份典型证书的预期结果。

验收标准：

- 参数核验结果能解释为什么选中某条 KB。
- PASS / FAIL / REVIEW 的原因能在报告中看懂。
- 知识库缺项不能伪装成证书不合格，应进入 REVIEW 或 ERROR。
- 解析字段缺失不能伪装成证书不合格，应提示源字段缺口。

## 4. 不建议按人员重排代码目录

当前 `langchain_app/` 已经按功能分层：

```text
langchain_app/
  app.py
  core/
  graph/
  services/
  retrieval/
  checks/
  utils/
```

不建议改成：

```text
member_a/
member_b/
member_c/
```

原因：

- 会破坏现有导入关系。
- 会让 Graph、checks、retrieval 的边界变得混乱。
- 后续合并和测试更困难。
- 项目验收看的是功能模块，不是人员目录。

推荐做法：

- 保持现有代码结构。
- 在文档中标注模块 owner。
- 每个人只在自己负责模块内改动。
- 跨模块改动先在群里说明输入输出变化。

## 5. 代码整体框架说明

### 5.1 UI 层

入口：

- `langchain_app/app.py`

职责：

- 上传 PDF。
- 设置 API Key、模型、topk 等参数。
- 调用 `run_verification(...)`。
- 展示日志、警告、错误和最终报告。

### 5.2 Pipeline 层

入口：

- `langchain_app/core/pipeline.py`

关键对象：

- `PipelineHooks`
- `load_shared_embedder`
- `run_verification`

职责：

- 连接 UI 和 LangGraph。
- 初始化配置、LLM、embedding。
- 创建初始 `VerificationState`。
- 调用 `run_verification_graph(...)`。

### 5.3 Graph 编排层

入口：

- `langchain_app/graph/verification_graph.py`

状态：

- `langchain_app/graph/state.py`

职责：

- 定义节点顺序。
- 定义提前终止逻辑。
- 保存全流程上下文。
- 汇总各核验节点输出。

核心状态字段：

- `source_pdf_path`
- `md_path`
- `json_path`
- `config`
- `embedder`
- `llm_client`
- `integrity_result`
- `environment_result`
- `location_result`
- `cycle_result`
- `parameter_result`
- `report_sections`
- `final_report`
- `errors`
- `warnings`
- `should_stop`

### 5.4 节点层

目录：

- `langchain_app/graph/nodes/`

职责：

- 从 state 读取输入。
- 调用对应 service 或 check。
- 将结果写回 state。
- 追加报告段落。
- 处理异常和提前停止。

节点列表：

```text
parse_pdf.py
parse_json.py
integrity_check.py
environment_check.py
location_check.py
cycle_check.py
parameter_check.py
assemble_report.py
```

### 5.5 解析服务层

目录：

- `langchain_app/services/`

职责：

- PDF 转 Markdown。
- Markdown 转 JSON。
- 解析缓存判断。
- 参数表结构化。

最关键的接口：

- `pdf_to_md_first_step(...)`
- `parse_md_to_json(...)`
- `json_cache_needs_refresh(...)`

### 5.6 检索层

目录：

- `langchain_app/retrieval/`
- `langchain_app/core/vector_db.py`

职责：

- 封装 Chroma 访问。
- 提供不同知识库的业务检索接口。
- 在 vector 检索不可用时退化到词法检索。

检索服务：

```text
CnasRetrievalService
TemperatureRetrievalService
AddressRetrievalService
CycleRetrievalService
```

### 5.7 核验层

目录：

- `langchain_app/checks/`

职责：

- 对 JSON 数据和 RAG 结果进行业务判定。
- 生成 Markdown 片段。
- 将每一类核验结果交给 Graph 统一拼接。

基础核验：

```text
integrity.py
environment.py
location.py
cycle.py
```

参数核验：

```text
checks/parameter/
  parameter.py       主入口与批处理
  contracts.py       参数合同化
  semantic.py        参数语义识别
  selector.py        KB 候选选择
  validator.py       范围/误差/U 判定
  rules.py           规则目录与别名
  retrieval.py       参数专用 KB 检索
  reporter.py        参数报告渲染
  planner.py         LLM planner/auditor
```

## 6. 模块接口约定

### 6.1 解析组给核验组

必须提供：

- 稳定 JSON 路径。
- 证书基础字段。
- 校准依据列表。
- 参数表中间数据。
- 参数合同字段。
- 解析质量标记。

若字段缺失，应明确表现为缺失，而不是填入错误值。

### 6.2 RAG 组给核验组

必须提供：

- 文档文本。
- metadata。
- distance 或 score。
- collection 名称。
- 来源库路径。
- 可用于报告解释的依据字段。

若检索失败，应返回可诊断错误，不应简单返回空列表。

### 6.3 核验组内部交付

必须提供：

- Markdown 报告片段。
- 明确判定。
- 明确原因。
- 系统异常和业务不符合的区分。

推荐判定口径：

| 判定 | 含义 |
| --- | --- |
| PASS | 证书内容满足规则 |
| FAIL | 证书内容明确不满足规则 |
| REVIEW | 信息不足、规则无法自动判定，需要人工复核 |
| ERROR | 系统或知识库异常，当前结果不可作为业务结论 |

## 7. 协作流程建议

每次开发按下面流程推进：

1. 解析组先给出 JSON 样例。
2. RAG 组确认知识库能查到相关依据。
3. 核验组根据 JSON 和 RAG 结果写规则。
4. 核验组跑完整流程。
5. 对照预期报告修正解析、检索或规则。
6. 把失败案例记录到回归样例。

不要一开始就追求覆盖所有证书。建议先选 5 到 10 份典型证书：

- 正常通过样例。
- 非 CNAS 跳过样例。
- 环境不完整样例。
- 地点不匹配样例。
- 周期异常样例。
- 参数表复杂样例。
- 知识库缺项样例。

## 8. 阶段计划

### 阶段 1：代码认领与接口冻结

目标：

- 每个人确认负责文件。
- 明确 JSON 字段契约。
- 明确 RAG 返回字段。
- 明确报告判定口径。

建议周期：1 到 2 天。

### 阶段 2：样例跑通

目标：

- 跑通 3 份证书。
- 生成完整报告。
- 标出明显问题。

建议周期：2 到 3 天。

### 阶段 3：参数核验强化

目标：

- 梳理主要参数类型。
- 完善语义规则。
- 完善范围、误差、不确定度判定。

建议周期：3 到 5 天。

### 阶段 4：回归与演示准备

目标：

- 固定测试样例。
- 整理最终报告。
- 准备分工说明和演示脚本。

建议周期：1 到 2 天。

## 9. 核验组检查清单

每天检查：

- 解析是否产出稳定 JSON。
- RAG 是否能解释查不到的原因。
- 核验规则是否有明确 PASS / FAIL / REVIEW / ERROR。
- 参数核验是否有典型案例支撑。
- Graph 主链是否还能跑通。

每次合并前检查：

- 是否改动了其他成员负责模块。
- 是否影响 JSON 字段。
- 是否影响 RAG metadata。
- 是否影响最终报告格式。
- 是否至少跑过一个 smoke test。

可优先运行：

```bash
python test_graph_runtime_smoke.py
python test_current_architecture.py
```

## 10. 最终建议

当前项目最难的不是 LangGraph 编排，而是三个契约：

1. PDF/MD 到 JSON 的结构化契约。
2. RAG 返回知识条目的字段契约。
3. 参数核验的业务判定契约。

分工时只要把这三个契约守住，三人或四人都能推进。代码不需要按人员重新整理目录，只需要在现有模块边界上明确 owner、输入输出和验收样例。
