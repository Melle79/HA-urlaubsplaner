"""Urlaubsplaner – Flask-Backend des Home Assistant Add-ons."""
from __future__ import annotations

import logging
import os
import threading
import time as time_module
from datetime import date, datetime, time as dt_time, timedelta

from flask import Flask, jsonify, request, send_from_directory

import ha_api
import ical
import logic
import notify
import store
from mqtt_publisher import Publisher, entity_list
from version import VERSION

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
_LOGGER = logging.getLogger("urlaubsplaner")

app = Flask(__name__, static_folder="../frontend", static_url_path="")

publisher: Publisher | None = None
_publish_lock = threading.Lock()
_scheduler_event = threading.Event()  # wird gesetzt wenn sich Urlaube ändern -> Scheduler wacht auf


def _interrupt_scheduler() -> None:
    """Scheduler-Sleep unterbrechen damit er den neuen Weckpunkt berechnet."""
    _scheduler_event.set()


# ---------------------------------------------------------------- Publizieren

def publish_now() -> None:
    """Zustände berechnen und via MQTT publizieren. Schaltet keine Helfer.
    Unterbricht den Scheduler damit er den Weckpunkt neu berechnet."""
    with _publish_lock:
        urlaube = store.load_urlaube()
        states = logic.build_states(urlaube)
        if publisher is not None:
            publisher.publish_discovery()
            publisher.publish_states(states)
    _interrupt_scheduler()


def _sync_helpers() -> None:
    """Helfer-Regeln anwenden – wird NUR vom Scheduler aufgerufen.

    Schaltet Entitäten basierend auf dem aktuellen Zustand der Entitäten:
    aktiv → einschalten/Option setzen, inaktiv → ausschalten/zurücksetzen.
    """
    helpers = store.load_helpers()
    if not helpers:
        return
    if not ha_api.available():
        _LOGGER.warning("SUPERVISOR_TOKEN fehlt – Helfer können nicht geschaltet werden")
        return
    urlaube = store.load_urlaube()
    states = logic.build_states(urlaube)
    for rule in helpers:
        key = ("urlaub_morgen" if rule.get("trigger") == "morgen"
               else "urlaub_gerade_vorbei" if rule.get("trigger") == "vorbei"
               else "urlaub_heute")
        active = states[key]["state"] == "ON"
        action = rule.get("action", "ein")
        entity = rule["entity"]
        _LOGGER.info("Helfer-Sync: %s | %s=%s | Aktion=%s", entity, key, "ON" if active else "OFF", action)
        if action == "ein":
            ha_api.set_onoff(entity, active)
        elif action == "aus":
            ha_api.set_onoff(entity, not active)
        elif action == "option":
            target = rule.get("option_urlaub") if active else rule.get("option_normal")
            if target:
                ha_api.select_option(entity, target)
            else:
                _LOGGER.info("Helfer %s – keine Option für diesen Zustand, übersprungen", entity)


# ---------------------------------------------------------------- MQTT-Commands
# Die Lovelace-Card sendet über den HA-Service `mqtt.publish` JSON-Commands
# an `urlaubsplaner/cmd`: {"action": "add"|"update"|"delete", ...}

def handle_command(payload: dict) -> None:
    action = str(payload.get("action", "")).lower()
    try:
        if action == "add":
            entry = store.add_urlaub(
                payload.get("start"), payload.get("end"), payload.get("label", ""),
                payload.get("start_time", ""), payload.get("end_time", ""),
            )
            _LOGGER.info("Command: Urlaub angelegt (%s)", entry["id"])
        elif action == "update":
            entry = store.update_urlaub(
                str(payload.get("id", "")),
                payload.get("start"), payload.get("end"), payload.get("label", ""),
                payload.get("start_time", ""), payload.get("end_time", ""),
            )
            if entry is None:
                _LOGGER.warning("Command: Urlaub %s nicht gefunden", payload.get("id"))
                return
            _LOGGER.info("Command: Urlaub aktualisiert (%s)", entry["id"])
        elif action == "delete":
            removed = store.delete_urlaub(str(payload.get("id", "")))
            if removed is None:
                _LOGGER.warning("Command: Urlaub %s nicht gefunden", payload.get("id"))
                return
            _LOGGER.info("Command: Urlaub gelöscht (%s)", removed["id"])
        else:
            _LOGGER.warning("Command: unbekannte Aktion %r", action)
            return
    except store.ValidationError as err:
        _LOGGER.warning("Command: ungültige Daten: %s", err)
        return
    publish_now()


