import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import httpx

from app.audit.chain import build_chain
from app.audit.report import render_report
from app.budget import BudgetExceeded
from app.checkpoints import checkpoint_key, load_frames, persist, save_frames
from app.config import Settings
from app.glimmer_client import GlimmerClient
from app.learn.boundaries import suggest_boundaries, validate_step_ranges
from app.learn.compile import compile_protocol, repair_step
from app.learn.frames import extract_audio, file_hash, keyframes, sample, teaching_keyframes
from app.learn.transcribe import transcribe
from app.learn.validate import StepRange, replay, validate_protocol
from app.meta_client import MetaClient
from app.processing_plan import plan_long_recording, plan_validation
from app.progress import JobProgress
from app.providers import OpinionProvider, TrackingProvider
from app.replay_cache import atomic_json
from app.run_summary import summarize
from app.samples import wire_frame
from app.schemas import Opinion, Protocol, TranscriptTurn
from app.selection import selected_video
from app.supervise.review_context import review_prompt, review_window
from app.supervise.verifier import Verifier
from app.track.geometry import FrameState
from app.track.native_video import probe_video
from app.track.recovery import recover_once
from app.track.sam import track, track_video


def tracked_stage(
    settings: Settings,
    folder: Path,
    name: str,
    client: MetaClient,
    protocol: Protocol,
    video: Path,
    paths: list[tuple[float, Path]],
    video_hash: str,
    color: bool = False,
    provider: TrackingProvider | None = None,
) -> list[FrameState]:
    enabled = (folder / "resume.json").exists()
    key = checkpoint_key(settings, protocol, video, color) if enabled else ""
    if provider is not None:
        from app.replay_cache import digest

        key = digest([key, provider.provider_id])
    checkpoint = folder / (name + ".npz")
    if enabled:
        saved = load_frames(
            checkpoint,
            key,
            paths,
            (settings.max_run_mask_mb if name == "tracking" else settings.max_validation_mask_mb)
            * 1024
            * 1024,
        )
        if saved is not None:
            return saved
    started = time.perf_counter()
    result = (
        provider.track(protocol, video, paths, video_hash, color)
        if provider is not None
        else (
            track_video(client, protocol, video, paths, video_hash, *([True] if color else []))
            if settings.sam_mode == "video"
            else track(client, protocol, paths, video_hash, *([True] if color else []))
        )
    )
    stats_path = folder / "tracking_stats.json"
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
    stats[name] = {
        "wall_ms": (time.perf_counter() - started) * 1000,
        "provider": provider.provider_id if provider else "meta-sam-3.1-v1",
        "sampled_frames": len(result),
        "unknown_frames_by_object": {
            obj.name: sum(f.objects.get(obj.name) is None for f in result)
            for obj in protocol.objects
        },
    }
    atomic_json(stats_path, stats)
    if enabled:
        save_frames(checkpoint, key, result)
        persist(settings)
    return result


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


