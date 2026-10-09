"""Terrain looks: the DXT1 writer, the texture table and the plugin (the plugin test needs the game's data)."""
import struct

import numpy as np
import pytest

from sc4_mcp import content, dbpf, fsh, gamedata, terrainlook as tl


def test_dxt1_round_trip():
    rng = np.random.default_rng(1)
    base = np.linspace(40, 200, 64 * 64 * 3).reshape(64, 64, 3)
    img = np.clip(base + rng.normal(0, 6, base.shape), 0, 255).astype(np.uint8)
    out = tl.write_fsh([img, img[::-1].copy()])
    assert out[:4] == b"SHPI" and struct.unpack_from("<II", out, 4) == (len(out), 2) and out[12:16] == b"G264"
    first, = struct.unpack_from("<I", out, 20)
    assert first % 16 == 0
    back = tl.read_entries(out)
    assert len(back) == 2 and back[0].shape == (64, 64, 3)
    mse = ((back[0].astype(float) - img) ** 2).mean()
    assert 10 * np.log10(255 ** 2 / mse) > 30
    flat = np.full((8, 8, 3), 120, np.uint8)                           # one colour: endpoints equal, still exact
    w, h, px = fsh.read_first(tl.write_fsh([flat]))
    assert (w, h) == (8, 8) and np.abs(np.frombuffer(px, np.uint8).reshape(8, 8, 4)[..., :3].astype(int) - 120).max() <= 4


INI = """[Admin]
Enabled=ON

[TropicalTextureMapTable]
; comment
00=0x32,0x33,0x36,0x31,0x39,
01=0x34,0x35,0x37,0x38,0x43,

[MiscTerrainTunables]
RaiseLowerAmount=80.5
"""


def test_table_shift_and_rewrite():
    rows = tl.table(INI)
    assert rows == [[0x32, 0x33, 0x36, 0x31, 0x39], [0x34, 0x35, 0x37, 0x38, 0x43]]
    wetter = tl.shifted(rows, 2)
    assert wetter == [[0x36, 0x37, 0x38, 0x31, 0x39], [0x31, 0x31, 0x35, 0x34, 0x43]]   # beach / cliffs stay
    assert tl.shifted(rows, -9)[0][:4] == [0x32] * 4
    ini = tl.ini_with_table(INI, wetter)
    assert tl.table(ini) == wetter and "RaiseLowerAmount=80.5" in ini and "[Admin]" in ini


def test_recolour_and_settings():
    img = np.full((8, 8, 3), (60, 90, 30), np.uint8)
    assert tl.recolour(img).tolist() == img.tolist()
    snowy = tl.recolour(img, snow=1.0).reshape(-1, 3).mean(0)
    assert snowy.min() > 180 and snowy[2] >= snowy[0]
    fall = tl.recolour(img, autumn=1.0).reshape(-1, 3).mean(0)
    assert fall[0] > fall[1] > fall[2]                                  # green turned orange-brown
    tinted = tl.recolour(img, tint_rgb=(200, 160, 100), tint_strength=1.0).reshape(-1, 3).mean(0)
    assert np.abs(tinted - (200, 160, 100)).max() < 3
    assert tl._settings("arid")["moisture_shift"] < 0
    for bad in ({"moisture_shift": 9}, {"snow": 2}, {"tint_rgb": [1, 2]}):
        with pytest.raises(tl.TerrainLookError):
            tl._settings("custom", **bad)
    with pytest.raises(tl.TerrainLookError):
        tl._settings("purple")


def test_look_plugin(tmp_path, monkeypatch):
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path / "plugins"))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    monkeypatch.setattr(content, "DISABLED", str(tmp_path / "disabled"))
    d = tl.design("arid")
    p = dbpf.DBPF(d["file"])
    tex = [e for e in p if e.type == dbpf.T_FSH]
    assert all(e.group == tl.G_TERRAIN_TEX and not e.compressed for e in tex)     # the game reads them raw
    assert {e.instance & 0xFF for e in tex} == set(tl.TEXTURES) and len(tex) == len(tl.TEXTURES) * tl.ZOOMS
    ini = p.read(p.get(*tl.INI_TGI)).decode("latin-1")
    assert tl.table(ini) == tl.shifted(tl.table(tl.game_ini()), -3)
    assert tl.current()["look"] == "arid" and d["png"][:4] == b"\x89PNG"
    snow = tl.design("arctic")
    p = dbpf.DBPF(snow["file"])
    assert p.get(*tl.INI_TGI) is None                                   # no shift: the game's table
    assert [x["look"] for x in content._manifest() if not x.get("disabled")] == ["arctic"]
    assert tl.design("default")["was"] == "arctic" and not tl.current()["active"]
