# Agent 面试代码版复习笔记

这份文档补充项目里的关键代码实现，适合在面试前快速对照。  
重点不是逐行背代码，而是理解“这段代码负责什么、为什么这样设计、面试时如何讲”。

---

## 1. LangGraph 的状态对象

文件：`langchain_app/graph/state.py`

```python
class VerificationState(BaseModel):
    source_pdf_path: Optional[str] = None
    md_path: Optional[str] = None
    json_path: Optional[str] = None

    config: Optional[Any] = None
    runtime_cfg: Optional[Any] = None
    embedder: Optional[Any] = None
    llm_client: Optional[Any] = None

    integrity_result: Optional[str] = None
    environment_result: Optional[str] = None
    location_result: Optional[str] = None
    cycle_result: Optional[str] = None
    parameter_result: Optional[str] = None

    final_report: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    should_stop: bool = False
    current_step: Optional[str] = None
    progress: float = 0.0
```

### 代码含义

- `source_pdf_path / md_path / json_path`
  - 记录文档处理中间结果
- `config / runtime_cfg / embedder / llm_client`
  - 保存运行依赖
- `integrity_result` 等字段
  - 记录各核验节点输出
- `logs / warnings / errors`
  - 让状态对象具备可观测性
- `should_stop`
  - 控制工作流是否提前终止
- `current_step / progress`
  - 方便前端和 API 展示任务进度

### 面试怎么讲

> 我在 LangGraph 版本里设计了统一的状态对象，让节点之间通过状态传递中间结果、错误信息和流程控制信号，而不是依赖全局变量。这样工作流更清晰，也更适合做条件路由和可观测性扩展。

---

## 2. 节点函数怎么定义

文件：`langchain_app/graph/nodes/parse_pdf.py`

```python
def parse_pdf_node(state: VerificationState) -> VerificationState:
    state.set_progress(0.1, "PDF解析")
    state.add_log("开始PDF解析")

    try:
        pdf_path = Path(state.source_pdf_path)
        md_path = pdf_to_md_first_step(
            pdf_file_path=pdf_path,
            config=state.config,
            hooks=None,
            stop_event=None,
        )

        if md_path is None:
            raise Exception("PDF解析失败")

        state.md_path = str(md_path)
        state.set_progress(0.2, "PDF解析完成")
        state.add_log(f"PDF解析成功: {md_path}")
    except Exception as e:
        state.add_error(f"PDF解析失败: {e}")
        state.should_stop = True

    return state
```

### 代码含义

- 节点输入是 `state`
- 节点输出也是 `state`
- 节点内部只做自己这一步的逻辑
- 成功时更新中间结果和进度
- 失败时记录错误并设置 `should_stop`

### 面试怎么讲

> LangGraph 节点的核心模式就是“读状态、做处理、写回状态”。我这里让节点只关心自己这一段业务，并在出错时把错误信息写回状态，而不是让整个流程直接崩掉。

---

## 3. 条件路由是怎么做的

文件：`langchain_app/graph/nodes/integrity_check.py`

```python
def integrity_check_node(state: VerificationState) -> VerificationState:
    state.set_progress(0.5, "完整性核验")
    state.add_log("开始完整性核验")

    try:
        report = check_certificate_integrity(
            state.json_path,
            cfg=state.runtime_cfg
        )

        state.integrity_result = report

        if "核验终止报告" in report or "系统拒绝处理" in report:
            state.should_stop = True
            state.add_warning("报告包含终止标记，将提前结束流程")

        state.set_progress(0.6, "完整性核验完成")
    except Exception as e:
        state.add_error(f"完整性核验失败: {e}")
        state.should_stop = True

    return state
```

### 代码含义

- 完整性节点先做业务判断
- 如果发现证书应被拒绝，设置 `should_stop = True`
- 图编排层再根据这个字段决定是否继续

### 面试怎么讲

> 我把“是否终止流程”的业务判断放在完整性节点里，但真正的流程跳转不在节点内部硬编码，而是在图层做条件路由。这样业务规则和流程控制是分开的。

---

## 4. 图是怎么编排的

文件：`langchain_app/graph/verification_graph.py`