def process_learn(
    settings: Settings, job: str, turns: list[TranscriptTurn], narration_text: str = ""
) -> None:
    folder = settings.data_dir / "jobs" / job
    client = MetaClient(settings, job)
    progress = JobProgress(folder)
    progress.update("Preparing your teaching video")
    try:
        video, source_offset, chosen = selected_video(folder / "original.mp4")
        if chosen and turns:
            turns = [
                TranscriptTurn(
                    start=max(0, t.start - source_offset),
                    end=min(chosen["end"] - source_offset, t.end - source_offset),
                    text=t.text,
                )
                for t in turns
                if t.end > source_offset and t.start < chosen["end"]
            ]
        if len(narration_text) > 4000:
            raise ValueError("Narration text must be at most 4000 characters")
        # Persist this resolution in the protocol so later pixel thresholds use
        # the same coordinate system. Leave headroom on the 512 MiB free worker.
        frames = sample(video, folder / "frames", 2, settings.max_teaching_duration_s * 2, 512)
        first_image = cv2.imread(str(frames[0][1]))
        if first_image is None or max(first_image.shape[:2]) < 64:
            raise ValueError(
                "Teaching frames must be readable and at least 64 pixels on the long side."
            )
        frame_side = max(first_image.shape[:2])
        if not turns and narration_text.strip():
            duration = float(probe_video(video)["duration_s"])
            turns = [TranscriptTurn(start=0, end=duration, text=narration_text.strip())]
        resumable = (folder / "resume.json").exists()
        if not turns and resumable and (folder / "narration.json").exists():
            turns = [
                TranscriptTurn.model_validate(t)
                for t in json.loads((folder / "narration.json").read_text())
            ]
        if not turns:
            progress.update("Reading the narration")
            audio = folder / "audio.wav"
            extract_audio(video, audio)
            turns = transcribe(client, audio)
        atomic_json(folder / "narration.json", [turn.model_dump() for turn in turns])
        persist(settings)
        progress.update("Writing the steps")
        selected = teaching_keyframes(frames) if len(frames) > 180 else keyframes(frames)
        protocol = (
            Protocol.model_validate_json((folder / "protocol.json").read_text())
            if resumable and (folder / "protocol.json").exists()
            else compile_protocol(client, selected, turns)
        )
        protocol.frame_max_side = frame_side
        atomic_json(folder / "protocol.json", protocol.model_dump(by_alias=True))
        persist(settings)
        atomic_json(folder / "narration.json", [turn.model_dump() for turn in turns])
        suggestions = {
            key: value.model_dump()
            for key, value in suggest_boundaries(protocol, turns, frames[-1][0]).items()
        }
        if source_offset:
            suggestions = {
                key: {"start": value["start"] + source_offset, "end": value["end"] + source_offset}
                for key, value in suggestions.items()
            }
        atomic_json(folder / "boundary_suggestions.json", suggestions)
        atomic_json(
            folder / "status.json",
            {
                "id": job,
                "status": "ready",
                "protocol": protocol.model_dump(by_alias=True),
                "validation": None,
                "boundary_suggestions": suggestions,
                "analysis_range": chosen,
                "boundary_suggestions_scope": "Narration timing proposals only. Check the video, fill missing steps and confirm every range before validation.",
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
    frames: list[FrameState],
    paths: list[tuple[float, Path]],
    folder: Path,
    *,
    overlay_refs: set[str] | None = None,
    evidence_refs: set[str] | None = None,
) -> dict[str, bytes]:
    evidence: dict[str, bytes] = {}
    for frame, (_, path) in zip(frames, paths, strict=True):
        if overlay_refs is not None and str(path) not in overlay_refs:
            continue
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
        if evidence_refs is None or str(path) in evidence_refs:
            evidence[str(path)] = output.read_bytes()
    return evidence


def finalize_run(folder: Path, run: dict[str, Any], evidence: dict[str, bytes]) -> None:
    run["summary"] = summarize(run)
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
        "tier_distribution": dict(
            Counter(
                settings.open_tier_label if c["tier"] == "glimmer" else c["tier"] for c in calls
            )
        ),
        "open_tier_label": settings.open_tier_label,
        "calls": calls,
        "cloud_frames": cloud,
        "local_frames": local,
        "egress_percent": 100 * cloud / (cloud + local) if cloud + local else None,
        "shadow_agreement": sum(bool(s.get("agree")) for s in available) / len(available)
        if available
        else None,
        "shadow_available": len(available),
        "shadow_requested": len({s.get("step_id") for s in shadow}),
        "shadow_opinions_requested": len(shadow),
        "note": "Egress counts frame transmissions including retries, not distinct frames. Modal is cloud.",
    }


