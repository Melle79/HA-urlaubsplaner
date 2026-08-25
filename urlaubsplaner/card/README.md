# Urlaubsplaner Card

Quelle der Lovelace-Karte. Sie wird **mit dem Add-on ausgeliefert**: Beim Start kopiert
`backend/cardsync.py` die Datei nach `www/` der Home-Assistant-Konfiguration und trägt sie
als Lovelace-Ressource `/local/urlaubsplaner-card.js?v=<Hash>` ein.

Der Hash am Ende der URL stammt aus dem Dateiinhalt. Ändert sich die Karte, ändert sich der
Hash, und die Ressource wird aktualisiert – der Browser lädt dann die neue Fassung, statt die
alte aus dem Cache zu nehmen.

Bis Add-on-Version 1.6.7 lag die Karte in einem eigenen Repository
([Melle79/HA-urlaubsplaner-card](https://github.com/Melle79/HA-urlaubsplaner-card), zuletzt
v1.0.8) und wurde über HACS installiert. Seit 1.7.0 ist dieses Verzeichnis die einzige Quelle.

Eine Datei, kein Build-Schritt: Änderungen gehen direkt in `urlaubsplaner-card.js`. Dabei
`CARD_VERSION` oben in der Datei mitziehen – die Zahl steht in der Browser-Konsole und hilft
beim Nachvollziehen, welche Fassung geladen wurde.
