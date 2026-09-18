# Grounded 2 · Discord Rich Presence détaillée

Affiche sur ton profil Discord ce que tu fais dans **Grounded 2** (version Xbox app / Game Pass) :

```
Joue à Grounded 2                                   [logo]  [icône de zone]
Size Don't Matter · Jour 16
📍 Avant-poste des rangers : snack · Nuit 🌙
1:23:45 écoulées
```

- **Ligne 1** : nom du monde et jour en jeu.
- **Ligne 2** : zone où tu te trouves (nom officiel, dans la langue du jeu — 118 zones connues) et moment de la journée (ou l'heure exacte).
- **Info-bulle du logo** : heure en jeu précise et heure/type de la dernière sauvegarde.
- **Petite icône** : surface / sous terre / avant-poste / installation.
- Dans les menus : « Dans les menus · Dernière partie : … ».
- Le chrono « écoulées » démarre au lancement du jeu ; la presence disparaît quand tu quittes.

Aucune dépendance : Python standard uniquement. Par défaut, rien n'est injecté dans le jeu, rien n'est lu en mémoire :
l'outil lit les **sauvegardes** (que le jeu écrit toutes les 5 minutes en autosave, à chaque sauvegarde manuelle
et à la déconnexion) et surveille le **processus** du jeu.

