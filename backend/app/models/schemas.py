from pydantic import BaseModel, Field


class VideoOut(BaseModel):
    id: str
    filename: str
    location: str
    recording_start_time: str
    status: str
    progress: float


class VideoStatus(BaseModel):
    video_id: str
    status: str
    progress: float
    current_time_seconds: float
    event_count: int
    alert_count: int
    error: str | None = None


class EventOut(BaseModel):
    id: str
    video_id: str
    timestamp_seconds: float
    timestamp_iso: str
    objects: list[str]
    track_ids: list[str]
    caption: str
    location: str
    frame_path: str | None = None
    confidence_summary: dict[str, float] = Field(default_factory=dict)


class AlertRuleIn(BaseModel):
    text: str
    cooldown_seconds: int | None = None


class AlertRuleOut(BaseModel):
    id: str
    text: str
    object_keywords: list[str]
    cooldown_seconds: int
    enabled: bool


class AlertHitOut(BaseModel):
    id: str
    rule_id: str
    event_id: str
    message: str
    timestamp_iso: str


class AlertsOut(BaseModel):
    rules: list[AlertRuleOut]
    hits: list[AlertHitOut]


class QueryIn(BaseModel):
    question: str
    video_id: str | None = None


class QueryOut(BaseModel):
    answer: str
    supporting_events: list[EventOut]
    used_fallback: bool


class UploadOut(BaseModel):
    video: VideoOut


class StatusOut(VideoStatus):
    pass


class SeedOut(BaseModel):
    video_id: str
    created_events: int
    created_rules: int
    created_hits: int


class HealthOut(BaseModel):
    ok: bool = True
    app_name: str
