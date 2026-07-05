"""Urlaubserinnerungen via Home Assistant Notify-Services."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import ha_api
import store

_LOGGER = logging.getLogger(__name__)


def list_notify_services() -> list[dict]:
    """Verfügbare notify.*-Services aus HA laden."""
    if not ha_api.available():
        return []
    try:
        services = ha_api.get_services()
        result = []
        for domain, svc_dict in (services or {}).items():
            if domain == "notify":
                for name in svc_dict:
                    entity_id = f"notify.{name}"
                    friendly = svc_dict[name].get("name") or name.replace("_", " ").title()
                    result.append({"service": entity_id, "name": friendly})
        result.sort(key=lambda s: s["service"])
        return result
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Notify-Services konnten nicht geladen werden: %s", err)
        return []


def send_notification(service: str, title: str, message: str) -> bool:
    """Benachrichtigung über einen HA Notify-Service senden."""
    if not ha_api.available():
        return False
    # service = "notify.mobile_app_iphone_von_sven"
    domain, _, name = service.partition(".")
    if domain != "notify" or not name:
        _LOGGER.warning("Ungültiger Notify-Service: %s", service)
        return False
    try:
        ha_api._request("POST", f"/services/notify/{name}",
                        {"title": title, "message": message})
        _LOGGER.info("Benachrichtigung gesendet via %s: %s", service, title)
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Benachrichtigung via %s fehlgeschlagen: %s", service, err)
        return False


def check_and_notify(urlaube: list[dict]) -> None:
    """Täglich prüfen ob Erinnerungen gesendet werden sollen."""
    settings = store.load_notify_settings()
    services = settings.get("services", [])
    vorlauf_tage = settings.get("vorlauf_tage", [1, 7])

    if not services or not urlaube:
        return

    today = date.today()

    for u in urlaube:
        try:
            start_d = date.fromisoformat(u["start"])
            end_d = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue

        label = u.get("label") or "Urlaub"
        start_time = u.get("start_time", "")
        end_time = u.get("end_time", "")

        # Vorlauf-Erinnerungen
        for tage in vorlauf_tage:
            if (start_d - today).days == tage:
                time_info = f" um {start_time} Uhr" if start_time else ""
                title = f"🏖️ Urlaub in {tage} {'Tag' if tage == 1 else 'Tagen'}"
                msg = (f"{label} beginnt am {start_d.strftime('%d.%m.%Y')}{time_info}.\n"
                       f"Dauer: {(end_d - start_d).days + 1} Tage.")
                _send_to_all(services, title, msg)

        # Am Tag selbst: Urlaubsbeginn
        if settings.get("notify_start", True) and start_d == today:
            time_info = f" um {start_time} Uhr" if start_time else " (ganztägig)"
            title = f"🏖️ Urlaubsbeginn: {label}"
            msg = f"Dein Urlaub beginnt heute{time_info}. Schöne Zeit! 🌴"
            _send_to_all(services, title, msg)

        # Am letzten Tag: Urlaubsende
        if settings.get("notify_end", True) and end_d == today:
            time_info = f" um {end_time} Uhr" if end_time else ""
            title = f"✈️ Urlaubsende: {label}"
            msg = f"Dein Urlaub endet heute{time_info}. Willkommen zurück! 🏠"
            _send_to_all(services, title, msg)


def _send_to_all(services: list[str], title: str, message: str) -> None:
    for svc in services:
        send_notification(svc, title, message)
