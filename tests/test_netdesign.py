"""New puzzle pieces: turning tiles and paths, the RUL0 text and the merge (no game needed)."""
import re

from sc4_mcp import netdesign as nd, puzzle

PATH = ("SC4PATHS\r\n1.1\r\n1\r\n1\r\n0\r\n-- Car_3_1\r\n1\r\n0\r\n3\r\n1\r\n2\r\n2.5,-8.0,0.0\r\n2.5,8.0,0.0\r\n"
        "-- stop_car_3_255\r\n1\r\n1\r\n0\r\n3\r\n255\r\n2.5,-7.4,0.0\r\n")


def _lines(t):
    return t.replace("\r", "").strip().split("\n")


def test_turning_paths_and_sides():
    one = _lines(nd.turn_path(PATH, 1, 0))
    assert one[5:12] == ["-- Car_3_1", "1", "0", "0", "2", "2", "-8,-2.5,0"]   # south-north becomes west-east
    assert one[-2:] == ["255", "-7.4,-2.5,0"]                                 # the stop path turns too
    t = PATH
    for _ in range(4):
        t = nd.turn_path(t, 1, 0)
    assert [ln.replace(".0", "") for ln in _lines(t)] == [ln.replace(".0", "") for ln in _lines(PATH)]
    assert nd.turn_side(0, 1, 0) == 1 and nd.turn_side(3, 1, 0) == 0 and nd.turn_side(255, 2, 0) == 255
    assert nd.turn_side(0, 0, 1) == 2 and nd.turn_point(1.0, 2.0, 1, 0) == (2.0, -1.0)


def test_tile_ids_and_stubs():
    assert nd.tile_id(0x5C400000, 1, 0) == 0x5C400100 and nd.tile_id(0x5C400000, 2, 3) == 0x5C400230
    cells = {(0, 0): {"networks": [(0, 0x00020002)]}, (1, 0): {"networks": [(0, 0x02020002)]},
             (2, 0): {"networks": [(0, 0x00000002)]}, (1, 1): {"networks": [(0, 0x02000200)]}}
    assert nd.stub_cells(cells, 0, 0, 2, 1) == {(0, 0), (1, 1)}      # (2, 0) is a dead end inside


def test_rul0_section_and_merge():
    cells = {(5, 5): {"networks": [(0, 0x00020002)]}, (6, 5): {"networks": [(0, 0x02020002), (3, 0x00000200)]},
             (6, 6): {"networks": [(0, 0x02000200)]}}
    text, letters = nd.rul0_section(0x5C4D0000, "MCP T", cells, 5, 5, 2, 2, 0x5C400000, 30, stubs={(5, 5)})
    assert "CellLayout = ab<" in text and "CellLayout = .c." in text and "CellLayout = ^.." in text
    assert "CheckType = a - road: 0x00020002,0xFFFFFFFF check" in text
    assert "CheckType = b - road: 0x02020002 street: 0x00000200" in text
    assert "AutoTileBase = 0x5C400000" in text and "Piece = 0.0, 0.0, 0, 0, 0x5C400000" in text
    assert text.count("CopyFrom = 0x5C4D0000") == 3
    names = puzzle.parse_names(text)
    assert names[0x5C4D0000]["name"] == "MCP T" and names[0x5C4D0000]["group"] == "SiMCP"
    assert names[0x5C4D0003]["rotate"] == 3
    base = "[Ordering]\nRotationRing = 1020, 1021\n\n[HighwayIntersectionInfo_0x00001020]\nCosts = 3000\n"
    merged = nd.merged_text(base, [{"name": "MCP T", "ring": [0x5C4D0000, 0x5C4D0001], "rul0": text}])
    assert re.search(r"\[Ordering\]\nRotationRing = 5C4D0000, 5C4D0001\t;SiMCP MCP T\nRotationRing = 1020", merged)
    assert merged.index("[HighwayIntersectionInfo_0x00001020]") < merged.index("[HighwayIntersectionInfo_0x5C4D0000]")
