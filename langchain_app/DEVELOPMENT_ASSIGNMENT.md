# langchain_app 开发分工说明

本文档只覆盖当前最新的 `langchain_app/` LangGraph 版本，风格参考 `PROJECT_STRUCTURE.md`：先给快速定位，再给职责边界，最后给输入输出契约。

目标：

- 让每个组员快速知道自己负责哪些代码。
- 明确解析组、RAG 组、核验组之间的交付物。
- 避免“解析不稳定、检索查不到、规则无法判定”三类问题互相甩锅。
- 保持现有代码结构，不按人员重新拆目录。

## 1. 当前主链

当前 `langchain_app` 的真实执行主链是：

```text
parse_pdf
-> parse_json
-> integrity_check
-> environment_check
-> location_check
-> cycle_check
-> parameter_check
-> assemble_report
```

关键入口：

- UI 入口：`langchain_app/app.py`
- Pipeline 入口：`langchain_app/core/pipeline.py`
- Graph 定义：`langchain_app/graph/verification_graph.py`
- 共享状态：`langchain_app/graph/state.py`
- 节点目录：`langchain_app/graph/nodes/`

Graph 节点主要负责状态传递和异常处理，真实业务逻辑主要在：

- `langchain_app/services/`
- `langchain_app/retrieval/`
- `langchain_app/checks/`

## 2. 推荐分工

### 2.1 四人分工

| 角色 | 负责人 | 负责范围 |
| --- | --- | --- |
| 解析与结构化组 | 成员 A | PDF -> MD -> JSON，保证核验输入稳定 |
| RAG/知识库组 | 成员 B | Chroma、Embedding、各类检索服务、知识库字段质量 |
| 核验与集成组 | 成员 C | Graph 主链、接口契约、验收标准、最终报告口径、完整性、环境、地点、周期、参数核验规则 |

### 2.2 三人分工

| 角色 | 负责人 | 负责范围 |
| --- | --- | --- |
| 解析与结构化组 | 成员 A | PDF -> MD -> JSON |
| RAG 与基础核验组 | 成员 B | 向量库检索、环境/地点/周期核验支持 |
| 核验与参数规则组 | 成员 C | 参数核验、规则验收、集成协调、最终报告口径 |

如果实际人数只有 3 人，建议把“基础核验”交给 RAG 组一起维护，因为环境、地点、周期核验都依赖知识库检索。

## 3. 快速定位索引

### 3.1 解析与结构化组

优先看：

- `langchain_app/services/parsing.py`
- `langchain_app/services/md_parser_pipeline.py`
- `langchain_app/services/generic_md_parser_template.py`
- `langchain_app/graph/nodes/parse_pdf.py`
- `langchain_app/graph/nodes/parse_json.py`
- `md_parser_no_llm.py`
- `pdf_md.py`

负责输出：

- `local_md/<证书名>.md`
- `local_json/<证书名>.json`

### 3.2 RAG/知识库组

优先看：

- `langchain_app/core/vector_db.py`
- `langchain_app/core/embedding_loader.py`
- `langchain_app/retrieval/cnas.py`
- `langchain_app/retrieval/temperature.py`
- `langchain_app/retrieval/address.py`
- `langchain_app/retrieval/cycle.py`
- `langchain_app/checks/parameter/retrieval.py`
- `langchain_app/utils/config.py`

负责知识库：

- `vector_db/cnas_calibration`
- `vector_db/temperature`
- `vector_db/general_cycle`
- `vector_db/huawei_cycle`
- `vector_db/address`

### 3.3 核验规则组

基础核验优先看：

- `langchain_app/checks/integrity.py`
- `langchain_app/checks/environment.py`
- `langchain_app/checks/location.py`
- `langchain_app/checks/cycle.py`

参数核验优先看：

