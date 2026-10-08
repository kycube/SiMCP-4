"""Talking to the SiMCP plugin and its inner bridge inside SimCity 4.

The plugin (simcp4.dll, in SiMCP's own user Plugins folder) exports a status block `g_simcp` and owns a
message-only window on the game's main thread. The inner bridge (simcp4bridge.dll) is staged here as a
content-addressed copy in %TEMP%\\simcp4 and loaded by the plugin on request, so a rebuilt bridge is picked up
without restarting the game. A request is written into the inner bridge's block, then WM_SIMCP with the op number
is sent to the plugin's window; the op runs on the main thread under SEH (status -100 = a fault was caught).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import tempfile
import time

from . import identity, win32

PLUG_MAGIC = 0x50344353    # 'SC4P'
BRIDGE_MAGIC = 0x42344353  # 'SC4B'
WM_SIMCP = 0x8000 + 0x4C4
PLUG_PING, PLUG_LOAD, PLUG_UNLOAD = 1, 2, 3
OP_PING, OP_CALL, OP_CALL_SEQ, OP_DEFER, OP_COMMAND, OP_STEP_DAYS = 16, 17, 18, 19, 20, 21

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PACKAGE_DIR, "bridge", "build")
PLUGIN_DLL = os.environ.get("SIMCP4_PLUGIN_DLL") or os.path.join(BUILD_DIR, "simcp4.dll")
BRIDGE_DLL = os.environ.get("SIMCP4_BRIDGE_DLL") or os.path.join(BUILD_DIR, "simcp4bridge.dll")
STAGE_DIR = os.path.join(tempfile.gettempdir(), "simcp4")

# PlugBlock offsets (bridge/simcp4.cpp; checked against the block's own layout[] at attach)
P_READY, P_HWND, P_TID, P_LAYOUT = 8, 12, 16, 20
P_COM, P_FRAMEWORK, P_APP, P_MSGSERVER, P_CMDSERVER = 52, 56, 60, 64, 68
P_HOOKS, P_INCALL = 72, 104
P_BMODULE, P_BBLOCK, P_BLOADS, P_BSTATUS, P_BERROR, P_BPATH = 108, 112, 116, 120, 124, 128
# BridgeBlock offsets (bridge/simcp4bridge.cpp)
B_LAYOUT, B_SEQ, B_OP, B_ARGS, B_STR = 8, 48, 52, 56, 120
B_DONESEQ, B_STATUS, B_RET, B_MSGLEN, B_MSG, B_STATE = 1144, 1148, 1152, 1216, 1220, 3268
B_OUTLEN, B_OUT = 3332, 3336
B_SCRATCH, SCRATCH_SIZE = 7432, 8192
B_PICK = B_SCRATCH + SCRATCH_SIZE   # pickActive, pickPos[3], pickHits, pickInstalled
STR_SIZE = 1024
CALLDESC = struct.Struct("<IIi6i")


class BridgeError(RuntimeError):
    pass


class BridgeResult:
    def __init__(self, status: int, ret: tuple[int, ...], msg: str):
        self.status, self.ret, self.msg = status, ret, msg

    @property
    def ok(self) -> bool:
        return self.status == 0

    def __repr__(self):
        return f"BridgeResult(status={self.status}, ret={self.ret[:6]}, msg={self.msg!r})"


def staged_copy(dll_path: str) -> str:
    """A content-addressed copy of the inner bridge in %TEMP%\\simcp4 (a loaded copy is never overwritten)."""
    data = open(dll_path, "rb").read()
    name = "simcp4bridge-%s.dll" % hashlib.sha1(data).hexdigest()[:12]
    os.makedirs(STAGE_DIR, exist_ok=True)
    dst = os.path.join(STAGE_DIR, name)
    if not os.path.exists(dst):
        tmp = dst + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
    return dst


def install_plugin(user_dir: str, dll_path: str = PLUGIN_DLL) -> str:
    """Copy simcp4.dll into <user_dir>\\Plugins (only SiMCP's own user folder; the game must not be running)."""
    dst = os.path.join(user_dir, "Plugins", "simcp4.dll")
    if os.path.exists(dst) and open(dst, "rb").read() == open(dll_path, "rb").read():
        return dst
    shutil.copyfile(dll_path, dst)
    return dst


def find_game() -> win32.Process | None:
    """The running game we can open, preferring an instance with the SiMCP plugin loaded. Instances started
    elevated (e.g. by GOG Galaxy) cannot be opened by a normal-user server and are skipped."""
    fallback = None
    for pid in win32.find_pids(identity.EXE_NAME):
        try:
            p = win32.Process(pid)
        except win32.WinError:
            continue
        try:
            if "simcp4.dll" in p.modules32():
                if fallback:
                    fallback.close()
                return p
        except win32.WinError:
            pass
        if fallback is None:
            fallback = p
        else:
            p.close()
    return fallback


class Bridge:
    def __init__(self, proc: win32.Process):
        self.proc = proc
        mods = proc.modules32()
        exe = mods.get(identity.EXE_NAME.lower())
        if not exe or exe[0] != identity.IMAGE_BASE:
            raise BridgeError("SimCity 4 is not running at its expected base")
        check = identity.check_exe(exe[1])
        if not check["ok"]:
            raise BridgeError(check["reason"])
        plug = mods.get("simcp4.dll")
        if not plug:
            raise BridgeError("the SiMCP plugin (simcp4.dll) is not loaded: start the game with game_launch, which "
                              "installs it into SiMCP's own user folder")
        self.plug = plug[0] + win32.pe_exports(plug[1])["g_simcp"]
        if proc.u32(self.plug) != PLUG_MAGIC:
            raise BridgeError("unexpected plugin block")
        layout = struct.unpack("<8I", proc.read(self.plug + P_LAYOUT, 32))
        if layout[1] != P_BPATH:
            raise BridgeError("plugin block layout mismatch (rebuild the plugin and restart the game)")
        self.block = 0

    # ---- plugin
    def plugin_state(self) -> dict:
        p, b = self.proc, self.plug
        return {"ready": p.u32(b + P_READY), "hwnd": p.u32(b + P_HWND), "main_thread": p.u32(b + P_TID),
                "com": p.u32(b + P_COM), "framework": p.u32(b + P_FRAMEWORK), "app": p.u32(b + P_APP),
                "message_server": p.u32(b + P_MSGSERVER), "command_server": p.u32(b + P_CMDSERVER),
                "hook_calls": list(struct.unpack("<8I", p.read(b + P_HOOKS, 32))),
                "bridge_module": p.u32(b + P_BMODULE), "bridge_block": p.u32(b + P_BBLOCK),
                "bridge_loads": p.u32(b + P_BLOADS)}

    @property
    def hwnd(self) -> int:
        return self.proc.u32(self.plug + P_HWND)

    def wait_ready(self, timeout: float = 120.0) -> None:
        end = time.time() + timeout
        while time.time() < end:
            r = self.proc.u32(self.plug + P_READY)
            if r == 1 and self.hwnd:
                return
            if r == 0xBAD:
                raise BridgeError("the plugin refused this executable")
            time.sleep(0.25)
        raise BridgeError("the plugin did not become ready (PostAppInit not reached)")

    def plugin_ping(self) -> bool:
        return win32.send_message(self.hwnd, WM_SIMCP, PLUG_PING) == PLUG_MAGIC

    # ---- inner bridge
    def attach(self, dll_path: str = BRIDGE_DLL) -> None:
        """Load the inner bridge (reusing an identical one already loaded)."""
        self.wait_ready()
        staged = staged_copy(dll_path)
        current = self.proc.read(self.plug + P_BPATH, 520).decode("utf-16-le", "replace").split("\0", 1)[0]
        if self.proc.u32(self.plug + P_BMODULE) and os.path.normcase(current) == os.path.normcase(staged):
            self.block = self.proc.u32(self.plug + P_BBLOCK)
        else:
            path = staged.encode("utf-16-le") + b"\0\0"
            if len(path) > 520:
                raise BridgeError("staging path too long: %s" % staged)
            self.proc.write(self.plug + P_BPATH, path)
            st = win32.send_message(self.hwnd, WM_SIMCP, PLUG_LOAD)
            if st != 0:
                raise BridgeError("loading the inner bridge failed (status %d, error %d)"
                                  % (st, self.proc.u32(self.plug + P_BERROR)))
            self.block = self.proc.u32(self.plug + P_BBLOCK)
        if not self.block or self.proc.u32(self.block) != BRIDGE_MAGIC:
            raise BridgeError("inner bridge block not found")
        lay = struct.unpack("<8I", self.proc.read(self.block + B_LAYOUT, 32))
        if (lay[1], lay[2], lay[3], lay[4], lay[5], lay[6], lay[7]) != (B_SEQ, B_STR, B_DONESEQ, B_STATE,
                                                                     B_OUTLEN + 4, B_SCRATCH, B_PICK):
            raise BridgeError("inner bridge layout mismatch %r" % (lay,))

    def unload(self) -> int:
        self.block = 0
        return win32.send_message(self.hwnd, WM_SIMCP, PLUG_UNLOAD)

    def call(self, op: int, args=(), raw: bytes | None = None, timeout_ms: int = 15000) -> BridgeResult:
        if not self.block:
            self.attach()
        p, b = self.proc, self.block
        a = list(args)[:16] + [0] * (16 - min(16, len(args)))
        p.write(b + B_ARGS, struct.pack("<16I", *[x & 0xFFFFFFFF for x in a]))
        if raw is not None:
            if len(raw) > STR_SIZE:
                raise BridgeError("request too large")
            p.write(b + B_STR, raw)
        seq = (p.u32(b + B_SEQ) + 1) & 0xFFFFFFFF
        p.write(b + B_SEQ, struct.pack("<II", seq, op))
        status = win32.send_message(self.hwnd, WM_SIMCP, op, timeout_ms=timeout_ms)
        ret = struct.unpack("<16i", p.read(b + B_RET, 64))
        n = p.u32(b + B_MSGLEN)
        msg = p.read(b + B_MSG, min(n, 2047)).decode("latin-1") if n else ""
        return BridgeResult(status, ret, msg)

    def scratch(self, offset: int = 0) -> int:
        """An address in the bridge's scratch area (8 KB the game never uses) for call arguments and outputs."""
        if not self.block:
            self.attach()
        if not 0 <= offset < SCRATCH_SIZE:
            raise BridgeError("scratch offset out of range")
        return self.block + B_SCRATCH + offset

    def pick_installed(self) -> bool:
        if not self.block:
            self.attach()
        return bool(self.proc.u32(self.block + B_PICK + 20))

    def set_pick(self, pos: tuple[float, float, float] | None, ttl_ms: int = 3000) -> None:
        """Point the virtual pointer at a world position (metres) for at most ttl_ms, or release it (None)."""
        if not self.block:
            self.attach()
        if pos is None:
            self.proc.write(self.block + B_PICK, struct.pack("<I", 0))
        else:
            self.proc.write(self.block + B_PICK + 4, struct.pack("<3f", *pos))
            deadline = (win32.k32.GetTickCount() + ttl_ms) & 0xFFFFFFFF
            self.proc.write(self.block + B_PICK, struct.pack("<I", deadline or 1))

    def faults(self) -> int:
        """Exceptions the bridge caught inside game code since it loaded: the game may be in an inconsistent state
        afterwards (a simulator stuck mid-update), so a restart is the safe course."""
        if not self.block:
            return 0
        return self.proc.u32(self.block + B_PICK + 24)

    def pick_hits(self) -> int:
        return self.proc.u32(self.block + B_PICK + 16)

    def ping(self) -> BridgeResult:
        return self.call(OP_PING)

    def call_function(self, addr: int, args=(), this: int = 0) -> BridgeResult:
        """Call addr (thiscall when `this`, else cdecl/stdcall) with up to 12 dword arguments."""
        if len(args) > 12:
            raise BridgeError("at most 12 arguments")
        args = list(args)
        return self.call(OP_CALL, [addr, 1 if this else 0, len(args), this] + args)

    def defer_call(self, addr: int, args=(), this: int = 0) -> BridgeResult:
        args = list(args)[:8]
        return self.call(OP_DEFER, [addr, 1 if this else 0, len(args), this] + args)

    def deferred_state(self) -> dict:
        posted, done, status, ret = struct.unpack("<IIii", self.proc.read(self.block + B_STATE, 16))
        return {"posted": posted, "done": done, "busy": posted != done, "status": status, "ret": ret}

    def call_sequence(self, calls) -> BridgeResult:
        """calls: [(fn_or_slot, this, [args], flags)] where flags may set bit 15 (fn is a vtable slot of this),
        bit 14 (this is an address to read), bits 8..13 (arg j is an address to read). this == -1 means the
        previous call's result. Returns ret[i] = EAX of call i."""
        raw = b""
        for fn, this, args, flags in calls:
            args = list(args)[:6]
            raw += CALLDESC.pack(fn & 0xFFFFFFFF, this & 0xFFFFFFFF, len(args) | flags,
                                 *([x if x < 1 << 31 else x - (1 << 32) for x in args] + [0] * (6 - len(args))))
        return self.call(OP_CALL_SEQ, [len(calls)], raw=raw)

    def vcall(self, obj: int, slot: int, *args) -> BridgeResult:
        """Call virtual method `slot` of `obj` (thiscall)."""
        return self.call_sequence([(slot, obj, list(args), 1 << 15)])

    def command_output(self) -> str:
        n = self.proc.u32(self.block + B_OUTLEN)
        return self.proc.read(self.block + B_OUT, min(n, 4095)).decode("latin-1") if n else ""

    def command(self, line: str, defer: bool = False, timeout_s: float = 30.0) -> dict:
        """Run a game command line through the game's command server ("ListCommands", "LoadRegion MCP Test").
        defer=True runs it from the game's message loop (for commands that open a modal window) and waits up to
        timeout_s for it to finish; a command still waiting on a dialog returns {"pending": true}."""
        raw = line.encode("latin-1") + bytes(1)
        if len(raw) > STR_SIZE:
            raise BridgeError("command line too long")
        r = self.call(OP_COMMAND, [1 if defer else 0], raw=raw)
        if not r.ok:
            raise BridgeError("command failed to run (status %d): %s" % (r.status, r.msg))
        if not defer:
            return {"status": r.ret[0], "output": self.command_output()}
        end = time.time() + timeout_s
        while time.time() < end:
            st = self.deferred_state()
            if not st["busy"]:
                if st["status"] != 0:
                    raise BridgeError("the deferred command crashed (status %d)" % st["status"])
                return {"status": st["ret"], "output": self.command_output()}
            time.sleep(0.1)
        return {"pending": True}

    def step_days(self, days: int, max_ms: int = 250, idle_per_day: int = 1) -> dict:
        """One bounded slice of exact day steps (see bridge/simcp4bridge.cpp StepDays); call again while
        in_progress or until all days are done, letting the game's loop run in between. idle_per_day gives the
        game's idle agents that many passes after each day, as its own loop does between days."""
        r = self.call(OP_STEP_DAYS, [days, max_ms, 0, idle_per_day], timeout_ms=max_ms + 15000)
        if not r.ok:
            raise BridgeError("stepping failed (status %d): %s" % (r.status, r.msg))
        return {"days": r.ret[0], "steps": r.ret[1], "day_number": r.ret[2] & 0xFFFFFFFF, "idle_passes": r.ret[3],
                "one_shots_pending": r.ret[4], "in_progress": bool(r.ret[5]), "message": r.msg}
