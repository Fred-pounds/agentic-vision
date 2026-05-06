from __future__ import annotations

import shutil
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import Settings
from app.models.schemas import (
    AlertRuleIn,
    AlertsOut,
    EventOut,
    HealthOut,
    QueryIn,
    QueryOut,
    SeedOut,
    StatusOut,
    UploadOut,
)
from app.services.alert_engine import compile_rule
from app.services.query_engine import QueryEngine
from app.services.repository import Repository
from app.services.video_processor import process_video


def create_router(settings: Settings, repo: Repository) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(app_name=settings.app_name)

    @router.post("/upload", response_model=UploadOut)
    def upload(
        file: UploadFile = File(...),
        location: str = Form("office"),
        recording_start_time: str = Form(""),
    ) -> UploadOut:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Missing filename")
        if not recording_start_time:
            recording_start_time = datetime.now(UTC).isoformat()
        video = repo.create_video(file.filename, location, recording_start_time)
        destination = settings.upload_dir / video.id / file.filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        repo.update_video_status(video.id, "queued", 0.01)
        thread = threading.Thread(
            target=process_video,
            args=(repo, settings, video.id, destination, location, recording_start_time),
            daemon=True,
        )
        thread.start()
        return UploadOut(video=repo.get_video(video.id))

    @router.get("/videos/{video_id}/status", response_model=StatusOut)
    def video_status(video_id: str) -> StatusOut:
        try:
            return repo.get_status(video_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Video not found") from exc

    @router.get("/events", response_model=list[EventOut])
    def events(video_id: str | None = None, object: str | None = None, limit: int = 100) -> list[EventOut]:
        return repo.list_events(video_id=video_id, object_name=object, limit=limit)

    @router.post("/query", response_model=QueryOut)
    def query(payload: QueryIn) -> QueryOut:
        engine = QueryEngine(repo, settings.llm_base_url, settings.llm_api_key, settings.llm_model)
        answer, events, used_fallback = engine.answer(payload.question, payload.video_id)
        return QueryOut(answer=answer, supporting_events=events, used_fallback=used_fallback)

    @router.post("/alert", response_model=AlertRuleOut)
    def create_alert(payload: AlertRuleIn) -> AlertRuleOut:
        cooldown = payload.cooldown_seconds or settings.alert_cooldown_seconds
        compiled = compile_rule(payload.text, cooldown)
        rule = repo.create_alert_rule(payload.text, compiled.keywords, compiled.cooldown_seconds)
        return rule

    @router.get("/alerts", response_model=AlertsOut)
    def alerts() -> AlertsOut:
        return AlertsOut(rules=repo.list_alert_rules(), hits=repo.list_alert_hits())

    @router.post("/seed", response_model=SeedOut)
    def seed() -> SeedOut:
        created_events = 0
        created_rules = 0
        created_hits = 0
        video = repo.create_video("seed-demo.mp4", "office", datetime.now(UTC).isoformat())
        for i, (objects, caption) in enumerate(
            [
                (["person"], "A person enters the office."),
                (["person", "bag"], "A person places a bag on the table."),
                (["bag"], "The bag remains on the table after the person leaves."),
            ]
        ):
            event = repo.add_event(
                video_id=video.id,
                timestamp_seconds=float(i * 12),
                timestamp_iso=datetime.now(UTC).isoformat(),
                objects=objects,
                track_ids=[f"seed-{i}"],
                caption=caption,
                location="office",
                frame_path=None,
                confidence_summary={obj: 0.9 for obj in objects},
            )
            created_events += 1
            created_hits += maybe_seed_alert(repo, event)
        rule = repo.create_alert_rule("notify me when someone enters", ["person"], settings.alert_cooldown_seconds)
        created_rules += 1
        created_hits += 1
        repo.add_alert_hit(rule.id, repo.list_events(video_id=video.id, limit=1)[0].id, "Seed alert hit", datetime.now(UTC).isoformat())
        return SeedOut(video_id=video.id, created_events=created_events, created_rules=created_rules, created_hits=created_hits)

    return router


def maybe_seed_alert(repo: Repository, event) -> int:
    count = 0
    for rule in repo.list_alert_rules():
        if any(keyword in event.objects for keyword in rule.object_keywords):
            repo.add_alert_hit(rule.id, event.id, f"{rule.text} matched at {event.timestamp_iso}", event.timestamp_iso)
            count += 1
    return count
