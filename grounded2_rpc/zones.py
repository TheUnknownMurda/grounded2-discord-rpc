"""Noms de zones localisés (généré depuis les fichiers du jeu, voir tools/extract_zones.py)."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Optional

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "zones.json")

# Correspondance LanguageSetting (GameUserSettings.ini) → code des noms de zones.
GAME_LANGUAGES = {
    "french": "fr",
    "english": "en",
    "german": "de",
    "spanish": "es",
    "spanishmexico": "es-MX",
    "latinamericanspanish": "es-MX",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "portuguese": "pt-BR",
    "brazilianportuguese": "pt-BR",
    "chinesesimplified": "zh-Hans",
    "simplifiedchinese": "zh-Hans",
    "chinesetraditional": "zh-Hant",
    "traditionalchinese": "zh-Hant",
}


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)["zones"]


def prettify(row: str) -> str:
    """Repli lisible pour une zone inconnue : ``Outpost_PineHill`` → ``Outpost Pine Hill``."""
    text = row.replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return text.strip() or "?"


def zone_name(row: str, lang: str = "en") -> str:
    zone = _load().get(row)
    if not zone:
        return prettify(row)
    names = zone.get("names", {})
    return names.get(lang) or names.get("en") or prettify(row)


def zone_kind(row: str) -> str:
    """``surface`` | ``underground`` | ``outpost`` | ``lab`` (sert au choix de la petite icône)."""
    zone = _load().get(row)
    if zone:
        return zone.get("kind", "surface")
    r = row.lower()
    if r.startswith("outpost_"):
        return "outpost"
    if any(k in r for k in ("anthill", "cave", "burrow", "tunnel", "underground", "abyss", "sinkhole")):
        return "underground"
    if any(k in r for k in ("lab", "facility", "station", "center")):
        return "lab"
    return "surface"


def known_zone(row: str) -> bool:
    return row in _load()


def language_from_setting(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return GAME_LANGUAGES.get(value.strip().lower().replace(" ", "").replace("_", ""))
