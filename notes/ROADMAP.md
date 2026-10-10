# Roadmap

What is left after phases 1-4 and the follow-ups of 2026-10-08, ranked from the easiest to the hardest. Each phase
ends with a commit; `LIVE_FACTS.md` records how every item was verified. S = about an hour, M = several hours,
L = a day or more, XL = several days.

## Phase 5 - low-hanging

- [x] Small upkeep: Pillow deprecation in heightmap, retire the test advice designs (S)
- [x] Menu icons for designs (S)
- [x] Creating My Sims: name, sign and one of the 21 faces (the face sets the gender; the dialog has no description field) (S)
- [x] Seaport zones on a city with water (S)
- [x] Strikes and jailbreaks status (S)
- [x] Region housekeeping: rename a region, delete a city / region (confirmed), back up a region (S)
- [x] Graphics and sound settings through the options dialogs' path (S-M)
- [x] School / hospital auto-budget: not a player option in this version, so not offered (cheat-class) (S)
- [x] Starting an offered neighbour deal: the game has no offered state - deals start when proposed (S-M)

## Phase 6 - new trees and vehicles

- [x] New tree types: flora exemplars with generated crossed-plane models (M) - painted placeholders or an agent's picture; better-looking trees come with Phase 8's meshes
- [x] New cars and trucks: automata exemplars with generated models, in the game's traffic (M) - sedan, van, pickup bodies as placeholders; trucks and better models come with Phase 8's meshes

## Phase 7 - props and lots

- [x] New props (M) - box, cylinder, cone, sign with a picture
- [x] Lot designer: game props, trees, textures on a design's lot (M) - fences not yet (the format notes call type-3 fence rows "not written back"; untested)

## Phase 8 - real buildings

- [x] Agent-supplied geometry: OBJ + MTL + PNG / JPEG textures, roofs, several parts (M-L)
- [x] Night lights for designs (Phase 11) - a night layer of DXT3 textures at instance + 0x8000 (lit windows, lamps, glowing materials; window patterns light only their panes); lamp props switch to the game's light flare at night
- [x] Working civic designs: police, fire, clinic, school with their own coverage, strength / capacity and costs (M); power plants (coal, oil, gas, wind: output 0x27812852 up to the game's plant of that kind) - a gas plant from parts supplied its 3,000 MWh in MCP Village
- [x] Custom ordinances and budget departments (the installed host DLLs) (M)
- [x] Rewards with unlock conditions (M) - landmarks are plain ploppables already (design_model_building)
- [x] New terrain brushes (M) - scaled copies of the game's god-mode brushes

## Phase 9 - harder

- [x] God-mode fire torch (L)
- [x] Animated content: seasonal trees, props by hours and dates (L); animated props (spin, sway) seen moving - the earlier snapshots were taken a whole loop apart
- [x] Sims and pedestrians as models (L) - new walkers as sprite atlases (design_walker, Phase 11)
- [x] Custom My Sim faces (L) - MySims.dat and 36 x 36 pictures in the MySim folder
- [x] Terrain looks (global) (L) - recoloured ground / beach / cliff textures and a drier or wetter texture table, as one plugin
- [x] The old simulator stall (L) - not reproduced; prevented where it could start: the bridge refuses calls to addresses that are not code and to objects that are not live (the faults logged after loading a city were such calls), counts them (game_status calls_refused), and the crash log names the op behind any caught fault

## Phase 10 - hardest

- [x] New network pieces (XL) - placing the game's and NAM's puzzle pieces (puzzle_pieces, place_puzzle_piece) and new ones captured from ground networks laid in a city (design_puzzle_piece; 3D tiles - bridges, elevated pieces - not yet)
- [x] Bridges and tunnels (XL) - bridges by name and tunnels reported on each drag (build_network); new bridges copied from the game's under a new name and deck height (design_bridge); recoloured bridge models: Phase 11
- [x] Transit-enabled lots (XL) - new stations on copies of the game's station lots, network tiles and transit properties kept (design_transit_station); ridership of a new station not measured yet
- [x] Lot Editor parity (L-XL) - any game lot read row by row (lot_layout) and edited copies with rows removed, moved or added (edit_lot), next to new lots (design_park, design_model_building) and growables; lots from other plugins are not read yet
- [x] Release packaging (M-L) - version 0.10.0, the simcp4 command, setup_check / --check, a wheel that bundles the DLLs and a release zip (scripts/package_release.py, CI artifact), client examples, CHANGELOG

## Phase 11 - realism polish (last)

The aim, as with SiMCP 3000: learn and write down best practices for realistic content within the bounds and the
style of the game, working from photographs of real things as references, and bring SiMCP's own content up to
them.

- [x] Cars and trucks: real side profiles, glass cabin, wheels with rims, painted texture (sedan, hatchback, SUV,
      van, pickup); seen in traffic
- [x] Buildings: rendered as the game's own (batrender: camera, sun, shadows, night lights, weathering); a
      Craftsman bungalow (ploppable, and grown by MCP Village and MCP Town), a pocket park, the Flatiron Building
- [x] Props: rendered per view (bench, acorn lamp, statue, paths), scaled as the game's; lamps light up at night
- [x] Vegetation: broadleaf, conifer, palm, shrub of rendered leaf clumps; seasonal trees rendered per season
- [x] Pedestrians: new walkers rendered as sprite atlases (design_walker), direction order measured
- [x] A written guide of what worked: guide topic "realism" (best practices 1 - 18)
- [x] Older designs brought up to date: upgrade_designs gives single-model designs a turned model per view (the Sign now faces its street), old trees re-rendered; per-view models for shape and OBJ props

I've left U-Drive-It (drivable vehicles, missions) out for now.
