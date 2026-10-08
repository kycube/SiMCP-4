# SiMCP 4 guide for agents

SiMCP 4 lets you play SimCity 4 Deluxe through the game's own code. The game runs on the user's Windows desktop;
you act on it through these tools and read everything back from the game's memory.

## Start

1. `game_launch()` starts the game (windowed 1024x768) or attaches to the instance SiMCP already started. It
   opens on the region view.
2. `game_status()` tells you whether the game is controllable, which region is loaded and, in a city, the city's
   status.
3. `list_regions()` shows the regions in SiMCP's user folder and their city tiles - it reads files, so it also
   works before the game starts.
4. `quit_game()` ends the game without saving.

## Regions and cities

A region is a grid of city tiles: small (1x1 grid squares = 64x64 cells), medium (2x2 = 128x128) and large
(4x4 = 256x256). Each tile has a city file; tiles nobody has founded yet are "New City" in god mode (terrain only).
SiMCP plays in its own user folder, never in the player's: the shipped regions are copied there by the game, and
the test region "MCP Test" has one large, two medium and eight small tiles on flat new land.

- `load_region(name)` opens a region (from the region view).
- `load_city(name)` opens the founded city of that name; `load_city(size="small")` (no name) opens the first
  unfounded tile of that size. Both work from the region view.
- `leave_city()` goes back to the region view without saving.
- `city_status()` reads the open city: name, mayor, founded or not, difficulty, size in cells, date, speed, pause.

## Time

`advance_time(days)` advances the open city by exactly that many game days with the game's own day code (all the
daily, weekly, monthly and yearly simulation work runs for every day), much faster than real time - about 80 days
per second in a city of 25,000 people. It leaves the game's own pause and speed as they were. If `max_seconds`
runs out first, `remaining_days` says how many days are left: call it again.

## Errors

Failures are tool errors with JSON `{"error": ..., "hint": ...}`. The hint says what to do next. Typical ones:
- a city is open and the tool needs the region view (`leave_city` first), or the other way round;
- another SimCity 4 started with administrator rights (GOG Galaxy launches it that way) is running: SiMCP cannot
  control it, but `game_launch` starts SiMCP's own game beside it.
