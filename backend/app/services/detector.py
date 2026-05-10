from dataclasses import dataclass
from typing import Any

import cv2

from app.services.text import normalize_object_label

try:
    from ultralytics import YOLO  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    YOLO = None


@dataclass(slots=True)
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]


class BaseDetector:
    def detect(self, frame: Any, frame_index: int) -> list[Detection]:
        raise NotImplementedError


class MockDetector(BaseDetector):
    def detect(self, frame: Any, frame_index: int) -> list[Detection]:
        height, width = frame.shape[:2]
        # Simulate a storyline based on frame_index
        # Assuming 1.5s sample interval and ~30fps, 10 frames is ~0.5s of real time if processed fast
        # But video_processor uses sample_stride, so frame_index increment is 'real' frame index.
        # Let's use a simpler logic based on a virtual 'tick'
        tick = frame_index // 30  # Roughly once per second of video

        if tick < 5:  # First 5 seconds: Empty
            return []
        if 5 <= tick < 15:  # 5-15s: Person enters
            return [Detection(label="person", confidence=0.92, bbox=(width // 4, height // 4, width // 2, height // 2))]
        if 15 <= tick < 25:  # 15-25s: Person with bag
            return [
                Detection(label="person", confidence=0.94, bbox=(width // 3, height // 4, width * 2 // 3, height * 2 // 3)),
                Detection(label="bag", confidence=0.88, bbox=(width // 2, height // 2, width * 2 // 3, height * 3 // 4)),
            ]
        if 25 <= tick < 40:  # 25-40s: Bag left behind
            return [Detection(label="bag", confidence=0.91, bbox=(width // 2, height // 2, width * 2 // 3, height * 3 // 4))]
        
        # 40s+: Someone comes back for the bag
        return [
            Detection(label="person", confidence=0.85, bbox=(width // 2, height // 3, width * 3 // 4, height * 2 // 3)),
            Detection(label="bag", confidence=0.89, bbox=(width // 2, height // 2, width * 2 // 3, height * 3 // 4)),
        ]


class YoloDetector(BaseDetector):
    def __init__(self, model_name: str = "yolov8n.pt"):
        if YOLO is None:
            raise RuntimeError("ultralytics is not available")
        self.model = YOLO(model_name)

    def detect(self, frame: Any, frame_index: int) -> list[Detection]:
        results = self.model.predict(frame, verbose=False)
        detections: list[Detection] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                cls_idx = int(box.cls.item())
                label = normalize_object_label(names[cls_idx])
                if label not in {"person", "bag", "cell phone", "laptop", "chair", "bottle", "cup", "book"}:
                    continue
                xyxy = box.xyxy[0].tolist()
                detections.append(
                    Detection(
                        label=label,
                        confidence=float(box.conf.item()),
                        bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])),
                    )
                )
        return detections


def build_detector(mock_mode: bool, yolo_model_name: str = "yolov8n.pt") -> BaseDetector:
    if mock_mode:
        return MockDetector()
    return YoloDetector(yolo_model_name)

