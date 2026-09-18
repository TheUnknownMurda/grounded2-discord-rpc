"""Détection du jeu en cours d'exécution et lecture de ses réglages (Windows, ctypes uniquement)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable, Optional

log = logging.getLogger(__name__)

DEFAULT_PROCESS_NAMES = (
    "Grounded2-WinGDK-Shipping.exe",   # Xbox app / Game Pass
    "Grounded2-Win64-Shipping.exe",    # Steam (nom supposé)
)

SETTINGS_INI_GLOB = os.path.join("%LOCALAPPDATA%", "Augusta", "Saved", "Config", "Users", "*", "*", "GameUserSettings.ini")

_k32 = ctypes.windll.kernel32
_u32 = ctypes.windll.user32

TH32CS_SNAPPROCESS = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", wt.LONG),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    ]


_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
_k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
_k32.CloseHandle.argtypes = [wt.HANDLE]
_u32.GetForegroundWindow.restype = wt.HWND
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]


@dataclass(frozen=True)
class GameProcess:
    pid: int
    exe_name: str
    start_time: float   # epoch (secondes)


def _process_start_time(pid: int) -> Optional[float]:
    handle = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        times = (wt.FILETIME * 4)()
        if not _k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return None
        raw = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return (raw - 116444736000000000) / 1e7
    finally:
        _k32.CloseHandle(handle)


def find_game(process_names: Iterable[str] = DEFAULT_PROCESS_NAMES) -> Optional[GameProcess]:
    wanted = {n.lower() for n in process_names}
    snapshot = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE or not snapshot:
        return None
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = _k32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in wanted:
                pid = int(entry.th32ProcessID)
                start = _process_start_time(pid) or time.time()
                return GameProcess(pid, entry.szExeFile, start)
            ok = _k32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snapshot)
    return None


def is_foreground(pid: int) -> bool:
    hwnd = _u32.GetForegroundWindow()
    if not hwnd:
        return False
    owner = wt.DWORD(0)
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return owner.value == pid


def read_game_settings() -> dict:
    """Lit les réglages utiles de GameUserSettings.ini (langue, intervalle d'autosave)."""
    import glob

    result: dict = {}
    candidates = glob.glob(os.path.expandvars(SETTINGS_INI_GLOB))
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for path in candidates[:1]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = re.match(r"\s*(LanguageSetting|AutosaveInterval|AutosavesNumber)\s*=\s*(.+?)\s*$", line)
                    if m:
                        result[m.group(1)] = m.group(2)
        except OSError:
            continue
    return result


def installed_version(install_roots: Iterable[str] = ("E:\\XboxGames\\Grounded 2", "C:\\XboxGames\\Grounded 2", "D:\\XboxGames\\Grounded 2")) -> Optional[str]:
    """Version du paquet Xbox d'après MicrosoftGame.config (si trouvé)."""
    for root in install_roots:
        cfg = os.path.join(root, "Content", "MicrosoftGame.config")
        try:
            with open(cfg, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        m = re.search(r'<Identity[^>]*Version="([^"]+)"', text)
        if m:
            return m.group(1)
    return None
