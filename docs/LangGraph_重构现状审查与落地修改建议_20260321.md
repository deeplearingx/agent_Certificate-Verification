# LangGraph 重构现状审查与落地修改建议（2026-03-21）

## 1. 文档目的

本文档基于 2026-03-21 对当前项目的最新代码状态和 `langchain` conda 环境下的实际验证结果，给出一份可以直接执行的修改建议。

本文档不讨论抽象方向，只关注：

- 现在的重构效果到底如何
- 当前真正阻塞交付的问题是什么
- 每个问题应该改哪些文件
- 具体怎么改
- 如何验收

---

## 2. 本轮验证基线

### 2.1 验证环境

- Python 解释器：`D:\conda_envs\langchain\python.exe`
- Conda 环境：`langchain`

### 2.2 已验证结论

在 `langchain` 环境下：

- `langchain` 可导入
- `langgraph` 可导入
- `langchain_openai` 可导入

说明：

- 当前问题已经不是“环境没装好”
- 当前问题主要是代码组织、模块边界和未完成迁移

### 2.3 已执行的关键验证

已执行并观察到失败的命令包括：

```powershell
& 'D:\conda_envs\langchain\python.exe' test_langchain_simple.py
& 'D:\conda_envs\langchain\python.exe' test_checks_simple.py
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.verification_graph import build_verification_graph; build_verification_graph().compile(); print('graph_ok')"
```

失败的主要原因：

- `core` 与 `graph` 的循环导入
- `checks/__init__.py` 顶层导入过重
- 参数核验仍是占位实现

---

## 3. 当前重构效果总体评价

### 3.1 已经做好的部分

当前版本已经不是“LangChain 外壳 + 老逻辑”的初始形态，而是已经完成了以下结构重构：

- 新增 `langchain_app/graph/`
- 新增 `langchain_app/checks/`
- 新增 `langchain_app/retrieval/`
- `langchain_app/core/pipeline.py` 已经将 LangGraph 作为主编排入口之一

这说明：

- 架构方向是正确的
- LangGraph 主编排已经开始落地
- 项目已进入“工程收口阶段”，不是“方向探索阶段”

### 3.2 当前还不能视为完成的原因

虽然结构基本成型，但以下关键条件尚未满足：

1. 核心包不能稳定导入
2. Graph 无法独立编译运行
3. 参数核验未完成迁移
4. tools 层仍回调旧根目录模块
5. checks 包无法按模块独立测试

因此当前结论应表述为：

**LangGraph 重构已进入中后期，但仍未达到可稳定交付状态。**

---

## 4. 当前最关键的 5 个问题

## 4.1 问题 1：`core` 与 `graph` 之间存在循环导入

### 现象

当前的导入链大致如下：

```text
langchain_app.core
  -> pipeline
  -> graph
  -> verification_graph
  -> nodes.parse_pdf
  -> langchain_app.core
```

直接结果：

- `test_langchain_simple.py` 失败
- `test_checks_simple.py` 失败
- `test_parameter_simple.py` 失败
- Graph 独立构建失败

### 根因

`parse_pdf.py` 当前通过顶层包再反向依赖 `langchain_app.core`：

- `langchain_app/graph/nodes/parse_pdf.py`

而 `langchain_app/core/__init__.py` 又在导出 `pipeline`，导致形成闭环。

### 需要修改的文件

- `langchain_app/core/__init__.py`
- `langchain_app/core/pipeline.py`
- `langchain_app/graph/nodes/parse_pdf.py`

### 可执行修改方案

#### 方案 A：最小改动方案

1. 在 `langchain_app/graph/nodes/parse_pdf.py` 中：
   - 不再写：
     ```python
     from langchain_app.core import pdf_to_md_first_step
     ```
   - 改为：
     ```python
     from langchain_app.core.pipeline import pdf_to_md_first_step
     ```

2. 在 `langchain_app/core/__init__.py` 中：
   - 不要默认导出 `pdf_to_md_first_step`
   - 不要把所有 pipeline 相关对象在包初始化时全部导出

#### 方案 B：推荐方案

将解析相关函数抽离到独立模块：

- 新建 `langchain_app/services/parsing.py`

把以下函数迁过去：

- `pdf_to_md_first_step`
- `json_cache_needs_refresh`
- 如果需要，也可放 `load_shared_embedder`

然后：

