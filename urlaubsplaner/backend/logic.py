"""Zustandsberechnung für die Urlaubsplaner-Entitäten (mit optionaler Uhrzeit)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


# Wie lange nach Urlaubsende "urlaub_gerade_vorbei" auf ON bleibt
JUST_ENDED_WINDOW = 60

# Ohne eingegebene Uhrzeit gilt der ganze Tag. Intern wird daraus eine feste
# Grenze, damit "mit Uhrzeit" und "ohne Uhrzeit" überall dieselbe Rechnung
# durchlaufen und jeder Wechsel einen Weckzeitpunkt hat.
DEFAULT_START_TIME = time(0, 0)
DEFAULT_END_TIME = time(23, 59)


def _fmt(d: date) -> str:
    return d.isoformat()


def _parse_time(t: str | None) -> time | None:
    """HH:MM -> time, leer/None -> None."""
    if not t:
        return None
    try:
        h, m = t.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _bounds(u: dict) -> tuple[datetime, datetime] | None:
    """Beginn und Ende eines Zeitraums als Zeitpunkte.

    Fehlt eine Uhrzeit, gilt der Tagesanfang bzw. das Tagesende. Damit ist ein
    Zeitraum immer ein durchgehendes Intervall – unabhängig davon, ob Uhrzeiten
    eingegeben wurden.
    """
    try:
        start_d = date.fromisoformat(u["start"])
        end_d = date.fromisoformat(u["end"])
    except (KeyError, ValueError):
        return None
    start_t = _parse_time(u.get("start_time")) or DEFAULT_START_TIME
    end_t = _parse_time(u.get("end_time")) or DEFAULT_END_TIME
    return datetime.combine(start_d, start_t), datetime.combine(end_d, end_t)


def _is_active(u: dict, dt: datetime) -> bool:
    """Prüft ob ein Zeitraum zum Zeitpunkt dt aktiv ist (inkl. Uhrzeiten)."""
    bounds = _bounds(u)
    if bounds is None:
        return False
    start_dt, end_dt = bounds
    now = dt.replace(second=0, microsecond=0)
    return start_dt <= now < end_dt


def _period_for_dt(dt: datetime, urlaube: list[dict]) -> dict | None:
    """Ersten aktiven Zeitraum zum Zeitpunkt dt liefern."""
    for u in urlaube:
        if _is_active(u, dt):
            return u
    return None


def _next_period(today: date, urlaube: list[dict]) -> dict | None:
    """Nächsten Zeitraum liefern (laufend oder zukünftig), nach Beginn sortiert."""
    candidates = []
    for u in urlaube:
        try:
            end_d = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue
        if end_d >= today:
            candidates.append(u)
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c.get("start", ""), c.get("start_time", ""), c.get("end", "")))
    return candidates[0]


def _preview(today: date, urlaube: list[dict], days: int = 14) -> list[dict]:
    """Tagesvorschau (ganztägig, ohne Uhrzeitauflösung – für den Strip in der Card)."""
    out = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        # Für den Strip gilt der Tag als Urlaubstag wenn er irgendwann im Zeitraum liegt
        in_urlaub = False
        for u in urlaube:
            try:
                if date.fromisoformat(u["start"]) <= day <= date.fromisoformat(u["end"]):
                    in_urlaub = True
                    break
            except (KeyError, ValueError):
                pass
        out.append({
            "datum": _fmt(day),
            "wochentag": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][day.weekday()],
            "urlaub": in_urlaub,
            "wochenende": day.weekday() >= 5,
        })
    return out


def _day_state(dt: datetime, urlaube: list[dict]) -> dict:
    period = _period_for_dt(dt, urlaube)
    attrs: dict = {"datum": _fmt(dt.date())}
    if period:
        start_d = date.fromisoformat(period["start"])
        end_d = date.fromisoformat(period["end"])
        attrs.update({
            "bezeichnung": period.get("label", "Urlaub"),
            "beginn": period["start"],
            "ende": period["end"],
            "dauer_tage": (end_d - start_d).days + 1,
            "rest_tage": (end_d - dt.date()).days,
        })
        if period.get("start_time"):
            attrs["startzeit"] = period["start_time"]
        if period.get("end_time"):
            attrs["endzeit"] = period["end_time"]
    return {"state": "ON" if period else "OFF", "attributes": attrs}


def _just_ended(urlaube: list[dict], now: datetime,
                window_minutes: int = JUST_ENDED_WINDOW) -> dict | None:
    """Zeitraum liefern, der innerhalb der letzten `window_minutes` geendet hat."""
    for u in urlaube:
        bounds = _bounds(u)
        if bounds is None:
            continue
        _, end_dt = bounds
        if timedelta(0) <= (now - end_dt) <= timedelta(minutes=window_minutes):
            return u
    return None


def build_states(urlaube: list[dict]) -> dict:
    """Alle Entitätszustände berechnen."""
    now = datetime.now().replace(second=0, microsecond=0)
    today = now.date()
    tomorrow_dt = datetime.combine(today + timedelta(days=1), time(0, 0))

    nxt = _next_period(today, urlaube)
    nxt_attrs: dict = {
        "urlaube": urlaube,
        "vorschau": _preview(today, urlaube),
        "anzahl": len(urlaube),
    }
    if nxt:
        start_d = date.fromisoformat(nxt["start"])
        end_d = date.fromisoformat(nxt["end"])
        running = _is_active(nxt, now)
        nxt_attrs.update({
            "bezeichnung": nxt.get("label", "Urlaub"),
            "beginn": nxt["start"],
            "ende": nxt["end"],
            "in_tagen": 0 if running else (start_d - today).days,
            "dauer_tage": (end_d - start_d).days + 1,
            "aktuell_urlaub": running,
        })
        if nxt.get("start_time"):
            nxt_attrs["startzeit"] = nxt["start_time"]
        if nxt.get("end_time"):
            nxt_attrs["endzeit"] = nxt["end_time"]
        nxt_state = "Läuft" if running else nxt["start"]
    else:
        nxt_attrs["aktuell_urlaub"] = False
        nxt_state = "Keiner geplant"

    # Urlaub gerade vorbei (innerhalb der letzten 60 Minuten nach Urlaubsende)
    ended = _just_ended(urlaube, now)
    vorbei_attrs: dict = {"datum": now.date().isoformat()}
    if ended:
        end_d = date.fromisoformat(ended["end"])
        end_t = _parse_time(ended.get("end_time"))
        end_dt = datetime.combine(end_d, end_t if end_t else time(23, 59))
        vorbei_attrs.update({
            "bezeichnung": ended.get("label", "Urlaub"),
            "ende": ended["end"],
            "vor_minuten": int((now - end_dt).total_seconds() / 60),
        })
        if ended.get("end_time"):
            vorbei_attrs["endzeit"] = ended["end_time"]

    return {
        "urlaub_heute": _day_state(now, urlaube),
        "urlaub_morgen": _day_state(tomorrow_dt, urlaube),
        "urlaub_gerade_vorbei": {"state": "ON" if ended else "OFF", "attributes": vorbei_attrs},
        "naechster_urlaub": {"state": nxt_state, "attributes": nxt_attrs},
    }


def next_wakeup(urlaube: list[dict]) -> datetime | None:
    """Nächsten relevanten Schaltzeitpunkt liefern (für den Scheduler).

    Das ist der nächste Zeitpunkt, an dem sich einer der Zustände tatsächlich
    ändert: Urlaubsbeginn, Urlaubsende oder das Ende des "gerade vorbei"-
    Fensters. Zeiträume ohne eingegebene Uhrzeit zählen dabei mit ihren
    Tagesgrenzen mit, damit auch sie punktgenau geschaltet werden.
    """
    now = datetime.now().replace(second=0, microsecond=0)
    candidates: list[datetime] = []
    for u in urlaube:
        bounds = _bounds(u)
        if bounds is None:
            continue
        start_dt, end_dt = bounds
        for dt in (start_dt, end_dt, end_dt + timedelta(minutes=JUST_ENDED_WINDOW)):
            if dt >= now:  # >= : der Schaltzeitpunkt selbst ist ein Weckpunkt
                candidates.append(dt)
    return min(candidates) if candidates else None
