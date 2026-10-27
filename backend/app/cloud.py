"""Owner-scoped Supabase persistence using the user's JWT, never a service-role key."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

FILES = {
    "original.mp4",
    "heldout.mp4",
    "protocol.json",
    "status.json",
    "run.json",
    "chain.json",
    "root.txt",
    "report.html",
    "self_check.json",
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
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in sorted(FILES):
                file_path = folder / name
                if file_path.exists():
                    archive.write(file_path, name)
        data = output.getvalue()
        if len(data) > 110 * 1024 * 1024:
            raise RuntimeError("Analysis archive exceeds private storage limit")
        path = self.owner + "/" + job + ".zip"
        self.request(
            "POST",
            "storage/v1/object/analysis-artifacts/" + path,
            content=data,
            headers={"Content-Type": "application/zip", "x-upsert": "true"},
        )
        self.request(
            "PATCH",
            "rest/v1/analysis_jobs",
            params={"id": "eq." + job},
            json={"status": result["status"], "result": result, "artifact_path": path},
        )

    def fail(self, job: str, message: str) -> None:
        self.request(
            "PATCH",
            "rest/v1/analysis_jobs",
            params={"id": "eq." + job},
            json={"status": "error", "result": {"id": job, "status": "error", "error": message}},
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
        if len(response.content) > 110 * 1024 * 1024:
            raise ValueError("Private archive too large")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            total = sum(info.file_size for info in archive.infolist())
            if total > 110 * 1024 * 1024:
                raise ValueError("Expanded archive too large")
            folder.mkdir(parents=True, exist_ok=True)
            for info in archive.infolist():
                if info.filename not in FILES:
                    raise ValueError("Unexpected private artifact")
                (folder / info.filename).write_bytes(archive.read(info))
        (folder / "owner.txt").write_text(self.owner)
        return True
