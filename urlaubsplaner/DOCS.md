# Urlaubsplaner – Dokumentation

## Voraussetzungen

- MQTT-Broker (z. B. das **Mosquitto broker** Add-on) und die MQTT-Integration in Home Assistant.
  Die Zugangsdaten holt sich das Add-on automatisch vom Supervisor (`services: mqtt:need`).
- Home Assistant Core 2025.10 oder neuer.

## Bedienung

1. Add-on starten und das Sidebar-Panel **„Urlaub"** öffnen.
2. Bezeichnung (optional), Von- und Bis-Datum eintragen – die Datumsfelder öffnen ein Kalender-Popup,
   manuelle Eingabe ist ebenso möglich.
3. **Speichern** – die Entitäten werden sofort aktualisiert.
4. Bestehende Urlaube können über **Bearbeiten** und **Löschen** geändert werden.
   Es können beliebig viele Zeiträume parallel angelegt werden.

## Entitäten

| Entity-ID | Beschreibung |
|---|---|
| `binary_sensor.urlaub_heute` | `on`, wenn heute in einem Urlaubszeitraum liegt |
| `binary_sensor.urlaub_morgen` | `on`, wenn morgen in einem Urlaubszeitraum liegt |
| `sensor.naechster_urlaub` | Nächster (oder laufender) Urlaub; alle Zeiträume im Attribut `urlaube` |

Die Zustände werden bei jeder Änderung sowie automatisch beim Datumswechsel um Mitternacht neu berechnet.

## Entitäten mitschalten (optional)

Unter **Mitgeschaltete Entitäten** in der Web-UI können beliebig viele Regeln angelegt werden.
Jede Regel besteht aus:

- **Entity-ID** – z. B. `input_boolean.urlaub`, `switch.warmwasser` oder `input_select.hausmodus`
- **Wann** – Auslöser `Urlaub heute` oder `Urlaub morgen` (z. B. um die Anwesenheitssimulation
  schon am Vortag scharf zu schalten)
- **Aktion** – `Im Urlaub einschalten`, `Im Urlaub ausschalten` (invertiert, z. B. für eine
  Zirkulationspumpe) oder `Option setzen` für `input_select`/`select`-Entitäten:
  Option im Urlaub plus optional eine Option für danach (ohne „danach“-Option wird nach dem
  Urlaub nichts zurückgesetzt)

Geschaltet wird bei jeder Änderung, beim Add-on-Start und beim Datumswechsel um Mitternacht –
und nur, wenn der Zustand tatsächlich abweicht. Hinweis: Solange eine Regel besteht, „gehört“
die Entität dem Add-on – manuelles Umschalten wird bei der nächsten Synchronisierung wieder
überschrieben. Eine bestehende Einzel-Einstellung aus v1.1.0 wird beim ersten Start automatisch
als Regel übernommen.

## Dashboard-Karte

Die [Urlaubsplaner Card](https://github.com/Melle79/HA-urlaubsplaner-card) (HACS, Typ Dashboard) zeigt
Badges, 14-Tage-Streifen und die Urlaubsliste – inklusive Anlegen/Bearbeiten/Löschen direkt in der Karte.
Die Karte sendet Änderungen über `mqtt.publish` an das Topic `urlaubsplaner/cmd`.

## Daten

Alle Urlaube liegen als JSON unter `/data/urlaube.json` im Add-on-Container und bleiben bei Updates erhalten.