def run_recording(
    settings: Settings,
    job: str,
    video: Path,
    protocol: Protocol,
    color_fallback: bool = False,
    *,
    fail_on_budget_exhaustion: bool = False,
    tracking_provider: TrackingProvider | None = None,
    spark_opinion: OpinionProvider | None = None,
) -> dict[str, Any]:
    """Run one recording through the same deterministic pipeline used by the API.

    The caller owns authorization, opt-in and input provenance. Exceptions propagate
    so offline tooling can stop without treating a failed run as a prediction.
    """
    folder = settings.data_dir / "jobs" / job
    folder.mkdir(parents=True, exist_ok=True)
    client = MetaClient(settings, job)
    try:
        progress = JobProgress(folder)
        progress.update("Preparing your recording")
        source_video = video
        video, source_offset, chosen = selected_video(video)
        paths = (
            sample(
                video,
                folder / "frames",
                2,
                settings.max_run_duration_s * 2,
                protocol.frame_max_side,
                protocol.frame_max_side < 1024,
            )
            if settings.sam_mode == "video"
            else sample(
                video,
                folder / "frames",
                2,
                180,
                protocol.frame_max_side,
                protocol.frame_max_side < 1024,
            )
        )
        plan = plan_long_recording(settings, protocol, video, paths, color_fallback)
        if plan:
            atomic_json(folder / "processing_plan.json", plan)
        client.tracking_progress = lambda done, total, unit: progress.update(
            "Finding objects in your recording", done, total, unit
        )
        client.mask_progress = lambda stage, done, total: progress.update(
            stage + " in your recording",
            done,
            total,
            "parts" if stage == "Checking mask data" else "masks",
        )
        frames = tracked_stage(
            settings,
            folder,
            "tracking",
            client,
            protocol,
            video,
            paths,
            file_hash(video),
            color_fallback,
            provider=tracking_provider,
        )
        progress.update("Checking the observed steps")
        supervisor = replay(protocol, frames)
        recovery = recover_once(
            client, protocol, frames, paths, supervisor.events, file_hash(video)
        )
        if recovery.changed_frame is not None:
            frames = recovery.frames
            supervisor = replay(protocol, frames)
        glimmer = GlimmerClient(settings, job)
        event_refs = {e.evidence_frame for e in supervisor.events if e.evidence_frame is not None}
        review_refs = {
            str(path)
            for event in supervisor.events
            if event.kind in ("step_completed", "uncertain")
            for _, path in review_window(paths, supervisor.events, event)
        }
        evidence = evidence_overlays(
            frames,
            paths,
            folder,
            overlay_refs=event_refs | review_refs,
            evidence_refs=event_refs,
        )
        review_full: list[Path] = []
        budget_blocked: list[BudgetExceeded] = []

        def spark_review(prompt: str, _images: list[Path]) -> Opinion:
            try:
                return (
                    spark_opinion(prompt, review_full)
                    if spark_opinion is not None
                    else client.structured(prompt, Opinion, review_full)
                )
            except BudgetExceeded as exc:
                # Verifier treats unavailable advisory models as uncertainty. The offline
                # batch may additionally stop instead of publishing a partial prediction.
                budget_blocked.append(exc)
                raise

        verifier = Verifier(
            glimmer.opinion,
            spark_review,
            api_only=not bool(settings.glimmer_base_url),
            open_tier_label=settings.open_tier_label,
        )
        review_total = sum(e.kind in ("step_completed", "uncertain") for e in supervisor.events)
        reviewed = 0
        progress.update("Reviewing uncertain and completed steps", 0, review_total, "step reviews")
        events = []
        for event in supervisor.events:
            events.append(event)
            if event.kind not in ("step_completed", "uncertain"):
                continue
            selected = review_window(paths, supervisor.events, event)
            nearby = [p for _, p in selected]
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
            if step is None:
                continue
            prompt = review_prompt(step, event, frames, [t for t, _ in selected])
            events.extend(
                verifier.review(event, prompt, review_crops, shadow=event.kind == "step_completed")
            )
            reviewed += 1
            progress.update(
                "Reviewing uncertain and completed steps", reviewed, review_total, "step reviews"
            )
            if fail_on_budget_exhaustion and budget_blocked:
                raise budget_blocked[-1]
        run: dict[str, Any] = {
            "id": job,
            "name": "Uploaded recording",
            "status": "ready",
            "provenance": "live-recording",
            "tracking_mode": settings.sam_mode,
            "processing_plan": plan,
            "video_sha256": file_hash(source_video),
            "analysis_range": chosen,
            "protocol": protocol.model_dump(by_alias=True),
            "frames": [
                wire_frame(f, max_contour_points=64 if len(paths) > 180 else 256) for f in frames
            ],
            "duration": frames[-1].t,
            "events": [e.model_dump() for e in events],
            "states": {k: s.status for k, s in supervisor.states.items()},
            "metrics": call_metrics(settings, job, verifier.shadow),
            "shadow": verifier.shadow,
            "tracking_stats": json.loads((folder / "tracking_stats.json").read_text())
            if (folder / "tracking_stats.json").exists()
            else {},
            "recovery_actions": recovery.actions,
        }
        if source_offset:
            for frame in run["frames"]:
                frame["t"] += source_offset
            for event in run["events"]:
                event["t"] += source_offset
            run["duration"] = (
                chosen["source_duration"] if chosen else run["duration"] + source_offset
            )
            run["advisory_time_scope"] = (
                "Model narrative times may be relative to the selected section. Event timestamps refer to the original recording."
            )
        run["events"].sort(key=lambda e: e["t"])
        finalize_run(folder, run, evidence)
        return run
    finally:
        client.close()


