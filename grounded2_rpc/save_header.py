"""Décodage du header de sauvegarde de Grounded 2 (blob ``HeaderData``).

Le header est un petit bloc (~240 octets) écrit par le jeu avec chaque
sauvegarde. Il contient le résumé affiché dans le menu « Charger » :
nom du monde, jour et heure en jeu, zone du joueur, type de sauvegarde…

Structure observée (versions de header 18 et 20, jeu 0.1.x → 0.3.x) :

    u32     header_version
    u32     (constante, 2)
    FString game_version           ex. "0.3.0.2"
    FGuid   world_id               4 × u32 LE, affiché en hexa A B C D
    u8      save_type              0 manuelle, 1 rapide, 2 auto, 3 déconnexion
    u32     slot_index             index d'autosave (0-2) / emplacement
    i64     save_time              FDateTime UTC (ticks de 100 ns depuis l'an 1)
    u32     day, hour, minute      horloge en jeu
    FString map_name               "Augusta_Main"
    FString zone_table             "/Game/Blueprints/Table_Zones.Table_Zones"
    FString zone_row               ex. "Outpost_Snackbar"
    u8 × 4  flags                  (sens exact non confirmé, voir README)
    FString session_mode           "" ou "Solo"
    FString world_name             nom donné par le joueur
    FString (vide)
    FString host_id                identifiant plateforme de l'hôte
    FGuid   save_id
    u8      flag_bool
    u64     (0)
    u32     counter_a
    u32     (0)
    u32     counter_b
    u32     counter_c

Les FString UE sont préfixées par un i32 : longueur > 0 → UTF-8 (nul inclus),
longueur < 0 → UTF-16-LE de -longueur caractères.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

SAVE_TYPES = {0: "manual", 1: "quicksave", 2: "autosave", 3: "logout"}

_EPOCH_TICKS = datetime(1, 1, 1, tzinfo=timezone.utc)


class HeaderError(ValueError):
    """Le blob ne ressemble pas à un header de sauvegarde Grounded 2."""


class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def _take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.buf):
            raise HeaderError("header tronqué")
        value = struct.unpack_from(fmt, self.buf, self.pos)
        self.pos += size
        return value[0] if len(value) == 1 else value

    def u8(self) -> int:
        return self._take("<B")

    def u32(self) -> int:
        return self._take("<I")

    def i32(self) -> int:
        return self._take("<i")

    def i64(self) -> int:
        return self._take("<q")

    def raw(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise HeaderError("header tronqué")
        chunk = self.buf[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def fstring(self) -> str:
        length = self.i32()
        if length == 0:
            return ""
        if length < 0:
            data = self.raw(-length * 2)
            return data.decode("utf-16-le", "replace").rstrip("\0")
        if length > 4096:
            raise HeaderError("FString invalide")
        data = self.raw(length)
        return data.decode("utf-8", "replace").rstrip("\0")

    def guid(self) -> str:
        a, b, c, d = self._take("<IIII")
        return f"{a:08X}{b:08X}{c:08X}{d:08X}"


@dataclass
class SaveHeader:
    header_version: int
    game_version: str
    world_id: str
    save_type: int
    slot_index: int
    save_time: datetime
    day: int
    hour: int
    minute: int
    map_name: str = ""
    zone_table: str = ""
    zone_row: str = ""
    flags: tuple = ()
    session_mode: str = ""
    world_name: str = ""
    host_id: str = ""
    save_id: str = ""
    flag_bool: int = 0
    counter_a: int = 0
    counter_b: int = 0
    counter_c: int = 0
    partial: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def save_type_name(self) -> str:
        return SAVE_TYPES.get(self.save_type, f"type{self.save_type}")

    @property
    def save_timestamp(self) -> float:
        return self.save_time.timestamp()

    def clock(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["save_time"] = self.save_time.isoformat()
        d["save_type_name"] = self.save_type_name
        return d


def parse_header(buf: bytes) -> SaveHeader:
    """Décode un blob HeaderData. Lève HeaderError si le début n'est pas valide.

    Les champs situés après la zone sont optionnels : si le blob s'arrête
    plus tôt (nouvelle version du jeu), ``partial`` vaut True et les champs
    manquants gardent leur valeur par défaut.
    """
    r = _Reader(buf)
    version = r.u32()
    if not 10 <= version <= 200:
        raise HeaderError(f"version de header improbable: {version}")
    r.u32()  # constante (2)
    game_version = r.fstring()
    if not game_version or not game_version[0].isdigit():
        raise HeaderError("version de jeu illisible")
    world_id = r.guid()
    save_type = r.u8()
    slot_index = r.u32()
    ticks = r.i64()
    try:
        save_time = _EPOCH_TICKS + timedelta(microseconds=ticks // 10)
    except OverflowError as exc:
        raise HeaderError("date de sauvegarde invalide") from exc
    day, hour, minute = r.u32(), r.u32(), r.u32()

    header = SaveHeader(
        header_version=version,
        game_version=game_version,
        world_id=world_id,
        save_type=save_type,
        slot_index=slot_index,
        save_time=save_time,
        day=day,
        hour=hour,
        minute=minute,
    )
    try:
        header.map_name = r.fstring()
        header.zone_table = r.fstring()
        header.zone_row = r.fstring()
        header.flags = tuple(r.u8() for _ in range(4))
        header.session_mode = r.fstring()
        header.world_name = r.fstring()
        r.fstring()  # toujours vide dans les fichiers observés
        header.host_id = r.fstring()
        header.save_id = r.guid()
        header.flag_bool = r.u8()
        r.raw(8)
        header.counter_a = r.u32()
        r.u32()
        header.counter_b = r.u32()
        header.counter_c = r.u32()
    except HeaderError:
        header.partial = True
    if r.pos < len(buf):
        header.extra["trailing_bytes"] = len(buf) - r.pos
    return header


def parse_header_file(path: str) -> Optional[SaveHeader]:
    with open(path, "rb") as fh:
        data = fh.read(4096)
    return parse_header(data)
