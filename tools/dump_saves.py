"""Affiche toutes les sauvegardes détectées avec l'intégralité des champs décodés (JSON).

Usage :  python tools/dump_saves.py [--json]

Utile pour vérifier le décodage après une mise à jour du jeu, ou pour
identifier les champs encore incertains (``flags``, ``session_mode``,
``counter_*``) en comparant avec ce que tu as fait en jeu.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from grounded2_rpc.config import load_config  # noqa: E402
from grounded2_rpc.saves import SaveWatcher    # noqa: E402
from grounded2_rpc.zones import zone_name      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="sortie JSON complète")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    config = load_config()
    saves = SaveWatcher(steam_dirs=config.get("steam_save_globs") or []).refresh()
    if args.json:
        out = []
        for s in saves:
            d = s.header.to_dict()
            d.update({"source": s.source, "key": s.key, "zone_fr": zone_name(s.header.zone_row, "fr"), "zone_en": zone_name(s.header.zone_row, "en")})
            out.append(d)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    if not saves:
        print("aucune sauvegarde trouvée")
        return 1
    for s in saves:
        h = s.header
        print(f"{h.save_time.astimezone():%Y-%m-%d %H:%M:%S}  {h.save_type_name:9} slot={h.slot_index}  monde={h.world_name!r}  "
              f"jour {h.day} {h.clock()}  zone={h.zone_row} ({zone_name(h.zone_row, 'fr')})  v{h.game_version}  "
              f"flags={h.flags} bool={h.flag_bool} mode={h.session_mode!r} compteurs=({h.counter_a}, {h.counter_b}, {h.counter_c})"
              f"{'  [partiel]' if h.partial else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
