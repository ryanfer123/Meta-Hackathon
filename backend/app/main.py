import json
import re
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError

from app.audit.chain import verify_entries
from app.config import Settings
from app.learn.validate import StepRange
from app.replay_cache import atomic_json
from app.samples import SAMPLES, sample_run
from app.schemas import Protocol, TranscriptTurn
from app.service import finalize_run, process_learn, process_run, process_validation


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    app = FastAPI(title="Apprentice", version="0.1.0")

    def job_folder(job: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}|sample-[a-z-]+", job):
            raise HTTPException(404, "Unknown job")
        return config.data_dir / "jobs" / job

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
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with target.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > config.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, "Recording exceeds configured upload limit")
                    out.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
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
        run = sample_run(name)
        finalize_run(job_folder(run["id"]), run, {})
        return run

    @app.post("/api/protocols", status_code=202)
    async def learn(
        tasks: BackgroundTasks,
        video: Annotated[UploadFile, File()],
        narration: Annotated[str, Form()] = "[]",
    ) -> dict[str, str]:
        live()
        try:
            turns = TypeAdapter(list[TranscriptTurn]).validate_json(narration)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid timestamped narration JSON") from exc
        job = uuid.uuid4().hex
        folder = job_folder(job)
        await save(video, folder / "original.mp4")
        atomic_json(folder / "status.json", {"id": job, "status": "processing"})
        tasks.add_task(process_learn, config, job, turns)
        return {"protocol_id": job, "status": "processing"}

    @app.get("/api/protocols/{job}")
    def get_protocol(job: str) -> Any:
        return read(job_folder(job) / "status.json")

    @app.post("/api/protocols/{job}/validate", status_code=202)
    async def validate(
        job: str,
        tasks: BackgroundTasks,
        heldout: Annotated[UploadFile, File()],
        ranges: Annotated[str, Form()],
        repair: Annotated[bool, Form()] = False,
    ) -> dict[str, str]:
        live()
        folder = job_folder(job)
        read(folder / "protocol.json")
        try:
            parsed = TypeAdapter(dict[str, StepRange]).validate_json(ranges)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid step ranges") from exc
        await save(heldout, folder / "heldout.mp4")
        atomic_json(folder / "status.json", {"id": job, "status": "validating"})
        tasks.add_task(process_validation, config, job, parsed, repair)
        return {"protocol_id": job, "status": "validating"}

    @app.post("/api/runs", status_code=202)
    async def start_run(
        tasks: BackgroundTasks,
        video: Annotated[UploadFile, File()],
        protocol_id: Annotated[str, Form()],
        color_fallback: Annotated[bool, Form()] = False,
    ) -> dict[str, str]:
        live()
        protocol = Protocol.model_validate(read(job_folder(protocol_id) / "protocol.json"))
        job = uuid.uuid4().hex
        folder = job_folder(job)
        await save(video, folder / "original.mp4")
        atomic_json(folder / "run.json", {"id": job, "status": "processing"})
        tasks.add_task(process_run, config, job, protocol, color_fallback)
        return {"run_id": job, "status": "processing"}

    @app.get("/api/runs/{job}")
    def get_run(job: str) -> Any:
        return read(job_folder(job) / "run.json")

    @app.get("/api/runs/{job}/report", response_class=HTMLResponse)
    def report(job: str) -> str:
        path = job_folder(job) / "report.html"
        if not path.exists():
            raise HTTPException(404, "Report not ready")
        return path.read_text()

    @app.post("/api/runs/{job}/verify")
    def verify(job: str, trusted_root: Annotated[str | None, Form()] = None) -> dict[str, object]:
        chain = read(job_folder(job) / "chain.json")
        return {
            "valid": verify_entries(chain, trusted_root),
            "trusted_root_supplied": trusted_root is not None,
            "scope": "chain and optional external root; evidence files not verified by this endpoint",
        }

    @app.get("/api/media/{job}/{name}")
    def media(job: str, name: str) -> FileResponse:
        if not re.fullmatch(r"original\.mp4|evidence_frame_[0-9_.]+\.jpg", name):
            raise HTTPException(404, "Unknown media")
        path = job_folder(job) / name
        if not path.exists():
            raise HTTPException(404, "Media not found")
        return FileResponse(path)

    @app.websocket("/ws/runs/{job}")
    async def stream(ws: WebSocket, job: str) -> None:
        import asyncio

        await ws.accept()
        try:
            path = job_folder(job) / "run.json"
            for _ in range(180):
                payload = (
                    json.loads(path.read_text()) if path.exists() else {"status": "processing"}
                )
                await ws.send_json(payload)
                if payload.get("status") in ("ready", "error") or "events" in payload:
                    break
                await asyncio.sleep(1)
        except (WebSocketDisconnect, HTTPException):
            return
        finally:
            try:
                await ws.close()
            except RuntimeError:
                pass

    dist = Path(__file__).resolve().parents[2] / ".." / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
