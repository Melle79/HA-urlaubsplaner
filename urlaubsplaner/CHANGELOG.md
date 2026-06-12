# Changelog

## 1.0.0

- Erste Version
- Web-UI (Ingress) zum Anlegen, Bearbeiten und Löschen mehrerer Urlaubszeiträume
- Entitäten via MQTT Discovery: `binary_sensor.urlaub_heute`, `binary_sensor.urlaub_morgen`, `sensor.naechster_urlaub`
- Command-Topic `urlaubsplaner/cmd` für die Urlaubsplaner Card
- Neuberechnung bei jeder Änderung und beim Datumswechsel um Mitternacht
