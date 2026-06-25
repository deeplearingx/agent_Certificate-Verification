# 主目录文件归类说明

本文以 `langchain_app/` LangGraph/LangChain 版本作为项目主线核心，对主目录文件进行归类。本文描述当前整理后的实际目录状态。

核心原则：

- `langchain_app/` 是当前唯一主线代码。
- 根目录保留启动入口、部署入口和当前解析仍会动态导入的兼容文件。
- 历史解析、RAG、核验脚本已经归入 `scripts_by_part/`。
- 旧版模块、旧实验、旧测试已经归入 `无关/` 的子目录。
- `local_*`、`final_reports/`、`reports/`、`output/` 等目录主要是运行缓存或产物。

## 1. 主线核心

| 路径 | 归类 | 负责人 | 说明 |
| --- | --- | --- | --- |
| `langchain_app/` | 主线核心代码 | 全组 | 最新 LangGraph/LangChain 版本主体 |
| `langchain_app/app.py` | 主线 UI | 核验组/集成协调 | Streamlit 直接运行版 |
| `langchain_app/core/` | 核心层 | 核验组/集成协调 | Pipeline、LLM、向量库、报告生成 |
| `langchain_app/graph/` | 编排层 | 核验组/集成协调 | LangGraph 状态、节点、路由、主图 |
| `langchain_app/services/` | 解析服务层 | 解析组 | PDF/MD/JSON 解析服务 |
| `langchain_app/retrieval/` | RAG 服务层 | RAG 组 | CNAS、温度、地址、周期检索 |
| `langchain_app/checks/` | 核验规则层 | 核验组 | 完整性、环境、地点、周期、参数核验 |
| `langchain_app/utils/` | 配置与运行工具 | 核验组/集成协调 | AppConfig、运行缓存等 |

配套文档：

- `langchain_app/PROJECT_STRUCTURE.md`
- `langchain_app/DEVELOPMENT_ASSIGNMENT.md`
- `langchain_app/CODING_STANDARDS.md`
- `langchain_app/ROOT_DIRECTORY_CLASSIFICATION.md`

## 2. 根目录保留入口

这些文件仍保留在根目录，因为它们是当前启动、部署或兼容入口。

| 路径 | 负责人 | 保留原因 |
| --- | --- | --- |
| `app.py` | 核验组/集成协调 | 当前 Streamlit 前端，通过 HTTP 调 FastAPI |
| `api/` | 核验组/集成协调 | 当前 FastAPI 后端 |
| `api/app.py` | 核验组/集成协调 | 任务提交、状态轮询、报告获取 |
| `main_pipeline.py` | 核验组/集成协调 | CLI 入口，调用 `langchain_app.core.run_verification` |
| `run_fastapi_app.py` | 核验组/集成协调 | FastAPI 启动包装 |
| `run_langchain_app.py` | 核验组/集成协调 | LangGraph 版本快速测试/启动脚本 |
| `pdf_md.py` | 解析组 | 当前 `langchain_app/services/parsing.py` 会动态导入 |
| `md_parser_no_llm.py` | 解析组 | 当前 Markdown -> JSON 解析入口之一 |
| `pytest.ini` | 核验组/集成协调 | 默认测试收口配置，排除 legacy 和 integration |
| `requirements.txt` | 核验组/集成协调 | 通用依赖 |
| `requirements_langchain.txt` | 核验组/集成协调 | LangGraph/LangChain 版本依赖 |
| `Dockerfile.api` | 核验组/集成协调 | API 镜像 |
| `Dockerfile.streamlit` | 核验组/集成协调 | Streamlit 镜像 |
| `docker-compose.yml` | 核验组/集成协调 | 本地 compose |
| `docker-compose.prod.yml` | 核验组/集成协调 | 生产风格 compose |
| `.env.example` | 核验组/集成协调 | 环境变量样例 |
| `README.md` | 核验组/集成协调 | 项目总说明 |

## 3. 按任务归档的历史脚本

目录：`scripts_by_part/`

该目录放从根目录移出的历史脚本，方便按小组职责查看。它们不是当前主线直接 import 的代码。

