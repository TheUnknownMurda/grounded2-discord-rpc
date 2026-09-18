# UE4SS_Grounded2 (runtime UE4SS pour Grounded 2)

Copie du paquet **UE4SS_Grounded2 v1.0.4** (3 septembre 2026) publié par *guestchoop666* sur Nexus Mods :
<https://www.nexusmods.com/grounded2/mods/52>. C'est un build de [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS)
3.0.1 (`Git SHA ca6f9b4c`) avec des signatures spécifiques au jeu (`UE4SS_Signatures/`). Licence MIT, voir
`ue4ss/LICENSE`.

Contenu : `dwmapi.dll` (proxy chargé par le jeu) et le dossier `ue4ss/` (runtime, réglages, mods de base).
Le fichier `ue4ss/UE4SS.log` généré à l'exécution n'est pas versionné ; le mod `Grounded2RPC` vit dans
`../Grounded2RPC` et est copié séparément.

`tools/install_mod.py` copie ces fichiers à côté de l'exe du jeu quand `dwmapi.dll` n'y est pas encore
(`--reinstall-ue4ss` pour écraser une installation existante). Pour retirer UE4SS : supprimer `dwmapi.dll` et
`ue4ss/` du dossier des binaires du jeu.

Testé avec le jeu 0.310.8 (Game Pass, `WinGDK`, UE 5.6). En cas de mise à jour du jeu qui casse UE4SS,
récupérer la nouvelle version du paquet sur Nexus et remplacer ce dossier.
