"""Régénère grounded2_rpc/data/zones.json à partir des fichiers du jeu.

Lit directement le conteneur IoStore de Grounded 2 (Augusta-WinGDK.utoc/.ucas,
non compressé et non chiffré dans la version Xbox) :

* ``Augusta/Content/Blueprints/Table_Zones.uasset`` : table des zones (nom de
  ligne → identifiant de texte dans la table ``game/areas``).
* ``Augusta/Content/Exported/Release_*/Localized/<lang>/Text/Text_<lang>.uasset`` :
  tables de textes d'Obsidian, une par langue, cumulées release après release.

Usage :  python tools/extract_zones.py [--game "E:\\XboxGames\\Grounded 2"] [--out chemin]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from collections import defaultdict

LANG_CODES = {"frfr": "fr", "enus": "en", "dede": "de", "eses": "es", "esmx": "es-MX", "itit": "it",
              "jajp": "ja", "kokr": "ko", "ptbr": "pt-BR", "zhch": "zh-Hans", "zhtw": "zh-Hant"}


# --------------------------------------------------------------------------- IoStore
class IoStore:
    """Lecture minimale d'un conteneur .utoc/.ucas (version 8, sans compression ni chiffrement)."""

    def __init__(self, utoc: str):
        self.utoc = utoc
        self.ucas = utoc[:-5] + ".ucas"
        data = open(utoc, "rb").read()
        if data[:16] != b"-==--==--==--==-":
            raise SystemExit("utoc invalide")
        ver = data[16]
        hsz, n, nb, _bsz, cmc, cml, self.block_size, dsz, _pc = struct.unpack_from("<IIIIIIIII", data, 20)
        flags = data[80]
        seeds = struct.unpack_from("<I", data, 84)[0]
        nohash = struct.unpack_from("<I", data, 96)[0]
        if flags & 0x2:
            raise SystemExit("conteneur chiffré : non pris en charge")
        p = hsz + 12 * n
        self.offlen = data[p:p + 10 * n]
        p += 10 * n
        if ver >= 4:
            p += 4 * seeds
        if ver >= 5:
            p += 4 * nohash
        self.blocks = data[p:p + 12 * nb]
        p += 12 * nb + cmc * cml
        self.paths = self._parse_directory(data[p:p + dsz])

    @staticmethod
    def _fstr(buf: bytes, pos: int):
        ln = struct.unpack_from("<i", buf, pos)[0]
        pos += 4
        if ln == 0:
            return "", pos
        if ln < 0:
            return buf[pos:pos + (-ln - 1) * 2].decode("utf-16-le"), pos + (-ln) * 2
        return buf[pos:pos + ln - 1].decode("utf-8", "replace"), pos + ln

    def _parse_directory(self, d: bytes) -> dict:
        mount, q = self._fstr(d, 0)
        nd = struct.unpack_from("<I", d, q)[0]; q += 4
        dirs = [struct.unpack_from("<IIII", d, q + i * 16) for i in range(nd)]; q += 16 * nd
        nf = struct.unpack_from("<I", d, q)[0]; q += 4
        files = [struct.unpack_from("<III", d, q + i * 12) for i in range(nf)]; q += 12 * nf
        ns = struct.unpack_from("<I", d, q)[0]; q += 4
        strings = []
        for _ in range(ns):
            s, q = self._fstr(d, q)
            strings.append(s)
        paths = {}
        NONE = 0xFFFFFFFF

        def walk(di: int, prefix: str):
            name, child, _sib, first_file = dirs[di]
            path = prefix + (strings[name] + "/" if name != NONE else "")
            f = first_file
            while f != NONE:
                fname, nxt, chunk = files[f]
                paths[path + strings[fname]] = chunk
                f = nxt
            c = child
            while c != NONE:
                walk(c, path)
                c = dirs[c][2]

        walk(0, mount)
        return paths

    def read(self, chunk: int) -> bytes:
        e = self.offlen[chunk * 10:(chunk + 1) * 10]
        off = int.from_bytes(e[0:5], "big"); ln = int.from_bytes(e[5:10], "big")
        first, last = off // self.block_size, (off + ln - 1) // self.block_size
        out = bytearray()
        with open(self.ucas, "rb") as fh:
            for b in range(first, last + 1):
                be = self.blocks[b * 12:(b + 1) * 12]
                boff = int.from_bytes(be[0:5], "little"); csz = int.from_bytes(be[5:8], "little")
                if be[11] != 0:
                    raise SystemExit("bloc compressé : non pris en charge")
                fh.seek(boff)
                out += fh.read(csz)
        start = off % self.block_size
        return bytes(out[start:start + ln])

    def find(self, pattern: str):
        rx = re.compile(pattern)
        return [(p, c) for p, c in self.paths.items() if rx.search(p)]


# ------------------------------------------------------------------------ zen package
class ZenPackage:
    """Sommaire d'un package cuit UE5 (format « zen », UE 5.5+) : name map + export data."""

    def __init__(self, d: bytes):
        has_ver, self.header_size = struct.unpack_from("<II", d, 0)
        p = 60
        if has_ver:
            p += 16
            ncv = struct.unpack_from("<i", d, p)[0]
            p += 4 + ncv * 20
        count, _nbytes = struct.unpack_from("<II", d, p)
        p += 16 + 8 * count
        headers = d[p:p + 2 * count]
        p += 2 * count
        self.names = []
        for i in range(count):
            b0, b1 = headers[2 * i], headers[2 * i + 1]
            ln = ((b0 & 0x3F) << 8) | b1
            if b0 & 0x80:
                self.names.append(d[p:p + ln * 2].decode("utf-16-le")); p += ln * 2
            else:
                self.names.append(d[p:p + ln].decode("utf-8")); p += ln
        self.export_data = d[self.header_size:]


