"""Tests rapides : ``python -m unittest discover -s tests``"""

from __future__ import annotations

import os
import struct
import sys
import time
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from grounded2_rpc.game import GameProcess               # noqa: E402
from grounded2_rpc.live import LiveError, LiveReader, parse_live  # noqa: E402
from grounded2_rpc.presence import build_presence        # noqa: E402
from grounded2_rpc.save_header import HeaderError, parse_header  # noqa: E402
from grounded2_rpc.saves import SaveInfo                 # noqa: E402
from grounded2_rpc.zones import zone_kind, zone_name     # noqa: E402


def fstr(s: str) -> bytes:
    b = s.encode("utf-8") + b"\0"
    return struct.pack("<i", len(b)) + b


def make_header(day=16, hour=2, minute=43, zone="Outpost_Snackbar", world="Mon monde", save_type=2, when=None) -> bytes:
    when = when or datetime(2026, 9, 18, 9, 48, tzinfo=timezone.utc)
    ticks = int((when - datetime(1, 1, 1, tzinfo=timezone.utc)).total_seconds() * 10_000_000)
    return (struct.pack("<II", 20, 2) + fstr("0.5.0.5") + struct.pack("<IIII", 1, 2, 3, 4)
            + struct.pack("<BI", save_type, 0) + struct.pack("<q", ticks) + struct.pack("<III", day, hour, minute)
            + fstr("Augusta_Main") + fstr("/Game/Blueprints/Table_Zones.Table_Zones") + fstr(zone)
            + bytes([1, 0, 1, 1]) + fstr("") + fstr(world) + fstr("") + fstr("0000")
            + b"\0" * 16 + b"\0" + b"\0" * 8 + struct.pack("<IIIII", 29, 0, 5543, 849, 0))


CONFIG = {"images": {"logo": "grounded2", "zone_outpost": "zone_outpost"}, "assume_in_world_after_minutes": 2, "clock_mode": "period"}


class HeaderTests(unittest.TestCase):
    def test_roundtrip(self):
        h = parse_header(make_header())
        self.assertEqual((h.day, h.hour, h.minute), (16, 2, 43))
        self.assertEqual(h.zone_row, "Outpost_Snackbar")
        self.assertEqual(h.world_name, "Mon monde")
        self.assertEqual(h.save_type_name, "autosave")
        self.assertEqual(h.world_id, "00000001000000020000000300000004")
        self.assertEqual(h.counter_b, 5543)
        self.assertFalse(h.partial)

    def test_truncated_is_partial(self):
        h = parse_header(make_header()[:120])
        self.assertTrue(h.partial)
        self.assertEqual(h.day, 16)

    def test_garbage_rejected(self):
        with self.assertRaises(HeaderError):
            parse_header(b"\xff" * 64)


class ZoneTests(unittest.TestCase):
    def test_known_zone(self):
        self.assertEqual(zone_name("Outpost_Snackbar", "en"), "Ranger Outpost: Snackbar")
        self.assertEqual(zone_kind("Anthill_Cave"), "underground")

    def test_unknown_zone_prettified(self):
        self.assertEqual(zone_name("Future_NewZone", "fr"), "Future New Zone")


class PresenceTests(unittest.TestCase):
    def _save(self, when):
        return SaveInfo("k", "xbox", parse_header(make_header(when=when)), "", 0)

    def test_not_running(self):
        self.assertEqual(build_presence(CONFIG, "fr", None, []).status, "not_running")

    def test_menu_then_assumed_then_in_world(self):
        now = time.time()
        old = self._save(datetime.fromtimestamp(now - 3600, tz=timezone.utc))
        proc = GameProcess(1, "x.exe", now - 30)
        st = build_presence(CONFIG, "fr", proc, [old], now=now)
        self.assertEqual(st.status, "menu")
        self.assertIn("Dans les menus", st.activity["details"])
        st = build_presence(CONFIG, "fr", proc, [old], now=now + 200)
        self.assertEqual(st.status, "assumed")
        fresh = self._save(datetime.fromtimestamp(now + 10, tz=timezone.utc))
        st = build_presence(CONFIG, "fr", proc, [fresh, old], now=now + 200)
        self.assertEqual(st.status, "in_world")
        self.assertEqual(st.activity["details"], "Mon monde · Jour 16")
        self.assertTrue(st.activity["state"].startswith("📍 Avant-poste des rangers : snack"))
        self.assertEqual(st.activity["assets"]["small_image"], "zone_outpost")

    def test_english_and_exact_clock(self):
        now = time.time()
        proc = GameProcess(1, "x.exe", now - 30)
        fresh = self._save(datetime.fromtimestamp(now, tz=timezone.utc))
        cfg = dict(CONFIG, clock_mode="exact", show_world_name=False)
        st = build_presence(cfg, "en", proc, [fresh], now=now)
        self.assertEqual(st.activity["details"], "Day 16")
        self.assertIn("02:43", st.activity["state"])


