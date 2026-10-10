"""Per-cell data layers of the open city, read from memory (re/reports/datamaps/REPORT.md; verified in LIVE_FACTS).

Most layers are cSC4SimGrid<T> objects held by the simulators: the element type is the CLSID at +0x10, the tract
size (cells per value) is 1 << [+0x1C], the counts are at +0x20/+0x24, and the values are an STLport vector of
vectors (one row per tract x) at +0x38. Terrain altitude and water depth are vertex arrays (cells + 1 per side).
"""

from __future__ import annotations

import struct

from . import memory, win32

GRID_TYPES = {0x602: ("B", 1), 0x603: ("b", 1), 0x604: ("H", 2), 0x605: ("h", 2), 0x606: ("I", 4),
              0x607: ("i", 4), 0x608: ("Q", 8), 0x609: ("q", 8), 0x60A: ("f", 4), 0x60B: ("d", 8)}

# name -> (global holding the owner, offset of the grid pointer in the owner, what it means)
LAYERS = {
    "zones": (0xB43D14, 0x48, "zone type per cell: 0 none, 1-3 residential low/medium/high, 4-6 commercial "
                              "low/medium/high, 7 agriculture, 8-9 industrial medium/high, 10 military, 11 airport, "
                              "12 seaport, 13 spaceport, 14 landfill, 15 plopped building"),
    "land_value": (0xB43D88, 0x28, "land value 0-255"),
    "land_value_intrinsic": (0xB43D88, 0x24, "land value from the terrain alone"),
    "slope": (0xB43D88, 0x30, "terrain slope"),
    "crime": (0xB43D70, 0x5C, "crime 0-255"),
    "police_coverage": (0xB43D98, 0x80, "police coverage 0-255"),
    "fire_coverage": (0xB43D78, 0x80, "fire coverage 0-255"),
    "flammability": (0xB43D7C, 0x58, "flammability 0-255"),
    "air_pollution": (0xB43D9C, 0x50, "air pollution (the data view scales 1024 to full)"),
    "water_pollution": (0xB43D9C, 0x54, "water pollution (the data view scales 1024 to full)"),
    "garbage": (0xB43D9C, 0x58, "garbage (the data view scales 4096 to full)"),
    "radiation": (0xB43D9C, 0x4C, "radiation (non-zero = radioactive)"),
    "power": (0xB43DA0, 0x80, "0 no consumer, 1 wired but unpowered, 2 powered"),
    "water": (0xB43D94, 0x34, "bit 0 watered, bit 1 building, bit 3 pipe or water facility"),
    "mayor_rating": (0xB43D60, 0x40, "mayor rating (aura) per cell, signed"),
    "transient_aura": (0xB43D60, 0x4C, "short-lived aura effects, signed"),
    "park_effect": (0xB43D60, 0x58, "park effect"),
    "landmark_effect": (0xB43D60, 0x68, "landmark effect"),
    "traffic_congestion": (0xB43DA8, 0x48, "traffic congestion 0-255"),
    "traffic_air_pollution": (0xB43DA8, 0x30, "air pollution caused by traffic"),
    "commercial_traffic": (0xB43DA8, 0x38, "commercial traffic"),
    "trip_length": (0xB43DA8, 0x44, "commute trip length"),
    "residential_population_low": (0xB43DA4, 0x48, "R$ residents"),
    "residential_population_medium": (0xB43DA4, 0x4C, "R$$ residents"),
    "residential_population_high": (0xB43DA4, 0x50, "R$$$ residents"),
    "education_low": (0xB43DA4, 0x7C, "EQ of R$ residents"),
    "education_medium": (0xB43DA4, 0x80, "EQ of R$$ residents"),
    "education_high": (0xB43DA4, 0x84, "EQ of R$$$ residents"),
    "health_low": (0xB43DA4, 0x88, "HQ of R$ residents"),
    "health_medium": (0xB43DA4, 0x8C, "HQ of R$$ residents"),
    "health_high": (0xB43DA4, 0x90, "HQ of R$$$ residents"),
    "average_age": (0xB43DA4, 0x54, "average age of residents"),
    "school_grade": (0xB43DA4, 0x70, "school grade"),
    "hospital_grade": (0xB43DA4, 0x74, "hospital grade"),
}