- `graph/nodes/parse_pdf.py` 从 `langchain_app.services.parsing` 导入
- `core/pipeline.py` 也从 `langchain_app.services.parsing` 导入

这样可以彻底打断 `core -> graph -> core` 闭环。

### 完成标准

以下命令必须通过：

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "import langchain_app.core; print('core_ok')"
& 'D:\conda_envs\langchain\python.exe' -c "import langchain_app.graph; print('graph_ok')"
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.verification_graph import build_verification_graph; build_verification_graph().compile(); print('compiled_ok')"
```

---

## 4.2 问题 2：`checks/__init__.py` 顶层导入过重

### 现象

现在只要导入：

```python
from langchain_app.checks.parameter import ...
```

也会触发：

- `integrity.py`
- `core`
- `pipeline`
- `graph`

导致参数模块测试无法独立运行。

### 根因

`langchain_app/checks/__init__.py` 直接在顶层导入全部 checks。

### 需要修改的文件

- `langchain_app/checks/__init__.py`

### 可执行修改方案

#### 方案 A：改为最小导出

将当前：

```python
from .integrity import ...
from .environment import ...
from .location import ...
from .cycle import ...
from .parameter import ...
```

改成：

```python
__all__ = [
    "integrity",
    "environment",
    "location",
    "cycle",
    "parameter",
]
```

不在包初始化时导入子模块。

#### 方案 B：惰性导入

如果确实需要维持旧导出形式，可以用 `__getattr__` 做惰性导入，但这会更复杂。当前建议先走方案 A。

### 完成标准

以下命令可通过：

```powershell
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
```

并且不再在导入阶段触发 `integrity -> core -> graph` 链条。

---

## 4.3 问题 3：多个 checks 的 `LLMClient` 初始化方式错误

### 现象

以下文件都在用：

```python
llm_client = LLMClient(cfg)
```

这在当前 `LLMClient` 签名下会把 `cfg` 传到 `api_key` 位置参数。

### 受影响文件

- `langchain_app/checks/integrity.py`
- `langchain_app/checks/environment.py`
- `langchain_app/checks/cycle.py`
- `langchain_app/checks/location.py`
- `langchain_app/core/llm_client.py`

### 可执行修改方案

统一替换为两种写法中的一种。

#### 方案 A：显式传参

```python
llm_client = LLMClient(config=cfg)
```

#### 方案 B：统一工厂

```python
from langchain_app.core import create_llm_client
llm_client = create_llm_client(cfg)
```

推荐使用方案 B，因为以后如果初始化逻辑调整，只需要改一处。

### 额外建议

建议增加一个最小公共函数，例如：

```python
def get_llm(cfg):
    return create_llm_client(cfg)
```

统一放在：

- `langchain_app/core/factories.py`

或直接沿用 `create_llm_client(cfg)`。

### 完成标准

至少完成以下验证：

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.checks.integrity import verify_with_llm; print('import_ok')"
```

后续有 API Key 时，再做真实调用验证。

---

## 4.4 问题 4：参数核验仍是占位实现

### 现象

`langchain_app/checks/parameter/parameter.py` 当前不是完整参数核验逻辑，而是一个“迁移说明 + 框架展示 + 检索测试”的过渡实现。

这意味着：

- 主流程虽然可以调用 `run_llm_mode()`
- 但参数核验结果并不等价于原 `param_check.py`

### 当前缺失的能力

从原版 `param_check.py` 看，至少包括以下核心能力：

1. 参数点提取
2. 知识库检索
3. 依据筛选
4. 语义预过滤
5. 点位范围验证
6. 误差验证
7. 不确定度验证
8. 批次级处理
9. 最终统计汇总
10. 报告强制后处理

而当前新参数模块虽然已有子文件：

- `parser.py`
- `retrieval.py`
- `semantic.py`
- `validator.py`
- `reporter.py`

但主入口仍未把它们组装成真实业务链。

### 需要修改的文件

- `langchain_app/checks/parameter/parameter.py`
- `langchain_app/checks/parameter/parser.py`
- `langchain_app/checks/parameter/retrieval.py`
- `langchain_app/checks/parameter/semantic.py`
- `langchain_app/checks/parameter/validator.py`
- `langchain_app/checks/parameter/reporter.py`

### 可执行修改方案

#### 第一步：给参数模块定义正式主链路

在 `parameter.py` 中明确主流程：

