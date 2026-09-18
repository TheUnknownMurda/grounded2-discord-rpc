"""Lecture des conteneurs de sauvegarde Xbox (« wgs », Windows Game Saves).

Les jeux installés via l'app Xbox / Game Pass stockent leurs sauvegardes dans
``%LOCALAPPDATA%\\Packages\\<paquet>\\SystemAppData\\wgs\\<xuid>_<titleid>\\`` :

* ``containers.index`` liste les conteneurs (nom logique, dossier GUID,
  numéro de fichier ``container.N``, date, taille).
* ``<GUID>/container.N`` liste les blobs du conteneur (nom logique → GUID de
  fichier). Pour Grounded 2 : ``HeaderData``, ``ScreenshotData``, ``WorldState``.
* ``<GUID>/<blobGUID>`` contient les données brutes.

Pendant qu'une sauvegarde est écrite, l'index peut référencer brièvement un
conteneur vide (taille 0) dont le fichier ``container.N`` n'existe pas encore :
les appelants doivent ignorer ces entrées et réessayer plus tard.
"""

from __future__ import annotations

import os
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, List, Optional

_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


class WgsError(ValueError):
    pass


def _filetime(value: int) -> datetime:
    return _FILETIME_EPOCH + timedelta(microseconds=value // 10)


class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.buf):
            raise WgsError("index tronqué")
        v = struct.unpack_from(fmt, self.buf, self.pos)
        self.pos += size
        return v[0] if len(v) == 1 else v

    def raw(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise WgsError("index tronqué")
        v = self.buf[self.pos : self.pos + n]
        self.pos += n
        return v

    def wstring(self) -> str:
        n = self.take("<I")
        if n > 4096:
            raise WgsError("chaîne invalide")
        return self.raw(n * 2).decode("utf-16-le", "replace")

    def guid(self) -> str:
        return uuid.UUID(bytes_le=self.raw(16)).hex.upper()


@dataclass(frozen=True)
class Container:
    name: str
    folder: str          # chemin absolu du dossier GUID
    file_number: int     # N de container.N
    modified: datetime   # UTC
    size: int
    flags: int

    @property
    def index_file(self) -> str:
        return os.path.join(self.folder, f"container.{self.file_number}")

    def blobs(self) -> Dict[str, str]:
        """Retourne {nom logique: chemin du blob}. Lève WgsError/OSError si absent."""
        with open(self.index_file, "rb") as fh:
            data = fh.read()
        r = _Reader(data)
        r.take("<I")  # version (4)
        count = r.take("<I")
        if count > 1000:
            raise WgsError("container.N invalide")
        out: Dict[str, str] = {}
        for _ in range(count):
            name = r.raw(128).decode("utf-16-le", "replace").rstrip("\0")
            primary = r.guid()
            secondary = r.guid()
            for candidate in (primary, secondary):
                path = os.path.join(self.folder, candidate)
                if os.path.isfile(path):
                    out[name] = path
                    break
        return out


def parse_index(path: str) -> List[Container]:
    """Décode un fichier ``containers.index`` (format version 14)."""
    with open(path, "rb") as fh:
        data = fh.read()
    base = os.path.dirname(path)
    r = _Reader(data)
    version = r.take("<I")
    if version not in (14,):
        # Format inconnu : on tente quand même, la structure est stable depuis des années.
        pass
    count = r.take("<I")
    if count > 10000:
        raise WgsError("index invalide")
    r.wstring()          # nom affiché du paquet (souvent vide)
    r.wstring()          # AUMID
    r.take("<Q")         # date de création
    r.take("<I")         # inconnu
    r.wstring()          # GUID sous forme de texte
    r.take("<Q")         # inconnu
    containers: List[Container] = []
    for _ in range(count):
        name = r.wstring()
        r.wstring()      # nom répété
        r.wstring()      # ETag cloud
        file_number = r.take("<B")
        flags = r.take("<I")
        folder = r.guid()
        modified = _filetime(r.take("<Q"))
        r.take("<Q")     # inconnu
        size = r.take("<Q")
        containers.append(Container(name, os.path.join(base, folder), file_number, modified, size, flags))
    return containers


def find_wgs_roots(package_family: str) -> Iterator[str]:
    """Itère sur les dossiers ``wgs/<xuid>_<titleid>`` du paquet (un par compte Xbox)."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return
    wgs = os.path.join(local, "Packages", package_family, "SystemAppData", "wgs")
    if not os.path.isdir(wgs):
        return
    for entry in os.scandir(wgs):
        if entry.is_dir() and os.path.isfile(os.path.join(entry.path, "containers.index")):
            yield entry.path


def read_blob(container: Container, blob_name: str, limit: Optional[int] = None) -> Optional[bytes]:
    """Lit un blob par nom logique ; None si le conteneur est incomplet."""
    try:
        blobs = container.blobs()
    except (OSError, WgsError):
        return None
    path = blobs.get(blob_name)
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            return fh.read(limit) if limit else fh.read()
    except OSError:
        return None
