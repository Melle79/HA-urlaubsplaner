# Changelog

## 1.4.2

- Fix: `__import__("datetime").time` im Scheduler durch sauberen `dt_time`-Import ersetzt
- Besseres Diagnose-Logging: Scheduler zeigt nächsten Weckzeitpunkt, `_sync_helper` loggt
  jeden Schaltvorgang inkl. Auslöser und Zustand
- Fix: doppelter `select_option`-Aufruf in `_sync_helper` entfernt
- SUPERVISOR_TOKEN-Fehler wird jetzt einmalig geloggt statt pro Entität

## 1.4.0

- **Optionale Start- und Endzeit** pro Urlaubszeitraum: Abfahrtszeit (Urlaub beginnt erst dann)
  und Ankunftszeit (Urlaub endet dann) können gesetzt werden
- Uhrzeitfelder in der Web-UI (Kalender-Popup oder manuelle Eingabe HH:MM)
- `binary_sensor.urlaub_heute` und `urlaub_morgen` schalten exakt zur konfigurierten Uhrzeit
- Neuer Scheduler: wacht präzise zur Start-/Endzeit auf, nicht nur um Mitternacht
- Neue Attribute `startzeit` / `endzeit` in den Entitäten
- Validierung: Endzeit muss nach Startzeit liegen (bei gleichem Tag)

## 1.3.0

- **Entitäten-Auswahl mit Suche**: schaltbare Entitäten werden mit Friendly Name aus Home Assistant
  geladen und im Formular als durchsuchbare Liste angeboten (Freitext weiterhin möglich)
- **Optionen werden mitgeladen**: bei `input_select`/`select` erscheinen die verfügbaren Optionen
  als Dropdown (inkl. „nicht zurücksetzen“ für die Option danach)
- Aktion passt sich der Entität an: bei Selects automatisch „Option setzen“,
  bei Schaltern nur Ein/Aus wählbar
- Neue API-Route `/api/entities`

## 1.2.0

- **Mehrere mitgeschaltete Entitäten**: pro Entität eine Regel mit Auslöser (Urlaub heute / Urlaub morgen)
  und Aktion (im Urlaub einschalten / ausschalten / Option setzen)
- **Option setzen** für `input_select`/`select`: Option im Urlaub und optional eine Option für danach
- Bestehende Einzel-Einstellung aus v1.1.0 wird automatisch als Regel übernommen
- Neue API-Routen `/api/helpers` (CRUD), `/api/settings` entfernt

## 1.1.0

- Optionale Helfer-Entität: eine bestehende Entität (z. B. `input_boolean.urlaub`) wird automatisch
  synchron zu „Urlaub heute" geschaltet – ein am ersten Urlaubstag, aus nach dem letzten
- Neues Einstellungs-Panel in der Web-UI
- Add-on benötigt dafür Zugriff auf die Home-Assistant-API (`homeassistant_api: true`)

## 1.0.0

- Erste Version
- Web-UI (Ingress) zum Anlegen, Bearbeiten und Löschen mehrerer Urlaubszeiträume
- Entitäten via MQTT Discovery: `binary_sensor.urlaub_heute`, `binary_sensor.urlaub_morgen`, `sensor.naechster_urlaub`
- Command-Topic `urlaubsplaner/cmd` für die Urlaubsplaner Card
- Neuberechnung bei jeder Änderung und beim Datumswechsel um Mitternacht
