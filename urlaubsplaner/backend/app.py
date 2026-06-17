"""Urlaubsplaner – Flask-Backend des Home Assistant Add-ons."""
from __future__ import annotations

import logging
import os
import threading
import time as time_module
from datetime import date, datetime, time as dt_time, timedelta

from flask import Flask, jsonify, request, send_from_directory

import ha_api
import logic
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


# ---------------------------------------------------------------- Publizieren

def publish_now(force_off: bool = False) -> None:
    """Zustände berechnen, via MQTT publizieren und Helfer-Entitäten schalten.

    force_off=False (Standard): beim Speichern/Ändern – schaltet nur ein, nie vorzeitig aus.
    force_off=True: vom Scheduler – schaltet auch aus wenn Urlaub vorbei.
    """
    with _publish_lock:
        urlaube = store.load_urlaube()
        states = logic.build_states(urlaube)
        if publisher is not None:
            publisher.publish_discovery()
            publisher.publish_states(states)
        _sync_helper(states, force_off=force_off)


def _sync_helper(states: dict, force_off: bool = False) -> None:
    """Helfer-Regeln anwenden: Entitäten je nach Auslöser und Aktion schalten.

    force_off=False (Standard beim Speichern/Ändern): schaltet nur EIN wenn aktiv,
    schaltet aber nicht AUS wenn noch nicht aktiv – damit ein manuell gesetzter
    Zustand nicht vorzeitig überschrieben wird.
    force_off=True (Scheduler/Datumswechsel/Urlaubsende): schaltet auch aus.
    """
    helpers = store.load_helpers()
    if not helpers:
        return
    if not ha_api.available():
        _LOGGER.warning("SUPERVISOR_TOKEN fehlt – Helfer-Entitäten können nicht geschaltet werden")
        return
    for rule in helpers:
        key = ("urlaub_morgen" if rule.get("trigger") == "morgen"
               else "urlaub_gerade_vorbei" if rule.get("trigger") == "vorbei"
               else "urlaub_heute")
        active = states[key]["state"] == "ON"
        action = rule.get("action", "ein")
        entity = rule["entity"]
        _LOGGER.info("Helfer-Sync: %s | Auslöser=%s (%s) | Aktion=%s | force_off=%s",
                     entity, key, "ON" if active else "OFF", action, force_off)
        if action == "ein":
            if active:
                ha_api.set_onoff(entity, True)
            elif force_off:
                ha_api.set_onoff(entity, False)
        elif action == "aus":
            if active:
                ha_api.set_onoff(entity, False)
            elif force_off:
                ha_api.set_onoff(entity, True)
        elif action == "option":
            target = rule.get("option_urlaub") if active else rule.get("option_normal")
            if active:
                if target:
                    ha_api.select_option(entity, target)
            elif force_off and target:
                ha_api.select_option(entity, target)


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
    """Genau zu relevanten Zeitpunkten neu berechnen:
    - täglich um Mitternacht (Datumswechsel)
    - zur start_time / end_time von heutigen Zeiträumen
    """
    last_day = date.today()
    while True:
        try:
            urlaube = store.load_urlaube()
            wakeup = logic.next_wakeup(urlaube)
            now = datetime.now()
            midnight = datetime.combine(date.today() + timedelta(days=1), dt_time(0, 0, 5))
            next_tick = min(wakeup, midnight) if wakeup else midnight
            sleep_secs = max(10, (next_tick - now).total_seconds())
            _LOGGER.info(
                "Scheduler: nächster Weckzeitpunkt %s (in %.0f s)",
                next_tick.strftime("%d.%m. %H:%M"), sleep_secs,
            )
            time_module.sleep(sleep_secs)
            if date.today() != last_day:
                last_day = date.today()
                _LOGGER.info("Datumswechsel – Zustände werden neu berechnet")
            else:
                _LOGGER.info("Uhrzeit-Trigger %s – Zustände werden neu berechnet",
                             next_tick.strftime("%H:%M"))
            publish_now(force_off=True)
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

def main() -> None:
    global publisher  # noqa: PLW0603

    # Startup-Diagnose
    _LOGGER.info("Urlaubsplaner v%s startet", VERSION)
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
