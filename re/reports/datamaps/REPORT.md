# datamaps: per-cell data layers readable from memory (SimCity 4 1.1.641, static analysis only)

Scratch: `<workbench>\re\datamaps\` (`layers.tsv`: every layer with its global, offset, type and notes; simulator
vtables beside the gzcom-dll names; the map-view dump). Offsets are relative to the cached pointer (the interface
at object+0; fire and police included: ctor 0x6ADA50 puts vtable 0xAB1160 at +0 and the service base at +8).

## 1. Answers

**Q1. The grid class cSC4SimGrid\<T\>** (CONFIRMED by code)
- Factories registered at 0x4605B0 (CLSID 0x49B9E601..0B -> ctor); every grid is `new(0x44)`. Primary vtables: u8
  0xA878C0 (Bool8 shares it, reports 0x602), s8 0xA87950, u16 0xA87D40, s16 0xA879E0, u32 0xA87DD0, s32 0xA87A70,
  u64 0xA87B00, s64 0xA87B90, f32 0xA87C20, f64 0xA87CB0.
- **Each ctor writes its type CLSID into +0x10**: 0x602 u8, 0x603 s8, 0x604 u16, 0x605 s16, 0x606 u32, 0x607 s32,
  0x608 u64, 0x609 s64, 0x60A f32, 0x60B f64 (low part of 0x49B9E6xx).
- Windows slot order = gzcom-dll: 7 GetCellValue(x,z) = tract value at (x>>shift, z>>shift), no bounds check;
  9 SetTractSize; 10 size; 11 shift; 12/13 CountX/Z; 22 GetTractValue; 24/25 GetGridData (`lea eax,[ecx+0x38]`);
  26 SetTractValue; 27 SetTractValues; 28 dtor.
- Layout: 0 vtable; 4 second vtable; 8 init byte; 0xC refcount; **0x10 type CLSID**; 0x14 instance id; **0x18 tract
  size**; **0x1C shift**; **0x20 / 0x24 tract count X / Z** (= city cells >> shift); 0x28/0x2C tract width in metres;
  0x30/0x34 1/width; **0x38 / 0x3C / 0x40 STLport `vector<vector<T>>` begin / end / cap**.
- **X-major**: `row = [[g+0x38] + 12*tx]` (each 12-byte entry an inner vector, first dword = data); value = T at
  `row + tz*sizeof(T)`. Cell (x,z): `tx = x >> [g+0x1C]`, `tz = z >> [g+0x1C]`. (SetTractSize 0x460FC0, GetTractValue
  0x45E0D0, data-view renderer 0x7A2380 walk the same vectors.)
- Coarse grids: air / water / radiation pollution tract 2, slope tract 8; other sizes come from exemplar values in
  simulator fields. **Always read +0x18/+0x1C at run time.**

**Q2. Layers** (CONFIRMED by getter bodies and grid ctors unless marked). Recipe `[global] -> +off -> grid`.

| Layer | Recipe | Type | Getter / notes |
|---|---|---|---|
| Zones | `[0xB43D14]+0x48` | s8 | slot 5. 0 none, 1-3 R low/med/high, 4-6 C, 7 agriculture, 8-9 I med/high, 10 military, 11 airport, 12 seaport, 13 spaceport, 14 landfill, 15 plopped |
| Land value | `[0xB43D88]+0x28` | u8 | slot 8 (data view 2); bands at bytes [LV+0x7F]/[LV+0x80] (0x6BD700) |
| Intrinsic land value | `[0xB43D88]+0x24` | u8 | slot 7 |
| Slope | `[0xB43D88]+0x30` | f32 | slot 9, tract 8 |
| Crime | `[0xB43D70]+0x5C` | u8 | slot 5 |
| Police coverage | `[0xB43D98]+0x80` | **u8** | slot 5 (header's short is wrong for 1.1.641; s16 companion at +0x84 unexplained) |
| Fire coverage | `[0xB43D78]+0x80` | **u8** | slot 5 |
| Flammability | `[0xB43D7C]+0x58` | u8 | slot 5 |
| Air pollution | `[0xB43D9C]+0x50` | s16 | GetPollutionGrid(0) (slot 5: t -> +0x50+4t, t=3 -> +0x4C) |
| Water pollution | `[0xB43D9C]+0x54` | s16 | (1) |
| Garbage | `[0xB43D9C]+0x58` | s16 | (2), tract 1 |
| Radiation | `[0xB43D9C]+0x4C` | s16 | (3); IsRadioactive |
| Pollution sources (LIKELY) | `[0xB43D9C]+0x40/+0x44/+0x48` | s16 | GetPollutionValue (slot 6) |
| Power | `[0xB43DA0]+0x80` | u8 | slots 35/36: **0 no consumer, 1 wired unpowered, 2 powered** (0x6EBE8F) |
| Power bitmaps | `[P+0x2C8]` wired, `[P+0x2D4]` powered, `[P+0x2D0]` mask | dwords | bit n = z*cellsX + x (helper 0x603DD0) |
| Water | `[0xB43D94]+0x34` | u8 | slot 7; IsCellWatered = v & 1; view keys 1 watered terrain, 2 unwatered building, 3 watered building, 9 pipes (bit0 watered, bit1 building, bit3 pipe: LIKELY) |
| Plumbing (2nd grid) | `[0xB43D94]+0x30` | u8 | unknown |
| Mayor rating | `[0xB43D60]+0x40` | s8 | slot 12 |
| Transient aura | `[0xB43D60]+0x4C` | s8 | slot 13 |
| Park | `[0xB43D60]+0x58` | s16 | slot 14 |
| Landmark | `[0xB43D60]+0x68` | s16 | slot 15 |
| Traffic congestion | `[0xB43DA8]+0x48` | u8 | slot 10 |
| Traffic (others) | air-polluting +0x30, commercial traffic +0x38, trip length +0x44 | u8 | slots 8, 9, 13 |
| Traffic volume | hash table `[TS+0x17C]..[TS+0x180]` | - | no grid: GetTrafficEdgeDensity (slot 12, 0x711460), key (bool<<24)\|(travelType<<16)\|(x<<8)\|z, bucket = key mod count; node next +0, key +4, value +8 (layout unknown) |
| Residential proximity R$/R$$/R$$$ | `[0xB43DA4]+0x38/+0x3C/+0x40` | u8 | slot 5 |
| Residential population | `+0x48/+0x4C/+0x50` | u16 | |
| EQ / HQ | `+0x7C/+0x80/+0x84` / `+0x88/+0x8C/+0x90` | f32 | |
| Average age | `[0xB43DA4]+0x54` | u8 | slot 41 |
| School / hospital grade | `+0x70` / `+0x74` | f32 | slots 39 / 40 |

- **Lot on a cell**: `[0xB43D08]` (lot manager) +0x50 = `vector<vector<cISC4Lot*>>` [x][z]: `lot = [[[LM+0x50] + 12*x]
  + 4*z]`; cell counts [LM+0x24]/[LM+0x28] (GetLot(x,z,bool) = slot 6, 0x72B410; slots 5/6 swapped vs header).
- **Desirability**: building development `[0xB43D68]+0x5C` = STLport map<DeveloperType, cISC4GrowthDeveloper*> (header
  [+0x5C], root [hdr+4], node left +8 right +0xC key +0x10 value +0x14; find 0x497520, GetDeveloper slot 32 0x696C80).
  Keys 0x1010/0x1020/0x1030 R$-R$$$; 0x3110/0x3120/0x3130 CS; 0x3320/0x3330 CO$$/$$$; 0x4100 IR, 0x4200 ID, 0x4300 IM,
  0x4400 IHT. Growth developer (vtable 0xAB1488): +0x114 desirability s16 (slot 13), +0x118 population s16 (15),
  +0x11C capacity u16 (14), +0x120 max capacity u16 (16), +0x10C u8 ?, +0x110 s16 ?, +0x90 desirability base; tract
  size byte [gd+0x44] (debug text 0x4C9520).
- **Moisture**: `[0xB43DAC]+0xDC` bare `vector<vector<u8>>` (weather slot 18).
- **Average EQ / HQ**: no stored grid (slots 21/22 allocate per call): `round(sum pop_i*EQ_i / sum pop_i)` (0x6F70E0).
- **Terrain** (Mac order = Windows; gzcom-dll header misaligned): `T=[0xB43CF4]`: cells [T+0x28]/[T+0x2C]; vertices
  NX=[T+0x38], NZ=[T+0x3C], total [T+0x5C]; vertex array [T+0x6C], **stride 36, altitude f32 at +0**:
  `alt(vx,vz) = f32[[T+0x6C] + 36*(vz*NX + vx)]`; cell corners (x,z)..(x+1,z+1); **sea level f32 [T+0x7C]**.

**Q3. Data views** (map view 0x7A2F60): view type [mapview+0x144] -> 1 aura+0x40, 2 LV+0x28, 3 police+0x80, 4 crime,
5 fire+0x80, 6 flammability, 7 power, 8 air, 9 congestion, 10 water+0x34, 12 park, 24 water pollution, 25 garbage,
26 radiation, 27/28 average EQ/HQ, 29 moisture, 30 age, 76 traffic volume (per frame from edge densities), 64..75
desirability via GetDeveloper (sub-mode [mapview+0x148]: 2 supply, 3 desirability, 4 growth, 5 occupancy).
Renderers u8 0x7A2380, s8 0x7A2740, s16 0x7A2C70 (`byte = clamp(128 + v*128/EC)`), f32 0x7A2E00. Exemplars type 0x23
(group 0x690F693F, instances 0x4A0B68xx): 0x4A0B47E5 view type, 0x4A0B47E4 colour ramp, 0x4A0B47EC EC scale (air /
water pollution 1024, garbage 4096, desirability 100, LV 100), 0x4A0B47E9 coverage overlay (1 education, 2 health,
3 fire, 4 police, 7 power, 8 water), 0x4A0B47F2/F3/F4 legend colours / LTEXT ids / title, 0x4A0B47ED sub-mode,
0x6B7C5CDD traffic travel types. "Police" / "Fire" panels show crime / flammability with coverage overlays.

**Q4. Query**: the vanilla terrain query prints position and cell (0xA92820, cell = pos * 0.0625); building queries
use occupant properties; the Maxis debug query (0x4C9520) prints the desirability breakdown per tract.
SC4QueryUIHooks extends the terrain query with these getters.

**Q5. Water**: `SW=[0xB43CF0]`; [SW+0x14] terrain; depth array [SW+0x18] (same stride / index; depth f32 +0, velocity
+0x10). Water level = altitude + depth. GetWaterType 0x73D7F0: 0 if depth <= 0; 3 if altitude+depth <= sea level
(sea / salt, LIKELY), else 2 (fresh). GetWaterDepthForCell (slot 6) = max of the 4 corners. Body map [SW+0x4C] u16
(LIKELY a body id).

## 4. Live tests
1. `[[0xB43D9C]+0x50]+0x10 == 0x49B9E605`, `+0x18 == 2`; crime tract counts vs `[city+0x118] >> shift`.
2. Fire / police coverage u8 and the s16 at +0x84 before / after placing a station.
3. Power values 2 / 1 on powered / wired cells vs the Power data view.
4. Water values 1/2/3/9 vs the legend.
5. Mayor rating s8 range and colour mapping.
6. Altitude on a flat new tile vs sea level (expect 250); water type 3 in the sea, 2 in a raised lake.
7. Walk the DeveloperType map (12 keys); desirability at a cell vs the debug query.
8. Traffic volume node+8 before / after traffic.
