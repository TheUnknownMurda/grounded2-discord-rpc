"""Construit l'activité Discord à partir de l'état du jeu et des sauvegardes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .game import GameProcess
from .i18n import period_key, t
from .saves import SaveInfo
from .zones import zone_kind, zone_name

# Une sauvegarde peut être horodatée légèrement avant l'heure de lancement
# mesurée (horloges différentes) : marge de tolérance en secondes.
CLOCK_SLACK = 90


def _truncate(text: str, limit: int = 128) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _image(config: dict, key: str) -> Optional[str]:
    value = (config.get("images") or {}).get(key)
    return value or None


@dataclass
class PresenceState:
    status: str                       # "not_running" | "menu" | "in_world" | "assumed"
    save: Optional[SaveInfo] = None
    activity: Optional[dict] = None

    def summary(self) -> str:
        if self.activity is None:
            return self.status
        return f"{self.status}: {self.activity.get('details', '')} | {self.activity.get('state', '')}"


def build_presence(config: dict, lang: str, process: Optional[GameProcess], saves: List[SaveInfo],
                   foreground: bool = True, now: Optional[float] = None) -> PresenceState:
    now = now or time.time()
    if process is None:
        return PresenceState("not_running")

    latest = saves[0] if saves else None
    session_saves = [s for s in saves if s.timestamp >= process.start_time - CLOCK_SLACK]
    assume_after = float(config.get("assume_in_world_after_minutes", 2)) * 60
    activity: dict = {
        "timestamps": {"start": int(process.start_time)},
        "assets": {},
    }
    buttons = [b for b in (config.get("buttons") or []) if b.get("label") and b.get("url")][:2]
    if buttons:
        activity["buttons"] = [{"label": _truncate(b["label"], 32), "url": b["url"]} for b in buttons]

    if session_saves:
        status, save = "in_world", session_saves[0]
    elif latest and assume_after >= 0 and now - process.start_time >= assume_after:
        status, save = "assumed", latest
    else:
        status, save = "menu", None

    if status == "menu":
        activity["details"] = t(lang, "menu")
        if latest:
            world = latest.header.world_name if config.get("show_world_name", True) else ""
            key = "last_world" if world else "last_world_no_name"
            activity["state"] = _truncate(t(lang, key, world=world, day=latest.header.day))
        else:
            activity["state"] = t(lang, "no_save")
        version = config.get("game_version_label") or ""
        activity["assets"]["large_image"] = _image(config, "menu") or _image(config, "logo")
        activity["assets"]["large_text"] = _truncate(t(lang, "tooltip_menu", version=version)).strip()
        _finalize(activity)
        return PresenceState(status, None, activity)

    header = save.header
    world = header.world_name if config.get("show_world_name", True) else ""
    details = t(lang, "world_day", world=world, day=header.day) if world else t(lang, "day", day=header.day)

    zone = zone_name(header.zone_row, lang) if header.zone_row else ""
    clock_mode = config.get("clock_mode", "period")
    clock = ""
    if clock_mode == "exact":
        clock = header.clock()
    elif clock_mode == "period":
        clock = t(lang, period_key(header.hour))
    elif clock_mode == "both":
        clock = f"{header.clock()} {t(lang, period_key(header.hour))}"
    if zone and clock:
        state = t(lang, "zone_clock", zone=zone, clock=clock)
    elif zone:
        state = t(lang, "zone", zone=zone)
    else:
        state = clock or t(lang, "menu")
    if not foreground and config.get("show_background_state", False):
        state = f"{state} · {t(lang, 'background')}"

    saved_at = datetime.fromtimestamp(header.save_timestamp).strftime("%H:%M")
    if status == "assumed":
        tooltip = t(lang, "tooltip_assumed", day=header.day, time=header.clock(), assumed=t(lang, "assumed"), saved_at=saved_at)
    else:
        tooltip = t(lang, "tooltip", day=header.day, time=header.clock(), save_type=t(lang, f"save_{header.save_type_name}"), saved_at=saved_at)

    kind = zone_kind(header.zone_row) if header.zone_row else "surface"
    activity["details"] = _truncate(details)
    activity["state"] = _truncate(state)
    activity["assets"]["large_image"] = _image(config, "logo")
    activity["assets"]["large_text"] = _truncate(tooltip)
    small = _image(config, f"zone_{kind}")
    if small:
        activity["assets"]["small_image"] = small
        activity["assets"]["small_text"] = _truncate(f"{t(lang, f'kind_{kind}')} · {zone}" if zone else t(lang, f"kind_{kind}"))

    party_mode = config.get("party_from_header", "off")
    if party_mode in ("flag3", "slot"):
        value = header.flags[3] if (party_mode == "flag3" and len(header.flags) == 4) else header.slot_index
        if 1 <= value <= 4:
            activity["party"] = {"id": header.world_id.lower(), "size": [int(value), 4]}

    _finalize(activity)
    return PresenceState(status, save, activity)


def _finalize(activity: dict) -> None:
    """Retire les champs vides pour respecter le schéma Discord."""
    assets = activity.get("assets") or {}
    for key in list(assets):
        if not assets[key]:
            del assets[key]
    if not assets:
        activity.pop("assets", None)
    for key in ("details", "state"):
        value = activity.get(key)
        if value is not None and len(value) < 2:
            activity[key] = value + " ·"
