# Changelog

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