class LayerError(RuntimeError):
    pass


def read_grid(p: win32.Process, g: int) -> dict:
    """{type, tract_size, nx, nz, rows}: rows[z][x] of tract values (x-major storage transposed)."""
    tclsid = p.u32(g + 0x10) & 0xFFF          # the CLSID 0x49B9E6xx; low 12 bits = element type
    if tclsid not in GRID_TYPES:
        raise LayerError("not a sim grid (type %#x)" % tclsid)
    fmt, size = GRID_TYPES[tclsid]
    shift, nx, nz = p.u32(g + 0x1C), p.u32(g + 0x20), p.u32(g + 0x24)
    begin, end = p.u32(g + 0x38), p.u32(g + 0x3C)
    if nx == 0 or nx > 4096 or nz > 4096 or (end - begin) // 12 != nx:
        raise LayerError("grid header unexpected (%d x %d)" % (nx, nz))
    rows_ptrs = struct.unpack("<%dI" % (3 * nx), p.read(begin, 12 * nx))[0::3]
    cols = [struct.unpack("<%d%s" % (nz, fmt), p.read(r, nz * size)) for r in rows_ptrs]
    rows = [[cols[x][z] for x in range(nx)] for z in range(nz)]
    if fmt in "fd":
        rows = [[round(v, 3) for v in row] for row in rows]
    return {"type": fmt, "tract_size": 1 << shift, "nx": nx, "nz": nz, "rows": rows}


def layer_grid(p: win32.Process, name: str) -> dict:
    if name not in LAYERS:
        raise LayerError("unknown layer %r" % name)
    glob, off, meaning = LAYERS[name]
    owner = p.u32(glob)
    if not owner or not memory.city_pointer(p):
        raise LayerError("no city is open")
    g = p.u32(owner + off)
    if not g:
        raise LayerError("layer %s not available" % name)
    out = read_grid(p, g)
    out["meaning"] = meaning
    return out


def terrain(p: win32.Process) -> dict:
    """Altitudes at cell corners (nz+1 rows of nx+1 values), the sea level, and water depth at the corners."""
    t = p.u32(memory.G_TERRAIN)
    if not t or not memory.city_pointer(p):
        raise LayerError("no city is open")
    nvx, nvz = p.u32(t + 0x38), p.u32(t + 0x3C)
    raw = p.read(p.u32(t + 0x6C), 36 * nvx * nvz)
    alt = [[round(struct.unpack_from("<f", raw, 36 * (z * nvx + x))[0], 2) for x in range(nvx)] for z in range(nvz)]
    out = {"vertices_x": nvx, "vertices_z": nvz, "sea_level": round(p.f32(t + 0x7C), 2), "altitude": alt}
    sw = p.u32(memory.G_SURFACE_WATER)
    if sw and p.u32(sw + 0x18):
        rawd = p.read(p.u32(sw + 0x18), 36 * nvx * nvz)
        out["water_depth"] = [[round(struct.unpack_from("<f", rawd, 36 * (z * nvx + x))[0], 2) for x in range(nvx)]
                              for z in range(nvz)]
    return out


def lot_at(p: win32.Process, x: int, z: int) -> int:
    """The cISC4Lot* on a cell (0 if none) from the lot manager's [x][z] table."""
    lm = p.u32(memory.G_LOT_MANAGER)
    if not lm:
        return 0
    nx, nz = p.u32(lm + 0x24), p.u32(lm + 0x28)
    if not (0 <= x < nx and 0 <= z < nz):
        raise LayerError("cell (%d, %d) is outside the city (%d x %d)" % (x, z, nx, nz))
    row = p.u32(p.u32(lm + 0x50) + 12 * x)
    return p.u32(row + 4 * z)
