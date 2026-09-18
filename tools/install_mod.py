"""Installe (ou retire) le mod UE4SS ``Grounded2RPC`` dans le dossier du jeu.

1. Si ``dwmapi.dll`` n'est pas à côté de l'exe, copie le runtime UE4SS embarqué (``mod/UE4SS_Grounded2`` :
   ``dwmapi.dll`` + dossier ``ue4ss``) ; ``--reinstall-ue4ss`` l'écrase s'il est déjà là.
2. Copie ``mod/Grounded2RPC`` vers ``<jeu>/Augusta/Binaries/<WinGDK|Win64>/ue4ss/Mods/Grounded2RPC``.
3. Crée ``%LOCALAPPDATA%\\Grounded2RPC`` où le mod écrit ``live.json``.

Usage :  python tools/install_mod.py [--game "E:\\XboxGames\\Grounded 2"] [--reinstall-ue4ss] [--uninstall]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_SRC = os.path.join(HERE, "..", "mod", "Grounded2RPC")
UE4SS_SRC = os.path.join(HERE, "..", "mod", "UE4SS_Grounded2")
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


def install_ue4ss(binaries: str, overwrite: bool = False) -> int:
    """Copie dwmapi.dll + ue4ss/ depuis mod/UE4SS_Grounded2. Sans ``overwrite``, les fichiers déjà
    présents (réglages, mods.txt…) sont conservés. Renvoie le nombre de fichiers copiés."""
    copied = 0
    for root, _dirs, files in os.walk(UE4SS_SRC):
        rel = os.path.relpath(root, UE4SS_SRC)
        target_dir = binaries if rel == "." else os.path.join(binaries, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in files:
            if name == "SOURCE.md":
                continue
            target = os.path.join(target_dir, name)
            if os.path.exists(target) and not overwrite:
                continue
            shutil.copy2(os.path.join(root, name), target)
            copied += 1
    return copied


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
    parser.add_argument("--reinstall-ue4ss", action="store_true", help="écrase le runtime UE4SS du jeu par la copie embarquée")
    parser.add_argument("--uninstall", action="store_true", help="retire le mod (UE4SS reste en place)")
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

    ue4ss_present = os.path.isfile(os.path.join(binaries, "dwmapi.dll")) and os.path.isdir(mods_dir)
    if not ue4ss_present or args.reinstall_ue4ss:
        if not os.path.isfile(os.path.join(UE4SS_SRC, "dwmapi.dll")):
            print("Runtime UE4SS embarqué introuvable (mod/UE4SS_Grounded2) : installe « UE4SS_Grounded2 » "
                  "(Nexus Mods, mod 52) à côté de l'exe du jeu puis relance ce script.")
            return 2
        copied = install_ue4ss(binaries, overwrite=args.reinstall_ue4ss)
        print(f"runtime UE4SS {'réinstallé' if args.reinstall_ue4ss else 'installé'} : {copied} fichier(s) → {binaries}")
    else:
        print("runtime UE4SS déjà présent (--reinstall-ue4ss pour le remplacer par la copie embarquée)")

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
