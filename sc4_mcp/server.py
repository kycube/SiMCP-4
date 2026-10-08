"""SiMCP 4: the SimCity 4 MCP server (stdio by default; --transport streamable-http for URL clients)."""

from __future__ import annotations

import argparse
import functools
import os

from mcp.server.fastmcp import FastMCP

from . import game as gamemod
from . import launch, regions
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
