from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from langchain_app.core import PipelineHooks, load_shared_embedder, run_verification
from langchain_app.utils import AppConfig, get_app_config


APP = FastAPI(
    title="Document Verification API",
    version="1.0.0",
    description=(
        "Service layer for the calibration-certificate verification pipeline. "
        "Submit a PDF, poll task status, and fetch the generated markdown report."
    ),
)

TASK_LOCK = Lock()
TASKS: dict[str, dict[str, Any]] = {}
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="verify-api")
EMBEDDER_LOCK = Lock()
EMBEDDER_CACHE: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str
    filename: str
    status_url: str
    report_url: str
    dry_run: bool = False


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    filename: str
    created_at: str
    updated_at: str
    progress: int = 0
    current_step: Optional[str] = None
    logs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    report_path: Optional[str] = None


class ReportResponse(BaseModel):
    task_id: str
    status: str
    report: str
    report_path: Optional[str] = None


class CancelResponse(BaseModel):
    task_id: str
    status: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_filename(filename: str) -> str:
    candidate = Path(filename or "uploaded.pdf").name
    return candidate or "uploaded.pdf"


def _serialize_task(task: dict[str, Any]) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        filename=task["filename"],
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        progress=task["progress"],
        current_step=task.get("current_step"),
        logs=list(task.get("logs", [])),
        warnings=list(task.get("warnings", [])),
        errors=list(task.get("errors", [])),
        report_path=task.get("report_path"),
    )


def _get_task(task_id: str) -> dict[str, Any]:
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        return task


def _create_task_record(task_id: str, pdf_path: Path, original_name: str, config: AppConfig) -> str:
    timestamp = _utc_now()
    record = {
        "task_id": task_id,
        "status": "pending",
        "filename": original_name,
        "pdf_path": str(pdf_path),
        "report_path": None,
        "report": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "progress": 0,
        "current_step": "queued",
        "logs": [],
        "warnings": [],
        "errors": [],
        "stop_event": Event(),
        "config_overrides": {},
        "config_root": str(config.root_dir),
    }
    with TASK_LOCK:
        TASKS[task_id] = record
    return task_id


def _update_task(task_id: str, **changes: Any) -> None:
    with TASK_LOCK:
        task = TASKS[task_id]
        task.update(changes)
        task["updated_at"] = _utc_now()


def _append_task_message(task_id: str, key: str, message: str) -> None:
    with TASK_LOCK:
        task = TASKS[task_id]
        bucket = task.setdefault(key, [])
        bucket.append(str(message))
        if len(bucket) > 200:
            del bucket[:-200]
        task["updated_at"] = _utc_now()


def _task_hooks(task_id: str) -> PipelineHooks:
    def set_status(message: str) -> None:
        _update_task(task_id, current_step=message)
        _append_task_message(task_id, "logs", f"STATUS: {message}")

    def set_progress(value: int) -> None:
        _update_task(task_id, progress=int(value))

    def info(message: str) -> None:
        _append_task_message(task_id, "logs", message)

    def warning(message: str) -> None:
        _append_task_message(task_id, "warnings", message)

    def error(message: str) -> None:
        _append_task_message(task_id, "errors", message)

    def success(message: str) -> None:
        _append_task_message(task_id, "logs", f"SUCCESS: {message}")

    return PipelineHooks(
        set_status=set_status,
        set_progress=set_progress,
        info=info,
        warning=warning,
        error=error,
        success=success,
    )


def _get_shared_embedder(model_path: str) -> Any:
    with EMBEDDER_LOCK:
        if model_path not in EMBEDDER_CACHE:
            EMBEDDER_CACHE[model_path] = load_shared_embedder(model_path)
        return EMBEDDER_CACHE[model_path]


def _build_config_for_task(task_id: str) -> AppConfig:
    task = _get_task(task_id)
    base_config = get_app_config()
    overrides = task.get("config_overrides", {})
    if overrides:
        return base_config.with_overrides(**overrides).ensure_directories()
    return base_config


def _save_report(task_id: str, config: AppConfig, pdf_path: Path, report: str) -> Path:
    report_path = config.final_reports_dir / f"Report_{pdf_path.stem}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    _update_task(task_id, report_path=str(report_path), report=report)
    return report_path


