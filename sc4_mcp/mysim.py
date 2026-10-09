"""My Sims: the five Sims a player can move into the city (re/agents/lua-udi Q5, LIVE_FACTS Phase 3).

The agent simulator (city +0x1AC) keeps five cISC4MySim* at [agent+0x14][0..4]; read through the interface's own
getters (slot 20 IsActive, 17 age, 16 sign, 18 male, 19 wealth, 25 home name, 26 job name, 11 / 12 residence /
job occupants, 14 location, 3 AsAdvisor -> the name at advisor +0x10).

Moving a Sim in is the player's path: the My Sims panel (command ToggleMySimPanel, root 0xCA1F1D9C) -> a free
slot's button -> the "Select A My Sim" dialog (root 0x6A243D9E) -> "Move In My Sim" -> the move-in tool picks a
house under the pointer (view PickOccupant; SiMCP's virtual pointer answers the house on the chosen cell).
"""

from __future__ import annotations

import struct
import time

from . import dialogs, memory, pointer

C_AGENT = 0x1AC
PANEL_ROOT = 0xCA1F1D9C
SLOT_BUTTONS = [0x8A8F410C, 0x8A8F410D, 0x8A8F410E, 0x8A8F410F, 0x8A8F4120]
SELECT_ROOT = 0x6A243D9E
# cISC4MySim::ZodiacSign order (= the dialog's sign list)
SIGNS = ["capricorn", "aquarius", "pisces", "aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra",
         "scorpio", "sagittarius"]
NAME_EDIT, SIGN_COMBO, IID_TEXT_EDIT, IID_COMBO = 0x8A243F1F, 0xAA243F5E, 0x231A1C57, 0x412CE496
EDIT_SET_TEXT, COMBO_SET_SELECTION = 49, 28
GENDER_LABEL = 0xEA243F57
# the "Select A My Sim" dialog's faces: button, preset name, sign, gender (the face sets all three)
FACES = [
    (0x6A243F17, "Deuce Flyer", "leo", "male"), (0xAA243F10, "Damien Flogisto", "virgo", "male"),
    (0x8A243F08, "Gustav Knifenfork", "aries", "male"), (0x6A243EFE, "Carmine Mercury", "gemini", "male"),
    (0xCA243EF3, "Hagar Topeka", "taurus", "male"), (0x2A243EEC, "Tad Bittoomuch", "pisces", "male"),
    (0xAA243EE2, "Lars Overdale", "virgo", "male"), (0x8A243EDB, "Omar Magenta", "cancer", "male"),
    (0xCA243ED1, "Theodore McGinty", "pisces", "male"), (0x8A243EC9, "Bob Newbie", "gemini", "male"),
    (0x6A243EC1, "Eve Tomayo", "aries", "female"), (0xEA243EB9, "Ophelia Woodard", "libra", "female"),
    (0x2A243F85, "Agnes Liu", "capricorn", "female"), (0x8A243E6C, "Judith Peynter", "leo", "female"),
    (0x2A243E56, "Coco Foto", "leo", "female"), (0x6A243E4E, "Sophia Spumoni", "cancer", "female"),
    (0x0A243E45, "Sandra Waive", "capricorn", "female"), (0xEA243E3D, "Phyllis Glassup", "libra", "female"),
    (0x6A243E35, "Epathia Marker", "aries", "female"), (0xAA243E2D, "Becka Zabeth", "capricorn", "female"),
    (0xAA243E23, "Bella Goth", "capricorn", "female")]
WEALTH = {0: "none", 1: "low", 2: "medium", 3: "high"}


class MySimError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise MySimError("the game's code failed (slot %d, status %d)" % (slot, r.status))
    return r.ret[0] & 0xFFFFFFFF


def _slots(g) -> list[int]:
    p = g.proc
    c = memory.city_pointer(p)
    if not c:
        raise MySimError("no city is open", "load_city opens one")
    agent = p.u32(c + C_AGENT)
    arr = p.u32(agent + 0x14) if agent else 0
    return [p.u32(arr + 4 * i) for i in range(5)] if arr else []


def sims(g) -> list[dict]:
    p = g.proc
    out = []
    for i, ms in enumerate(_slots(g)):
        if not ms or not _v(g, ms, 20) & 0xFF:
            out.append({"slot": i + 1, "active": False})
            continue
        adv = _v(g, ms, 3)
        home, job = _v(g, ms, 25), _v(g, ms, 26)
        d = {"slot": i + 1, "active": True, "name": memory.rz_string(p, ms - 0x80),     # the personal name
             "advisor": memory.rz_string(p, adv + 0x10) if adv else None,
             "age": _v(g, ms, 17) & 0xFF, "sign": SIGNS[_v(g, ms, 16) % 12], "male": bool(_v(g, ms, 18) & 0xFF),
             "wealth": WEALTH.get(_v(g, ms, 19), None), "home": memory.rz_string(p, home) if home else None,
             "job": memory.rz_string(p, job) if job else None}
        s = g.bridge.scratch(0x760)
        p.write(s, bytes(12))
        if _v(g, ms, 14, s) & 0xFF:
            x, _, z = struct.unpack("<3f", p.read(s, 12))
            d["location"] = [round(x / 16, 1), round(z / 16, 1)]
        out.append(d)
    return out