```python
graph = StateGraph(VerificationState)

graph.add_node("parse_pdf", parse_pdf_node)
graph.add_node("parse_json", parse_json_node)
graph.add_node("integrity_check", integrity_check_node)
graph.add_node("environment_check", environment_check_node)
graph.add_node("location_check", location_check_node)
graph.add_node("cycle_check", cycle_check_node)
graph.add_node("parameter_check", parameter_check_node)
graph.add_node("assemble_report", assemble_report_node)

graph.set_entry_point("parse_pdf")

graph.add_edge("parse_pdf", "parse_json")
graph.add_edge("parse_json", "integrity_check")

graph.add_conditional_edges(
    "integrity_check",
    lambda state: "assemble_report" if state.should_stop else "environment_check",
    {
        "assemble_report": "assemble_report",
        "environment_check": "environment_check",
    },
)

graph.add_edge("environment_check", "location_check")
graph.add_edge("location_check", "cycle_check")
graph.add_edge("cycle_check", "parameter_check")
graph.add_edge("parameter_check", "assemble_report")
graph.add_edge("assemble_report", END)
```

### 代码含义

- `add_node`
  - 定义业务阶段
- `add_edge`
  - 定义固定流转
- `add_conditional_edges`
  - 定义条件路由
- `assemble_report -> END`
  - 表示所有路径最终汇总到报告节点

### 面试怎么讲

> 我把原本脚本里的串行阶段拆成了图节点。普通阶段通过 `add_edge` 串起来，完整性校验这种带分支的阶段通过 `add_conditional_edges` 管理，这样工作流更可扩展，也更容易解释。

---

## 5. 报告节点怎么汇总所有结果

文件：`langchain_app/graph/nodes/assemble_report.py`

```python
def assemble_report_node(state: VerificationState) -> VerificationState:
    state.set_progress(1.0, "报告组装")
    state.add_log("开始报告组装")

    try:
        report = VerificationReport()
        source_name = Path(state.source_pdf_path).name if state.source_pdf_path else ""
        report.set_header(
            source_name=source_name,
            model=getattr(state.runtime_cfg, "model", ""),
            temperature=getattr(state.runtime_cfg, "temperature", 0.0),
            topk=getattr(state.runtime_cfg, "topk", 3)
        )

        if state.integrity_result:
            report.add_section("## 第一步：完整性核验")
            report.add_section(state.integrity_result)

        if state.environment_result:
            report.add_section("## 第二步：环境条件核验", prepend_divider=True)
            report.add_section(state.environment_result)

        if state.location_result:
            report.add_section("## 第三步：校准地点核验", prepend_divider=True)
            report.add_section(state.location_result)

        state.final_report = report.render()
    except Exception as e:
        state.add_error(f"报告组装失败: {e}")

    return state
```

### 代码含义

- 报告节点不负责判断，只负责汇总
- 它读取前面节点的结果并统一渲染成最终报告
- 这是典型的“汇聚节点”

### 面试怎么讲

> 我把报告生成单独做成最后一个节点，让它只负责聚合前面各阶段的结果。这样前面的节点只输出业务结果，最后由统一节点负责展示层格式化。

---

## 6. 顺序版 pipeline 是怎么组织的

文件：`core/pipeline.py`

```python
check_plan = [
    ("Processing [2/6]: Integrity check", 30, InfoCheckRunner(), hooks.emit_error, "Integrity check completed", "完整性核验异常"),
    ("Processing [3/6]: Environment check", 50, EnvironmentCheckRunner(), hooks.emit_warning, None, "环境核验异常"),
    ("Processing [4/6]: Location check", 65, LocationCheckRunner(), hooks.emit_warning, "Location check completed", "地点核验异常"),
    ("Processing [5/6]: Cycle check", 70, CycleCheckRunner(), hooks.emit_warning, None, "周期核验异常"),
    ("Processing [6/6]: Parameter check", 90, ParameterCheckRunner(), hooks.emit_error, None, "参数核验异常"),
]

for status_text, progress, runner, error_hook, success_message, error_title in check_plan:
    hooks.emit_status(status_text)
    hooks.emit_progress(progress)
    try:
        result = runner.run(
            json_path=str(json_path),
            runtime_cfg=runtime_cfg,
            stop_event=stop_event,
            embedder=shared_embedder,
        )
        report.add_section(result.report, prepend_divider=True)
        if result.should_stop:
            hooks.emit_error("Certificate rejected by integrity check")
            return report.render()
    except Exception as exc:
        error_hook(f"{runner.name} check failed: {exc}")
```

### 代码含义

- 顺序版 pipeline 用 `check_plan` 统一组织各核验阶段
- 每个阶段都遵循类似模式：
  - 更新状态
  - 执行 runner
  - 收集报告
  - 处理异常
- 这是迁移到 LangGraph 之前的基础版本

### 面试怎么讲

> 我一开始保留了顺序版 pipeline，用统一的 `check_plan` 组织核验阶段，这样便于快速跑通业务闭环，也方便后续逐步迁移到 LangGraph，而不是一次性重写全部逻辑。

