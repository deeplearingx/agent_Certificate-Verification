# AI智能文档核验系统 - LangGraph 架构版

## 概述

这是基于 LangGraph 编排框架重构的 AI 智能文档核验系统，完全保留原始 LlamaIndex 版本的功能，并提供更强的流程编排能力、更好的调试跟踪和可扩展性。

## 架构优势

### 重构前（LlamaIndex 版本）
- 使用多个分散的组件
- 学习曲线较陡
- 工具和 Agent 集成复杂
- 调试和跟踪困难

### 重构后（LangGraph 编排 + LangChain 能力层）
- **统一编排**：使用 LangGraph 作为主流程编排层
- **简化架构**：核心组件更少，逻辑更清晰
- **强大生态**：访问 LangChain 的大量工具和集成
- **更好调试**：使用 LangSmith 进行追踪和调试
- **高度扩展**：支持动态工具绑定和 Agent 行为调整
- **功能完整**：完全保留原始项目的所有功能

## 项目架构

```
langchain_app/
├── __init__.py                 # 项目初始化
├── app.py                      # Streamlit 主应用
├── core/                       # 核心功能
│   ├── __init__.py
│   ├── llm_client.py           # LLM 客户端
│   ├── vector_db.py            # 向量数据库管理
│   ├── report_generator.py     # 报告生成器
│   └── pipeline.py            # Graph 入口兼容层
├── services/                   # 服务层（避免循环导入）
│   ├── __init__.py
│   └── parsing.py             # PDF 解析服务
├── graph/                      # LangGraph 流程编排
│   ├── __init__.py
│   ├── state.py               # 状态定义
│   ├── verification_graph.py   # 主图构建
│   └── nodes/                # 节点定义
├── checks/                     # 核验模块
│   ├── __init__.py
│   ├── integrity.py          # 信息完整性核验
│   ├── environment.py        # 环境条件核验
│   ├── location.py           # 校准地点核验
│   ├── cycle.py              # 校准周期核验
│   └── parameter/            # 参数与不确定度核验
├── agents/                     # Agent 模块（辅助层）
│   ├── __init__.py
│   └── verification_agent.py   # 核验 Agent
├── tools/                      # 工具模块
│   ├── __init__.py
│   └── example_tools.py       # 所有核验工具
└── utils/                      # 工具函数
    ├── __init__.py
    └── config.py               # 配置管理
```

## 核心组件

### 1. 配置管理 (`utils/config.py`)
与原始项目完全兼容的配置类

```python
from langchain_app.utils import get_app_config

# 从环境变量加载
config = get_app_config()

# 覆盖配置
config = config.with_overrides(temperature=0.2)

# 确保目录存在
config = config.ensure_directories()

# 兼容旧入口时才转换为运行时命名空间
legacy_runtime_cfg = config.to_runtime_namespace()
```

### 2. LLM 客户端 (`core/llm_client.py`)
使用 LangChain 的 ChatOpenAI 封装

```python
from langchain_app.utils import get_app_config
from langchain_app.core import LLMClient

config = get_app_config()
llm = LLMClient(config)

# 生成响应
response = llm.generate_response(
    prompt="请描述这个证书",
    system_prompt="你是一名核验专家"
)

# 语义核验
fields = {"仪器名称": "信号发生器", "型号": "33511B"}
result = llm.verify_with_llm(
    fields=fields,
    cert_no="CNAS-001",
    system_prompt="核验规则..."
)
```

### 3. 向量数据库 (`core/vector_db.py`)
向量数据库管理类

```python
from langchain_app.core import VectorDatabase
from langchain_app.utils import get_app_config

config = get_app_config()

db = VectorDatabase(
    collection_name=config.cnas_collection,
    persist_directory=str(config.cnas_db_dir)
)

# 相似度搜索
results = db.similarity_search(query="电压范围", k=5)

# 带分数搜索
results_with_score = db.similarity_search_with_score(query="电压范围", k=5)

# 获取集合信息
info = db.get_collection_info()
```

### 4. 流水线编排 (`core/pipeline.py`)
与原始项目完全兼容的流水线

```python
from langchain_app.utils import get_app_config
from langchain_app.core import (
    PipelineHooks,
    run_verification,
    load_shared_embedder
)

config = get_app_config()
embedder = load_shared_embedder(str(config.embed_model_path))

# 创建钩子
hooks = PipelineHooks(
    set_status=st.text,
    set_progress=st.progress,
    info=st.info,
    warning=st.warning,
    error=st.error,
    success=st.success
)

# 运行核验
final_report = run_verification(
    pdf_file_path=Path("certificate.pdf"),
    config=config,
    hooks=hooks,
    embedder=embedder
)
```

### 5. 工具模块 (`tools/example_tools.py`)
所有核验工具的 LangChain 封装

```python
from langchain_app.tools import get_all_tools

tools = get_all_tools()

# 工具列表:
# - parse_pdf_to_md: PDF→MD转换
# - parse_md_to_json: MD→JSON解析
# - info_check: 信息完整性核验
# - environment_check: 环境条件核验
# - location_check: 校准地点核验
# - cycle_check: 校准周期核验
# - parameter_check: 参数与不确定度核验
```

### 6. 核验 Agent (`agents/verification_agent.py`)
文档核验 Agent

```python
from langchain_app.agents import VerificationAgent
from langchain_app.core import LLMClient
from langchain_app.utils import get_app_config

config = get_app_config()
llm = LLMClient(config)

agent = VerificationAgent(llm)

# 获取 Agent 信息
agent_info = agent.get_agent_info()

# 运行核验
report = agent.run_verification("path/to/certificate.pdf")
```

