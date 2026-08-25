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

- **Entität** – durchsuchbare Auswahl aller schaltbaren Entitäten (input_boolean, switch, light,
  fan, automation, script, climate) sowie `input_select`/`select`; alternativ kann die Entity-ID
  weiterhin frei eingetippt werden
- **Wann** – Auslöser `Urlaub heute` oder `Urlaub morgen` (z. B. um die Anwesenheitssimulation
  schon am Vortag scharf zu schalten)
- **Aktion** – `Im Urlaub einschalten`, `Im Urlaub ausschalten` (invertiert, z. B. für eine
  Zirkulationspumpe) oder `Option setzen` für `input_select`/`select`-Entitäten:
  Option im Urlaub plus optional eine Option für danach – die verfügbaren Optionen werden
  automatisch aus Home Assistant geladen und als Dropdown angeboten („nicht zurücksetzen“
  lässt die Entität nach dem Urlaub unverändert)

Geschaltet wird **nur beim Wechsel** – also wenn ein Urlaub beginnt oder endet, oder wenn die
Regel selbst geändert wird. Das Add-on wacht zwar öfter auf (Mitternacht, eingetragene Uhrzeiten,
Benachrichtigungszeit), schreibt dabei aber nichts nach Home Assistant, solange sich nichts
geändert hat. Wer den Zustand zwischendurch von Hand umstellt, behält ihn deshalb bis zum
nächsten echten Urlaubswechsel; „Jetzt synchronisieren“ in der Web-UI setzt ihn sofort zurück.
Eine bestehende Einzel-Einstellung aus v1.1.0 wird beim ersten Start automatisch als Regel
übernommen.

## Dashboard-Karte

Die Karte wird **vom Add-on mitgeliefert**: Beim Start landet `urlaubsplaner-card.js` in `www/`
deiner Konfiguration und wird als Lovelace-Ressource (`/local/urlaubsplaner-card.js`) eingetragen.
Eine Installation über HACS ist nicht mehr nötig. Im Dashboard genügt dann:

```yaml
type: custom:urlaubsplaner-card
title: Urlaub
```

Sie zeigt Badges, den 14-Tage-Streifen und die Urlaubsliste – inklusive Anlegen, Bearbeiten und
Löschen direkt in der Karte. Änderungen gehen über `mqtt.publish` an das Topic `urlaubsplaner/cmd`.

Ist die Karte noch aus einer anderen Quelle eingebunden (etwa HACS unter `/hacsfiles/…`), legt das
Add-on **keine** zweite Ressource an und schreibt stattdessen einen Hinweis ins Protokoll. Entferne
in dem Fall zuerst die alte Einbindung. Fehlt dem Add-on das Schreibrecht auf die Konfiguration,
wird die Karte übersprungen – das Add-on läuft normal weiter.

## Daten

Alle Urlaube liegen als JSON unter `/data/urlaube.json` im Add-on-Container und bleiben bei Updates erhalten.
