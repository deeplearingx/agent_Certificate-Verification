# 项目文档目录

本目录只保留当前 LangChain / LangGraph 主线开发需要的核心文档。旧版重构方案、面试说明、部署草稿、阶段复盘等历史材料不再放在 `docs/` 主目录，避免和当前交付文档混淆。

## 当前保留文档

- [`模块需求归纳.md`](./模块需求归纳.md)：按 PDF 解析、RAG、基础核验、参数核验、Graph 编排、接口和测试归纳整体需求。
- [`基础核验模块需求说明.md`](./基础核验模块需求说明.md)：整理环境条件、校准地点、校准周期的输入输出、比较规则、状态口径和当前实现差异。
- [`参数核验模块需求说明.md`](./参数核验模块需求说明.md)：整理参数核验的能力库对比、范围/误差/不确定度规则、仪器规则分流、`▽` 标识和 `P/F/P*` 后续规则。

## 配套文档

- [`../README.md`](../README.md)：项目总说明、架构、运行方式。
- [`../langchain_app/DEVELOPMENT_ASSIGNMENT.md`](../langchain_app/DEVELOPMENT_ASSIGNMENT.md)：开发分工与输入输出契约。
- [`../langchain_app/PROJECT_STRUCTURE.md`](../langchain_app/PROJECT_STRUCTURE.md)：主线代码结构说明。
- [`../langchain_app/CODING_STANDARDS.md`](../langchain_app/CODING_STANDARDS.md)：编码规范与报告状态口径。
- [`../langchain_app/checks/parameter/PROFILE_ARCHITECTURE.md`](../langchain_app/checks/parameter/PROFILE_ARCHITECTURE.md)：参数核验 profile / rule_set 拆分说明。

