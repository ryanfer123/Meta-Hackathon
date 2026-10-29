import json
import re
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr, TypeAdapter, ValidationError

from app.audit.chain import verify_entries
from app.auth import authenticate
from app.cloud import CloudJobs
from app.config import Settings
from app.learn.boundaries import validate_step_ranges
from app.learn.validate import StepRange
from app.replay_cache import atomic_json
from app.sample_access import SampleRateLimiter, is_public_sample
from app.samples import SAMPLES, sample_run
from app.schemas import Protocol, TranscriptTurn
from app.service import finalize_run, process_learn, process_run, process_validation
from app.track.native_video import probe_video


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    app = FastAPI(title="Apprentice", version="0.1.0")

    sample_limiter = SampleRateLimiter()
    sample_lock = Lock()
    sample_ready: set[str] = set()

    @app.middleware("http")
    async def require_account(request: Request, call_next: Any) -> Any:
        public_sample = is_public_sample(request.method, request.url.path)
        if public_sample:
            retry = sample_limiter.retry_after(request.client.host if request.client else "unknown")
            if retry:
                return JSONResponse(
                    {"detail": "Sample request limit reached. Try again shortly."},
                    status_code=429,
                    headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
                )
        if request.method == "POST" and request.headers.get("content-type", "").startswith(
            "multipart/form-data"
        ):
            size = request.headers.get("content-length")
            if size is None:
                return JSONResponse({"detail": "Upload size is required"}, status_code=411)
            if not size.isdigit() or int(size) > config.max_upload_mb * 1024 * 1024 + 1024 * 1024:
                return JSONResponse({"detail": "Upload exceeds configured limit"}, status_code=413)
        if (
            not public_sample
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/health"
            and request.method != "OPTIONS"
        ):
            try:
                request.state.owner = await authenticate(
                    config, request.headers.get("authorization", "")
                )
            except HTTPException as exc:
                return JSONResponse(
                    {"detail": exc.detail},
                    status_code=exc.status_code,
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    active_jobs: set[str] = set()
    active_lock = Lock()

    def cloud(request: Request) -> CloudJobs:
        return CloudJobs(
            config,
            request.headers.get("authorization", "").removeprefix("Bearer "),
            request.state.owner,
        )

    def job_settings(request: Request) -> Settings:
        return config.model_copy(
            update={
                "supabase_access_token": SecretStr(
                    request.headers.get("authorization", "").removeprefix("Bearer ")
                )
            }
        )

    def execute_job(
        request: Request, job: str, kind: str, operation: Callable[..., None], *args: Any
    ) -> None:
        settings = job_settings(request)
        try:
            operation(settings, job, *args)
            if config.cloud_jobs:
                db = cloud(request)
                try:
                    db.archive(job, config.data_dir / "jobs" / job, kind)
                except Exception:
                    db.fail(
                        job,
                        "Processing finished, but private persistence failed. Do not start duplicate work.",
                    )
                finally:
                    db.close()
        finally:
            with active_lock:
                active_jobs.discard(job)

    def begin_job(request: Request, job: str, kind: str, existing: bool = False) -> None:
        if config.cloud_jobs:
            db = cloud(request)
            try:
                db.begin(job, kind, existing)
            except RuntimeError as exc:
                if not existing:
                    shutil.rmtree(config.data_dir / "jobs" / job, ignore_errors=True)
                raise HTTPException(409, str(exc)) from exc
            finally:
                db.close()
        with active_lock:
            active_jobs.add(job)

    async def save_job_upload(
        request: Request,
        job: str,
        kind: str,
        file: UploadFile,
        target: Path,
        existing: bool = False,
    ) -> None:
        begin_job(request, job, kind, existing)
        try:
            await save(file, target)
        except Exception:
            if config.cloud_jobs:
                db = cloud(request)
                try:
                    db.fail(job, "Upload failed. Choose a valid recording and retry.")
                finally:
                    db.close()
            with active_lock:
                active_jobs.discard(job)
            if not existing:
                shutil.rmtree(target.parent, ignore_errors=True)
            raise

    def cloud_status(request: Request, job: str) -> Any:
        db = cloud(request)
        try:
            row = db.get(job)
            if not row:
                raise HTTPException(404, "Unknown job")
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            with active_lock:
                active = job in active_jobs
            if (
                row["status"] == "processing"
                and not active
                and (datetime.now(UTC) - created).total_seconds() > 60
            ):
                db.fail(
                    job,
                    "The worker restarted before this job finished. Re-upload the recording to retry.",
                )
                return {
                    "id": job,
                    "status": "error",
                    "error": "The worker restarted before this job finished. Re-upload the recording to retry.",
                }
            return row["result"]
        finally:
            db.close()

    def job_folder(job: str, request: Request | None = None, create: bool = False) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}|sample-[a-z-]+", job):
            raise HTTPException(404, "Unknown job")
        if job.startswith("sample-") and job.removeprefix("sample-") not in SAMPLES:
            raise HTTPException(404, "Unknown sample")
        folder = config.data_dir / "jobs" / job
        if request is not None and config.auth_required and not job.startswith("sample-"):
            owner_file = folder / "owner.txt"
            if create:
                folder.mkdir(parents=True, exist_ok=False)
                owner_file.write_text(request.state.owner)
            elif not owner_file.exists() and config.cloud_jobs:
                db = cloud(request)
                try:
                    if not db.restore(job, folder):
                        raise HTTPException(404, "Job artifact is not ready")
                finally:
                    db.close()
            elif not owner_file.exists() or owner_file.read_text() != request.state.owner:
                raise HTTPException(404, "Unknown job")
        return folder

    def ensure_sample(job: str) -> None:
        if job.startswith("sample-"):
            folder = job_folder(job)
            with sample_lock:
                if job not in sample_ready:
                    # Local deterministic fixtures only: no clients, cloud writes or budgets.
                    finalize_run(folder, sample_run(job.removeprefix("sample-")), {})
                    sample_ready.add(job)

    def read(path: Path) -> Any:
        if not path.exists():
            raise HTTPException(404, "Not found")
        return json.loads(path.read_text())

    def live() -> None:
        try:
            config.require_live()
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    async def save(file: UploadFile, target: Path) -> None:
        if file.content_type not in {"video/mp4", "video/quicktime", "application/octet-stream"}:
            raise HTTPException(415, "Choose an MP4 or MOV recording")
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with target.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > config.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, "Recording exceeds configured upload limit")
                    out.write(chunk)
            if total == 0:
                raise HTTPException(422, "Recording is empty")
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "auth_required": config.auth_required,
            "cloud_jobs": config.cloud_jobs,
            "replay_mode": config.replay_mode,
            "live_configured": bool(config.model_api_key.get_secret_value())
            and not config.replay_mode,
            "glimmer_configured": bool(config.glimmer_base_url),
            "real_evaluation": "pending",
            "provenance": "synthetic samples",
        }

    @app.get("/api/samples")
    def samples() -> list[dict[str, str]]:
        return [
            {"name": n, "title": title, "provenance": "synthetic"} for n, title in SAMPLES.items()
        ]

    @app.post("/api/runs/sample/{name}")
    def start_sample(name: str) -> dict[str, Any]:
        if name not in SAMPLES:
            raise HTTPException(404, "Unknown sample")
        job = "sample-" + name
        ensure_sample(job)
        return dict(read(job_folder(job) / "run.json"))

    @app.post("/api/protocols", status_code=202)
    async def learn(
        tasks: BackgroundTasks,
        request: Request,
        video: Annotated[UploadFile, File()],
        narration: Annotated[str, Form()] = "[]",
        narration_text: Annotated[str, Form(max_length=4000)] = "",
    ) -> dict[str, str]:
        live()
        try:
            turns = TypeAdapter(list[TranscriptTurn]).validate_json(narration)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid timestamped narration JSON") from exc
        job = uuid.uuid4().hex
        folder = job_folder(job, request, create=True)
        await save_job_upload(request, job, "learn", video, folder / "original.mp4")
        atomic_json(folder / "status.json", {"id": job, "status": "processing"})
        tasks.add_task(execute_job, request, job, "learn", process_learn, turns, narration_text)
        return {"protocol_id": job, "status": "processing"}

    @app.get("/api/protocols/{job}")
    def get_protocol(job: str, request: Request) -> Any:
        if config.cloud_jobs:
            return cloud_status(request, job)
        return read(job_folder(job, request) / "status.json")

    @app.post("/api/protocols/{job}/validate", status_code=202)
    async def validate(
        job: str,
        request: Request,
        tasks: BackgroundTasks,
        heldout: Annotated[UploadFile, File()],
        ranges: Annotated[str, Form()],
        repair: Annotated[bool, Form()] = False,
        ranges_confirmed: Annotated[bool, Form()] = False,
    ) -> dict[str, str]:
        live()
        folder = job_folder(job, request)
        protocol = Protocol.model_validate(read(folder / "protocol.json"))
        if not ranges_confirmed:
            raise HTTPException(422, "Review and confirm every step boundary before validation")
        try:
            parsed = TypeAdapter(dict[str, StepRange]).validate_json(ranges)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid step ranges") from exc
        try:
            validate_step_ranges(protocol, parsed)
            duration = float(probe_video(folder / "original.mp4")["duration_s"])
            validate_step_ranges(protocol, parsed, duration)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        atomic_json(
            folder / "boundary_confirmation.json",
            {
                "confirmed": True,
                "ranges": {key: value.model_dump() for key, value in parsed.items()},
            },
        )
        await save_job_upload(request, job, "learn", heldout, folder / "heldout.mp4", existing=True)
        atomic_json(folder / "status.json", {"id": job, "status": "validating"})
        tasks.add_task(execute_job, request, job, "learn", process_validation, parsed, repair)
        return {"protocol_id": job, "status": "validating"}

    @app.post("/api/runs", status_code=202)
    async def start_run(
        tasks: BackgroundTasks,
        request: Request,
        video: Annotated[UploadFile, File()],
        protocol_id: Annotated[str, Form()],
        color_fallback: Annotated[bool, Form()] = False,
    ) -> dict[str, str]:
        live()
        protocol = Protocol.model_validate(read(job_folder(protocol_id, request) / "protocol.json"))
        job = uuid.uuid4().hex
        folder = job_folder(job, request, create=True)
        await save_job_upload(request, job, "run", video, folder / "original.mp4")
        atomic_json(folder / "run.json", {"id": job, "status": "processing"})
        tasks.add_task(execute_job, request, job, "run", process_run, protocol, color_fallback)
        return {"run_id": job, "status": "processing"}

    @app.get("/api/runs/{job}")
    def get_run(job: str, request: Request) -> Any:
        ensure_sample(job)
        if config.cloud_jobs and not job.startswith("sample-"):
            return cloud_status(request, job)
        return read(job_folder(job, request) / "run.json")

    @app.get("/api/runs/{job}/report", response_class=HTMLResponse)
    def report(job: str, request: Request) -> str:
        ensure_sample(job)
        path = job_folder(job, request) / "report.html"
        if not path.exists():
            raise HTTPException(404, "Report not ready")
        return path.read_text()

    @app.post("/api/runs/{job}/verify")
    def verify(
        job: str, request: Request, trusted_root: Annotated[str | None, Form()] = None
    ) -> dict[str, object]:
        ensure_sample(job)
        chain = read(job_folder(job, request) / "chain.json")
        return {
            "valid": verify_entries(chain, trusted_root),
            "trusted_root_supplied": trusted_root is not None,
            "scope": "chain and optional external root; evidence files not verified by this endpoint",
        }

    @app.get("/api/media/{job}/{name}")
    def media(job: str, name: str, request: Request) -> FileResponse:
        if not re.fullmatch(r"original\.mp4|evidence_frame_[0-9_.]+\.jpg", name):
            raise HTTPException(404, "Unknown media")
        ensure_sample(job)
        path = job_folder(job, request) / name
        if not path.exists():
            raise HTTPException(404, "Media not found")
        return FileResponse(path)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    return app


app = create_app()
