"""Lot Editor parity: reading the game's lots and writing edited copies (needs the game's data files)."""
import pytest

from sc4_mcp import content, dbpf, gamedata, lotedit


@pytest.fixture
def designs(tmp_path, monkeypatch):
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    return tmp_path


def test_layout_reads_rows(designs):
    lay = lotedit.layout("0x4BAFBA9F")                  # the elevated light rail station
    assert lay["size_cells"] == [3, 1]
    nets = [r for r in lay["rows"] if r["type"] == "network"]
    assert len(nets) == 3 and all(r["network"] == "light_rail" and r["size_m"] == [16.0, 16.0] for r in nets)
    assert [r["name"] for r in lay["rows"] if r["type"] == "building"]


def test_edit_removes_moves_and_adds(designs, monkeypatch):
    from sc4_mcp import lotdesign
    monkeypatch.setattr(lotdesign, "_tree", lambda key: {"id": "0x16700000", "name": "Oak Tree"})
    before = lotedit.layout("0x6A636337")              # the gazebo
    gazebo = [r for r in before["rows"] if r.get("name") == "Gazebo"][0]
    out = lotedit.edit("MCP Test Grove", "0x6A636337", remove=[13, 14], move=[{"index": gazebo["index"], "x": 7, "z": 7}],
                       add=[{"tree": "Oak Tree", "x": 3, "z": 3}])
    after = lotedit.layout(out["lot"])
    assert len(after["rows"]) == len(before["rows"]) - 2 + 1
    moved = [r for r in after["rows"] if r.get("name") == "Gazebo"][0]
    assert (moved["x"], moved["z"]) == (7.0, 7.0) and moved["size_m"] == gazebo["size_m"]
    assert after["rows"][-1]["type"] == "tree" and after["rows"][-1]["id"] == "0x16700000"
    bld = [r for r in after["rows"] if r["type"] == "building"][0]
    assert bld["id"] == out["building"]
    with pytest.raises(lotedit.LotEditError):
        lotedit.edit("MCP Bad", "0x6A636337", remove=[bld["index"] + 100])
