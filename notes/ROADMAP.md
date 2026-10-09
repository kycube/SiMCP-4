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
- [ ] Night lights for designs (how the game lights a 3D model's windows at night is not found yet)
- [x] Working civic designs: police, fire, clinic, school with their own coverage, strength / capacity and costs (M) - power plants not yet (their output property is not pinned down)
- [x] Custom ordinances and budget departments (the installed host DLLs) (M)
- [x] Rewards with unlock conditions (M) - landmarks are plain ploppables already (design_model_building)
- [x] New terrain brushes (M) - scaled copies of the game's god-mode brushes

## Phase 9 - harder

- [x] God-mode fire torch (L)
- [x] Animated content: seasonal trees, props by hours and dates (L) - animation frames are written as the game's animated props have them, but neither a Maxis animated prop nor ours was seen to move in snapshots
- [ ] Sims and pedestrians as models (L) - format read (LIVE_FACTS); making new ones moved to Phase 11
- [x] Custom My Sim faces (L) - MySims.dat and 36 x 36 pictures in the MySim folder
- [ ] Terrain looks (global) (L)
- [ ] The old simulator stall (L, needs a reproduction)

## Phase 10 - hardest

- [ ] New network pieces (XL)
- [ ] Bridges and tunnels (XL)
- [ ] Transit-enabled lots (XL)
- [ ] Lot Editor parity (L-XL)
- [ ] Release packaging (M-L)

## Phase 11 - realism polish (last)

The aim, as with SiMCP 3000: learn and write down best practices for realistic content within the bounds and the
style of the game, working from photographs of real things as references, and bring SiMCP's own content up to
them.

- [ ] Cars and trucks: real proportions, paint, glass, lights, wheels; the game's look at every zoom
- [ ] Buildings: homes, shops, parks, landmarks - massing, roofs, windows, materials, lots that read as real
- [ ] Props: street furniture, signs, statues
- [ ] Vegetation: trees (broadleaf, conifer, palm, seasonal) and shrubs, hedges, flower beds
- [ ] Pedestrians: new walkers as sprite atlases (the format is in LIVE_FACTS, Phase 9)
- [ ] A written guide of what worked (scale, texture size and detail, colour against the game's palette, shading,
      silhouettes at each zoom) for agents designing content

U-Drive-It (drivable vehicles, missions) is left out for now, at the user's request.
