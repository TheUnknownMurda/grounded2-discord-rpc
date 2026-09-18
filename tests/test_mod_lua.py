"""Exécute mod/Grounded2RPC/Scripts/main.lua dans un faux environnement UE4SS.

Nécessite ``lupa`` (``pip install lupa``) ; le test est ignoré sinon. Il vérifie la
logique du mod (détection menu/partie, appels protégés, JSON, diagnostic) sans le jeu.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from lupa import lua54  # type: ignore
except Exception:  # pragma: no cover - lupa absent
    lua54 = None

MOD_PATH = os.path.join(os.path.dirname(__file__), "..", "mod", "Grounded2RPC", "Scripts", "main.lua")

# Faux UE4SS : classes avec fonctions (nom, paramètres, retour) et objets avec valeurs.
# Convention des itérateurs ForEach* (identique au build UE4SS du jeu) : ne rien renvoyer
# pour continuer, ``true`` pour arrêter ; toute autre valeur corrompt la pile → erreur.
FAKE_UE4SS = r"""
local M = {}
local function FName(s) return { ToString = function() return s end } end
local function step(cb, item)
    local r = cb(item)
    if r == true then return true end
    if r ~= nil then error("attempt to call a nil value (callback returned " .. tostring(r) .. ")") end
    return false
end
local function step2(cb, a, b)
    local r = cb(a, b)
    if r == true then return true end
    if r ~= nil then error("attempt to call a nil value (callback returned " .. tostring(r) .. ")") end
    return false
end
local function Prop(name, ptype)
    return { GetFName = function() return FName(name) end, GetClass = function() return { GetFName = function() return FName(ptype) end } end }
end
local INVALID = { IsValid = function() return false end }

function M.class(fullname, funcs, props, super)
    local cls = {}
    cls.IsValid = function() return true end
    cls.GetFullName = function() return fullname end
    cls.GetFName = function() return FName(fullname:match("[^.:]+$")) end
    cls.GetSuperStruct = function() return super or INVALID end
    cls.ForEachFunction = function(self, cb)
        for _, f in ipairs(funcs) do
            local fn = {
                GetFName = function() return FName(f.name) end,
                ForEachProperty = function(_, pcb)
                    for _, p in ipairs(f.params or {}) do if step(pcb, Prop(p[1], p[2])) then return end end
                    if f.ret then step(pcb, Prop("ReturnValue", f.ret)) end
                end,
            }
            if step(cb, fn) then return end
        end
    end
    cls.ForEachProperty = function(self, cb)
        for _, p in ipairs(props or {}) do if step(cb, Prop(p[1], p[2])) then return end end
    end
    return cls
end

function M.object(fullname, cls, members)
    local obj = {}
    obj.IsValid = function() return members.__valid ~= false end
    obj.GetFullName = function() return fullname end
    obj.GetClass = function() return cls end
    return setmetatable(obj, { __index = function(_, k) return members[k] end })
end

M.instances = {}
function M.FindAllOf(class_name)
    local list = M.instances[class_name]
    if not list or #list == 0 then error("no instances of " .. class_name) end
    return list
end

function M.enum(path, entries)   -- entries : { {"ETimeOfDay::Morning", 0}, ... }
    local e = { IsValid = function() return true end }
    e.GetNameByValue = function(_, v)
        for _, it in ipairs(entries) do if it[2] == v then return FName(it[1]) end end
        return FName("None")
    end
    e.ForEachName = function(_, cb)
        for _, it in ipairs(entries) do if step2(cb, FName(it[1]), it[2]) then return end end
    end
    M.objects[path] = e
end
M.objects = {}
function M.StaticFindObject(path)
    return M.objects[path] or INVALID
end