def process_run(settings: Settings, job: str, protocol: Protocol, color_fallback: bool) -> None:
    folder = settings.data_dir / "jobs" / job
    try:
        run_recording(settings, job, folder / "original.mp4", protocol, color_fallback)
    except Exception as exc:
        atomic_json(folder / "run.json", {"id": job, "status": "error", "error": error_name(exc)})


def failing_step_ids(protocol: Protocol, result: dict[str, object]) -> list[str]:
    """Select only steps whose observed validation diagnostics identify a failure."""
    failed: set[str] = set()
    discriminative = result.get("steps", {})
    if isinstance(discriminative, dict):
        failed.update(str(step_id) for step_id, passed in discriminative.items() if passed is False)
    controls = result.get("counterfactuals", [])
    if isinstance(controls, list):
        for control in controls:
            if isinstance(control, dict) and control.get("eligible") and not control.get("flagged"):
                failed.add(str(control.get("step")))
                if control.get("swap_with"):
                    failed.add(str(control["swap_with"]))
    states = result.get("replay_states", {})
    if isinstance(states, dict):
        for replay_states in states.values():
            if isinstance(replay_states, dict):
                failed.update(str(key) for key, status in replay_states.items() if status != "DONE")
    return [step.id for step in protocol.steps if step.id in failed]


