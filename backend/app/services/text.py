import re


from datetime import UTC, datetime


def format_human_time(timestamp_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp_iso)
        return dt.astimezone(UTC).strftime("%H:%M:%S")
    except Exception:
        return timestamp_iso


OBJECT_SYNONYMS: dict[str, list[str]] = {
    "person": ["person", "people", "someone", "anyone", "man", "woman", "human"],
    "bag": ["bag", "backpack", "handbag", "suitcase", "luggage"],
    "cell phone": ["phone", "cell phone", "mobile", "smartphone"],
    "laptop": ["laptop", "computer"],
    "chair": ["chair", "seat"],
    "bottle": ["bottle"],
    "cup": ["cup", "mug"],
    "book": ["book"],
}


def normalize_object_label(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in {"backpack", "handbag", "suitcase"}:
        return "bag"
    return normalized


def extract_object_keywords(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for canonical, synonyms in OBJECT_SYNONYMS.items():
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in synonyms):
            found.append(canonical)
    return sorted(set(found))


def summarize_objects(objects: list[str]) -> str:
    if not objects:
        return "nothing notable"
    if len(objects) == 1:
        return objects[0]
    if len(objects) == 2:
        return f"{objects[0]} and {objects[1]}"
    return ", ".join(objects[:-1]) + f", and {objects[-1]}"

