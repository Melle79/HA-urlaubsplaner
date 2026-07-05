"""iCal Export und Import für Urlaubszeiträume."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timezone, timedelta

_LOGGER = logging.getLogger(__name__)

PRODID = "-//Urlaubsplaner//HA Add-on//DE"
CALNAME = "Urlaubsplaner"


# ---------------------------------------------------------------- Export

def export_ical(urlaube: list[dict]) -> bytes:
    """Urlaube als iCal-Datei exportieren."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        f"X-WR-CALNAME:{CALNAME}",
        "X-WR-TIMEZONE:Europe/Berlin",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for u in urlaube:
        try:
            start_d = date.fromisoformat(u["start"])
            end_d = date.fromisoformat(u["end"])
        except (KeyError, ValueError):
            continue

        label = u.get("label") or "Urlaub"
        uid = u.get("id", uuid.uuid4().hex) + "@urlaubsplaner"
        start_t = _parse_time(u.get("start_time"))
        end_t = _parse_time(u.get("end_time"))

        if start_t:
            dtstart = f"DTSTART;TZID=Europe/Berlin:{_fmt_dt(start_d, start_t)}"
        else:
            dtstart = f"DTSTART;VALUE=DATE:{start_d.strftime('%Y%m%d')}"

        if end_t:
            dtend = f"DTEND;TZID=Europe/Berlin:{_fmt_dt(end_d, end_t)}"
        else:
            # iCal: ganztägig endet am Tag NACH dem letzten Tag
            end_excl = end_d + timedelta(days=1)
            dtend = f"DTEND;VALUE=DATE:{end_excl.strftime('%Y%m%d')}"

        now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_utc}",
            dtstart,
            dtend,
            f"SUMMARY:{_escape(label)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------- Import

def import_ical(data: bytes) -> tuple[list[dict], list[str]]:
    """iCal-Datei parsen und Urlaube extrahieren.

    Rückgabe: (urlaube, warnungen)
    Urlaube haben die gleiche Struktur wie store.add_urlaub erwartet.
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as err:
        return [], [f"Datei konnte nicht gelesen werden: {err}"]

    urlaube: list[dict] = []
    warnings: list[str] = []

    # Einfacher Parser ohne externe Bibliothek (icalendar nicht im Container)
    events = _parse_vevents(text)
    for ev in events:
        try:
            result = _parse_event(ev)
            if result:
                urlaube.append(result)
        except Exception as err:
            warnings.append(f"Event übersprungen: {err}")

    return urlaube, warnings


def _parse_vevents(text: str) -> list[dict[str, str]]:
    """VEVENT-Blöcke aus iCal-Text extrahieren."""
    # Zeilenfortsetzungen zusammenführen (RFC 5545)
    text = text.replace("\r\n ", "").replace("\r\n\t", "")
    text = text.replace("\n ", "").replace("\n\t", "")

    events: list[dict[str, str]] = []
    in_event = False
    current: dict[str, str] = {}

    for line in text.splitlines():
        line = line.strip()
        if line.upper() == "BEGIN:VEVENT":
            in_event = True
            current = {}
        elif line.upper() == "END:VEVENT":
            if in_event:
                events.append(current)
            in_event = False
        elif in_event and ":" in line:
            # Key kann Parameter haben: DTSTART;VALUE=DATE:20260801
            key_full, _, value = line.partition(":")
            key_base = key_full.split(";")[0].upper()
            current[key_full.upper()] = value
            current[key_base] = value  # auch ohne Parameter speichern

    return events


def _parse_event(ev: dict[str, str]) -> dict | None:
    """Ein VEVENT in ein Urlaubsdict umwandeln."""
    summary = _unescape(ev.get("SUMMARY", "").strip()) or "Urlaub"

    # DTSTART / DTEND finden (mit oder ohne Parameter)
    dtstart_raw = _find_param(ev, "DTSTART")
    dtend_raw = _find_param(ev, "DTEND")

    if not dtstart_raw:
        return None

    start_d, start_t = _parse_ical_dt(dtstart_raw, ev)
    if dtend_raw:
        end_d, end_t = _parse_ical_dt(dtend_raw, ev)
        # iCal: ganztägiges DTEND ist exklusiv -> einen Tag zurück
        if end_t is None and end_d:
            end_d = end_d - timedelta(days=1)
    else:
        end_d, end_t = start_d, None

    if not start_d or not end_d:
        return None
    if end_d < start_d:
        end_d = start_d

    return {
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "label": summary[:60],
        "start_time": start_t.strftime("%H:%M") if start_t else "",
        "end_time": end_t.strftime("%H:%M") if end_t else "",
    }


def _find_param(ev: dict, key: str) -> str | None:
    """Wert für einen Key suchen, auch mit Parametern (DTSTART;TZID=...)."""
    # Erst exakten Key, dann mit Parametern
    if key in ev:
        return ev[key]
    for k, v in ev.items():
        if k.startswith(key + ";"):
            return v
    return None


def _parse_ical_dt(value: str, ev: dict) -> tuple[date | None, time | None]:
    """iCal Datum/Zeit parsen, Zeitzonen-Konvertierung nach lokal."""
    value = value.strip()

    # Ganztägig: YYYYMMDD
    if len(value) == 8 and value.isdigit():
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8])), None
        except ValueError:
            return None, None

    # Mit Uhrzeit: YYYYMMDDTHHMMSS oder YYYYMMDDTHHMMSSZ
    if "T" in value:
        date_part, _, time_part = value.partition("T")
        try:
            d = date(int(date_part[:4]), int(date_part[4:6]), int(date_part[6:8]))
            h = int(time_part[0:2])
            m = int(time_part[2:4])
            t = time(h, m)

            # UTC -> lokale Zeit
            if value.endswith("Z"):
                dt_utc = datetime.combine(d, t)
                try:
                    from zoneinfo import ZoneInfo
                    import time as time_mod
                    # Lokale Zeitzone aus Systemkonfiguration
                    local_tz_name = None
                    try:
                        import subprocess
                        result = subprocess.run(["cat", "/etc/timezone"], capture_output=True, text=True, timeout=2)
                        local_tz_name = result.stdout.strip() or None
                    except Exception:
                        pass
                    if not local_tz_name:
                        # Fallback: tm_gmtoff aus localtime
                        lt = time_mod.localtime(dt_utc.timestamp())
                        offset_sec = lt.tm_gmtoff
                    else:
                        tz = ZoneInfo(local_tz_name)
                        dt_local = dt_utc.replace(tzinfo=timezone.utc).astimezone(tz)
                        d = dt_local.date()
                        t = dt_local.time().replace(second=0, microsecond=0)
                        d = d  # bereits gesetzt
                except Exception:
                    # Letzter Fallback: Monat-basiert (CEST März-Okt, CET Rest)
                    offset_sec = 7200 if 3 <= d.month <= 10 else 3600
                else:
                    if 'offset_sec' in dir():
                        dt = dt_utc + timedelta(seconds=offset_sec)
                        d, t = dt.date(), dt.time().replace(second=0, microsecond=0)

            return d, t
        except (ValueError, IndexError):
            return None, None

    return None, None


def _fmt_dt(d: date, t: time) -> str:
    return f"{d.strftime('%Y%m%d')}T{t.strftime('%H%M%S')}"


def _parse_time(t: str | None) -> time | None:
    if not t:
        return None
    try:
        h, m = t.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _unescape(s: str) -> str:
    return s.replace("\\,", ",").replace("\\;", ";").replace("\\n", "\n").replace("\\\\", "\\")