# ---------------------------------------------------------------- Scheduler

def _scheduler() -> None:
    """Helfer zu relevanten Zeitpunkten schalten."""
    _LOGGER.info("Scheduler gestartet – einmaliger Sync beim Start")
    _sync_helpers()

    last_day = date.today()
    while True:
        try:
            _scheduler_event.clear()
            urlaube = store.load_urlaube()
            wakeup = logic.next_wakeup(urlaube)
            now = datetime.now()
            midnight = datetime.combine(date.today() + timedelta(days=1), dt_time(0, 0, 5))
            next_tick = min(wakeup, midnight) if wakeup else midnight
            sleep_secs = max(10, (next_tick - now).total_seconds())
            _LOGGER.info(
                "Scheduler: nächster Weckzeitpunkt %s (in %.0f s / %.1f h)",
                next_tick.strftime("%d.%m. %H:%M"), sleep_secs, sleep_secs / 3600,
            )
            interrupted = _scheduler_event.wait(timeout=sleep_secs)
            if interrupted:
                _LOGGER.info("Scheduler: Urlaub geändert – Weckpunkt wird neu berechnet")
                continue  # sofort neu berechnen, noch nicht schalten
            if date.today() != last_day:
                last_day = date.today()
                _LOGGER.info("Datumswechsel – Helfer werden synchronisiert")
            else:
                _LOGGER.info("Uhrzeit-Trigger %s – Helfer werden synchronisiert",
                             next_tick.strftime("%H:%M"))
            publish_now()
            _sync_helpers()
            # Täglich um Mitternacht: Urlaubserinnerungen prüfen
            if date.today() != last_day or True:  # immer nach Datumswechsel
                notify.check_and_notify(store.load_urlaube())
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Scheduler-Fehler: %s", err)
            time_module.sleep(60)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/status")
def api_status():
    return jsonify(
        {
            "version": VERSION,
            "mqtt_connected": bool(publisher and publisher.connected.is_set()),
            "ha_api": ha_api.available(),
            "anzahl": len(store.load_urlaube()),
            "entities": entity_list(),
        }
    )


@app.route("/api/debug")
def api_debug():
    """Diagnose: zeigt aktuellen Zustand, Helfer und was geschaltet werden würde."""
    import time as _t
    urlaube = store.load_urlaube()
    helpers = store.load_helpers()
    states = logic.build_states(urlaube)
    wakeup = logic.next_wakeup(urlaube)
    now = datetime.now()

    result = {
        "systemzeit": now.strftime("%d.%m.%Y %H:%M:%S"),
        "zeitzone": list(getattr(_t, "tzname", ("?", "?"))),
        "ha_api_verfuegbar": ha_api.available(),
        "supervisor_token_gesetzt": bool(os.environ.get("SUPERVISOR_TOKEN")),
        "naechster_weckpunkt": wakeup.strftime("%d.%m. %H:%M") if wakeup else "Mitternacht",
        "urlaube": urlaube,
        "states": {k: v["state"] for k, v in states.items()},
        "helfer": helpers,
        "was_wuerde_jetzt_geschaltet": [],
    }

    for rule in helpers:
        key = ("urlaub_morgen" if rule.get("trigger") == "morgen"
               else "urlaub_gerade_vorbei" if rule.get("trigger") == "vorbei"
               else "urlaub_heute")
        active = states[key]["state"] == "ON"
        action = rule.get("action", "ein")
        entity = rule["entity"]
        if action == "ein":
            soll = "ON" if active else "OFF"
        elif action == "aus":
            soll = "OFF" if active else "ON"
        elif action == "option":
            soll = rule.get("option_urlaub") if active else rule.get("option_normal") or "(nichts)"
        else:
            soll = "?"
        result["was_wuerde_jetzt_geschaltet"].append({
            "entity": entity,
            "trigger": key,
            "trigger_state": states[key]["state"],
            "aktion": action,
            "soll_zustand": soll,
            "ha_api_ok": ha_api.available(),
        })

    return jsonify(result)


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """Helfer manuell synchronisieren (für Diagnosezwecke)."""
    _LOGGER.info("Manueller Sync via Web-UI ausgelöst")
    _sync_helpers()
    return jsonify({"ok": True})


