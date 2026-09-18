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


if __name__ == "__main__":
    unittest.main()
