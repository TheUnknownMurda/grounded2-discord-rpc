"""Client minimal du protocole IPC de Discord (Rich Presence), sans dépendance.

Protocole : tube nommé ``\\\\.\\pipe\\discord-ipc-N`` (N = 0..9), trames
``[opcode u32 LE][longueur u32 LE][JSON]``.

    opcode 0  HANDSHAKE   {"v": 1, "client_id": "..."}      → DISPATCH/READY
    opcode 1  FRAME       {"cmd": "SET_ACTIVITY", "args": {"pid": …, "activity": {…}}, "nonce": …}
    opcode 2  CLOSE
    opcode 3  PING / 4 PONG
"""

from __future__ import annotations

import json
import logging
import os
import struct
import uuid
from typing import Optional

log = logging.getLogger(__name__)

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = range(5)


class DiscordNotRunning(ConnectionError):
    pass


class DiscordIPC:
    def __init__(self, client_id: str):
        self.client_id = str(client_id)
        self._pipe = None
        self.user: Optional[dict] = None

    # ------------------------------------------------------------ connexion
    @property
    def connected(self) -> bool:
        return self._pipe is not None

    def connect(self) -> None:
        last_error: Optional[BaseException] = None
        for n in range(10):
            path = rf"\\.\pipe\discord-ipc-{n}"
            try:
                self._pipe = open(path, "r+b", buffering=0)
                break
            except OSError as exc:
                last_error = exc
                continue
        else:
            raise DiscordNotRunning(f"aucun tube discord-ipc-* accessible ({last_error})")
        try:
            self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
            op, payload = self._recv()
        except Exception:
            self.close()
            raise
        if op == OP_CLOSE or payload.get("evt") != "READY":
            message = payload.get("message") or payload.get("data", {}).get("message") or payload
            self.close()
            raise ConnectionError(f"handshake refusé par Discord : {message}")
        self.user = payload.get("data", {}).get("user")
        log.info("connecté à Discord (%s) en tant que %s", payload.get("data", {}).get("config", {}).get("cdn_host", "?"),
                 (self.user or {}).get("username", "?"))

    def close(self) -> None:
        if self._pipe is None:
            return
        try:
            self._send(OP_CLOSE, {})
        except Exception:
            pass
        try:
            self._pipe.close()
        finally:
            self._pipe = None

    # -------------------------------------------------------------- trames
    def _send(self, op: int, payload: dict) -> None:
        if self._pipe is None:
            raise ConnectionError("non connecté")
        data = json.dumps(payload).encode("utf-8")
        self._pipe.write(struct.pack("<II", op, len(data)) + data)

    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._pipe.read(n - len(buf))
            if not chunk:
                raise ConnectionError("Discord a fermé le tube")
            buf += chunk
        return buf

    def _recv(self) -> tuple:
        op, length = struct.unpack("<II", self._read_exact(8))
        body = self._read_exact(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            payload = {}
        if op == OP_PING:
            self._send(OP_PONG, payload)
            return self._recv()
        return op, payload

    def _command(self, cmd: str, args: dict) -> dict:
        nonce = str(uuid.uuid4())
        self._send(OP_FRAME, {"cmd": cmd, "args": args, "nonce": nonce})
        while True:
            op, payload = self._recv()
            if op == OP_CLOSE:
                self.close()
                raise ConnectionError(f"connexion fermée par Discord : {payload}")
            if payload.get("nonce") == nonce:
                if payload.get("evt") == "ERROR":
                    raise RuntimeError(f"Discord a refusé {cmd} : {payload.get('data')}")
                return payload.get("data") or {}
            # événement non sollicité : ignoré

    # ------------------------------------------------------------- activité
    def set_activity(self, activity: Optional[dict], pid: Optional[int] = None) -> dict:
        args = {"pid": int(pid or os.getpid())}
        if activity is not None:
            args["activity"] = activity
        return self._command("SET_ACTIVITY", args)

    def clear_activity(self, pid: Optional[int] = None) -> dict:
        return self.set_activity(None, pid)
