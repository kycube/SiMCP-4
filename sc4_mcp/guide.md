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

What you can do, by section below: regions and terrain (including whole regions from a height map); time;
reading the city (data layers, the network map and routes, traffic, lots and how full they are, budget,
advisors, graphs); running it (taxes, department and per-building funding with their effect on service,
ordinances, loans, neighbour deals, play options); building (networks, zones, plopping, bulldozing, trees,
terraforming, historical buildings); looking at it (camera, snapshots); disasters and emergencies; U-Drive-It and
My Sims; and making content (buildings for the menus, buildings that grow in zones, advice and news).

## Regions and cities

A region is a grid of city tiles: small (1x1 grid squares = 64x64 cells), medium (2x2 = 128x128) and large
(4x4 = 256x256). Each tile has a city file; tiles nobody has founded yet are "New City" in god mode (terrain only).
SiMCP plays in its own user folder, never in the player's: the shipped regions are copied there by the game, and
the test region "MCP Test" has one large, two medium and eight small tiles on flat new land.

- `load_region(name)` opens a region (from the region view).
- `load_city(name)` opens the founded city of that name; `load_city(size="small")` (no name) opens the first
  unfounded tile of that size. Both work from the region view.
- `open_tile(x, z)` opens any tile by its grid square (a saved city, or a new one in god mode, where
  `terrain_brushes()` / `terraform(...)` shape the land for free before `found_city`).
- `new_region(name)` creates a region (random tile layout) and opens it.
- `set_region_layout(region, width, height, tile)` gives a region without founded cities a new grid of city tiles
  (all small, medium or large); `import_region_terrain(region, heights=[[metres...], ...])` (or `image_path` to a
  greyscale picture) shapes the whole region at once through the game's own height-map import: every tile is
  generated again from its part of the map (sea level is 250 m; about 13 s per small tile). Plan a region as
  new_region -> set_region_layout -> import_region_terrain -> open_tile / found_city.
- `saved_city(region, city)` and `city_thumbnail(region, city)` read a saved city from its file.
- `leave_city()` goes back to the region view without saving.
- Housekeeping, on files only and never on the region the game has loaded: `backup_region(region)` copies a region
  into SiMCP's backups; `remove_city(region, city)` and `remove_region(region)` move files there (nothing is
  deleted; a removed city's tile is a new, unfounded city next time). `rename_region(region, new_name)` changes the
  name the game shows; the game reads region names when it starts, so a running game cannot load that region again
  until it restarts (`quit_game`, `game_launch`).
- `city_status()` reads the open city: name, mayor, founded or not, difficulty, size in cells, date, speed, pause.

## Time

`advance_time(days)` runs the open city that many game days and stops on the target day. The default mode,
"natural", lets the game play at its fast speed (about 10-20 days per second): buildings finish construction, cars
drive and growth happens as for a player who presses fast and waits. "exact" steps days under a hidden pause (fast
and deterministic, but construction barely moves - for budget and time checks); "unthrottled" is in between.
Afterwards the player's speed and pause state come back - an unpaused city keeps running at its own speed while
you think, so pause it (`set_paused(true)`) when you need it still. If `max_seconds` runs out first,
`remaining_days` says how many days are left: call it again.

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
- `network_map(network)` - where the roads, streets, avenues, highways, rails, power lines (and, by name, pipes and
  subways) are, one string per cell row, with each cell's connected sides as a hex digit (1 west, 2 north, 4 east,
  8 south) and the connections to neighbour cities; `traffic=true` adds the busiest cells with their trips by
  travel type, and `map_data("traffic_volume")` gives the trips through every cell. `find_route(x0, z0, x1, z1)` gives the cells a car (or one
  network) follows between two places - an error means they are not connected.
- `lots(zone, area, occupancy=true)` - lots and their buildings (name, zone, wealth, state such as abandoned or under
  construction) and how full each is (residents or jobs against capacity); `tile_info` shows it for one lot.
- `advisors()` - what each advisor says now, with mood and priority; read it every few months.

- `graphs()` - the game's Graphs window: every graph's lines with their latest value; `graph_data(series)` - the
  history behind a graph or an advisor trend (monthly samples; tax rates daily).

