# Docker Deployment Guide

## What this setup gives you

This project is now dockerized with two services:

- `api`: FastAPI backend for task submission, polling, and report retrieval
- `streamlit`: frontend UI that talks to the FastAPI backend over HTTP

This means the project can run in a more production-like shape:

```text
Browser -> Streamlit container -> FastAPI container -> core pipeline
```

## Files added

- `Dockerfile.api`
- `Dockerfile.streamlit`
- `docker-compose.yml`
- `.dockerignore`

## Important note about MinerU

Real `PDF -> MD` parsing depends on `MinerU`.

Some environments can install it directly, while others cannot. For that reason:

- the API image defaults to `INSTALL_MINERU=0`
- this guarantees the image can still build for service smoke testing and `dry_run`
- to enable real MinerU parsing during image build, set:

```bash
INSTALL_MINERU=1
```

If `MinerU` cannot be installed in your environment, the service still works for:

- health checks
- file upload API
- task lifecycle API
- Streamlit -> FastAPI integration
- `dry_run=true` smoke testing

## Quick start

### 1. Prepare environment variables

Create a `.env` file in the repo root if needed:

```env
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
INSTALL_MINERU=0
```

### 2. Build and start

```bash
docker compose up --build
```

### 3. Open services

- FastAPI docs: `http://127.0.0.1:8000/docs`
- Streamlit UI: `http://127.0.0.1:8501`

## Service ports

- FastAPI: `8000`
- Streamlit: `8501`

## Mounted directories

The compose file mounts these host directories into the API container:

- `./models -> /app/models`
- `./vector_db -> /app/vector_db`
- `./local_pdf -> /app/local_pdf`
- `./local_md -> /app/local_md`
- `./local_json -> /app/local_json`
- `./final_reports -> /app/final_reports`
- `./reports -> /app/reports`
- `./output -> /app/output`

Why this matters:

- model files are reused instead of copied into the image
- vector databases stay persistent across container restarts
- generated reports and temporary files remain on the host

## Common commands

### Start in background

```bash
docker compose up -d
```

### View logs

```bash
docker compose logs -f api
docker compose logs -f streamlit
```

### Stop services

```bash
docker compose down
```

### Rebuild after code changes

```bash
docker compose up --build
```

## Recommended validation flow

### 1. Backend health

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### 2. Dry-run task

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/tasks/verify" \
  -F "file=@pdf/sample.pdf" \
  -F "dry_run=true"
```

### 3. Frontend validation

Open Streamlit and click:

- `检查后端健康状态`
- upload a PDF
- enable `Dry Run`
- click `开始智能核验`

This verifies frontend/backend separation is working inside containers.

## Architecture notes

Before serviceization:

```text
Streamlit -> run_verification()
```

After serviceization + containerization:

```text
Browser -> Streamlit -> FastAPI -> run_verification()
```

This is better because:

- frontend and backend are decoupled
- the backend becomes reusable for other clients
- deployment becomes more consistent
- the system looks much closer to a production AI application

