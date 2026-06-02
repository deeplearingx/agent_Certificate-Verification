# LangGraph 版本 - 启动和调试指南

## 第一步：确认环境

### 1.1 激活 conda 环境

```powershell
# Windows PowerShell
conda activate langchain

# 或者在 cmd 中
D:\conda_envs\langchain\Scripts\activate.bat
```

### 1.2 验证依赖

```powershell
python -c "import langchain; import langgraph; print('✓ LangChain:', langchain.__version__); print('✓ LangGraph:', langgraph.__version__)"
```

预期输出：
```
✓ LangChain: 1.2.13
✓ LangGraph: 1.1.3
```

---

## 第二步：运行基础测试

### 2.1 简单架构测试

```powershell
cd d:\workspace\ai大模型开发课\文档核验\document-verification-master
python test_langchain_simple.py
```

预期结果：
```
============================================================
LangChain 重构版 - 架构测试
============================================================

[OK] Config 模块加载成功
  - Model: deepseek-chat
  - Embedding Model: ...
  - Temperature: 0.1

[OK] LLMClient 导入成功
[OK] VectorDatabase 导入成功
[OK] VerificationReport 导入成功

[OK] 工具模块加载成功
  - 找到 7 个工具

[OK] VerificationAgent 导入成功

============================================================
测试结果汇总
============================================================
  配置模块: 通过
  核心模块: 通过
  工具模块: 通过
  Agent 模块: 通过

所有测试通过！LangChain 架构设置成功！
============================================================
```

---

## 第三步：启动 Streamlit 应用

### 3.1 方式一：直接启动

```powershell
# 确保在正确的目录
cd d:\workspace\ai大模型开发课\文档核验\document-verification-master

# 启动应用
streamlit run langchain_app/app.py
```

### 3.2 方式二：指定端口

```powershell
streamlit run langchain_app/app.py --server.port 8502
```

### 3.3 访问应用

浏览器自动打开：http://localhost:8501

---

## 第四步：可能遇到的问题及解决方案

### 问题 1：ModuleNotFoundError: No module named 'langchain'

**原因**：没有在正确的 conda 环境中运行

**解决方案**：
```powershell
# 激活 langchain 环境
conda activate langchain

# 验证
python -c "import langchain; print(langchain.__version__)"
```

### 问题 2：找不到 md_parser_no_llm 模块

**原因**：项目根目录不在 Python 路径中

**解决方案**：
- 确保在项目根目录运行
- 或者在代码中添加：
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

### 问题 3：向量数据库找不到

**原因**：vector_db 目录不存在或路径配置错误

**解决方案**：
```powershell
# 检查 vector_db 目录是否存在
ls vector_db

# 如果不存在，需要从原始项目复制过来
```

### 问题 4：环境变量未配置

**原因**：没有配置 .env 文件

**解决方案**：
```powershell
# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
```

---

## 第五步：调试技巧

### 5.1 查看完整错误栈

在应用运行时，如果出现错误，可以添加以下调试代码：

```python
import traceback
try:
    # 你的代码
    pass
except Exception as e:
    print(f"错误: {e}")
    print("详细堆栈:")
    print(traceback.format_exc())
```

### 5.2 测试单个节点

你可以单独测试每个节点：

```python
from langchain_app.graph.state import create_initial_state
from langchain_app.graph.nodes.parse_pdf import parse_pdf_node
from langchain_app.utils import get_app_config

config = get_app_config()
state = create_initial_state(
    pdf_path="path/to/test.pdf",
    config=config
)

result_state = parse_pdf_node(state)
print("PDF解析结果:", result_state.md_path)
```

### 5.3 启用 LangSmith 调试（可选）

```powershell
# 安装 langsmith
pip install langsmith

# 设置环境变量
$env:LANGCHAIN_TRACING_V2 = "true"
$env:LANGCHAIN_API_KEY = "your-api-key"
$env:LANGCHAIN_PROJECT = "document-verification"

# 然后启动应用
streamlit run langchain_app/app.py
```