def _run_verification_task(task_id: str) -> None:
    task = _get_task(task_id)
    pdf_path = Path(task["pdf_path"])
    stop_event = task["stop_event"]
    config = _build_config_for_task(task_id)

    _update_task(task_id, status="running", current_step="starting", progress=0)

    try:
        embedder = _get_shared_embedder(str(config.embed_model_path))
        report = run_verification(
            pdf_file_path=pdf_path,
            config=config,
            hooks=_task_hooks(task_id),
            stop_event=stop_event,
            embedder=embedder,
        )

        if stop_event.is_set():
            if report:
                _save_report(task_id, config, pdf_path, report)
            _update_task(task_id, status="cancelled", current_step="cancelled")
            return

        if not report:
            raise RuntimeError("Verification finished without producing a report.")

        _save_report(task_id, config, pdf_path, report)
        _update_task(task_id, status="completed", current_step="completed", progress=100)
    except Exception as exc:
        _append_task_message(task_id, "errors", str(exc))
        _update_task(task_id, status="failed", current_step="failed")


def _submit_verification_task(task_id: str) -> None:
    EXECUTOR.submit(_run_verification_task, task_id)


def _normalize_overrides(
    *,
    api_key: Optional[str],
    model: Optional[str],
    temperature: Optional[float],
    max_tokens: Optional[int],
    topk: Optional[int],
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if api_key:
        overrides["api_key"] = api_key
    if model:
        overrides["model"] = model
    if temperature is not None:
        overrides["temperature"] = temperature
    if max_tokens is not None:
        overrides["max_tokens"] = max_tokens
    if topk is not None:
        overrides["topk"] = topk
    return overrides


def _complete_dry_run_task(task_id: str) -> None:
    task = _get_task(task_id)
    pdf_path = Path(task["pdf_path"])
    content = "\n".join(
        [
            "# Dry Run Verification Report",
            "",
            f"- task_id: `{task_id}`",
            f"- filename: `{task['filename']}`",
            f"- source_path: `{pdf_path}`",
            "",
            "This is a smoke-test report generated by the FastAPI service layer.",
            "It proves the HTTP upload -> task creation -> polling -> report retrieval",
            "workflow is working without invoking the heavy verification pipeline.",
        ]
    )
    config = _build_config_for_task(task_id)
    _update_task(task_id, status="running", current_step="dry_run", progress=30)
    _append_task_message(task_id, "logs", "Dry-run task accepted.")
    _append_task_message(task_id, "logs", "Skipped heavy verification pipeline.")
    _save_report(task_id, config, pdf_path, content)
    _update_task(task_id, status="completed", current_step="completed", progress=100)


@APP.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="document-verification-api",
        version=APP.version,
    )


@APP.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="document-verification-api",
        version=APP.version,
    )


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
    filename = _safe_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    config = get_app_config().ensure_directories()
    upload_bytes = await file.read()
    if not upload_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    record_id = str(uuid4())
    pdf_path = config.local_pdf_dir / f"{record_id}_{filename}"
    pdf_path.write_bytes(upload_bytes)

    record_id = _create_task_record(
        task_id=record_id,
        pdf_path=pdf_path,
        original_name=filename,
        config=config,
    )
    overrides = _normalize_overrides(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        topk=topk,
    )
    _update_task(record_id, config_overrides=overrides)
    if dry_run:
        _complete_dry_run_task(record_id)
    else:
        _submit_verification_task(record_id)

    return TaskCreateResponse(
        task_id=record_id,
        status="completed" if dry_run else "pending",
        filename=filename,
        status_url=f"/api/v1/tasks/{record_id}",
        report_url=f"/api/v1/tasks/{record_id}/report",
        dry_run=dry_run,
    )


@APP.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    return _serialize_task(_get_task(task_id))


@APP.post("/api/v1/tasks/{task_id}/cancel", response_model=CancelResponse)
def cancel_task(task_id: str) -> CancelResponse:
    task = _get_task(task_id)
    if task["status"] in {"completed", "failed", "cancelled"}:
        return CancelResponse(task_id=task_id, status=task["status"])

    task["stop_event"].set()
    _update_task(task_id, status="cancelling", current_step="cancelling")
    return CancelResponse(task_id=task_id, status="cancelling")


@APP.get("/api/v1/tasks/{task_id}/report", response_model=ReportResponse)
def get_task_report(task_id: str) -> ReportResponse:
    task = _get_task(task_id)
    if task["status"] not in {"completed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is not finished yet. Current status: {task['status']}.",
        )
    if not task.get("report"):
        raise HTTPException(status_code=404, detail=f"Report not found for task: {task_id}")

    return ReportResponse(
        task_id=task_id,
        status=task["status"],
        report=task["report"],
        report_path=task.get("report_path"),
    )


app = APP
