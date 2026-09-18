' Lance la Rich Presence sans fenetre (raccourci a placer dans le dossier Demarrage de Windows).
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run "pythonw -m grounded2_rpc", 0, False
