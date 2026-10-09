"""SiMCP 4: the SimCity 4 MCP server (stdio by default; --transport streamable-http for URL clients)."""

from __future__ import annotations

import argparse
import functools
import json
import os

from mcp.server.fastmcp import FastMCP, Image

from . import game as gamemod
from . import build, catalog, cheats, city, content, disasters, economy, heightmap, history, launch, layers, luaquery, memory, mysim, neighbors, networks, options, pointer, regions, services, terrain, udi, view
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


@tool(mcp, "read")
@guarded
def saved_city(region: str, city: str, terrain: bool = False) -> dict:
    """A saved city read from its file, without the game: tile, size, populations, mayor rating, difficulty,
    names; with terrain=true also the saved altitudes at every cell corner.

    Args:
        region: the region's name.
        city: the city's name.
        terrain: include the altitude grid (rows of cells+1 values, metres).
    """
    try:
        path = regions.find_city_file(launch.USER_DIR, region, city)
        out = regions.read_city(path)
        if terrain:
            out["terrain"] = regions.read_terrain(path)
        return out
    except (OSError, ValueError) as e:
        return {"error": str(e), "hint": "list_regions shows the regions and their cities"}


@tool(mcp, "observe")
@guarded
def city_thumbnail(region: str, city: str, view: str = "satellite"):
    """The picture the region view shows for a saved city (the game renders it on every save), read from the file.

    Args:
        region: the region's name.
        city: the city's name.
        view: satellite or transport.
    """
    try:
        path = regions.find_city_file(launch.USER_DIR, region, city)
        png = regions.read_thumbnail(path, view)
    except (OSError, ValueError) as e:
        return {"error": str(e), "hint": "list_regions shows the regions and their cities"}
    return [json.dumps({"region": region, "city": city, "view": view}), Image(data=png, format="png")]


@tool(mcp, "act")
@guarded
def open_tile(x: int, z: int) -> dict:
    """Open a city tile of the loaded region by its grid square (the tile's north-west corner, as list_regions
    gives it), as the region view's Play button does: a saved city loads; an empty tile opens as a new city in god
    mode (shape the land, then found_city).

    Args:
        x: the tile's grid column.
        z: the tile's grid row.
    """
    return G.open_tile(x, z)


@tool(mcp, "act")
@guarded
def new_region(name: str, water: bool = False) -> dict:
    """Create a new region in SiMCP's user folder, as the region view's Create New Region does (the game picks a
    random layout of city tiles; new tiles start flat), and open it.

    Args:
        name: the region's name (letters, digits, spaces, - ' _).
        water: start the tiles low (the "Water" terrain choice) instead of plains.
    """
    return G.new_region(name, water)


def _reload_region(name: str) -> None:
    """The game reads config.bmp when a region loads; loading the same region again does nothing, so go through
    another region and back."""
    others = [r["folder"] for r in regions.list_regions(launch.USER_DIR) if r["folder"] != name]
    if others:
        G.load_region(others[0])
    G.load_region(name)


@tool(mcp, "act")
@guarded
def set_region_layout(region: str, width: int, height: int, tile: str = "small") -> dict:
    """Give a region a new grid of city tiles (its config.bmp): width x height grid squares (1 km each) filled with
    small (1x1), medium (2x2) or large (4x4) city tiles. Refused when the region has founded cities. Reopens the
    region when the region view shows it.

    Args:
        region: the region's folder name (list_regions).
        width: grid squares east-west (1-64; a multiple of the tile's span).
        height: grid squares north-south.
        tile: small, medium or large.
    """
    try:
        cities = heightmap._established(region)
        if cities:
            return {"error": "the region has founded cities: %s" % ", ".join(cities[:5]),
                    "hint": "a new layout would orphan them; use a new region (new_region)"}
        out = heightmap.write_layout(region, width, height, tile)
    except heightmap.HeightmapError as e:
        return {"error": str(e), "hint": e.hint}
    G.attach(10.0)
    if G.status().get("view") == "region" and G.region_name() == region:
        _reload_region(region)
        out["reloaded"] = True
    return out


@tool(mcp, "destructive")
@guarded
def import_region_terrain(region: str, heights: list[list[float]] | None = None, image_path: str = "",
                          replace_cities: bool = False, max_seconds: float = 1800.0) -> dict:
    """Shape a whole region from a height map, through the game's own region import (RegionBitmapLoad): every city
    tile of the region is deleted and generated again from its part of the map, then saved (about 13 s per small
    tile). Heights are metres: sea level is 250, the game stores grey x 3 m (0-765). The region view must show the
    region (load_region). A region with founded cities is refused unless replace_cities.

    Args:
        region: the region's folder name (the one the region view shows).
        heights: rows of heights in metres (north row first, west to east), any size from 2 x 2: resampled to the
            region's map size. Use this or image_path.
        image_path: a greyscale image file (any common format) used instead: grey level x 3 m.
        replace_cities: allow deleting founded cities.
        max_seconds: how long to wait for the game to generate the tiles.
    """
    G.attach(10.0)
    try:
        bmp, info = heightmap.make_bitmap(region, heights=heights, image_path=image_path)
        res = heightmap.import_terrain(G, region, bmp, replace_cities, max_seconds)
    except heightmap.HeightmapError as e:
        return {"error": str(e), "hint": e.hint}
    res["map"] = info
    return res


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


@tool(mcp, "act")
@guarded
def found_city(name: str, mayor: str, difficulty: str = "easy") -> dict:
    """Found (establish) the unfounded tile that is open, as the player does: the Mayor Mode button, then the
    Establish City dialog with the city's and the mayor's names and the difficulty. After this the god-mode terrain
    tools are no longer available and the difficulty cannot change (the game's own rule).

    Args:
        name: the city's name (1-31 characters).
        mayor: the mayor's name (1-31 characters).
        difficulty: "easy", "medium" or "hard" (sets the starting funds and the economy's difficulty).
    """
    return G.found_city(name, mayor, difficulty)


