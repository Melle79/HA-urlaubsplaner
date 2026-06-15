"""Persistente Speicherung der Urlaubszeiträume (/data/urlaube.json)."""
from __future__ import annotations

import json
import os
import re
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


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _validate_time(t: str | None) -> str:
    """Uhrzeit validieren; leer/None -> '' (= ganzer Tag)."""
    if not t:
        return ""
    t = str(t).strip()
    if not _TIME_RE.match(t):
        raise ValidationError("Ungültige Uhrzeit (erwartet HH:MM, z. B. 08:30)")
    return t


def _validate(start: str, end: str, label: str,
              start_time: str = "", end_time: str = "") -> tuple[str, str, str, str, str]:
    try:
        start_d = date.fromisoformat(str(start))
        end_d = date.fromisoformat(str(end))
    except (TypeError, ValueError) as err:
        raise ValidationError("Ungültiges Datum (erwartet JJJJ-MM-TT)") from err
    if end_d < start_d:
        raise ValidationError("Das Ende darf nicht vor dem Beginn liegen")
    start_t = _validate_time(start_time)
    end_t = _validate_time(end_time)
    if start_d == end_d and start_t and end_t and end_t <= start_t:
        raise ValidationError("Die Endzeit muss nach der Startzeit liegen")
    label = str(label or "").strip()[:60] or "Urlaub"
    return start_d.isoformat(), end_d.isoformat(), label, start_t, end_t


def load_urlaube() -> list[dict]:
    with _lock:
        urlaube = _load()
    urlaube.sort(key=lambda u: (u.get("start", ""), u.get("start_time", ""), u.get("end", "")))
    return urlaube


def add_urlaub(start: str, end: str, label: str = "",
               start_time: str = "", end_time: str = "") -> dict:
    start, end, label, start_t, end_t = _validate(start, end, label, start_time, end_time)
    entry = {"id": uuid.uuid4().hex[:8], "start": start, "end": end, "label": label,
             "start_time": start_t, "end_time": end_t}
    with _lock:
        urlaube = _load()
        urlaube.append(entry)
        _save(urlaube)
    return entry


def update_urlaub(urlaub_id: str, start: str, end: str, label: str = "",
                  start_time: str = "", end_time: str = "") -> dict | None:
    start, end, label, start_t, end_t = _validate(start, end, label, start_time, end_time)
    with _lock:
        urlaube = _load()
        entry = next((u for u in urlaube if u.get("id") == urlaub_id), None)
        if entry is None:
            return None
        entry.update({"start": start, "end": end, "label": label,
                      "start_time": start_t, "end_time": end_t})
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


# ---------------------------------------------------------------- Helfer-Regeln

import re as _re

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
_ENTITY_RE = _re.compile(r"^[a-z_]+\.[a-z0-9_]+$")

TRIGGERS = ("heute", "morgen")
ACTIONS = ("ein", "aus", "option")


def _validate_rule(data: dict) -> dict:
    entity = str(data.get("entity", "")).strip().lower()
    if not _ENTITY_RE.match(entity):
        raise ValidationError("Ungültige Entity-ID (erwartet z. B. input_boolean.urlaub)")
    trigger = str(data.get("trigger", "heute")).strip().lower()
    if trigger not in TRIGGERS:
        raise ValidationError("Ungültiger Auslöser (heute/morgen)")
    action = str(data.get("action", "ein")).strip().lower()
    if action not in ACTIONS:
        raise ValidationError("Ungültige Aktion (ein/aus/option)")
    option_urlaub = str(data.get("option_urlaub", "")).strip()[:100]
    option_normal = str(data.get("option_normal", "")).strip()[:100]
    if action == "option":
        if entity.split(".")[0] not in ("input_select", "select"):
            raise ValidationError("'Option setzen' geht nur mit input_select.* oder select.*")
        if not option_urlaub:
            raise ValidationError("Bitte die Option für den Urlaub angeben")
    else:
        option_urlaub = option_normal = ""
    return {
        "entity": entity,
        "trigger": trigger,
        "action": action,
        "option_urlaub": option_urlaub,
        "option_normal": option_normal,
    }


def _load_settings_raw() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_settings_raw(settings: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def load_helpers() -> list[dict]:
    """Helfer-Regeln laden; alte Einzel-Einstellung (v1.1.0) wird migriert."""
    with _lock:
        settings = _load_settings_raw()
        if "helpers" not in settings:
            # Migration von v1.1.0 ({"helper_entity": "..."})
            legacy = str(settings.get("helper_entity", "")).strip().lower()
            helpers = []
            if legacy and _ENTITY_RE.match(legacy):
                helpers.append({
                    "id": uuid.uuid4().hex[:8], "entity": legacy,
                    "trigger": "heute", "action": "ein",
                    "option_urlaub": "", "option_normal": "",
                })
            _save_settings_raw({"helpers": helpers})
            return helpers
        return settings.get("helpers", [])


def add_helper(data: dict) -> dict:
    rule = _validate_rule(data)
    rule["id"] = uuid.uuid4().hex[:8]
    with _lock:
        settings = _load_settings_raw()
        helpers = settings.get("helpers", [])
        if any(h["entity"] == rule["entity"] and h["trigger"] == rule["trigger"] for h in helpers):
            raise ValidationError("Für diese Entität gibt es mit diesem Auslöser bereits eine Regel")
        helpers.append(rule)
        _save_settings_raw({"helpers": helpers})
    return rule


def update_helper(helper_id: str, data: dict) -> dict | None:
    rule = _validate_rule(data)
    with _lock:
        settings = _load_settings_raw()
        helpers = settings.get("helpers", [])
        entry = next((h for h in helpers if h.get("id") == helper_id), None)
        if entry is None:
            return None
        if any(h["entity"] == rule["entity"] and h["trigger"] == rule["trigger"]
               and h.get("id") != helper_id for h in helpers):
            raise ValidationError("Für diese Entität gibt es mit diesem Auslöser bereits eine Regel")
        entry.update(rule)
        _save_settings_raw({"helpers": helpers})
    return entry


def delete_helper(helper_id: str) -> dict | None:
    with _lock:
        settings = _load_settings_raw()
        helpers = settings.get("helpers", [])
        removed = next((h for h in helpers if h.get("id") == helper_id), None)
        if removed:
            helpers = [h for h in helpers if h.get("id") != helper_id]
            _save_settings_raw({"helpers": helpers})
        return removed