@app.route("/api/entities", methods=["GET"])
def api_entities():
    return jsonify({"available": ha_api.available(), "entities": ha_api.list_entities()})


@app.route("/api/helpers", methods=["GET"])
def api_helpers():
    return jsonify(store.load_helpers())


@app.route("/api/helpers", methods=["POST"])
def api_add_helper():
    data = request.get_json(silent=True) or {}
    try:
        rule = store.add_helper(data)
    except store.ValidationError as err:
        return jsonify({"error": str(err)}), 400
    warning = None
    if ha_api.available() and ha_api.get_state(rule["entity"]) is None:
        warning = "Entität wurde in HA nicht gefunden"
    publish_now()
    return jsonify({**rule, **({"warning": warning} if warning else {})}), 201


@app.route("/api/helpers/<hid>", methods=["PUT"])
def api_update_helper(hid: str):
    data = request.get_json(silent=True) or {}
    try:
        rule = store.update_helper(hid, data)
    except store.ValidationError as err:
        return jsonify({"error": str(err)}), 400
    if rule is None:
        return jsonify({"error": "Nicht gefunden"}), 404
    publish_now()
    return jsonify(rule)


@app.route("/api/helpers/<hid>", methods=["DELETE"])
def api_delete_helper(hid: str):
    removed = store.delete_helper(hid)
    if removed is None:
        return jsonify({"error": "Nicht gefunden"}), 404
    return jsonify({"ok": True})


@app.route("/api/urlaube", methods=["GET"])
def api_urlaube():
    return jsonify(store.load_urlaube())


@app.route("/api/urlaube", methods=["POST"])
def api_add_urlaub():
    data = request.get_json(silent=True) or {}
    try:
        entry = store.add_urlaub(
            data.get("start"), data.get("end"), data.get("label", ""),
            data.get("start_time", ""), data.get("end_time", ""),
        )
    except store.ValidationError as err:
        return jsonify({"error": str(err)}), 400
    publish_now()
    return jsonify(entry), 201


@app.route("/api/urlaube/<uid>", methods=["PUT"])
def api_update_urlaub(uid: str):
    data = request.get_json(silent=True) or {}
    try:
        entry = store.update_urlaub(
            uid, data.get("start"), data.get("end"), data.get("label", ""),
            data.get("start_time", ""), data.get("end_time", ""),
        )
    except store.ValidationError as err:
        return jsonify({"error": str(err)}), 400
    if entry is None:
        return jsonify({"error": "Nicht gefunden"}), 404
    publish_now()
    return jsonify(entry)


@app.route("/api/urlaube/<uid>", methods=["DELETE"])
def api_delete_urlaub(uid: str):
    removed = store.delete_urlaub(uid)
    if removed is None:
        return jsonify({"error": "Nicht gefunden"}), 404
    publish_now()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Start

# ---------------------------------------------------------------- iCal

@app.route("/api/urlaube.ics")
def api_ical_export():
    urlaube = store.load_urlaube()
    data = ical.export_ical(urlaube)
    return data, 200, {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Disposition": "attachment; filename=urlaube.ics",
    }


@app.route("/api/ical/import", methods=["POST"])
def api_ical_import():
    data = request.get_data()
    if not data:
        return jsonify({"error": "Keine Datei erhalten"}), 400
    nur_zukuenftige = request.args.get("nur_zukuenftige", "1") == "1"
    imported, warnings = ical.import_ical(data)

    if nur_zukuenftige:
        heute = date.today().isoformat()
        imported = [u for u in imported if u.get("end", "") >= heute]

    added, skipped = 0, 0
    existing = store.load_urlaube()

    for u in imported:
        # Duplikat: gleicher Start + Ende + Bezeichnung
        is_dup = any(
            e.get("start") == u["start"] and e.get("end") == u["end"]
            and e.get("label", "") == u.get("label", "")
            for e in existing
        )
        if is_dup:
            skipped += 1
            continue
        try:
            store.add_urlaub(u["start"], u["end"], u.get("label", ""),
                             u.get("start_time", ""), u.get("end_time", ""))
            added += 1
        except store.ValidationError as err:
            warnings.append(f"Übersprungen ({u.get('label', '?')}): {err}")
            skipped += 1

    if added:
        publish_now()
    return jsonify({"added": added, "skipped": skipped, "warnings": warnings})


