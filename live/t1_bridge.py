"""Live test 1: the plugin, the inner bridge and the command system (needs SimCity 4 1.1.641 and bridge\\build).

    python live/t1_bridge.py

Starts SiMCP's game (beside a player's instance if one is open) or attaches to it. Checks: the plugin reached
PostAppInit on the main thread, the inner bridge loads and answers on that thread, getters on cISC4App work and agree
with the memory globals, a deliberate fault comes back as status -100 with the game still running, a hot reload
works, and the game's command server runs "ListCommands".
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sc4_mcp import game as gamemod, memory  # noqa: E402

SLOT_APP_GETAPPSTATE = 25
SLOT_APP_GETCITY = 37


def main():
    g = gamemod.Game()
    t0 = time.time()
    st = g.launch()
    print("launch", st, "%.1fs" % (time.time() - t0))
    b, proc = g.bridge, g.proc
    ps = b.plugin_state()
    print("plugin", {k: (hex(v) if isinstance(v, int) else v) for k, v in ps.items()})
    assert ps["app"] and ps["framework"] and ps["command_server"] and ps["message_server"], ps
    assert b.plugin_ping(), "plugin ping"
    r = b.ping()
    print("bridge ping", r)
    assert r.ok and r.ret[1] == ps["main_thread"], "bridge runs on the main thread"
    r = b.vcall(ps["app"], SLOT_APP_GETAPPSTATE)
    print("cISC4App::GetAppState ->", r.ret[0], "memory:", memory.app_state(proc))
    assert r.ok and r.ret[0] == memory.app_state(proc)
    print("[0xB43C94] =", hex(proc.u32(memory.G_APP)), "plugin app =", hex(ps["app"]),
          "vtable", hex(proc.u32(ps["app"])))
    assert proc.u32(memory.G_APP) == ps["app"] and proc.u32(ps["app"]) == memory.APP_VTABLE
    r = b.vcall(ps["app"], SLOT_APP_GETCITY)
    print("cISC4App::GetCity ->", hex(r.ret[0] & 0xFFFFFFFF))
    r = b.call_function(0x10)
    print("fault test", r)
    assert r.status == -100 and proc.alive(), "a fault is caught and the game keeps running"
    assert b.ping().ok
    loads = b.plugin_state()["bridge_loads"]
    b.unload()
    b.attach()
    print("hot reload: loads", loads, "->", b.plugin_state()["bridge_loads"], b.ping())
    c = b.command("ListCommands")
    print("ListCommands -> status", c["status"], "output", len(c["output"]), "chars:", c["output"][:300])
    c2 = b.command("NoSuchCommandAtAll")
    print("unknown command -> status", c2["status"])
    print("OK")


if __name__ == "__main__":
    main()
