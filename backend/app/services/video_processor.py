from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import cv2

from app.services.alert_engine import maybe_trigger_alerts
from app.services.captioner import BaseCaptioner, TemplateCaptioner, build_captioner
from app.services.detector import BaseDetector, Detection, build_detector
from app.services.repository import Repository
from app.services.text import normalize_object_label


@dataclass(slots=True)
class TrackState:
    track_id: str
    label: str
    bbox: tuple[int, int, int, int]
    last_seen_frame: int


class SimpleTracker:
    def __init__(self) -> None:
        self.next_id = 1
        self.active: dict[str, TrackState] = {}

    def assign(self, detections: list[Detection], frame_index: int) -> list[tuple[Detection, str]]:
        assignments: list[tuple[Detection, str]] = []
        remaining = dict(self.active)
        updated: dict[str, TrackState] = {}
        for detection in detections:
            matched_id = None
            matched_score = 0.0
            for track_id, track in remaining.items():
                if track.label != detection.label:
                    continue
                score = iou(track.bbox, detection.bbox)
                if score > matched_score:
                    matched_id = track_id
                    matched_score = score
            if matched_id and matched_score > 0.1:
                track_id = matched_id
                remaining.pop(track_id, None)
            else:
                track_id = f"t{self.next_id}"
                self.next_id += 1
            updated[track_id] = TrackState(track_id=track_id, label=detection.label, bbox=detection.bbox, last_seen_frame=frame_index)
            assignments.append((detection, track_id))
        self.active = updated
        return assignments


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / float(area_a + area_b - inter)


def build_processors(settings) -> tuple[BaseDetector, BaseCaptioner]:
    detector = build_detector(settings.vision_mock_mode)
    captioner = build_captioner(settings.vlm_base_url, settings.vlm_api_key, settings.vlm_model)
    return detector, captioner


def process_video(
    repo: Repository,
    settings,
    video_id: str,
    file_path: Path,
    location: str,
    recording_start_time: str,
) -> None:
    detector, captioner = build_processors(settings)
    fallback_captioner = TemplateCaptioner()
    tracker = SimpleTracker()
    cap = cv2.VideoCapture(str(file_path))
    if not cap.isOpened():
        repo.update_video_status(video_id, "failed", 1.0, error="Unable to open uploaded video")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_stride = max(1, int(round(fps * settings.frame_sample_seconds)))
    last_objects: list[str] = []
    last_caption = ""
    last_event_time = -999.0
    frame_index = 0
    created_any = False

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            current_time_seconds = frame_index / fps
            if frame_index % sample_stride != 0:
                frame_index += 1
                continue

            detections = detector.detect(frame, frame_index)
            detections = [d for d in detections if normalize_object_label(d.label)]
            assignments = tracker.assign(detections, frame_index)
            objects = sorted({normalize_object_label(d.label) for d, _ in assignments})
            track_ids = [track_id for _, track_id in assignments]

            frame_dir = settings.keyframe_dir / video_id
            frame_dir.mkdir(parents=True, exist_ok=True)
            frame_path = frame_dir / f"frame_{frame_index:06d}.jpg"
            cv2.imwrite(str(frame_path), frame)

            try:
                caption_result = captioner.caption(frame, objects, location, frame_index)
            except Exception:
                caption_result = fallback_captioner.caption(frame, objects, location, frame_index)
            timestamp_iso = iso_from_start(recording_start_time, current_time_seconds)

            # More robust change detection:
            # 1. First event ever
            # 2. Objects appeared or disappeared
            # 3. Caption changed significantly
            # 4. Periodic heartbeat (every 10 seconds of video time)
            objects_changed = set(objects) != set(last_objects)
            caption_changed = caption_result.caption != last_caption
            heartbeat = (current_time_seconds - last_event_time) >= 10.0

            if not created_any or objects_changed or caption_changed or heartbeat:
                event = repo.add_event(
                    video_id=video_id,
                    timestamp_seconds=current_time_seconds,
                    timestamp_iso=timestamp_iso,
                    objects=objects,
                    track_ids=track_ids,
                    caption=caption_result.caption,
                    location=location,
                    frame_path=str(frame_path),
                    confidence_summary={d.label: d.confidence for d in detections},
                )
                maybe_trigger_alerts(repo, event, cooldown_override=settings.alert_cooldown_seconds)
                created_any = True
                last_objects = list(objects)
                last_caption = caption_result.caption
                last_event_time = current_time_seconds
            progress = min(0.99, frame_index / max(total_frames, 1)) if total_frames else 0.5
            repo.update_video_status(video_id, "processing", progress, current_time_seconds=current_time_seconds)
            frame_index += 1
        repo.update_video_status(video_id, "completed", 1.0, current_time_seconds=frame_index / fps)
    except Exception as exc:  # pragma: no cover - demo safety
        repo.update_video_status(video_id, "failed", min(0.99, frame_index / max(total_frames, 1)), current_time_seconds=frame_index / fps, error=str(exc))
    finally:
        cap.release()


def iso_from_start(recording_start_time: str, offset_seconds: float) -> str:
    try:
        start = datetime.fromisoformat(recording_start_time)
    except ValueError:
        start = datetime.now(UTC)
    return (start + timedelta(seconds=offset_seconds)).astimezone(UTC).isoformat()