| 路径 | 负责人 | 内容 |
| --- | --- | --- |
| `scripts_by_part/README.md` | 核验组/集成协调 | 目录说明 |
| `scripts_by_part/02_parsing_legacy/` | 解析组 | 早期 PDF 解析、PDF 识别、PDF + 向量库实验脚本 |
| `scripts_by_part/03_rag_kb_legacy/` | RAG 组 | CNAS、温度、地址、周期向量库构建和检索调试脚本 |
| `scripts_by_part/04_verification_legacy/` | 核验组 | 早期依据、完整性、环境、地点、周期核验脚本 |

解析组参考脚本：

- `scripts_by_part/02_parsing_legacy/pdf解析.py`
- `scripts_by_part/02_parsing_legacy/pdf解析+构建向量数据库.py`
- `scripts_by_part/02_parsing_legacy/测试PDF识别.py`
- `scripts_by_part/02_parsing_legacy/测试新PDF.py`

RAG 组参考脚本：

- `scripts_by_part/03_rag_kb_legacy/CNSA数据库搭建.py`
- `scripts_by_part/03_rag_kb_legacy/旧cnsa数据库搭建.py`
- `scripts_by_part/03_rag_kb_legacy/cnsa检索.py`
- `scripts_by_part/03_rag_kb_legacy/温度向量数据库搭建.py`
- `scripts_by_part/03_rag_kb_legacy/校准地点向量数据库搭建.py`
- `scripts_by_part/03_rag_kb_legacy/通用周期向量数据库搭建.py`
- `scripts_by_part/03_rag_kb_legacy/华为周期向量数据库搭建.py`
- `scripts_by_part/03_rag_kb_legacy/依据检索模块1.py`
- `scripts_by_part/03_rag_kb_legacy/检索仪器名称.py`

核验组参考脚本：

- `scripts_by_part/04_verification_legacy/依据核验.py`
- `scripts_by_part/04_verification_legacy/依据核验b.py`
- `scripts_by_part/04_verification_legacy/依据核验c.py`
- `scripts_by_part/04_verification_legacy/信息完整性核验.py`
- `scripts_by_part/04_verification_legacy/建议校准周期核验.py`
- `scripts_by_part/04_verification_legacy/校准地点核验.py`
- `scripts_by_part/04_verification_legacy/温度核验.py`

## 4. 已归档旧版代码

目录：`无关/`

该目录默认不参与当前 LangGraph 主线开发，只用于追溯旧逻辑。

| 路径 | 内容 | 当前替代位置 |
| --- | --- | --- |
| `无关/README.md` | 目录说明 | - |
| `无关/01_legacy_modules/` | 旧 `core`、`checks`、`config`、`kb`、`llm` 模块 | `langchain_app/core/`、`langchain_app/checks/`、`langchain_app/retrieval/` |
| `无关/02_apps_and_demos/` | 旧 UI、demo、安装测试脚本 | `app.py`、`api/`、`langchain_app/app.py` |
| `无关/03_parsing_legacy/` | 旧 PDF、Markdown、pdfplumber、Camelot、PaddleOCR 解析实验 | `langchain_app/services/` |
| `无关/04_verification_legacy/` | 旧 `*_check.py`、`param_check*.py` | `langchain_app/checks/` |
| `无关/05_tests_legacy/` | 旧测试脚本 | `tests/` |
| `无关/06_tools_legacy/` | 旧工具脚本 | 按需迁移到主线工具或文档 |

使用原则：

- 默认不改 `无关/`。
- 默认不从 `无关/` import。
- 旧逻辑如有价值，迁移进 `langchain_app/` 对应模块并补测试。

## 5. 解析组目录

主线维护：

- `langchain_app/services/`
- `langchain_app/graph/nodes/parse_pdf.py`
- `langchain_app/graph/nodes/parse_json.py`
- `pdf_md.py`
- `md_parser_no_llm.py`
- `local_pdf/`
- `local_md/`
- `local_json/`

参考归档：

- `scripts_by_part/02_parsing_legacy/`
- `无关/03_parsing_legacy/`

运行数据：

- `pdf/`
- `pdf_md_json/`
- `CNAS解析/`

## 6. RAG 组目录

主线维护：

- `langchain_app/retrieval/`
- `langchain_app/core/vector_db.py`
- `langchain_app/core/embedding_loader.py`
- `langchain_app/checks/parameter/retrieval.py`
- `vector_db/`
- `models/`

知识库目录：

