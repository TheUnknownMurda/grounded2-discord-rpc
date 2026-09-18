"""Source « temps réel » : ``live.json`` écrit par le mod UE4SS (dossier ``mod/Grounded2RPC``).

Le mod réécrit le fichier toutes les 2 s (ou toutes les 10 s sans changement). S'il est
absent, illisible ou plus vieux que ``stale_seconds``, on retombe sur les sauvegardes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

DEFAULT_PATHS = [
    "%LOCALAPPDATA%/Grounded2RPC/live.json",
    # au cas où le conteneur Game Pass redirigerait les écritures de l'application
    "%LOCALAPPDATA%/Packages/Microsoft.OE-Augusta_8wekyb3d8bbwe/LocalCache/Local/Grounded2RPC/live.json",
]
DEFAULT_STALE_SECONDS = 30
# Un fichier en cours de réécriture peut manquer ou être tronqué pendant quelques ms :
# on garde la dernière valeur valide pendant ce délai.
REWRITE_GRACE = 5


class LiveError(ValueError):
    """Le fichier ne contient pas un état valide."""


@dataclass
class LiveState:
    ts: float                        # os.time() côté mod (epoch, secondes)
    in_world: bool
    day: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    zone_row: str = ""
    players: Optional[int] = None
    party_members: Optional[int] = None
    host: Optional[bool] = None
    difficulty: Optional[int] = None
    game_mode: Optional[int] = None
    time_of_day: Optional[int] = None
    time_of_day_name: str = ""       # Morning / Day / Evening / Night (enum ETimeOfDay du jeu)
    difficulty_name: str = ""        # Mild / Medium / Whoa (enum EGameDifficulty)
    game_mode_name: str = ""
    world_name: str = ""             # PlaythroughName
    world_id: str = ""               # PlaythroughGuid, même écriture que world_id du header
    loading: Optional[bool] = None
    cutscene: Optional[bool] = None
    mod_version: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """Assez d'infos pour afficher une partie (jour + horloge)."""
        return self.in_world and None not in (self.day, self.hour, self.minute)

    def clock(self) -> str:
        return f"{self.hour or 0:02d}:{self.minute or 0:02d}"

    def age(self, now: Optional[float] = None) -> float:
        return (now or time.time()) - self.ts


def _opt_int(value) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _opt_bool(value) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def parse_live(text: str) -> LiveState:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LiveError(f"JSON invalide : {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("ts"), (int, float)):
        raise LiveError("champ ts manquant")
    return LiveState(
        ts=float(data["ts"]),
        in_world=bool(data.get("in_world", False)),
        day=_opt_int(data.get("day")),
        hour=_opt_int(data.get("hour")),
        minute=_opt_int(data.get("minute")),
        zone_row=str(data.get("zone_row") or ""),
        players=_opt_int(data.get("players")),
        party_members=_opt_int(data.get("party_members")),
        host=_opt_bool(data.get("host")),
        difficulty=_opt_int(data.get("difficulty")),
        game_mode=_opt_int(data.get("game_mode")),
        time_of_day=_opt_int(data.get("time_of_day")),
        time_of_day_name=str(data.get("time_of_day_name") or ""),
        difficulty_name=str(data.get("difficulty_name") or ""),
        game_mode_name=str(data.get("game_mode_name") or ""),
        world_name=str(data.get("world_name") or ""),
        world_id=str(data.get("world_id") or ""),
        loading=_opt_bool(data.get("loading")),
        cutscene=_opt_bool(data.get("cutscene")),
        mod_version=str(data.get("mod") or ""),
        raw=data,
    )


class LiveReader:
    def __init__(self, paths: Optional[List[str]] = None, stale_seconds: float = DEFAULT_STALE_SECONDS):
        self.paths = [os.path.expandvars(p) for p in (paths or DEFAULT_PATHS)]
        self.stale_seconds = float(stale_seconds)
        self._last: Optional[LiveState] = None
        self._last_read_at = 0.0
        self._last_error = ""

    @property
    def path(self) -> str:
        """Premier chemin candidat (pour les messages)."""
        return self.paths[0] if self.paths else ""

    def _read_file(self) -> Optional[LiveState]:
        for path in self.paths:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            try:
                return parse_live(text)
            except LiveError as exc:
                if str(exc) != self._last_error:
                    self._last_error = str(exc)
                    log.debug("live.json illisible (%s), nouvel essai plus tard", exc)
                return None
        return None

    def read(self, now: Optional[float] = None) -> Optional[LiveState]:
        """État courant du mod, ou None si absent / périmé."""
        now = now or time.time()
        state = self._read_file()
        if state is not None:
            self._last, self._last_read_at = state, now
        elif self._last is not None and now - self._last_read_at > REWRITE_GRACE:
            self._last = None
        state = self._last
        if state is None:
            return None
        if state.age(now) > self.stale_seconds:
            return None
        return state
