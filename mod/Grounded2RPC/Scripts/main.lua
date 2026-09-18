-- Grounded2RPC · mod UE4SS pour Grounded 2
--
-- Écrit toutes les 2 s l'état de la partie (zone, jour, heure, joueurs, difficulté)
-- dans %LOCALAPPDATA%\Grounded2RPC\live.json, que l'outil grounded2_rpc lit pour
-- afficher une Discord Rich Presence en temps réel (au lieu d'attendre l'autosave).
--
-- Lecture seule : aucun hook, aucune modification d'objet du jeu. Chaque appel de
-- fonction du jeu est vérifié (0 paramètre attendu) puis protégé par pcall ; si une
-- mise à jour du jeu change une signature, le champ correspondant est simplement omis.
--
-- Au premier passage en partie, un dump de diagnostic (propriétés et fonctions des
-- classes utilisées) est écrit dans live_diag.txt à côté de live.json.

local UEHelpers = require("UEHelpers")

local MOD_VERSION = "1.1"
local POLL_MS = 2000          -- fréquence de lecture
local HEARTBEAT_S = 10        -- réécriture du fichier même sans changement (preuve de vie)

-- ---------------------------------------------------------------------------- log
local function log(fmt, ...)
    print(string.format("[Grounded2RPC] " .. fmt .. "\n", ...))
end

local logged_once = {}
local function log_once(key, fmt, ...)
    if logged_once[key] then return end
    logged_once[key] = true
    log(fmt, ...)
end

-- ------------------------------------------------------------------------ fichiers
local function script_dir()
    local ok, info = pcall(debug.getinfo, 1, "S")
    if ok and info and info.source then
        local src = info.source:gsub("^@", "")
        return src:match("^(.*)[\\/]") or "."
    end
    return "."
end

local function output_dir()
    local base = os.getenv("LOCALAPPDATA")
    if base and base ~= "" then
        return base .. "\\Grounded2RPC"
    end
    return script_dir()
end

local OUT_DIR = output_dir()
local LIVE_PATH = OUT_DIR .. "\\live.json"
local DIAG_PATH = OUT_DIR .. "\\live_diag.txt"

local function write_file(path, content)
    -- écriture dans un fichier temporaire puis renommage (Windows refuse le
    -- renommage vers un fichier existant : on le supprime d'abord)
    local tmp = path .. ".tmp"
    local fh, err = io.open(tmp, "wb")
    if not fh then
        return false, err
    end
    fh:write(content)
    fh:close()
    os.remove(path)
    local ok, rerr = os.rename(tmp, path)
    if ok then return true end
    local direct = io.open(path, "wb")
    if direct then
        direct:write(content)
        direct:close()
        os.remove(tmp)
        return true
    end
    return false, rerr
end

-- --------------------------------------------------------------------------- JSON
local function json_string(s)
    s = tostring(s)
    s = s:gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' end
        if c == "\\" then return "\\\\" end
        if c == "\n" then return "\\n" end
        if c == "\r" then return "\\r" end
        if c == "\t" then return "\\t" end
        return string.format("\\u%04x", c:byte())
    end)
    return '"' .. s .. '"'
end

local function json_value(v)
    local t = type(v)
    if t == "nil" then return "null" end
    if t == "boolean" then return v and "true" or "false" end
    if t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "null" end
        if math.type(v) == "integer" or v == math.floor(v) then
            return string.format("%d", v)
        end
        return string.format("%.3f", v)
    end
    return json_string(v)
end

