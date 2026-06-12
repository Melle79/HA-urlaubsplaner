"""Urlaubsplaner – Flask-Backend des Home Assistant Add-ons."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date

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

def publish_now() -> None:
    """Zustände berechnen, via MQTT publizieren und Helfer-Entität schalten."""
    with _publish_lock:
        urlaube = store.load_urlaube()
        states = logic.build_states(urlaube)
        if publisher is not None:
            publisher.publish_discovery()
            publisher.publish_states(states)
        _sync_helper(states)


def _sync_helper(states: dict) -> None:
    """Optionale Helfer-Entität (z. B. input_boolean) an „Urlaub heute" angleichen."""
    entity = store.load_settings().get("helper_entity", "")
    if not entity:
        return
    on = states["urlaub_heute"]["state"] == "ON"
    ha_api.set_onoff(entity, on)


# ---------------------------------------------------------------- MQTT-Commands
# Die Lovelace-Card sendet über den HA-Service `mqtt.publish` JSON-Commands
# an `urlaubsplaner/cmd`: {"action": "add"|"update"|"delete", ...}

def handle_command(payload: dict) -> None:
    action = str(payload.get("action", "")).lower()
    try:
        if action == "add":
            entry = store.add_urlaub(
                payload.get("start"), payload.get("end"), payload.get("label", "")
            )
            _LOGGER.info("Command: Urlaub angelegt (%s)", entry["id"])
        elif action == "update":
            entry = store.update_urlaub(
                str(payload.get("id", "")),
                payload.get("start"),
                payload.get("end"),
                payload.get("label", ""),
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
    """Bei Datumswechsel Zustände neu berechnen und publizieren."""
    last_day = date.today()
    while True:
        time.sleep(60)
        try:
            if date.today() != last_day:
                last_day = date.today()
                _LOGGER.info("Datumswechsel – Zustände werden neu berechnet")
                publish_now()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Scheduler-Fehler: %s", err)


# ---------------------------------------------------------------- Routen

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


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(store.load_settings())


@app.route("/api/settings", methods=["PUT"])
def api_put_settings():
    data = request.get_json(silent=True) or {}
    try:
        settings = store.save_settings(data)
    except store.ValidationError as err:
        return jsonify({"error": str(err)}), 400
    if settings["helper_entity"] and ha_api.get_state(settings["helper_entity"]) is None:
        # Speichern trotzdem, aber Hinweis zurückgeben
        publish_now()
        return jsonify({**settings, "warning": "Entität wurde in HA nicht gefunden"})
    publish_now()
    return jsonify(settings)


@app.route("/api/urlaube", methods=["GET"])
def api_urlaube():
    return jsonify(store.load_urlaube())


@app.route("/api/urlaube", methods=["POST"])
def api_add_urlaub():
    data = request.get_json(silent=True) or {}
    try:
        entry = store.add_urlaub(data.get("start"), data.get("end"), data.get("label", ""))
    except store.ValidationError as err:
        return jsonify({"error": str(err)}), 400
    publish_now()
    return jsonify(entry), 201


@app.route("/api/urlaube/<uid>", methods=["PUT"])
def api_update_urlaub(uid: str):
    data = request.get_json(silent=True) or {}
    try:
        entry = store.update_urlaub(uid, data.get("start"), data.get("end"), data.get("label", ""))
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
