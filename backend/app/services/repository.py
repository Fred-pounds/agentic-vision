from datetime import UTC, datetime
from uuid import uuid4

from app.models.schemas import AlertHitOut, AlertRuleOut, EventOut, VideoOut, VideoStatus
from app.storage.database import Database, dumps, loads


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def create_video(self, filename: str, location: str, recording_start_time: str) -> VideoOut:
        video_id = str(uuid4())
        self.db.execute(
            "INSERT INTO videos (id, filename, location, recording_start_time, status, progress) VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, filename, location, recording_start_time, "queued", 0),
        )
        return self.get_video(video_id)

    def get_video(self, video_id: str) -> VideoOut:
        row = self.db.fetchone("SELECT * FROM videos WHERE id = ?", (video_id,))
        if not row:
            raise KeyError(video_id)
        return VideoOut(**row)

    def update_video_status(
        self,
        video_id: str,
        status: str,
        progress: float,
        current_time_seconds: float = 0,
        error: str | None = None,
    ) -> None:
        self.db.execute(
            "UPDATE videos SET status = ?, progress = ?, current_time_seconds = ?, error = ? WHERE id = ?",
            (status, progress, current_time_seconds, error, video_id),
        )

    def get_status(self, video_id: str) -> VideoStatus:
        row = self.db.fetchone("SELECT * FROM videos WHERE id = ?", (video_id,))
        if not row:
            raise KeyError(video_id)
        event_count = self.db.fetchone("SELECT COUNT(*) AS count FROM events WHERE video_id = ?", (video_id,))["count"]
        alert_count = self.db.fetchone(
            """
            SELECT COUNT(*) AS count FROM alert_hits
            JOIN events ON alert_hits.event_id = events.id
            WHERE events.video_id = ?
            """,
            (video_id,),
        )["count"]
        return VideoStatus(
            video_id=video_id,
            status=row["status"],
            progress=row["progress"],
            current_time_seconds=row["current_time_seconds"],
            event_count=event_count,
            alert_count=alert_count,
            error=row["error"],
        )

    def add_event(
        self,
        video_id: str,
        timestamp_seconds: float,
        timestamp_iso: str,
        objects: list[str],
        track_ids: list[str],
        caption: str,
        location: str,
        frame_path: str | None,
        confidence_summary: dict[str, float],
    ) -> EventOut:
        event_id = str(uuid4())
        self.db.execute(
            """
            INSERT INTO events
            (id, video_id, timestamp_seconds, timestamp_iso, objects_json, track_ids_json, caption, location, frame_path, confidence_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                video_id,
                timestamp_seconds,
                timestamp_iso,
                dumps(objects),
                dumps(track_ids),
                caption,
                location,
                frame_path,
                dumps(confidence_summary),
            ),
        )
        return self.get_event(event_id)

    def get_event(self, event_id: str) -> EventOut:
        row = self.db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
        if not row:
            raise KeyError(event_id)
        return event_from_row(row)

    def list_events(
        self,
        video_id: str | None = None,
        object_name: str | None = None,
        limit: int = 100,
    ) -> list[EventOut]:
        clauses: list[str] = []
        params: list[object] = []
        if video_id:
            clauses.append("video_id = ?")
            params.append(video_id)
        if object_name:
            clauses.append("(objects_json LIKE ? OR caption LIKE ?)")
            params.extend([f"%{object_name}%", f"%{object_name}%"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.fetchall(
            f"SELECT * FROM events {where} ORDER BY timestamp_seconds DESC LIMIT ?",
            (*params, limit),
        )
        return [event_from_row(row) for row in rows]

    def create_alert_rule(self, text: str, object_keywords: list[str], cooldown_seconds: int) -> AlertRuleOut:
        rule_id = str(uuid4())
        self.db.execute(
            "INSERT INTO alert_rules (id, text, object_keywords_json, cooldown_seconds, enabled) VALUES (?, ?, ?, ?, 1)",
            (rule_id, text, dumps(object_keywords), cooldown_seconds),
        )
        return self.get_alert_rule(rule_id)

    def get_alert_rule(self, rule_id: str) -> AlertRuleOut:
        row = self.db.fetchone("SELECT * FROM alert_rules WHERE id = ?", (rule_id,))
        if not row:
            raise KeyError(rule_id)
        return alert_rule_from_row(row)

    def list_alert_rules(self) -> list[AlertRuleOut]:
        rows = self.db.fetchall("SELECT * FROM alert_rules ORDER BY rowid DESC")
        return [alert_rule_from_row(row) for row in rows]

    def add_alert_hit(self, rule_id: str, event_id: str, message: str, timestamp_iso: str | None = None) -> AlertHitOut:
        hit_id = str(uuid4())
        created = timestamp_iso or datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT INTO alert_hits (id, rule_id, event_id, message, timestamp_iso) VALUES (?, ?, ?, ?, ?)",
            (hit_id, rule_id, event_id, message, created),
        )
        return self.get_alert_hit(hit_id)

    def get_alert_hit(self, hit_id: str) -> AlertHitOut:
        row = self.db.fetchone("SELECT * FROM alert_hits WHERE id = ?", (hit_id,))
        if not row:
            raise KeyError(hit_id)
        return AlertHitOut(**row)

    def list_alert_hits(self) -> list[AlertHitOut]:
        rows = self.db.fetchall("SELECT * FROM alert_hits ORDER BY timestamp_iso DESC LIMIT 100")
        return [AlertHitOut(**row) for row in rows]

    def latest_hit_for_rule(self, rule_id: str) -> AlertHitOut | None:
        row = self.db.fetchone(
            "SELECT * FROM alert_hits WHERE rule_id = ? ORDER BY timestamp_iso DESC LIMIT 1",
            (rule_id,),
        )
        return AlertHitOut(**row) if row else None


def event_from_row(row: dict) -> EventOut:
    return EventOut(
        id=row["id"],
        video_id=row["video_id"],
        timestamp_seconds=row["timestamp_seconds"],
        timestamp_iso=row["timestamp_iso"],
        objects=loads(row["objects_json"]),
        track_ids=loads(row["track_ids_json"]),
        caption=row["caption"],
        location=row["location"],
        frame_path=row["frame_path"],
        confidence_summary=loads(row["confidence_json"]),
    )


def alert_rule_from_row(row: dict) -> AlertRuleOut:
    return AlertRuleOut(
        id=row["id"],
        text=row["text"],
        object_keywords=loads(row["object_keywords_json"]),
        cooldown_seconds=row["cooldown_seconds"],
        enabled=bool(row["enabled"]),
    )