class LiveTests(unittest.TestCase):
    def test_parse(self):
        live = parse_live('{"ts": 1700000000, "in_world": true, "day": 16, "hour": 2, "minute": 43, "zone_row": "Outpost_Snackbar", "players": 3, "host": true, "mod": "1.0"}')
        self.assertTrue(live.complete)
        self.assertEqual(live.clock(), "02:43")
        self.assertEqual((live.players, live.host, live.mod_version), (3, True, "1.0"))
        self.assertFalse(parse_live('{"ts": 1, "in_world": true, "day": 3}').complete)
        with self.assertRaises(LiveError):
            parse_live('{"in_world": true}')
        with self.assertRaises(LiveError):
            parse_live('{"ts": 1, ')

    def test_reader_stale_and_missing(self):
        import tempfile
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "live.json")
            reader = LiveReader([path], stale_seconds=30)
            self.assertIsNone(reader.read(now))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"ts": %d, "in_world": true, "day": 1, "hour": 8, "minute": 0}' % int(now))
            self.assertIsNotNone(reader.read(now))
            os.remove(path)
            self.assertIsNotNone(reader.read(now + 2))        # réécriture en cours : on garde l'ancienne valeur
            self.assertIsNone(reader.read(now + 10))          # disparu pour de bon
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"ts": %d, "in_world": true, "day": 1, "hour": 8, "minute": 0}' % int(now - 31))
            self.assertIsNone(reader.read(now))               # périmé (mod arrêté, jeu figé…)


class LivePresenceTests(unittest.TestCase):
    def _save(self, when):
        return SaveInfo("k", "xbox", parse_header(make_header(when=when)), "", 0)

    def test_live_has_priority_over_saves(self):
        now = time.time()
        proc = GameProcess(1, "x.exe", now - 30)
        old = self._save(datetime.fromtimestamp(now - 3600, tz=timezone.utc))
        live = parse_live('{"ts": %d, "in_world": true, "day": 21, "hour": 19, "minute": 5, "zone_row": "Picnic_Area", "players": 3}' % int(now))
        st = build_presence(CONFIG, "fr", proc, [old], now=now, live=live)
        self.assertEqual(st.status, "live")
        self.assertEqual(st.activity["details"], "Mon monde · Jour 21")     # nom du monde : dernière sauvegarde
        self.assertIn("Soir", st.activity["state"])
        self.assertIn("pique-nique", st.activity["state"])
        self.assertIn("en direct", st.activity["assets"]["large_text"])
        self.assertIn("dernière sauvegarde", st.activity["assets"]["large_text"])
        self.assertEqual(st.activity["party"], {"id": "00000001000000020000000300000004", "size": [3, 4]})

    def test_live_world_name_guid_and_period_from_game(self):
        now = time.time()
        proc = GameProcess(1, "x.exe", now - 30)
        old = self._save(datetime.fromtimestamp(now - 3600, tz=timezone.utc))
        # 09:30 : Matin d'après l'enum du jeu (MorningEndHour = 10), et nom/guid du mod prioritaires
        live = parse_live('{"ts": %d, "in_world": true, "day": 3, "hour": 9, "minute": 30, "time_of_day_name": "Morning", '
                          '"world_name": "Nouveau monde", "world_id": "AABBCCDD00000000000000000000FFFF", "players": 2}' % int(now))
        st = build_presence(CONFIG, "fr", proc, [old], now=now, live=live)
        self.assertEqual(st.activity["details"], "Nouveau monde · Jour 3")
        self.assertIn("Matin", st.activity["state"])
        self.assertEqual(st.activity["party"]["id"], "aabbccdd00000000000000000000ffff")
        # sans nom d'enum : d'après l'heure (seuils du jeu : 10 h = Journée)
        live = parse_live('{"ts": %d, "in_world": true, "day": 3, "hour": 10, "minute": 0}' % int(now))
        st = build_presence(CONFIG, "fr", proc, [old], now=now, live=live)
        self.assertIn("Journée", st.activity["state"])

    def test_live_menu_and_no_saves(self):
        now = time.time()
        proc = GameProcess(1, "x.exe", now - 3600)
        old = self._save(datetime.fromtimestamp(now - 7200, tz=timezone.utc))
        menu = parse_live('{"ts": %d, "in_world": false}' % int(now))
        st = build_presence(CONFIG, "fr", proc, [old], now=now, live=menu)
        self.assertEqual(st.status, "menu")                       # pas de « partie supposée » quand le mod dit menu
        live = parse_live('{"ts": %d, "in_world": true, "day": 1, "hour": 8, "minute": 0, "players": 1}' % int(now))
        st = build_presence(CONFIG, "en", proc, [], now=now, live=live)
        self.assertEqual(st.activity["details"], "Day 1")
        self.assertNotIn("party", st.activity)
        self.assertNotIn("last save", st.activity["assets"]["large_text"])

    def test_live_incomplete_falls_back_to_saves(self):
        now = time.time()
        proc = GameProcess(1, "x.exe", now - 30)
        fresh = self._save(datetime.fromtimestamp(now, tz=timezone.utc))
        live = parse_live('{"ts": %d, "in_world": true}' % int(now))    # signatures inconnues : pas de jour/heure
        st = build_presence(CONFIG, "fr", proc, [fresh], now=now, live=live)
        self.assertEqual(st.status, "in_world")


if __name__ == "__main__":
    unittest.main()
