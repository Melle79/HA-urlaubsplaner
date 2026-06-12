"""Persistente Speicherung der Urlaubszeiträume (/data/urlaube.json)."""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import date

DATA_DIR = os.environ.get("DATA_DIR", "./data")
URLAUBE_FILE = os.path.join(DATA_DIR, "urlaube.json")
_lock = threading.Lock()


class ValidationError(ValueError):
    """Ungültige Eingabedaten."""


def _load() -> list[dict]:
    if not os.path.exists(URLAUBE_FILE):
        return []
    try:
        with open(URLAUBE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(urlaube: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = URLAUBE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(urlaube, f, ensure_ascii=False, indent=2)
    os.replace(tmp, URLAUBE_FILE)


def _validate(start: str, end: str, label: str) -> tuple[str, str, str]:
    try:
        start_d = date.fromisoformat(str(start))
        end_d = date.fromisoformat(str(end))
    except (TypeError, ValueError) as err:
        raise ValidationError("Ungültiges Datum (erwartet JJJJ-MM-TT)") from err
    if end_d < start_d:
        raise ValidationError("Das Ende darf nicht vor dem Beginn liegen")
    label = str(label or "").strip()[:60] or "Urlaub"
    return start_d.isoformat(), end_d.isoformat(), label


def load_urlaube() -> list[dict]:
    with _lock:
        urlaube = _load()
    urlaube.sort(key=lambda u: (u.get("start", ""), u.get("end", "")))
    return urlaube


def add_urlaub(start: str, end: str, label: str = "") -> dict:
    start, end, label = _validate(start, end, label)
    entry = {"id": uuid.uuid4().hex[:8], "start": start, "end": end, "label": label}
    with _lock:
        urlaube = _load()
        urlaube.append(entry)
        _save(urlaube)
    return entry


def update_urlaub(urlaub_id: str, start: str, end: str, label: str = "") -> dict | None:
    start, end, label = _validate(start, end, label)
    with _lock:
        urlaube = _load()
        entry = next((u for u in urlaube if u.get("id") == urlaub_id), None)
        if entry is None:
            return None
        entry.update({"start": start, "end": end, "label": label})
        _save(urlaube)
    return entry


def delete_urlaub(urlaub_id: str) -> dict | None:
    with _lock:
        urlaube = _load()
        removed = next((u for u in urlaube if u.get("id") == urlaub_id), None)
        if removed:
            urlaube = [u for u in urlaube if u.get("id") != urlaub_id]
            _save(urlaube)
        return removed
