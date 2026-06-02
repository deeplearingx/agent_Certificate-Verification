# Document Verification

This project verifies calibration certificate PDFs through a multi-stage pipeline:

`PDF -> Markdown -> JSON -> integrity/environment/location/cycle/parameter checks`

## Entrypoints

- Web UI: `streamlit run app.py` (this Streamlit UI now acts as a client of the FastAPI backend)
- CLI: `python main_pipeline.py <pdf_path>`
- API: `uvicorn api.app:app --host 0.0.0.0 --port 8000`
- Docker: `docker compose up --build`
- Production-style Docker: `docker compose -f docker-compose.prod.yml up --build`

## Configuration

Configuration is centralized in [config/settings.py](/d:/workspace/ai大模型开发课/文档核验/document-verification-master/config/settings.py).

1. Copy `.env.example` to `.env` or export equivalent environment variables.
2. Set `DEEPSEEK_API_KEY`.
3. Verify local paths for:
   - `EMBED_MODEL_PATH`
   - `CNAS_DB_DIR`
   - `TEMPERATURE_DB_DIR`
   - `GENERAL_CYCLE_DB_DIR`
   - `HUAWEI_CYCLE_DB_DIR`
   - `ADDRESS_DB_DIR`

## Key Directories

- `local_pdf/`: uploaded or input PDFs
- `local_md/`: parsed markdown cache
- `local_json/`: structured extraction cache
- `final_reports/`: final markdown reports
- `vector_db/`: Chroma vector databases
- `models/`: local embedding/model artifacts

## Structure

- `app.py`: Streamlit UI
- `main_pipeline.py`: CLI entrypoint
- `core/pipeline.py`: shared verification pipeline
- `config/settings.py`: centralized runtime settings
- `checks` remain as top-level modules for now:
  - `info_check.py`
  - `env_check.py`
  - `location_check.py`
  - `cycle_check.py`
  - `param_check.py`

## Notes

- The repository still contains research scripts and legacy parsers.
- Current refactoring focuses on configuration safety and shared pipeline reuse, not business rule changes.
- FastAPI serviceization guide: `docs/fastapi_service.md`
- Startup guide: `docs/startup_guide.md`
- Docker deployment guide: `docs/docker_deployment.md`
- Production-style Docker + Nginx guide: `docs/docker_production.md`
- When using `app.py`, start the FastAPI backend first and then launch Streamlit.
