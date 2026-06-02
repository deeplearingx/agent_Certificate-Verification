# 项目启动操作文档

本文档用于说明这个项目在本地和 Docker 环境下的启动方式，默认以 **Windows + PowerShell + conda 环境** 为例。

---

## 1. 项目说明

当前项目有 3 种常见运行方式：

- **CLI 模式**
  - 直接命令行跑单个 PDF
- **本地前后端模式**
  - FastAPI 作为后端
  - Streamlit 作为前端
- **Docker 模式**
  - 容器化运行前后端

推荐的启动优先级：

1. 先跑 **FastAPI 健康检查**
2. 再跑 **Streamlit + FastAPI 联调**
3. 最后再尝试 **真实 PDF 核验**
4. 如需演示部署，再跑 **Docker**

---

## 2. 目录与入口说明

### 主要入口文件

- `main_pipeline.py`
  - 命令行入口
- `api/app.py`
  - FastAPI 后端入口
- `run_fastapi_app.py`
  - FastAPI 启动脚本
- `app.py`
  - Streamlit 前端入口

### 主要输出目录

- `local_pdf/`
  - 上传或待处理 PDF
- `local_md/`
  - PDF 解析得到的 Markdown
- `local_json/`
  - Markdown 解析得到的 JSON
- `final_reports/`
  - 最终核验报告

---

## 3. 启动前准备

## 3.1 进入项目目录

```powershell
cd "d:\workspace\ai大模型开发课\文档核验\document-verification-master"
```

## 3.2 激活 conda 环境

如果你已经有 `langchain` 环境：

```powershell
conda activate langchain
```

如果你不想依赖当前终端环境，也可以始终显式使用该环境的 Python：

```powershell
& "d:\conda_envs\langchain\python.exe" --version
```

## 3.3 配置环境变量

先复制 `.env.example`：

```powershell
Copy-Item .env.example .env
```

然后至少补全：

- `DEEPSEEK_API_KEY`

建议检查这些路径是否正确：

- `EMBED_MODEL_PATH`
- `CNAS_DB_DIR`
- `TEMPERATURE_DB_DIR`
- `GENERAL_CYCLE_DB_DIR`
- `HUAWEI_CYCLE_DB_DIR`
- `ADDRESS_DB_DIR`

## 3.4 安装依赖

如果当前环境还没装依赖：

```powershell
pip install -r requirements.txt
```

如果你想确保一定装到 `langchain` 环境：

```powershell
& "d:\conda_envs\langchain\python.exe" -m pip install -r requirements.txt
```

---

## 4. 最小可运行验证

推荐先做一个最小验证，确认服务层是通的。

### 4.1 启动 FastAPI

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload --log-level debug
```

或者：

```powershell
& "d:\conda_envs\langchain\python.exe" -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload --log-level debug
```

也可以使用启动脚本：

```powershell
python run_fastapi_app.py
```

### 4.2 健康检查

新开一个 PowerShell 窗口，执行：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

如果正常，应返回：

```json
{"status":"ok","service":"document-verification-api","version":"1.0.0"}
```

如果这一步成功，说明：

- FastAPI 已启动
- 路由可访问
- 服务层基本正常

---

## 5. 本地命令行启动

这种方式适合直接跑单个 PDF，不经过前端页面。

```powershell
python main_pipeline.py "pdf\你的文件.pdf"
```

或者：

```powershell
& "d:\conda_envs\langchain\python.exe" main_pipeline.py "pdf\你的文件.pdf"
```

执行完成后，报告一般会输出到：

```text
final_reports\
```

适合场景：

- 快速验证核心 pipeline
- 不需要前端交互
- 排查业务逻辑问题

---

## 6. 本地前后端启动

这是当前最推荐的本地使用方式。

架构如下：

```text
Browser -> Streamlit -> FastAPI -> core pipeline
```

## 6.1 第一步：启动 FastAPI 后端

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload --log-level debug
```

保持这个终端不要关闭。

## 6.2 第二步：启动 Streamlit 前端

另开一个 PowerShell 窗口，执行：

```powershell
streamlit run app.py
```

或者：

```powershell
& "d:\conda_envs\langchain\python.exe" -m streamlit run app.py
```

正常情况下，终端会给出类似地址：

```text
http://localhost:8501
```

浏览器打开即可。

## 6.3 第三步：页面内操作

打开页面后，建议按以下顺序操作：

1. 检查左侧 `FastAPI Base URL`
   - 默认应为 `http://127.0.0.1:8000`
2. 点击“检查后端健康状态”
3. 先勾选 `Dry Run`
4. 上传 PDF
5. 点击“开始智能核验”

### 为什么先用 Dry Run

`Dry Run` 不会真正执行重型解析流程，只验证：

- 前端到后端是否连通
- 文件上传是否正常
- 任务创建是否成功
- 状态轮询是否正常
- 报告获取是否正常

这一步非常适合排查“服务层有没有问题”。

---

## 7. 用 curl 手动调用接口

如果你想不经过 Streamlit，直接验证 API，可以按下面步骤操作。

## 7.1 提交 Dry Run 任务

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/tasks/verify" `
  -F "file=@pdf\时间和频率证书2026\JJG 488-2018瞬时日差测量仪\2GB25013881-0002.pdf" `
  -F "dry_run=true"
```

成功后会返回：

- `task_id`
- `status`
- `status_url`
- `report_url`

## 7.2 查询任务状态

把返回的 `task_id` 替换进去：

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/tasks/你的task_id"
```

## 7.3 获取报告

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/tasks/你的task_id/report"
```

---

## 8. 真实核验启动方式