Coordinates: cells (x, z) from the north-west corner; x grows east, z grows south. A small city is 64x64 cells, a
medium 128x128, a large 256x256.

## Founding and running a city

- `found_city(name, mayor, difficulty)` founds the open unfounded tile (mayor mode starts).
- `rename_city(name, mayor)` renames the city or its mayor later, as the control panel's city name window does.
- `set_speed(slow|medium|fast)`, `set_paused(true|false)`: the game's own clock while you watch it run.
- `set_tax(group, rate)`, `departments()` / `set_department_funding(...)`, `ordinances()` / `set_ordinance(...)`,
  `loans()` / `take_loan(amount)`: the budget window's controls, with the game's limits.
- `building_funding(x, z)` / `set_building_funding(x, z, item, percent)`: one civic building's or power plant's
  funding and what it buys. Funding drives an efficiency curve (read from the game): police stations lose
  coverage in step with the money (50 % funding = half efficiency; the coverage map fell 45 % in a month), fire
  stations and power plants lose more than the money saved (50 % = a quarter of the efficiency and of a plant's
  output), school and hospital capacity is maximum x staff funding, and buses / ambulances keep half their reach
  at zero. New schools and hospitals start at 25 %: raise them as enrolment grows. The department slider
  (`set_department_funding`) sets every building of the department at once.
- `neighbor_deals()` / `open_neighbor_deals()` / `cancel_neighbor_deal(index)`: selling or buying power and water
  and moving garbage to neighbour cities. A deal needs a connection: build a power line (power), pipe (water) or
  road (garbage) to the map edge with `build_network(..., connect_neighbor=true)`. Opening the deals panel (as the
  advisor suggests) starts every deal that is possible at once; cancel the ones you do not want.
- `game_options()` / `set_play_option(option, on)`: the Play Options dialog (auto go to disaster, urgent advice
  dialogs...). `graphics_options(...)` and `audio_options(...)` read the Graphic / Audio Options dialogs, or set
  them through the dialogs themselves (levels low / medium / high, switches, volumes 0-100); with no arguments
  they only read. The window size and renderer come from `game_launch`.
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
- A new road joins an old one only where the drag passes over the old one's cells: start or end the drag on
  them. `build_network` warns when an end lies beside another network without joining it; `find_route` checks
  that two places are connected.
- `zone(zone_type, x0, z0, x1, z1)` - zoning (with automatic streets in large zones) and de-zoning.
- `build_menu(menu)` - what can be plopped now, per build menu, with cost and monthly cost; greyed items are
  locked rewards or need more population, a later era, or are excluded. `build_menu(menu="trees")` lists trees.
- `plop(building, x, z, facing)` - a building from the menus with its north-west corner at (x, z).
- `bulldoze(x0, z0, x1, z1)` and `plant_trees(tree, x0, z0, x1, z1)`.
- `make_historical(x, z)`: keep a zoned building as it is (the game will not redevelop it).

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

## U-Drive-It and My Sims

- `missions()` lists the missions the City Situations advisor offers and the mission / vehicle state;
  `start_mission(title)` makes the game offer one (let the city run a few seconds first so vehicles are out) and
  `close_dialog("Accept")` starts it. `drive(keys, seconds)` holds driving keys (accelerate, brake, left, right...)
  - the game must be running; `missions()` gives the vehicle's cell and heading and the target's cell.
  `stop_driving()` leaves the vehicle.
- `move_in_sim(x, z)` moves a My Sim into the house on a cell; `my_sims()` follows them (home, job, where they are).

## Making new buildings

- `design_building(name, template, ...)` makes a new menu item from one of the game's own (its models, props and
  textures) with a new name, description and costs.
- `design_model_building(name, width_m, depth_m, height_m, wall_rgb, roof_rgb, ...)` makes a building with its own
  generated 3D model and textures on its own lot.
