# Changelog

## 0.12.1

- **Walkers play their whole walk cycle**: a sprite's frame count is its descriptor's last value (the game's
  walkers: 11 per direction). design_walker drew 8 frames per direction under a descriptor saying 11, so the game
  showed 3 frames of another direction in every loop; it now draws 11 and writes the count it drew (the frame
  table keeps the game's constant 8). Seen in the game with probe walkers: every frame of the cycle, nothing from
  another direction. Rebuild older walker designs with `design_walker(..., replace=true)`.

## 0.12.0

The roadmap's last open items (all but U-Drive-It, left out at the user's request). 114 tools.

- **Power plants as designs**: `design_civic_building(kind="coal_power" | "oil_power" | "gas_power" |
  "wind_power")` copies the base game's plant (output 0x27812852, type, pollution, costs) under its own model;
  `output_mwh` may lower the output, never raise it. Civic designs take `parts_model`, `lot_depth` and `replace`.
  "MCP Gas Plant" (built from parts after combined-cycle plants) supplied its 3,000 MWh in MCP Village.
- **Older designs brought up to date**: `upgrade_designs` gives designs with one model (drawn the same from every
  side) a turned model per view under the same ids; shape and OBJ props are now made per view (a sign faces its
  street). Animated props keep one model, as the game's own.
- **The old simulator stall, prevented where it could start**: the bridge refuses calls to addresses that are not
  code and to objects that are not live (status -4), counts them (`game_status` calls_refused) - the faults logged
  after loading a city were such calls. Not reproduced since.
- **Lots**: props take `"y"` (metres above the ground), as the game's plant lots raise their smoke to the stacks.
- **Night**: "glow" on a window pattern lights only its panes.
- Animated props confirmed moving in the game (the earlier snapshots were a whole loop apart).

## 0.11.0

Phase 11, realism: new content drawn the way the game's own is made, and best practices learned from photographs
and from judging the results in the game beside Maxis' own (guide topic "realism"; `notes/LIVE_FACTS.md`). 113 tools.

- **Buildings rendered as the game's own** (`batrender`): every view - five zooms, four rotations - rendered with
  the Building Architect's camera and sun (as BAT4Blender documents them and as measured on the game's models),
  shadows, sky occlusion, weathering and a night light layer (lit windows, lamps), laid over the model's
  camera-facing triangles or a low-poly shell, in DXT1 / DXT3 tiles. The view rule measured with probes: index
  (lot facing - camera rotation) mod 4, the model turned r + 2 quarter turns.
- **Buildings from parts and photos**: `photo_add` / `photo_view` / `photo_rectify`, `parts_preview` (the game's
  own views), `design_model_building(parts_model=..., lot_depth=..., replace=true)`,
  `design_growable_building(parts_model=..., objects=...)`; a Craftsman bungalow, the Flatiron Building.
- **Trees and shrubs** (`design_tree`): broadleaf, conifer, palm and shrub built of rendered leaf clumps;
  `design_seasonal_tree` renders each season (blossom, autumn colours, bare limbs, snow).
- **Props** (`design_prop(parts_model=...)`): rendered per view; a bench, an acorn lamp, a statue, park paths;
  lamps ("glow" materials) light up at night with the game's light flare.
- **Cars** (`design_car`): sedan, hatchback, SUV, van and pickup with real side profiles, glass cabins, rimmed
  wheels and painted textures.
- **Pedestrians** (`design_walker`): sprite atlases rendered from a posed figure, 8 directions x 8 walk frames.

## 0.10.0

The roadmap's Phases 1-10 (see `notes/ROADMAP.md`; what each step showed in the running game is in
`notes/LIVE_FACTS.md`). 108 tools.

- **Play**: launching the game beside the player's own (its own user folder; the player's plugins mirrored
  read-only), regions and cities, the camera and snapshots, time, the budget and ordinances, building networks,
  zones and lots as the player's tools do (bridges by name, tunnels reported), puzzle pieces (the game's and NAM's),
  data views, advisors and news, disasters and emergency dispatch, My Sims, neighbour deals, terraforming,
  options, housekeeping.
- **New content**: menu buildings (copied or with their own model, OBJ import), growables, civic buildings that
  work as the game's, rewards, ordinances and budget departments, advice and news, trees, cars, props (timed,
  animated), parks and lots, seasonal trees, terrain brushes, terrain looks, My Sim faces, puzzle pieces captured
  from networks laid in a city, bridges, transit stations, and lots edited as in the Lot Editor.
- **Release**: `simcp4` command, `python -m sc4_mcp --check` / the `setup_check` tool, wheels that bundle the
  plugin and bridge DLLs (`scripts/package_release.py`).