@tool(mcp, "set")
@guarded
def set_speed(speed: str) -> dict:
    """The game's speed buttons: "slow", "medium" or "fast" (like the buttons, this also un-pauses).

    Args:
        speed: "slow", "medium" or "fast".
    """
    return G.set_speed(speed)


@tool(mcp, "set")
@guarded
def set_paused(paused: bool) -> dict:
    """Pause or resume the simulation with the game's pause button.

    Args:
        paused: true to pause, false to run.
    """
    return G.set_paused(paused)


def _opt(fn, *a):
    try:
        G.attach(10.0)
        return fn(G, *a)
    except options.OptionsError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def game_options() -> dict:
    """The game's options: the Play Options dialog's switches (auto go to disaster, edge scrolling, expanded
    tooltips, urgent advice dialogs, auto edge reconciliation), sound and music, graphics settings and resolution,
    pause on focus loss. Read from the game's preferences."""
    return _opt(options.options)


@tool(mcp, "set")
@guarded
def set_play_option(option: str, on: bool) -> dict:
    """Switch one of the Play Options, as the dialog's Accept does (the game is told and saves its preferences in
    SiMCP's own user folder).

    Args:
        option: auto_go_to_disaster, edge_scrolling, expanded_tooltips, urgent_advice_dialogs or
            auto_edge_reconciliation.
        on: true to switch it on.
    """
    return _opt(options.set_play_option, option, on)


@tool(mcp, "destructive")
@guarded
def save_city(allow_shipped: bool = False) -> dict:
    """Save the open city with the game's own save, into its file in SiMCP's user folder (replacing the previous
    save). SiMCP's copies of the cities shipped with the game are kept as shipped unless allow_shipped.

    Args:
        allow_shipped: also save over SiMCP's copy of a city that came with the game.
    """
    return G.save_city(allow_shipped)


@tool(mcp, "read")
@guarded
def dialog_status() -> dict:
    """The game's open dialog windows, topmost first: title, texts and buttons (labels and ids). When a dialog is
    open the game waits for an answer; close_dialog answers it."""
    from . import dialogs
    G.attach(10.0)
    return dialogs.status(G)


@tool(mcp, "act")
@guarded
def close_dialog(button: str) -> dict:
    """Answer the topmost dialog by pressing one of its buttons, as the player clicks it.

    Args:
        button: the button's label as dialog_status shows it (case-insensitive; a unique part is enough) or its id.
    """
    from . import dialogs
    G.attach(10.0)
    return dialogs.click(G, button)


@tool(mcp, "set")
@guarded
def set_popups(enabled: bool) -> dict:
    """Whether the game opens popup windows (advisor messages, message boxes) during play. With popups off the game
    keeps running unattended; advice still reaches the advisors panel and news (read them with advisors()).

    Args:
        enabled: true = the game's normal popups, false = none.
    """
    G.attach(10.0)
    return G.set_popups(enabled)


@tool(mcp, "destructive")
@guarded
def leave_city() -> dict:
    """Go back to the region view without saving (unsaved changes to the city are lost)."""
    return G.leave_city()


@tool(mcp, "act")
@guarded
def advance_time(days: int = 1, mode: str = "natural", max_seconds: float = 90.0) -> dict:
    """Advance the open city by this many game days and pause exactly on the target day.

    mode "natural" (default) lets the game play at its fast speed - everything happens as for a player who presses
    fast and waits (buildings finish construction, cars drive, idle work runs), about 10-20 days per second.
    "unthrottled" removes the game's spacing between days (much faster, but buildings finish on wall-clock time in
    this game, so fewer complete per day). "exact" steps days with the game's day code under a hidden pause
    (fastest and fully deterministic per day; construction barely progresses - use it for budget / time checks).
    The player's speed and pause state are restored. If max_seconds runs out first, remaining_days says how many
    days are left.

    Args:
        days: game days to advance (1 or more).
        mode: natural, unthrottled or exact.
        max_seconds: wall-clock limit for this call (keep it under your client's tool timeout).
    """
    if days < 1:
        return {"error": "days must be 1 or more", "hint": "advance_time(days=30) advances a month"}
    if mode == "exact":
        out = G.advance_days(days, max_seconds)
        out["mode"] = "exact"
        return out
    if mode not in ("natural", "unthrottled"):
        return {"error": "unknown mode %r" % mode, "hint": "natural, unthrottled or exact"}
    return G.run_days(days, max_seconds, unthrottled=(mode == "unthrottled"))


@tool(mcp, "read")
@guarded
def city_status() -> dict:
    """The open city: name, mayor, founded or not, difficulty, size in cells, the game date, speed and pause state,
    read from the game's memory; and how many cheats SiMCP has used in it (cheat log)."""
    out = G.city_status()
    if isinstance(out, dict) and out.get("name"):
        out["cheats_used"] = len(cheats.used(out["name"], out.get("region")))
        bad = history.stalled(G.proc, out.get("day_number") or 0)
        if bad:
            out["warning"] = ("the %s simulator has stopped (no history for over two months): the game process is in "
                              "a bad state - save, then quit_game and game_launch" % " and ".join(bad))
    return out


def _city():
    """The attached game with a city open (raises the usual {error, hint} otherwise)."""
    G.attach(10.0)
    if not memory.city_pointer(G.proc):
        raise gamemod.GameError("no city is open", "load_city opens one from the region view")
    return G


TRAFFIC_MEANING = ("trips through each cell per commute (morning + evening, all travel types: walk, car, bus, "
                   "trains, freight, subway, monorail) - the Traffic Volume data view; network_map(traffic=true) "
                   "splits it by travel type")


def _traffic_grid(g) -> dict:
    nx, nz = networks._city_size(g.proc)
    rows = [[0] * nx for _ in range(nz)]
    for (x, z), by in networks.traffic(g).items():
        if x < nx and z < nz:
            rows[z][x] = sum(by.values())
    return {"type": "I", "tract_size": 1, "nx": nx, "nz": nz, "rows": rows, "meaning": TRAFFIC_MEANING}


