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
  unfold while the game runs. `disaster_status()` lists what is going on. Fire is god mode's torch: it lights the cell you
  give (a building or trees there burn and spread).
- `dispatch(unit, x, z)` sends fire or police units, as the dispatch buttons do (a station with a free unit and a
  road route is needed).

## U-Drive-It and My Sims

- `missions()` lists the missions the City Situations advisor offers and the mission / vehicle state;
  `start_mission(title)` makes the game offer one (let the city run a few seconds first so vehicles are out) and
  `close_dialog("Accept")` starts it. `drive(keys, seconds)` holds driving keys (accelerate, brake, left, right...)
  - the game must be running; `missions()` gives the vehicle's cell and heading and the target's cell.
  `stop_driving()` leaves the vehicle.
- Puzzle pieces (interchanges, ramps, NAM's roundabouts, turn lanes, overpasses...): `puzzle_pieces(query)`
  finds them by name or group, `puzzle_pieces(hid=...)` gives one's size, rotations and Tab ring, and
  `place_puzzle_piece(hid, x, z)` places it with its handle on that cell, charged like the player's tool.
  Check first with build=false: the result's cells are where it lands (NAM's FLEX pieces sit a cell off their
  handle). auto_fit tries neighbouring cells and other rotations, as the tool does under the pointer.
- Bridges and tunnels come with build_network: over water the leg lists `bridge_choices` (names, as the
  bridge chooser shows them) and `bridge="Stone Arch"` picks one; a drag into a steep hill becomes a tunnel
  where the game's solver makes one. Each leg reports its `bridges` and `tunnels` (from, to, cells).
  `bridges(query)` lists every bridge the game loads; `design_bridge(name, base, height_m)` copies one under a
  new name with its deck higher or lower (after a restart it is in the choices).
- The Lot Editor: `lot_layout(lot)` lists what a lot holds, row by row (building, props - a list of ids is a
  prop family, one picked at random -, ground textures, trees, network tiles, water and land constraints) with
  positions in metres; `edit_lot(name, lot, remove, move, add)` makes a new item from a game lot with rows
  taken out, moved or turned and props, trees and grounds added.
- Transit stations: `design_transit_station(name, kind)` (bus, subway, light_rail, monorail, passenger_rail,
  freight_rail, ferries, parking, toll_booth...) copies the game's station lot - its size and, for transit-
  enabled lots, its network tiles - and the station's transit properties, with SiMCP's building (a block or an
  OBJ model). Elevated stations draw their track as part of the building: give such a station a model with the
  platform, or the track on its lot is invisible.
- New puzzle pieces: lay ground networks (roads, streets, avenues, one-way, dirt, rail...) in an empty corner
  with build_network, then `design_puzzle_piece(name, x0, z0, x1, z1)` makes them a piece: the cells keep the
  tiles they show and their traffic paths, and the cells whose networks leave the rectangle stay ordinary
  network so roads can join the piece there (capture a little past a junction to give it open ends). It joins
  the game at the next start (quit_game, game_launch); `place_puzzle_piece(hid, x, z)` puts its north-west cell
  on (x, z), with three more rotations. Keep a piece while saved cities use it.
