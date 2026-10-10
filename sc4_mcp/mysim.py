"""My Sims: the five Sims a player can move into the city (re/reports/lua-udi Q5, LIVE_FACTS Phase 3).

The agent simulator (city +0x1AC) keeps five cISC4MySim* at [agent+0x14][0..4]; read through the interface's own
getters (slot 20 IsActive, 17 age, 16 sign, 18 male, 19 wealth, 25 home name, 26 job name, 11 / 12 residence /
job occupants, 14 location, 3 AsAdvisor -> the name at advisor +0x10).

Moving a Sim in is the player's path: the My Sims panel (command ToggleMySimPanel, root 0xCA1F1D9C) -> a free
slot's button -> the "Select A My Sim" dialog (root 0x6A243D9E) -> "Move In My Sim" -> the move-in tool picks a
house under the pointer (view PickOccupant; SiMCP's virtual pointer answers the house on the chosen cell).

Faces of one's own: the dialog also lists the Sims in <user folder>\\MySim\\MySims.dat (the file the game's "import
from The Sims" button writes): a 36 x 36 BMP in that folder each, with a name, gender and sign.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import struct
import time

from . import dialogs, launch, memory, pointer

C_AGENT = 0x1AC
PANEL_ROOT = 0xCA1F1D9C
SLOT_BUTTONS = [0x8A8F410C, 0x8A8F410D, 0x8A8F410E, 0x8A8F410F, 0x8A8F4120]
SELECT_ROOT = 0x6A243D9E
# cISC4MySim::ZodiacSign order (= the dialog's sign list)
SIGNS = ["capricorn", "aquarius", "pisces", "aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra",
         "scorpio", "sagittarius"]
NAME_EDIT, SIGN_COMBO, IID_TEXT_EDIT, IID_COMBO = 0x8A243F1F, 0xAA243F5E, 0x231A1C57, 0x412CE496
EDIT_SET_TEXT, COMBO_SET_SELECTION = 49, 28
EDIT_TEXT = 0xE0                     # the name box's text: begin / end pointers
# the dialog's 21 face buttons in its own order (0xAB5208): button i shows entry order[start + i]
FACE_BUTTONS = [0xAA243E23, 0xAA243E2D, 0x6A243E35, 0xEA243E3D, 0x0A243E45, 0x6A243E4E, 0x2A243E56, 0x8A243E6C,
                0x2A243F85, 0xEA243EB9, 0x6A243EC1, 0x8A243EC9, 0xCA243ED1, 0x8A243EDB, 0xAA243EE2, 0x2A243EEC,
                0xCA243EF3, 0x6A243EFE, 0x8A243F08, 0xAA243F10, 0x6A243F17]
PAGE_BUTTON = 0x12345000             # + page - first page shown (six page buttons)
# the dialog object (root window +0x10C is its command listener at object +8): entries 0x30 bytes each
W_LISTENER, D_ORDER, D_START, D_COUNT, D_PAGE_BASE, D_ENTRIES = 0x10C, 0x14, 0x3C, 0x40, 0x44, 0x50
E_IMAGE_FILE, E_NAME, E_MALE, E_SIGN = 0x08, 0x1C, 0x2C, 0x2D
# the game's own faces: preset name, sign, gender (the face sets all three)
FACES = [
    ("Deuce Flyer", "leo", "male"), ("Damien Flogisto", "virgo", "male"), ("Gustav Knifenfork", "aries", "male"),
    ("Carmine Mercury", "gemini", "male"), ("Hagar Topeka", "taurus", "male"), ("Tad Bittoomuch", "pisces", "male"),
    ("Lars Overdale", "virgo", "male"), ("Omar Magenta", "cancer", "male"), ("Theodore McGinty", "pisces", "male"),
    ("Bob Newbie", "gemini", "male"), ("Eve Tomayo", "aries", "female"), ("Ophelia Woodard", "libra", "female"),
    ("Agnes Liu", "capricorn", "female"), ("Judith Peynter", "leo", "female"), ("Coco Foto", "leo", "female"),
    ("Sophia Spumoni", "cancer", "female"), ("Sandra Waive", "capricorn", "female"),
    ("Phyllis Glassup", "libra", "female"), ("Epathia Marker", "aries", "female"),
    ("Becka Zabeth", "capricorn", "female"), ("Bella Goth", "capricorn", "female")]
WEALTH = {0: "none", 1: "low", 2: "medium", 3: "high"}
DAT_NAME, DAT_MAGIC, FACE_PX = "MySims.dat", 0x4A32E4AA, 36


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


def _folder() -> str:
    return os.path.join(launch.USER_DIR, "MySim")


def read_dat(path: str) -> list[dict]:
    """MySims.dat: magic 0x4A32E4AA, then per Sim: name (byte length + text), male (byte), sign (byte), image
    file name without .bmp (byte length + text) - the game's reader at 0x43B860."""
    try:
        data = open(path, "rb").read()
    except OSError:
        return []
    if len(data) < 4 or struct.unpack_from("<I", data)[0] != DAT_MAGIC:
        return []
    out, i = [], 4
    while i < len(data):
        n = data[i]
        name = data[i + 1:i + 1 + n].decode("latin-1")
        i += 1 + n
        if i + 3 > len(data):
            break
        male, sign, m = data[i], data[i + 1], data[i + 2]
        image = data[i + 3:i + 3 + m].decode("latin-1")
        i += 3 + m
        out.append({"name": name, "gender": "male" if male else "female", "sign": SIGNS[sign % 12],
                    "image": image + ".bmp"})
    return out


