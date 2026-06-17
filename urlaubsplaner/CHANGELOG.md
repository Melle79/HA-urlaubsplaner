# Changelog

## 1.4.6

- Fix: `set_onoff` nutzt jetzt domain-spezifische Services (z. B. `input_boolean.turn_on`)
  mit Fallback auf `homeassistant.turn_on` – robuster für alle Entitätstypen
- Startup-Log zeigt ob SUPERVISOR_TOKEN vorhanden ist (HA-API erreichbar)
- Debug-Log wenn Entität bereits im gewünschten Zustand ist

## 1.4.5

- Aktions-Labels im Helfer-Formular passen sich dem Auslöser an:
  heute → „Im Urlaub ein-/ausschalten", morgen → „Am Vortag ein-/ausschalten",
  vorbei → „Nach Urlaub ein-/ausschalten"

## 1.4.4

- **Neuer Auslöser „Urlaub gerade vorbei"** in den Helfer-Regeln: schaltet Entitäten
  in den 60 Minuten nach Urlaubsende (z. B. Willkommen-zu-Hause-Automation, Hausmodus
  zurück auf „Zuhause", Heizung wieder hochfahren)
- Neue Entität `binary_sensor.urlaub_gerade_vorbei` via MQTT Discovery
  (ON für 60 Min. nach Urlaubsende, Attribute: `bezeichnung`, `ende`, `vor_minuten`)

## 1.4.3

- Fix: Helfer-Entitäten wurden nach Urlaubsende (Endzeit) nicht zurückgeschaltet
- `next_wakeup` liefert die Endzeit jetzt als Weckpunkt (`>= now` statt `> now`),
  damit der Scheduler genau zur Ankunftszeit aufwacht und die Helfer abschaltet

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