local function json_object(tbl)
    local keys = {}
    for k in pairs(tbl) do keys[#keys + 1] = k end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do
        parts[#parts + 1] = json_string(k) .. ":" .. json_value(tbl[k])
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

-- --------------------------------------------------------------- réflexion UE4SS
local function fname_str(obj)
    local ok, s = pcall(function() return obj:GetFName():ToString() end)
    return ok and s or "?"
end

local function class_chain(obj)
    local chain = {}
    local ok, class = pcall(function() return obj:GetClass() end)
    local guard = 0
    while ok and class and class:IsValid() and guard < 32 do
        chain[#chain + 1] = class
        guard = guard + 1
        ok, class = pcall(function() return class:GetSuperStruct() end)
    end
    return chain
end

local function function_params(fn)
    -- liste des paramètres (nom:type) et type de retour d'une UFunction ;
    -- le 3e résultat vaut false si l'énumération a échoué (signature inconnue)
    local params, ret = {}, "void"
    local ok, err = pcall(function()
        fn:ForEachProperty(function(prop)
            local pname = fname_str(prop)
            local ptype = "?"
            pcall(function() ptype = prop:GetClass():GetFName():ToString() end)
            if pname == "ReturnValue" then
                ret = ptype
            else
                params[#params + 1] = pname .. ":" .. ptype
            end
            -- ne rien renvoyer = continuer (un « return false » casse l'itération d'UE4SS)
        end)
    end)
    if not ok then ret = "? (" .. tostring(err) .. ")" end
    return params, ret, ok
end

local signature_cache = {}   -- "<classe>:<fonction>" -> {nparams=…, sig=…}

local function function_info(obj, name)
    local class_name = "?"
    pcall(function() class_name = obj:GetClass():GetFullName() end)
    local key = class_name .. ":" .. name
    local cached = signature_cache[key]
    if cached ~= nil then return cached end
    local found
    for _, class in ipairs(class_chain(obj)) do
        pcall(function()
            class:ForEachFunction(function(fn)
                if fname_str(fn) == name then
                    found = fn
                    return true   -- stoppe l'itération
                end
            end)
        end)
        if found then break end
    end
    if not found then
        signature_cache[key] = false
        log_once("missing:" .. key, "fonction %s introuvable sur %s", name, class_name)
        return false
    end
    local params, ret, enumerated = function_params(found)
    local info = {
        nparams = enumerated and #params or -1,   -- -1 : signature inconnue, on n'appelle pas
        sig = string.format("%s(%s) -> %s", name, table.concat(params, ", "), ret),
    }
    signature_cache[key] = info
    return info
end

-- Appelle obj:name() seulement si la fonction existe et n'attend aucun paramètre.
-- Renvoie nil en cas d'échec (jamais d'erreur Lua remontée).
local function call0(obj, name)
    local info = function_info(obj, name)
    if not info then return nil end
    if info.nparams ~= 0 then
        log_once("params:" .. info.sig, "fonction ignorée (%s) : %s",
            info.nparams < 0 and "signature illisible" or "paramètres requis", info.sig)
        return nil
    end
    local ok, result = pcall(function() return obj[name](obj) end)
    if not ok then
        log_once("call:" .. name, "appel %s échoué : %s", name, tostring(result))
        return nil
    end
    return result
end

local function get_prop(obj, name)
    local ok, v = pcall(function() return obj[name] end)
    if ok then return v end
    return nil
end

local function to_plain(v)
    -- convertit une valeur UE (FName, FText, FString…) en valeur Lua simple
    local t = type(v)
    if t == "userdata" then
        local ok, s = pcall(function() return v:ToString() end)
        if ok and type(s) == "string" then return s end
        return nil
    end
    if t == "number" or t == "string" or t == "boolean" then return v end
    return nil
end

-- ------------------------------------------------------------------ instances
local function pick_instance(class_name)
    -- première instance « vivante » : dans un niveau chargé, jamais un objet par défaut
    local ok, all = pcall(FindAllOf, class_name)
    if not ok or not all then return nil end
    local fallback
    for _, obj in ipairs(all) do
        local valid = false
        pcall(function() valid = obj:IsValid() end)
        if valid then
            local full = ""
            pcall(function() full = obj:GetFullName() end)
            if not full:find("Default__", 1, true) then
                if full:find(":PersistentLevel.", 1, true) then
                    return obj
                end
                fallback = fallback or obj
            end
        end
    end
    return fallback
end

local instances = {}   -- class_name -> objet (revalidé à chaque tick)

local function instance(class_name)
    local obj = instances[class_name]
    if obj then
        local valid = false
        pcall(function() valid = obj:IsValid() end)
        if valid then return obj end
        instances[class_name] = nil
    end
    obj = pick_instance(class_name)
    if obj then
        instances[class_name] = obj
        local full = "?"
        pcall(function() full = obj:GetFullName() end)
        log("%s : %s", class_name, full)
    end
    return obj
end

-- ------------------------------------------------------------------ diagnostic
local SIMPLE_TYPES = {
    BoolProperty = true, IntProperty = true, Int8Property = true, Int16Property = true,
    Int64Property = true, UInt16Property = true, UInt32Property = true, UInt64Property = true,
    FloatProperty = true, DoubleProperty = true, NameProperty = true, StrProperty = true,
    ByteProperty = true, EnumProperty = true, TextProperty = true,
}

local function dump_object(out, label, obj)
    if not obj then
        out[#out + 1] = string.format("== %s : (aucune instance)", label)
        return
    end
    local full = "?"
    pcall(function() full = obj:GetFullName() end)
    out[#out + 1] = string.format("== %s : %s", label, full)
    for _, class in ipairs(class_chain(obj)) do
        local cname = "?"
        pcall(function() cname = class:GetFullName() end)
        -- on s'arrête aux classes moteur (trop verbeuses, sans intérêt ici)
        if cname:find("/Script/Engine.", 1, true) or cname:find("/Script/CoreUObject.", 1, true) then break end
        out[#out + 1] = "-- " .. cname
        pcall(function()
            class:ForEachProperty(function(prop)
                local pname = fname_str(prop)
                local ptype = "?"
                pcall(function() ptype = prop:GetClass():GetFName():ToString() end)
                local shown = ""
                if SIMPLE_TYPES[ptype] then
                    local v = to_plain(get_prop(obj, pname))
                    if v ~= nil then shown = " = " .. tostring(v) end
                end
                out[#out + 1] = string.format("  prop  %-44s %s%s", pname, ptype, shown)
            end)
        end)
        pcall(function()
            class:ForEachFunction(function(fn)
                local params, ret = function_params(fn)
                out[#out + 1] = string.format("  func  %-44s (%s) -> %s", fname_str(fn), table.concat(params, ", "), ret)
            end)
        end)
    end
end

-- ---------------------------------------------------------------------- enums
local ENUMS = {
    time_of_day = "/Script/Maine.ETimeOfDay",
    difficulty = "/Script/Maine.EGameDifficulty",
    game_mode = "/Script/Maine.EGameMode",
    game_type = "/Script/Maine.EGameType",
}
local enum_cache = {}

local function find_enum(path)
    local e = enum_cache[path]
    if e ~= nil then return e end
    local ok, obj = pcall(StaticFindObject, path)
    local valid = false
    if ok and obj then pcall(function() valid = obj:IsValid() end) end
    e = valid and obj or false
    enum_cache[path] = e
    if not e then log_once("enum:" .. path, "enum %s introuvable", path) end
    return e
end

-- "ETimeOfDay::Morning" -> "Morning" ; nil si l'enum ou la valeur est inconnue
local function enum_name(path, value)
    if type(value) ~= "number" then return nil end
    local e = find_enum(path)
    if not e then return nil end
    local ok, name = pcall(function() return e:GetNameByValue(value):ToString() end)
    if ok and type(name) == "string" and name ~= "None" and name ~= "" then
        return (name:gsub("^.*::", ""))
    end
    return nil
end

local function dump_enum(out, path)
    local e = find_enum(path)
    if not e then
        out[#out + 1] = "== enum " .. path .. " : introuvable"
        return
    end
    out[#out + 1] = "== enum " .. path
    pcall(function()
        e:ForEachName(function(name, value)
            local text = "?"
            pcall(function() text = name:ToString() end)
            out[#out + 1] = string.format("  %-44s = %s", text, tostring(value))
        end)
    end)
end

-- ------------------------------------------------------------------ diagnostic
local diag_written = false

local function write_diag(gs)
    if diag_written then return end
    diag_written = true
    local out = { "Grounded2RPC diag - mod " .. MOD_VERSION .. " - " .. os.date("%Y-%m-%d %H:%M:%S"), "" }
    for _, path in ipairs({ ENUMS.time_of_day, ENUMS.difficulty, ENUMS.game_mode, ENUMS.game_type, "/Script/Maine.ESaveGamePlayerCountType" }) do
        dump_enum(out, path)
    end
    dump_object(out, "SurvivalGameState", gs or instance("SurvivalGameState"))
    dump_object(out, "CalendarComponent", instance("CalendarComponent"))
    dump_object(out, "ZoneManagerComponent", instance("ZoneManagerComponent"))
    dump_object(out, "PartyComponent", instance("PartyComponent"))
    dump_object(out, "SurvivalModeManagerComponent", instance("SurvivalModeManagerComponent"))
    dump_object(out, "SaveLoadManager", instance("SaveLoadManager"))
    dump_object(out, "GameInstance", UEHelpers.GetGameInstance())
    local ok, err = write_file(DIAG_PATH, table.concat(out, "\n") .. "\n")
    if ok then
        log("diagnostic écrit : %s", DIAG_PATH)
    else
        log("diagnostic non écrit (%s)", tostring(err))
    end
end

-- --------------------------------------------------------------------- collecte
local function valid_object(v)
    if type(v) ~= "userdata" then return nil end
    local ok, valid = pcall(function() return v:IsValid() end)
    if ok and valid then return v end
    return nil
end

-- composant du GameState (propriété), sinon recherche globale
local function component(gs, prop_name, class_name)
    if gs then
        local c = valid_object(get_prop(gs, prop_name))
        if c then return c end
    end
    return instance(class_name)
end

-- FGuid -> "AAAAAAAABBBBBBBBCCCCCCCCDDDDDDDD" (même écriture que world_id dans le header de sauvegarde)
local function guid_string(guid)
    local ok, s = pcall(function()
        return string.format("%08X%08X%08X%08X",
            guid.A & 0xFFFFFFFF, guid.B & 0xFFFFFFFF, guid.C & 0xFFFFFFFF, guid.D & 0xFFFFFFFF)
    end)
    if ok and s ~= "00000000000000000000000000000000" then return s end
    return nil
end

local function collect()
    local data = { ts = os.time(), mod = MOD_VERSION, in_world = false }

    local gi = UEHelpers.GetGameInstance()
    if gi and gi:IsValid() then
        local menu = call0(gi, "IsCurrentLevelMenuLevel")
        if type(menu) == "boolean" then data.menu_level = menu end
        local single = call0(gi, "GetIsSinglePlayer")
        if type(single) == "boolean" then data.single_player = single end
        local loading = get_prop(gi, "IsInMapLoad")
        if type(loading) == "boolean" then data.loading = loading end
    end

    local gs = instance("SurvivalGameState")
    if gs then
        local name = to_plain(get_prop(gs, "PlaythroughName"))
        if type(name) == "string" and name ~= "" then data.world_name = name end
        local guid = get_prop(gs, "PlaythroughGuid")
        if guid ~= nil then data.world_id = guid_string(guid) end
        local ok, n = pcall(function() return gs.PlayerArray:GetArrayNum() end)
        if not ok then ok, n = pcall(function() return #gs.PlayerArray end) end
        if ok and type(n) == "number" then data.players = n end
        local role = to_plain(get_prop(gs, "Role"))
        if type(role) == "number" then data.host = (role == 3) end   -- ROLE_Authority
        local cutscene = call0(gs, "GetInCutscene")
        if type(cutscene) == "boolean" then data.cutscene = cutscene end
    end

    local cal = component(gs, "CalendarComponent", "CalendarComponent")
    if cal then
        data.in_world = true
        data.day = call0(cal, "GetDay")
        data.hour = call0(cal, "GetHour")
        data.minute = call0(cal, "GetMinute")
        data.time_of_day = call0(cal, "GetTimeOfDay")
        data.time_of_day_name = enum_name(ENUMS.time_of_day, data.time_of_day)
        data.is_day = call0(cal, "IsDayTime")
    end

    local zm = component(gs, "ZoneManagerComponent", "ZoneManagerComponent")
    if zm then
        local handle = call0(zm, "GetLocalZoneRowHandle")
        if handle ~= nil then
            local ok, row = pcall(function() return handle.RowName:ToString() end)
            if ok and type(row) == "string" and row ~= "None" then
                data.zone_row = row
            elseif not ok then
                log_once("zone_row", "RowName illisible : %s", tostring(row))
            end
        end
    end

    local party = component(gs, "PartyComponent", "PartyComponent")
    if party then
        local n = call0(party, "GetNumPartyMembers")
        if type(n) == "number" then data.party_members = n end
    end

    local mm = component(gs, "SurvivalModeManagerComponent", "SurvivalModeManagerComponent")
    if mm then
        data.difficulty = call0(mm, "GetGameDifficulty")
        data.difficulty_name = enum_name(ENUMS.difficulty, data.difficulty)
        data.game_mode = call0(mm, "GetGameMode")
        data.game_mode_name = enum_name(ENUMS.game_mode, data.game_mode)
        data.game_type = call0(mm, "GetGameType")
        data.game_type_name = enum_name(ENUMS.game_type, data.game_type)
        data.new_game_plus = call0(mm, "IsNewGamePlus")
    end

    -- objets résiduels après un retour au menu : le GameInstance fait foi
    if data.in_world and data.menu_level == true then
        data.in_world = false
    end
    return data, gs
end

-- ----------------------------------------------------------------------- boucle
local last_payload = nil
local last_write = 0
local was_in_world = nil

local function tick()
    local ok, data, gs = pcall(collect)
    if not ok then
        log_once("collect", "collecte échouée : %s", tostring(data))
        data = { ts = os.time(), mod = MOD_VERSION, in_world = false, error = tostring(data) }
    end

    if data.in_world ~= was_in_world then
        was_in_world = data.in_world
        if data.in_world then
            log("en partie · %s · jour %s %s:%s (%s) · zone %s · %s joueur(s) · %s",
                tostring(data.world_name), tostring(data.day), tostring(data.hour), tostring(data.minute),
                tostring(data.time_of_day_name), tostring(data.zone_row), tostring(data.players), tostring(data.difficulty_name))
            write_diag(gs)
        else
            log("hors partie (menus)")
        end
    end

    local ts = data.ts
    data.ts = nil
    local payload = json_object(data)
    data.ts = ts
    local now = os.time()
    if payload ~= last_payload or now - last_write >= HEARTBEAT_S then
        local wok, err = write_file(LIVE_PATH, json_object(data))
        if wok then
            last_payload = payload
            last_write = now
        else
            log_once("write", "écriture impossible dans %s : %s", LIVE_PATH, tostring(err))
        end
    end
end

log("mod %s · sortie : %s", MOD_VERSION, LIVE_PATH)

-- Les objets du jeu ne se lisent que depuis le thread du jeu. Pendant un chargement,
-- ce thread ne dépile pas : on n'empile pas de nouvelle demande tant que la
-- précédente n'a pas tourné.
local tick_pending = false

LoopAsync(POLL_MS, function()
    if not tick_pending then
        tick_pending = true
        ExecuteInGameThread(function()
            tick_pending = false
            local ok, err = pcall(tick)
            if not ok then log_once("tick", "erreur : %s", tostring(err)) end
        end)
    end
    return false
end)
