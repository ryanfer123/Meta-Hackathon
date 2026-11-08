import json
import re
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal

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
from app.cloud import CLOUD_SOURCE_MAX_BYTES, CloudJobs, source_bytes
from app.config import Settings
from app.learn.boundaries import validate_step_ranges
from app.learn.frames import file_hash
from app.learn.validate import StepRange
from app.object_preview import descriptions, process_preview
from app.progress import with_progress
from app.replay_cache import atomic_json
from app.sample_access import SampleRateLimiter, is_public_sample
from app.samples import SAMPLES, sample_run
from app.schemas import Protocol, TranscriptTurn
from app.selection import selection
from app.service import finalize_run, process_learn, process_run, process_validation
from app.track.codec_status import codec_compiled
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
        request: Request,
        job: str,
        kind: str,
        operation: Callable[..., None],
        *args: Any,
        tracking_mode: Literal["image", "video"] | None = None,
    ) -> None:
        settings = job_settings(request)
        if tracking_mode is not None:
            settings = settings.model_copy(update={"sam_mode": tracking_mode})
        folder = config.data_dir / "jobs" / job

        def checkpoint() -> None:
            for run_id, filename in (
                (job, "calls.jsonl"),
                (job + "-validation", "validation-calls.jsonl"),
            ):
                source = config.data_dir / "runs" / run_id / "calls.jsonl"
                if source.exists():
                    shutil.copyfile(source, folder / filename)
            target = folder / ("run.json" if kind == "run" else "status.json")
            value = read(target)
            value["resumable"] = True
            atomic_json(target, value)
            if config.cloud_jobs:
                db = cloud(request)
                try:
                    db.archive(job, folder, kind)
                finally:
                    db.close()

        settings._checkpoint_callback = checkpoint
        try:
            if (folder / "resume.json").exists():
                checkpoint()
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
        with active_lock:
            if len(active_jobs) >= config.max_active_jobs:
                if not existing:
                    shutil.rmtree(config.data_dir / "jobs" / job, ignore_errors=True)
                raise HTTPException(
                    503,
                    "The server is checking another recording. Try again shortly; no analysis was started.",
                    headers={"Retry-After": "30"},
                )
            active_jobs.add(job)
        try:
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
        except Exception:
            with active_lock:
                active_jobs.discard(job)
            raise

    async def save_job_upload(
        request: Request,
        job: str,
        kind: str,
        file: UploadFile,
        target: Path,
        existing: bool = False,
        section: tuple[float | None, float | None] = (None, None),
        maximum_s: float = 300,
    ) -> None:
        staging = target.with_name(target.name + "." + uuid.uuid4().hex + ".upload")
        begun = False
        try:
            maximum = config.max_upload_mb * 1024 * 1024
            message = "Recording exceeds configured upload limit"
            if config.cloud_jobs:
                remaining = CLOUD_SOURCE_MAX_BYTES - source_bytes(target.parent, target)
                if remaining < maximum:
                    maximum = remaining
                    message = "Recordings for this job must total at most 90 MiB. Compress the videos or choose smaller files. No analysis was started."
            if maximum <= 0 or (file.size is not None and file.size > maximum):
                raise HTTPException(413, message)
            await save(file, staging, maximum, message)
            try:
                chosen = selection(staging, *section, maximum_s)
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(422, str(exc)) from exc
            begin_job(request, job, kind, existing)
            begun = True
            staging.replace(target)
            selections_path = target.parent / "selection.json"
            selections = read(selections_path) if selections_path.exists() else {}
            if chosen:
                selections[target.name] = chosen
            else:
                selections.pop(target.name, None)
            atomic_json(selections_path, selections)
        except Exception:
            if begun and config.cloud_jobs:
                db = cloud(request)
                try:
                    db.fail(job, "Upload failed. Choose a valid recording and retry.")
                finally:
                    db.close()
            if begun:
                with active_lock:
                    active_jobs.discard(job)
            if not existing:
                shutil.rmtree(target.parent, ignore_errors=True)
            raise
        finally:
            staging.unlink(missing_ok=True)

    def cloud_status(request: Request, job: str) -> Any:
        if not re.fullmatch(r"[a-f0-9]{32}", job):
            raise HTTPException(404, "Unknown job")
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
                    "The worker stopped before completion. Open My runs to resume saved stages; unfinished work may need to run again.",
                    resumable=bool(row.get("artifact_path")),
                )
                return {
                    "id": job,
                    "status": "error",
                    "resumable": bool(row.get("artifact_path")),
                    "error": "The worker stopped before completion. Open My runs to resume saved stages; unfinished work may need to run again.",
                }
            result = row["result"]
            if row.get("artifact_path"):
                result = {**result, "resumable": True}
            if active and re.fullmatch(r"[a-f0-9]{32}", job):
                return with_progress(result, config.data_dir / "jobs" / job)
            return result
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

    async def save(file: UploadFile, target: Path, maximum: int, message: str) -> None:
        if file.content_type not in {"video/mp4", "video/quicktime", "application/octet-stream"}:
            raise HTTPException(415, "Choose an MP4 or MOV recording")
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with target.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > maximum:
                        raise HTTPException(413, message)
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
            "max_run_duration_s": config.max_run_duration_s,
            "max_teaching_duration_s": config.max_teaching_duration_s,
            "max_upload_bytes": config.max_upload_mb * 1024 * 1024,
            "max_cloud_source_bytes": CLOUD_SOURCE_MAX_BYTES if config.cloud_jobs else None,
            "sam_codec_compiled": codec_compiled(),
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
        trim_start_s: Annotated[float | None, Form()] = None,
        trim_end_s: Annotated[float | None, Form()] = None,
    ) -> dict[str, str]:
        live()
        try:
            turns = TypeAdapter(list[TranscriptTurn]).validate_json(narration)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid timestamped narration JSON") from exc
        job = uuid.uuid4().hex
        folder = job_folder(job, request, create=True)
        await save_job_upload(
            request,
            job,
            "learn",
            video,
            folder / "original.mp4",
            section=(trim_start_s, trim_end_s),
            maximum_s=config.max_teaching_duration_s,
        )
        atomic_json(folder / "status.json", {"id": job, "status": "processing"})
        atomic_json(
            folder / "resume.json",
            {
                "operation": "learn",
                "turns": [t.model_dump() for t in turns],
                "narration_text": narration_text,
                "video_sha256": file_hash(folder / "original.mp4"),
            },
        )
        tasks.add_task(execute_job, request, job, "learn", process_learn, turns, narration_text)
        return {"protocol_id": job, "status": "processing"}

    @app.get("/api/protocols/{job}")
    def get_protocol(job: str, request: Request) -> Any:
        if config.cloud_jobs:
            return cloud_status(request, job)
        folder = job_folder(job, request)
        return with_progress(read(folder / "status.json"), folder)

    @app.post("/api/protocols/{job}/validate", status_code=202)
    async def validate(
        job: str,
        request: Request,
        tasks: BackgroundTasks,
        heldout: Annotated[UploadFile, File()],
        ranges: Annotated[str, Form()],
        repair: Annotated[bool, Form()] = False,
        trim_start_s: Annotated[float | None, Form()] = None,
        trim_end_s: Annotated[float | None, Form()] = None,
        ranges_confirmed: Annotated[bool, Form()] = False,
        tracking_mode: Annotated[Literal["image", "video"] | None, Form()] = None,
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
        await save_job_upload(
            request,
            job,
            "learn",
            heldout,
            folder / "heldout.mp4",
            existing=True,
            section=(trim_start_s, trim_end_s),
            maximum_s=config.max_teaching_duration_s,
        )
        atomic_json(
            folder / "boundary_confirmation.json",
            {
                "confirmed": True,
                "ranges": {key: value.model_dump() for key, value in parsed.items()},
            },
        )
        atomic_json(folder / "status.json", {"id": job, "status": "validating"})
        atomic_json(
            folder / "resume.json",
            {
                "operation": "validate",
                "ranges": {k: v.model_dump() for k, v in parsed.items()},
                "repair": repair,
                "tracking_mode": tracking_mode,
                "video_sha256": file_hash(folder / "original.mp4"),
                "heldout_sha256": file_hash(folder / "heldout.mp4"),
            },
        )
        tasks.add_task(
            execute_job,
            request,
            job,
            "learn",
            process_validation,
            parsed,
            repair,
            tracking_mode=tracking_mode,
        )
        return {"protocol_id": job, "status": "validating"}

    @app.post("/api/runs", status_code=202)
    async def start_run(
        tasks: BackgroundTasks,
        request: Request,
        video: Annotated[UploadFile, File()],
        protocol_id: Annotated[str, Form()],
        color_fallback: Annotated[bool, Form()] = False,
        trim_start_s: Annotated[float | None, Form()] = None,
        trim_end_s: Annotated[float | None, Form()] = None,
        preview_only: Annotated[bool, Form()] = False,
        tracking_mode: Annotated[Literal["image", "video"] | None, Form()] = None,
    ) -> dict[str, str]:
        live()
        protocol = Protocol.model_validate(read(job_folder(protocol_id, request) / "protocol.json"))
        job = uuid.uuid4().hex
        folder = job_folder(job, request, create=True)
        await save_job_upload(
            request,
            job,
            "run",
            video,
            folder / "original.mp4",
            section=(trim_start_s, trim_end_s),
            maximum_s=config.max_run_duration_s if tracking_mode == "video" else 90,
        )
        atomic_json(folder / "run.json", {"id": job, "status": "processing"})
        atomic_json(folder / "protocol.json", protocol.model_dump(by_alias=True))
        atomic_json(
            folder / "resume.json",
            {
                "operation": "preview" if preview_only else "run",
                "protocol": protocol.model_dump(by_alias=True),
                "color_fallback": color_fallback,
                "tracking_mode": tracking_mode,
                "video_sha256": file_hash(folder / "original.mp4"),
            },
        )
        tasks.add_task(
            execute_job,
            request,
            job,
            "run",
            process_preview if preview_only else process_run,
            protocol,
            *([] if preview_only else [color_fallback]),
            tracking_mode=tracking_mode,
        )
        return {"run_id": job, "status": "processing"}

    @app.post("/api/runs/{job}/analyse", status_code=202)
    def analyse_preview(
        job: str,
        request: Request,
        tasks: BackgroundTasks,
        prompts: Annotated[str, Form()] = "",
        preview_only: Annotated[bool, Form()] = False,
        tracking_mode: Annotated[Literal["image", "video"] | None, Form()] = None,
    ) -> dict[str, str]:
        live()
        if job.startswith("sample-"):
            raise HTTPException(404, "Unknown job")
        folder = job_folder(job, request)
        value = read(folder / "run.json")
        if value.get("phase") != "object-preview" or value.get("status") != "ready":
            raise HTTPException(409, "Finish an object preview before continuing")
        data = read(folder / "resume.json")
        if file_hash(folder / "original.mp4") != data.get("video_sha256"):
            raise HTTPException(409, "The saved recording changed")
        protocol = Protocol.model_validate(data["protocol"])
        if prompts:
            try:
                protocol = descriptions(
                    protocol, TypeAdapter(dict[str, str]).validate_json(prompts)
                )
            except (ValueError, ValidationError) as exc:
                raise HTTPException(
                    422, "Provide a short visual description for every existing object"
                ) from exc
        begin_job(request, job, "run", existing=True)
        data.update(
            operation="preview" if preview_only else "run",
            protocol=protocol.model_dump(by_alias=True),
            tracking_mode=tracking_mode or data.get("tracking_mode"),
        )
        atomic_json(folder / "resume.json", data)
        atomic_json(folder / "protocol.json", protocol.model_dump(by_alias=True))
        atomic_json(folder / "run.json", {"id": job, "status": "processing"})
        tasks.add_task(
            execute_job,
            request,
            job,
            "run",
            process_preview if preview_only else process_run,
            protocol,
            *([] if preview_only else [bool(data.get("color_fallback"))]),
            tracking_mode=data.get("tracking_mode"),
        )
        return {"run_id": job, "status": "processing"}

    @app.post("/api/jobs/{job}/resume", status_code=202)
    def resume_job(job: str, request: Request, tasks: BackgroundTasks) -> dict[str, str]:
        live()
        if job.startswith("sample-"):
            raise HTTPException(404, "Unknown job")
        with active_lock:
            if job in active_jobs:
                raise HTTPException(409, "This analysis is already running")
        state = cloud_status(request, job) if config.cloud_jobs else None
        if state and state.get("status") in {"processing", "validating", "ready"}:
            raise HTTPException(409, "This analysis is running or already completed")
        folder = job_folder(job, request)
        data = read(folder / "resume.json")
        if file_hash(folder / "original.mp4") != data.get("video_sha256") or (
            data.get("heldout_sha256")
            and file_hash(folder / "heldout.mp4") != data["heldout_sha256"]
        ):
            raise HTTPException(409, "Saved recordings changed; start a new analysis")
        fn: Callable[..., None]
        args: tuple[Any, ...]
        operation = data.get("operation")
        if operation == "preview":
            kind, fn, args = "run", process_preview, (Protocol.model_validate(data["protocol"]),)
        elif operation == "run":
            kind, fn, args = (
                "run",
                process_run,
                (Protocol.model_validate(data["protocol"]), bool(data.get("color_fallback"))),
            )
        elif operation == "learn":
            kind, fn, args = (
                "learn",
                process_learn,
                ([TranscriptTurn.model_validate(t) for t in data["turns"]], data["narration_text"]),
            )
        elif operation == "validate":
            kind, fn, args = (
                "learn",
                process_validation,
                (
                    TypeAdapter(dict[str, StepRange]).validate_python(data["ranges"]),
                    bool(data["repair"]),
                ),
            )
        else:
            raise HTTPException(409, "No supported checkpoint is available")
        target = folder / ("run.json" if kind == "run" else "status.json")
        if not config.cloud_jobs and read(target).get("status") == "ready":
            raise HTTPException(409, "This analysis already completed")
        begin_job(request, job, kind, existing=True)
        for run_id, filename in (
            (job, "calls.jsonl"),
            (job + "-validation", "validation-calls.jsonl"),
        ):
            saved = folder / filename
            if saved.exists():
                dest = config.data_dir / "runs" / run_id / "calls.jsonl"
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Restore only after a worker lost its local logs. Never overwrite newer usage.
                if not dest.exists():
                    shutil.copyfile(saved, dest)
        atomic_json(target, {"id": job, "status": "processing", "resumable": True})
        tasks.add_task(
            execute_job, request, job, kind, fn, *args, tracking_mode=data.get("tracking_mode")
        )
        return {"id": job, "status": "processing", "kind": kind}

    @app.get("/api/runs/{job}")
    def get_run(job: str, request: Request) -> Any:
        ensure_sample(job)
        if config.cloud_jobs and not job.startswith("sample-"):
            return cloud_status(request, job)
        folder = job_folder(job, request)
        return with_progress(read(folder / "run.json"), folder)

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
