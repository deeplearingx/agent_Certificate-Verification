# LangGraph 重构效果复盘与落地修改建议（2026-03-21）

## 1. 当前重构效果结论

基于 `langchain` 虚拟环境的最新验证，这次重构已经从“架构雏形”推进到了“主骨架可导入、可构图、基础 smoke test 可通过”的阶段。

已经确认通过的内容：

- `D:\conda_envs\langchain\python.exe test_langchain_simple.py`
- `D:\conda_envs\langchain\python.exe test_checks_simple.py`
- `D:\conda_envs\langchain\python.exe test_parameter_simple.py`
- `build_verification_graph().compile()`

说明当前这些部分已经基本收口：

- `langchain_app.core` 的懒加载策略
- `langchain_app.checks` 的懒导入策略
- `LLMClient(config=cfg)` 的调用方式
- 参数子模块的基础拆分与单测接口
- LangGraph 主图的编译

但这次重构**还不能直接判定为“完全交付完成”**，因为仍然存在会在真实执行链路中触发的接口问题和报告组装问题。

---

## 2. 这轮复盘的验证结果

### 2.1 已确认修好的部分

1. `LLMClient(cfg)` 的风险点已经修复。

当前业务模块中的调用点都已经改为：

- `langchain_app/checks/integrity.py`
- `langchain_app/checks/environment.py`
- `langchain_app/checks/cycle.py`
- `langchain_app/checks/location.py`
- `langchain_app/checks/parameter/parameter.py`

统一写法为 `LLMClient(config=cfg)`。

2. `checks/__init__.py` 已改为惰性导入，不再在包初始化阶段全量拉起所有检查模块。

3. 参数子模块的接口兼容问题已经收口。

`parse_value_with_unit()` 保持 2 值返回，`test_parameter_simple.py` 已与之对齐。

---

## 3. 当前仍然存在的已确认问题

### 3.1 严重问题：`location_check` 链路存在真实接口漂移

#### 现象

`check_location()` 当前函数签名是：

```python
def check_location(json_file: str, cfg: Optional[AppConfig] = None) -> str:
```

但是以下调用方仍然传入了它不接受的参数：

- `langchain_app/graph/nodes/location_check.py`
- `langchain_app/tools/example_tools.py`

它们会传：

```python
embedder_obj=...
stop_event=None
```

#### 已验证的最小复现

在 `langchain` 环境中执行：

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.nodes.location_check import location_check_wrapper; from types import SimpleNamespace; print(location_check_wrapper('dummy.json', SimpleNamespace(), embedder=None))"
```

报错为：

```text
TypeError: check_location() got an unexpected keyword argument 'embedder_obj'
```

同样，直接执行 `location_check_node` 也会把错误写入 state：

```text
["校准地点核验失败: check_location() got an unexpected keyword argument 'embedder_obj'"]
```

#### 影响

- Graph 虽然能 `compile()`，但执行到地点核验节点会失败
- tools 层中的 `location_check` 也会失败
- 当前 smoke test 没覆盖这个问题，所以它被隐藏了

#### 建议修改

建议统一成“所有 checks 主入口都接受相同兼容参数”的方式，直接把 `check_location()` 补齐为兼容签名，而不是在每个调用方反复特判。

目标文件：

- `langchain_app/checks/location.py`

建议改法：

```python
def check_location(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
) -> str:
```

说明：

- `location` 模块当前即使没用到 `embedder_obj`，也建议先接受该参数
- 这样可以和 `parameter` 模块主入口保持一致
- graph 节点、tools、wrapper 都不需要再写兼容分支

同时同步清理以下文件中的多余兼容逻辑或注释：

- `langchain_app/graph/nodes/location_check.py`
- `langchain_app/tools/example_tools.py`

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.nodes.location_check import location_check_wrapper; from types import SimpleNamespace; print(type(location_check_wrapper('dummy.json', SimpleNamespace(), embedder=None)).__name__)"
```

通过标准：

- 不再抛出 `unexpected keyword argument`
- 如果文件不存在，允许进入正常的文件读取错误，而不是签名错误

---

### 3.2 严重问题：`pipeline` 与 `assemble_report` 存在重复组装报告的风险

#### 现状

