"""Installe (ou retire) le mod UE4SS ``Grounded2RPC`` dans le dossier du jeu.

Copie ``mod/Grounded2RPC`` vers ``<jeu>/Augusta/Binaries/<WinGDK|Win64>/ue4ss/Mods/Grounded2RPC``
(UE4SS doit déjà être installé : ``dwmapi.dll`` + dossier ``ue4ss`` à côté de l'exe) et crée
``%LOCALAPPDATA%\\Grounded2RPC`` où le mod écrit ``live.json``.

Usage :  python tools/install_mod.py [--game "E:\\XboxGames\\Grounded 2"] [--uninstall]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_SRC = os.path.join(HERE, "..", "mod", "Grounded2RPC")
MOD_NAME = "Grounded2RPC"

# Racines d'installation connues (Xbox app / Game Pass, puis Steam).
DEFAULT_ROOTS = [
    r"E:\XboxGames\Grounded 2", r"C:\XboxGames\Grounded 2", r"D:\XboxGames\Grounded 2", r"F:\XboxGames\Grounded 2",
    r"C:\Program Files (x86)\Steam\steamapps\common\Grounded2",
]
BINARIES = [
    ("Content", "Augusta", "Binaries", "WinGDK"),   # Xbox app / Game Pass
    ("Augusta", "Binaries", "WinGDK"),
    ("Augusta", "Binaries", "Win64"),               # Steam
]


def find_binaries(root: str) -> str | None:
    for parts in BINARIES:
        path = os.path.join(root, *parts)
        if os.path.isdir(path):
            return path
    return None


def main(argv=None) -> int:
    if os.name == "nt":  # console Windows souvent en cp1252
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Installe le mod UE4SS Grounded2RPC.")
    parser.add_argument("--game", help="dossier du jeu (contient Content/ ou Augusta/)")
    parser.add_argument("--uninstall", action="store_true", help="retire le mod")
    args = parser.parse_args(argv)

    roots = [args.game] if args.game else DEFAULT_ROOTS
    binaries = next((b for b in (find_binaries(r) for r in roots) if b), None)
    if not binaries:
        print("Dossier du jeu introuvable. Indique-le : python tools/install_mod.py --game \"E:\\XboxGames\\Grounded 2\"")
        return 2
    mods_dir = os.path.join(binaries, "ue4ss", "Mods")
    target = os.path.join(mods_dir, MOD_NAME)
    print(f"binaires du jeu : {binaries}")

    if args.uninstall:
        if os.path.isdir(target):
            shutil.rmtree(target)
            print(f"mod retiré : {target}")
        else:
            print("mod déjà absent")
        return 0

    if not os.path.isfile(os.path.join(binaries, "dwmapi.dll")) or not os.path.isdir(mods_dir):
        print("UE4SS n'est pas installé dans ce dossier (dwmapi.dll + ue4ss/Mods attendus).")
        print("Installe d'abord « UE4SS_Grounded2 » (Nexus Mods, mod 52) puis relance ce script.")
        return 2

    os.makedirs(target, exist_ok=True)
    for name in ("Scripts",):
        src, dst = os.path.join(MOD_SRC, name), os.path.join(target, name)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    with open(os.path.join(target, "enabled.txt"), "w", encoding="utf-8"):
        pass  # présence du fichier = mod activé (pas besoin de toucher mods.txt)

    out_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Grounded2RPC")
    os.makedirs(out_dir, exist_ok=True)

    print(f"mod installé : {target}")
    print(f"fichier live  : {os.path.join(out_dir, 'live.json')} (écrit par le mod une fois en jeu)")
    print("Lance le jeu : la console UE4SS doit afficher « [Grounded2RPC] mod … » puis « en partie · jour … » une fois dans un monde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