- `langchain_app/checks/parameter/parameter.py`
- `langchain_app/checks/parameter/contracts.py`
- `langchain_app/checks/parameter/semantic.py`
- `langchain_app/checks/parameter/selector.py`
- `langchain_app/checks/parameter/validator.py`
- `langchain_app/checks/parameter/rules.py`
- `langchain_app/checks/parameter/reporter.py`
- `langchain_app/checks/parameter/planner.py`
- `langchain_app/checks/parameter/profiles/`
- `langchain_app/checks/parameter/PROFILE_ARCHITECTURE.md`

### 3.4 核验与集成组

优先看：

- `langchain_app/core/pipeline.py`
- `langchain_app/graph/verification_graph.py`
- `langchain_app/graph/state.py`
- `langchain_app/graph/routers.py`
- `langchain_app/graph/nodes/*.py`
- `langchain_app/core/report_generator.py`

## 4. 解析组输入输出契约

### 4.1 输入

解析组接收：

```text
PDF 文件路径
AppConfig 配置
PipelineHooks 或 Graph state hooks
stop_event
可选 LLM client
```

当前主要入口：

- `pdf_to_md_first_step(pdf_path, config, hooks, stop_event, lang="ch")`
- `parse_md_to_json(md_path, out_dir, llm_client=None, allow_llm_fallback=False, hooks=None)`

### 4.2 输出文件契约

解析组必须产出：

```text
local_md/<pdf_stem>.md
local_json/<pdf_stem>.json
```

如果 PDF 是明确非 CNAS 文件，允许提前终止，但必须给 Graph 返回可用于生成跳过报告的信息。

### 4.3 JSON 顶层契约

JSON 应保持以下结构：

```json
{
  "__parameter_contract_schema_version": 2,
  "__md_parser_pipeline_signature": "string",
  "properties": {
    "证书列表": {
      "items": {
        "properties": {
          "CNAS": "是/否/未知",
          "证书编号": "string",
          "委托单位": "string",
          "委托方地址": "string",
          "仪器名称": "string",
          "型号规格": "string",
          "型号": "string",
          "制造厂": "string",
          "制造商": "string",
          "机身号": "string",
          "序列号": "string",
          "管理号": "string",
          "接收日期": "YYYY-MM-DD",
          "校准日期": "YYYY-MM-DD",
          "温度": "string",
          "相对湿度": "string",
          "温度_内页": "string",
          "相对湿度_内页": "string",
          "校准地点": "string",
          "建议校准周期": "string",
          "校准依据": ["JJG/JJF/GJB ..."],
          "依据参数_中间数据": []
        }
      }
    }
  }
}
```

字段要求：

- 字段缺失时使用空字符串、空数组或明确缺失标记，不要填入猜测值。
- 同义字段可以同时保留，例如 `型号规格` 和 `型号`，核验组会做兼容读取。
- `校准依据` 必须是列表；如果原文只有一个依据，也应输出单元素列表。
- 日期尽量标准化为 `YYYY-MM-DD`、`YYYY/MM/DD` 或 `YYYY.MM.DD`。

### 4.4 参数行契约

`依据参数_中间数据` 应是参数行列表，每一行至少包含：

```json
{
  "项目名称": "string",
  "数据明细": {
    "原始表头或字段名": "原始值"
  },
  "__normalized_fields": {
    "condition_value": "string",
    "nominal_value": "string",
    "reference_value": "string",
    "measure_value": "string",
    "error_value": "string",
    "limit_value": "string",
    "cert_u": "string"
  },
  "__parameter_contract": {
    "schema_version": 2,
    "row_shape": "string",
    "semantic_target": "string",
    "semantic_subtype": "string",
    "item_label": "string",
    "condition_axis": "string",
    "condition_value": "string",
    "nominal_value": "string",
    "reference_value": "string",
    "measure_value": "string",
    "error_value": "string",
    "limit_value": "string",
    "cert_u": "string",
    "unit_family": "frequency/time/voltage_power/motion/length/unknown",
    "source_headers": {
      "field_name": "source_header"
    },
    "confidence": 0.0,
    "needs_disambiguation": false
  },
  "__parser_meta": {
    "parse_source": "html_table/html_table_inline/text/unknown",
    "section_rule": "string",
    "unit_inherited": false,
    "parser_risk": "low/medium/high",
    "notes": []
  }
}
```