@tool(mcp, "read")
@guarded
def map_data(layer: str = "", x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1) -> dict:
    """One data layer of the open city as a grid, read from the game's memory: the values the game's data views and
    simulation use. Call with no layer to list the layers. Values are per tract (tract_size cells square; rows[z][x]
    in tract units); a cell (x, z) is in tract (x // tract_size, z // tract_size).

    Args:
        layer: a layer name ("zones", "land_value", "crime", "police_coverage", "fire_coverage", "air_pollution",
            "water_pollution", "garbage", "power", "water", "traffic_congestion", "traffic_volume", "mayor_rating",
            ...); "" lists them.
        x0: first cell column of the area to return (0 = west edge).
        z0: first cell row of the area to return.
        x1: last cell column (inclusive; -1 = the city's edge).
        z1: last cell row (inclusive; -1 = the city's edge).
    """
    if not layer:
        return {"layers": {**{k: v[2] for k, v in layers.LAYERS.items()}, "traffic_volume": TRAFFIC_MEANING},
                "also": "tile_info(x, z) gives every layer at one cell, with terrain, water and the lot"}
    g = _city()
    if layer == "traffic_volume":
        d = _traffic_grid(g)
    else:
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
def network_map(network: str = "", x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1,
                traffic: bool = False) -> dict:
    """Where the roads, rails, highways, streets, power lines, pipes and subways are: a character map of the area
    (one string per cell row, rows[z - z0][x - x0]) with each cell's connected sides, read from the game's network
    pieces. Also lists pieces that connect to a neighbour city across the map edge, and - for areas of at most 400
    cells - every piece with its sides per network.

    Args:
        network: "" for everything above ground (pipes and subways are underground and share cells with roads), or
            one network: road, rail, elevated_highway, street, pipe, power_line, avenue, subway, light_rail,
            monorail, one_way_road, dirt_road, ground_highway.
        x0: first cell column (0 = west edge).
        z0: first cell row (0 = north edge).
        x1: last cell column (inclusive; -1 = the city's edge).
        z1: last cell row (inclusive; -1 = the city's edge).
        traffic: also list the busiest cells of the area with their trips per travel type.
    """
    g = _city()
    try:
        out = networks.network_map(g, network, x0, z0, x1, z1)
        ax0, az0, ax1, az1 = out["area"]
        if traffic:
            t = {c: v for c, v in networks.traffic(g).items() if ax0 <= c[0] <= ax1 and az0 <= c[1] <= az1}
            top = sorted(t.items(), key=lambda kv: -sum(kv[1].values()))[:30]
            out["busiest"] = [{"x": c[0], "z": c[1], "trips": sum(v.values()), "by_travel_type": v} for c, v in top]
        if (ax1 - ax0 + 1) * (az1 - az0 + 1) <= 400:
            out["pieces"] = networks.pieces(g, ax0, az0, ax1, az1)
        return out
    except networks.NetworkError as e:
        return {"error": str(e), "hint": "network_map() with no arguments maps the whole city"}


def _nb(fn, *a):
    try:
        return fn(_city(), *a)
    except neighbors.NeighborError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def neighbor_deals() -> dict:
    """The city's deals with neighbour cities (selling or buying power and water, exporting or importing garbage):
    partner tile, amount per month, the month's income or expense, state, dates; the month's deal totals; and the
    connections to neighbours (power lines, pipes, roads, rails... reaching the map edge)."""
    return _nb(neighbors.deals)


@tool(mcp, "act")
@guarded
def open_neighbor_deals() -> dict:
    """Open the Budget window's Neighbor Deals panel, as the player does after the advisor reports a possible deal:
    the game proposes every deal the connections and both cities' surplus and need allow, and those deals start
    at once (the panel has no accept step). A deal needs a connection: a power line, pipe or road to the map edge
    built with build_network(connect_neighbor=true)."""
    return _nb(neighbors.open_deals)


@tool(mcp, "act")
@guarded
def cancel_neighbor_deal(index: int) -> dict:
    """Cancel a running neighbour deal, as its "Cancel Deal" button does (the money stops at once; opening the
    panel again proposes it anew if it is still possible).

    Args:
        index: the deal's index from neighbor_deals.
    """
    return _nb(neighbors.cancel_deal, index)


@tool(mcp, "read")
@guarded
def find_route(x0: int, z0: int, x1: int, z1: int, kind: str = "car") -> dict:
    """The shortest way along connected network pieces from one cell to another (cells in order, plus the corner
    cells where the way turns) - for planning drives, checking that places are connected, or laying pipes.

    Args:
        x0: start cell column (must hold a piece of the network).
        z0: start cell row.
        x1: goal cell column.
        z1: goal cell row.
        kind: "car" (roads, streets, avenues, one-way and dirt roads, highways) or one network name.
    """
    g = _city()
    try:
        path = networks.route(g, (x0, z0), (x1, z1), kind)
    except networks.NetworkError as e:
        return {"error": str(e), "hint": "network_map shows which cells hold which network"}
    turns = [path[0]] + [b for a, b, c in zip(path, path[1:], path[2:])
                         if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1])] + [path[-1]]
    return {"kind": kind, "cells": len(path), "path": [list(c) for c in path], "turns": [list(c) for c in turns]}


@tool(mcp, "read")
@guarded
def get_budget() -> dict:
    """The city's money: funds, the tax rate of every zone and wealth group, this month's income and expenses, last
    month's, year to date, the game's end-of-year estimate, and loans. Read from the game."""
    return city.budget(_city())


def _econ(fn, *a):
    try:
        return fn(_city(), *a)
    except economy.EconomyError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "set")
@guarded
def set_tax(group: str, rate: float) -> dict:
    """Set the tax rate of one zone and wealth group, as the Budget window's spinners do (0.0 to 20.0 percent in
    steps of 0.1; outside values are clamped). Returns the rate the game now uses.

    Args:
        group: one of residential_low, residential_medium, residential_high, commercial_services_low,
            commercial_services_medium, commercial_services_high, commercial_office_medium, commercial_office_high,
            industrial_agriculture, industrial_dirty, industrial_manufacturing, industrial_high_tech.
        rate: the tax rate in percent.
    """
    return _econ(economy.set_tax, group, rate)