- `move_in_sim(x, z)` moves a My Sim into the house on a cell; `my_sims()` follows them (home, job, where they are).
- `design_my_sim_face(name, gender, sign, image_path)` adds a face of one's own to the Select A My Sim dialog (a
  photo cropped and scaled to 36 x 36, or a simple drawn face); `move_in_sim(x, z, face=name)` uses it. A city
  keeps the picture's file name: if the picture goes (`remove_my_sim_face`), that Sim shows a blank face.

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
  props, trees and ground textures (paving, plaza, concrete, asphalt, grass, lawn, yard, meadow, gravel, garden, sand,
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
  building) with its own model (block, OBJ or `parts_model`), name, costs, coverage radius and strength or
  capacity, and appears in its service's menu. Fund it like any other (set_building_funding). Power plants too:
  kind `coal_power`, `oil_power`, `gas_power` or `wind_power` copies the base game's plant of that kind (output,
  pollution, ageing, costs; lot 4 x 4, wind 2 x 1) - `output_mwh` can lower its output, never raise it above the
  game's own (honest play); solar, nuclear and hydrogen are left out because the game unlocks them by its own
  conditions. Raise its smoke to the stacks as the game's plant lots do: objects
  `{"prop": "0x2A94B0DB", "x": m, "z": m, "y": stack height}` (gas smoke; 0x005B0000 is the oil plants' smoke).
- `design_reward(name, condition, requirement, ...)` makes a reward the city earns: locked (greyed, with your
  requirement text) until `condition` - a read-only expression like an advice trigger, e.g.
  `game.g_city_r_population > 5000 and game.g_mayor_rating > 60` - is true, then available in the Rewards menu,
  with the effects of the game's statue or Mayor's House.
- `design_ordinance(name, description, monthly, enact_cost, effects, condition)` adds an ordinance to the
  Ordinances window (through the installed custom ordinance DLL): monthly income or cost, effects such as
  crime 0.9 or mayor_rating 3, available when `condition` holds (checked monthly). The game keeps an
  ordinance's values in a city's save. `design_model_building(..., department={...})` gives a building its
  own budget department (name, budget group, monthly cost and / or income) in the Budget window.
- `design_brush(name, base, radius_scale, strength_scale)` makes a god-mode terrain brush from one of the game's
  (a wider mountain, a gentler valley...); after a restart `terraform("simcp_<name>", ...)` uses it before a
  city is founded.
- `terrain_look(look)` changes how all terrain looks, in every city: `lush`, `arid`, `arctic` (snow), `autumn`,
  or `custom` values (moisture_shift moves the game's texture table drier or wetter; saturation, brightness,
  tint, snow, autumn recolour the game's own textures); `default` goes back. The running game keeps the file
  open: `quit_game()`, `terrain_look(...)`, `game_launch()`. Look in daylight (`day_night("day")`): evening
  light turns snow beige.
- Things that change: `design_seasonal_tree(name, shape)` makes a tree for lots that follows the seasons
  (blossom from 1 March, summer from 1 June, autumn colours from 1 September, bare or snowy from 1 December):
  place it with {"seasonal_tree": name, "x", "z"}. Each season appears at its start date, so a lot placed
  mid-season shows that tree from the next season change on. `design_prop(..., hours=[19, 6])` shows a prop
  only at those hours of the game's day (at night here; the game's day / night cycle must run - forced day or
  night freezes it), `dates={"start": [12, 1], "days": 31}` only on those dates every year, and
  `animation="spin"` / `"sway"` gives it animation frames like the game's animated props (it moves on the
  game's draw clock, paused or not; a loop is 2 s, so snapshots a whole number of loops apart look the same).
  Flora planted with plant_trees never changes: the game runs no growth or succession for trees.
- Lot objects take `"y"`: metres above the ground for a prop (smoke at a chimney top, a prop on a roof).
- `design_advice(name, advisor, title, message, trigger)` writes advice or a news headline for the advisors (a
  Lua package like the game's own): it appears when its trigger - a read-only expression such as
  `game.g_city_r_population > 1000` - is true. #city# in the text becomes the city's name.
- Designs are plugin files in SiMCP's own Plugins folder (`content_designs()`); the game loads them at start-up, so
  `quit_game()` and `game_launch()` before they appear in `build_menu()`. `disable_design(name)` (with the game
  closed) moves a design's file aside. `upgrade_designs()` (game closed) brings designs made by older SiMCP
  versions up to date: a single model, which the game draws the same from every side, becomes a turned model per
  view, under the same ids (lots in saved cities show it after a restart).

## Buildings from parts (photo to building)

For realistic buildings, describe the building as 3D parts in metres and draw its walls as authored facades
measured from a photograph (SiMCP 3000's photo-to-building model): `design_model_building(name, 0, 0, 0,
lot_cells=..., parts_model={...})`.

1. `photo_add(name, image_path, crop, scale)` - a reference photo (kept in SiMCP's home, never the game's).
2. `photo_view(name, x0, y0, x1, y1, grid)` - read corners, eaves, ridges, storey lines, windows and doors off a
   pixel grid; `photo_rectify(name, quad, width_m, height_m)` shows a facade with the perspective removed.
3. Write the model: {"materials": {name: {...}}, "parts": [{"type": ...}, ...]}. Axes: x and y on the lot in
   metres from its corner (a cell is 16 m), the +y side facing the street, +x is west, z up. Parts: box, extrude,
   prism / cylinder, cone / pyramid, roof (hip, gable_x, gable_y, pyramid, shed_+x / -x / +y / -y, flat; pitch,
   overhang, gable, bargeboard, finial, ridge_cap), beam, panel, patch. Materials: color, pattern (clapboard,
   shingle, fishscale, brick, stone, roof_shingle, slate, paving, clapboard_window, wall_window), texture (a
   picture file), photo (with quad), facade (authored: windows, doors, bands, railings, ornaments at measured
   positions). partmodel.py and facade.py document every key.
4. `parts_preview(parts_model, lot_cells, zoom=5, scale=2)` - the building exactly as the game will draw it, all
   four sides, without the game; iterate on the massing first.
5. `design_model_building(...)` writes the building the way the game's own are made (the Building Architect's
   way): every view - five zooms, four rotations - rendered with the game's camera and light (a warm sun from the
   viewer's left, blue shade, shadows, sky occlusion) and laid over the model's triangles that face the camera.
   quit_game, game_launch, plop it, and judge it with `snapshot` at the closest zoom in daylight, in all four
   rotations, beside the game's own. To iterate, `design_model_building(..., replace=true)` (with the game
   closed) rebuilds it under the same ids: copies already placed update after game_launch.
6. Homes the city grows: `design_growable_building(name, "residential", wealth, 0, 0, 0, [0, 0, 0], [0, 0, 0],
   lot_width=1, lot_depth=2, stage=1, parts_model=..., objects=[...])` - the same model on a growable lot (the
   game's house lots are 1 x 2 or 1 x 3; x across the lot, y toward the street). Plop a copy first
   (`design_model_building(..., lot_cells=1, lot_depth=2)`) to judge it. Match the wealth to the city (a small
   town grows $ houses: check `demand()`), use stage 1 for young towns, and zone two cells deep along a street
   joined to the road network (`zone(..., streets=false)`; start new streets on the road they branch from) - the
   design then takes its share of new lots (one in eight among the game's seven $ 1 x 2 stage-1 houses).

## Realism (best practices)

Learned building houses after photographs and judging them in the game beside Maxis' own (more in
notes/LIVE_FACTS.md). The game's look: an orthographic camera 45 degrees from the vertical, 7 px per metre at the
closest zoom, a warm sun from the viewer's left and blue shade - SiMCP renders every view that way, so what you
choose is shape, size, colour and detail.

The camera
1. Roofs dominate. From 45 degrees a one-storey house is mostly roof; walls show for their height minus the
   overhang. Keep overhangs at 0.4 - 0.6 m, roof pitches 30 - 40 degrees (shallower reads as a flat grey slab),
   and break big roofs with a front gable, dormers or a lower porch roof.
2. What sits under a roof is hidden. A porch under the main roof does not read; give it its own roof (a front
   gable over the porch is the strongest), and make piers, steps and the porch beam parts.
3. Silhouette and volumes beat paint: chimneys, gables, bays, porches and steps are parts. Fine trim under about
   0.15 m is a pixel at most; use light lines (bargeboards, ridge caps, fascia beams 0.2 - 0.3 m deep) to draw
   the roof's shape.
4. Check every view: parts_preview(..., rotation=-1, scale=3) shows all four sides at 3x. Nothing may poke
   through a roof (a box top under a shallow roof shows as a bright patch); overlapping parts are fine.

Size
5. Scale to the game, not only to the photo: Maxis' 1 x 2 middle-income house lot holds a house about 12 x 10 m;
   a real bungalow of 11 x 15 m looked bulky beside it. Front yards are short (the house near the street), back
   yards long.

Colour and material
6. Pick colours as the material looks in daylight; the renderer adds the sun and the shade (a white wall comes
   out about (225, 210, 200) in the sun and (85, 82, 108) in the shade, as the game's own). Roofs a little darker
   and cooler than they seem (asphalt shingle about #4f5150).
7. Every material gets weathering ("grain", default 0.06; 0.1 - 0.15 for roofs and paving): blotches in model
   space, the same in every view, no tiling. Clean flat colours look like plastic beside Maxis' textures.
8. Authored facades (windows, doors, trim at measured places) beat pasted photos; windows need a frame and sill in
   a colour that contrasts with the wall to read at 7 px per metre.

Night
9. Lit windows make a building belong at night: facades light a share of their windows ("night": {"lit":
   0.65}) and lamps ({"type": "lamp", ...}); the game lays this light over the building a few seconds after
   dusk. A building without lights sits dark among lit neighbours. "glow" on a wall_window / clapboard_window
   pattern lights only its panes (a plain glowing material lights all over: keep that for lamps, signs and
   warning lights - a red ring at a stack's top reads at night).

The lot
10. Dress lots as Maxis does: the natural lawn ground "yard" (the striped "lawn" is a sports field), shrubs along
    the front of the house (game prop 0x1ECF0000 and other "Shrub", "Bush", "Flowers" props from game_props), a
    maple or two, a walk from the street to the door and a driveway (patch parts, a dark grey). The game draws
    the building's shadow on the ground itself; nothing to paint.

Landmarks and tall buildings
11. Work from two photographs if you can: one from the street (facade, storeys, ornament) and one from above (the
    roof, the plan - the game's camera is above). Extrude the plan ("extrude" with the footprint's points) in
    sections - base, shaft, crown - each with facades generated per edge (a script: bays, floor bands, windows);
    a cornice is the plan grown by a metre or so; an offset plan's sharp corners grow fast, so check the lot.
12. Big facades: 12 - 16 px per metre ("px_per_m") is enough at the game's 7 px per metre and keeps renders fast.

Trees and shrubs
13a. Seasons: design_seasonal_tree renders each season (blossom, summer, autumn colours, bare limbs or snow); a
    seasonal tree placed mid-season shows from the next season's start date (1 March, 1 June, 1 September,
    1 December). "snow" works on any material (roofs too).
13. design_tree draws broadleaf, conifer, palm and shrub as the game's own trees are made: leaf clumps with
    see-through leaf textures, lit by the sun with their own shadows, the light wrapping through the leaves. Keep
    foliage olive and a little muted (the default); bright pure greens look plastic. Dense models are laid on a
    low-poly shell automatically (the game does not draw tree models with thousands of vertices).

Props
14a. Lamps: give the lamp's glass a material with "glow" - the prop then lights up at night with the game's own
    light flare, as its lamp posts do. A prop takes its day and night states when placed: lots placed before the
    prop had lights stay dark until they are placed again.
14. Props are seen from far above: make them 1.5 - 2 times life size ("scale": 1.7), as the game's own benches
    (3 - 4 m) and lamp posts (7 - 8 m) are, with members at least 0.15 m thick; at life size they vanish.
15. Trees on lots: use the game's tree props (game_props("deciduous"), "pine", "palm": full-size at once) rather
    than flora on the lot, which stays a sapling.

Cars
16. Cars are lit by the game per face; what makes them real is the side profile (raked glass, hood, deck), a
    cabin narrower than the body, wheels with rims, and real paint colours - silver, white, black, greys, dark
    blue, deep red. Pure saturated colours look like toys.

Pedestrians
17. design_walker draws a person as the game's walkers are: about life size at the two closest zooms, 8
    directions x 8 walk frames, a short shadow. Clothes in everyday colours (navy, grey, denim, a few warm
    tops) read as a crowd; one bright colour on everyone looks like a uniform.

Industry
18. Industrial buildings beside the game's own look grimy, not new: greyed colours (cladding about #b3b5b1,
    roofs #75797a), weathering 0.1 - 0.12, roof clutter (vents, ducts, a pipe rack) and the game's own smoke
    props raised to the stack tops (lot objects with "y"). A plant's parts: a long hall with a band of high
    windows, boxy process units, tall stacks with a dark band and a red ring at the top, tanks, cooling cells
    with fan shrouds, a transformer yard toward the street.

## Cheats

`cheat(name, argument)` runs one of the game's player cheats. Cheats are not honest play: SiMCP runs only vetted
ones, logs every use, and `city_status()` shows how many were used in the city. Prefer playing without them.

## Errors

Failures are tool errors with JSON `{"error": ..., "hint": ...}`. The hint says what to do next. Typical ones:
- a city is open and the tool needs the region view (`leave_city` first), or the other way round;
- another SimCity 4 started with administrator rights (GOG Galaxy launches it that way) is running: SiMCP cannot
  control it, but `game_launch` starts SiMCP's own game beside it.
