# Production-Style Docker Deployment

## What this adds

This setup adds:

- `docker-compose.prod.yml`
- `nginx/default.conf`

The production-style topology becomes:

```text
Browser -> Nginx -> Streamlit
               -> FastAPI
```

Nginx is the single public entrypoint:

- `/` -> Streamlit frontend
- `/api/*` -> FastAPI backend
- `/docs` -> FastAPI Swagger UI

## Why this is better than exposing both services directly

Compared with the development compose file:

- users only need one public address
- frontend and backend can stay on private container ports
- reverse proxy settings are centralized
- it matches common production deployment patterns more closely

## Files

- `docker-compose.prod.yml`
- `nginx/default.conf`

## Start the production-style stack

```bash
docker compose -f docker-compose.prod.yml up --build
```

Run in background:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## Access points

- App entry: `http://127.0.0.1/`
- API health: `http://127.0.0.1/api/v1/health`
- Swagger docs: `http://127.0.0.1/docs`

## How routing works

### Frontend

Requests to `/` go to the Streamlit container.

### Backend

Requests to `/api/` go to the FastAPI container.

The Streamlit frontend is configured with:

```text
STREAMLIT_API_BASE_URL=http://nginx
```

So inside the container network it also talks through Nginx instead of calling
the API container directly. This keeps the frontend aligned with the same public
routing layout users see externally.

## Environment variables

Recommended `.env` example:

```env
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
INSTALL_MINERU=0
```

If your environment supports MinerU image installation, change:

```env
INSTALL_MINERU=1
```

## Common commands

### View logs

```bash
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f streamlit
```

### Stop services

```bash
docker compose -f docker-compose.prod.yml down
```

## Recommended verification flow

### 1. Reverse proxy health

```bash
curl http://127.0.0.1/api/v1/health
```

Expected:

```json
{"status":"ok","service":"document-verification-api","version":"1.0.0"}
```

### 2. Open the frontend

Visit:

```text
http://127.0.0.1/
```

### 3. Run a dry-run task from the UI

This verifies:

- Nginx routing
- Streamlit frontend
- FastAPI backend
- frontend/backend decoupling

## What this means on your resume

You can now accurately say:

- completed containerized deployment for both frontend and backend
- added Nginx reverse proxy and unified ingress for AI service delivery
- moved the project closer to a production-style architecture