M.loops = {}
function M.LoopAsync(ms, cb) M.loops[#M.loops + 1] = cb end
function M.ExecuteInGameThread(cb) cb() end
M.prints = {}

local UEHelpers = {}
function UEHelpers.GetGameInstance() return M.game_instance or INVALID end
package.preload["UEHelpers"] = function() return UEHelpers end

FindAllOf = M.FindAllOf
StaticFindObject = M.StaticFindObject
LoopAsync = M.LoopAsync
ExecuteInGameThread = M.ExecuteInGameThread
print = function(s) M.prints[#M.prints + 1] = s end
return M
"""

FAKE_WORLD = r"""
local M = ...
local Cal = M.class("/Script/Maine.CalendarComponent", {
    { name = "GetDay", ret = "IntProperty" }, { name = "GetHour", ret = "IntProperty" }, { name = "GetMinute", ret = "IntProperty" },
    { name = "GetTimeOfDay", ret = "EnumProperty" }, { name = "IsDayTime", ret = "BoolProperty" }, { name = "GetTotalHour", ret = "IntProperty" },
    { name = "GetHoursUntilHour", params = { { "Hour", "IntProperty" } }, ret = "FloatProperty" },
}, { { "CurrentTime", "DoubleProperty" } })
local Zone = M.class("/Script/Maine.ZoneManagerComponent", { { name = "GetLocalZoneRowHandle", ret = "StructProperty" } })
local GS = M.class("/Script/Maine.SurvivalGameState", { { name = "GetInCutscene", ret = "BoolProperty" } }, {}, M.class("/Script/Engine.GameState", {}, {}))
local Party = M.class("/Script/Maine.PartyComponent", { { name = "GetNumPartyMembers", ret = "IntProperty" } })
local Mode = M.class("/Script/Maine.SurvivalModeManagerComponent", {
    { name = "GetGameDifficulty", ret = "EnumProperty" }, { name = "GetGameMode", ret = "EnumProperty" },
    { name = "GetGameType", ret = "EnumProperty" }, { name = "IsNewGamePlus", ret = "BoolProperty" } })
local SLM = M.class("/Script/Maine.SaveLoadManager", { { name = "IsLoading", ret = "BoolProperty" } })
local GI = M.class("/Script/Maine.SurvivalGameInstance", {
    { name = "IsCurrentLevelMenuLevel", ret = "BoolProperty" }, { name = "IsInGameLevel", params = { { "InMapName", "StrProperty" } }, ret = "BoolProperty" },
    { name = "GetIsSinglePlayer", ret = "BoolProperty" } }, { { "IsInMapLoad", "BoolProperty" } })
M.enum("/Script/Maine.ETimeOfDay", { { "ETimeOfDay::Morning", 0 }, { "ETimeOfDay::Day", 1 }, { "ETimeOfDay::Evening", 2 }, { "ETimeOfDay::Night", 3 } })
M.enum("/Script/Maine.EGameDifficulty", { { "EGameDifficulty::Mild", 0 }, { "EGameDifficulty::Medium", 1 }, { "EGameDifficulty::Whoa", 2 } })

M.state = { menu = true, day = 16, hour = 2, minute = 43, zone = "Outpost_Snackbar", players = 2 }
local S = M.state
local function FName(s) return { ToString = function() return s end } end

M.game_instance = M.object("/Engine/Transient.SurvivalGameInstance_0", GI, {
    IsCurrentLevelMenuLevel = function() return S.menu end,
    IsInGameLevel = function() error("should not be called (param)") end,
    GetIsSinglePlayer = function() return S.players == 1 end,
    IsInMapLoad = false,
})
local level = "/Game/Maps/Augusta_Main.Augusta_Main:PersistentLevel."
M.instances["CalendarComponent"] = {
    M.object("/Game/BP.Default__BP_GS_C:CalendarComponent", Cal, { GetDay = function() return 99 end }),
    M.object(level .. "BP_GS_C_0.CalendarComponent", Cal, {
        GetDay = function() return S.day end, GetHour = function() return S.hour end, GetMinute = function() return S.minute end,
        GetTimeOfDay = function() return 3 end, IsDayTime = function() return false end, GetTotalHour = function() return S.day * 24 + S.hour end,
        GetHoursUntilHour = function() error("should not be called") end, CurrentTime = 123.5,
    }),
}
M.instances["ZoneManagerComponent"] = { M.object(level .. "BP_GS_C_0.ZoneManagerComponent", Zone, {
    GetLocalZoneRowHandle = function() return { RowName = FName(S.zone) } end }) }
M.instances["PartyComponent"] = { M.object(level .. "BP_GS_C_0.PartyComponent", Party, { GetNumPartyMembers = function() return S.players end }) }
M.instances["SurvivalModeManagerComponent"] = { M.object(level .. "BP_GS_C_0.ModeManager", Mode, {
    GetGameDifficulty = function() return 1 end, GetGameMode = function() return 0 end, GetGameType = function() return 0 end, IsNewGamePlus = function() return false end }) }
-- le GameState expose ses composants par propriété (comme le vrai InGameGameState / SurvivalGameState)
M.instances["SurvivalGameState"] = { M.object(level .. "BP_GS_C_0", GS, {
    PlayerArray = { GetArrayNum = function() return S.players end }, Role = 3, GetInCutscene = function() return false end,
    PlaythroughName = "Mon monde", PlaythroughGuid = { A = 1, B = 2, C = -1, D = 4 },
    CalendarComponent = M.instances["CalendarComponent"][2], ZoneManagerComponent = M.instances["ZoneManagerComponent"][1],
    PartyComponent = M.instances["PartyComponent"][1], SurvivalModeManagerComponent = M.instances["SurvivalModeManagerComponent"][1] }) }
M.instances["SaveLoadManager"] = { M.object("/Engine/Transient.SaveLoadManager_0", SLM, { IsLoading = function() return false end }) }
"""


@unittest.skipIf(lua54 is None, "lupa (Lua 5.4) non installé")
class LuaModTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="g2rpc_")
        os.environ["LOCALAPPDATA"] = self.tmp
        os.makedirs(os.path.join(self.tmp, "Grounded2RPC"))   # créé par l'outil Python / l'installateur
        self.lua = lua54.LuaRuntime(unpack_returned_tuples=True)
        self._run = self.lua.eval("function(src, name, ...) return assert(load(src, name))(...) end")
        self.fake = self._run(FAKE_UE4SS, "=fake_ue4ss")
        self._run(FAKE_WORLD, "=fake_world", self.fake)
        with open(MOD_PATH, "r", encoding="utf-8") as fh:
            self._run(fh.read(), "@" + MOD_PATH)
        self.assertEqual(len(self.fake.loops), 1, "LoopAsync doit être enregistrée une fois")

    def _tick(self):
        self.fake.loops[1]()

    def _live(self) -> dict:
        with open(os.path.join(self.tmp, "Grounded2RPC", "live.json"), "r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_menu_then_world(self):
        self._tick()
        live = self._live()
        self.assertFalse(live["in_world"])
        self.assertTrue(live["menu_level"])
        self.assertIn("ts", live)
        self.assertEqual(live["mod"], "1.1")

        self.fake.state.menu = False
        self._tick()
        live = self._live()
        self.assertTrue(live["in_world"])
        self.assertEqual((live["day"], live["hour"], live["minute"]), (16, 2, 43))
        self.assertEqual(live["zone_row"], "Outpost_Snackbar")
        self.assertEqual(live["players"], 2)
        self.assertEqual(live["party_members"], 2)
        self.assertTrue(live["host"])
        self.assertEqual(live["difficulty"], 1)
        self.assertEqual(live["difficulty_name"], "Medium")
        self.assertFalse(live["loading"])
        self.assertEqual(live["time_of_day"], 3)
        self.assertEqual(live["time_of_day_name"], "Night")
        self.assertEqual(live["world_name"], "Mon monde")
        self.assertEqual(live["world_id"], "0000000100000002FFFFFFFF00000004")
        self.assertNotIn("game_mode_name", live)          # enum EGameMode absent du faux : champ omis
        # le diagnostic est écrit au premier passage en partie
        with open(os.path.join(self.tmp, "Grounded2RPC", "live_diag.txt"), "r", encoding="utf-8") as fh:
            diag = fh.read()
        self.assertIn("GetHoursUntilHour", diag)
        self.assertIn("(Hour:IntProperty) -> FloatProperty", diag)
        self.assertIn("CurrentTime", diag)
        self.assertIn("= 123.5", diag)
        self.assertNotIn("/Script/Engine.GameState", diag)   # classes moteur ignorées
        self.assertIn("ETimeOfDay::Evening", diag)
        self.assertIn("= 2", diag)
        self.assertIn("(InMapName:StrProperty) -> BoolProperty", diag)

        self.fake.state.zone = "Picnic_Area"
        self.fake.state.minute = 44
        self._tick()
        live = self._live()
        self.assertEqual(live["zone_row"], "Picnic_Area")
        self.assertEqual(live["minute"], 44)

        self.fake.state.menu = True
        self._tick()
        self.assertFalse(self._live()["in_world"])   # objets résiduels : le GameInstance fait foi

    def test_functions_with_params_are_skipped(self):
        self.fake.state.menu = False
        # remplace GetDay par une version qui exige un paramètre : elle doit être ignorée, pas appelée
        self._run("""
            local M = ...
            local cal = M.instances["CalendarComponent"][2]
            local cls = cal.GetClass()
            local orig = cls.ForEachFunction
            cls.ForEachFunction = function(self, cb)
                local stop = cb({ GetFName = function() return { ToString = function() return "GetDay" end } end,
                     ForEachProperty = function(_, pcb) pcb({ GetFName = function() return { ToString = function() return "Which" end } end,
                                                              GetClass = function() return { GetFName = function() return { ToString = function() return "IntProperty" end } end } end }) end })
                if stop then return end
                orig(self, cb)
            end
        """, "=patch", self.fake)
        self._tick()
        live = self._live()
        self.assertTrue(live["in_world"])
        self.assertNotIn("day", live)
        self.assertEqual(live["hour"], 2)
        prints = list(self.fake.prints.values())
        self.assertTrue(any("GetDay(Which:IntProperty)" in p for p in prints), prints)

    def test_unknown_signature_is_not_called(self):
        self.fake.state.menu = False
        self._run("""
            local M = ...
            local cal = M.instances["CalendarComponent"][2]
            local cls = cal.GetClass()
            local orig = cls.ForEachFunction
            cls.ForEachFunction = function(self, cb)
                local stop = cb({ GetFName = function() return { ToString = function() return "GetDay" end } end,
                                  ForEachProperty = function() error("reflection unavailable") end })
                if stop then return end
                orig(self, cb)
            end
        """, "=patch", self.fake)
        self._tick()
        live = self._live()
        self.assertNotIn("day", live)
        self.assertEqual(live["hour"], 2)
        prints = list(self.fake.prints.values())
        self.assertTrue(any("signature illisible" in p and "GetDay" in p for p in prints), prints)

    def test_collect_error_is_contained(self):
        self.fake.state.menu = False
        self.fake.instances["ZoneManagerComponent"][1].GetClass = self.lua.eval("function() error('boom') end")
        self._tick()
        live = self._live()
        self.assertTrue(live["in_world"])
        self.assertEqual(live["day"], 16)
        self.assertNotIn("zone_row", live)


if __name__ == "__main__":
    unittest.main()
