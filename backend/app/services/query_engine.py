from datetime import UTC, datetime
import re
import httpx
import json

from app.models.schemas import EventOut
from app.services.repository import Repository
from app.services.text import extract_object_keywords, format_human_time


class QueryEngine:
    def __init__(self, repo: Repository, base_url: str | None, api_key: str | None, model: str):
        self.repo = repo
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.model = model

    def answer(self, question: str, video_id: str | None = None) -> tuple[str, list[EventOut], bool]:
        # Broad retrieval: Get all recent events for this video
        events = self.repo.list_events(video_id=video_id, limit=100)
        
        if not events:
            return "No activity has been recorded yet.", [], False
            
        if not self.base_url:
            raise RuntimeError("LLM_BASE_URL not configured")
            
        # We sort events chronologically for the LLM context
        events_sorted = sorted(events, key=lambda e: e.timestamp_seconds)
        
        answer_text = self._llm_answer(question, events_sorted)
        
        # Parse the answer for event IDs to support seeking
        clean_answer, event_ids = self._parse_llm_response(answer_text)
        
        # Filter original events to find the ones the AI identified
        supporting_events = [e for e in events if e.id in event_ids]
        
        # If no specific IDs found, provide default context
        if not supporting_events and len(events) > 0:
            supporting_events = events[:2]
            
        return clean_answer, supporting_events, False

    def _llm_answer(self, question: str, events: list[EventOut]) -> str:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        # Create a rich timeline context with IDs
        context_lines = []
        for e in events:
            time_str = format_human_time(e.timestamp_iso)
            objects_str = ", ".join(e.objects)
            context_lines.append(f"ID: {e.id} | [{time_str}] Location: {e.location} | Objects: {objects_str} | Description: {e.caption}")
            
        context = "\n".join(context_lines)
        
        system_prompt = (
            "You are a professional security and vision assistant. "
            "You are provided with a chronological timeline of events detected in a video stream. "
            "Use this timeline to answer the user's question accurately. "
            "If the information is not in the timeline, say you don't know based on the recorded data. "
            "Be precise about times and descriptions.\n\n"
            "CRITICAL: If you find relevant events, you MUST list their IDs at the very end of your response "
            "in this exact format: Relevant Event IDs: [id1, id2]"
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": f"Timeline Events:\n{context}\n\nQuestion: {question}",
                },
            ],
            "temperature": 0.1,
        }
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    def _parse_llm_response(self, text: str) -> tuple[str, list[str]]:
        # More robust regex to catch variations:
        # Matches "Relevant Event ID", "Relevant Event IDs", "Event ID:", etc.
        # Catches IDs inside or outside of brackets
        import re
        
        # 1. Look for the "Relevant Event ID(s)" trigger
        label_pattern = r"(?:Relevant\s+)?Event\s+IDs?:\s*"
        # 2. Look for IDs which are typically UUIDs or similar hex/dash strings
        id_pattern = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{8,}"
        
        # Find the label and everything after it
        match = re.search(f"{label_pattern}(.*)", text, re.IGNORECASE | re.DOTALL)
        if match:
            remaining_text = match.group(1)
            # Find all strings that look like IDs in that remaining segment
            found_ids = re.findall(id_pattern, remaining_text, re.IGNORECASE)
            
            # Clean up the display text: Remove the entire "Relevant Event ID..." block
            clean_text = re.sub(f"{label_pattern}.*", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
            
            if found_ids:
                return clean_text, found_ids
            
        return text, []
