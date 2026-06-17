"""Zustandsberechnung für die Urlaubsplaner-Entitäten (mit optionaler Uhrzeit)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


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


def _is_active(u: dict, dt: datetime) -> bool:
    """Prüft ob ein Zeitraum zum Zeitpunkt dt aktiv ist (inkl. Uhrzeiten)."""
    try:
        start_d = date.fromisoformat(u["start"])
        end_d = date.fromisoformat(u["end"])
    except (KeyError, ValueError):
        return False
    today = dt.date()
    if not (start_d <= today <= end_d):
        return False
    now = dt.time().replace(second=0, microsecond=0)
    start_t = _parse_time(u.get("start_time"))
    end_t = _parse_time(u.get("end_time"))
    # Erster Tag: frühestens ab start_time
    if today == start_d and start_t and now < start_t:
        return False
    # Letzter Tag: spätestens bis end_time
    if today == end_d and end_t and now >= end_t:
        return False
    return True


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


def _just_ended(urlaube: list[dict], now: datetime, window_minutes: int = 60) -> dict | None:
    """Zeitraum liefern, der innerhalb der letzten `window_minutes` geendet hat."""
    for u in urlaube:
        try:
            end_d = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue
        end_t = _parse_time(u.get("end_time"))
        end_dt = datetime.combine(end_d, end_t if end_t else time(23, 59))
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

    Liefert den nächsten noch nicht erreichten start_time oder end_time
    aus allen Zeiträumen, die heute oder morgen einen solchen haben.
    """
    now = datetime.now().replace(second=0, microsecond=0)
    today = now.date()
    candidates: list[datetime] = []
    for u in urlaube:
        try:
            start_d = date.fromisoformat(u["start"])
            end_d = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue
        # Start-Zeit: relevant wenn Starttag heute oder morgen
        if u.get("start_time") and start_d >= today:
            t = _parse_time(u["start_time"])
            if t:
                dt = datetime.combine(start_d, t)
                if dt > now:
                    candidates.append(dt)
        # End-Zeit: >= now damit die Endzeit selbst als Weckpunkt gilt
        if u.get("end_time") and end_d >= today:
            t = _parse_time(u["end_time"])
            if t:
                dt = datetime.combine(end_d, t)
                if dt >= now:  # >= statt >: Endzeit selbst ist Weckpunkt
                    candidates.append(dt)
    return min(candidates) if candidates else None
