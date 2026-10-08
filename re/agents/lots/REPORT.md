# RE report: lots (lots, buildings, occupants, lot configurations, menus, demand, zones) - SC4 1.1.641, static only

Scratch: `<workbench>\re\lots\`. "LM" = the cISC4LotManager pointer `[0xB43D08]` (= zone developer +4); offsets below
are relative to LM.

## 1. Answers

**Q1. Lot manager and cSC4Lot.**
- Lot manager vtable 0xAB37C0, 28 slots (CONFIRMED), gzcom-dll order except two overload pairs: slot 5
  `GetLot(cS3DVector3 const&)`, slot 6 `GetLot(x, z, bool exactOrigin)` (0x72B410); slot 8 `GetLotsSurroundingLot(x,
  z, list, flags)`, slot 9 the `(cISC4Lot const*, list, flags)` overload. Others: 7 GetLotsInCellRect, 13
  GetRandomLot, 14 GetOccupantLot(cISC4Occupant*), 15 GetSafeLotIterator, 16 GetLotCount (`[LM+0x64]`), 23 CreateLot
  0x72E520, 24 DeleteLot, 27 GetMaximumCapacityGrid (`[LM+0x70]`).
- Storage (CONFIRMED): cell grid `[LM+0x24]`/`[LM+0x28]` counts; `[LM+0x50]` vector of 12-byte rows by x, each row's
  first dword a `cISC4Lot*[z]` array: `lot(x,z) = [[ [LM+0x50] + 12*x ] + 4*z]` (0 = none; every cell of a lot points
  to it). Lot list: `[LM+0x5C]` = sentinel of an STLport list, node `{next, prev, cISC4Lot*}`; count `[LM+0x64]`.
- cSC4Lot (CONFIRMED): size 0x8C, ctor 0x6C1E50(x, z, w, h, facing), QI 0x6BF190 (cISC4Lot 0xE818FCED at +0). Vtables
  +0 0xAB19B0 (cISC4Lot), +4 0xAB1994, +8 0xAB1930 (property holder), +0x1C 0xAB1914 (traffic source).
- cISC4Lot vtable 0xAB19B0, 70 slots, header order except 50/51 swapped: 9 GetLotConfiguration `[+0x34]`; 12 GetFlags
  (byte +0x79); 14 GetBoundingRect (bytes +0x20..+0x23); 21 GetLocation (+0x7A/+0x7B); 22 GetSize (+0x7C/+0x7D); 23
  GetFacing (+0x7E); 25 GetUnit `[+0x4C]`; 31 GetZoneType (+0x81); 33 GetState (+0x7F); 35 GetCondition (+0x80); 41
  GetOccupantWealth (+0x82); 43 IsHistorical (flag 0x20); 45 GetVacateReason (+0x83); 46 GetBuildingType(bool force)
  `[+0x3C]` (falls back to lot configuration slot 3); 48 GetBuilding; 49 GetLotOccupants; **50 GetCapacity(DeveloperType,
  bool force)**, **51 GetCapacity(WealthType)**; 52 GetAvailableCapacity; 53 GetPopulation(DeveloperType); 54
  GetPopulations (this+0x54); 61 GetOccupancy; 64 GetJobs(float[4]); 65 GetNeedsPower (flag 0x08); 66 GetHasPower (flag
  0x10); 68 GetVerticesAreLocked (flag 0x40).
- Lot states: 0 Created, 1 Ready, 2 Constructing, 3 Occupied, 4 Vacant ("abandoned", LIKELY), 5 Destructing, 6
  Destroyed. No water bit on the lot (flag bits 0x02 / 0x04 / 0x80 unknown): water from the plumbing simulator.
- Capacity per wealth: slot 51 maps the building profile's purpose to a developer type (BuildingDevelopmentSim slot
  30 GetDeveloperType(purpose, wealth)) then slot 50. Population: vector at +0x54 of 12-byte STLport maps keyed by
  developer type (key +0x10, u16 value +0x14). GetJobs: jobs[1..3] = population x DemandSim slot 8
  CalculateJobsPerUnitOfDemand(devType+1).

**Q2. Building occupant** (CONFIRMED): cSC4BuildingOccupant (ctor ~0x458E90). Vtables +0 **0xA872C0**
(cISC4BuildingOccupant, 20 slots; QI answers 0x87DDA3A9, else +4), **+4 0xA87238** (cISC4Occupant, 34 slots), +8
0xA8721C, +0xC property holder 0xA871B8, +0x20 0xA871A0. Slots: 3 AsOccupant (+4), 4 GetBuildingType `[+0x38]`, 12
GetBuildingName and 13 GetExemplarName (via BuildingDevelopmentSim slots 38/37; cIGZString*), 14 GetOrientation (byte
+0x54), 9 GetCompletionPercent (+0x58), 19 GetName (property 0x899AFBAD "Item Name").
- **Building type = the building exemplar's instance id** (casino 0x033A0000 = exemplar `RW64x64_Casino_033A`).
- **Occupant type** = cISC4Occupant slot 7 `[occ+0x24]` (building object +0x28): building **0x278128A0**, flora
  **0x74758926**, prop **0xA823821E**; also 0x69D25C5F, 0x6A11BD2B, 0xABF98CB4 (toxic), 0x68FD0C69, 0x895D1169,
  0x0990B2EA (not named).
- Lot -> building: lot slot 48 GetBuilding (0x6BFA30: OccupantManager slot 35, first occupant of type 0x278128A0 in
  the lot rect, QI; non-owning). Building -> lot: LM slot 14 GetOccupantLot(building+4).
- Power / water per building: lot slot 66; PlumbingSim `[0xB43D94]` (vtable 0xAB2228) slot 9
  IsBuildingWatered(cISC4Occupant*) (LIKELY), slot 11 IsCellWatered(x, z).

**Q3. Occupant manager** `[0xB43D0C]`, vtable 0xA8F7F0, 49 slots (CONFIRMED): 0..27 header order; for the overload
pairs 28/29 .. 44/45 the even slot takes a cISC4OccupantFilter* and the odd slot a uint32 type (stores it into the
default filter `[OM+0x34]+0xC` and tail-jumps; type 0 = all); 46/47 the other way round (46 type, 47 filter).
IterateOccupantsByBBox (43 type, 42 filter): `(bool cdecl cb(cISC4Occupant*, void*), data, cS3DVector3 const* min,
cS3DVector3 const* max, type)`, coordinates in metres (cell x 16, y ignored). Per occupant: slot 7 GetType, 10
GetBoundingBox, 8 GetPosition.

**Q4. Lot configurations and the placeable catalogue**
- Lot configuration manager `[0xB43D18]`, vtable 0xA8EC58 (CONFIRMED): 8 GetLotConfiguration(IID) = hash lookup in the
  global hash_map **0xB216C8** (buckets `[0xB216CC]`..`[0xB216D0]`, node `{next, IID +4, cISC4LotConfiguration* +8}`,
  bucket = IID % n; count LIKELY `[0xB216D8]`); 20 GetLotConfigurationMap returns 0xB216C8; slot 6 takes (config*,
  bool) (AddLotConfiguration overloads swapped).
- cSC4LotConfiguration, vtable 0xA8CEB8, 33 slots, ctor 0x4797A0, size 0xC0 (CONFIRMED): +8 IID; +0xC name (cRZString;
  char* at +0x10); +0x20/+0x21 size x/z; +0x24 family vector; +0x3C growth stage; +0x3E/+0x40 min/max capacity (u16);
  +0x44 zone-type list, +0x58 wealth list, +0x6C purpose list; +0x90 vector of 0x34-byte lot objects (type byte +0;
  type 0 building: building IIDs / families in a vector at +0x28). Slot 24 = the primary building object.
- **Menu population** (CONFIRMED): city view menu builder 0x7F06B0 -> 0x7EFF40: (1) every building type from
  BuildingDevelopmentSim `[0xB43D68]` slot 12 (count) / slot 11 (vector); (2) skips growables (BuildingProfile slot 39
  flags `[+0x1C] & 7`); (3) keeps exemplars whose OccupantGroups (0xAA1DD396) contain an include-set group and no
  exclude-set group; (4) requires a Lot Resource Key (0xEA260589) that LotConfigMgr slot 8 resolves; (5) reads name
  (0x8A416A99 LTEXT / 0x899AFBAD / 0x20), description (0xCA416AB5 / 0x8A2602A9), plop cost (0x49CAC341), icon
  (0x8A2602B8), order (0x8A2602B9); (6) **availability**: City Exclusion Group (0xEA2E078B) set and CivicBuildingSim
  `[0xB43DB4]` (vtable 0xAB0C7C) slot 5 IsBuildingExcluded(group) -> greyed; **Conditional Building (0xEA3209F8)** true
  -> status = slot 6 GetConditionalBuildingStatus(buildingIID): enabled only if `status && (status->status & 2)`, not
  listed if `status & 1`; menu byte `[this+0x446]` forces all enabled and shown (GUESS: debug / cheat); ferry terminals
  (0x0BD86FD3) greyed when TrafficSim slot 32 (ferry type) >= 16.
- Menu groups (table 0xABC010..0xABC058, LIKELY): 0x1006 park, 0x1300 / 0x130A transport / ferry, 0x1400 power, 0x1401
  water, 0x1402 garbage, 0x1500 police, 0x1501 jail, 0x1502 fire, 0x1503..0x1506 education, 0x1507 health, 0x1508
  airport, 0x150A landmark, 0x150B reward, 0x1519 (unknown). Button handlers 0x7F39D0 (utilities), 0x7F3Cxx
  (transport), 0x7F4780..0x7F4EA0 (police, park, fire, health, landmark, education).
- **Honest play**: the plop control (0x4C09CC) does **not** check the conditional status (it only caps plops per
  activation for conditional / exclusion buildings); PlaceLot with a locked reward plops it (cheat-class) unless the
  bridge applies the menu checks.

**Q5. Demand** (CONFIRMED): DemandSim `[0xB43D74]`, vtable 0xAB0E48, header order. Slot 6 GetDemand(id, index) = STLport
map at **DS+0x50** keyed by `id + index` (node key +0x10, cISC4Demand* +0x14); keys are the instance ids of the 173
demand exemplars (group 0xC7BB4816, type 3); index 0 local, 0x10000 regional, 0x20000 **total**. Ids: R$/$$/$$$
0x1010/0x1020/0x1030; Cs 0x3110/0x3120/0x3130; Co 0x3320/0x3330; I-R/D/M/HT 0x4100/0x4200/0x4300/0x4400. **Census =
id+1**; jobs $..$$$ 0x2010..0x2030; workforce 0x2110..; caps Co$$ 0x3B20, Co$$$ 0x3B30, I-R..I-HT 0x4900..0x4C00;
connections 0x3800, 0x4800. The demand graph (0x6A7600, monthly) stores `GetDemand(id, 0x20000)->QueryActiveDemandValue()`
into HistoryWarehouse slot 12 under 0x2A67A399, 0xAA67A3A0, 0x8A67A3A4, 0x0A67A3A9, 0xAA67A3AD, 0xCA67A3B2, 0xAA67A3B7,
0x2A67A3BC, 0xEA67A3BF, 0x0A67A3C4, 0xEA67A3C8, 0x8A67A3CC (R$..I-HT); graph scale +-6000. The UI meter posts
kSC4MessageActiveDemandChanged 0x426840A0 with `active/max x 1000` (or `active/min x -1000`). Cap (slot 35, 0x5D4E60):
`raw = demand - supply` clamped to [min, max], tax / economy modifiers, limited to `max x (1 - cap)` (cap float +0x44,
slot 26). Census: GetLocalPopulationSummary (slot 11): QuerySupplyValue when GetRegionUse()==1, QueryDemandValue when
==2. Total residents `[[0xB43DA4]+0xA4]` (Residential slot 16).

**Q6. Zones** (CONFIRMED): zone type (lot +0x81, zone grid) 0 none; 1-3 R low/med/high; 4-6 C; 7 agriculture; 8-9 I
med/high; 10 military; 11 airport; 12 seaport; 13 spaceport; 14 landfill; 15 plopped. Wealth 0-3 (none, $, $$, $$$).
Purpose 1 residence, 2 services, 3 office, 4 tourism, 5 agriculture, 6 processing, 7 manufacturing, 8 high-tech.
ZoneManager `[0xB43D14]`, vtable 0xA92E00: slot 5 GetZoneGrid `[ZM+0x48]`; 6 counts `[ZM+0x4C+4t]`; 7
GetUndevelopedTileCount(type) `[ZM+0x8C+4t]`, 8 the no-argument version `[ZM+0x10C]` (swapped); 10 abandoned tiles
`[ZM+0x114]`; 12 GetZoneType(x, z).

## 2. Layouts
- **cSC4Lot**: +0xC refcount; +0x20..+0x23 u8 minX, minZ, maxX, maxZ (inclusive); +0x24 altitude float; +0x28 slope;
  +0x34 configuration*; +0x38 last state-change date; +0x3C building type (IID); +0x40 map; +0x4C business unit;
  +0x50 travel designate; +0x54 population vector<map>; +0x60 travel map; +0x78 initialised; +0x79 flags; +0x7A/+0x7B
  location; +0x7C/+0x7D size; +0x7E facing 0..3; +0x7F state; +0x80 condition; +0x81 zone; +0x82 wealth; +0x83
  vacate reason; +0x84 list.
- **cSC4BuildingOccupant**: +0x28 type; +0x38 building IID; +0x3C..+0x50 bounding box; +0x54 orientation; +0x55 lit;
  +0x58 completion.
- **BuildingProfile**: +0 purpose; +4 wealth; +8 u16 current capacity; +0xC vector of 12-byte {devType, ...}
  capacities; +0x1C category flags.
- **cSC4Demand** (vtable 0xAA2758, 34 slots): +0x10 id; +0x14 supply; +0x18 demand; +0x1C newSupply; +0x20 newDemand;
  +0x2C max; +0x30 min; **+0x34 active**; +0x3C economy; +0x40 tax; **+0x44 cap**; +0x48 region use.
- **ConditionalBuildingStatus**: CivicBuildingSim hash_map at +0x2C (buckets `[+0x30]`, `[+0x34]`); node {next, IID +4,
  status +8}; status u8 +0, u16 count +2, cRZString tooltip +4.

## 3. Recipes (main thread; read-only unless stated)
1. **lots()** (app state 2): walk `[LM+0x5C]` or call lot slots per lot (14 rect, 23 facing, 31 zone, 41 wealth, 33
   state, 43 historical, 66 power, 9 -> configuration slots 3/4/7, 46(true) building IID, 48 building; per developer
   type 51/50 capacity, 53 population; water PlumbingSim slot 9 on building+4). From Python read the same fields; names
   from the exemplar inventory by IID (plugins: BuildingDevelopmentSim slot 38 via the bridge).
2. **building_info(x, z)**: LM slot 6 (x, z, false), then as 1.
3. **demand()**: per id `DS->vtbl[6](id, 0x20000)`, then slot 12 (active), 26 (cap), 14/15 (max/min), 8/9 (supply /
   demand); census id+1 with slot 8 or 9 per slot 28.
4. **Catalogue**: GetLotConfigurationMap or BuildingDevelopmentSim slots 12/11 plus the exemplar properties; apply the
   Q4 menu rules and gate PlaceLot on CivicBuildingSim slots 5/6 (honest play).
5. **zone_summary()**: ZoneManager slots 6/7/8/10, or the zone grid.

## 4. Live tests
1. `[[0xB43D08]+0x64]` = nodes in the +0x5C list; `[[lot]] == 0xAB19B0`; plop a park: count +1, grid cells point to it.
2. Known building: `[lot+0x3C]` == building slot 4 == exemplar IID; BuildingDevelopmentSim slot 38 name = query window.
3. Abandoned `[lot+0x7F] == 4`; under construction 2; historical `[+0x79] & 0x20`.
4. `GetDemand(0x1010, 0x20000)` slot 12 vs the demand graph; cap +0x44 vs Co$$ near the cap.
5. R$ census (0x21011) vs the census window; `[[0xB43DA4]+0xA4]` vs the city population.
6. Locked reward (casino 0x033A0000): status null or no bit 2; after unlocking bit 2; vs the Rewards menu.
7. Zone grid value vs GetZoneType(x, z) (slot 12); tract shift 0.
8. PlumbingSim slot 9 on watered / unwatered buildings vs the query window.
