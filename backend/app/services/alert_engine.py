from dataclasses import dataclass

from app.services.repository import Repository
from app.services.text import extract_object_keywords, format_human_time
from app.services.notifier import send_alert_email


@dataclass(slots=True)
class CompiledRule:
    keywords: list[str]
    cooldown_seconds: int


def compile_rule(text: str, cooldown_seconds: int) -> CompiledRule:
    keywords = extract_object_keywords(text)
    return CompiledRule(keywords=keywords, cooldown_seconds=cooldown_seconds)


def event_matches_rule(objects: list[str], caption: str, keywords: list[str]) -> bool:
    if not keywords:
        return False
    haystack = " ".join([*objects, caption]).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def maybe_trigger_alerts(repo: Repository, event, cooldown_override: int | None = None) -> int:
    created = 0
    rules = repo.list_alert_rules()
    for rule in rules:
        if not rule.enabled:
            continue
        if not event_matches_rule(event.objects, event.caption, rule.object_keywords):
            continue
        cooldown_seconds = cooldown_override or rule.cooldown_seconds
        latest = repo.latest_hit_for_rule(rule.id)
        if latest:
            last_event = repo.get_event(latest.event_id)
            delta = event.timestamp_seconds - last_event.timestamp_seconds
            if delta < cooldown_seconds:
                continue
        message = f"{rule.text} matched at {format_human_time(event.timestamp_iso)}"
        repo.add_alert_hit(rule.id, event.id, message, event.timestamp_iso)
        send_alert_email(rule.text, message)
        created += 1
    return created
