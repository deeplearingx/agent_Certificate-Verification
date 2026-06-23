# AI 智能文档核验系统

本项目用于对校准证书 PDF 执行自动化核验，当前主线是 `langchain_app/` 下的 LangGraph/LangChain 版本。系统会把 PDF 解析为 Markdown 和 JSON，再依次进行完整性、环境条件、校准地点、校准周期、参数与不确定度核验，最后生成 Markdown 核验报告。

## 项目主链

```text
PDF
-> Markdown
-> JSON 结构化数据
-> 完整性核验
-> 环境条件核验
-> 校准地点核验
-> 校准周期核验
-> 参数与不确定度核验
-> 最终 Markdown 报告
```

LangGraph 节点顺序：

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

核心入口：

- `langchain_app/core/pipeline.py`：主流程入口，连接配置、LLM、Embedding 和 Graph。
- `langchain_app/graph/verification_graph.py`：LangGraph 主图。
- `langchain_app/graph/state.py`：全流程共享状态。
- `langchain_app/graph/nodes/`：各流程节点。

## 项目架构

```text
document-verification-master/
├── app.py                         # Streamlit 前端，调用 FastAPI 后端
├── api/                           # FastAPI 服务层
├── main_pipeline.py               # CLI 单文件核验入口
├── run_fastapi_app.py             # FastAPI 启动包装
├── run_langchain_app.py           # LangGraph 版本快速测试/启动脚本
├── pdf_md.py                      # PDF -> Markdown 兼容解析入口
├── md_parser_no_llm.py            # Markdown -> JSON 兼容解析入口
├── langchain_app/                 # 当前主线代码
│   ├── app.py                     # 直接运行版 Streamlit UI
│   ├── core/                      # Pipeline、LLM、Embedding、向量库、报告生成
│   ├── graph/                     # LangGraph 状态、节点、路由、主图
│   ├── services/                  # PDF/MD/JSON 解析服务
│   ├── retrieval/                 # RAG 检索服务
│   ├── checks/                    # 完整性、环境、地点、周期、参数核验
│   ├── tools/                     # LangChain 工具封装
│   └── utils/                     # 配置、运行缓存、环境工具
├── scripts_by_part/               # 按任务归档的历史脚本
├── tests/                         # 当前主线测试
│   ├── langchain_app/             # Graph 和架构烟测
│   └── legacy/                    # 旧测试归档，默认不运行
├── vector_db/                     # Chroma 向量数据库
├── models/                        # 本地嵌入模型或模型缓存
├── local_pdf/                     # 输入 PDF 或上传缓存
├── local_md/                      # Markdown 中间产物
├── local_json/                    # JSON 中间产物
├── final_reports/                 # 最终报告
├── reports/                       # 中间报告或历史报告
└── docs/                          # 项目文档
```

三类业务模块：

- 解析组：`langchain_app/services/`、`pdf_md.py`、`md_parser_no_llm.py`，负责 `PDF -> MD -> JSON`。
- RAG 组：`langchain_app/retrieval/`、`langchain_app/core/vector_db.py`、`langchain_app/core/embedding_loader.py`，负责知识库检索。
- 核验组：`langchain_app/checks/`、`langchain_app/graph/`、`langchain_app/core/pipeline.py`，负责核验规则、Graph 集成和最终报告口径。

更详细的分工和接口契约见：

- `langchain_app/DEVELOPMENT_ASSIGNMENT.md`
- `langchain_app/ROOT_DIRECTORY_CLASSIFICATION.md`
- `docs/LangGraph_小组分工与代码导览.md`
- `langchain_app/checks/parameter/PROFILE_ARCHITECTURE.md`

## 环境准备

推荐使用项目已有的 conda `langchain` 环境，或自行创建 Python 环境。

### 方式一：使用已有 conda 环境

```powershell
conda activate langchain
```

如果当前终端的 `conda run` 遇到中文编码问题，可以直接使用该环境的 Python：

```powershell
D:\conda_envs\langchain\python.exe -m pytest -q --tb=short
```

### 方式二：新建环境

```bash
conda create -n langchain python=3.11
conda activate langchain
pip install -r requirements_langchain.txt
```

通用依赖也可使用：

```bash
pip install -r requirements.txt
```

## 配置说明

配置入口在 `langchain_app/utils/config.py`，运行时通过 `.env` 或环境变量读取。

先复制示例配置：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

常用环境变量：

```text
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TEMPERATURE=0.1
DEEPSEEK_MAX_TOKENS=2048

TOPK=50
BATCH_SIZE=5
MAX_WORKERS=5

EMBED_MODEL_PATH=./models
CNAS_DB_DIR=./vector_db/cnas_calibration
TEMPERATURE_DB_DIR=./vector_db/temperature
GENERAL_CYCLE_DB_DIR=./vector_db/general_cycle
HUAWEI_CYCLE_DB_DIR=./vector_db/huawei_cycle
ADDRESS_DB_DIR=./vector_db/address

LOCAL_PDF_DIR=./local_pdf
LOCAL_MD_DIR=./local_md
LOCAL_JSON_DIR=./local_json
FINAL_REPORTS_DIR=./final_reports
REPORTS_DIR=./reports
```

运行前建议确认以下目录存在或可自动创建：

- `local_pdf/`
- `local_md/`
- `local_json/`
- `final_reports/`
- `reports/`
- `vector_db/`
- `models/`

