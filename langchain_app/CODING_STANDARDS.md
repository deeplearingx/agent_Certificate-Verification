# langchain_app 代码规范

本规范覆盖 `langchain_app/` 下所有模块。与 [DEVELOPMENT_ASSIGNMENT.md](./DEVELOPMENT_ASSIGNMENT.md) 配套：分工文档讲"谁做什么"，本规范讲"代码必须长什么样"。

修改任何 canonical 契约（字段名、返回结构、判定状态）必须更新本文件，并在 PR 描述里点名提示。

---

## 1. 总则

1. **契约只在边界生效**：解析出口、检索出口、核验入口/出口。模块内部允许任意中间表示。
2. **下游不做兼容兜底**：不要写 `props.get("A") or props.get("B")`、不要写 `if isinstance(x, Document) else dict[...]`。把兼容性挪到产出端的归一化层。
3. **系统异常 ≠ 业务不合格**：解析失败、检索失败、知识库缺失 → REVIEW 或 ERROR，不得 FAIL。
4. **改契约 = 改 schema_version**：任何 canonical 字段变更必须 bump 对应的 schema version 并使旧缓存失效。

---

## 2. JSON Schema 契约（解析出口）

### 2.1 canonical key 列表

下表中 **canonical key 列**是下游唯一可读的字段名。同义词列出现在原始文档中，但产出 JSON 时必须由 [`services/field_normalizer.py`](services/field_normalizer.py) 归一为 canonical key。

| canonical key | 同义词（解析端会自动归一） |
| --- | --- |
| `仪器名称` | `INSTRUMENT_NAME`, `instrument_name` |
| `型号规格` | `型号`, `规格型号`, `规格` |
| `制造商` | `制造厂`, `厂家`, `manufacturer` |
| `序列号` | `机身号`, `出厂编号`, `serial_no` |
| `管理号` | `资产编号`, `asset_number` |
| `委托单位` | `委托单位名称`, `客户名称`, `client` |
| `委托方地址` | `委托单位地址`, `客户地址` |
| `温度` / `温度_内页` | `环境温度` / `温度_内` |
| `相对湿度` / `相对湿度_内页` | `湿度`, `湿度_内页` |
| `校准地点` | `校准地址`, `地点`, `实验室地点` |
| `校准日期` / `接收日期` / `签发日期` | `测试日期` / `送样日期` / `签发时间`, `出具日期` |
| `CNAS` | `是否CNAS`, `CNAS标志` |
| `证书编号` | `Certificate No`, `certificate_no` |
| `建议校准周期` | `校准周期`, `推荐校准周期` |
| `校准依据`（list） | `依据` |

完整列表见 `field_normalizer.ALIAS_MAP`。

### 2.2 归一化规则

- **优先级**：列表顺序即优先级，列表首个非空值入 canonical key。
- **可追溯性**：所有命中过的同义键挪入 `__raw_fields` 子对象。下游需要原始字段时只能从这里读，不得回退到顶层别名。
- **未识别字段**：不在 `ALIAS_MAP` 里的字段原样保留，便于解析端临时引入新字段。
- **归一化时机**：
  1. 解析出口：`parse_md_to_json` 写完 JSON 后立即调用 `normalize_certificate_json_file`。
  2. 检查入口：所有 `check_*` 函数必须用 `load_and_normalize_certificate_json` 读 JSON，禁止直接 `json.load`。
- 旧 JSON 文件无需迁移，加载时自动归一化（in-memory）；想固化到磁盘可手动跑一次 `normalize_certificate_json_file`。

### 2.3 顶层结构

```json
{
  "__parameter_contract_schema_version": 2,
  "__md_parser_pipeline_signature": "...",
  "properties": {
    "证书列表": {
      "items": {
        "properties": {
          // canonical keys + __raw_fields
        }
      }
    }
  },
  "依据参数_中间数据": [ /* 参数行，结构见 DEVELOPMENT_ASSIGNMENT §4.4 */ ]
}
```

### 2.4 字段值规范

- 缺失字段：使用空字符串、空数组或显式缺失标记。**禁止填猜测值**。
- 列表字段（如 `校准依据`）即使只有一项也必须是数组。
- 日期：`YYYY-MM-DD` / `YYYY/MM/DD` / `YYYY.MM.DD` 三种之一。
- 数值字段保留原文本（带单位），不做提前数值化；数值化是核验模块的责任。

---

## 3. 检索返回契约

### 3.1 唯一返回结构

所有新增检索入口必须返回 [`retrieval/types.RetrievalResponse`](retrieval/types.py)：

```python
RetrievalResponse(
    query="...",
    hits=[RetrievalHit(page_content="...", metadata={...}), ...],
    diagnostic=Diagnostic(code=DiagnosticCode.OK, message="", fallback_used=False),
    db_dir="...",
    collection="...",
    topk=N,
)
```

- 调用方判分支必须用 `diagnostic.code`，**禁止**用 `len(hits) == 0` 推断错误类型。
- `RetrievalHit.metadata` 至少包含：`collection`、`db_dir`、`distance` 或 `score`、可解释来源（`file_code` / `standard_name` / `source` 之一）。

历史代码遗留两种格式（LangChain `Document` 列表、中文键 dict 列表）。新代码禁止再生产这两种形态。读取历史数据可用：