## 安装和运行

### 1. 安装依赖
```bash
# 激活 LangChain 环境
conda activate langchain_env

# 安装依赖
pip install -r requirements_langchain.txt
```

### 2. 运行示例应用
```bash
# 方式一：使用主脚本
python run_langchain_app.py

# 方式二：直接启动应用
cd langchain_app
streamlit run app.py

# 方式三：在项目根目录启动
streamlit run langchain_app/app.py --server.port 8502
```

### 3. 测试代码
```bash
# 快速测试
python test_langchain_migration.py

# 简单测试
python test_langchain_simple.py
```

## 配置

### 环境变量
```bash
# 基础配置
DEEPSEEK_API_KEY="your-api-key"
DEEPSEEK_API_BASE="https://api.deepseek.com/v1"
DEEPSEEK_MODEL="deepseek-chat"
DEEPSEEK_TEMPERATURE=0.1
DEEPSEEK_MAX_TOKENS=2048

# 检索配置
TOPK=50
BATCH_SIZE=5
MAX_WORKERS=5

# 路径配置
EMBED_MODEL_PATH="./models"
CNAS_DB_DIR="./vector_db/cnas_calibration"
TEMPERATURE_DB_DIR="./vector_db/temperature"
GENERAL_CYCLE_DB_DIR="./vector_db/general_cycle"
HUAWEI_CYCLE_DB_DIR="./vector_db/huawei_cycle"
ADDRESS_DB_DIR="./vector_db/address"

# 业务配置
USE_LLM_VERIFICATION=true
USE_LLM_LOCATION_CHECK=true
MUST_MATCH_THRESHOLD=0.45
OPTIONAL_MATCH_THRESHOLD=0.45
DEFAULT_CYCLE="12个月"
```

### 使用 .env 文件
```bash
# 创建 .env 文件
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

## 功能说明

### 支持的核验类型
1. **信息完整性核验** - 检查字段完整性、CNAS标识
2. **环境条件核验** - 检查温度、湿度是否符合要求
3. **校准地点核验** - 验证地点是否在认可范围内
4. **校准周期核验** - 检查校准周期合理性
5. **参数与不确定度核验** - 最复杂的核验，检查参数范围和不确定度

### 5个向量数据库
| 数据库 | 数据来源 | 用途 |
|--------|---------|------|
| cnas_calibration | CNAS认可的校准能力 | 参数与不确定度核验 |
| temperature | 温度要求.xlsx | 环境条件核验 |
| general_cycle_data | 通用建议校准周期.xlsx | 校准周期核验 |
| huawei_cycle_data | 华为建议校准周期.xlsx | 华为设备周期核验 |
| address | 校准地点.xlsx | 校准地点核验 |

## 与原始项目兼容性

### 完全兼容
- 向量数据库格式不变
- 缓存系统不变（local_pdf、local_md、local_json）
- 配置接口完全兼容
- 所有检查器功能完全相同

### 迁移方式
无需修改原始项目文件，只需使用 langchain_app/ 中的代码即可。

```python
# 兼容旧导入（仍可用，但只是兼容层）：
from config.settings import get_app_config
from core.pipeline import run_verification

# 推荐的 canonical 导入：
from langchain_app.utils import get_app_config
from langchain_app.core import run_verification

# 功能完全相同！
```

## 开发指南

### 添加新工具

```python
# 在 langchain_app/tools/example_tools.py 中添加
from langchain.tools import tool

@tool
def new_check_tool(json_data: str) -> str:
    """新的核验工具 - 描述工具用途"""
    # 实现逻辑
    return "核验完成"

# 不要忘记在 get_all_tools() 中添加
def get_all_tools() -> List:
    return [
        parse_pdf_to_md,
        # ... 其他工具
        new_check_tool,  # 添加新工具
    ]
```

### 创建自定义 Agent

```python
from langchain.agents import create_agent
from langchain_app.tools import get_all_tools
from langchain_app.agents import VerificationAgent

class CustomAgent(VerificationAgent):
    def __init__(self, llm):
        super().__init__(llm)
        self.tools = get_all_tools()
        # 自定义初始化

    def run_verification(self, pdf_path: str) -> str:
        # 自定义实现
        pass
```

## 调试技巧

### 使用 LangSmith
```bash
# 安装 LangSmith
pip install langsmith

# 设置环境变量
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY="your-langsmith-api-key"
export LANGCHAIN_PROJECT="document-verification"
```

### 使用 Hooks 进行调试
```python
from langchain_app.core import PipelineHooks

hooks = PipelineHooks(
    set_status=print,
    set_progress=lambda x: print(f"Progress: {x}%"),
    info=lambda x: print(f"INFO: {x}"),
    warning=lambda x: print(f"WARN: {x}"),
    error=lambda x: print(f"ERROR: {x}"),
    success=lambda x: print(f"SUCCESS: {x}"),
)
```

## 测试

```bash
# 运行完整测试
python test_langchain_migration.py

# 运行快速测试
python test_langchain_simple.py
```

## 迁移指南

详细的迁移指南请查看项目根目录的 `langchain_refactor_guide.md` 文件。

## 下一步

1. 运行快速测试：`python test_langchain_simple.py`
2. 运行完整测试：`python test_langchain_migration.py`
3. 启动应用：`streamlit run langchain_app/app.py`
4. 查看迁移指南：`langchain_refactor_guide.md`

## 贡献

如果你想为项目做出贡献，请遵循以下步骤：
1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到你的仓库
5. 创建 Pull Request

## 许可证

MIT License

## 联系

如有问题，请通过项目 Issues 联系。