@tool(mcp, "read")
@guarded
def departments() -> dict:
    """The city's budget departments (police, fire, health, education, transit, utilities...): funding percentage,
    the most the player may set, and this month's expense and income for each."""
    g = _city()
    return {"departments": [{k: v for k, v in d.items() if not k.startswith("_")} for d in economy.departments(g)]}


@tool(mcp, "set")
@guarded
def set_department_funding(department: str, percent: float) -> dict:
    """Set a department's funding, as the Budget window's slider does (0 up to the department's maximum, usually
    120 percent; clamped). It sets every building of the department to that funding (building_funding shows what
    that does to each one's service). Returns the new monthly expense.

    Args:
        department: the department's name as departments() lists it (e.g. "Police Dept.", "Education"; a unique
            part of the name is enough) or its id.
        percent: the funding in percent of the full cost.
    """
    return _econ(economy.set_department_funding, department, percent)


def _svc(fn, *a):
    try:
        return fn(_city(), *a)
    except services.ServiceError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def building_funding(x: int, z: int) -> dict:
    """A civic building's or power plant's funding and what it buys: each budget item (funding percent, full and
    current monthly cost), the game's response curve from funding to effect with the effect now, and the service
    measured in the game - power plant efficiency, condition and output capacity; police / fire station efficiency;
    school / hospital capacity, staff and enrolment. Funding below 100 percent saves money and weakens the service
    by the curve (fire stations and power plants lose effect faster than the money saved; school buses and
    ambulances keep half their coverage at zero).

    Args:
        x: a cell of the building (column).
        z: a cell of the building (row).
    """
    return _svc(services.building_funding, x, z)


@tool(mcp, "set")
@guarded
def set_building_funding(x: int, z: int, item: str, percent: float) -> dict:
    """Set one building's funding, as its funding slider in the Budget window does (0 up to the item's maximum,
    usually 120 percent; clamped). Returns the cost and the measured service before and after.

    Args:
        x: a cell of the building (column).
        z: a cell of the building (row).
        item: power, police, fire, school_staff, school_buses, hospital_staff or ambulances (building_funding lists
            a building's items).
        percent: the funding in percent of the full cost.
    """
    return _svc(services.set_building_funding, x, z, item, percent)


@tool(mcp, "read")
@guarded
def ordinances() -> dict:
    """Every ordinance the game knows (including those added by plugins): whether it is available to this city,
    enacted, its enactment and repeal fees, its current monthly income or cost, and its description."""
    return {"ordinances": economy.ordinances(_city())}


@tool(mcp, "set")
@guarded
def set_ordinance(name: str, enacted: bool) -> dict:
    """Enact or repeal an ordinance, as the Ordinances panel does (only ordinances available to the city). Fees and
    monthly effects are settled with the month's budget.

    Args:
        name: the ordinance's name as ordinances() lists it (a unique part of the name is enough) or its id.
        enacted: true to enact, false to repeal.
    """
    return _econ(economy.set_ordinance, name, enacted)


@tool(mcp, "read")
@guarded
def loans() -> dict:
    """The city's loans (principal, monthly payment, what is left to pay, when they end) and the bank's limits."""
    return economy.loans(_city())


@tool(mcp, "act")
@guarded
def take_loan(amount: int) -> dict:
    """Take a loan from the bank, as the Loans window does: 5,000 to 100,000 in steps of 5,000, within the game's
    limits (number of loans and total borrowing). The money is added to the funds at once; it is repaid monthly with
    interest (SimCity 4 has no early repayment).

    Args:
        amount: the loan amount.
    """
    return _econ(economy.take_loan, amount)


@tool(mcp, "read")
@guarded
def demand() -> dict:
    """Residential, commercial and industrial demand per wealth group, as the game's demand graph shows it, with
    the share blocked by caps, plus the number of residents."""
    return city.demand(_city())


@tool(mcp, "read")
@guarded
def lots(zone: str = "", x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1, limit: int = 500,
         occupancy: bool = False) -> dict:
    """The lots of the open city with their building: position, size, facing, zone, wealth, state (occupied,
    abandoned, under construction...), historical, power, the building's name and exemplar id, and optionally how
    full each one is (residents or jobs against capacity, per wealth group).

    Args:
        zone: only lots of this zone (e.g. "residential_low", "industrial_high", "plopped"); "" = all.
        x0: west edge of the area (cells).
        z0: north edge of the area (cells).
        x1: east edge (inclusive; -1 = the city's edge).
        z1: south edge (inclusive; -1 = the city's edge).
        limit: at most this many lots in the answer (count always gives the total).
        occupancy: add residents / jobs and capacity per lot (a few game calls per lot).
    """
    g = _city()
    return city.lots(g, zone or None, x0, z0, x1 if x1 >= 0 else 1 << 30, z1 if z1 >= 0 else 1 << 30,
                     limit=limit, occupancy=occupancy)


@tool(mcp, "set")
@guarded
def rename_city(name: str = "", mayor: str = "") -> dict:
    """Rename the open city and / or its mayor, as the city name window of the control panel does. The next
    save_city writes the city under its new name.

    Args:
        name: the city's new name (1-31 characters; "" = keep).
        mayor: the mayor's new name ("" = keep).
    """
    try:
        return city.rename(_city(), name, mayor)
    except ValueError as e:
        return {"error": str(e), "hint": ""}


@tool(mcp, "act")
@guarded
def make_historical(x: int, z: int, historical: bool = True) -> dict:
    """Make a zoned building historical (or not), as the "Make Historical" button of its query window does: the
    game will not redevelop or replace it (it can still be abandoned or bulldozed). Free.

    Args:
        x: a cell of the building's lot (column).
        z: a cell of the building's lot (row).
        historical: true to protect it, false to lift the protection.
    """
    try:
        return city.set_historical(_city(), x, z, historical)
    except ValueError as e:
        return {"error": str(e), "hint": "lots() lists the lots with their zone"}