最低要求：

- `项目名称` 不得为空。
- `数据明细` 必须保留原始字段，方便追溯。
- `__normalized_fields` 必须尽力填充，不能识别时留空。
- `__parameter_contract.schema_version` 必须和 `contracts.py` 中版本一致。
- `__parser_meta` 必须能说明参数是从哪里解析出来的。

### 4.5 解析组交付物

解析组每轮应交付：

- 3 到 5 份典型 PDF 的 MD 输出。
- 对应 JSON 输出。
- 字段缺失清单。
- 表格错列、单位继承、乱码、跨页表格等解析风险记录。

验收标准：

- 基础核验字段能稳定读取。
- 参数核验能从 JSON 中收集到参数行。
- JSON 缓存过期时能自动刷新。
- 缺失字段能被识别为缺失，而不是被误填为错误业务值。

## 5. RAG 组输入输出契约

### 5.1 输入

RAG 组接收：

```text
query 文本
AppConfig 配置
topk
可选 filter_condition
可选 embedding_function / embedder
```

常见 query 来源：

- 证书中的校准依据。
- 仪器名称。
- 型号规格。
- 校准地点。
- 参数项目名称和测量点。

### 5.2 当前兼容返回格式

当前 `retrieval/` 目录下服务主要返回 LangChain `Document` 列表：

```python
Document(
    page_content="知识库条目正文",
    metadata={
        "distance": 0.123,
        "...": "其他字段"
    }
)
```

参数核验专用检索可能返回字典列表：

```json
{
  "文档内容": "string",
  "metadata": {
    "distance": 0.123
  }
}
```

后续新增检索接口时，应尽量向下面的规范格式靠拢。

### 5.3 推荐标准返回字段

每条检索结果至少应包含：

```json
{
  "page_content": "string",
  "metadata": {
    "collection": "string",
    "db_dir": "string",
    "source": "string",
    "distance": 0.0,
    "score": 0.0,
    "file_code": "JJG/JJF/GJB ...",
    "standard_name": "string",
    "instrument_name": "string",
    "measured": "string",
    "measure_range_text": "string",
    "error_limit_text": "string",
    "uncertainty_text": "string",
    "address": "string",
    "temperature_requirement": "string",
    "humidity_requirement": "string",
    "cycle_requirement": "string"
  }
}
```

不同知识库可以只填相关字段，但必须保留：

- `page_content`
- `metadata.collection`
- `metadata.db_dir`
- `metadata.distance` 或 `metadata.score`
- 可解释来源的字段，例如 `file_code`、`standard_name`、`source`

### 5.4 检索诊断契约

RAG 组需要能区分以下情况：

| 情况 | 说明 | 不应如何处理 |
| --- | --- | --- |
| DB_MISSING | 向量库路径不存在 | 不应返回“无匹配” |
| COLLECTION_MISSING | collection 名称错误或不存在 | 不应返回“证书不合格” |
| EMBEDDING_UNAVAILABLE | embedding 加载失败，退化到词法检索 | 不应悄悄吞掉 |
| EMPTY_COLLECTION | collection 存在但没有数据 | 不应返回业务 FAIL |
| NO_SAME_BASIS | 找不到同一规程号条目 | 参数核验应进入 REVIEW 或 ERROR |
| LOW_SIMILARITY | 有结果但相似度过低 | 应提示人工复核 |
| METADATA_INCOMPLETE | 条目存在但字段缺失 | 应报告知识库字段缺口 |

推荐诊断结构：

```json
{
  "ok": true,
  "query": "string",
  "db_dir": "string",
  "collection": "string",
  "topk": 5,
  "items_count": 5,
  "diagnostic": {
    "code": "OK/DB_MISSING/COLLECTION_MISSING/...",
    "message": "string",
    "fallback_used": false
  }
}
```

