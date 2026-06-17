"""Zugriff auf die Home-Assistant-API über den Supervisor-Proxy."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

_LOGGER = logging.getLogger(__name__)

API_BASE = "http://supervisor/core/api"
TIMEOUT = 10

ONOFF_DOMAINS = ("input_boolean", "switch", "light", "fan", "automation", "script", "climate")
SELECT_DOMAINS = ("input_select", "select")


def _token() -> str:
    return os.environ.get("SUPERVISOR_TOKEN", "")


def available() -> bool:
    return bool(_token())


def _request(method: str, path: str, payload: dict | None = None) -> dict | list | None:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else None


def get_state(entity_id: str) -> str | None:
    try:
        data = _request("GET", f"/states/{entity_id}")
        return data.get("state") if isinstance(data, dict) else None
    except urllib.error.HTTPError as err:
        if err.code == 404:
            _LOGGER.warning("Helfer-Entität %s nicht gefunden", entity_id)
        else:
            _LOGGER.warning("HA-API-Fehler beim Lesen von %s: %s", entity_id, err)
        return None
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("HA-API nicht erreichbar: %s", err)
        return None


def set_onoff(entity_id: str, on: bool) -> bool:
    """Entität direkt schalten – OHNE vorherigen State-Check.

    Der State-Check war fehleranfällig (Race Conditions, falsche States).
    HA ignoriert redundante Calls ohnehin.
    """
    if not available():
        _LOGGER.warning("Kein SUPERVISOR_TOKEN – %s kann nicht geschaltet werden", entity_id)
        return False
    domain = entity_id.split(".", 1)[0]
    service = "turn_on" if on else "turn_off"
    state_str = "on" if on else "off"
    # Erst domain-spezifisch, dann homeassistant-Fallback
    for svc_domain in (domain, "homeassistant"):
        try:
            _request("POST", f"/services/{svc_domain}/{service}", {"entity_id": entity_id})
            _LOGGER.info("Helfer %s → %s (via %s.%s)", entity_id, state_str, svc_domain, service)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("%s.%s für %s fehlgeschlagen: %s", svc_domain, service, entity_id, err)
    _LOGGER.warning("Helfer %s konnte nicht auf %s geschaltet werden", entity_id, state_str)
    return False


def select_option(entity_id: str, option: str) -> bool:
    """Option einer input_select-/select-Entität setzen – OHNE vorherigen State-Check."""
    if not available():
        _LOGGER.warning("Kein SUPERVISOR_TOKEN – %s kann nicht gesetzt werden", entity_id)
        return False
    domain = entity_id.split(".", 1)[0]
    if domain not in SELECT_DOMAINS:
        _LOGGER.warning("select_option: %s ist kein Select (Domain: %s)", entity_id, domain)
        return False
    try:
        _request("POST", f"/services/{domain}/select_option",
                 {"entity_id": entity_id, "option": option})
        _LOGGER.info("Helfer %s → Option %r", entity_id, option)
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Option für %s konnte nicht gesetzt werden: %s", entity_id, err)
        return False


def list_entities() -> list[dict]:
    """Schaltbare Entitäten und Selects mit Optionen aus HA laden."""
    if not available():
        return []
    try:
        states = _request("GET", "/states")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Entitätenliste konnte nicht geladen werden: %s", err)
        return []
    out = []
    for s in states if isinstance(states, list) else []:
        eid = s.get("entity_id", "")
        domain = eid.split(".", 1)[0]
        attrs = s.get("attributes", {}) or {}
        if domain in SELECT_DOMAINS:
            out.append({
                "entity_id": eid,
                "name": attrs.get("friendly_name", eid),
                "options": list(attrs.get("options", []) or []),
            })
        elif domain in ONOFF_DOMAINS:
            out.append({
                "entity_id": eid,
                "name": attrs.get("friendly_name", eid),
                "options": None,
            })
    out.sort(key=lambda e: e["entity_id"])
    return out