## 运行方式

### 1. 命令行核验单个 PDF

```bash
python main_pipeline.py local_pdf/sample.pdf
```

输出报告默认写入：

```text
final_reports/Report_<pdf_stem>.md
```

### 2. FastAPI 后端

```bash
python run_fastapi_app.py
```

或：

```bash
uvicorn api.app:APP --host 0.0.0.0 --port 8000
```

主要接口：

- `GET /api/v1/health`：健康检查。
- `POST /api/v1/tasks/verify`：提交 PDF 核验任务。
- `GET /api/v1/tasks/{task_id}`：查询任务状态。
- `POST /api/v1/tasks/{task_id}/cancel`：取消任务。
- `GET /api/v1/tasks/{task_id}/report`：获取报告。

### 3. Streamlit 前端 + FastAPI 后端

先启动 FastAPI：

```bash
python run_fastapi_app.py
```

再启动根目录 Streamlit 前端：

```bash
streamlit run app.py
```

根目录 `app.py` 是前端客户端，会向 FastAPI 后端提交任务并轮询结果。

### 4. 直接运行 LangGraph Streamlit UI

```bash
streamlit run langchain_app/app.py --server.port 8502
```

也可以使用交互式启动脚本：

```bash
python run_langchain_app.py
```

选择：

- `1`：快速测试。
- `3`：启动 `langchain_app/app.py`。

### 5. Docker 运行

本地 compose：

```bash
docker compose up --build
```

生产风格 compose：

```bash
docker compose -f docker-compose.prod.yml up --build
```

## 测试方式

默认测试已经通过 `pytest.ini` 收口：

- 默认只运行当前主线测试。
- `tests/legacy/` 默认不收集。
- `integration` 标记测试默认不运行，避免无 API Key 或外部服务不可用时失败。

运行默认测试：

```bash
python -m pytest -q --tb=short
```

在本机 conda `langchain` 环境中运行：

```powershell
D:\conda_envs\langchain\python.exe -m pytest -q --tb=short
```

只跑 Graph 和架构烟测：

```bash
python -m pytest tests/langchain_app -q
```

运行需要真实 API Key 的集成测试：

```bash
python -m pytest -m integration
```

当前整理后的默认测试状态：

```text
379 passed, 5 deselected, 2 xfailed, 1 warning, 8 subtests passed
```

其中两个 `xfail` 是保留的待确认规则点：

- 旧 golden fixture 与当前解析 schema 的精确比对不一致。
- 信号质量频率列是否应进入 `condition_axis` 待解析组和核验组确认。

## 输入输出契约

### 解析输出

解析组至少需要产出：

```text
local_md/<pdf_stem>.md
local_json/<pdf_stem>.json
```

JSON 顶层应包含：

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
          "仪器名称": "string",
          "校准依据": ["JJG/JJF/GJB ..."],
          "依据参数_中间数据": []
        }
      }
    }
  }
}
```

参数核验重点依赖：

- `__normalized_fields`
- `__parameter_contract`
- `__parser_meta`
- `数据明细`

参数核验已经新增 profile 层，用于后续按仪器/规程拆分特殊规则：

- `langchain_app/checks/parameter/profiles/`
- `langchain_app/checks/parameter/PROFILE_ARCHITECTURE.md`

### RAG 返回字段

RAG 组返回结果应包含：

```json
{
  "document": "原始或片段文本",
  "metadata": {
    "file_code": "JJF/JJG/GJB ...",
    "standard_name": "规程名称",
    "instrument_name": "仪器名称",
    "measured": "被测量",
    "measure_range_text": "测量范围",
    "uncertainty": "不确定度"
  },
  "distance": 0.0,
  "score": 1.0,
  "collection": "collection_name",
  "source": "vector_db/..."
}
```

检索失败时应返回可诊断原因，例如知识库不存在、集合为空、embedding 加载失败、相似度不足，而不是只返回空列表。

### 核验报告状态

所有核验模块统一使用：

| 状态 | 含义 |
| --- | --- |
| PASS | 证书内容满足规则 |
| FAIL | 证书内容明确不满足规则 |
| REVIEW | 信息不足、知识库缺项或规则无法自动判定，需要人工复核 |
| ERROR | 系统、配置、解析或知识库异常，当前结果不可作为业务结论 |

## 历史代码与归档

当前主线代码只看 `langchain_app/`。

历史脚本按任务归档在：

- `scripts_by_part/02_parsing_legacy/`
- `scripts_by_part/03_rag_kb_legacy/`
- `scripts_by_part/04_verification_legacy/`

旧版模块、旧 demo 和旧实验代码归档在：

- `无关/`

旧测试归档在：

- `tests/legacy/`

原则：

- 默认不从 `无关/` import。
- 默认不运行 `tests/legacy/`。
- 旧逻辑如需继续使用，先迁移到 `langchain_app/` 对应模块，再补当前主线测试。

## 开发建议

- 解析组改 JSON 字段前，先同步字段契约。
- RAG 组改 metadata 或检索返回字段前，先同步核验组。
- 核验组改 PASS/FAIL/REVIEW/ERROR 规则前，补对应测试或样例。
- 不按人员拆代码目录，继续按 `services/`、`retrieval/`、`checks/`、`graph/` 分层维护。
- 根目录保留启动入口和兼容入口，业务代码优先放入 `langchain_app/`。