---

## 7. Hooks 解耦是怎么做的

文件：`core/pipeline.py`

```python
@dataclass
class PipelineHooks:
    set_status: Optional[Callable[[str], None]] = None
    set_progress: Optional[Callable[[int], None]] = None
    info: Optional[Callable[[str], None]] = None
    warning: Optional[Callable[[str], None]] = None
    error: Optional[Callable[[str], None]] = None
    success: Optional[Callable[[str], None]] = None
```

### 代码含义

- 核心 pipeline 不直接依赖具体 UI
- CLI、FastAPI、Streamlit 都能挂接这些回调
- 这是一种轻量解耦机制

### 面试怎么讲

> 我用 hooks 把核心流程和外部展示层解耦了。这样同一套 `run_verification()` 既能被命令行调用，也能被 FastAPI 包装，还能把状态同步回前端。

---

## 8. FastAPI 任务化是怎么实现的

文件：`api/app.py`

```python
TASK_LOCK = Lock()
TASKS: dict[str, dict[str, Any]] = {}
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="verify-api")
EMBEDDER_CACHE: dict[str, Any] = {}
```

### 代码含义

- `TASKS`
  - 保存任务状态
- `TASK_LOCK`
  - 保证并发安全
- `EXECUTOR`
  - 后台线程池执行长任务
- `EMBEDDER_CACHE`
  - 避免 embedding 模型重复加载

### 面试怎么讲

> 由于文档核验是长任务，我没有做同步阻塞接口，而是用内存任务表加线程池实现了一个轻量任务系统，适合单机演示和服务化验证。

---

## 9. FastAPI 的异步任务提交接口

文件：`api/app.py`

```python
@APP.post("/api/v1/tasks/verify", response_model=TaskCreateResponse, status_code=202)
async def submit_verification_task(
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(default=None),
    model: Optional[str] = Form(default=None),
    temperature: Optional[float] = Form(default=None),
    max_tokens: Optional[int] = Form(default=None),
    topk: Optional[int] = Form(default=None),
    dry_run: bool = Form(default=False),
) -> TaskCreateResponse:
```

### 代码含义

- 用 `multipart/form-data` 上传 PDF
- 附带模型参数和 `dry_run` 开关
- 返回 `202` 表示任务已受理

### 面试怎么讲

> 我把接口设计成异步受理模式，提交任务后先返回 `task_id`，前端再轮询状态。这是 Agent 和 RAG 系统中非常常见的服务化方式。

---

## 10. 后台任务如何复用核心 pipeline

文件：`api/app.py`

```python
def _submit_verification_task(task_id: str) -> None:
    EXECUTOR.submit(_run_verification_task, task_id)

def _run_verification_task(task_id: str) -> None:
    config = _build_config_for_task(task_id)
    embedder = _get_shared_embedder(str(config.embed_model_path))
    report = run_verification(
        pdf_file_path=pdf_path,
        config=config,
        hooks=_task_hooks(task_id),
        stop_event=stop_event,
        embedder=embedder,
    )
```

### 代码含义

- 真正的业务逻辑还是 `run_verification()`
- FastAPI 只负责：
  - 收参数
  - 管任务
  - 调 pipeline
  - 保存报告

### 面试怎么讲

> 我没有把业务逻辑写进路由函数，而是保留 `run_verification()` 作为核心能力，再由 FastAPI 做一层服务包装。这样核心逻辑可以被 CLI、API、前端同时复用。

---

## 11. 面试时最推荐讲的三段代码

如果时间有限，优先讲这三段：

1. `VerificationState`
   - 体现状态管理和可观测性
2. `build_verification_graph`
   - 体现 Agent 工作流编排和条件路由
3. `submit_verification_task + _run_verification_task`
   - 体现服务化、长任务处理和核心能力复用

---

## 12. 代码细节如何转成设计表达

### 不要这样讲

- 这里我定义了一个函数
- 这里我又调了一个模块
- 这里我写了个 if

### 更好的讲法

- 这里我把节点输入输出统一成状态对象，目的是降低模块之间耦合
- 这里我用条件路由处理完整性失败后的早停，避免不必要的后续计算
- 这里我把长任务改成任务提交和轮询模式，是为了适配真实服务场景

---

## 13. 最后一句总结

这套代码最值得讲的不是“用了哪些框架”，而是你如何把：

- 文档解析
- 结构化抽取
- 多知识库 RAG
- 规则校验
- LangGraph 工作流
- FastAPI 服务化

组织成一个既能跑通业务、又能支撑工程落地的 Agent 系统。