`langchain_app/core/pipeline.py` 当前做了两层报告拼接：

1. 先在 `pipeline.run_verification()` 里构建了一个总报告 header
2. graph 执行后，又把：
   - `integrity_result`
   - `environment_result`
   - `location_result`
   - `cycle_result`
   - `parameter_result`
   - `final_report`
   再次逐段追加进去

而 `langchain_app/graph/nodes/assemble_report.py` 又会自己重新组装一次 `final_report`。

#### 风险

- 同一份报告内容可能被重复拼接两次
- `assemble_report` 里新建的 `VerificationReport()` 没有设置 header，最终可能带出空 header
- UI 侧保存出来的 Markdown 容易出现“先是一份报告，再嵌一份报告”的结构

#### 建议修改

把职责收口成一条清晰链路：

1. `assemble_report_node` 负责组装**唯一正式报告**
2. `pipeline.run_verification()` 只负责：
   - 调 graph
   - 返回 `final_state.final_report`
   - 在异常时做兜底日志

目标文件：

- `langchain_app/graph/nodes/assemble_report.py`
- `langchain_app/core/pipeline.py`

具体建议：

1. 在 `assemble_report_node` 中用 `build_verification_report_header(...)` 构造报告头

需要使用：

- `state.source_pdf_path`
- `state.config.model`
- `state.config.temperature`
- `state.config.topk`

2. 在 `pipeline.run_verification()` 中删除下面这种重复追加逻辑：

- 追加 `final_state.integrity_result`
- 追加 `final_state.environment_result`
- 追加 `final_state.location_result`
- 追加 `final_state.cycle_result`
- 追加 `final_state.parameter_result`
- 再追加 `final_state.final_report`

3. 改为：

```python
if final_state.final_report:
    return final_state.final_report
```

#### 验收标准

最终 Markdown：

- 只出现一份主标题
- 每个核验步骤只出现一次
- 不出现空白 header 字段

---

### 3.3 中等问题：当前测试覆盖不到真实 graph 执行链路

#### 现状

当前通过的测试主要是：

- 导入测试
- graph 编译测试
- 参数子模块单测

但没有一条测试真正执行过：

```text
parse_pdf -> parse_json -> integrity -> environment -> location -> cycle -> parameter -> assemble_report
```

所以 `location_check` 这种运行时签名错误会被漏掉。

#### 建议修改

新增一个 graph 级 smoke test，而不是只测 compile。

目标文件建议：

- 新增 `test_graph_runtime_smoke.py`

建议做法：

1. 使用一个最小 JSON fixture，跳过真实 PDF 解析
2. 直接构造 `VerificationState`
3. 设置：
   - `json_path`
   - `runtime_cfg`
   - `embedder`
   - `llm_client`
4. monkeypatch 掉最重的外部依赖调用，让图至少完整跑完一遍
5. 断言：
   - `final_state.errors == []`
   - `final_state.final_report` 非空
   - 报告中含有 5 个核验章节

#### 验收命令

```powershell
& 'D:\conda_envs\langchain\python.exe' test_graph_runtime_smoke.py
```

---

### 3.4 中等问题：`location` 模块接口没有和其他 checks 形成统一约定

#### 现状

目前几个检查模块的主入口风格不统一：

- `check_environment(json_file, cfg)`
- `check_cycle_reasonableness(json_file, cfg)`
- `check_location(json_file, cfg)`
- `run_llm_mode(json_file, cfg, stop_event=None, embedder_obj=None)`

这也是 graph 节点不得不写兼容性调用的根源之一。

#### 建议修改

统一检查模块的入口签名为：

```python
def xxx_check(
    json_file: str,
    cfg,
    stop_event=None,
    embedder_obj=None,
) -> str:
```

至少要求以下几个入口统一：

- `check_certificate_integrity`
- `check_environment`
- `check_location`
- `check_cycle_reasonableness`
- `check_parameters` / `run_llm_mode`

说明：

- 不是要求每个模块都要用这些参数
- 而是要求它们至少能接受这些参数
- 这样 graph 节点和 tool 层就不需要再做特判

#### 优先级

中等，建议和 3.1 一起做

---

### 3.5 低到中等问题：命名和文案仍有“LangChain 版”遗留