# ---------------------------------------------------------------- Backup / Restore

@app.route("/api/backup")
def api_backup():
    urlaube = store.load_urlaube()
    helpers = store.load_helpers()
    notify_settings = store.load_notify_settings()
    return jsonify({
        "version": VERSION,
        "urlaube": urlaube,
        "helpers": helpers,
        "notify_settings": notify_settings,
    }), 200, {
        "Content-Disposition": "attachment; filename=urlaubsplaner-backup.json",
    }


@app.route("/api/restore", methods=["POST"])
def api_restore():
    data = request.get_json(silent=True)
    if not data or "urlaube" not in data:
        return jsonify({"error": "Ungültiges Backup-Format"}), 400

    added_u, skipped_u = 0, 0
    existing = store.load_urlaube()
    for u in data.get("urlaube", []):
        is_dup = any(
            e.get("start") == u.get("start") and e.get("end") == u.get("end")
            and e.get("label", "") == u.get("label", "")
            for e in existing
        )
        if is_dup:
            skipped_u += 1
            continue
        try:
            store.add_urlaub(u.get("start"), u.get("end"), u.get("label", ""),
                             u.get("start_time", ""), u.get("end_time", ""))
            added_u += 1
        except store.ValidationError:
            skipped_u += 1

    if added_u:
        publish_now()
    return jsonify({"urlaube_added": added_u, "urlaube_skipped": skipped_u})


# ---------------------------------------------------------------- Notify

@app.route("/api/notify/services")
def api_notify_services():
    return jsonify(notify.list_notify_services())


@app.route("/api/notify/settings", methods=["GET"])
def api_notify_settings_get():
    return jsonify(store.load_notify_settings())


@app.route("/api/notify/settings", methods=["PUT"])
def api_notify_settings_put():
    data = request.get_json(silent=True) or {}
    try:
        settings = store.save_notify_settings(data)
    except Exception as err:  # noqa: BLE001
        return jsonify({"error": str(err)}), 400
    return jsonify(settings)


@app.route("/api/notify/test", methods=["POST"])
def api_notify_test():
    data = request.get_json(silent=True) or {}
    service = str(data.get("service", ""))
    if not service:
        return jsonify({"error": "Kein Service angegeben"}), 400
    ok = notify.send_notification(service, "🏖️ Urlaubsplaner Test",
                                  "Benachrichtigung funktioniert!")
    return jsonify({"ok": ok})


def main() -> None:
    global publisher  # noqa: PLW0603

    # Startup-Diagnose
    _LOGGER.info("Urlaubsplaner v%s startet – Systemzeit: %s", VERSION, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    try:
        import time as _t
        _LOGGER.info("Zeitzone des Containers: %s", _t.tzname)
    except Exception:
        pass
    if ha_api.available():
        _LOGGER.info("HA-API verfügbar (SUPERVISOR_TOKEN gesetzt) – Helfer-Entitäten werden geschaltet")
    else:
        _LOGGER.warning(
            "SUPERVISOR_TOKEN nicht gesetzt – Helfer-Entitäten werden NICHT geschaltet! "
            "Prüfe ob 'homeassistant_api: true' in der config.yaml steht und das Add-on neu gestartet wurde."
        )

    mqtt_host = os.environ.get("MQTT_HOST")
    if mqtt_host:
        publisher = Publisher(
            host=mqtt_host,
            port=int(os.environ.get("MQTT_PORT", "1883")),
            username=os.environ.get("MQTT_USER"),
            password=os.environ.get("MQTT_PASSWORD"),
        )
        publisher.on_ready = lambda: threading.Thread(target=publish_now, daemon=True).start()
        publisher.on_command = handle_command
        publisher.start()
    else:
        _LOGGER.warning("MQTT_HOST nicht gesetzt – es werden keine Entitäten angelegt")

    threading.Thread(target=publish_now, daemon=True).start()
    threading.Thread(target=_scheduler, daemon=True).start()

    port = int(os.environ.get("PORT", "8099"))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
