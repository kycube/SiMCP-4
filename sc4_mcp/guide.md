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

## Seeing the city

Everything is read from the game's memory, never from screenshots:
- `city_status()` - name, mayor, date, speed, pause.
- `get_budget()` - funds, tax rate per zone and wealth group, this month's income and expenses, last month, year to
  date, the end-of-year estimate, loans. Funds change once a month, when the month is settled.
- `demand()` - residential / commercial / industrial demand per wealth group (the demand graph) and caps.
- `map_data(layer)` - a whole data layer as a grid (`map_data()` lists the layers: zones, land value, crime,
  coverage, pollution, power, water, traffic, mayor rating, population, education, health...). Values are per tract;
  `tract_size` says how many cells one value covers.
- `tile_info(x, z)` - every layer at one cell, the terrain altitude, water, and the lot and building there.
- `lots(zone, area)` - lots and their buildings (name, zone, wealth, state such as abandoned or under construction).
- `advisors()` - what each advisor says now, with mood and priority; read it every few months.

- `graphs()` - the game's Graphs window: every graph's lines with their latest value; `graph_data(series)` - the
  history behind a graph or an advisor trend (monthly samples; tax rates daily).

Coordinates: cells (x, z) from the north-west corner; x grows east, z grows south. A small city is 64x64 cells, a
medium 128x128, a large 256x256.

## Founding and running a city

- `found_city(name, mayor, difficulty)` founds the open unfounded tile (mayor mode starts).
- `set_speed(slow|medium|fast)`, `set_paused(true|false)`: the game's own clock while you watch it run.
- `set_tax(group, rate)`, `departments()` / `set_department_funding(...)`, `ordinances()` / `set_ordinance(...)`,
  `loans()` / `take_loan(amount)`: the budget window's controls, with the game's limits.
- `save_city()` saves as the game's Save does (shipped cities are protected unless you say otherwise).
- `dialog_status()` / `close_dialog(button)`: a dialog the game opened (advisor popups, notices, offers) and its
  buttons; `set_popups(false)` keeps advisor popups from interrupting.

## Building

Every building tool does what the player's tool does after the mouse picks the cells: the game's own rules, the
game's own cost, charged to the city's funds (nothing is built that the city cannot pay for). Each takes
`build_it=false` to report the cost first. Building needs a founded city (mayor mode).
- `build_network(network, points)` - roads, streets, avenues, rail, pipes, power lines...: one drag per leg
  between consecutive points; the game's solver lays diagonals and curves. Building over an existing network of
  the same kind is charged again, as in the game.
- `zone(zone_type, x0, z0, x1, z1)` - zoning (with automatic streets in large zones) and de-zoning.
- `build_menu(menu)` - what can be plopped now, per build menu, with cost and monthly cost; greyed items are
  locked rewards or need more population, a later era, or are excluded. `build_menu(menu="trees")` lists trees.
- `plop(building, x, z, facing)` - a building from the menus with its north-west corner at (x, z).
- `bulldoze(x0, z0, x1, z1)` and `plant_trees(tree, x0, z0, x1, z1)`.

Growth is the game's: zone land next to roads, give it power and water, and advance time; buildings grow when
there is demand.

## Looking at the city

- `camera()` / `set_camera(x, z, zoom, rotation)` move the city view with the game's view commands.
- `snapshot(...)` returns a picture the game draws itself (its own snapshot, UI included) and keeps the PNG; the
  game window must not be minimised.
- `day_night(mode)` keeps it day (clearer pictures), night, or lets the clock run.
- `city_figures(expression)` reads the ~190 figures the advisors use (game.g_*), read-only.

## Disasters and emergencies

- `start_disaster(disaster, x, z)` uses god mode's Disasters menu through the game's disaster tool; disasters
  unfold while the game runs. `disaster_status()` lists what is going on.
- `dispatch(unit, x, z)` sends fire or police units, as the dispatch buttons do (a station with a free unit and a
  road route is needed).

## Cheats

`cheat(name, argument)` runs one of the game's player cheats. Cheats are not honest play: SiMCP runs only vetted
ones, logs every use, and `city_status()` shows how many were used in the city. Prefer playing without them.

## Errors

Failures are tool errors with JSON `{"error": ..., "hint": ...}`. The hint says what to do next. Typical ones:
- a city is open and the tool needs the region view (`leave_city` first), or the other way round;
- another SimCity 4 started with administrator rights (GOG Galaxy launches it that way) is running: SiMCP cannot
  control it, but `game_launch` starts SiMCP's own game beside it.
