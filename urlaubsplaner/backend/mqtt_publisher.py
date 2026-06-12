"""MQTT Discovery: legt das Urlaubsplaner-Gerät mit Entitäten in Home Assistant an.

Zusätzlich wird ein Command-Topic abonniert, über das die Lovelace-Card
(per `mqtt.publish`-Service) Urlaube anlegen, bearbeiten und löschen kann.
"""
from __future__ import annotations

import json
import logging
import threading

import paho.mqtt.client as mqtt

from version import VERSION

_LOGGER = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
BASE_TOPIC = "urlaubsplaner"
AVAILABILITY_TOPIC = f"{BASE_TOPIC}/availability"
COMMAND_TOPIC = f"{BASE_TOPIC}/cmd"
DEVICE_ID = "urlaubsplaner"

# (component, key, anzeigename, icon)
ENTITY_DEFS = [
    ("binary_sensor", "urlaub_heute", "Urlaub heute", "mdi:beach"),
    ("binary_sensor", "urlaub_morgen", "Urlaub morgen", "mdi:beach"),
    ("sensor", "naechster_urlaub", "Nächster Urlaub", "mdi:airplane-takeoff"),
]


def entity_list() -> list[dict]:
    """Entity-IDs für die Anzeige in der UI."""
    return [
        {"entity_id": f"{component}.{key}", "name": name}
        for component, key, name, _icon in ENTITY_DEFS
    ]


class Publisher:
    """Verwaltet die MQTT-Verbindung, Discovery, Zustände und Commands."""

    def __init__(self, host: str, port: int, username: str | None, password: str | None):
        self.connected = threading.Event()
        self.on_ready = None  # Callback nach jedem (Re-)Connect
        self.on_command = None  # Callback für Nachrichten auf COMMAND_TOPIC
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="urlaubsplaner"
        )
        if username:
            self._client.username_pw_set(username, password or "")
        self._client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._host = host
        self._port = port

    def start(self) -> None:
        try:
            self._client.connect_async(self._host, self._port, keepalive=60)
            self._client.loop_start()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("MQTT-Verbindung fehlgeschlagen: %s", err)

    def stop(self) -> None:
        try:
            self._client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _publish(self, topic: str, payload: str) -> None:
        # QoS 1: paho puffert Nachrichten bis zur Verbindung und stellt sie zu
        self._client.publish(topic, payload, qos=1, retain=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            _LOGGER.info("Mit MQTT-Broker verbunden")
            client.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)
            client.subscribe(COMMAND_TOPIC, qos=1)
            self.connected.set()
            if self.on_ready is not None:
                try:
                    self.on_ready()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("Fehler beim Re-Publish nach Connect: %s", err)
        else:
            _LOGGER.error("MQTT-Verbindung abgelehnt: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        _LOGGER.warning("MQTT-Verbindung getrennt (%s)", reason_code)
        self.connected.clear()

    def _on_message(self, client, userdata, msg) -> None:
        if msg.topic != COMMAND_TOPIC or self.on_command is None:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            _LOGGER.warning("Ungültiges Command-Payload: %s", err)
            return
        try:
            self.on_command(payload)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Fehler bei Command-Verarbeitung: %s", err)

    # ---------- Discovery ----------

    def publish_discovery(self) -> None:
        device = {
            "identifiers": [DEVICE_ID],
            "name": "Urlaubsplaner",
            "manufacturer": "Urlaubsplaner Add-on",
            "model": "Urlaubszeiträume",
            "sw_version": VERSION,
        }
        for component, key, name, icon in ENTITY_DEFS:
            config_topic = f"{DISCOVERY_PREFIX}/{component}/{DEVICE_ID}/{key}/config"
            payload = {
                "name": name,
                "unique_id": f"{DEVICE_ID}_{key}",
                # object_id ist seit HA 2025.10 deprecated, ab 2026.4 entfernt
                "default_entity_id": f"{component}.{key}",
                "state_topic": f"{BASE_TOPIC}/{key}/state",
                "json_attributes_topic": f"{BASE_TOPIC}/{key}/attributes",
                "availability_topic": AVAILABILITY_TOPIC,
                "icon": icon,
                "device": device,
            }
            self._publish(config_topic, json.dumps(payload))
        _LOGGER.info("Discovery veröffentlicht")

    def publish_states(self, states: dict) -> None:
        for key, value in states.items():
            self._publish(f"{BASE_TOPIC}/{key}/state", value["state"])
            self._publish(
                f"{BASE_TOPIC}/{key}/attributes",
                json.dumps(value["attributes"], ensure_ascii=False),
            )

    def remove_all(self) -> None:
        """Discovery- und State-Topics löschen (leere retained Payloads)."""
        for component, key, _name, _icon in ENTITY_DEFS:
            self._publish(f"{DISCOVERY_PREFIX}/{component}/{DEVICE_ID}/{key}/config", "")
            self._publish(f"{BASE_TOPIC}/{key}/state", "")
            self._publish(f"{BASE_TOPIC}/{key}/attributes", "")
        _LOGGER.info("Alle Entitäten aus MQTT entfernt")
