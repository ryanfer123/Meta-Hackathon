import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(canonical(value))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class ReplayCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get(self, namespace: str, key: str) -> Any:
        path = self.root / namespace / f"{key}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, namespace: str, key: str, payload: Any, provenance: str) -> None:
        atomic_json(
            self.root / namespace / f"{key}.json",
            {"provenance": provenance, "payload": payload, "sha256": digest(payload)},
        )