# ------------------------------------------------------------------- tables de texte
def parse_text_asset(data: bytes) -> dict:
    """Tables de textes Obsidian → {nom de table: {id: texte}}."""
    pkg = ZenPackage(data)
    ed = pkg.export_data
    headers = []
    for idx, name in enumerate(pkg.names):
        if name.startswith("/") or name.startswith("Text_"):
            continue
        pat = struct.pack("<II", idx, 0) + b"\x00\x11" + struct.pack("<II", idx, 0)
        pos = ed.find(pat)
        if pos >= 0:
            headers.append((pos, name))
    headers.sort()
    tables = {}
    for i, (start, name) in enumerate(headers):
        end = headers[i + 1][0] if i + 1 < len(headers) else len(ed)
        p = start + 18
        while p + 14 <= end:   # premier enregistrement : [u32 id][00][09][u32 id][i32 len]
            id1 = struct.unpack_from("<I", ed, p)[0]
            if ed[p + 4] == 0 and ed[p + 5] == 9 and struct.unpack_from("<I", ed, p + 6)[0] == id1:
                ln = struct.unpack_from("<i", ed, p + 10)[0]
                if ln != 0 and -20000 < ln < 20000:
                    break
            p += 1
        recs = {}
        while p + 14 <= end:
            id1 = struct.unpack_from("<I", ed, p)[0]
            flags, typ = ed[p + 4], ed[p + 5]
            if typ != 9 or (flags & 0x7F):
                break
            if flags & 0x80:
                q = p + 7
            else:
                if struct.unpack_from("<I", ed, p + 6)[0] != id1:
                    break
                q = p + 10
            ln = struct.unpack_from("<i", ed, q)[0]; q += 4
            if ln == 0:
                text = ""
            elif ln < 0:
                text = ed[q:q + (-ln - 1) * 2].decode("utf-16-le", "replace"); q += (-ln) * 2
            else:
                text = ed[q:q + ln - 1].decode("utf-8", "replace"); q += ln
            recs[id1] = text
            p = q + 8
        tables[name] = recs
    return tables


# ---------------------------------------------------------------------- Table_Zones
ROW_HEADER = bytes.fromhex("800b04800704")   # en-tête « unversioned » commun à toutes les lignes


def parse_zone_table(data: bytes) -> dict:
    pkg = ZenPackage(data)
    ed = pkg.export_data
    zone_names = {i for i, n in enumerate(pkg.names) if not n.startswith("/") and n != "Table_Zones"}
    rows = {}
    p = 0
    while p + 32 <= len(ed):
        idx, num = struct.unpack_from("<II", ed, p)
        if num == 0 and idx in zone_names and ed[p + 8:p + 14] == ROW_HEADER:
            table, text_id, ztype = struct.unpack_from("<III", ed, p + 14)
            rows[pkg.names[idx]] = {"area_id": text_id, "type": ztype, "table": table}
            p += 32
        else:
            p += 1
    return rows


def zone_kind(row: str) -> str:
    r = row.lower()
    if r.startswith("outpost_"):
        return "outpost"
    if any(k in r for k in ("anthill", "cave", "burrow", "tunnel", "underground", "abyss", "sinkhole", "_under")):
        return "underground"
    if any(k in r for k in ("lab", "facility", "oof", "archives", "station", "center", "checkpoint", "tubes", "maze")):
        return "lab"
    return "surface"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=r"E:\XboxGames\Grounded 2", help="dossier d'installation du jeu")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "grounded2_rpc", "data", "zones.json"))
    args = ap.parse_args()
    utoc = os.path.join(args.game, "Content", "Augusta", "Content", "Paks", "Augusta-WinGDK.utoc")
    if not os.path.isfile(utoc):
        print("utoc introuvable :", utoc); return 1
    store = IoStore(utoc)
    print(f"{len(store.paths)} fichiers dans le conteneur")

    zones_hits = store.find(r"/Blueprints/Table_Zones\.uasset$")
    if not zones_hits:
        print("Table_Zones.uasset introuvable"); return 1
    zones = parse_zone_table(store.read(zones_hits[0][1]))
    print(f"{len(zones)} zones")

    texts = defaultdict(list)
    for path, chunk in store.find(r"/Exported/Release_[0-9_]+/Localized/([a-z]+)/Text/Text_[a-z]+\.uasset$"):
        m = re.search(r"/(Release_[0-9_]+)/Localized/([a-z]+)/", path)
        texts[m.group(2)].append((tuple(int(x) for x in m.group(1).split("_")[1:]), chunk))
    areas = {}
    for lang, chunks in texts.items():
        merged = {}
        for _, chunk in sorted(chunks):
            merged.update(parse_text_asset(store.read(chunk)).get("game/areas", {}))
        areas[LANG_CODES.get(lang, lang)] = merged
    print("langues :", ", ".join(sorted(areas)))

    out = {"_meta": {"source": f"Table_Zones.uasset + Exported/Release_*/Localized/*/Text (jeu dans {args.game})",
                     "generator": "tools/extract_zones.py"}, "zones": {}}
    missing = set()
    for row, info in sorted(zones.items()):
        names = {}
        for lang, table in sorted(areas.items()):
            text = table.get(info["area_id"])
            names[lang] = text.replace("\u00a0", " ") if text else None
            if not text:
                missing.add(info["area_id"])
        out["zones"][row] = {"area_id": info["area_id"], "kind": zone_kind(row), "names": names}
    if missing:
        print("identifiants de texte sans traduction :", sorted(missing))
    with open(os.path.abspath(args.out), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("écrit :", os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
