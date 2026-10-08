"""The content server: new buildings and lots for the game, written as plugin files (re/agents/formats).

New content goes into one folder of SiMCP's own user folder, `<UserDir>\\Plugins\\zzz_SiMCP` (never the player's
Plugins folder), loaded after everything else. Each design is one DBPF file with its exemplars; a manifest in
SiMCP's home lists them. The game reads plugins at start-up, so new content appears after game_launch.

Stage 1 (here): a building made from an existing menu lot of the game - its models, props and textures - under new
ids, with its own name, description, costs and menu: a lot exemplar (group 0xA8FBD372) whose building row names
the new building, and a building exemplar with the same parent cohort. Removing a design moves its file to
`<SiMCP home>\\content-disabled` (nothing is deleted).
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import time

from . import dbpf, gamedata, launch

FOLDER = os.path.join(launch.USER_DIR, "Plugins", "zzz_SiMCP")
DISABLED = os.path.join(launch.ROOT, "content-disabled")
MANIFEST = os.path.join(launch.ROOT, "content.json")
G_LOTS = 0xA8FBD372
G_SIMCP_BUILDINGS = 0x5C4D0F00          # SiMCP's own building exemplar group
P_NAME, P_ITEM_NAME, P_ITEM_DESC, P_NAME_KEY, P_DESC_KEY = 0x20, 0x899AFBAD, 0x8A2602A9, 0x8A416A99, 0xCA416AB5
P_PLOP, P_BULLDOZE, P_MONTHLY, P_LOT_KEY, P_GROUPS = 0x49CAC341, 0x099AFACD, 0xEA54D286, 0xEA260589, 0xAA1DD396
LOT_ROW0 = 0x88EDC900


class ContentError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _manifest() -> list[dict]:
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_manifest(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, MANIFEST)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:40] or "design"


def _find_exemplar(tgi_type: int, instance: int, group: int | None = None, not_group: int | None = None):
    d = gamedata._main_dat()
    if d is None:
        raise ContentError("the game's SimCity_1.dat was not found")
    hits = [e for e in d.find(tgi_type, group, instance) if not_group is None or e.group != not_group]
    if not hits:
        return None, None
    e = hits[0]
    return e, dbpf.parse_exemplar(d.read(e))


def _set(props: list[dbpf.Property], pid: int, ptype: int, values, multi: bool = False) -> None:
    for p in props:
        if p.id == pid:
            p.ptype, p.values, p.multi = ptype, values, multi
            return
    props.append(dbpf.Property(pid, ptype, values, multi))


def _drop(props: list[dbpf.Property], *ids: int) -> list[dbpf.Property]:
    return [p for p in props if p.id not in ids]


def _new_ids(taken: set[int], n: int) -> list[int]:
    out = []
    while len(out) < n:
        v = random.getrandbits(32) | 0x10000000
        if v not in taken and v not in out:
            out.append(v)
    return out


def designs() -> list[dict]:
    return _manifest()


def clone_lot(template_lot: int, template_building: int | None, name: str, description: str = "",
              plop_cost: int | None = None, monthly_cost: int | None = None, bulldoze_cost: int | None = None,
              taken: set[int] | None = None) -> dict:
    """Write a new design made from a game lot and its building (both from SimCity_1.dat)."""
    if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
        raise ContentError("give the design a name (1-60 characters)")
    if any(d["name"].lower() == name.lower() and not d.get("disabled") for d in _manifest()):
        raise ContentError("a design named %r exists" % name, "content_designs lists them")
    le, lot = _find_exemplar(dbpf.T_EXEMPLAR, template_lot, G_LOTS)
    if lot is not None and template_building is None:      # the building the game's own lot names
        rows = [p.values for p in lot.props if LOT_ROW0 <= p.id <= 0x88EDCDFF and p.multi and p.values
                and p.values[0] == 0 and len(p.values) >= 13]
        template_building = rows[0][12] if rows else 0
    be, bld = _find_exemplar(dbpf.T_EXEMPLAR, template_building, not_group=G_LOTS)
    if lot is None or bld is None:
        raise ContentError("the template lot or building is not in the game's own data",
                           "use a lot and building id from build_menu (Maxis items)")
    lot_iid, bld_iid = _new_ids(taken or set(), 2)
    # the lot: same rows, the building row (type 0) now names the new building
    lprops = [dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values, p.multi)
              for p in lot.props]
    found = False
    for p in lprops:
        if LOT_ROW0 <= p.id <= 0x88EDCDFF and p.multi and p.values and p.values[0] == 0:
            p.values = p.values[:12] + [bld_iid]
            found = True
    if not found:
        raise ContentError("the template lot has no building row")
    _set(lprops, P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name))
    # the building: same properties, new name, description, costs and lot
    bprops = _drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                  p.multi) for p in bld.props], P_NAME_KEY, P_DESC_KEY)
    _set(bprops, P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name))
    _set(bprops, P_ITEM_NAME, dbpf.PT_STRING, name)
    _set(bprops, P_ITEM_DESC, dbpf.PT_STRING, description or name)
    _set(bprops, P_LOT_KEY, dbpf.PT_UINT32, [lot_iid])
    if plop_cost is not None:
        _set(bprops, P_PLOP, dbpf.PT_SINT64, [int(plop_cost)])
    if monthly_cost is not None:
        old = [p for p in bprops if p.id == P_MONTHLY]
        _set(bprops, P_MONTHLY, dbpf.PT_SINT64, [int(monthly_cost)], multi=old[0].multi if old else True)
    if bulldoze_cost is not None:
        _set(bprops, P_BULLDOZE, dbpf.PT_SINT64, [int(bulldoze_cost)])
    records = [(dbpf.T_EXEMPLAR, G_SIMCP_BUILDINGS, bld_iid, dbpf.build_exemplar(bprops, bld.parent)),
               (dbpf.T_EXEMPLAR, G_LOTS, lot_iid, dbpf.build_exemplar(lprops, lot.parent))]
    os.makedirs(FOLDER, exist_ok=True)
    path = os.path.join(FOLDER, "SiMCP_%s.dat" % _slug(name))
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "file": path, "lot": "0x%08X" % lot_iid, "building": "0x%08X" % bld_iid,
             "template_lot": "0x%08X" % template_lot, "template_building": "0x%08X" % template_building,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = _manifest()
    items.append(entry)
    _save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch, then build_menu")


def disable(name: str) -> dict:
    """Take a design out of the game: its file moves to SiMCP's content-disabled folder (not deleted)."""
    items = _manifest()
    hit = [d for d in items if d["name"].lower() == name.lower()]
    if not hit:
        raise ContentError("no design named %r" % name)
    d = hit[0]
    os.makedirs(DISABLED, exist_ok=True)
    if os.path.exists(d["file"]):
        dest = os.path.join(DISABLED, os.path.basename(d["file"]))
        shutil.move(d["file"], dest)
        d["file"] = dest
    d["disabled"] = True
    _save_manifest(items)
    return dict(d, note="restart the game for the change to take effect")
