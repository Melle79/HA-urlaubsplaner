"""Zugriff auf die Home-Assistant-API über den Supervisor-Proxy.

Wird genutzt, um optional eine bestehende Helfer-Entität (z. B. ein
input_boolean) synchron zu „Urlaub heute" zu schalten.
Benötigt `homeassistant_api: true` in der config.yaml des Add-ons.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

_LOGGER = logging.getLogger(__name__)

API_BASE = "http://supervisor/core/api"
TIMEOUT = 10


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
    """Aktuellen Zustand einer Entität lesen (None bei Fehler/unbekannt)."""
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
    """Entität ein-/ausschalten (nur wenn der Zustand abweicht)."""
    if not available():
        _LOGGER.warning("Kein SUPERVISOR_TOKEN – Helfer-Entität kann nicht geschaltet werden")
        return False
    desired = "on" if on else "off"
    current = get_state(entity_id)
    if current == desired:
        return True
    service = "turn_on" if on else "turn_off"
    try:
        _request("POST", f"/services/homeassistant/{service}", {"entity_id": entity_id})
        _LOGGER.info("Helfer-Entität %s → %s", entity_id, desired)
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Helfer-Entität %s konnte nicht geschaltet werden: %s", entity_id, err)
        return False


def select_option(entity_id: str, option: str) -> bool:
    """Option einer input_select-/select-Entität setzen (nur wenn abweichend)."""
    if not available():
        _LOGGER.warning("Kein SUPERVISOR_TOKEN – Helfer-Entität kann nicht geschaltet werden")
        return False
    if get_state(entity_id) == option:
        return True
    domain = "input_select" if entity_id.startswith("input_select.") else "select"
    try:
        _request(
            "POST",
            f"/services/{domain}/select_option",
            {"entity_id": entity_id, "option": option},
        )
        _LOGGER.info("Helfer-Entität %s → Option %r", entity_id, option)
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Option für %s konnte nicht gesetzt werden: %s", entity_id, err)
        return False
