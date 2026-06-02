# AI 智能文档核验系统

## 项目简介

基于 LangGraph 编排框架的 AI 文档核验系统，用于自动分析校准证书，执行完整性、准确性和合规性检查。

## 核心功能

| 核验类型 | 说明 |
|---------|------|
| 信息完整性核验 | 检查字段完整性、CNAS标识 |
| 环境条件核验 | 检查温度、湿度是否符合要求 |
| 校准地点核验 | 验证地点是否在认可范围内 |
| 校准周期核验 | 检查校准周期合理性 |
| 参数与不确定度核验 | 检查参数范围和不确定度 |

## 技术架构

```
┌─────────────────────────────────────────┐
│           Streamlit 前端界面            │
├─────────────────────────────────────────┤
│           LangGraph 流程编排            │
├─────────────────────────────────────────┤
│  LangChain LLM客户端  │  向量数据库检索  │
├─────────────────────────────────────────┤
│        5个核验模块（完整性/环境/地点/周期/参数） │
└─────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
conda activate langchain_env
pip install -r requirements_langchain.txt
```

### 2. 配置环境变量

```bash
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_API_BASE="https://api.deepseek.com/v1"
```

### 3. 启动应用

```bash
streamlit run app.py
```

## 项目结构

```
langchain_app/
├── app.py                 # Streamlit 主应用
├── core/                  # 核心功能（LLM客户端、向量数据库）
├── graph/                 # LangGraph 流程编排
├── checks/                # 核验模块
├── agents/                # Agent 模块
├── tools/                 # 工具模块
├── utils/                 # 配置管理
└── services/              # 服务层
```

## 技术栈

- **框架**: LangGraph + LangChain
- **LLM**: DeepSeek API (OpenAI兼容)
- **向量数据库**: ChromaDB
- **嵌入模型**: BAAI/bge-m3
- **前端**: Streamlit

## 许可证

MIT License
