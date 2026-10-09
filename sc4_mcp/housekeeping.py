"""Region housekeeping on SiMCP's own files: backups, removing a city or a region (moved aside into SiMCP's backups,
never deleted), renaming a region. Only while the game does not have the region loaded (the game rewrites a loaded
region's files), and only inside SiMCP's own Regions folder.
"""

from __future__ import annotations

import configparser
import os
import shutil
import time

from . import heightmap, launch, regions

BACKUPS = os.path.join(launch.ROOT, "backups")


class HousekeepingError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _folder(name: str) -> str:
    try:
        return heightmap.region_folder(name)
    except heightmap.HeightmapError as e:
        raise HousekeepingError(str(e), e.hint)


def _ini_name(folder: str) -> str | None:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read(os.path.join(folder, "region.ini"), encoding="latin-1")
        return cp.get("Regional Settings", "Name", fallback=None)
    except configparser.Error:
        return None


def _game_running(g) -> dict | None:
    if g is None:
        return None
    try:
        st = g.status()
    except Exception:  # noqa: BLE001 - no game: nothing is loaded
        return None
    return st if st.get("running") else None


def _not_loaded(g, folder: str) -> None:
    """The game must not have this region open (it keeps and rewrites its files). The game knows a region by its
    display name (region.ini), which can differ from the folder's name after a rename."""
    st = _game_running(g)
    loaded = ((st or {}).get("region") or "").lower()
    if loaded and loaded in {os.path.basename(folder).lower(), (_ini_name(folder) or "").lower()}:
        raise HousekeepingError("the game has the region %r loaded" % st["region"],
                                "load another region first (load_region), or quit_game")


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup_region(name: str) -> dict:
    """Copy a region folder (config, settings and every city) to SiMCP's backups."""
    src = _folder(name)
    dest = os.path.join(BACKUPS, "%s-%s" % (os.path.basename(src), _stamp()))
    shutil.copytree(src, dest)
    files = sorted(os.listdir(dest))
    return {"region": name, "backup": dest, "files": files}


def remove_city(g, region: str, city: str) -> dict:
    """Take a city out of a region: its file moves to SiMCP's backups (the tile becomes a new city)."""
    folder = _folder(region)
    _not_loaded(g, folder)
    hits = []
    for f in os.listdir(folder):
        if not f.lower().endswith(".sc4"):
            continue
        path = os.path.join(folder, f)
        try:
            info = regions.read_city(path)
        except Exception:  # noqa: BLE001
            info = {}
        key = city.strip().lower()
        if key in (f.lower(), (info.get("name") or "").lower()) or f.lower() == "city - %s.sc4" % key:
            hits.append((path, info))
    if not hits:
        raise HousekeepingError("no city %r in region %r" % (city, region), "list_regions shows the cities")
    if len(hits) > 1:
        raise HousekeepingError("%d cities match %r" % (len(hits), city), "give the file name")
    path, info = hits[0]
    dest_dir = os.path.join(BACKUPS, "%s-%s" % (os.path.basename(folder), _stamp()))
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    shutil.move(path, dest)
    return {"region": region, "removed": os.path.basename(path), "tile": [info.get("tile_x"), info.get("tile_y")],
            "kept_at": dest, "note": "the tile is a new city the next time the region loads"}


def remove_region(g, name: str) -> dict:
    """Take a whole region away: its folder moves to SiMCP's backups."""
    folder = _folder(name)
    _not_loaded(g, folder)
    os.makedirs(BACKUPS, exist_ok=True)
    dest = os.path.join(BACKUPS, "%s-%s" % (os.path.basename(folder), _stamp()))
    shutil.move(folder, dest)
    return {"region": name, "kept_at": dest,
            "note": "the game lists regions when it starts: it disappears from the list after a restart"}


def rename_region(g, name: str, new_name: str) -> dict:
    """Give a region a new display name (region.ini "Name"; the folder keeps its name)."""
    folder = _folder(name)
    if not heightmap.REGION_NAME.fullmatch(new_name or ""):
        raise HousekeepingError("a region name is 1-32 letters, digits, spaces, - ' _")
    _not_loaded(g, folder)
    others = {r.get("name", r["folder"]).lower() for r in regions.list_regions(launch.USER_DIR)
              if r["folder"].lower() != os.path.basename(folder).lower()}
    if new_name.lower() in others:
        raise HousekeepingError("another region is called %r" % new_name)
    ini = os.path.join(folder, "region.ini")
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    cp.read(ini, encoding="latin-1")
    if not cp.has_section("Regional Settings"):
        raise HousekeepingError("region.ini has no [Regional Settings]")
    old = cp.get("Regional Settings", "Name", fallback=name)
    cp.set("Regional Settings", "Name", new_name)
    tmp = ini + ".tmp"
    with open(tmp, "w", encoding="latin-1") as f:
        for section in cp.sections():
            f.write("[%s]\n" % section)
            for k, v in cp.items(section):
                f.write("%s = %s\n" % (k, v))
    os.replace(tmp, ini)
    out = {"folder": os.path.basename(folder), "name_was": old, "name": new_name}
    if _game_running(g):
        out["note"] = ("the game read the region list when it started: it cannot load this region (under either "
                       "name) until it restarts (quit_game, then game_launch)")
    return out