#### 现状

以下文件的命名或说明仍然偏向旧叙述：

- `langchain_app/app_example.py`
- `test_langchain_simple.py`
- 部分注释和输出文案

虽然技术上不阻塞，但会影响后续维护判断，尤其是团队成员会误以为这仍然是“LangChain Agent 主导架构”。

#### 建议修改

建议统一文案为：

- “LangGraph 编排 + LangChain 能力层”

至少更新这些位置：

- `langchain_app/app_example.py`
- `langchain_app/agents/verification_agent.py`
- `test_langchain_simple.py`
- README / docs 中仍写“LangChain 重构版”的章节

---

### 3.6 低优先级问题：环境里仍有 `requests` 依赖告警

#### 现状

所有最新测试都会出现：

```text
RequestsDependencyWarning: urllib3 (...) or chardet/charset_normalizer (...) doesn't match a supported version
```

#### 影响

- 当前不影响导入和基础测试
- 但说明环境依赖并不干净
- 后续如果出现网络请求异常，排障成本会变高

#### 建议修改

在 `langchain` 环境里统一整理这些包版本：

- `requests`
- `urllib3`
- `charset_normalizer`

建议做法：

1. 导出当前版本
2. 对齐到兼容组合
3. 更新到环境说明文档中

这项不需要先改代码，但要记在交付收尾里

---

## 4. 建议的落地修改顺序

### 第一优先级：先修真实运行错误

1. 修 `check_location()` 的签名兼容
2. 删除 graph 和 tools 层为它写的重复兼容逻辑

完成标准：

- `location_check_wrapper(...)` 不再报 `unexpected keyword argument`
- `location_check_node(...)` 不再在进入节点时立即报错

### 第二优先级：收口报告链路

1. `assemble_report_node` 生成唯一正式报告
2. `pipeline.run_verification()` 只返回 graph 的最终报告

完成标准：

- 输出的 Markdown 没有重复章节
- 没有空 header

### 第三优先级：补 runtime smoke test

1. 新增 graph 运行级测试
2. 不再只测导入和 compile

完成标准：

- 至少有一条测试能跑通 graph 的主执行链

### 第四优先级：统一主入口签名

1. 所有 checks 主入口都支持统一参数
2. graph 节点不再写 `try/except TypeError` 兼容调用

完成标准：

- graph 节点代码更简洁
- tools 层不再出现接口猜测式调用

### 第五优先级：统一命名和环境说明

1. 文案从“LangChain 版”更新为“LangGraph 编排版”
2. 整理 `requests` 依赖告警

---

## 5. 推荐的验收命令

### 5.1 基础 smoke test

```powershell
& 'D:\conda_envs\langchain\python.exe' test_langchain_simple.py
& 'D:\conda_envs\langchain\python.exe' test_checks_simple.py
& 'D:\conda_envs\langchain\python.exe' test_parameter_simple.py
```

### 5.2 Graph 构图验收

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.verification_graph import build_verification_graph; g=build_verification_graph(); c=g.compile(); print('graph_ok', sorted(list(c.nodes.keys())))"
```

### 5.3 `location` 接口验收

```powershell
& 'D:\conda_envs\langchain\python.exe' -c "from langchain_app.graph.nodes.location_check import location_check_wrapper; from types import SimpleNamespace; location_check_wrapper('dummy.json', SimpleNamespace(), embedder=None)"
```

通过标准：

- 允许报文件不存在
- 不允许再报 `unexpected keyword argument`

### 5.4 报告去重验收

建议新增一条最小执行链测试，断言：

- 最终报告只包含一个一级标题
- 不出现双份的“完整性/环境/地点/周期/参数”章节

---

## 6. 最终判断

这次重构的最新状态可以这样定性：

- 架构方向：正确
- 主骨架：已经成型
- 基础导入与编译：已基本收口
- 真实运行链路：还差最后一轮接口和报告收尾

最关键的一句话是：

**现在已经不是“大重构失败”，而是“主结构基本稳定，但还存在 1 个确定会炸的运行时接口问题，以及 1 个会影响最终报告质量的组装问题”。**

只要先把这两项修掉，这次 LangGraph 重构就会更接近可交付状态。
