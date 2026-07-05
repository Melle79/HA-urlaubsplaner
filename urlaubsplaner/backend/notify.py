"""Urlaubserinnerungen via Home Assistant Notify-Services."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import ha_api
import store

_LOGGER = logging.getLogger(__name__)


def list_notify_services() -> list[dict]:
    """Verfügbare notify.*-Services aus HA laden.
    
    Die HA REST API /services gibt eine Liste zurück:
    [{"domain": "notify", "services": {"mobile_app_iphone": {...}, ...}}, ...]
    """
    if not ha_api.available():
        return []
    try:
        services = ha_api.get_services()
        result = []
        # Liste von {"domain": str, "services": dict}
        if isinstance(services, list):
            for entry in services:
                if not isinstance(entry, dict):
                    continue
                if entry.get("domain") != "notify":
                    continue
                svc_dict = entry.get("services") or {}
                for name, info in svc_dict.items():
                    entity_id = f"notify.{name}"
                    friendly = (info.get("name") if isinstance(info, dict) else None) \
                               or name.replace("_", " ").title()
                    result.append({"service": entity_id, "name": friendly})
        # Fallback: Dict {"notify": {"mobile_app_iphone": {...}}}
        elif isinstance(services, dict):
            svc_dict = services.get("notify") or {}
            for name, info in svc_dict.items():
                entity_id = f"notify.{name}"
                friendly = (info.get("name") if isinstance(info, dict) else None) \
                           or name.replace("_", " ").title()
                result.append({"service": entity_id, "name": friendly})
        result.sort(key=lambda s: s["service"])
        _LOGGER.info("Notify-Services gefunden: %s", [r["service"] for r in result])
        return result
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Notify-Services konnten nicht geladen werden: %s", err)
        return []


def send_notification(service: str, title: str, message: str) -> tuple[bool, str]:
    """Benachrichtigung über einen HA Notify-Service senden.
    
    Rückgabe: (ok, fehlermeldung)
    """
    if not ha_api.available():
        return False, "SUPERVISOR_TOKEN nicht gesetzt"
    domain, _, name = service.partition(".")
    if domain != "notify" or not name:
        return False, f"Ungültiger Service: {service}"
    try:
        ha_api._request("POST", f"/services/notify/{name}",
                        {"title": title, "message": message})
        _LOGGER.info("Benachrichtigung gesendet via %s: %s", service, title)
        return True, ""
    except Exception as err:  # noqa: BLE001
        detail = str(err)
        _LOGGER.warning("Benachrichtigung via %s fehlgeschlagen: %s", service, detail)
        return False, detail


def _render(template: str, ctx: dict) -> str:
    """Einfaches Template-Rendering: {platzhalter} ersetzen."""
    try:
        return template.format_map(ctx)
    except (KeyError, ValueError):
        # Unbekannte Platzhalter unverändert lassen
        import string
        result = template
        for key, val in ctx.items():
            result = result.replace("{" + key + "}", str(val))
        return result


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

        # Gemeinsamer Kontext für alle Templates
        ctx = {
            "bezeichnung":   label,
            "beginn":        start_d.strftime("%d.%m.%Y"),
            "ende":          end_d.strftime("%d.%m.%Y"),
            "dauer":         str((end_d - start_d).days + 1),
            "abfahrt":       start_time,
            "ankunft":       end_time,
            "abfahrt_info":  f" um {start_time} Uhr" if start_time else "",
            "ankunft_info":  f" um {end_time} Uhr" if end_time else "",
            "tage_vorher":   "",
            "tage_vorher_wort": "",
        }

        # Vorlauf-Erinnerungen
        for tage in vorlauf_tage:
            if (start_d - today).days == tage:
                ctx_v = {**ctx, "tage_vorher": str(tage),
                         "tage_vorher_wort": "Tag" if tage == 1 else "Tagen"}
                title = _render(settings.get("tpl_vorlauf_title",
                    store.DEFAULT_NOTIFY["tpl_vorlauf_title"]), ctx_v)
                msg = _render(settings.get("tpl_vorlauf_msg",
                    store.DEFAULT_NOTIFY["tpl_vorlauf_msg"]), ctx_v)
                _send_to_all(services, title, msg)

        # Am Tag selbst: Urlaubsbeginn
        if settings.get("notify_start", True) and start_d == today:
            title = _render(settings.get("tpl_start_title",
                store.DEFAULT_NOTIFY["tpl_start_title"]), ctx)
            msg = _render(settings.get("tpl_start_msg",
                store.DEFAULT_NOTIFY["tpl_start_msg"]), ctx)
            _send_to_all(services, title, msg)

        # Am letzten Tag: Urlaubsende
        if settings.get("notify_end", True) and end_d == today:
            title = _render(settings.get("tpl_end_title",
                store.DEFAULT_NOTIFY["tpl_end_title"]), ctx)
            msg = _render(settings.get("tpl_end_msg",
                store.DEFAULT_NOTIFY["tpl_end_msg"]), ctx)
            _send_to_all(services, title, msg)


def _send_to_all(services: list[str], title: str, message: str) -> None:
    for svc in services:
        ok, err = send_notification(svc, title, message)
        if not ok:
            _LOGGER.warning("Service %s: %s", svc, err)