def write_dat(path: str, sims: list[dict]) -> None:
    out = bytearray(struct.pack("<I", DAT_MAGIC))
    for s in sims:
        name = s["name"].encode("latin-1")
        image = s["image"][:-4].encode("latin-1") if s["image"].lower().endswith(".bmp") else \
            s["image"].encode("latin-1")
        out += bytes([len(name)]) + name + bytes([s["gender"] == "male", SIGNS.index(s["sign"]), len(image)]) + image
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, path)


def custom_faces() -> list[dict]:
    return read_dat(os.path.join(_folder(), DAT_NAME))


def faces() -> list[dict]:
    own = [{"face": i, "preset_name": n, "sign": sg, "gender": gd} for i, (n, sg, gd) in enumerate(FACES)]
    return own + [{"face": len(FACES) + i, "preset_name": c["name"], "sign": c["sign"], "gender": c["gender"],
                   "custom": True, "image": c["image"]} for i, c in enumerate(custom_faces())]


def face_picture(image_path: str = "", skin=(232, 190, 160), hair=(90, 60, 35),
                 shirt=(60, 100, 170), background=(150, 185, 215)):
    """A 36 x 36 face: a photo or picture cropped to its centre square and scaled, or a simple drawn one."""
    from PIL import Image, ImageDraw
    if image_path:
        try:
            im = Image.open(image_path).convert("RGB")
        except OSError as e:
            raise MySimError("cannot read %s: %s" % (image_path, e))
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        return im.resize((FACE_PX, FACE_PX), Image.LANCZOS)
    big = 4 * FACE_PX                                   # drawn large and scaled down: smooth edges
    im = Image.new("RGB", (big, big), tuple(background))
    d = ImageDraw.Draw(im)
    k = big / 36.0

    def box(x0, y0, x1, y1):
        return [x0 * k, y0 * k, x1 * k, y1 * k]
    d.ellipse(box(4, 27, 32, 46), fill=tuple(shirt))                       # shoulders
    d.rectangle(box(15, 22, 21, 29), fill=tuple(skin))                     # neck
    d.ellipse(box(9, 6, 27, 27), fill=tuple(skin))                         # face
    d.chord(box(8, 3, 28, 20), 180, 360, fill=tuple(hair))                 # hair
    for ex in (14, 22):
        d.ellipse(box(ex - 1.3, 14, ex + 1.3, 16.6), fill=(40, 30, 25))    # eyes
    d.arc(box(14, 17, 22, 23), 20, 160, fill=(150, 60, 50), width=int(k))  # smile
    return im.resize((FACE_PX, FACE_PX), Image.LANCZOS)


