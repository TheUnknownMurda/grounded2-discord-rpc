"""Chargement de config.json (avec valeurs par défaut)."""

from __future__ import annotations

import json
import os
from typing import Optional

DEFAULTS: dict = {
    # Identifiant de l'application créée sur https://discord.com/developers/applications
    "client_id": "",
    # "auto" = langue du jeu (GameUserSettings.ini), sinon "fr", "en"…
    "language": "auto",
    # Fréquence de vérification (processus + sauvegardes), en secondes.
    "poll_interval_seconds": 5,
    # Sans nouvelle sauvegarde depuis le lancement, on considère le joueur en partie
    # (avec la dernière sauvegarde connue) après ce délai. -1 pour désactiver.
    "assume_in_world_after_minutes": 2,
    # Afficher le nom du monde (sinon seulement le jour).
    "show_world_name": True,
    # Horloge en jeu : "period" (Matin/Journée/Soir/Nuit), "exact" (HH:MM), "both", "none".
    "clock_mode": "period",
    # Ajouter « En arrière-plan » quand la fenêtre du jeu n'a pas le focus.
    "show_background_state": False,
    # Taille de groupe affichée (« 2 sur 4 ») : "off", "flag3" ou "slot" (voir README, à valider).
    "party_from_header": "off",
    # Source temps réel (mod UE4SS, dossier mod/) : fichier live.json écrit par le mod.
    "live_enabled": True,
    "live_paths": [
        "%LOCALAPPDATA%/Grounded2RPC/live.json",
        "%LOCALAPPDATA%/Packages/Microsoft.OE-Augusta_8wekyb3d8bbwe/LocalCache/Local/Grounded2RPC/live.json",
    ],
    # Au-delà de cet âge (secondes), live.json est ignoré et on retombe sur les sauvegardes.
    "live_stale_seconds": 30,
    # Afficher « n sur 4 » d'après le nombre de joueurs vu par le mod (à partir de 2 joueurs).
    "party_from_live": True,
    # Noms d'exécutables à surveiller.
    "process_names": ["Grounded2-WinGDK-Shipping.exe", "Grounded2-Win64-Shipping.exe"],
    # Dossiers de sauvegardes Steam (expérimental, motifs glob).
    "steam_save_globs": ["%LOCALAPPDATA%/Augusta/Saved/SaveGames/**/*.sav"],
    # Clés des images téléversées dans l'application Discord (ou URLs https).
    "images": {
        "logo": "grounded2",
        "menu": "grounded2",
        "zone_surface": "zone_surface",
        "zone_underground": "zone_underground",
        "zone_outpost": "zone_outpost",
        "zone_lab": "zone_lab",
    },
    # Jusqu'à 2 boutons : [{"label": "…", "url": "https://…"}] (visibles par les autres, pas par toi).
    "buttons": [{"label": "Get This Presence", "url": "https://github.com/TheUnknownMurda/grounded2-discord-rpc"}],
    # Texte de version affiché dans l'info-bulle du menu (auto si vide).
    "game_version_label": "",
}


def default_config_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "config.json")


def load_config(path: Optional[str] = None) -> dict:
    path = path or default_config_path()
    config = json.loads(json.dumps(DEFAULTS))  # copie profonde
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8-sig") as fh:
            user = json.load(fh)
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    config["_path"] = path
    return config
