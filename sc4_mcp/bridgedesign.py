"""New bridges: copies of the game's (or a plugin's) bridges under a new name, cost or height.

A bridge is an exemplar of type 7 in group 0xA82CA30F (the game's 44 in SimCity_1.dat, more from plugins: NAM
adds dozens): its pieces (0x482CB443 start, 0x482CB445 span, 0x482CB449 end - piece exemplars with the models),
0x482CB441 the deck height (m above the water), 0x482CB447 / 0x482CB44C / 0x482CB468 span and length limits,
0x8A2602B9 its cost (16 for the level road bridge .. 864 for the Golden Gate), 0x482CB46F its icon [PNG group
0x6A386D26, instance] and 0x482CD466 its name [LTEXT group 0x6A231EAA, instance]. The network tool offers every
bridge listed for that network in the network INI (type 0, group 0x8A5971C5, instance 0x8A5993B9, NAM's
controller here): [RoadBridgeExemplars], [AvenueBridgeExemplars]... lines "n = 0x6534284a, 0xa82ca30f, instance,
comment" (the tool's bridge table, read by build_network's bridge_choices; read once, at the first network tool).
A new bridge keeps its base's pieces and icon and gets SiMCP's own instance, name and values; at game_launch SiMCP
writes zzz_SiMCP\\SiMCP_NetworkINI.dat - the active INI with SiMCP's bridges added to their base's sections.
"""

from __future__ import annotations

import os
import time

from . import content, dbpf, launch, puzzle

G_BRIDGES, T_BRIDGE = 0xA82CA30F, 7
INI_TGI = (0, 0x8A5971C5, 0x8A5993B9)         # the network INI: per-network bridge lists
INI_FILE = "SiMCP_NetworkINI.dat"
G_NAMES, G_ICONS = 0x6A231EAA, 0x6A386D26
P_HEIGHT, P_ICON, P_NAME_KEY, P_COST = 0x482CB441, 0x482CB46F, 0x482CD466, 0x8A2602B9
OWN = 0x005C4D00                           # SiMCP's bridges: base top byte | 0x005C4D00 + n


class BridgeError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _files() -> list[str]:
    from . import gamedata
    main = gamedata._main_dat()
    files = [main.path] if main else []
    root = os.path.join(launch.USER_DIR, "Plugins")
    plugs = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith((".dat", ".sc4desc")):
                plugs.append(os.path.join(dp, f))
    return files + sorted(plugs, key=puzzle._load_order_key)


_cache: dict = {}


def bridges() -> list[dict]:
    """Every bridge the game loads (later files win): name, exemplar, instance, cost, height."""
    if _cache.get("root") == launch.USER_DIR:
        return _cache["list"]
    found, names = {}, {}
    for f in _files():
        try:
            d = dbpf.DBPF(f)
        except (OSError, ValueError):
            continue
        for e in d.find(dbpf.T_EXEMPLAR, G_BRIDGES):
            try:
                ex = dbpf.parse_exemplar(d.read(e))
            except Exception:  # noqa: BLE001 - a damaged plugin record
                continue
            pr = {p.id: p.values for p in ex.props}
            if pr.get(0x10) != [T_BRIDGE]:
                continue
            found[e.instance] = (f, ex, pr)
        for e in d.find(dbpf.T_LTEXT, G_NAMES):
            names[e.instance] = (f, e)
    out = []
    for inst, (f, ex, pr) in found.items():
        key = pr.get(P_NAME_KEY)
        shown = ""
        if isinstance(key, list) and len(key) >= 2 and key[1] in names:
            nf, ne = names[key[1]]
            try:
                shown = dbpf.parse_ltext(dbpf.DBPF(nf).read(ne)).strip()
            except Exception:  # noqa: BLE001
                shown = ""
        elif isinstance(key, list) and len(key) >= 2:      # the game's own: its language file
            from . import gamedata
            shown = (gamedata.locale_text(key[1], key[0]) or "").strip()
        out.append({"name": shown or str(pr.get(0x20, "")), "exemplar": str(pr.get(0x20, "")),
                    "instance": "0x%08X" % inst, "cost": (pr.get(P_COST) or [None])[0],
                    "height_m": (pr.get(P_HEIGHT) or [None])[0], "file": f, "_ex": ex})
    out.sort(key=lambda b: int(b["instance"], 16))
    _cache.update(root=launch.USER_DIR, list=out)
    return out


def find(base: str) -> dict:
    want = base.strip().lower()
    every = bridges()
    hits = [b for b in every if b["name"].lower() == want or b["exemplar"].lower() == want] or \
           [b for b in every if want in b["name"].lower() or want in b["exemplar"].lower()]
    if not hits:
        raise BridgeError("no bridge %r" % base, "build_network(..., build_it=false) lists the bridges offered")
    return hits[0]


