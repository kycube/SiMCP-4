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

- [ ] Agent-supplied geometry (OBJ or vertices / triangles + PNG textures), roofs, several parts, night lights (M-L)
- [ ] Working civic designs: police, fire, school, power with their own capacity, coverage and costs (M)
- [ ] Custom ordinances and budget departments (the installed host DLLs) (M)
- [ ] Rewards and landmarks with unlock conditions (M)
- [ ] New terrain brushes (M)

## Phase 9 - harder

- [ ] God-mode fire torch (L)
- [ ] Animated content: seasonal trees, animated props (L)
- [ ] Sims and pedestrians as models (L)
- [ ] Custom My Sim faces (L)
- [ ] U-Drive-It content: drivable vehicles, new missions; driving a mission to success (deferred by the user) (L)
- [ ] Terrain looks (global) (L)
- [ ] The old simulator stall (L, needs a reproduction)

## Phase 10 - hardest

- [ ] New network pieces (XL)
- [ ] Bridges and tunnels (XL)
- [ ] Transit-enabled lots (XL)
- [ ] Lot Editor parity (L-XL)
- [ ] Release packaging (M-L)