@tool(mcp, "read")
@guarded
def advisors(include_fluff: bool = False) -> dict:
    """What the city's advisors say now: each advisor's mood and current messages (title, mood, priority, text) - the
    same advice the game shows in its advisor panel, popups and news ticker.

    Args:
        include_fluff: also list the fluffy news (jokes without game meaning).
    """
    return city.advisors(_city(), include_fluff)


def _build(fn, *a, **kw):
    try:
        return fn(_city(), *a, **kw)
    except build.BuildError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def build_menu(menu: str = "") -> dict:
    """What the player can plop now, from the game's build menus (with plugins): each item's name, lot and
    building ids, menus, size in cells, plop cost, monthly cost, and whether the menu offers it (available=false:
    greyed - a locked reward, a population or era requirement, an exclusion). menu="trees" lists the trees.

    Args:
        menu: one menu only: parks, rail, transit (bus, subway, tram, parking, toll), ferries, power, water,
            garbage, police, jail, fire, education, health,
            airports, landmarks, rewards, or trees. "" = all.
    """
    if menu == "trees":
        return {"trees": build.tree_types()}
    g = _city()
    return {"items": catalog.ploppables(build._Caller(g), menu)}


@tool(mcp, "act")
@guarded
def plop(building: str, x: int, z: int, facing: str = "north") -> dict:
    """Plop a building from the build menus, as the player's plop tool does: the game's placement rules apply and
    its plop cost is charged. Refused when the menu greys it out (locked reward, requirement not met) or the spot
    is taken, too steep or under water (nothing is charged then).

    Args:
        building: a name from build_menu ("Coal Power Plant") or its lot or building id ("0x02000002").
        x: west edge of the lot (cell).
        z: north edge of the lot (cell).
        facing: the side the lot's front faces: north (toward smaller z), east, south or west.
    """
    return _build(build.plop, building, x, z, facing)


@tool(mcp, "act")
@guarded
def build_network(network: str, points: list[list[int]], build_it: bool = True, connect_neighbor: bool = False,
                  bridge: int = -1) -> dict:
    """Build a road, rail, pipe, power line or other network through cells, as the player drags it: one drag per
    leg between consecutive points, laid by the game's own path solver (diagonals and curves as the game makes
    them), each leg's cost charged to the funds (a leg the city cannot pay is not built).

    Args:
        network: road, street, avenue, one_way_road, rail, light_rail, monorail, subway, elevated_highway,
            ground_highway, dirt_road, pipe or power_line.
        points: cells [[x, z], ...]: where the drag starts and each point where it bends or ends (2 to 64). To join
            an existing road, start or end ON one of its cells (a drag beside it does not connect).
        build_it: false = only report each leg's cost and whether the game allows it.
        connect_neighbor: at the city edge, accept the game's offer to connect to the neighbour city.
        bridge: over water, which of the game's bridge choices to build (index; -1 = the game's default).
    """
    out = _build(build.network, network, [tuple(q) for q in points], build_it, connect_neighbor, bridge)
    if build_it and isinstance(out, dict) and out.get("built"):
        try:
            loose = networks.unjoined_ends(G, [tuple(q) for q in points], network)
        except Exception:  # noqa: BLE001 - only a hint
            loose = []
        if loose:
            out["warning"] = ("the new %s ends next to another network without joining it at %s: a drag joins only "
                              "the pieces it passes over - drag again from the existing piece to the new one"
                              % (network, ", ".join("(%d, %d)" % c for c in loose)))
    return out


@tool(mcp, "act")
@guarded
def zone(zone_type: str, x0: int, z0: int, x1: int, z1: int, build_it: bool = True, streets: bool = True,
         alternate: bool = False) -> dict:
    """Zone (or de-zone) a rectangle of cells, as the player's zone tool does: the game's zoning rules (slope,
    size) and its cost per cell, charged to the funds. Areas larger than one drag (32 x 32, 48 x 48 for
    agriculture) are zoned in several drags.

    Args:
        zone_type: residential_low, residential_medium, residential_high, commercial_low, commercial_medium,
            commercial_high, agriculture, industrial_medium, industrial_high, military, airport, seaport,
            spaceport, landfill, or dezone.
        x0: west edge (cell).
        z0: north edge (cell).
        x1: east edge (cell, inclusive).
        z1: south edge (cell, inclusive).
        build_it: false = only report the cost.
        streets: lay the automatic streets inside large zones (false = the Ctrl-drag).
        alternate: the Alt-drag variant of the zone tool.
    """
    return _build(build.zone, zone_type, x0, z0, x1, z1, build_it, streets, alternate)


@tool(mcp, "destructive")
@guarded
def bulldoze(x0: int, z0: int, x1: int, z1: int, build_it: bool = True) -> dict:
    """Bulldoze everything on a rectangle of cells (buildings, lots, networks, trees), as the player's bulldozer
    does: the game's demolition cost is taken from the funds (as in the game, this can go below zero).

    Args:
        x0: west edge (cell).
        z0: north edge (cell).
        x1: east edge (cell, inclusive).
        z1: south edge (cell, inclusive).
        build_it: false = only report the cost.
    """
    return _build(build.bulldoze, x0, z0, x1, z1, build_it)


@tool(mcp, "act")
@guarded
def plant_trees(tree: str, x0: int, z0: int, x1: int, z1: int, build_it: bool = True) -> dict:
    """Plant one tree in each cell of a rectangle, as the player's flora tool does: each tree's price is charged,
    and planting stops when the city cannot pay.

    Args:
        tree: a tree from build_menu(menu="trees"): its name ("Oak Tree") or id.
        x0: west edge (cell).
        z0: north edge (cell).
        x1: east edge (cell, inclusive).
        z1: south edge (cell, inclusive).
        build_it: false = only report the cost.
    """
    return _build(build.trees, tree, x0, z0, x1, z1, build_it)