当前代码中如果还没有统一诊断对象，至少要在日志、异常信息或报告中保留以上诊断信息。

### 5.5 各知识库字段要求

CNAS 能力库应尽量提供：

- `file_code` 或 `校准依据`
- `standard_name` 或 `文件名称`
- `instrument_name` 或 `仪器名称`
- `measured` 或 `被测量/项目`
- `measure_range_text`
- `error_limit_text`
- `uncertainty_text`

温湿度库应尽量提供：

- `仪器名称`
- `文件编号`
- `文件名称`
- `温度要求`
- `相对湿度要求`
- `最大温度变化范围`
- `认可组织`

地址库应尽量提供：

- `标准地址`
- `专业室`
- `序号`
- `distance`

周期库应尽量提供：

- `仪器名称`
- `依据`
- `建议校准周期`
- `来源`

### 5.6 RAG 组交付物

RAG 组每轮应交付：

- 每个知识库的 collection 名称。
- 每个知识库的 metadata 字段说明。
- 典型 query 和返回样例。
- 查不到时的诊断样例。
- topk 和阈值建议。

验收标准：

- 环境、地点、周期、参数核验都能拿到可解释的检索依据。
- 查不到时能说明是系统问题、知识库缺口还是证书依据不匹配。
- 不把知识库异常误判为证书业务不合格。

## 6. 核验组输入输出契约

### 6.1 输入

核验组接收：

```text
json_path
AppConfig
stop_event
embedder_obj
llm_client
RAG 检索结果
```

各核验模块当前入口：

- `check_certificate_integrity(json_file, cfg, stop_event, embedder_obj, llm_client)`
- `check_environment(json_file, cfg, stop_event, embedder_obj, llm_client)`
- `check_location(json_file, cfg, stop_event, embedder_obj, llm_client)`
- `check_cycle_reasonableness(json_file, cfg, stop_event, embedder_obj, llm_client)`
- `check_parameters(json_file, cfg, stop_event, embedder_obj, llm_client)`

### 6.2 输出

所有核验函数必须返回 Markdown 字符串。

Graph 节点会把 Markdown 写入：

- `state.integrity_result`
- `state.environment_result`
- `state.location_result`
- `state.cycle_result`
- `state.parameter_result`
- `state.report_sections`

### 6.3 Markdown 报告格式契约

基础核验报告推荐格式：

```markdown
# [报告] <核验项名称>

## 一、输入信息

| 字段 | 值 |
| --- | --- |
| 证书编号 | ... |
| 仪器名称 | ... |

## 二、检索依据

| Top | 来源 | distance/score | 关键字段 | 摘要 |
| --- | --- | --- | --- | --- |
| 1 | ... | ... | ... | ... |

## 三、核验明细

| 项目 | 证书值 | 依据值 | 判定 | 说明 |
| --- | --- | --- | --- | --- |
| 温度 | 23 ℃ | 20 ℃~26 ℃ | PASS | 符合要求 |

## 四、结论

> **判定**: PASS/FAIL/REVIEW/ERROR
> **原因**: ...
```

参数核验报告推荐保留现有明细表思路：

```markdown
## 参数核验详情

| 序号 | 点位 | 测量点 | 测试条件 | KB编号 | KB条目 | 证书匹配项 | 范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
```

### 6.4 判定状态契约

所有核验模块统一使用以下状态：

| 状态 | 含义 | 使用条件 |
| --- | --- | --- |
| PASS | 通过 | 证书值、依据值、规则都明确，且证书满足要求 |
| FAIL | 不通过 | 证书明确违反规则，且证据充分 |
| REVIEW | 人工复核 | 字段不足、语义歧义、知识库覆盖缺口、低相似度、解析风险较高 |
| ERROR | 系统异常 | 解析失败、知识库无法访问、collection 缺失、必要依赖异常 |

重要规则：

