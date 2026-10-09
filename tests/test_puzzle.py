"""Puzzle pieces: names from RUL0 text (no game needed)."""
from sc4_mcp import puzzle

RUL0 = """[Ordering]
RotationRing = 1020, 1021

;### next file: 1020_Clovers.txt ###
;### last modified: Aug 08 09:23:13 UTC 2026 ###

;Added by Tarkus 1/26/2010.
;Real Highway Cloverleaf
[HighwayIntersectionInfo_0x00001020]
Piece       = 0.0, 0.0, 0, 0, 0x02011000
;CellLayout =..ab..
CellLayout =..ab..
Costs       = 3000 ; dollars
[HighwayIntersectionInfo_0x00001021]
CopyFrom    = 0x1020
Rotate		= 1

;### next file: 7C00_SingleTileRoundabouts.txt ###
;Road x Road Single Tile Roundabout
[HighwayIntersectionInfo_0x00007C11]
Costs = 30
[HighwayIntersectionInfo_0x00007C12]
CopyFrom = 0x7C11
Transpose = 1
"""


def test_names_groups_and_copies():
    n = puzzle.parse_names(RUL0)
    assert n[0x1020] == {"name": "Real Highway Cloverleaf", "group": "Clovers", "cost": 3000}
    assert n[0x1021]["name"] == "Real Highway Cloverleaf" and n[0x1021]["rotate"] == 1
    assert n[0x7C11]["group"] == "SingleTileRoundabouts" and n[0x7C11]["cost"] == 30
    assert n[0x7C12]["name"] == "Road x Road Single Tile Roundabout" and n[0x7C12]["transpose"] == 1


def test_load_order_files_before_folders(monkeypatch, tmp_path):
    monkeypatch.setattr(puzzle.launch, "USER_DIR", str(tmp_path))
    a = str(tmp_path / "Plugins" / "zzz.dat")
    b = str(tmp_path / "Plugins" / "770-nam" / "Controller.dat")
    c = str(tmp_path / "Plugins" / "aaa" / "x.dat")
    order = sorted([b, a, c], key=puzzle._load_order_key)
    assert order == [a, b, c]                       # root files first, then folders alphabetically
