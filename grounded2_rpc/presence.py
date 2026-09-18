"""Construit l'activité Discord à partir de l'état du jeu, du mod temps réel et des sauvegardes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .game import GameProcess
from .i18n import period_key, period_key_from_name, t
from .live import LiveState
from .saves import SaveInfo
from .zones import zone_kind, zone_name

# Une sauvegarde peut être horodatée légèrement avant l'heure de lancement
# mesurée (horloges différentes) : marge de tolérance en secondes.
CLOCK_SLACK = 90
MAX_PLAYERS = 4


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
    status: str                       # "not_running" | "menu" | "in_world" | "assumed" | "live"
    save: Optional[SaveInfo] = None
    activity: Optional[dict] = None

    def summary(self) -> str:
        if self.activity is None:
            return self.status
        return f"{self.status}: {self.activity.get('details', '')} | {self.activity.get('state', '')}"


def build_presence(config: dict, lang: str, process: Optional[GameProcess], saves: List[SaveInfo],
                   foreground: bool = True, now: Optional[float] = None,
                   live: Optional[LiveState] = None) -> PresenceState:
    """``live`` (mod UE4SS) a priorité sur les sauvegardes quand il est présent et à jour."""
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

    save: Optional[SaveInfo]
    if live is not None and live.complete:
        status, save = "live", latest
    elif live is not None and not live.in_world:
        status, save = "menu", None
    elif session_saves:
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

    show_world = config.get("show_world_name", True)
    saved_at = datetime.fromtimestamp(save.header.save_timestamp).strftime("%H:%M") if save else ""
    if status == "live":
        assert live is not None
        day, hour, minute, zone_row = live.day, live.hour, live.minute, live.zone_row
        # nom du monde : celui du mod, sinon celui de la dernière sauvegarde
        world = (live.world_name or (save.header.world_name if save else "")) if show_world else ""
        tooltip = t(lang, "tooltip_live", day=day, time=live.clock())
        if save:
            tooltip += f" · {t(lang, 'last_save', saved_at=saved_at)}"
    else:
        assert save is not None
        header = save.header
        day, hour, minute, zone_row = header.day, header.hour, header.minute, header.zone_row
        world = header.world_name if show_world else ""
        if status == "assumed":
            tooltip = t(lang, "tooltip_assumed", day=day, time=header.clock(), assumed=t(lang, "assumed"), saved_at=saved_at)
        else:
            tooltip = t(lang, "tooltip", day=day, time=header.clock(), save_type=t(lang, f"save_{header.save_type_name}"), saved_at=saved_at)

    details = t(lang, "world_day", world=world, day=day) if world else t(lang, "day", day=day)
    zone = zone_name(zone_row, lang) if zone_row else ""
    clock_mode = config.get("clock_mode", "period")
    exact = f"{hour:02d}:{minute:02d}"
    period = period_key_from_name(live.time_of_day_name, hour) if status == "live" else period_key(hour)
    clock = ""
    if clock_mode == "exact":
        clock = exact
    elif clock_mode == "period":
        clock = t(lang, period)
    elif clock_mode == "both":
        clock = f"{exact} {t(lang, period)}"
    if zone and clock:
        state = t(lang, "zone_clock", zone=zone, clock=clock)
    elif zone:
        state = t(lang, "zone", zone=zone)
    else:
        state = clock or t(lang, "menu")
    if not foreground and config.get("show_background_state", False):
        state = f"{state} · {t(lang, 'background')}"

    kind = zone_kind(zone_row) if zone_row else "surface"
    activity["details"] = _truncate(details)
    activity["state"] = _truncate(state)
    activity["assets"]["large_image"] = _image(config, "logo")
    activity["assets"]["large_text"] = _truncate(tooltip)
    small = _image(config, f"zone_{kind}")
    if small:
        activity["assets"]["small_image"] = small
        activity["assets"]["small_text"] = _truncate(f"{t(lang, f'kind_{kind}')} · {zone}" if zone else t(lang, f"kind_{kind}"))

    party_id = save.header.world_id.lower() if save else "grounded2"
    if status == "live" and live.world_id:
        party_id = live.world_id.lower()
    if status == "live" and config.get("party_from_live", True):
        players = live.players or 0
        if players >= 2:
            activity["party"] = {"id": party_id, "size": [min(players, MAX_PLAYERS), MAX_PLAYERS]}
    elif status != "live":
        party_mode = config.get("party_from_header", "off")
        if party_mode in ("flag3", "slot"):
            header = save.header
            value = header.flags[3] if (party_mode == "flag3" and len(header.flags) == 4) else header.slot_index
            if 1 <= value <= MAX_PLAYERS:
                activity["party"] = {"id": party_id, "size": [int(value), MAX_PLAYERS]}

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
