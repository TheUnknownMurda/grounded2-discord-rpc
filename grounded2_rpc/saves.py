"""Collecte des sauvegardes Grounded 2 (Xbox / Game Pass, et Steam en mode expérimental).

``SaveWatcher.refresh()`` renvoie la liste des sauvegardes connues, triées de la
plus récente à la plus ancienne. Les headers sont mis en cache par conteneur :
un conteneur en cours d'écriture (incomplet) conserve sa dernière valeur
valide, ce qui évite les « trous » dans la presence.
"""

from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import wgs
from .save_header import HeaderError, SaveHeader, parse_header

log = logging.getLogger(__name__)

XBOX_PACKAGE_FAMILY = "Microsoft.OE-Augusta_8wekyb3d8bbwe"


@dataclass
class SaveInfo:
    key: str               # identifiant stable (nom du conteneur ou chemin)
    source: str            # "xbox" | "steam"
    header: SaveHeader
    path: str              # dossier ou fichier d'origine
    modified: float        # mtime (epoch) de l'index/fichier

    @property
    def timestamp(self) -> float:
        return self.header.save_timestamp


class SaveWatcher:
    def __init__(self, steam_dirs: Optional[List[str]] = None, xbox_family: str = XBOX_PACKAGE_FAMILY):
        self.xbox_family = xbox_family
        self.steam_dirs = steam_dirs or []
        self._cache: Dict[str, SaveInfo] = {}
        self._index_sig: Dict[str, tuple] = {}
        self._seen_incomplete: set = set()

    # ------------------------------------------------------------------ Xbox
    def _refresh_xbox(self) -> None:
        for root in wgs.find_wgs_roots(self.xbox_family):
            index_path = os.path.join(root, "containers.index")
            try:
                st = os.stat(index_path)
                sig = (st.st_mtime_ns, st.st_size)
            except OSError:
                continue
            if self._index_sig.get(root) == sig and not self._seen_incomplete:
                continue
            try:
                containers = wgs.parse_index(index_path)
            except (OSError, wgs.WgsError) as exc:
                log.debug("index illisible (%s), nouvel essai plus tard", exc)
                continue
            self._index_sig[root] = sig
            present = set()
            for c in containers:
                if not c.name.startswith("ID-"):
                    continue  # ex. MaineGameUserSettings
                key = f"xbox:{root}:{c.name}"
                present.add(key)
                cached = self._cache.get(key)
                if cached and cached.modified == c.modified.timestamp() and cached.path == c.folder:
                    self._seen_incomplete.discard(key)
                    continue
                data = wgs.read_blob(c, "HeaderData", limit=4096)
                if data is None:
                    # conteneur en cours d'écriture : on garde l'ancienne valeur
                    self._seen_incomplete.add(key)
                    continue
                try:
                    header = parse_header(data)
                except HeaderError as exc:
                    log.warning("header illisible pour %s : %s", c.name, exc)
                    self._seen_incomplete.discard(key)
                    continue
                self._seen_incomplete.discard(key)
                self._cache[key] = SaveInfo(key, "xbox", header, c.folder, c.modified.timestamp())
                log.info("sauvegarde lue : %s (%s, jour %d, %s)", c.name, header.save_type_name, header.day, header.zone_row)
            for key in [k for k in self._cache if k.startswith(f"xbox:{root}:") and k not in present]:
                del self._cache[key]
                self._seen_incomplete.discard(key)

    # ----------------------------------------------------------------- Steam
    def _refresh_steam(self) -> None:
        """Expérimental : tente de lire le début des fichiers .sav comme un header."""
        for pattern in self.steam_dirs:
            for path in glob.glob(os.path.expandvars(pattern), recursive=True):
                key = f"steam:{path}"
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                cached = self._cache.get(key)
                if cached and cached.modified == st.st_mtime:
                    continue
                try:
                    with open(path, "rb") as fh:
                        header = parse_header(fh.read(4096))
                except (OSError, HeaderError):
                    continue
                self._cache[key] = SaveInfo(key, "steam", header, path, st.st_mtime)

    # ------------------------------------------------------------------- API
    def refresh(self) -> List[SaveInfo]:
        self._refresh_xbox()
        if self.steam_dirs:
            self._refresh_steam()
        return sorted(self._cache.values(), key=lambda s: s.timestamp, reverse=True)

    def all(self) -> List[SaveInfo]:
        return sorted(self._cache.values(), key=lambda s: s.timestamp, reverse=True)
