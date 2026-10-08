"""The game's windows and dialogs (re/agents/advisors-ui/REPORT.md section Q3; verified in LIVE_FACTS).

The window manager (cIGZWinMgr, system service 0xA417445E) owns every window: a tree from the main window, each
node a cGZWin with id +0x10, a child list +0x44, caption cRZString +0x50, rectangle +0xA8..+0xB4 and flags +0xC8
(1 visible, 2 enabled, 0x1000 = running a modal loop). IsModal (slot 42) says whether a modal dialog is open.
Buttons are pressed with the game's own GZWinClickButton command (it posts a mouse down/up at the button's centre,
as a player's click), so the game reacts exactly as to the player.
"""

from __future__ import annotations

import struct

from . import bridge as bridgemod
from . import memory

SRV_WINMGR, IID_WINMGR = 0xA417445E, 0x5A4
WM_GET_MAIN = 3
WM_IS_MODAL = 42
IID_BUTTON = 0x8810
SLOT_FW_GETSERVICE = 5

W_ID, W_CHILDREN, W_PARENT, W_CAPTION, W_RECT, W_FLAGS = 0x10, 0x44, 0x48, 0x50, 0xA8, 0xC8
F_VISIBLE, F_ENABLED, F_MODAL = 0x1, 0x2, 0x1000

# Known dialog roots (UI layout root ids) -> a name (re/agents/advisors-ui)
KNOWN = {0xAA921F4F: "save or quit", 0x6AAEEC4A: "exit choice", 0x2A96ED21: "save during a disaster",
         0x4A9DB60C: "advisor message", 0xEBB16D71: "mission offer", 0xEBBC081E: "mission result",
         0x4A35B0F2: "tutorial step", 0xEA5E748C: "exit tutorial", 0xAA3AC002: "budget / loans",
         0x6A414973: "establish city", 0x27DF05BE: "obliterate city", 0x6A4D0A59: "edge reconcile",
         0x2A5CFB2C: "missing plug-ins", 0xAA8DEF97: "notice"}


def win_mgr(g) -> int:
    """cIGZWinMgr* from the framework's GetSystemService (the result is written into the bridge's request area)."""
    if getattr(g, "_winmgr", 0):
        return g._winmgr
    b, p = g.bridge, g.proc
    fw = b.plugin_state()["framework"]
    out = b.block + bridgemod.B_STR + 1008
    p.write(out, bytes(4))
    b.call_function(p.u32(p.u32(fw) + 4 * SLOT_FW_GETSERVICE), [SRV_WINMGR, IID_WINMGR, out], this=fw)
    g._winmgr = p.u32(out)
    return g._winmgr


def _children(p, w: int) -> list[int]:
    lst = p.u32(w + W_CHILDREN)
    if not lst:
        return []
    sent = p.u32(lst)
    out, node, n = [], p.u32(sent), 0
    while node and node != sent and n < 2000:
        out.append(p.u32(node + 8))
        node = p.u32(node)
        n += 1
    return out


def _is_button(g, w: int) -> bool:
    p, b = g.proc, g.bridge
    out = b.block + bridgemod.B_STR + 1012
    p.write(out, bytes(4))
    r = b.call_function(p.u32(p.u32(w)), [IID_BUTTON, out], this=w)
    btn = p.u32(out)
    if btn:   # QueryInterface AddRef'd it
        b.call_function(p.u32(p.u32(btn) + 8), [], this=btn)
    return bool(r.ret[0] & 0xFF) and bool(btn)


def _describe(g, w: int, depth: int = 0, max_depth: int = 6) -> dict:
    p = g.proc
    flags = p.u32(w + W_FLAGS)
    x0, y0, x1, y1 = struct.unpack("<4i", p.read(w + W_RECT, 16))
    d = {"id": "0x%08X" % p.u32(w + W_ID), "text": memory.rz_string(p, w + W_CAPTION, 2000),
         "rect": [x0, y0, x1, y1], "enabled": bool(flags & F_ENABLED)}
    if _is_button(g, w):
        d["button"] = True
    kids = [c for c in _children(p, w) if p.u32(c + W_FLAGS) & F_VISIBLE]
    if kids and depth < max_depth:
        d["children"] = [_describe(g, c, depth + 1, max_depth) for c in kids]
    return d


def _modal_windows(g) -> list[int]:
    p = g.proc
    wm = win_mgr(g)
    main = g.bridge.call_function(p.u32(p.u32(wm) + 4 * WM_GET_MAIN), [], this=wm).ret[0] & 0xFFFFFFFF
    out, stack = [], [main]
    while stack:
        w = stack.pop()
        for c in _children(p, w):
            f = p.u32(c + W_FLAGS)
            if not f & F_VISIBLE:
                continue
            if f & F_MODAL:
                out.append(c)
            stack.append(c)
    return out


def is_modal(g) -> bool:
    p = g.proc
    wm = win_mgr(g)
    return bool(g.bridge.call_function(p.u32(p.u32(wm) + 4 * WM_IS_MODAL), [], this=wm).ret[0] & 0xFF)


def _flatten(d: dict, out: list):
    if d.get("text") or d.get("button"):
        out.append(d)
    for c in d.get("children", []):
        _flatten(c, out)


def status(g) -> dict:
    if not is_modal(g):
        return {"open": False}
    dialogs = []
    top = g.proc.u32(win_mgr(g) + 0x38)          # the window manager's current (topmost) modal window
    wins = _modal_windows(g)
    wins.sort(key=lambda w: w != top)
    for w in wins:
        tree = _describe(g, w)
        flat = []
        _flatten(tree, flat)
        rid = int(tree["id"], 16)
        dialogs.append({"id": tree["id"], "kind": KNOWN.get(rid), "title": tree["text"],
                        "texts": [x["text"] for x in flat if not x.get("button") and x["text"]],
                        "buttons": [{"id": x["id"], "label": x["text"], "enabled": x["enabled"]}
                                    for x in flat if x.get("button")]})
    return {"open": True, "dialogs": dialogs}


def click(g, button: str) -> dict:
    """Press a button of the open dialog by its label (case-insensitive, unique part) or id."""
    st = status(g)
    if not st["open"]:
        return {"error": "no dialog is open", "hint": "dialog_status shows open dialogs"}
    d = st["dialogs"][0]                          # the topmost dialog answers first
    key = button.strip().lower()
    hits = [x for x in d["buttons"] if x["id"].lower() == key or x["label"].lower() == key] or \
           [x for x in d["buttons"] if key and key in x["label"].lower()]
    if len(hits) != 1:
        return {"error": "no single button matches %r" % button, "hint": "buttons: %s" % d["buttons"]}
    btn = hits[0]
    r = g.bridge.command("GZWinClickButton %d %d" % (int(btn["id"], 16), int(d["id"], 16)))
    return {"pressed": btn, "dialog": d["kind"] or d["title"], "status": r.get("status")}