```text
load_json
  -> collect_params
  -> retrieve_kb_entries
  -> semantic_filter
  -> validate_rows
  -> aggregate_results
  -> render_report
```

#### 第二步：把现有子模块职责固定下来

- `parser.py`
  - 参数采集
  - 数值/单位解析
  - 依据代号提取

- `retrieval.py`
  - Chroma/CNAS 查询
  - 检索结果标准化

- `semantic.py`
  - 参数语义推断
  - 依据候选筛选

- `validator.py`
  - 范围验证
  - 误差验证
  - 不确定度验证

- `reporter.py`
  - 行级表格
  - 批次汇总
  - 最终统计

#### 第三步：保留兼容入口

确保以下函数名仍保留：

```python
def run_llm_mode(...)
def check_parameters(...)
```

这样可避免上层改动过大。

#### 第四步：做新旧结果对拍

不要只看“能跑”，要做固定样本对拍：

- 同一份 JSON
- 原 `param_check.py`
- 新 `langchain_app.checks.parameter.run_llm_mode`

比对：

- PASS 数
- FAIL 数
- REVIEW 数
- 依据匹配
- 关键结论

### 完成标准

以下验证至少要通过：

```powershell
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
& 'D:\conda_envs\langchain\python.exe' test_original_vs_new.py
```

如果没有正式对拍脚本，应补一份。

---

## 4.5 问题 5：tools 层仍回调旧根目录模块

### 现象

`langchain_app/tools/example_tools.py` 当前仍在通过：

- `sys.path.insert(...)`
- `import info_check`
- `import env_check`
- `import location_check`
- `import cycle_check`
- `import param_check`

来调用旧逻辑。

这会造成：

- 新旧双轨长期并存
- tools 层与新 checks 脱节
- 后续维护难度持续上升

### 需要修改的文件

- `langchain_app/tools/example_tools.py`

### 可执行修改方案

将以下函数全部改为调用 `langchain_app.checks`：

- `info_check`
- `environment_check`
- `location_check`
- `cycle_check`
- `parameter_check`

具体改法示例：

#### 旧写法

```python
import info_check
report = info_check.check_certificate_integrity(...)
```

#### 新写法

```python
from langchain_app.checks.integrity import check_certificate_integrity
report = check_certificate_integrity(...)
```

其他四个模块同理。

### 完成标准

用检索命令验证：

```powershell
rg -n "import info_check|import env_check|import location_check|import cycle_check|import param_check|sys.path.insert" langchain_app\tools\example_tools.py
```

目标是：

- 以上旧式调用在 `example_tools.py` 中全部消失

---

## 5. 推荐修改顺序

建议严格按以下顺序执行：

1. 修复循环导入
2. 精简 `checks/__init__.py`
3. 修复 `LLMClient` 初始化方式
4. 让 Graph 独立可编译
5. 修改 tools 层到新 checks
6. 补齐参数核验主链路
7. 做参数核验对拍
8. 最后再更新文档、注释、Agent 角色

原因如下：

- 前 4 步解决“项目不能导入、不能运行”的问题
- 第 5 步解决新旧双轨继续扩大的问题
- 第 6、7 步解决“最关键业务尚未完成”的问题
- 最后收尾项再做，避免返工

---

## 6. 建议的验收命令

建议在 `langchain` 环境中统一执行以下命令：

```powershell
& 'D:\conda_envs\langchain\python.exe' test_langchain_simple.py
& 'D:\conda_envs\langchain\python.exe' test_checks_simple.py
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.verification_graph import build_verification_graph; build_verification_graph().compile(); print('graph_ok')"
```

参数核验补齐后，再增加：

```powershell
& 'D:\conda_envs\langchain\python.exe' test_original_vs_new.py
```

---

## 7. 最终结论

当前这版重构的真实状态不是“失败”，也不是“已经完成”。

更准确的评价是：

**架构层面已经成功，工程层面还差最后一轮收口。**

最值得肯定的点：

- LangGraph 主架构已经建立
- 新 checks 和 retrieval 层已经成型
- 项目不再停留在“仅仅包装旧逻辑”的阶段

最需要尽快解决的点：

- 循环导入
- 错误的 LLMClient 初始化
- 参数核验占位实现
- tools 仍回调旧模块

只要按本文档的顺序推进，这次重构是可以收敛成稳定交付版本的。
