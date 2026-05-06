from datetime import UTC, datetime

import httpx

from app.models.schemas import EventOut
from app.services.repository import Repository
from app.services.text import extract_object_keywords


class QueryEngine:
    def __init__(self, repo: Repository, base_url: str | None, api_key: str | None, model: str):
        self.repo = repo
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.model = model

    def answer(self, question: str, video_id: str | None = None) -> tuple[str, list[EventOut], bool]:
        keywords = extract_object_keywords(question)
        events = self._retrieve_events(question, video_id, keywords)
        if not events:
            return "I could not find matching events.", [], True
        fallback = self._fallback_answer(question, events)
        if not self.base_url:
            return fallback, events, True
        try:
            answer = self._llm_answer(question, events)
            return answer, events, False
        except Exception:
            return fallback, events, True

    def _fallback_answer(self, question: str, events: list[EventOut]) -> str:
        q = question.lower()
        if not events:
            return "I don't see any activity in the recorded footage."

        if "where" in q and ("bag" in q or "last seen" in q):
            # Find the very last event where a bag was present
            matching = [e for e in events if "bag" in e.objects]
            if matching:
                event = matching[0]  # list_events returns sorted by timestamp desc
                return f"Your bag was last seen in {event.location} at {self._format_time(event.timestamp_iso)}."
            return "I couldn't find a bag in any of the recorded events."

        if any(term in q for term in ["did anyone enter", "someone enter", "anyone enter", "any people", "see a person"]):
            people_events = [e for e in events if "person" in e.objects]
            if people_events:
                return f"Yes, I detected a person {len(people_events)} times, most recently at {self._format_time(people_events[0].timestamp_iso)}."
            return "No person was detected in the footage I analyzed."

        if "activity" in q or "happen" in q or "summary" in q or "summarize" in q:
            all_objects = set()
            for e in events:
                all_objects.update(e.objects)
            obj_str = ", ".join(all_objects) if all_objects else "no specific objects"
            return f"I observed {len(events)} events involving {obj_str}. The latest activity was at {self._format_time(events[0].timestamp_iso)}."

        summary = ", ".join(event.caption for event in events[:3])
        return f"Based on recent observations: {summary}."

    def _llm_answer(self, question: str, events: list[EventOut]) -> str:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        context = "\n".join(
            f"- {event.timestamp_iso} | {event.location} | {', '.join(event.objects)} | {event.caption}"
            for event in events[:8]
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Answer only from the provided event context. Be concise and factual.",
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nEvent context:\n{context}",
                },
            ],
            "temperature": 0.2,
        }
        if not self.base_url:
            raise RuntimeError("LLM base URL not configured")
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def _retrieve_events(self, question: str, video_id: str | None, keywords: list[str]) -> list[EventOut]:
        events = self.repo.list_events(video_id=video_id, object_name=keywords[0] if keywords else None, limit=50)
        q = question.lower()
        has_time_hint = any(term in q for term in ["afternoon", "morning", "evening", "today", "tonight"])
        if has_time_hint:
            filtered = [event for event in events if self._matches_time_hint(event.timestamp_iso, q)]
            return filtered
        if not events and video_id:
            events = self.repo.list_events(video_id=video_id, limit=50)
        if not events:
            events = self.repo.list_events(limit=50)
        return events

    @staticmethod
    def _matches_time_hint(timestamp_iso: str, q: str) -> bool:
        try:
            dt = datetime.fromisoformat(timestamp_iso)
        except ValueError:
            return True
        hour = dt.astimezone(UTC).hour
        if "morning" in q:
            return 5 <= hour < 12
        if "afternoon" in q:
            return 12 <= hour < 18
        if "evening" in q or "tonight" in q:
            return 18 <= hour <= 23
        return True

    @staticmethod
    def _format_time(timestamp_iso: str) -> str:
        try:
            dt = datetime.fromisoformat(timestamp_iso)
        except ValueError:
            return timestamp_iso
        return dt.astimezone(UTC).strftime("%-I:%M %p")
