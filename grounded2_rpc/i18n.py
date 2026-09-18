"""Textes de la presence (fr / en). Les noms de zones viennent de zones.json dans la langue du jeu."""

from __future__ import annotations

STRINGS = {
    "fr": {
        "menu": "Dans les menus",
        "last_world": "Dernière partie : {world} · Jour {day}",
        "last_world_no_name": "Dernière partie : jour {day}",
        "no_save": "Aucune sauvegarde trouvée",
        "day": "Jour {day}",
        "world_day": "{world} · Jour {day}",
        "zone": "📍 {zone}",
        "zone_clock": "📍 {zone} · {clock}",
        "assumed": "dernière sauvegarde connue",
        "tooltip": "Grounded 2 · Jour {day}, {time} · sauvegarde {save_type} à {saved_at}",
        "tooltip_assumed": "Grounded 2 · Jour {day}, {time} · {assumed} ({saved_at})",
        "tooltip_menu": "Grounded 2 {version}",
        "tooltip_live": "Grounded 2 · Jour {day}, {time} · en direct (mod UE4SS)",
        "last_save": "dernière sauvegarde à {saved_at}",
        "period_morning": "Matin 🌅",
        "period_day": "Journée ☀️",
        "period_evening": "Soir 🌇",
        "period_night": "Nuit 🌙",
        "kind_surface": "En surface",
        "kind_underground": "Sous terre",
        "kind_outpost": "Avant-poste",
        "kind_lab": "Installation",
        "save_manual": "manuelle",
        "save_quicksave": "rapide",
        "save_autosave": "auto",
        "save_logout": "de déconnexion",
        "players": "{n} joueur(s)",
        "background": "⏸ En arrière-plan",
    },
    "en": {
        "menu": "In the menus",
        "last_world": "Last played: {world} · Day {day}",
        "last_world_no_name": "Last played: day {day}",
        "no_save": "No save found",
        "day": "Day {day}",
        "world_day": "{world} · Day {day}",
        "zone": "📍 {zone}",
        "zone_clock": "📍 {zone} · {clock}",
        "assumed": "last known save",
        "tooltip": "Grounded 2 · Day {day}, {time} · {save_type} save at {saved_at}",
        "tooltip_assumed": "Grounded 2 · Day {day}, {time} · {assumed} ({saved_at})",
        "tooltip_menu": "Grounded 2 {version}",
        "tooltip_live": "Grounded 2 · Day {day}, {time} · live (UE4SS mod)",
        "last_save": "last save at {saved_at}",
        "period_morning": "Morning 🌅",
        "period_day": "Daytime ☀️",
        "period_evening": "Evening 🌇",
        "period_night": "Night 🌙",
        "kind_surface": "On the surface",
        "kind_underground": "Underground",
        "kind_outpost": "Ranger outpost",
        "kind_lab": "Facility",
        "save_manual": "manual",
        "save_quicksave": "quick",
        "save_autosave": "auto",
        "save_logout": "logout",
        "players": "{n} player(s)",
        "background": "⏸ In the background",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang) or STRINGS["en"]
    text = table.get(key) or STRINGS["en"].get(key) or key
    return text.format(**kwargs) if kwargs else text


# Seuils du CalendarComponent du jeu : DaytimeStartHour 6, MorningEndHour 10,
# EveningStartHour 17, DaytimeEndHour 20.
def period_key(hour: int) -> str:
    if 6 <= hour < 10:
        return "period_morning"
    if 10 <= hour < 17:
        return "period_day"
    if 17 <= hour < 20:
        return "period_evening"
    return "period_night"


_PERIOD_BY_NAME = {"morning": "period_morning", "day": "period_day", "evening": "period_evening", "night": "period_night"}


def period_key_from_name(name: str, hour: int) -> str:
    """Période d'après l'enum ETimeOfDay du jeu (Morning/Day/Evening/Night), sinon d'après l'heure."""
    return _PERIOD_BY_NAME.get((name or "").strip().lower()) or period_key(hour)
