"""New bridges: the network INI's bridge lists (no game needed)."""
from sc4_mcp import bridgedesign as bd

INI = """[MiscNetworks]
x = 1

[RoadBridgeExemplars]

; 0x2821ED93
1 = 0x6534284a, 0xa82ca30f, 0x00000001, level road bridge

7 = 0x6534284a, 0xa82ca30f, 0x00000007, stone arch road bridge
;7b = disabled
;Custom


[AvenueBridgeExemplars]
1 = 0x6534284a, 0xa82ca30f, 0x60104F00, plain avenue bridge
"""


def test_section_lookup():
    assert bd.section_of(INI, 0x7) == "RoadBridgeExemplars"
    assert bd.section_of(INI, 0x60104F00) == "AvenueBridgeExemplars"
    assert bd.section_of(INI, 0x5C4D00) is None


def test_merge_appends_to_the_section():
    out = bd.merged_ini(INI, [{"section": "RoadBridgeExemplars", "instance": "0x005C4D00", "name": "MCP Arch"},
                              {"section": "AvenueBridgeExemplars", "instance": "0x605C4D00", "name": "MCP Ave"}])
    road = out[out.index("[RoadBridgeExemplars]"):out.index("[AvenueBridgeExemplars]")]
    assert "8 = 0x6534284a, 0xa82ca30f, 0x005C4D00, SiMCP MCP Arch" in road
    assert out.rstrip().endswith("2 = 0x6534284a, 0xa82ca30f, 0x605C4D00, SiMCP MCP Ave")
    assert bd.section_of(out, 0x005C4D00) == "RoadBridgeExemplars"