- `design_growable_building(name, purpose, wealth, width_m, depth_m, height_m, wall_rgb, roof_rgb, lot_width,
  lot_depth, ...)` makes a house, shop, office or factory that the city grows by itself on zoned land of its kind
  (it borrows demand, capacity and pollution from a game building of the same purpose, wealth and lot size, and
  carries every building style). Zone 2-cell-deep strips: 1-deep lots rarely develop. It competes with the game's
  own buildings, so expect a share of the new lots, not all. A saved city whose lots hold a design needs that
  design: bulldoze those buildings before disabling it.
- `design_tree(name, shape, height_m, width_m, leaf_rgb, trunk_rgb, cost)` adds a tree type to the game's tree
  menu (plant it with `plant_trees`): a painted broadleaf, conifer or palm on three crossed planes, or your own
  picture with `image_path` (a PNG with a transparent background - the better-looking option). The trees cast
  shadows of their outline; plant them a cell or two apart. The game's own trees start as saplings and grow,
  a designed tree is full-size at once.
- `design_car(name, kind, body_rgb, wealth)` adds a car to the city's traffic: a sedan, van or pickup body with
  its own paint, head and tail lights, the game's shadow and night lights, driven by the commuters of one wealth
  class (cheap, middle, rich). It shares the road with the game's own cars of that class.
- Lots: `design_park(name, objects, lot_cells, ground)` lays out a park, plaza or garden for the Parks menu from
  the game's props (`game_props("bench")` finds them by name; use the id when several share a name), SiMCP's
  props, trees and ground textures (paving, plaza, concrete, asphalt, grass, lawn, meadow, gravel, garden, sand,
  parking). Objects are {"prop" | "tree" | "ground": name or id, "x": m, "z": m, "rotation": 0-3}, metres
  from the lot's north-west corner, the street along the south (+z) edge. `design_model_building` takes the same
  `ground` and `objects`. `design_prop(name, shape, ...)` makes a box, cylinder, cone or sign (with a picture on
  its street side) to place on lots.
- Your own 3D models: `design_model_building(..., model_path="house.obj", model_scale=1)` and
  `design_prop(..., model_path=...)` take a Wavefront OBJ with its MTL and PNG / JPEG textures: y up, the +z side
  facing the street, faces counter-clockwise seen from outside (a face seen from behind does not draw - model
  both sides of thin parts), texture coordinates 0..1 (the game does not repeat textures), one texture per
  material (scaled to a power of two up to 512). Transparent pixels are cut out. The tool returns a picture of
  the imported model; its size times model_scale (metres) must fit the lot.
- `design_civic_building(name, kind, radius_m, strength, capacity, ...)` makes a working police station, fire
  station, clinic or school: it serves the city as the game's own (its service is copied from the game's
  building) with its own model (block or OBJ), name, costs, coverage radius and strength or capacity, and
  appears in its service's menu. Fund it like any other (set_building_funding).
- `design_reward(name, condition, requirement, ...)` makes a reward the city earns: locked (greyed, with your
  requirement text) until `condition` - a read-only expression like an advice trigger, e.g.
  `game.g_city_r_population > 5000 and game.g_mayor_rating > 60` - is true, then available in the Rewards menu,
  with the effects of the game's statue or Mayor's House.
- `design_advice(name, advisor, title, message, trigger)` writes advice or a news headline for the advisors (a
  Lua package like the game's own): it appears when its trigger - a read-only expression such as
  `game.g_city_r_population > 1000` - is true. #city# in the text becomes the city's name.
- Designs are plugin files in SiMCP's own Plugins folder (`content_designs()`); the game loads them at start-up, so
  `quit_game()` and `game_launch()` before they appear in `build_menu()`. `disable_design(name)` (with the game
  closed) moves a design's file aside.

## Cheats

`cheat(name, argument)` runs one of the game's player cheats. Cheats are not honest play: SiMCP runs only vetted
ones, logs every use, and `city_status()` shows how many were used in the city. Prefer playing without them.

## Errors

Failures are tool errors with JSON `{"error": ..., "hint": ...}`. The hint says what to do next. Typical ones:
- a city is open and the tool needs the region view (`leave_city` first), or the other way round;
- another SimCity 4 started with administrator rights (GOG Galaxy launches it that way) is running: SiMCP cannot
  control it, but `game_launch` starts SiMCP's own game beside it.
