"""Owner-scoped Supabase persistence using the user's JWT, never a service-role key."""

import json
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from typing import Any

import httpx

from app.config import Settings

ARCHIVE_MAX_BYTES = 110 * 1024 * 1024
# Leave room for the protocol, event data and standalone report.
CLOUD_SOURCE_MAX_BYTES = 90 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024


def source_bytes(folder: Path, replacing: Path) -> int:
    return sum(
        path.stat().st_size
        for name in ("original.mp4", "heldout.mp4")
        if (path := folder / name) != replacing and path.is_file()
    )


FILES = {
    "resume.json",
    "selection.json",
    "tracking_stats.json",
    "calls.jsonl",
    "validation-calls.jsonl",
    "tracking.npz",
    "teaching-tracking.npz",
    "second-tracking.npz",
    "original.mp4",
    "heldout.mp4",
    "protocol.json",
    "status.json",
    "run.json",
    "chain.json",
    "root.txt",
    "report.html",
    "self_check.json",
    "narration.json",
    "boundary_suggestions.json",
    "boundary_confirmation.json",
}


class CloudJobs:
    def __init__(self, settings: Settings, token: str, owner: str):
        self.settings, self.owner = settings, owner
        self.http = httpx.Client(
            base_url=settings.supabase_url.rstrip("/") + "/",
            timeout=120,
            headers={
                "apikey": settings.supabase_publishable_key,
                "Authorization": "Bearer " + token,
            },
        )

    def close(self) -> None:
        self.http.close()

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.http.request(method, path, **kwargs)
        if not response.is_success:
            # Never echo provider bodies, headers, signed links, or tokens.
            if response.status_code == 409:
                raise RuntimeError(
                    "Another analysis is active. Wait for it before starting another."
                )
            raise RuntimeError(
                "Private workspace persistence failed. Retry without starting duplicate work."
            )
        return response

    def get(self, job: str) -> dict[str, Any] | None:
        rows = self.request(
            "GET", "rest/v1/analysis_jobs", params={"id": "eq." + job, "select": "*"}
        ).json()
        return dict(rows[0]) if rows else None

    def begin(self, job: str, kind: str, existing: bool = False) -> None:
        payload = {"status": "processing", "result": {"id": job, "status": "processing"}}
        if existing:
            row = self.get(job)
            if not row or row["status"] == "processing":
                raise RuntimeError("Job is unavailable or already processing.")
            self.request("PATCH", "rest/v1/analysis_jobs", params={"id": "eq." + job}, json=payload)
        else:
            self.request(
                "POST",
                "rest/v1/analysis_jobs",
                json={**payload, "id": job, "kind": kind, "owner_id": self.owner},
            )

    def archive(self, job: str, folder: Path, kind: str) -> None:
        target = "status.json" if kind == "learn" else "run.json"
        result = json.loads((folder / target).read_text())
        if (folder / "resume.json").exists():
            result["resumable"] = True
        files = [folder / name for name in sorted(FILES) if (folder / name).is_file()]
        if sum(path.stat().st_size for path in files) > ARCHIVE_MAX_BYTES:
            raise RuntimeError("Analysis archive exceeds private storage limit")
        path = self.owner + "/" + job + ".zip"
        with TemporaryFile() as output:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                for file_path in files:
                    archive.write(file_path, file_path.name)
            size = output.tell()
            if size > ARCHIVE_MAX_BYTES:
                raise RuntimeError("Analysis archive exceeds private storage limit")
            output.seek(0)
            self.request(
                "POST",
                "storage/v1/object/analysis-artifacts/" + path,
                content=iter(lambda: output.read(STREAM_CHUNK_BYTES), b""),
                headers={
                    "Content-Type": "application/zip",
                    "Content-Length": str(size),
                    "x-upsert": "true",
                },
            )
        self.request(
            "PATCH",
            "rest/v1/analysis_jobs",
            params={"id": "eq." + job},
            json={"status": result["status"], "result": result, "artifact_path": path},
        )

    def fail(self, job: str, message: str, *, resumable: bool = False) -> None:
        self.request(
            "PATCH",
            "rest/v1/analysis_jobs",
            params={"id": "eq." + job},
            json={
                "status": "error",
                "result": {"id": job, "status": "error", "error": message, "resumable": resumable},
            },
        )

    def restore(self, job: str, folder: Path) -> bool:
        row = self.get(job)
        if not row or not row.get("artifact_path"):
            return False
        expected = self.owner + "/" + job + ".zip"
        if row["artifact_path"] != expected:
            raise ValueError("Invalid private artifact path")
        response = self.request(
            "GET", "storage/v1/object/authenticated/analysis-artifacts/" + expected
        )
        if len(response.content) > ARCHIVE_MAX_BYTES:
            raise ValueError("Private archive too large")
        folder.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryFile() as saved:
            saved.write(response.content)
            del response
            saved.seek(0)
            with zipfile.ZipFile(saved) as archive:
                members = archive.infolist()
                if sum(info.file_size for info in members) > ARCHIVE_MAX_BYTES:
                    raise ValueError("Expanded archive too large")
                names = [info.filename for info in members]
                if any(name not in FILES for name in names) or len(names) != len(set(names)):
                    raise ValueError("Unexpected private artifact")
                with TemporaryDirectory(prefix=".restore-", dir=folder.parent) as staging:
                    for info in members:
                        with (
                            archive.open(info) as src,
                            (Path(staging) / info.filename).open("wb") as dst,
                        ):
                            shutil.copyfileobj(src, dst, STREAM_CHUNK_BYTES)
                    # Do not overwrite an existing input until every member decoded successfully.
                    folder.mkdir(parents=True, exist_ok=True)
                    for name in names:
                        (Path(staging) / name).replace(folder / name)
        (folder / "owner.txt").write_text(self.owner)
        return True