def faces() -> list[dict]:
    return [{"face": i, "preset_name": n, "sign": sg, "gender": gd} for i, (_, n, sg, gd) in enumerate(FACES)]


def _iface(g, win_id: int, iid: int) -> int:
    p, b = g.proc, g.bridge
    w = dialogs.find_window(g, win_id, True)
    if not w:
        raise MySimError("the dialog's control %#x is missing" % win_id)
    out = b.scratch(0x7A0)
    p.write(out, bytes(4))
    b.call_function(p.u32(p.u32(w)), [iid, out], this=w)
    ptr = p.u32(out)
    if not ptr:
        raise MySimError("the dialog's control %#x has no interface %#x" % (win_id, iid))
    b.call_function(p.u32(p.u32(ptr) + 8), [], this=ptr)          # QueryInterface AddRef'd it; the window keeps it
    return ptr


def _open_panel(g) -> None:
    """The My Sim panel must be showing before its slot buttons are pressed: a press on the hidden panel makes its
    handler use an unset member and the game crashes (0x771D42, LIVE_FACTS). Right after a move-in the game hides
    the panel's parents for a moment, so wait for them; toggle only when the panel itself is hidden."""
    p = g.proc
    toggled = False
    for _ in range(25):
        w = dialogs.find_window(g, PANEL_ROOT, False)
        if w:
            own = p.u32(w + dialogs.W_FLAGS) & dialogs.F_VISIBLE
            chain, x = True, p.u32(w + dialogs.W_PARENT)
            while x:
                if not p.u32(x + dialogs.W_FLAGS) & dialogs.F_VISIBLE:
                    chain = False
                    break
                x = p.u32(x + dialogs.W_PARENT)
            if own and chain:
                return
            if not own and not toggled:
                g.bridge.command("ToggleMySimPanel")
                toggled = True
        time.sleep(0.2)
    raise MySimError("the My Sim panel did not open", "the city must be founded (mayor mode); try again")


def move_in(g, x: int, z: int, face: int | str | None = None, name: str = "", sign: str = "") -> dict:
    """Make a My Sim and move it into the house on cell (x, z) through the player's panel, the Select A My Sim
    dialog (face, name, sign) and its move-in tool."""
    free = [i for i, ms in enumerate(_slots(g)) if ms and not _v(g, ms, 20) & 0xFF]
    if not free:
        raise MySimError("all five My Sim slots are taken")
    pick = None
    if face is not None and face != "":
        if isinstance(face, int) or str(face).isdigit():
            k = int(face)
            if not 0 <= k < len(FACES):
                raise MySimError("face is 0-%d" % (len(FACES) - 1), "my_sim_faces lists them")
            pick = FACES[k]
        else:
            hits = [f for f in FACES if f[1].lower() == str(face).lower()]
            if not hits:
                raise MySimError("no face %r" % face, "my_sim_faces lists them")
            pick = hits[0]
    if sign and sign.lower() not in SIGNS:
        raise MySimError("sign is one of %s" % ", ".join(SIGNS))
    if name and (len(name) > 31 or any(ord(ch) < 32 for ch in name)):
        raise MySimError("the name is 1-31 characters")
    if dialogs.is_modal(g):
        raise MySimError("a dialog is open", "dialog_status / close_dialog first (the panel ignores clicks then)")
    occ = pointer.building_at(g, x, z)
    if not occ:
        raise MySimError("no building on cell (%d, %d)" % (x, z), "lots(zone='residential_low') lists houses")
    p, b = g.proc, g.bridge
    try:
        _open_panel(g)
        b.command("GZWinClickButton %d %d" % (SLOT_BUTTONS[free[0]], PANEL_ROOT))
        time.sleep(0.5)
        st = dialogs.status(g)
        if not st["open"] or st["dialogs"][0]["id"] != "0x%08X" % SELECT_ROOT:
            raise MySimError("the Select A My Sim dialog did not open", "dialog_status shows what is open")
        if pick:
            for _ in range(3):                    # the dialog may still be settling: check the gender label it sets
                b.command("GZWinClickButton %d %d" % (pick[0], SELECT_ROOT))
                time.sleep(0.3)
                gw = dialogs.find_window(g, GENDER_LABEL, True)
                if gw and memory.rz_string(p, gw + dialogs.W_CAPTION, 20).lower() == pick[3]:
                    break
            else:
                raise MySimError("the face did not take", "dialog_status shows the dialog")
        if name:
            raw = name.encode("latin-1", "replace")
            buf = b.scratch(0x7C0)
            p.write(buf, raw + bytes(1))
            b.vcall(_iface(g, NAME_EDIT, IID_TEXT_EDIT), EDIT_SET_TEXT, buf, len(raw), 1)
        if sign:
            b.vcall(_iface(g, SIGN_COMBO, IID_COMBO), COMBO_SET_SELECTION, SIGNS.index(sign.lower()), 1)
        dialogs.click(g, "Move In My Sim")
        time.sleep(0.5)
        picks = pointer.click(g, x, z, occupant=occ)
    finally:
        pointer.release(g, occ)
    time.sleep(0.5)
    now = sims(g)
    return {"moved_in": now[free[0]].get("active", False), "sim": now[free[0]], "picks": picks}