如果你要跑真实任务，不要加 `dry_run=true`。

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/tasks/verify" `
  -F "file=@pdf\时间和频率证书2026\JJG 488-2018瞬时日差测量仪\2GB25013881-0002.pdf"
```

或者直接在 Streamlit 页面里取消勾选 `Dry Run`。

### 注意

真实任务会走完整链路：

`PDF -> Markdown -> JSON -> 多维核验 -> 报告生成`

此时如果缺少依赖，最常见的报错就是：

- `No module named 'mineru'`

因为真实 `PDF -> Markdown` 依赖 `MinerU`。

---

## 9. Docker 启动方式

适合做容器化演示或部署验证。

## 9.1 开发版 Docker

### 1. 准备 `.env`

建议至少包含：

```env
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
INSTALL_MINERU=0
```

说明：

- `INSTALL_MINERU=0`
  - 适合先验证容器构建、接口链路和 dry run
- 如果你的环境支持 MinerU，再改成 `1`

### 2. 启动

```powershell
docker compose up --build
```

后台运行：

```powershell
docker compose up -d --build
```

### 3. 访问地址

- FastAPI 文档：`http://127.0.0.1:8000/docs`
- Streamlit 页面：`http://127.0.0.1:8501`

### 4. 查看日志

```powershell
docker compose logs -f api
docker compose logs -f streamlit
```

### 5. 停止

```powershell
docker compose down
```

---

## 10. 生产风格 Docker 启动方式

这版通过 Nginx 做统一入口。

架构如下：

```text
Browser -> Nginx -> Streamlit
               -> FastAPI
```

## 10.1 启动

```powershell
docker compose -f docker-compose.prod.yml up --build
```

后台运行：

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

## 10.2 访问地址

- 统一入口：`http://127.0.0.1/`
- API 健康检查：`http://127.0.0.1/api/v1/health`
- Swagger 文档：`http://127.0.0.1/docs`

## 10.3 查看日志

```powershell
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f streamlit
```

## 10.4 停止

```powershell
docker compose -f docker-compose.prod.yml down
```

---

## 11. 推荐的启动顺序

如果你第一次接手这个项目，建议按下面顺序来：

### 路线一：最快验证服务层

1. 启动 FastAPI
2. 调 `GET /api/v1/health`
3. 提交 `dry_run=true` 任务
4. 查询状态
5. 获取报告

### 路线二：完整本地联调

1. 启动 FastAPI
2. 启动 Streamlit
3. 页面里先跑 `Dry Run`
4. 再尝试真实核验

### 路线三：演示部署能力

1. 准备 `.env`
2. 运行 `docker compose up --build`
3. 或运行生产风格 `docker compose -f docker-compose.prod.yml up --build`

---

## 12. 常见问题排查

## 12.1 健康检查失败

现象：

- `curl http://127.0.0.1:8000/api/v1/health` 无返回
- 浏览器打不开 `http://127.0.0.1:8000/docs`

排查：

1. 确认 FastAPI 终端是否还在运行
2. 确认启动命令是否正确
3. 确认 `8000` 端口未被占用

推荐命令：

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload --log-level debug
```

---

## 12.2 Streamlit 页面打不开

排查：

1. 确认是否已执行：

```powershell
streamlit run app.py
```

2. 查看终端输出的本地地址，一般是：

```text
http://localhost:8501
```

3. 确认 `8501` 端口没有冲突

---

## 12.3 页面里提示后端不可用

排查：

1. 确认 FastAPI 是否已启动
2. 确认页面左侧 `FastAPI Base URL` 是否为：

```text
http://127.0.0.1:8000
```

3. 在单独终端执行：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

---

## 12.4 真实任务报 `No module named 'mineru'`

原因：

- 真实 `PDF -> Markdown` 依赖 `MinerU`
- 当前环境没有安装 `mineru`

现象：

- `PDF → MD failed: No module named 'mineru'`
- `markdown file was not generated`
- `Verification finished without producing a report`

建议：

1. 先使用 `Dry Run` 验证服务链路
2. 再补装 `MinerU`
3. 真实任务需要确认 `MinerU` 依赖可用

---

## 12.5 没有生成报告

可能原因：

- 文档解析失败
- Markdown 没生成
- JSON 抽取失败
- 中间某个核验模块报错

排查建议：

1. 看 FastAPI 终端日志
2. 看 Streamlit 页面中的错误信息
3. 看任务状态接口返回的 `errors`
4. 检查：
   - `local_md/`
   - `local_json/`
   - `final_reports/`

---

## 13. 常用启动命令速查

### 本地 FastAPI

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload --log-level debug
```

### 本地 Streamlit

```powershell
streamlit run app.py
```

### 命令行跑单个 PDF

```powershell
python main_pipeline.py "pdf\你的文件.pdf"
```

### Docker 开发版

```powershell
docker compose up --build
```

### Docker 生产风格版

```powershell
docker compose -f docker-compose.prod.yml up --build
```

---

## 14. 推荐你当前最常用的启动方式

如果你是为了：

### 调试接口和前后端联调

推荐：

1. 启动 FastAPI
2. 启动 Streamlit
3. 先跑 `Dry Run`

### 跑真实业务

推荐：

1. 确认 `MinerU` 已安装
2. 启动 FastAPI
3. 用 Streamlit 或 curl 提交真实任务

### 演示部署能力

推荐：

1. Docker 开发版
2. 再演示生产风格 Nginx 统一入口

---

## 15. 相关文档

- `README.md`
- `docs/fastapi_service.md`
- `docs/docker_deployment.md`
- `docs/docker_production.md`

