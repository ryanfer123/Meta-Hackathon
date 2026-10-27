from pathlib import Path

from app.meta_client import MetaClient
from app.schemas import TranscriptTurn


def transcribe(client: MetaClient, wav: Path) -> list[TranscriptTurn]:
    turns = client.transcribe(wav)
    if not turns:
        raise ValueError("No timestamped speech turns returned. Provide narration JSON.")
    return turns