def process_validation(
    settings: Settings, job: str, ranges: dict[str, StepRange], repair: bool
) -> None:
    folder = settings.data_dir / "jobs" / job
    client = MetaClient(settings, job + "-validation")
    try:
        progress = JobProgress(folder)
        progress.update("Preparing both videos")
        protocol = Protocol.model_validate_json((folder / "protocol.json").read_text())
        a_hash, b_hash = file_hash(folder / "original.mp4"), file_hash(folder / "heldout.mp4")
        if a_hash == b_hash:
            raise ValueError("Held-out recording must differ from the compile recording")
        validate_step_ranges(protocol, ranges)
        duration = float(probe_video(folder / "original.mp4")["duration_s"])
        validate_step_ranges(protocol, ranges, duration)
        a_video, a_offset, a_selection = selected_video(folder / "original.mp4")
        b_video, _, b_selection = selected_video(folder / "heldout.mp4")
        if a_selection and any(
            r.start < a_selection["start"] or r.end > a_selection["end"] for r in ranges.values()
        ):
            raise ValueError("Step boundaries must stay inside the selected teaching section")
        local_ranges = {
            k: StepRange(start=v.start - a_offset, end=v.end - a_offset) for k, v in ranges.items()
        }
        a_paths = sample(
            a_video,
            folder / "frames",
            2,
            settings.max_teaching_duration_s * 2,
            protocol.frame_max_side,
            protocol.frame_max_side < 1024,
        )
        b_paths = sample(
            b_video,
            folder / "heldout-frames",
            2,
            settings.max_teaching_duration_s * 2,
            protocol.frame_max_side,
            protocol.frame_max_side < 1024,
        )
        plan = plan_validation(settings, protocol, a_video, a_paths, b_video, b_paths)
        if plan:
            atomic_json(folder / "validation_plan.json", plan)
        client.tracking_progress = lambda done, total, unit: progress.update(
            "Finding objects in the teaching video", done, total, unit
        )
        client.mask_progress = lambda stage, done, total: progress.update(
            stage + " in the teaching video",
            done,
            total,
            "parts" if stage == "Checking mask data" else "masks",
        )
        if settings.sam_mode == "video":
            a = tracked_stage(
                settings,
                folder,
                "teaching-tracking",
                client,
                protocol,
                a_video,
                a_paths,
                file_hash(a_video),
            )
            client.tracking_progress = lambda done, total, unit: progress.update(
                "Finding objects in the second video", done, total, unit
            )
            client.mask_progress = lambda stage, done, total: progress.update(
                stage + " in the second video",
                done,
                total,
                "parts" if stage == "Checking mask data" else "masks",
            )
            b = tracked_stage(
                settings,
                folder,
                "second-tracking",
                client,
                protocol,
                b_video,
                b_paths,
                file_hash(b_video),
            )
        else:
            a = tracked_stage(
                settings,
                folder,
                "teaching-tracking",
                client,
                protocol,
                a_video,
                a_paths,
                file_hash(a_video),
            )
            client.tracking_progress = lambda done, total, unit: progress.update(
                "Finding objects in the second video", done, total, unit
            )
            b = tracked_stage(
                settings,
                folder,
                "second-tracking",
                client,
                protocol,
                b_video,
                b_paths,
                file_hash(b_video),
            )
        progress.update("Testing the steps and deliberate mistakes")
        result = validate_protocol(protocol, a, b, local_ranges)
        history: list[dict[str, object]] = [
            {
                "round": 0,
                "checks": result["checks"],
                "verified": result["verified"],
                "attempted_steps": [],
                "repaired_steps": [],
            }
        ]
        for round_idx in range(1, 4):
            if result["verified"] or not repair:
                break
            failed = failing_step_ids(protocol, result)
            if not failed:
                break
            changed: list[str] = []
            repair_stage = f"Improving unclear steps (round {round_idx})"
            progress.update(repair_stage, 0, len(failed), "steps")
            repaired_count = 0
            for i, step in enumerate(protocol.steps):
                if step.id not in failed:
                    continue
                fixed = repair_step(client, step, json.dumps(result), keyframes(a_paths, limit=3))
                if fixed.id != step.id:
                    raise ValueError("Repair changed a step ID")
                if fixed != step:
                    changed.append(step.id)
                    protocol.steps[i] = fixed
                repaired_count += 1
                progress.update(repair_stage, repaired_count, len(failed), "steps")
            if changed:
                protocol = Protocol.model_validate(protocol.model_dump(by_alias=True))
                result = validate_protocol(protocol, a, b, local_ranges)
            result["repair_rounds"] = round_idx
            history.append(
                {
                    "round": round_idx,
                    "checks": result["checks"],
                    "verified": result["verified"],
                    "attempted_steps": failed,
                    "repaired_steps": changed,
                    "changed_steps": changed,
                }
            )
            if not changed:
                break
        result["repair_history"] = history
        result["compile_video_sha256"] = a_hash
        result["held_out_video_sha256"] = b_hash
        result["analysis_ranges"] = {"teaching": a_selection, "second": b_selection}
        result["tracking_mode"] = settings.sam_mode
        result["processing_plan"] = plan
        atomic_json(folder / "self_check.json", result)
        atomic_json(folder / "protocol.json", protocol.model_dump(by_alias=True))
        atomic_json(
            folder / "status.json",
            {
                "id": job,
                "status": "ready",
                "protocol": protocol.model_dump(by_alias=True),
                "validation": result,
                "boundary_suggestions": json.loads(
                    (folder / "boundary_suggestions.json").read_text()
                )
                if (folder / "boundary_suggestions.json").exists()
                else {},
                "analysis_range": a_selection,
                "confirmed_ranges": {key: value.model_dump() for key, value in ranges.items()},
                "provenance": "live-meta-compiled",
            },
        )
    except Exception as exc:
        atomic_json(
            folder / "status.json", {"id": job, "status": "error", "error": error_name(exc)}
        )
    finally:
        client.close()