def design_bridge(name: str, base: str, height_m: float | None = None) -> dict:
    """A copy of a bridge the game offers under a new name, its deck at another height (0x482CB441)."""
    content._check_name(name)
    b = find(base)
    if height_m is not None and not 0 <= float(height_m) <= 200:
        raise BridgeError("height_m is 0..200")
    base_inst = int(b["instance"], 16)
    taken = {int(x["instance"], 16) for x in bridges()}
    taken |= {int(d["instance"], 16) for d in content._manifest() if d.get("kind") == "bridge"}
    inst = (base_inst & 0xFF000000) | OWN
    while inst in taken:
        inst += 1
    ex = b["_ex"]
    props = [dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values, p.multi)
             for p in ex.props]
    content._set(props, 0x20, dbpf.PT_STRING, "SiMCP_bridge_%s" % content._slug(name))
    content._set(props, P_NAME_KEY, dbpf.PT_UINT32, [G_NAMES, inst], multi=True)
    if height_m is not None:
        content._set(props, P_HEIGHT, dbpf.PT_FLOAT32, [float(height_m)], multi=True)
    _, ini = base_ini()
    section = section_of(ini, base_inst)
    if not section:
        raise BridgeError("the network INI lists no bridge %s" % b["instance"], "pick a bridge the game offers")
    records = [(dbpf.T_EXEMPLAR, G_BRIDGES, inst, dbpf.build_exemplar(props, ex.parent)),
               (dbpf.T_LTEXT, G_NAMES, inst, dbpf.build_ltext(name))]
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_bridge_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "bridge", "file": path, "instance": "0x%08X" % inst, "base": b["name"],
             "base_instance": b["instance"], "section": section,
             "height_m": float(height_m) if height_m is not None else b["height_m"],
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    _cache.clear()
    return dict(entry, note="plugins load at start: quit_game, game_launch; then build_network(..., bridge=%r) "
                            "builds it where the base bridge would fit" % name)


def _ini_files() -> list[str]:
    ours = os.path.normcase(os.path.abspath(os.path.join(content.FOLDER, INI_FILE)))
    out = []
    for f in _files()[1:]:
        if os.path.normcase(os.path.abspath(f)) == ours:
            continue
        try:
            if dbpf.DBPF(f).get(*INI_TGI):
                out.append(f)
        except (OSError, ValueError):
            continue
    return out


def base_ini() -> tuple[str, str]:
    """The network INI the game would use without SiMCP's: (file, text)."""
    from . import gamedata
    files = _ini_files()
    if files:
        d = dbpf.DBPF(files[-1])
        return files[-1], d.read(d.get(*INI_TGI)).decode("latin-1")
    d = gamedata._main_dat()
    return d.path, d.read(d.get(*INI_TGI)).decode("latin-1")


def section_of(text: str, instance: int) -> str | None:
    """The [...BridgeExemplars] section listing a bridge instance."""
    import re
    sec = None
    for line in text.splitlines():
        m = re.match(r"^\[([^\]]+)\]", line.strip())
        if m:
            sec = m.group(1)
            continue
        if sec and sec.lower().endswith("bridgeexemplars") and "=" in line and not line.strip().startswith(";"):
            vals = [v.strip() for v in line.split("=", 1)[1].split(",")]
            if len(vals) >= 3:
                try:
                    if int(vals[2], 16) == instance:
                        return sec
                except ValueError:
                    pass
    return None


def merged_ini(text: str, items: list[dict]) -> str:
    """The INI with each bridge's line added at the end of its section (keys after the section's highest)."""
    import re
    lines = text.splitlines()
    for d in items:
        sec = d.get("section")
        start = next((i for i, ln in enumerate(lines) if ln.strip().lower() == "[%s]" % sec.lower()), None)
        if start is None:
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        keys = [int(m.group(1)) for ln in lines[start + 1:end] for m in [re.match(r"^\s*(\d+)\s*=", ln)] if m]
        new = "%d = 0x6534284a, 0xa82ca30f, %s, SiMCP %s" % (max(keys + [0]) + 1, d["instance"], d["name"])
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, new)
    return "\n".join(lines) + "\n"


def merge_network_ini() -> dict:
    """Write (or move aside) SiMCP's network INI; called before the game starts."""
    items = [d for d in content._manifest() if d.get("kind") == "bridge" and not d.get("disabled") and d.get("section")]
    path = os.path.join(content.FOLDER, INI_FILE)
    if not items:
        if os.path.exists(path):
            os.makedirs(content.DISABLED, exist_ok=True)
            dest = os.path.join(content.DISABLED, "SiMCP_NetworkINI-%s.dat" % time.strftime("%Y%m%d-%H%M%S"))
            os.replace(path, dest)
            return {"network_ini": None, "moved_aside": dest}
        return {"network_ini": None}
    if os.path.realpath(content.FOLDER) != os.path.abspath(content.FOLDER):
        raise BridgeError("SiMCP's plugin folder is a link; refusing to write there")
    src, text = base_ini()
    dbpf.write_dbpf(path, [INI_TGI + (merged_ini(text, items).encode("latin-1"),)], compress=False)
    return {"network_ini": path, "base": src, "bridges": len(items)}