- 知识库缺项不等于证书不合格，优先用 REVIEW 或 ERROR。
- 解析字段缺失不等于证书不合格，优先用 REVIEW，并说明源字段缺口。
- LLM 调用失败不应直接导致业务 FAIL，除非规则本身不依赖 LLM。
- FAIL 必须有明确证书值、依据值和规则说明。
- PASS 必须说明依据来自哪里。

### 6.5 REVIEW 原因分类

推荐在说明中使用以下原因类型：

| 原因类型 | 说明 |
| --- | --- |
| source_field_gap | JSON 源字段缺失或解析不可靠 |
| kb_coverage_gap | 知识库没有覆盖对应规程或能力项 |
| semantic_ambiguity | 参数语义无法唯一确定 |
| low_similarity | 检索结果相似度不足 |
| llm_unavailable | LLM 不可用，但规则需要 LLM 辅助 |
| manual_policy | 业务上要求人工复核 |

### 6.6 核验组交付物

核验组每轮应交付：

- 每个核验项的规则说明。
- 每个核验项的 PASS/FAIL/REVIEW/ERROR 示例。
- 每个核验项的 Markdown 输出样例。
- 参数核验典型案例清单。

验收标准：

- 报告能解释判定依据。
- 系统异常和业务不合格区分清楚。
- 参数核验能解释选中哪条 KB，以及为什么选中。
- 复杂或不确定情况进入 REVIEW，不强行给 FAIL。

## 7. 组间交接表

| 上游 | 下游 | 交接物 | 必须说明 |
| --- | --- | --- | --- |
| 解析组 | 基础核验组 | JSON 基础字段 | 缺失字段、非 CNAS 标记、日期格式 |
| 解析组 | 参数核验组 | 参数行、normalized fields、contract、parser meta | 单位继承、解析风险、原始字段 |
| RAG 组 | 基础核验组 | 环境/地点/周期检索结果 | 来源、distance、字段缺失、查不到原因 |
| RAG 组 | 参数核验组 | CNAS 能力库候选 | 规程号、能力项、范围、误差、U、同规程过滤结果 |
| 核验组 | 核验组 | Markdown 报告片段 | 判定状态、证据、异常说明 |

## 8. 不建议的做法

不要按人员重排代码目录，例如：

```text
member_a/
member_b/
member_c/
```

原因：

- 会破坏现有模块分层。
- 会增加导入和合并成本。
- 不利于 Graph 主链维护。
- 项目验收看功能模块，不看人员目录。

推荐做法：

- 保持 `langchain_app/` 当前结构。
- 用本文档标注 owner。
- 每个人在负责模块内开发。
- 跨模块改动先说明接口变化。

## 9. 每日检查清单

核验组每天检查：

- 解析组是否产出稳定 JSON。
- RAG 组是否能解释查不到的原因。
- 核验组是否统一使用 PASS/FAIL/REVIEW/ERROR。
- 参数核验是否有案例支撑。
- Graph 主链是否还能跑通。

建议优先跑：

```bash
python test_graph_runtime_smoke.py
python test_current_architecture.py
```

## 10. 最小验收样例

建议至少准备以下样例：

| 样例 | 用途 |
| --- | --- |
| 正常 CNAS 证书 | 验证全流程 PASS |
| 非 CNAS 证书 | 验证提前跳过 |
| 环境字段缺失证书 | 验证完整性和环境 REVIEW/FAIL |
| 地点不匹配证书 | 验证地址库检索和地点规则 |
| 周期异常证书 | 验证周期库和日期逻辑 |
| 参数表复杂证书 | 验证参数解析、语义、范围、误差、U |
| 知识库缺项证书 | 验证 REVIEW/ERROR 口径 |

## 11. 一句话总结

当前项目的核心协作边界是三个契约：

```text
解析组交稳定 JSON
RAG 组交可解释检索结果
核验组交可追溯 Markdown 判定报告
```

只要这三个契约稳定，LangGraph 主链就容易集成；如果这三个契约不稳定，单个模块即使能独立跑通，最终报告也会反复出问题。