def design_face(name: str, gender: str = "male", sign: str = "aries", image_path: str = "", skin=None, hair=None,
                shirt=None) -> dict:
    """Add a face of one's own to the Select A My Sim dialog: <user folder>\\MySim\\<name>.bmp (36 x 36) and its
    entry in MySims.dat. The dialog reads them each time it opens."""
    name = name.strip()
    if not 1 <= len(name) <= 31 or any(ord(ch) < 32 or ord(ch) > 255 for ch in name):
        raise MySimError("the name is 1-31 characters (latin-1)")
    if gender not in ("male", "female"):
        raise MySimError("gender is male or female")
    if sign.lower() not in SIGNS:
        raise MySimError("sign is one of %s" % ", ".join(SIGNS))
    if any(n.lower() == name.lower() for n, _, _ in FACES):
        raise MySimError("%r is one of the game's own faces" % name, "choose another name")
    folder = _folder()
    if os.path.realpath(folder) != os.path.abspath(folder) or not os.path.realpath(folder).lower().startswith(
            os.path.realpath(launch.USER_DIR).lower()):
        raise MySimError("the MySim folder is not SiMCP's own")
    os.makedirs(folder, exist_ok=True)
    kw = {k: tuple(v) for k, v in (("skin", skin), ("hair", hair), ("shirt", shirt)) if v}
    im = face_picture(image_path, **kw)
    stem = re.sub(r"[^A-Za-z0-9 _-]", "", name).strip()[:40] or "face"
    im.save(os.path.join(folder, stem + ".bmp"), "BMP")
    path = os.path.join(folder, DAT_NAME)
    sims = [s for s in read_dat(path) if s["name"].lower() != name.lower()]
    sims.append({"name": name, "gender": gender, "sign": sign.lower(), "image": stem + ".bmp"})
    write_dat(path, sims)
    buf = io.BytesIO()
    im.resize((FACE_PX * 4, FACE_PX * 4)).save(buf, "PNG")
    return {"name": name, "gender": gender, "sign": sign.lower(), "image": os.path.join(folder, stem + ".bmp"),
            "face": len(FACES) + len(sims) - 1, "png": buf.getvalue(),
            "note": "move_in_sim(x, z, face=%r) moves a Sim with this face in" % name}


