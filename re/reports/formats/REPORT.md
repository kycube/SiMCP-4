# RE report: formats (what SiMCP has to write to add a building, lot, prop or texture). SC4 1.1.641, static analysis only

Scratch folder: `<workbench>\re\formats\`. It holds `ex.py` and `dump.py` (exemplar loader with cohort resolution), `catalog_named.txt` (the full property catalogue for buildings, lots and props: ids, counts, types and examples, plus community names), `propnames.json` (1,395 names taken from `sources\sc4-custom-budget-departments\properties files\new_properties.xml`), `rows.py`, `s3d.py` (a 3DMD parser checked on 300 game models), `fsh.py` (a SHPI parser) and the disassembly dumps.

## 1. Answers

**Q1. Exemplar properties.** The full table is in `catalog_named.txt`. The essentials, CONFIRMED from the game's data unless marked:
- Common to all three: 0x10 Exemplar Type (Uint32: 2 building, 0x10 lot, 0x1E prop, 0x0F flora) and 0x20 name (String). The parent cohort TGI sits in the exemplar header, and child values override the cohort's.
- 0x27812810 Occupant Size (Float32×3) is [x width, y height, z depth] in metres.
- Model keys (Uint32 lists):
  - 0x27812820 RKT0 = {T, G, I}: one model for every zoom and rotation.
  - 0x27812821 RKT1 = {0x5AD0E817, group, base}: 20 models. See Q3.
  - 0x27812822 RKT2 and 0x27812823 RKT3 hold explicit instance lists (code 0x496830).
  - 0x27812824 RKT4 is a list of 8-dword state records {state, 0, 0, 0, key kind 0x2781282x, T, G, I}, read at 0x496F18.
  - In the game's 1,544 props: RKT1 738, RKT4 618, RKT0 102.
- Text and menu:
  - 0x8A416A99 User Visible Name Key = {0x2026960B, group, instance}; 0xCA416AB5 Item Description Key.
  - 0x899AFBAD Item Name and 0x8A2602A9 Item Description are plain-string fallbacks.
  - 0x8A2602B8 Item Icon (PNG instance), 0x8A2602B9 Item Order, 0x49CAC341 Plop Cost (Sint64), 0x099AFACD Bulldoze Cost (Sint64).
  - 0xAA1DD396 OccupantGroups (Uint32 list): park [0x1005, 0x1006]; the R$ house [0x1000, 0x11010, 0x2002].
  - 0xEA260589 Lot Resource Key = the lot configuration's IID.
  - 0xEA3209F8 Conditional Building, 0xEA2E078B City Exclusion Group.
  - The menu reads all of these at 0x7EFF40 (rules in `re/reports/lots/REPORT.md`).
- Simulation: 0x27812832 Wealth (Uint8 0-3), 0x27812833 Purpose (Uint8), 0x27812834 Capacity Satisfied [demand id, n] (R$ = [0x1010, 6]), 0x27812840 / 0x27812841 Demand Satisfied / Created, 0x27812850 Park Effect and 0x2781284F Landmark Effect [value, radius], 0x27812851 pollution at centre [air, water, garbage, radiation], 0x68EE9764 pollution radii, 0x27812854 power consumed, 0xC8ED2D84 water consumed, 0x29244DB5 flammability, 0x49BEDA31 max fire stage.
- Family and costs: 0x27812870 Building/prop Family (R 0x1000xxxx, C 0x4000xxxx, I 0x7000xxxx, prop 0xA000xxxx), 0x88FCD877 Building foundation, 0xEA54D283..D286 budget item (department, line, purpose, cost Sint64), 0x8A1C3E72 worth.
- Prop-only: 0x0ABFC024 AppearanceZoomsFlag (seen 0x10 and 0x18: zoom bitmask, GUESS), 0x8A5E5DB8 Is Ground Model, 0xE9A316EB Prop Wealth, 0x49A1E05A Requester Satisfaction, 0x4A149631 Time of Day, 0x6A5E0727 Active Lot State, 0x4A9F188B Light, 0xC98204B8 effect name, 0x69F14D33 Orient To Slope.

What each kind of content needs (LIKELY; the exact growable test is BuildingProfile flags, see lots report Q4):
- **(a) A ploppable building that appears in a menu.** It needs:
  - type 2, a model key, Occupant Size, a menu OccupantGroup (0x1006 park, 0x150A landmark, ...);
  - 0xEA260589 pointing at a lot that exists in group 0xA8FBD372;
  - name (0x8A416A99 or 0x899AFBAD), 0x8A2602B8 icon, 0x49CAC341 cost, plus 0x099AFACD and 0x8A2602B9.
  - Effects such as park effect, budget and sounds come from the cohort or its own properties.
- **(b) A growable R/C/I building.** It needs type 2, size, RKT1, Wealth 0x27812832, Purpose 0x27812833, Capacity Satisfied 0x27812834 (C and I: jobs per wealth), a family 0x27812870 and OccupantGroups (R: 0x1000 + 0x11010 + 0x2002). There is no 0xEA260589: the lot names the building or its family.
- **(c) A prop.** It needs type 0x1E, 0x20, 0x27812810, a model key; optionally a family 0x27812870, 0x0ABFC024 and 0x8A416A99.

Complete examples from the game's data (property ids and types only):
- **Park: PZ1x1_ParkPlayground1, building `6534284A-07BDDF1C-6A636333`.**
  - Parent cohort `05342861-07BDDF1C-00000002` "Park" → `...-00000001` "Civic" (0x10 = 2).
  - Its own properties: 0x20 S; 0x099AFACD i64 10; 0x27812810 f[10, 0, 10]; 0x27812820 RKT0 {S3D, 0xBADB57F1, 0x0E110000}. That model is an invisible 3-vertex "null" mesh: the park's look comes entirely from props and textures on the lot.
  - Also: 0x27812832 u8; 0x27812840 u32[6]; 0x27812850 i32[2]; 0x27812851 i32[4]; 0x27812854 u32; 0x29244DB5 / 0x49BEDA31 u8; 0x2A499F85 u32; 0x49CAC341 i64 90; 0x68EE9764 f[4]; 0x8A2602B8 u32; 0x8A416A99 u32[3]; 0xAA1DD396 [0x1005, 0x1006]; 0xAA1DD397 u32; 0xC8ED2D84 u32; 0xC9B93A56 u32; 0xCA416AB5 u32[3]; 0xEA260589 0x6A636333; 0xEA54D286 i64[1].
- **Park lot `6534284A-A8FBD372-6A636333`** (parent `05342861-A8FBD372-AA1B5002`, which carries slopes, 0x88EDC798 and 0x88FCD877):
  - 0x10 = 0x10; 0x20 S; 0x27812837 u8 1; 0x4A4A88F0 u8 8; 0x88EDC789 u8 2; 0x88EDC790 u8[1, 1]; 0x88EDC793 u8[15]; 0x88EDC795 u8 0; 0x88EDC796 u8 0.
  - Rows 0x88EDC900..0x88EDC90A: 8 props, 1 building, 1 texture.
- **1x1 house: R$6x8_123HouTinyHouse1, building `6534284A-67BDDF0C-004A0000`.**
  - Cohort chain `05342861-67BDDF0C-20000001` (family 0x10000001, fire, pollution, power, water, value) → "R$" (wealth 1) → "Residential" (0x10 = 2, purpose 1, sounds).
  - Its own properties: 0x20, 0x099AFACD, 0x27812810 [6, 8, 8], 0x27812821 RKT1 base 0x004A0000, 0x27812834 [0x1010, 6], 0x499AFA38 u8 9, 0x88FCD877 0x004A1000, 0x8A1C3E72 i64, 0x8A416A99, 0xAA1DD396.
- **House lot R$3_1x1, `6534284A-A8FBD372-300000C0`.** It has the park lot's properties plus 0x88EDC791 family [0x10000001], zone types [1, 2, 3], wealth [1], purpose [1], growth stage 3. Its building row names family 0x10000001; there are also 8 props, 1 flora and 2 textures.

**Q2. Lot configurations** (all CONFIRMED unless marked).
- **Code:**
  - The lot configuration manager loads lots only from exemplars whose group is **0xA8FBD372**. The filter callback at 0x489990 compares the key's group, then calls manager slot 5 (0x489A60), which creates a cSC4LotConfiguration and calls its vtable slot 31 = reader 0x479F70.
  - 0x478AC0 is the reverse: it writes a LotConfiguration back to an exemplar (the Lot Editor's save path).
  - The row reader is 0x479D10 and the row writer 0x4783A0.
- **Lot properties:**
  - 0x88EDC789 version (u8; 2 in the game's data).
  - 0x88EDC790 size [x, z] in cells; 0x88EDC791 family list; 0x88EDC793 zone types; 0x88EDC795 wealth; 0x88EDC796 purpose.
  - 0x27812837 growth stage.
  - Slopes: 0x88EDC792 max slope before a lot foundation, 0xE99B068C max slope allowed, 0x699B08A4 min slope allowed.
  - 0x89136440 water compatibility, 0xE99B068D do-construction, 0x88EDC798 retaining-wall types, 0x88EDC797 fence definition (read, unused in game data), 0x88FCD877 foundation.
  - **0x4A4A88F0 required roads**, bits 0-3 = left, top, right, bottom. If bit 0x08 is missing, the loader logs "should have a road required on the south edge" and sets it (0x47A496..0x47A510).
  - Game values: 8 on 1,703 lots, 12 on 108, 9 on 87, a few with 10/11/13/15.
- **Rows 0x88EDC900..0x88EDCDFF** (Uint32 lists):
  - Reading stops at the first missing id, so rows must be numbered contiguously from 0x88EDC900. Rows with fewer than 10 values are skipped.
  - Fields:
    - [0] object type: 0 building (one per lot), 1 prop, 2 texture, 3 fence (not written back), 4 flora, 5 water cell, 6 land cell, 7 network.
    - [1] detail flags: objects other than buildings are dropped when `([1] & 0x30) >= detail << 4` (detail is a reader argument; LIKELY the lot-detail graphics option). 0x00 always shown, 0x10 medium and up, 0x20 high only; bit 0x01 unknown.
    - [2] orientation 0-3 relative to the lot; bit 31 = mirror flag (struct +3; textures use it).
    - [3..5] x, y, z position and [6..9] minX, minZ, maxX, maxZ: signed **16.16 fixed-point metres** from the lot's corner. One cell is 16 m. y (height) is kept only for props.
    - [10] usage (always 0).
    - [11] object id, unique within the lot (version ≥ 2 only). Version < 2 has no id column, and ids come from the counter 0xB2166C.
    - [12+] the object: building IID or building family; prop IID or prop family (0xA000xxxx, a random member is chosen); flora exemplar IID; lot-texture FSH instance. Type 7 networks: [12] network type, [13..14] edge masks.
- **Facing (LIKELY):** the street edge is lot-local **+z** (z = 16·sizeZ). For-sale-sign props sit at z/depth ≈ 0.95 on 156 lots, and 1,466 of 1,909 building rows use orientation 2.
- **Lot textures:** FSH group 0x0986135E, instances base+0..base+4 (one per zoom).

**Q3. S3D models (`3DMD`).**
- **Loader** 0x806FA0 (CONFIRMED): it reads the chunks in fixed order HEAD, VERT, INDX, PRIM, MATS, ANIM, PROP, REGP (PRIM/MATS 0x80741B, ANIM 0x807971, PROP 0x807E62, REGP 0x807FF9).
  - It checks HEAD major = 1 and minor ≤ 5; minor ≤ 3 is the legacy vertex layout. All game models are 1.5.
  - The loader parses sequentially and does not need the chunk sizes. 83 of 300 sampled Maxis models carry wrong sizes (mostly ANIM). SiMCP should write correct sizes anyway.
- **Chunk layouts:**
  - Each chunk is tag + u32 size (including the 8-byte header).
  - HEAD: u16 major, u16 minor.
  - VERT: u32 block count; each block u16 flags, u16 count, u32 format, then count × stride bytes. The stride comes from 0x8D0370: 3 floats per position count (bits 0-1), 1 dword per colour (bits 8-9), 2 floats per UV set (bits 14-17), plus rarer fields. **0x80004001 = xyz + uv, 20 bytes**, used by every sampled model except legacy code 2 (also 20 bytes).
  - INDX: block u16 flags, u16 stride 2, u16 count, then u16 indices.
  - PRIM: block u16 n, then n × {u32 type (0 = triangle list), u32 first, u32 count}.
  - MATS: per material u32 flags (observed 0xA3, 0xAB, 0xAA), u8 alphaFunc 4, u8 depthFunc 3, u8 src blend, u8 dst blend (1,0 opaque; 4,5 alpha), u16 alpha threshold 0x7FFF, u32 material class, u8 reserved, u8 texture count. Each texture: **u32 FSH instance**, u8 wrapU, u8 wrapV, (minor 5: u8 mag, u8 min), u16 animRate, u16 animMode, u8 name length, name with NUL.
  - ANIM: u16 frames, u16 fps, u16 mode 3, u32 flags, f32 displacement, u16 meshes. Each mesh: u8 name length, u8 flags, name, then per frame u16 vert, index, prim and mats block numbers.
  - PROP and REGP: u32 counts, usually 0. A few REGP entries name effect points ("fx_...").
- **Instances (CONFIRMED by 0x496830 and the data):** RKT1 model = **base + 0x100·zoom + 0x10·rotation**, zoom 0-4 (zoom 1..5), rotation = (view − object orientation) mod 4. Material names suggest the order S, W, N, E.
  - The house has 20 models 0x004A0000..0x004A0430 and a foundation set at base + 0x1000.
  - Every game S3D (41,075) is in group 0xBADB57F1.
  - Maxis buildings are billboards: each model is a few textured quads (the Z1 house: 7 vertices, 18 indices) showing a pre-rendered sprite.
- **Texture lookup (LIKELY, from plugin data):** a model in group 0xBADB57F1 takes its FSH from group **0x1ABE787D**; a model in a custom group takes FSH from the same group.

**Q4. FSH textures (`SHPI`)** (layout from data, LIKELY):
- Header: `SHPI`, u32 file size, u32 entry count, char[4] directory id (`G264` for buildings; `G354` also seen).
- Directory: entry count × {char[4] name, u32 offset}.
- Each bitmap: u32 = code (low byte) | 24-bit offset to the next block (0 = last), u16 width, u16 height, u16 x centre, u16 y centre, u16 x offset, u16 y offset (high nibble of the y offset = mipmap count, rarely set), then the pixel data.
- Codes: 0x60 DXT1, 0x61 DXT3, 0x7D ARGB8888, 0x7F RGB888, 0x78 565, 0x7E 1555, 0x6D 4444, 0x7B 8-bit palette.
- Game building and prop textures: one entry, one level (no mipmaps), DXT1/DXT3, power of two up to 256². They live in SimCity_2..5.dat, group 0x1ABE787D. The FSH container code is at 0xA10607.
- **Menu icon:** PNG (type 0x856DDBAC), group **0x6A386D26**, instance = 0x8A2602B8. It is 176×44 = 4 frames of 44×44 (button states; order GUESS). The menu builder references this group at 0x7EFF40.

**Q5. Names and descriptions.**
- LTEXT record: u16 character count, u16 0x1000, UTF-16LE.
- 0x8A416A99 / 0xCA416AB5 hold the full TGI. The game's own text is in `<Language>\SimCityLocale.DAT` (buildings group 0x0A554AE0, e.g. 0x2A8B735D = "Playground"; props 0x6A554AFD).
- Plugins ship LTEXT in their own DAT under any group (0x6A231EAA, 0x123007BB, ...).
- Menu fallback order (lots report): LTEXT → 0x899AFBAD → 0x20. So SiMCP can skip LTEXT and write 0x899AFBAD / 0x8A2602A9 strings (single language).

**Q6. Choosing ids, and load order.**
- **Fixed groups:** lots **0xA8FBD372** (required). Props 0xC977C536 (all game props; plugins also use 57 other groups). Flora 0xE83E0437. S3D 0xBADB57F1 with FSH 0x1ABE787D. Lot textures 0x0986135E. Icons 0x6A386D26.
- **Free groups:** buildings may use any group (game cohort groups 0x67BDDF0C R, 0x47BDDF12 C, 0xA7BDDF17, 0x07BDDF1C civic/park, 0x8A3858D8, 0xCA386E22; plugins use 33). Building and lot ids are unique by instance id alone (hash maps keyed by IID; building type = IID).
- **Recommendation:** model bases with the low 16 bits zero, not colliding at +0x1000; one private SiMCP group for buildings; random high instance ids checked against the game and plugin inventories before writing.
- **Load order** (sc4-dbpf-loading source; LIKELY for the stock game): game DATs → `<install>\Plugins` → `Documents\SimCity 4\Plugins`. Within a folder: its files in name order, then subfolders depth-first. A later file wins for the same TGI. Extensions: .dat, .SC4Lot, .SC4Desc, .SC4Model and extension-less files (the stock game checks the DBPF signature). So a `Plugins\zzz_SiMCP\` folder loads last.
- Plugins load at start-up only. New content needs a restart, unless the bridge can add a segment at run time (open question 4).

**Q7. Lot Editor, and rendering thumbnails.**
- **The Lot Editor code is present** (CONFIRMED):
  - cSC4WinLotConfigurationChooser: CLSID 0xC918C6FF, layout 0x96A006B0/0x891C9259 "Lot Configurations" with New/Edit/Delete.
  - cSC4WinLotConfigurationEditor: 0x4918C704, layout 0x09234182, created by 0x486D30 from the chooser's Edit handler 0x489490.
  - Network lot chooser 0x29AAD0F6 and editor 0x29AB0142 (layouts 0x89AAD2AA / 0xE9AB008C).
  - Title "Lot Editor -- " at 0x47F0B0; it saves to (0x6534284A, 0xA8FBD372, IID) via 0x478AC0 / 0x47E580.
- **No code references the chooser layout 0x891C9259**, so its entry point was not found statically (GUESS: only reachable in the BAT Lot Editor mode).
- Developer cheat strings exist: "LotPlop" 0xABC948, "BuildingPlop" 0xABC938, "RenderProp", "PlopAllLots" (cheat-class).
- **Thumbnails:** no offline renderer exists. Options:
  1. Decode the Z5 sprite texture of our own RKT1 models (DXT decoding is easy). This is the building image per rotation.
  2. In game: plop the building in a test city and use the snapshot command (kCommandID_OpenSnapshotDialog / "TakeSnapshot").

## 2. Layouts (CONFIRMED from the reader and writer)
- **cSC4LotConfiguration:** +8 IID; +0xC name; +0x20/+0x21 size; +0x24 family vector; +0x30 max slope; +0x34 min slope; +0x38 foundation slope; +0x3C growth stage; +0x42 water compatibility; +0x44/+0x58/+0x6C zone, wealth and purpose bitsets; +0x8D do-construction; +0x8E required roads; +0x90 object vector; +0x9C retaining walls.
- **Lot object (0x34 bytes):** +0 type; +1 detail flags; +2 orientation; +3 mirror; +4/+8/+0xC x, y, z floats (metres); +0x10 maxX; +0x14 maxZ; +0x18 minX; +0x1C minZ; +0x20 usage; +0x24 object id; +0x28 IID vector.

## 3. Recipe: install a ploppable park
1. Write one DBPF with `sc4_mcp.dbpf.write_dbpf` (QFS + DIR are already handled) into `Plugins\zzz_SiMCP\<name>.dat`, containing:
   - The building exemplar (parent cohort Park `05342861-07BDDF1C-00000002`): Q1(a) properties.
   - The lot exemplar (group 0xA8FBD372, parent `05342861-A8FBD372-AA1B5002`): version 2, size, zones [15], roads 0x08, rows 0x88EDC900.. in order. Row 0 is the building row `[0, 0, 2, x, 0, z, minX, minZ, maxX, maxZ, 0, oid, buildingIID]` in 16.16 metres, then texture and prop rows.
   - 20 S3D models (RKT1), their FSH (0x1ABE787D), the PNG icon (0x6A386D26), and the name as 0x899AFBAD or an LTEXT record.
2. Restart the game.
3. Honest play: the item then goes through the normal menu and plop path (costs charged).
4. Growables (a lot with a family row plus a building in that family): the game develops them itself. Placing one directly with PlaceLot is cheat-class.

## 4. Open questions (live tests)
1. Install a test park DAT in `Plugins\zzz_SiMCP\`, restart, and confirm it appears in the Parks menu. LotConfigMgr slot 8 (IID) should return non-null.
2. Read the lot-detail setting and check that props with flag 0x20 disappear at medium detail.
3. Plop a lot whose 0x4A4A88F0 has bit 0x08 only, and confirm the road must touch the +z edge.
4. Can the bridge load a new DAT at run time (resource manager: add a segment) and then call LotConfigMgr slot 5 and the BuildingDevelopmentSim loader without restarting?
5. Test a model in a private S3D group with its FSH in the same group, to confirm the texture-group rule.
6. Find what opens layout 0x891C9259: try GZCOM `CreateInstance(0xC918C6FF)` from the bridge on a test city.
