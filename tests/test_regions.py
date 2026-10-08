"""Regions from files: config.bmp tiles, region.ini, and the region-view record of saved cities (synthetic data)."""
import os
import struct

from PIL import Image

from sc4_mcp import dbpf, regions


def _city_record(minor: int, name: str, mayor: str, tile=(3, 1), span=2, mode=1, pops=(100, 20, 5)) -> bytes:
    b = struct.pack("<HH7I", 1, minor, tile[0], tile[1], span, span, *pops) + struct.pack("<f", 0.5)
    if minor == 13:
        b += bytes([40, 2, 0]) + struct.pack("<I", 0x12345678) + bytes(20) + bytes([mode])
    else:
        b += bytes(0x3B - len(b) - 1 if minor == 9 else 0x3F - len(b) - 1) + bytes([mode])
    def lstr(t: str) -> bytes:
        return struct.pack("<I", len(t)) + t.encode()
    if minor == 13:     # name, -, mayor, -, utility advisor, description, - (as the game writes them)
        b += lstr(name) + lstr("") + lstr(mayor) + lstr("") + lstr("Jonas Sparks") + lstr("") + lstr("") + bytes(16)
    else:
        b += lstr(name) + bytes(8) + lstr(mayor) + bytes(16)
    return b


def test_region_folder(tmp_path):
    rd = tmp_path / "Regions" / "MCP Unit"
    rd.mkdir(parents=True)
    (rd / "region.ini").write_text("[Regional Settings]\nName = MCP Unit\nTerrain type = 0\nWater Min = 60\n"
                                   "Water Max = 100\n")
    im = Image.new("RGB", (6, 4))
    for x in range(4):
        for y in range(4):
            im.putpixel((x, y), (0, 0, 255))                  # one large tile
    for (x, y) in ((4, 0), (5, 0), (4, 1), (5, 1)):
        im.putpixel((x, y), (0, 255, 0))                      # one medium
    for (x, y) in ((4, 2), (5, 2), (4, 3), (5, 3)):
        im.putpixel((x, y), (255, 0, 0) if (x + y) % 2 else (255, 60, 60))  # four small
    im.save(rd / "config.bmp")
    dbpf.write_dbpf(str(rd / "City - Founded.sc4"),
                    [(regions.T_REGION_VIEW, regions.G_REGION_VIEW, 0, _city_record(13, "Founded", "Ada", (4, 0)))])
    dbpf.write_dbpf(str(rd / "City - New City.sc4"),
                    [(regions.T_REGION_VIEW, regions.G_REGION_VIEW, 0,
                      _city_record(9, "New City", "Mayor", (0, 0), 4, mode=0, pops=(0, 0, 0)))])
    rs = regions.list_regions(str(tmp_path))
    assert len(rs) == 1
    r = rs[0]
    assert r["name"] == "MCP Unit" and r["water_min"] == 60
    sizes = sorted(t["size"] for t in r["tiles"])
    assert sizes == ["large", "medium", "small", "small", "small", "small"]
    by = {(t["x"], t["y"]): t for t in r["tiles"]}
    assert by[(4, 0)]["city"] == "Founded" and by[(0, 0)]["city"] == "New City"
    c = {c["name"]: c for c in r["cities"]}
    assert c["Founded"]["established"] and c["Founded"]["mayor"] == "Ada"
    assert c["Founded"]["population"] == {"residential": 100, "commercial": 20, "industrial": 5}
    assert not c["New City"]["established"] and c["New City"]["size"] == "large"
