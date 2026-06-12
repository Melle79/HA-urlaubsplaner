"""Zustandsberechnung für die Urlaubsplaner-Entitäten."""
from __future__ import annotations

from datetime import date, timedelta


def _fmt(d: date) -> str:
    return d.isoformat()


def _period_for(day: date, urlaube: list[dict]) -> dict | None:
    """Ersten Zeitraum liefern, der den Tag enthält."""
    for u in urlaube:
        try:
            start = date.fromisoformat(u["start"])
            end = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue
        if start <= day <= end:
            return u
    return None


def _next_period(today: date, urlaube: list[dict]) -> dict | None:
    """Nächsten Zeitraum liefern (laufend oder zukünftig), nach Beginn sortiert."""
    candidates = []
    for u in urlaube:
        try:
            start = date.fromisoformat(u["start"])
            end = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue
        if end >= today:
            candidates.append((start, end, u))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2]


def _day_state(day: date, urlaube: list[dict]) -> dict:
    period = _period_for(day, urlaube)
    attrs = {"datum": _fmt(day)}
    if period:
        start = date.fromisoformat(period["start"])
        end = date.fromisoformat(period["end"])
        attrs.update(
            {
                "bezeichnung": period.get("label", "Urlaub"),
                "beginn": period["start"],
                "ende": period["end"],
                "dauer_tage": (end - start).days + 1,
                "rest_tage": (end - day).days,
            }
        )
    return {"state": "ON" if period else "OFF", "attributes": attrs}


def _preview(today: date, urlaube: list[dict], days: int = 14) -> list[dict]:
    """Tagesvorschau für die Card (analog zum `vorschau`-Attribut des Ferienplaners)."""
    out = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        period = _period_for(day, urlaube)
        out.append(
            {
                "datum": _fmt(day),
                "wochentag": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][day.weekday()],
                "urlaub": period is not None,
                "wochenende": day.weekday() >= 5,
            }
        )
    return out


def build_states(urlaube: list[dict]) -> dict:
    """Alle Entitätszustände berechnen.

    Rückgabe: key -> {"state": str, "attributes": dict}
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)

    nxt = _next_period(today, urlaube)
    nxt_attrs: dict = {"urlaube": urlaube, "vorschau": _preview(today, urlaube), "anzahl": len(urlaube)}
    if nxt:
        start = date.fromisoformat(nxt["start"])
        end = date.fromisoformat(nxt["end"])
        running = start <= today
        nxt_attrs.update(
            {
                "bezeichnung": nxt.get("label", "Urlaub"),
                "beginn": nxt["start"],
                "ende": nxt["end"],
                "in_tagen": 0 if running else (start - today).days,
                "dauer_tage": (end - start).days + 1,
                "aktuell_urlaub": running,
            }
        )
        nxt_state = "Läuft" if running else nxt["start"]
    else:
        nxt_attrs.update({"aktuell_urlaub": False})
        nxt_state = "Keiner geplant"

    return {
        "urlaub_heute": _day_state(today, urlaube),
        "urlaub_morgen": _day_state(tomorrow, urlaube),
        "naechster_urlaub": {"state": nxt_state, "attributes": nxt_attrs},
    }
