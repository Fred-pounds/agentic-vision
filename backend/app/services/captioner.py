import base64
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.text import summarize_objects


@dataclass(slots=True)
class CaptionResult:
    caption: str
    used_fallback: bool


class BaseCaptioner:
    def caption(self, frame: Any, objects: list[str], location: str, frame_index: int) -> CaptionResult:
        raise NotImplementedError


class TemplateCaptioner(BaseCaptioner):
    def caption(self, frame: Any, objects: list[str], location: str, frame_index: int) -> CaptionResult:
        action = ["appeared", "moved", "waited", "shifted"][frame_index % 4]
        caption = f"{summarize_objects(objects).capitalize()} {action} in {location}"
        return CaptionResult(caption=caption, used_fallback=True)


class OpenAICaptioner(BaseCaptioner):
    def __init__(self, base_url: str, api_key: str | None, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def caption(self, frame: Any, objects: list[str], location: str, frame_index: int) -> CaptionResult:
        _, encoded = cv2_imencode(frame)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Describe the scene briefly and concretely.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Describe this frame in one sentence. Location: {location}. Detected objects: {', '.join(objects) or 'none'}."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                    ],
                },
            ],
            "temperature": 0.2,
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        try:
            caption = data["choices"][0]["message"]["content"].strip()
        except Exception:
            caption = f"{summarize_objects(objects).capitalize()} observed in {location}"
        return CaptionResult(caption=caption, used_fallback=False)


def build_captioner(base_url: str | None, api_key: str | None, model: str) -> BaseCaptioner:
    if not base_url:
        raise RuntimeError("VLM_BASE_URL is not configured. Real captioning is required.")
    return OpenAICaptioner(base_url, api_key, model)


def cv2_imencode(frame: Any) -> tuple[bool, str]:
    import cv2

    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode frame")
    return ok, base64.b64encode(buffer.tobytes()).decode("ascii")

