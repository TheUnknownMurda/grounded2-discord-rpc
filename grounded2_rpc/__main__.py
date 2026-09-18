"""Point d'entrée : ``python -m grounded2_rpc [options]``."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import time
from typing import Optional

from . import __version__
from .config import load_config
from .discord_ipc import DiscordIPC, DiscordNotRunning
from .game import GameProcess, find_game, installed_version, is_foreground, read_game_settings
from .live import LiveReader
from .presence import build_presence
from .saves import SaveWatcher
from .zones import language_from_setting

log = logging.getLogger("grounded2_rpc")

MIN_UPDATE_INTERVAL = 15      # Discord ignore les mises à jour plus rapprochées
RECONNECT_INTERVAL = 20


def setup_logging(verbose: bool) -> None:
    # La console Windows est souvent en cp1252 : on force l'UTF-8 pour les emojis/accents.
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "Grounded2RPC")
    try:
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(os.path.join(log_dir, "grounded2_rpc.log"), maxBytes=512_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(fmt)
        root.addHandler(handler)
    except OSError:
        pass


def resolve_language(config: dict, settings: dict) -> str:
    wanted = (config.get("language") or "auto").lower()
    if wanted != "auto":
        return wanted
    return language_from_setting(settings.get("LanguageSetting")) or "en"


class App:
    def __init__(self, config: dict, dry_run: bool, simulate: bool):
        self.config = config
        self.dry_run = dry_run
        self.simulate = simulate
        self.watcher = SaveWatcher(steam_dirs=config.get("steam_save_globs") or [])
        self.live: Optional[LiveReader] = None
        if config.get("live_enabled", True):
            self.live = LiveReader(config.get("live_paths") or None, float(config.get("live_stale_seconds", 30)))
        self.live_active: Optional[bool] = None
        self.ipc: Optional[DiscordIPC] = None if dry_run else DiscordIPC(config["client_id"])
        self.last_sent: Optional[dict] = None
        self.last_sent_at = 0.0
        self.pending: Optional[dict] = None
        self.pending_clear = False
        self.next_connect = 0.0
        self.settings = read_game_settings()
        self.lang = resolve_language(config, self.settings)
        if not config.get("game_version_label"):
            version = installed_version()
            config["game_version_label"] = f"v{version}" if version else ""
        self._simulated: Optional[GameProcess] = None
        log.info("Grounded 2 Rich Presence %s · langue %s · autosave toutes les %s min",
                 __version__, self.lang, (self.settings.get("AutosaveInterval") or "?").split(".")[0])
        if self.live is not None:
            log.info("source temps réel (mod UE4SS) : %s", self.live.path)

    # ------------------------------------------------------------- Discord
    def _ensure_connected(self) -> bool:
        if self.ipc is None:
            return True
        if self.ipc.connected:
            return True
        if time.time() < self.next_connect:
            return False
        self.next_connect = time.time() + RECONNECT_INTERVAL
        try:
            self.ipc.connect()
            self.last_sent = None
            return True
        except DiscordNotRunning as exc:
            log.warning("Discord n'est pas joignable (%s) ; nouvel essai dans %ds", exc, RECONNECT_INTERVAL)
        except Exception as exc:  # handshake refusé, etc.
            log.error("connexion Discord impossible : %s", exc)
        return False

    def _send(self, activity: Optional[dict]) -> None:
        if self.ipc is None:
            log.info("[dry-run] activité → %s", json.dumps(activity, ensure_ascii=False) if activity else "effacée")
            self.last_sent = activity
            self.last_sent_at = time.time()
            return
        if not self._ensure_connected():
            return
        try:
            if activity is None:
                self.ipc.clear_activity()
            else:
                self.ipc.set_activity(activity)
            self.last_sent = activity
            self.last_sent_at = time.time()
            log.info("presence %s", "effacée" if activity is None else f"mise à jour : {activity.get('details')} | {activity.get('state')}")
        except Exception as exc:
            log.warning("envoi à Discord échoué (%s) ; reconnexion", exc)
            self.ipc.close()
            self.last_sent = None      # force un nouvel envoi après reconnexion
            self.next_connect = time.time() + 5

    # ---------------------------------------------------------------- boucle
    def _current_process(self) -> Optional[GameProcess]:
        if self.simulate:
            if self._simulated is None:
                self._simulated = GameProcess(pid=os.getpid(), exe_name="simulation", start_time=time.time() - 3600)
            return self._simulated
        return find_game(self.config.get("process_names") or [])

    def tick(self) -> None:
        process = self._current_process()
        saves = self.watcher.refresh()
        if process is None:
            if self.last_sent is not None:
                self._send(None)
            return
        foreground = True if self.simulate else is_foreground(process.pid)
        live = self.live.read() if self.live is not None else None
        active = live is not None
        if active != self.live_active:
            self.live_active = active
            if active:
                log.info("mod temps réel détecté (v%s) : zone et horloge en direct", live.mod_version or "?")
            elif self.live is not None:
                log.info("mod temps réel absent ou muet : repli sur les sauvegardes")
        state = build_presence(self.config, self.lang, process, saves, foreground=foreground, live=live)
        activity = state.activity
        if activity == self.last_sent:
            return
        if time.time() - self.last_sent_at < MIN_UPDATE_INTERVAL and self.last_sent is not None:
            return  # on réessaiera au prochain tick
        log.debug("état : %s", state.summary())
        self._send(activity)

    def run_forever(self) -> None:
        interval = max(1.0, float(self.config.get("poll_interval_seconds", 5)))
        try:
            while True:
                try:
                    self.tick()
                except Exception:
                    log.exception("erreur pendant la mise à jour")
                time.sleep(interval)
        except KeyboardInterrupt:
            log.info("arrêt demandé")
        finally:
            if self.ipc is not None and self.ipc.connected:
                try:
                    self.ipc.clear_activity()
                except Exception:
                    pass
                self.ipc.close()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="grounded2_rpc", description="Discord Rich Presence détaillée pour Grounded 2.")
    parser.add_argument("--config", help="chemin de config.json (défaut : à côté du dossier grounded2_rpc)")
    parser.add_argument("--dry-run", action="store_true", help="n'envoie rien à Discord, affiche l'activité calculée")
    parser.add_argument("--once", action="store_true", help="une seule itération puis quitte")
    parser.add_argument("--simulate", action="store_true", help="fait comme si le jeu tournait (test sans lancer le jeu)")
    parser.add_argument("--dump", action="store_true", help="liste les sauvegardes décodées et quitte")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    config = load_config(args.config)

    if args.dump:
        watcher = SaveWatcher(steam_dirs=config.get("steam_save_globs") or [])
        for save in watcher.refresh():
            h = save.header
            print(f"{h.save_time.astimezone():%Y-%m-%d %H:%M}  {h.save_type_name:9} {h.world_name!r:24} jour {h.day:3} {h.clock()}  "
                  f"{h.zone_row:32} v{h.game_version:8} flags={h.flags} mode={h.session_mode!r}  [{save.key.split(':')[-1]}]")
        reader = LiveReader(config.get("live_paths") or None, float(config.get("live_stale_seconds", 30)))
        live = reader.read()
        if live is None:
            print(f"live.json : absent ou périmé ({reader.path})")
        else:
            print(f"live.json : il y a {live.age():.0f} s · {json.dumps(live.raw, ensure_ascii=False)}")
        return 0

    client_id = str(config.get("client_id") or "").strip()
    if not args.dry_run and not client_id.isdigit():
        log.error("client_id manquant dans %s : crée une application sur https://discord.com/developers/applications "
                  "et colle son « Application ID » (voir README). Utilise --dry-run pour tester sans Discord.", config["_path"])
        return 2

    app = App(config, dry_run=args.dry_run, simulate=args.simulate)
    if args.once:
        app.tick()
        if app.ipc is not None and app.ipc.connected:
            time.sleep(1)
            app.ipc.close()
        return 0
    app.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