- `retrieval.types.hit_from_langchain_document(doc)`
- `retrieval.types.hit_from_legacy_dict(item)`
- `retrieval.types.response_from_documents(...)`
- `retrieval.types.response_from_legacy_dicts(...)`

### 3.2 DiagnosticCode 取值

| code | 含义 | 调用方推荐处理 |
| --- | --- | --- |
| `OK` | 正常返回 | 按 hits 做业务判定 |
| `DB_MISSING` | 向量库路径不存在 | ERROR |
| `COLLECTION_MISSING` | collection 名称错误或不存在 | ERROR |
| `EMBEDDING_UNAVAILABLE` | embedding 加载失败 | ERROR（已 fallback 时降为 REVIEW） |
| `EMPTY_COLLECTION` | collection 内无数据 | ERROR |
| `NO_SAME_BASIS` | 找不到同一规程号条目 | REVIEW |
| `LOW_SIMILARITY` | 有结果但相似度过低 | REVIEW |
| `METADATA_INCOMPLETE` | 条目缺关键字段 | REVIEW，并在报告中标记知识库缺口 |
| `UNEXPECTED_ERROR` | 未分类异常 | ERROR |

`DiagnosticCode.is_system_error` 用于区分系统问题 vs 业务/数据问题。

### 3.3 知识库 metadata 字段要求

详见 [DEVELOPMENT_ASSIGNMENT.md §5.5](./DEVELOPMENT_ASSIGNMENT.md)。RAG 组负责维护每个知识库的字段清单和典型样本。

---

## 4. 核验模块契约

### 4.1 入口签名

所有核验函数统一签名：

```python
def check_xxx(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:  # 返回 Markdown
    ...
```

> 后续若需要引入 `RetrievalResponse` 注入或缓存句柄，统一封装为 `CheckContext`，**不要**继续往位置参数尾部加。

### 4.2 必须使用 canonical loader

```python
from langchain_app.services.field_normalizer import load_and_normalize_certificate_json

raw_data, props = load_and_normalize_certificate_json(json_file)
instrument_name = props.get("仪器名称", "")  # canonical key 直接读
```

禁止直接 `json.load` + `props["properties"]["证书列表"]...`，会绕过归一化。

### 4.3 判定状态

四态枚举：`PASS / FAIL / REVIEW / ERROR`。规则见 [DEVELOPMENT_ASSIGNMENT §6.4](./DEVELOPMENT_ASSIGNMENT.md)。

REVIEW 必须在说明中写明原因类型：
- `source_field_gap` — JSON 源字段缺失
- `kb_coverage_gap` — 知识库未覆盖该规程
- `semantic_ambiguity` — 参数语义不可唯一确定
- `low_similarity` — 检索结果相似度不足
- `llm_unavailable` — LLM 不可用
- `manual_policy` — 业务要求人工复核

### 4.4 Markdown 报告

固定四节：输入信息 / 检索依据 / 核验明细 / 结论。结论必须包含 `判定` 和 `原因` 两行。模板见 [DEVELOPMENT_ASSIGNMENT §6.3](./DEVELOPMENT_ASSIGNMENT.md)。

---

## 5. 模块边界与导入

```
graph/        ← 入口编排，禁止有业务逻辑
core/         ← pipeline、vector_db、LLMClient、报告聚合
services/     ← 解析层（PDF/MD/JSON），归一化在此
retrieval/    ← 检索服务、types
checks/       ← 核验规则（依赖 services + retrieval）
utils/        ← 纯函数工具，禁止反向依赖任何上层
```

依赖方向：`graph → core/checks → services/retrieval → utils`。反向导入禁止。

---

## 6. 命名与代码风格

- 模块文件 `snake_case.py`；类 `PascalCase`；函数/变量 `snake_case`；常量 `UPPER_SNAKE_CASE`。
- 布尔值用 `is_/has_/should_/can_` 前缀。
- 函数 ≤ 50 行，文件 ≤ 800 行，嵌套 ≤ 4 层。超过即拆分。
- 注释只解释 **为什么**，不解释 **是什么**。代码本身要能自解释。
- 类型注解：所有公开函数必须带 type hints。

---

## 7. 错误处理与日志

- **不允许静默吞异常**：`except Exception: pass` 一律禁止。最低要求是 `logger.warning` + 重抛 或 转 ERROR 状态。
- 系统异常分类参考 §3.2 DiagnosticCode；解析失败必须包含原始文件名和失败阶段。
- 用户可见错误信息不得泄露文件系统路径以外的环境细节。

---

## 8. 测试要求

- 新增核验规则必须附 ≥ 1 个 PASS、1 个 FAIL、1 个 REVIEW 案例（fixtures 放到 `tests/fixtures/`）。
- 解析层每轮交付 3-5 份典型 PDF 的 MD + JSON 输出。
- 每日跑：
  ```bash
  python test_graph_runtime_smoke.py
  python test_current_architecture.py
  ```
  全绿才能合并到 `main`。

---

## 9. Git 提交规范

```
<type>: <subject>

<body>
```

`type` ∈ {`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`}。
- subject ≤ 70 字符，祈使句。
- body 写**为什么**，不写**做了什么**（diff 自带）。
- 涉及契约变更（§2 / §3 / §4）必须在 body 第一段说明影响范围。

PR 必须包含：变更摘要、影响模块、测试计划。

---

## 10. 修订记录

| 日期 | 变更 |
| --- | --- |
| 2026-06-23 | 初版：canonical field schema + RetrievalResponse 契约 |
