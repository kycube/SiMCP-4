"""SiMCP 4: the SimCity 4 MCP server (stdio by default; --transport streamable-http for URL clients)."""

from __future__ import annotations

import argparse
import functools
import os

from mcp.server.fastmcp import FastMCP

from . import game as gamemod
from . import city, launch, layers, memory, regions
from .registry import tool

INSTRUCTIONS = (
    "Tools for playing SimCity 4 Deluxe (1.1.641) through the game's own code. Start with guide(), then "
    "game_launch(). Coordinates are city cells; regions are grids of city tiles. Every result is JSON; failures "
    "are tool errors with {error, hint}."
)

mcp = FastMCP("simcity4", instructions=INSTRUCTIONS)
G = gamemod.Game()
GUIDE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide.md")


def guarded(fn):
    """Turn expected failures into {error, hint} results (shown to the model as tool errors)."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except gamemod.GameError as e:
            return {"error": str(e), "hint": e.hint}
        except Exception as e:  # noqa: BLE001 - a tool must answer, not crash the server
            return {"error": "%s: %s" % (type(e).__name__, e), "hint": "see game_status"}
    return wrapper


@tool(mcp, "read")
def guide(topic: str = "start") -> str:
    """How to use this server: the guide for agents, by topic.

    Args:
        topic: "start" (overview and first steps), "all" (the whole guide) or a section name such as "regions".
    """
    text = open(GUIDE, encoding="utf-8").read()
    if topic in ("all", ""):
        return text
    sections = text.split("\n## ")
    for s in sections[1:]:
        title = s.split("\n", 1)[0].strip().lower()
        if topic.lower() in title:
            return "## " + s
    return sections[0] + "\n\nSections: " + ", ".join(s.split("\n", 1)[0] for s in sections[1:])


@tool(mcp, "act")
@guarded
def game_launch(windowed: bool = True, width: int = 1024, height: int = 768, intro: bool = False,
                timeout_s: int = 120) -> dict:
    """Start SimCity 4 (or attach to the instance SiMCP started earlier) and connect to it. The game runs without
    administrator rights and with SiMCP's own user folder (its own Regions and settings; the player's plugins are
    mirrored, so the simulation is the same), and opens on the region view. Returns the game status.

    Args:
        windowed: run in a window (true) or full screen.
        width: window / screen width in pixels (screen recipes are measured at 1024x768).
        height: window / screen height in pixels.
        intro: play the intro movie.
        timeout_s: seconds to wait for the game to finish starting.
    """
    return G.launch(windowed=windowed, width=width, height=height, intro=intro, timeout=timeout_s)


@tool(mcp, "read")
@guarded
def game_status() -> dict:
    """Whether SimCity 4 is running and controllable, and what it shows (region view or a city)."""
    return G.status()


@tool(mcp, "read")
@guarded
def list_regions() -> dict:
    """The regions in SiMCP's user folder with their city tiles (grid position, size small / medium / large) and
    each tile's saved city (name, mayor, established or not, populations). Reads files: works without the game."""
    rs = regions.list_regions(launch.USER_DIR)
    for r in rs:
        r["cities"] = [{k: c.get(k) for k in ("name", "mayor", "tile_x", "tile_y", "size", "established",
                                              "population", "file", "error") if c.get(k) is not None}
                       for c in r["cities"]]
    return {"user_dir": launch.USER_DIR, "regions": rs}


@tool(mcp, "act")
@guarded
def load_region(name: str) -> dict:
    """Open a region in the region view (the game's own LoadRegion). Works from the region view; leave a city first.

    Args:
        name: the region's folder name as list_regions shows it (e.g. "MCP Test", "Timbuktu").
    """
    return G.load_region(name)


@tool(mcp, "act")
@guarded
def load_city(name: str = "", size: str = "any") -> dict:
    """Open a city of the loaded region with the region view's own LoadCity: with a name, the founded city of that
    name; without one, the first unfounded tile of the given size (it opens in god mode: terrain only). Returns the
    city's status.

    Args:
        name: a founded city's name as list_regions shows it, or "" for an unfounded tile.
        size: for an unfounded tile: "small" (64x64 cells), "medium" (128x128), "large" (256x256) or "any".
    """
    return G.load_city(name=name, size=size)


@tool(mcp, "destructive")
@guarded
def leave_city() -> dict:
    """Go back to the region view without saving (unsaved changes to the city are lost)."""
    return G.leave_city()


@tool(mcp, "act")
@guarded
def advance_time(days: int = 1, max_seconds: float = 60.0) -> dict:
    """Advance the open city by exactly this many game days, far faster than real time, with the game's own day
    code: every day runs all of the simulation's daily, weekly, monthly and yearly work. The game's own pause and
    speed settings are left as they were. Returns the new date; if max_seconds runs out first, remaining_days says
    how many days are left (call again to continue).

    Args:
        days: game days to advance (1 or more).
        max_seconds: wall-clock limit for this call (keep it under your client's tool timeout).
    """
    if days < 1:
        return {"error": "days must be 1 or more", "hint": "advance_time(days=30) advances a month"}
    return G.advance_days(days, max_seconds)


@tool(mcp, "read")
@guarded
def city_status() -> dict:
    """The open city: name, mayor, founded or not, difficulty, size in cells, the game date, speed and pause state.
    Read from the game's memory."""
    return G.city_status()