---

## 第六步：快速验证流程

### 完整流程测试脚本

创建一个简单的测试脚本 `test_graph_runtime.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 LangGraph 完整流程
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

try:
    from langchain_app.utils import get_app_config
    from langchain_app.graph import create_graph
    from langchain_app.graph.state import create_initial_state

    print("=" * 60)
    print("LangGraph 完整流程测试")
    print("=" * 60)

    # 1. 加载配置
    print("\n[1/4] 加载配置...")
    config = get_app_config()
    print("  ✓ 配置加载成功")
    print(f"  - 模型: {config.model}")
    print(f"  - 嵌入模型: {config.embed_model_path}")

    # 2. 创建图
    print("\n[2/4] 创建图...")
    graph = create_graph()
    print("  ✓ 图创建成功")
    print(f"  - 节点: {list(graph.nodes.keys())}")

    # 3. 创建初始状态（使用一个示例PDF）
    print("\n[3/4] 创建初始状态...")

    # 检查是否有示例PDF
    sample_pdf = None
    local_pdf_dir = config.local_pdf_dir
    if local_pdf_dir.exists():
        pdf_files = list(local_pdf_dir.glob("*.pdf"))
        if pdf_files:
            sample_pdf = pdf_files[0]
            print(f"  ✓ 找到示例PDF: {sample_pdf.name}")

    if not sample_pdf:
        print("  ⚠ 没有找到示例PDF，跳过实际执行")
        print("\n" + "=" * 60)
        print("测试通过！图构建和导入都正常。")
        print("要运行完整流程，请上传一个PDF文件到应用。")
        print("=" * 60)
        sys.exit(0)

    # 4. 执行图（可选，可能需要很长时间）
    print("\n[4/4] 图已准备好，可以在 Streamlit 应用中使用！")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("现在可以运行: streamlit run langchain_app/app.py")
    print("=" * 60)

except Exception as e:
    print(f"\n✗ 测试失败: {e}")
    import traceback
    print("\n详细错误:")
    print(traceback.format_exc())
    sys.exit(1)
```

---

## 第七步：项目文件说明

### 核心目录结构

```
langchain_app/
├── app.py                      # Streamlit 主应用（入口）
├── core/                       # 核心功能模块
│   ├── llm_client.py          # LLM 客户端
│   ├── vector_db.py           # 向量数据库管理
│   ├── report_generator.py    # 报告生成
│   └── pipeline.py            # 兼容层入口
├── graph/                      # LangGraph 流程
│   ├── state.py               # 状态定义
│   ├── verification_graph.py  # 主图构建
│   └── nodes/                # 各个节点实现
│       ├── parse_pdf.py
│       ├── parse_json.py
│       ├── integrity_check.py
│       ├── environment_check.py
│       ├── location_check.py
│       ├── cycle_check.py
│       ├── parameter_check.py
│       └── assemble_report.py
├── checks/                     # 核验模块（复用原始代码）
├── utils/                      # 工具函数
│   └── config.py             # 配置管理
├── tools/                      # LangChain 工具
└── agents/                     # Agent 模块
```

### 主要入口文件

| 文件 | 用途 |
|-----|------|
| `langchain_app/app.py` | Streamlit Web 应用 |
| `langchain_app/core/pipeline.py` | 兼容性 `run_verification()` 接口 |
| `langchain_app/graph/verification_graph.py` | LangGraph 主流程 |
| `test_langchain_simple.py` | 简单架构测试 |
| `test_langchain_migration.py` | 完整迁移测试 |

---

## 总结

快速启动步骤：

```powershell
# 1. 激活环境
conda activate langchain

# 2. 进入项目目录
cd d:\workspace\ai大模型开发课\文档核验\document-verification-master

# 3. 运行测试（可选，验证环境）
python test_langchain_simple.py

# 4. 启动应用
streamlit run langchain_app/app.py
```

应用会在 http://localhost:8501 打开，你可以上传 PDF 文件进行核验！
