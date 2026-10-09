"""Region layouts and height maps (no game needed)."""
import os

import pytest

from sc4_mcp import heightmap, regions


@pytest.fixture
def region(tmp_path, monkeypatch):
    monkeypatch.setattr(heightmap.launch, "USER_DIR", str(tmp_path))
    monkeypatch.setattr(heightmap, "HOME", str(tmp_path / "heightmaps"))
    folder = tmp_path / "Regions" / "Test"
    folder.mkdir(parents=True)
    (folder / "region.ini").write_text("[Regional Settings]\nName = Test\nTerrain type = 0\n")
    return "Test"


def test_layout_and_bitmap(region):
    out = heightmap.write_layout(region, 2, 2, "small")
    assert out["cities"] == 4 and out["heightmap_size"] == [129, 129]
    grid = regions.read_config_bmp(os.path.join(heightmap.region_folder(region), "config.bmp"))
    assert (grid["width"], grid["height"]) == (2, 2) and len(grid["tiles"]) == 4
    bmp, info = heightmap.make_bitmap(region, heights=[[210, 300], [450, 600]])
    from PIL import Image
    im = Image.open(bmp)
    assert im.size == (129, 129) and im.mode in ("L", "P")          # 8 bits: the only kind the game takes
    assert info["lowest_m"] == 210 and info["highest_m"] == 600


def test_layout_rules(region):
    with pytest.raises(heightmap.HeightmapError):
        heightmap.write_layout(region, 3, 2, "medium")               # medium tiles need even sizes
    assert heightmap.write_layout(region, 4, 4, "large")["cities"] == 1
    with pytest.raises(heightmap.HeightmapError):
        heightmap.make_bitmap(region, heights=[[1, 2, 3], [4, 5]])  # not a rectangle
    with pytest.raises(heightmap.HeightmapError):
        heightmap.region_folder("Nope")