def _city():
    """The attached game with a city open (raises the usual {error, hint} otherwise)."""
    G.attach(10.0)
    if not memory.city_pointer(G.proc):
        raise gamemod.GameError("no city is open", "load_city opens one from the region view")
    return G


@tool(mcp, "read")
@guarded
def map_data(layer: str = "", x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1) -> dict:
    """One data layer of the open city as a grid, read from the game's memory: the values the game's data views and
    simulation use. Call with no layer to list the layers. Values are per tract (tract_size cells square; rows[z][x]
    in tract units); a cell (x, z) is in tract (x // tract_size, z // tract_size).

    Args:
        layer: a layer name ("zones", "land_value", "crime", "police_coverage", "fire_coverage", "air_pollution",
            "water_pollution", "garbage", "power", "water", "traffic_congestion", "mayor_rating", ...); "" lists them.
        x0: first cell column of the area to return (0 = west edge).
        z0: first cell row of the area to return.
        x1: last cell column (inclusive; -1 = the city's edge).
        z1: last cell row (inclusive; -1 = the city's edge).
    """
    if not layer:
        return {"layers": {k: v[2] for k, v in layers.LAYERS.items()},
                "also": "tile_info(x, z) gives every layer at one cell, with terrain, water and the lot"}
    g = _city()
    d = layers.layer_grid(g.proc, layer)
    ts = d["tract_size"]
    tx0, tz0 = max(0, x0 // ts), max(0, z0 // ts)
    tx1 = d["nx"] - 1 if x1 < 0 else min(d["nx"] - 1, x1 // ts)
    tz1 = d["nz"] - 1 if z1 < 0 else min(d["nz"] - 1, z1 // ts)
    rows = [r[tx0:tx1 + 1] for r in d["rows"][tz0:tz1 + 1]]
    flat = [v for r in rows for v in r]
    return {"layer": layer, "meaning": d["meaning"], "tract_size": ts, "tracts": [d["nx"], d["nz"]],
            "area_tracts": [tx0, tz0, tx1, tz1], "min": min(flat), "max": max(flat),
            "mean": round(sum(flat) / len(flat), 2), "rows": rows}


@tool(mcp, "read")
@guarded
def tile_info(x: int, z: int) -> dict:
    """Everything about one cell of the open city: the value of every data layer there, the terrain altitude at its
    corners, water depth and sea level, and the lot / building standing on it. Read from memory.

    Args:
        x: cell column (0 = west edge).
        z: cell row (0 = north edge).
    """
    g = _city()
    p = g.proc
    out = {"x": x, "z": z, "layers": {}}
    for name in layers.LAYERS:
        try:
            d = layers.layer_grid(p, name)
            ts = d["tract_size"]
            out["layers"][name] = d["rows"][z // ts][x // ts]
        except (layers.LayerError, IndexError):
            pass
    t = layers.terrain(p)
    corners = [(x, z), (x + 1, z), (x, z + 1), (x + 1, z + 1)]
    out["altitude"] = [t["altitude"][cz][cx] for cx, cz in corners]
    out["sea_level"] = t["sea_level"]
    if "water_depth" in t:
        out["water_depth"] = max(0.0, max(t["water_depth"][cz][cx] for cx, cz in corners))
    out["lot"] = city.lot_info(g, x, z)
    return out


@tool(mcp, "read")
@guarded
def get_budget() -> dict:
    """The city's money: funds, the tax rate of every zone and wealth group, this month's income and expenses, last
    month's, year to date, the game's end-of-year estimate, and loans. Read from the game."""
    return city.budget(_city())


@tool(mcp, "read")
@guarded
def demand() -> dict:
    """Residential, commercial and industrial demand per wealth group, as the game's demand graph shows it, with
    the share blocked by caps, plus the number of residents."""
    return city.demand(_city())


@tool(mcp, "read")
@guarded
def lots(zone: str = "", x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1, limit: int = 500) -> dict:
    """The lots of the open city with their building: position, size, facing, zone, wealth, state (occupied,
    abandoned, under construction...), historical, power, and the building's name and exemplar id.

    Args:
        zone: only lots of this zone (e.g. "residential_low", "industrial_high", "plopped"); "" = all.
        x0: west edge of the area (cells).
        z0: north edge of the area (cells).
        x1: east edge (inclusive; -1 = the city's edge).
        z1: south edge (inclusive; -1 = the city's edge).
        limit: at most this many lots in the answer (count always gives the total).
    """
    g = _city()
    return city.lots(g, zone or None, x0, z0, x1 if x1 >= 0 else 1 << 30, z1 if z1 >= 0 else 1 << 30,
                     limit=limit)


@tool(mcp, "read")
@guarded
def advisors(include_fluff: bool = False) -> dict:
    """What the city's advisors say now: each advisor's mood and current messages (title, mood, priority, text) - the
    same advice the game shows in its advisor panel, popups and news ticker.

    Args:
        include_fluff: also list the fluffy news (jokes without game meaning).
    """
    return city.advisors(_city(), include_fluff)


@tool(mcp, "destructive")
@guarded
def quit_game(force: bool = False) -> dict:
    """Quit SimCity 4 without saving (an open city's unsaved changes are lost; save first if needed).

    Args:
        force: end the process instead of asking the game to quit (use only if the game no longer responds).
    """
    return G.quit(force=force)


def main():
    ap = argparse.ArgumentParser(prog="python -m sc4_mcp")
    ap.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()
    if a.transport == "streamable-http":
        mcp.settings.port = a.port
    mcp.run(transport=a.transport)


if __name__ == "__main__":
    main()