En option, un petit **mod UE4SS** (dossier `mod/`) fournit la zone et l'horloge **en temps réel** (voir
[Temps réel avec UE4SS](#temps-réel-avec-ue4ss-optionnel)) ; sans lui, ou s'il tombe en panne, l'outil retombe
automatiquement sur les sauvegardes.

## Prérequis

- Windows 10/11, **Python 3.11+** (`python --version`).
- Discord (client de bureau, Stable/PTB/Canary) lancé sur le même PC.
- Grounded 2 installé via l'app Xbox / Game Pass (la version Steam est gérée en mode expérimental, voir plus bas).

## Installation (5 minutes)

### 1. Créer l'application Discord

1. Va sur <https://discord.com/developers/applications> → **New Application**.
2. Nomme-la exactement **`Grounded 2`** (c'est ce nom qui s'affiche après « Joue à »).
3. Dans **General Information**, copie l'**Application ID**. Copie `config.example.json` en `config.json`
   (ce fichier est ignoré par git) et colle l'ID dedans :
   ```json
   "client_id": "123456789012345678",
   ```

### 2. Envoyer les images

Dans l'application : **Rich Presence → Art Assets → Add Image(s)**. Envoie les fichiers du dossier `assets/`
en gardant **exactement** ces noms (clés) :

| Fichier                  | Clé                | Rôle                                  |
|--------------------------|--------------------|---------------------------------------|
| `grounded2.png`          | `grounded2`        | grande image (key art du jeu)         |
| `zone_surface.png`       | `zone_surface`     | petite icône : en surface             |
| `zone_underground.png`   | `zone_underground` | petite icône : sous terre / fourmilière |
| `zone_outpost.png`       | `zone_outpost`     | petite icône : avant-poste des rangers |
| `zone_lab.png`           | `zone_lab`         | petite icône : installation / labo    |

`grounded2_icon.png` (la fourmi) est une alternative pour la grande image : envoie-la sous la clé `grounded2_icon`
et mets `"logo": "grounded2_icon"` dans `config.json`. Tu peux aussi mettre une URL `https://…` directe à la place
d'une clé. Les images mettent parfois quelques minutes à apparaître côté Discord.

### 3. Lancer

Double-clique sur **`Grounded2RPC.bat`** (ou `python -m grounded2_rpc` dans le dossier). Laisse la fenêtre ouverte :
elle affiche ce qui est envoyé à Discord. Lance ensuite le jeu (ou l'inverse, peu importe).

Dans Discord, vérifie que **Paramètres → Activité → Confidentialité de l'activité → « Partager votre activité
en cours »** est activé, sinon rien ne s'affiche.

### 4. Démarrage automatique (optionnel)

`Grounded2RPC-silencieux.vbs` lance l'outil sans fenêtre. Pour qu'il démarre avec Windows : `Win + R` →
`shell:startup` → crée-y un raccourci vers ce `.vbs`. Les logs sont dans
`%LOCALAPPDATA%\Grounded2RPC\grounded2_rpc.log`.

## Configuration (`config.json`)

| Clé                             | Défaut     | Description |
|---------------------------------|------------|-------------|
| `client_id`                     | `""`       | Application ID Discord (obligatoire). |
| `language`                      | `"auto"`   | `auto` = langue des textes du jeu (`GameUserSettings.ini`), sinon `fr`, `en`… Les noms de zones existent en fr, en, de, es, es-MX, it, ja, ko, pt-BR, zh-Hans, zh-Hant ; les autres textes en fr et en. |
| `poll_interval_seconds`         | `5`        | Fréquence de vérification du processus et des sauvegardes. |
| `assume_in_world_after_minutes` | `2`        | Sans nouvelle sauvegarde depuis le lancement, considère que tu es en partie (dernière sauvegarde connue) après ce délai. `-1` pour rester sur « Dans les menus » jusqu'à la première sauvegarde. |
| `show_world_name`               | `true`     | Afficher le nom du monde. |
| `clock_mode`                    | `"period"` | `period` (Matin 🌅 / Journée ☀️ / Soir 🌇 / Nuit 🌙), `exact` (`02:43`), `both`, `none`. |
| `show_background_state`         | `false`    | Ajoute « ⏸ En arrière-plan » quand la fenêtre du jeu n'a pas le focus. |
| `party_from_header`             | `"off"`    | Affiche « 2 sur 4 » à partir d'un champ du header (`flag3` ou `slot`) — champ **non confirmé**, voir plus bas. |
| `live_enabled`                  | `true`     | Utiliser `live.json` écrit par le mod UE4SS quand il existe (voir [Temps réel](#temps-réel-avec-ue4ss-optionnel)). |
| `live_paths`                    | …          | Emplacements possibles de `live.json` (`%LOCALAPPDATA%\Grounded2RPC\live.json` en premier). |
| `live_stale_seconds`            | `30`       | Au-delà de cet âge, `live.json` est ignoré → repli sur les sauvegardes. |
| `party_from_live`               | `true`     | Affiche « n sur 4 » d'après le nombre de joueurs vu par le mod (à partir de 2 joueurs). |
| `process_names`                 | …          | Exécutables surveillés (`Grounded2-WinGDK-Shipping.exe` pour Xbox). |
| `steam_save_globs`              | …          | Motifs de fichiers `.sav` Steam (expérimental). |
| `images`                        | …          | Clés d'images (ou URLs) : `logo`, `menu`, `zone_surface`, `zone_underground`, `zone_outpost`, `zone_lab`. |
| `buttons`                       | `[]`       | Jusqu'à 2 boutons `{"label": "…", "url": "https://…"}` (visibles par les autres, pas par toi). |

## Comment ça marche

1. **Processus** : `Grounded2-WinGDK-Shipping.exe` est cherché toutes les 5 s ; son heure de lancement sert de chrono.
2. **Sauvegardes** : la version Xbox stocke les sauvegardes dans
   `%LOCALAPPDATA%\Packages\Microsoft.OE-Augusta_8wekyb3d8bbwe\SystemAppData\wgs\…` (format « wgs »).
   Chaque sauvegarde contient un petit bloc `HeaderData` (~240 octets) que le jeu utilise pour le menu
   « Charger » : version, identifiant du monde, type de sauvegarde, date, **jour/heure en jeu**, carte,
   **zone du joueur** (`Outpost_Snackbar`, `Picnic_Area`…), nom du monde… Voir `grounded2_rpc/save_header.py`.
3. **Zones** : `grounded2_rpc/data/zones.json` relie les 118 lignes de `Table_Zones` du jeu aux noms affichés
   dans les 11 langues (extraits des fichiers du jeu avec `tools/extract_zones.py`).
4. **État** :
   - jeu fermé → presence effacée ;
   - jeu lancé, aucune sauvegarde depuis le lancement → « Dans les menus » (puis « partie supposée » après
     `assume_in_world_after_minutes`) ;
   - une sauvegarde postérieure au lancement → « en partie » avec ses infos.
5. Discord n'accepte qu'une mise à jour toutes les 15 s ; l'outil n'envoie que les changements.

**Fraîcheur des infos** : sans le mod, la zone/le jour sont ceux de la **dernière sauvegarde** (autosave toutes les
5 min par défaut — réglable dans le jeu, plus une sauvegarde manuelle/rapide à tout moment). Ce n'est pas du temps
réel, mais c'est fiable, sans risque pour le jeu et robuste aux mises à jour (le format du header n'a pas changé entre
les versions 0.1.1 et 0.5.0 du jeu). Pour du temps réel, voir la section suivante.

## Temps réel avec UE4SS (optionnel)

[UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) est un runtime de scripting Lua qui se charge dans le jeu via un DLL
proxy (`dwmapi.dll`). Le mod `mod/Grounded2RPC` l'utilise en **lecture seule** : toutes les 2 s il interroge le
`SurvivalGameState` du monde chargé (nom et GUID de la partie, nombre de joueurs) et ses composants
(`CalendarComponent` : jour, heure, minute, période `ETimeOfDay` ; `ZoneManagerComponent` : zone ;
`SurvivalModeManagerComponent` : difficulté `EGameDifficulty`, mode) et écrit `%LOCALAPPDATA%\Grounded2RPC\live.json` :

```json
{"in_world":true,"world_name":"Size Don't Matter","world_id":"…","day":17,"hour":11,"minute":19,
 "time_of_day_name":"Day","zone_row":"Snackbar_Area","players":1,"difficulty_name":"Medium","ts":1789732536,…}
```

L'outil Python lit ce fichier en priorité ; s'il a plus de `live_stale_seconds` (jeu fermé, mod cassé par une mise à
jour…), il revient aux sauvegardes sans rien changer d'autre. La presence affiche alors « en direct (mod UE4SS) » dans
l'info-bulle et, à plusieurs, « n sur 4 » (groupe identifié par le GUID de la partie).

La limite restante est celle de Discord : une mise à jour toutes les **15 s** maximum.

### Installation

1. Installe **UE4SS_Grounded2** ([Nexus Mods, mod 52](https://www.nexusmods.com/grounded2/mods/52)) : extrais
   `dwmapi.dll` et le dossier `ue4ss` **à côté de l'exe du jeu** :
   - Game Pass : `E:\XboxGames\Grounded 2\Content\Augusta\Binaries\WinGDK\` (le dossier est inscriptible) ;
   - Steam : `…\Grounded2\Augusta\Binaries\Win64\`.

   Lance le jeu une fois : `ue4ss\UE4SS.log` doit contenir `Found GUObjectArray` et `Using engine version: 5.6`.
2. Copie le mod :
   ```bash
   python tools/install_mod.py
   ```
   (`--game "E:\XboxGames\Grounded 2"` si le dossier n'est pas détecté, `--uninstall` pour le retirer). Le mod est
   activé par son fichier `enabled.txt` ; `mods.txt` n'est pas modifié.
3. Lance le jeu et entre dans un monde : `ue4ss\UE4SS.log` affiche `[Grounded2RPC] en partie · jour …` et
   `live.json` apparaît. `python -m grounded2_rpc --dump` montre son contenu.

Au premier passage en partie, le mod écrit aussi `live_diag.txt` (valeurs des enums, propriétés et signatures des
classes utilisées) : c'est le fichier à regarder si un champ manque dans `live.json` après une mise à jour du jeu —
le mod n'appelle une fonction que si elle existe et n'attend aucun paramètre, et journalise sinon
`fonction ignorée (paramètres requis)`. Les enums observés (jeu 0.310.8) : `ETimeOfDay` Morning/Day/Evening/Night,
`EGameDifficulty` Mild/Medium/Whoa. Les seuils des périodes viennent du jeu (matin 6 h–10 h, journée 10 h–17 h,
soir 17 h–20 h, nuit sinon) et servent aussi au mode sauvegardes.

### Points d'attention

- **Stabilité** : quelques joueurs signalent des lags puis un plantage après ~1 h avec UE4SS (`Maximum number of
  UObjects exceeded`). L'auteur du paquet conseille `ConsoleEnabled = 0` et `RenderMode = ExternalThread` dans
  `ue4ss\UE4SS-settings.ini`, et de désactiver les mods UE4SS inutiles dans `mods.txt`. Le mod Grounded2RPC ne crée
  aucun objet et ne pose aucun hook.
- **Mises à jour du jeu** : UE4SS peut cesser de fonctionner jusqu'à la mise à jour du paquet Nexus ; l'outil repasse
  alors automatiquement sur les sauvegardes.
- **Écrire un mod pour ce build d'UE4SS** : dans les callbacks `ForEachFunction` / `ForEachProperty` / `ForEachName`,
  ne rien renvoyer pour continuer et `return true` pour arrêter — `return false` corrompt la pile et interrompt
  l'itération au premier élément (`attempt to call a nil value`).

## Champs encore incertains (tu peux aider à les confirmer)

Le header contient 4 octets `flags` (observés `(1, 0, 1, 2)` et `(1, 0, 1, 1)`) et une chaîne `session_mode`
(`""` ou `"Solo"`). Ce n'est **pas** la difficulté : sur un même monde joué en `Medium` (valeur lue par le mod
UE4SS), le 4ᵉ octet alterne entre 1 et 2 d'une autosave à l'autre. Le jeu expose une fonction
`SaveGameHeaderData.RedirectGetLastSavePlayerCountType` (enum `ESaveGamePlayerCountType`) : c'est le candidat le plus
probable. Pour trancher :

1. joue quelques minutes **en solo**, attends une autosave, puis `python tools/dump_saves.py` ;
2. refais la même chose **à deux** ;
3. compare la colonne `flags` : si elle suit le nombre de joueurs, mets `"party_from_header": "flag3"` (inutile avec
   le mod UE4SS, qui donne le nombre de joueurs directement).

## Version Steam (expérimental)

Non testée. L'outil scanne `%LOCALAPPDATA%\Augusta\Saved\SaveGames\**\*.sav` et tente de lire le début de
chaque fichier comme un header. Si ça ne marche pas, ouvre un `.sav` dans un éditeur hexadécimal : le header
devrait apparaître quelque part au début du fichier (chaîne `Augusta_Main` puis `/Game/Blueprints/Table_Zones`) —
adapte `saves.py` en conséquence. Ajoute aussi le vrai nom de l'exécutable Steam dans `process_names`.

## Dépannage

- **`client_id manquant`** : remplis `config.json` (voir Installation, étape 1).
- **`handshake refusé par Discord : Invalid Client ID`** : l'ID est faux ou incomplet.
- **`Discord n'est pas joignable`** : Discord n'est pas lancé (ou tourne en administrateur alors que l'outil non,
  ou l'inverse) ; l'outil réessaie toutes les 20 s.
- **Rien ne s'affiche** : vérifie le paramètre de confidentialité d'activité Discord ; ferme le jeu et relance-le
  si Discord affichait déjà « Grounded 2 » via sa propre détection.
- **Mauvaise langue** : `"language": "fr"` dans `config.json` (le mode `auto` suit la langue des textes du jeu).
- **Images absentes** : les clés dans `config.json` doivent être identiques à celles des Art Assets.
- **Zone affichée comme `Nouvelle Zone`** (nom brut) : nouvelle zone ajoutée par une mise à jour → lance
  `python tools/extract_zones.py --game "E:\XboxGames\Grounded 2"` pour régénérer `zones.json`.

## Outils et tests

- `python -m grounded2_rpc --dump` : liste des sauvegardes décodées.
- `python -m grounded2_rpc --dry-run --once [--simulate]` : affiche l'activité calculée sans rien envoyer
  (`--simulate` fait comme si le jeu tournait).
- `python -m grounded2_rpc --simulate` : envoie une presence réelle à Discord sans lancer le jeu (test visuel).
- `python tools/dump_saves.py [--json]` : tous les champs du header, y compris ceux non affichés.
- `python tools/extract_zones.py` : régénère `grounded2_rpc/data/zones.json` depuis les fichiers du jeu.
- `python tools/install_mod.py [--uninstall]` : installe/retire le mod UE4SS dans le dossier du jeu.
- `python -m unittest discover -s tests` : tests unitaires (`pip install lupa` pour exécuter aussi le mod Lua dans un
  faux environnement UE4SS).