- `vector_db/cnas_calibration/`
- `vector_db/temperature/`
- `vector_db/general_cycle/`
- `vector_db/huawei_cycle/`
- `vector_db/address/`

参考归档：

- `scripts_by_part/03_rag_kb_legacy/`
- `无关/01_legacy_modules/kb/`

数据与缓存：

- `data/`
- `.hf_cache/`
- `Dai_cache/`
- `env_pack/`

## 7. 核验组目录

主线维护：

- `langchain_app/checks/integrity.py`
- `langchain_app/checks/environment.py`
- `langchain_app/checks/location.py`
- `langchain_app/checks/cycle.py`
- `langchain_app/checks/parameter/`
- `langchain_app/checks/parameter/profiles/`
- `langchain_app/checks/parameter/PROFILE_ARCHITECTURE.md`
- `langchain_app/graph/nodes/*_check.py`
- `notes/`

参考归档：

- `scripts_by_part/04_verification_legacy/`
- `无关/04_verification_legacy/`

历史评估与临时报告：

- `param_check_accuracy_report.json`
- `param_check_accuracy_final_report.md`
- `100_percent_accuracy_report.md`
- `tmp_latest_param_report.md`

## 8. 测试目录

主线测试：

- `tests/`
- `tests/langchain_app/test_graph_runtime_smoke.py`
- `tests/langchain_app/test_current_architecture.py`

默认 pytest 行为：

- `pytest.ini` 将默认测试范围收口到 `tests/`。
- `tests/legacy/` 默认不收集。
- `integration` 标记测试默认不运行，需要真实外部 API 时再显式启用。
- 当前默认测试命令：`python -m pytest -q --tb=short`。

旧测试归档：

- `tests/legacy/`
- `无关/05_tests_legacy/`

建议责任：

- 解析组维护 `tests/test_md_parser_*`、`tests/test_parsing_*`。
- RAG 组维护 `tests/test_vector_db_search_strategy.py`、`tests/test_parameter_retrieval.py`。
- 核验组维护 `tests/test_environment_check.py`、`tests/test_cycle_utils.py`、`tests/test_param_*`、`tests/test_parameter_*`。
- 核验组维护 `tests/langchain_app/`、`tests/test_fastapi_service.py`、`pytest.ini`。
- `tests/legacy/` 中的旧测试只作为迁移参考，不作为当前验收标准。

## 9. 文档和报告

当前文档：

- `docs/README.md`
- `docs/模块需求归纳.md`
- `docs/基础核验模块需求说明.md`
- `docs/参数核验模块需求说明.md`
- `langchain_app/PROJECT_STRUCTURE.md`
- `langchain_app/DEVELOPMENT_ASSIGNMENT.md`
- `langchain_app/CODING_STANDARDS.md`
- `langchain_app/ROOT_DIRECTORY_CLASSIFICATION.md`

历史说明、阶段报告、面试材料、旧部署草稿和早期重构方案不再作为 `docs/` 主目录交付文档；这些材料只用于追溯，不参与当前 LangChain / LangGraph 主线运行链。

## 10. 运行产物和缓存

| 路径 | 类型 |
| --- | --- |
| `final_reports/` | 最终报告 |
| `reports/` | 中间或旧版报告 |
| `audit_reports/` | 审计报告 |
| `output/` | 输出目录 |
| `langchain_app/output/` | LangChain app 输出目录 |
| `backups/` | 备份 |
| `memory/` | 历史记忆或缓存 |
| `testout_v2/` | 测试输出 |
| `.pytest_cache/` | pytest 缓存 |
| `__pycache__/` | Python 缓存 |

## 11. 异常目录

以下目录名疑似 Windows 路径转义或工具生成结果，暂不自动删除：

- `dworkspaceai大模型开发课文档核验document-verification-masterlangchain_app{core,agents,tools,utils}`
- `Dai_cache/`

建议确认无引用后再清理。

## 12. 总览

当前目录层级可以这样理解：

```text
第一层：langchain_app/ 是主线代码
第二层：app.py / api/ / main_pipeline.py 是主线入口包装
第三层：scripts_by_part/ 是按小组职责归档的历史脚本
第四层：无关/ 是旧版代码和旧测试归档
第五层：vector_db/ models/ local_* final_reports/ 是运行数据和产物
第六层：docs/ 和根目录 md 是说明、汇报、历史材料
```
