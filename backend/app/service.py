import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import httpx

from app.audit.chain import build_chain
from app.audit.report import render_report
from app.config import Settings
from app.glimmer_client import GlimmerClient
from app.learn.compile import compile_protocol, repair_step
from app.learn.frames import extract_audio, file_hash, keyframes, sample
from app.learn.transcribe import transcribe
from app.learn.validate import StepRange, replay, validate_protocol
from app.meta_client import MetaClient
from app.replay_cache import atomic_json
from app.samples import wire_frame
from app.schemas import Opinion, Protocol, TranscriptTurn
from app.supervise.verifier import Verifier
from app.track.geometry import FrameState
from app.track.sam import track


def error_name(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return (
            f"Model provider returned HTTP {exc.response.status_code}. Check local account access."
        )
    if isinstance(exc, httpx.HTTPError):
        return "Model endpoint could not be reached."
    if isinstance(exc, (ValueError, RuntimeError)):
        return str(exc)[:500]
    return "Processing failed; inspect local server diagnostics."


def process_learn(settings: Settings, job: str, turns: list[TranscriptTurn]) -> None:
    folder = settings.data_dir / "jobs" / job
    client = MetaClient(settings, job)
    try:
        video = folder / "original.mp4"
        frames = sample(video, folder / "frames")
        if not turns:
            audio = folder / "audio.wav"
            extract_audio(video, audio)
            turns = transcribe(client, audio)
        protocol = compile_protocol(client, keyframes(frames), turns)
        atomic_json(folder / "protocol.json", protocol.model_dump(by_alias=True))
        atomic_json(
            folder / "status.json",
            {
                "id": job,
                "status": "ready",
                "protocol": protocol.model_dump(by_alias=True),
                "validation": None,
                "provenance": "live-meta-compiled-unverified",
            },
        )
    except Exception as exc:
        atomic_json(
            folder / "status.json", {"id": job, "status": "error", "error": error_name(exc)}
        )
    finally:
        client.close()


def evidence_overlays(
    frames: list[FrameState], paths: list[tuple[float, Path]], folder: Path
) -> dict[str, bytes]:
    evidence: dict[str, bytes] = {}
    for frame, (_, path) in zip(frames, paths, strict=True):
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("Cannot read evidence frame")
        for name, detection in frame.objects.items():
            if detection is None or detection.mask is None:
                continue
            contours, _ = cv2.findContours(
                detection.mask.astype("uint8"), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            cv2.drawContours(image, contours, -1, (90, 250, 210), 2)
            if contours:
                x, y, _, _ = cv2.boundingRect(contours[0])
                cv2.putText(
                    image,
                    name,
                    (x, max(15, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (90, 250, 210),
                    1,
                )
        output = folder / ("evidence_" + path.name)
        cv2.imwrite(str(output), image)
        evidence[str(path)] = output.read_bytes()
    return evidence


def finalize_run(folder: Path, run: dict[str, Any], evidence: dict[str, bytes]) -> None:
    chain, root = build_chain(run["events"], evidence)
    run["chain_root"] = root
    run["chain"] = chain
    atomic_json(folder / "chain.json", chain)
    (folder / "root.txt").write_text(root + "\n")
    (folder / "report.html").write_text(render_report(run, root, evidence))
    atomic_json(folder / "run.json", run)


def call_metrics(settings: Settings, job: str, shadow: list[dict[str, object]]) -> dict[str, Any]:
    path = settings.data_dir / "runs" / job / "calls.jsonl"
    calls = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    cloud = sum(c.get("cloud_frames", 0) for c in calls)
    local = sum(c.get("local_frames", 0) for c in calls)
    available = [s for s in shadow if s.get("available")]
    return {
        "model_calls": len(calls),
        "tier_distribution": dict(Counter(c["tier"] for c in calls)),
        "calls": calls,
        "cloud_frames": cloud,
        "local_frames": local,
        "egress_percent": 100 * cloud / (cloud + local) if cloud + local else None,
        "shadow_agreement": sum(bool(s.get("agree")) for s in available) / len(available)
        if available
        else None,
        "shadow_available": len(available),
        "shadow_requested": len(shadow),
        "note": "Egress counts frame transmissions including retries, not distinct frames. Modal is cloud.",
    }


def process_run(settings: Settings, job: str, protocol: Protocol, color_fallback: bool) -> None:
    folder = settings.data_dir / "jobs" / job
    client = MetaClient(settings, job)
    try:
        video = folder / "original.mp4"
        paths = sample(video, folder / "frames")
        frames = track(client, protocol, paths, file_hash(video), color_fallback)
        supervisor = replay(protocol, frames)
        glimmer = GlimmerClient(settings, job)
        evidence = evidence_overlays(frames, paths, folder)
        review_full: list[Path] = []
        verifier = Verifier(
            glimmer.opinion,
            lambda prompt, images: client.structured(prompt, Opinion, review_full),
            api_only=not bool(settings.glimmer_base_url),
        )
        events = []
        for event in supervisor.events:
            events.append(event)
            if event.kind not in ("step_completed", "uncertain"):
                continue
            nearby = [p for t, p in paths if event.t - 1 <= t <= event.t][-3:]
            review_full = [folder / ("evidence_" + p.name) for p in nearby]
            review_crops: list[Path] = []
            step = next((s for s in protocol.steps if s.id == event.step_id), None)
            names = {
                str(getattr(p, key))
                for p in (step.action + step.post if step else [])
                for key in ("a", "b", "obj")
                if hasattr(p, key)
            } - {"hand"}
            for raw_path, outlined in zip(nearby, review_full, strict=True):
                state = next(f for f in frames if f.evidence_frame == str(raw_path))
                boxes = [
                    cv2.boundingRect(d.mask.astype("uint8"))
                    for name, d in state.objects.items()
                    if name in names and d is not None and d.mask is not None and d.mask.any()
                ]
                image = cv2.imread(str(outlined))
                if image is None:
                    raise ValueError("Cannot read verifier evidence")
                if boxes:
                    x0, y0 = (
                        max(0, min(x for x, _, _, _ in boxes) - 64),
                        max(0, min(y for _, y, _, _ in boxes) - 64),
                    )
                    x1 = min(state.width, max(x + w for x, _, w, _ in boxes) + 64)
                    y1 = min(state.height, max(y + h for _, y, _, h in boxes) + 64)
                    image = image[y0:y1, x0:x1]
                crop = folder / ("review_" + str(event.step_id) + "_" + raw_path.name)
                cv2.imwrite(str(crop), image)
                review_crops.append(crop)
            prompt = (
                "Review only observable completion. "
                + protocol.model_dump_json()
                + "\n"
                + event.model_dump_json()
            )
            events.extend(
                verifier.review(event, prompt, review_crops, shadow=event.kind == "step_completed")
            )
        run: dict[str, Any] = {
            "id": job,
            "name": "Uploaded recording",
            "status": "ready",
            "provenance": "live-recording",
            "video_sha256": file_hash(video),
            "protocol": protocol.model_dump(by_alias=True),
            "frames": [wire_frame(f) for f in frames],
            "duration": frames[-1].t,
            "events": [e.model_dump() for e in events],
            "states": {k: s.status for k, s in supervisor.states.items()},
            "metrics": call_metrics(settings, job, verifier.shadow),
            "shadow": verifier.shadow,
        }
        run["events"].sort(key=lambda e: e["t"])
        finalize_run(folder, run, evidence)
    except Exception as exc:
        atomic_json(folder / "run.json", {"id": job, "status": "error", "error": error_name(exc)})
    finally:
        client.close()


def process_validation(
    settings: Settings, job: str, ranges: dict[str, StepRange], repair: bool
) -> None:
    folder = settings.data_dir / "jobs" / job
    client = MetaClient(settings, job + "-validation")
    try:
        protocol = Protocol.model_validate_json((folder / "protocol.json").read_text())
        a_hash, b_hash = file_hash(folder / "original.mp4"), file_hash(folder / "heldout.mp4")
        if a_hash == b_hash:
            raise ValueError("Held-out recording must differ from the compile recording")
        a_paths = sample(folder / "original.mp4", folder / "frames")
        b_paths = sample(folder / "heldout.mp4", folder / "heldout-frames")
        a = track(client, protocol, a_paths, file_hash(folder / "original.mp4"))
        b = track(client, protocol, b_paths, file_hash(folder / "heldout.mp4"))
        result = validate_protocol(protocol, a, b, ranges)
        history = [{"round": 0, "checks": result["checks"], "verified": result["verified"]}]
        for round_idx in range(1, 4):
            if result["verified"] or not repair:
                break
            for i, step in enumerate(protocol.steps):
                fixed = repair_step(client, step, json.dumps(result), keyframes(a_paths, limit=3))
                if fixed.id != step.id:
                    raise ValueError("Repair changed a step ID")
                protocol.steps[i] = fixed
            protocol = Protocol.model_validate(protocol.model_dump(by_alias=True))
            result = validate_protocol(protocol, a, b, ranges)
            result["repair_rounds"] = round_idx
            history.append(
                {"round": round_idx, "checks": result["checks"], "verified": result["verified"]}
            )
        result["repair_history"] = history
        result["compile_video_sha256"] = a_hash
        result["held_out_video_sha256"] = b_hash
        atomic_json(folder / "self_check.json", result)
        atomic_json(folder / "protocol.json", protocol.model_dump(by_alias=True))
        atomic_json(
            folder / "status.json",
            {
                "id": job,
                "status": "ready",
                "protocol": protocol.model_dump(by_alias=True),
                "validation": result,
                "provenance": "live-meta-compiled",
            },
        )
    except Exception as exc:
        atomic_json(
            folder / "status.json", {"id": job, "status": "error", "error": error_name(exc)}
        )
    finally:
        client.close()