def remove_face(name: str) -> dict:
    """Take a face of one's own out of the dialog; its picture moves to SiMCP's backups. A city keeps its Sims'
    picture file names: a Sim whose picture is gone shows a blank face (no harm otherwise)."""
    path = os.path.join(_folder(), DAT_NAME)
    sims = read_dat(path)
    hit = [s for s in sims if s["name"].lower() == name.strip().lower()]
    if not hit:
        raise MySimError("no face of one's own called %r" % name, "my_sim_faces lists them")
    write_dat(path, [s for s in sims if s is not hit[0]])
    src = os.path.join(_folder(), hit[0]["image"])
    moved = None
    if os.path.exists(src) and not any(s["image"].lower() == hit[0]["image"].lower() for s in sims
                                       if s is not hit[0]):
        dest = os.path.join(launch.ROOT, "backups", "MySim-%s" % time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(dest, exist_ok=True)
        moved = shutil.move(src, os.path.join(dest, hit[0]["image"]))
    return {"removed": hit[0]["name"], "picture_moved_to": moved}


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
    the panel's parents for a moment, so wait for them; toggle only when the panel itself is hidden. While a Sim's
    own panel shows, the first toggle only closes it: toggle again after a moment."""
    p = g.proc
    toggled = False
    for k in range(25):
        if k in (8, 16):
            toggled = False
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


def _name_box(g) -> str:
    p = g.proc
    w = dialogs.find_window(g, NAME_EDIT, True)
    if not w:
        return ""
    a, e = struct.unpack("<II", p.read(w + EDIT_TEXT, 8))
    return p.read(a, min(e - a, 64)).decode("latin-1") if a and 0 <= e - a else ""


def _dialog_list(g) -> tuple[int, list[str]]:
    """The dialog's faces in its current order (it sorts them: gender, recent, A-Z) and the first one shown."""
    p = g.proc
    w = dialogs.find_window(g, SELECT_ROOT, True)
    lst = p.u32(w + W_LISTENER) if w else 0
    if not lst:
        raise MySimError("the Select A My Sim dialog is not open")
    d = lst - 8
    order, n, ent = p.u32(d + D_ORDER), p.u32(d + D_COUNT), p.u32(d + D_ENTRIES)
    if not (order and ent and 0 < n < 1000):
        raise MySimError("the dialog's face list is unreadable")
    names = []
    for k in struct.unpack("<%dI" % n, p.read(order, 4 * n)):
        a, e = struct.unpack("<II", p.read(ent + 0x30 * k + E_NAME, 8))
        names.append(p.read(a, min(e - a, 64)).decode("latin-1") if a and 0 <= e - a else "")
    return p.u32(d + D_START), names


def _choose_face(g, name: str) -> None:
    """Show the face's page and press its button: button i shows the dialog's entry order[start + i]; a page button
    sets start = page * 21 (the last page ends at the last face). The name box then shows the face's name."""
    p, b = g.proc, g.bridge
    for _ in range(3):
        start, names = _dialog_list(g)
        hits = [j for j, n in enumerate(names) if n.lower() == name.lower()]
        if not hits:
            raise MySimError("the dialog has no face %r" % name, "my_sim_faces lists them; a face of one's own "
                             "needs its picture in the MySim folder")
        j = hits[0]
        if not start <= j < start + len(FACE_BUTTONS):
            w = dialogs.find_window(g, SELECT_ROOT, True)
            base = p.u32(p.u32(w + W_LISTENER) - 8 + D_PAGE_BASE)
            page = j // len(FACE_BUTTONS) - base
            if not 0 <= page < 6:
                raise MySimError("the face is on a page the dialog does not offer now")
            b.command("GZWinClickButton %d %d" % (PAGE_BUTTON + page, SELECT_ROOT))
            time.sleep(0.3)
            start, names = _dialog_list(g)
            if not start <= j < start + len(FACE_BUTTONS):
                continue
        b.command("GZWinClickButton %d %d" % (FACE_BUTTONS[j - start], SELECT_ROOT))
        time.sleep(0.3)
        if _name_box(g).lower() == name.lower():
            return
    raise MySimError("the face did not take", "dialog_status shows the dialog")


def move_in(g, x: int, z: int, face: int | str | None = None, name: str = "", sign: str = "") -> dict:
    """Make a My Sim and move it into the house on cell (x, z) through the player's panel, the Select A My Sim
    dialog (face, name, sign) and its move-in tool."""
    free = [i for i, ms in enumerate(_slots(g)) if ms and not _v(g, ms, 20) & 0xFF]
    if not free:
        raise MySimError("all five My Sim slots are taken")
    pick = None
    if face is not None and face != "":
        every = faces()
        if isinstance(face, int) or str(face).isdigit():
            k = int(face)
            if not 0 <= k < len(every):
                raise MySimError("face is 0-%d" % (len(every) - 1), "my_sim_faces lists them")
            pick = every[k]["preset_name"]
        else:
            hits = [f for f in every if f["preset_name"].lower() == str(face).strip().lower()]
            if not hits:
                raise MySimError("no face %r" % face, "my_sim_faces lists them")
            pick = hits[0]["preset_name"]
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
            _choose_face(g, pick)
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
