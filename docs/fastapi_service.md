# FastAPI Service Guide

## What "serviceization" means here

Serviceization means separating:

- transport layer: HTTP API, file upload, task status endpoints
- business layer: the existing verification pipeline in `core/pipeline.py`
- runtime concerns: task queue, status tracking, report persistence

In this project, `run_verification()` stays as the core business capability. The
new FastAPI layer only wraps it so other systems can call it through HTTP.

## Why this is useful

Compared with running `main_pipeline.py` or Streamlit locally, a service layer:

- gives you stable API endpoints
- lets frontend or other systems call the verifier
- supports long-running task polling
- makes containerization and deployment easier

## New API entrypoints

- `GET /api/v1/health`: health check
- `POST /api/v1/tasks/verify`: upload a PDF and create a verification task
- `GET /api/v1/tasks/{task_id}`: poll task status
- `POST /api/v1/tasks/{task_id}/cancel`: request cancellation
- `GET /api/v1/tasks/{task_id}/report`: fetch the markdown report after completion

## Request flow

1. Client uploads a PDF to `POST /api/v1/tasks/verify`
2. The API stores the file in `local_pdf/`
3. A background worker calls the existing `run_verification()` pipeline
4. Pipeline hooks update task progress, status, warnings, and errors
5. The report is saved in `final_reports/`
6. The client polls the task endpoint and fetches the final report

## How to run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Or:

```bash
python run_fastapi_app.py
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Example usage

### 1. Create a task

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/tasks/verify" ^
  -H "accept: application/json" ^
  -H "Content-Type: multipart/form-data" ^
  -F "file=@local_pdf\\sample.pdf" ^
  -F "api_key=your_deepseek_api_key"
```

Example response:

```json
{
  "task_id": "d9c4a0f5-6c02-4ccb-8e45-9b8d3158be26",
  "status": "pending",
  "filename": "sample.pdf",
  "status_url": "/api/v1/tasks/d9c4a0f5-6c02-4ccb-8e45-9b8d3158be26",
  "report_url": "/api/v1/tasks/d9c4a0f5-6c02-4ccb-8e45-9b8d3158be26/report"
}
```

### 2. Poll status

```bash
curl "http://127.0.0.1:8000/api/v1/tasks/d9c4a0f5-6c02-4ccb-8e45-9b8d3158be26"
```

### 3. Fetch report

```bash
curl "http://127.0.0.1:8000/api/v1/tasks/d9c4a0f5-6c02-4ccb-8e45-9b8d3158be26/report"
```

## Why the API is async-by-design

Document verification is a long-running job:

- PDF parsing can be slow
- embedding model loading is expensive
- downstream verification makes multiple model and retrieval calls

So the API uses a task-based pattern instead of blocking the request. This is a
common serviceization step for Agent and RAG systems.

## How to evolve this into a production service

Current version:

- single-process FastAPI
- in-memory task registry
- background thread execution

Next upgrades:

1. Replace in-memory tasks with Redis or a database
2. Move background jobs to Celery, RQ, or a message queue
3. Add authentication and rate limiting
4. Add structured logging and monitoring
5. Containerize with Docker and mount model/vector-db directories

## Serviceization checklist

When you serviceize an AI workflow, try to separate these layers:

- core capability: keep your pipeline callable as a plain Python function
- API adapter: handle HTTP inputs and outputs only
- task runtime: handle queueing, status, cancellation, retries
- storage: keep reports, uploaded files, and task metadata outside the business logic

That separation is exactly what the new FastAPI wrapper is doing around this project.