@tool(mcp, "read")
@guarded
def graphs() -> dict:
    """The game's Graphs window: every graph (mayor rating, funds, income and expenses, population by type and age,
    demand, power, water, pollution, garbage, commute time, traffic volume, crime, education, life expectancy...) with
    each line's latest value in the units the window shows. graph_data gives the history of a line."""
    return {"graphs": history.graphs(_city().proc)}


@tool(mcp, "read")
@guarded
def graph_data(series: str = "", last: int = 24) -> dict:
    """The history of one or more series the city keeps (the data behind the Graphs window and the advisors'
    trends): dated samples, oldest first. Most series get one sample a month; tax rates one a day.

    Args:
        series: a graph title ("Funds (000s)", "Crime"), a line ("Power: Capacity"), a series name ("funds",
            "air_pollution", "tax_rate_residential_low") or an id ("0x4A5BA3D0"). "" lists every series kept.
        last: the newest this many samples per series (0 = all kept).
    """
    p = _city().proc
    if not series.strip():
        return {"series": history.all_series(p)}
    return history.series_data(p, series, last)


def _view(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except view.ViewError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def camera() -> dict:
    """Where the city view looks: the centre cell (x, z), the ground altitude there, zoom (1 far .. 6 close),
    rotation (0..3) and the viewport size in pixels."""
    return _view(view.camera, _city().proc)


@tool(mcp, "set")
@guarded
def set_camera(x: int = -1, z: int = -1, zoom: int = 0, rotation: int = -1) -> dict:
    """Move the city view as the player does (the game's own view commands); omitted values stay as they are.

    Args:
        x: centre cell, west-east (-1 = keep).
        z: centre cell, north-south (-1 = keep).
        zoom: 1 (far) to 6 (close); 0 = keep.
        rotation: 0..3 (each step is a quarter turn clockwise); -1 = keep.
    """
    g = _city()
    return _view(view.set_camera, g, None if x < 0 else x, None if z < 0 else z, zoom or None,
                 None if rotation < 0 else rotation)


@tool(mcp, "set")
@guarded
def day_night(mode: str = "") -> dict:
    """The day/night cycle, as god mode's button sets it: day_and_night (the clock runs), day (always day) or
    night (always night). With no mode it reads the setting.

    Args:
        mode: day_and_night, day, night, or "" to read.
    """
    return _view(view.day_night, _city(), mode)


@tool(mcp, "observe")
@guarded
def snapshot(x: int = -1, z: int = -1, zoom: int = 0, rotation: int = -1, width: int = 1024):
    """A picture of the city as the game draws it (the game's own snapshot of its view, with its UI), after moving
    the view if asked. Returns the camera and the image; the full-size PNG is kept in SiMCP's snapshots folder.

    Args:
        x: centre cell, west-east (-1 = keep).
        z: centre cell, north-south (-1 = keep).
        zoom: 1 (far) to 6 (close); 0 = keep.
        rotation: 0..3; -1 = keep.
        width: scale the image to this many pixels wide (the PNG keeps the full size).
    """
    g = _city()
    try:
        if x >= 0 or z >= 0 or zoom or rotation >= 0:
            view.set_camera(g, None if x < 0 else x, None if z < 0 else z, zoom or None,
                            None if rotation < 0 else rotation)
        info, jpeg = view.snapshot(g, width)
    except view.ViewError as e:
        return {"error": str(e), "hint": e.hint}
    return [json.dumps(info), Image(data=jpeg, format="jpeg")]


def _disaster(fn, *a):
    try:
        return fn(_city(), *a)
    except (disasters.DisasterError, pointer.PointerError) as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def disaster_status() -> dict:
    """Disasters going on in the open city (fires, volcanoes, earthquakes, riots, toxic spills...) with their
    locations, and the god-mode Disasters menu."""
    out = _disaster(disasters.status)
    if "error" not in out:
        out["menu"] = [d["key"] for d in disasters.menu()]
    return out


@tool(mcp, "act")
@guarded
def start_disaster(disaster: str, x: int, z: int) -> dict:
    """Start a disaster from the god-mode Disasters menu at a cell, with the game's own disaster tool (as the
    player's click). Disasters unfold while the game runs: set_paused(false) or advance_time afterwards.

    Args:
        disaster: volcano, earthquake, fire, meteor, tornado, lightning, robot_attack, autosaurus_wrecks or ufo.
        x: cell, west-east.
        z: cell, north-south.
    """
    return _disaster(disasters.start, disaster, x, z)


@tool(mcp, "act")
@guarded
def dispatch(unit: str, x: int, z: int) -> dict:
    """Send emergency units to a cell with the game's dispatch tools (as the player's dispatch buttons): the city
    needs a station of that kind with a free unit and a road route to the cell.

    Args:
        unit: fire, police, fire_plane or police_helicopter.
        x: cell, west-east.
        z: cell, north-south.
    """
    return _disaster(disasters.dispatch, unit, x, z)


@tool(mcp, "act")
@guarded
def cheat(name: str, argument: str = "") -> dict:
    """Run one of the game's player cheats - outside honest play, so every use is logged (SiMCP's cheats.jsonl)
    and counted in city_status. Only vetted cheats run, with checked arguments: weaknesspays (+1,000), riskymoney
    (+10,000, may start a riot), howdryiam (all watered), fightthepower (all powered), barstuck, whattimeizit
    <hour>, stopwatch pause|resume|magnify <n>, showtime, whererufrom <city name>, hellomynameis <mayor name>,
    dollyllama, casper [off], gp on|off. Developer and crashing cheats are refused.

    Args:
        name: the cheat (case-insensitive).
        argument: its argument, if it takes one (a single word for names).
    """
    try:
        return cheats.run(_city(), name, argument)
    except cheats.CheatError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def city_figures(expression: str = "") -> dict:
    """The city figures the game computes for its advisors (about 190 game.g_* values: population per zone and
    wealth, tile and building counts, coverage, congestion, funds, borrowing...), read from the game's own Lua state.
    With no expression it lists the names; with one it evaluates it, read-only.

    Args:
        expression: e.g. "game.g_population", "game.g_road_tile_count + game.g_street_tile_count",
            "game.trend_value(game_trends.G_FUNDS, 12)". Allowed: game.g_* values, read-only game functions
            (trend_value, trend_slope, trend_count, ordinance_is_on, difficulty_level...), the constant tables
            (game_trends, tuning_constants...), numbers, strings, arithmetic, comparisons, and/or/not, tostring,
            tonumber, math.*.
    """
    g = _city()
    try:
        if not expression.strip():
            return {"figures": luaquery.variables(g)}
        return luaquery.evaluate(g, expression)
    except luaquery.LuaError as e:
        return {"error": str(e), "hint": e.hint}


def _udi(fn, *a):
    try:
        return fn(_city(), *a)
    except udi.DriveError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def missions() -> dict:
    """U-Drive-It: the missions the City Situations advisor offers now, and the current mission and vehicle
    (status, time used and limit, target cell and distance, vehicle cell and heading)."""
    out = _udi(udi.status)
    if "error" not in out:
        out["offers"] = _udi(udi.offers)
    return out


@tool(mcp, "act")
@guarded
def start_mission(mission: str) -> dict:
    """Ask the game to offer a U-Drive-It mission (by its title or guid from missions()). The game picks a vehicle
    of that kind out in the city and opens the offer dialog: answer it with close_dialog("Accept"),
    close_dialog("Free Drive") or close_dialog("Cancel"). The city must have been running for a few seconds so
    vehicles are out.

    Args:
        mission: the mission title or guid.
    """
    return _udi(udi.start, mission)


@tool(mcp, "act")
@guarded
def drive(keys: list[str], seconds: float = 1.0) -> dict:
    """Hold driving keys for a while, as the player does, then release them; returns the mission and vehicle
    state. The game must be running (not paused). Heading x is east, z south; "left" turns toward the vehicle's
    left.

    Args:
        keys: any of accelerate, brake, left, right, special (horn / siren / hose), alternate, off_road, climb,
            dive, power_up, power_down - held together.
        seconds: how long to hold them (0 to 10).
    """
    return _udi(udi.drive, keys, seconds)


@tool(mcp, "act")
@guarded
def stop_driving() -> dict:
    """Leave the vehicle (the Escape key), ending a free drive or giving up a mission."""
    return _udi(udi.stop)


def _mysim(fn, *a):
    try:
        return fn(_city(), *a)
    except (mysim.MySimError, pointer.PointerError) as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def my_sims() -> dict:
    """The five My Sim slots: for each Sim living in the city, name, age, sign, wealth, home, job and where it is
    now (cell)."""
    out = _mysim(mysim.sims)
    return out if isinstance(out, dict) else {"sims": out}


@tool(mcp, "act")
@guarded
def move_in_sim(x: int, z: int, face: str = "", name: str = "", sign: str = "") -> dict:
    """Make a My Sim and move it into the house on a cell, through the game's My Sims panel, its Select A My Sim
    dialog and the move-in tool. The face sets the gender (and a preset name and sign, which name and sign
    override). The game then reports through the Sim's own advice balloons.

    Args:
        x: a cell of the house (west-east).
        z: a cell of the house (north-south).
        face: one of the dialog's 21 faces, by number or preset name (my_sim_faces lists them); "" = the default.
        name: the Sim's name (1-31 characters; "" = the face's preset name).
        sign: capricorn, aquarius, pisces, aries, taurus, gemini, cancer, leo, virgo, libra, scorpio or
            sagittarius ("" = the face's).
    """
    return _mysim(mysim.move_in, x, z, face or None, name, sign)


@tool(mcp, "read")
@guarded
def my_sim_faces() -> dict:
    """The faces the Select A My Sim dialog offers: number, preset name, sign and gender."""
    return {"faces": mysim.faces()}


def _terrain(fn, *a):
    try:
        return fn(_city(), *a)
    except (terrain.TerrainError, pointer.PointerError) as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def terrain_brushes() -> dict:
    """The terrain brushes available now: in a founded city the mayor's raise / lower / level (charged); before
    founding, god mode's brushes (mountains, valleys, canyons, craters, lakes, levelling, smoothing, erosion,
    plains... free)."""
    return _terrain(terrain.brushes)


@tool(mcp, "act")
@guarded
def terraform(brush: str, cells: list[list[int]], seconds: float = 1.0) -> dict:
    """Hold a terrain brush on cells, as the player holds the mouse: the effect grows with the time held; with
    several cells the brush moves along them. In mayor mode each application is charged. Returns the altitudes
    before and after and the cost.

    Args:
        brush: a name from terrain_brushes() (mayor mode: raise, lower, level).
        cells: [[x, z], ...] - one cell, or a path for the brush to move along.
        seconds: how long to hold (0.1 to 10).
    """
    return _terrain(terrain.apply, brush, [tuple(c) for c in cells], seconds)


def _content(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except content.ContentError as e:
        return {"error": str(e), "hint": e.hint}


@tool(mcp, "read")
@guarded
def content_designs() -> dict:
    """The buildings SiMCP designed (its plugin files in SiMCP's own Plugins folder): name, ids, file, state."""
    return {"designs": content.designs()}


@tool(mcp, "act")
@guarded
def design_building(name: str, template: str, description: str = "", plop_cost: int = -1,
                    monthly_cost: int = -1, bulldoze_cost: int = -1) -> dict:
    """Design a new building for the build menus from one of the game's own menu items (its models, props and
    textures) under a new name, description and costs; it is written as a plugin file into SiMCP's own Plugins
    folder. The game loads plugins at start-up: quit_game and game_launch, then it is in build_menu like any other.

    Args:
        name: the new building's name, shown in the menu.
        template: a Maxis item from build_menu: its name ("Playground") or lot id.
        description: the menu description.
        plop_cost: the plop cost (-1 = the template's).
        monthly_cost: the monthly cost (-1 = the template's).
        bulldoze_cost: the bulldoze cost (-1 = the template's).
    """
    g = _city()
    hits = catalog.find(build._Caller(g), template)
    if not hits:
        return {"error": "no build menu item matches %r" % template, "hint": "build_menu lists the items"}
    if len({h["lot"] for h in hits}) > 1:
        return {"error": "%r matches several items" % template, "hint": "use the lot id from build_menu"}
    it = hits[0]
    return _content(content.clone_lot, it["lot"], None, name, description,
                    None if plop_cost < 0 else plop_cost, None if monthly_cost < 0 else monthly_cost,
                    None if bulldoze_cost < 0 else bulldoze_cost)


@tool(mcp, "act")
@guarded
def design_model_building(name: str, width_m: float, depth_m: float, height_m: float, wall_rgb: list[int],
                          roof_rgb: list[int], windows: bool = True, lot_cells: int = 1, description: str = "",
                          plop_cost: int = 500, monthly_cost: int = 20) -> dict:
    """Design a new building with its own 3D model and textures (a block with a window grid and a flat roof) on
    its own paved lot, for the Parks menu; written as a plugin into SiMCP's own Plugins folder. The game loads
    plugins at start-up: quit_game and game_launch, then it is in build_menu like any other.

    Args:
        name: the new building's name, shown in the menu.
        width_m: west-east size in metres (a cell is 16 m; it must fit the lot).
        depth_m: north-south size in metres.
        height_m: height in metres (2..400).
        wall_rgb: the wall colour [r, g, b] (0..255).
        roof_rgb: the roof colour [r, g, b].
        windows: draw a window on every 4 m x 4 m of wall.
        lot_cells: the lot's size in cells a side (1..6).
        description: the menu description.
        plop_cost: the plop cost.
        monthly_cost: the monthly cost.
    """
    if len(wall_rgb) != 3 or len(roof_rgb) != 3 or not all(0 <= c <= 255 for c in list(wall_rgb) + list(roof_rgb)):
        return {"error": "colours are [r, g, b] with values 0..255"}
    return _content(content.model_building, name, width_m, depth_m, height_m, tuple(wall_rgb), tuple(roof_rgb),
                    windows, lot_cells, description, plop_cost, monthly_cost)


@tool(mcp, "act")
@guarded
def design_advice(name: str, advisor: str, title: str, message: str, trigger: str = "1", mood: str = "neutral",
                  priority: int = 50, once: bool = True, news_only: bool = False, timeout_days: int = 30) -> dict:
    """Write a new piece of advice or a news headline for the game's advisors, as a Lua plugin like the game's own
    advice scripts: the advisor shows it when its trigger is true. The game loads it at start-up (quit_game,
    game_launch); advisors() then lists it.

    Args:
        name: a name for the design (content_designs lists it).
        advisor: utilities, health_education, city_planning, transportation, environment, finances, safety, or news
            (the news ticker).
        title: the headline (plain text; <b>, <i> allowed; #city# becomes the city's name).
        message: the advice text (plain text with <b>, <i>, <u>, <br>, <p>; no links).
        trigger: when to show it - a read-only expression of the city's values, e.g.
            "game.g_city_r_population > 1000" or "game.g_funds < 5000"; "1" = at once. lua_query lists the values.
        mood: alarm, bad, neutral, good or fluff.
        priority: 0-100 (higher shows first).
        once: show it only the first time the trigger is true.
        news_only: only in the news ticker, not as an advisor message.
        timeout_days: how long it stays.
    """
    return _content(content.advice_design, name, advisor, title, message, trigger, mood, priority, once, news_only,
                    timeout_days)


@tool(mcp, "act")
@guarded
def design_growable_building(name: str, purpose: str, wealth: int, width_m: float, depth_m: float, height_m: float,
                             wall_rgb: list[int], roof_rgb: list[int], windows: bool = True, lot_width: int = 1,
                             lot_depth: int = 2, stage: int = 0, capacity: int = 0, description: str = "") -> dict:
    """Design a building that grows by itself in zones (a house, shop, office or factory) with its own 3D model and
    lot. A game growable of the same purpose, wealth and lot size lends its zone types, demand, pollution and
    capacity; the design gets its own building family and carries all four building styles, so the city may grow
    it on fitting zoned lots when demand calls for it. Written as a plugin into SiMCP's own Plugins folder; the
    game loads it at start-up (quit_game, game_launch).

    Args:
        name: the building's name (shown in its query window).
        purpose: residential, commercial_services, commercial_office, agriculture, industrial_processing,
            industrial_manufacturing or industrial_high_tech.
        wealth: 1 ($), 2 ($$) or 3 ($$$) (industry and agriculture have fewer kinds).
        width_m: west-east size in metres (it must fit the lot: 16 m per cell).
        depth_m: north-south size in metres.
        height_m: height in metres (2..400).
        wall_rgb: wall colour [r, g, b].
        roof_rgb: roof colour [r, g, b].
        windows: draw a window on every 4 m x 4 m of wall.
        lot_width: lot width in cells along the road (1..6). Lots one cell deep rarely develop; 2 deep is common.
        lot_depth: lot depth in cells (1..6).
        stage: growth stage (1 = the earliest; 0 = the template's).
        capacity: residents or jobs (0 = the template's).
        description: a note kept in the design list.
    """
    if len(wall_rgb) != 3 or len(roof_rgb) != 3 or not all(0 <= c <= 255 for c in list(wall_rgb) + list(roof_rgb)):
        return {"error": "colours are [r, g, b] with values 0..255"}
    return _content(content.growable_building, name, purpose, int(wealth), width_m, depth_m, height_m,
                    tuple(wall_rgb), tuple(roof_rgb), windows, (lot_width, lot_depth), stage, capacity, description)


@tool(mcp, "destructive")
@guarded
def disable_design(name: str) -> dict:
    """Take a SiMCP design out of the game: its file moves to SiMCP's content-disabled folder (nothing is
    deleted); restart the game for it to leave the menus. Buildings of it already in cities stay as they are.

    Args:
        name: the design's name.
    """
    return _content(content.disable, name)


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
