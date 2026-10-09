"""My Sim faces of one's own (no game needed): MySims.dat and the 36 x 36 pictures."""
import os
import struct

import pytest
from PIL import Image

from sc4_mcp import mysim


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(mysim.launch, "USER_DIR", str(tmp_path / "UserDir"))
    monkeypatch.setattr(mysim.launch, "ROOT", str(tmp_path))
    (tmp_path / "UserDir").mkdir()
    return tmp_path


def test_dat_layout_matches_the_games_reader(tmp_path):
    path = str(tmp_path / "MySims.dat")
    mysim.write_dat(path, [{"name": "Ann", "gender": "female", "sign": "leo", "image": "Ann.bmp"}])
    data = open(path, "rb").read()
    assert struct.unpack_from("<I", data)[0] == 0x4A32E4AA
    assert data[4:] == b"\x03Ann" + bytes([0, 7, 3]) + b"Ann"              # name, male, sign, image without .bmp
    assert mysim.read_dat(path) == [{"name": "Ann", "gender": "female", "sign": "leo", "image": "Ann.bmp"}]


def test_design_face_adds_to_the_dialog_list(user):
    out = mysim.design_face("MCP Kim", "male", "virgo", hair=(10, 10, 10))
    pic = Image.open(out["image"])
    assert pic.size == (36, 36) and pic.mode == "RGB" and out["image"].endswith("MCP Kim.bmp")
    every = mysim.faces()
    assert len(every) == len(mysim.FACES) + 1 and every[-1]["preset_name"] == "MCP Kim"
    assert every[-1]["face"] == out["face"] == len(mysim.FACES)
    mysim.design_face("MCP Kim", "female", "leo")                         # same name: replaced, not added
    assert [(f["name"], f["gender"]) for f in mysim.custom_faces()] == [("MCP Kim", "female")]


def test_design_face_from_a_picture(user):
    src = user / "photo.png"
    Image.new("RGB", (120, 80), (200, 30, 30)).save(src)
    out = mysim.design_face("MCP Photo", "female", "aries", image_path=str(src))
    assert Image.open(out["image"]).getpixel((18, 18)) == (200, 30, 30)


def test_design_face_checks(user):
    with pytest.raises(mysim.MySimError):
        mysim.design_face("Bella Goth")                                   # one of the game's faces
    with pytest.raises(mysim.MySimError):
        mysim.design_face("x" * 32)
    with pytest.raises(mysim.MySimError):
        mysim.design_face("MCP A", sign="ophiuchus")


def test_remove_face_moves_the_picture_aside(user):
    out = mysim.design_face("MCP Gone", "male", "leo")
    res = mysim.remove_face("MCP Gone")
    assert not os.path.exists(out["image"]) and os.path.isfile(res["picture_moved_to"])
    assert res["picture_moved_to"].startswith(str(user / "backups"))
    assert mysim.custom_faces() == []
    with pytest.raises(mysim.MySimError):
        mysim.remove_face("MCP Gone")
