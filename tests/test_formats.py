"""Offline tests for the file formats (no game needed; game files are only used when installed)."""
import os
import random
import struct

import pytest

from sc4_mcp import dbpf, identity


def test_qfs_round_trip():
    rnd = random.Random(4)
    samples = [b"", b"a", b"abc" * 1000, bytes(rnd.getrandbits(8) for _ in range(5000)),
               b"".join(struct.pack("<I", rnd.randrange(16)) for _ in range(20000))]
    for s in samples:
        c = dbpf.qfs_compress(s)
        assert c[:2] == b"\x10\xfb"
        assert dbpf.qfs_decompress(c) == s


def test_dbpf_write_read(tmp_path):
    ex = dbpf.build_exemplar([
        dbpf.Property(0x10, dbpf.PT_UINT32, [0x10]),
        dbpf.Property(0x20, dbpf.PT_STRING, "MCP test lot", True),
        dbpf.Property(0x88EDC790, dbpf.PT_UINT32, [1, 2, 3, 4], True),
        dbpf.Property(0x27812810, dbpf.PT_FLOAT32, [0.5], False),
        dbpf.Property(0x4A4A88F0, dbpf.PT_BOOL, [True], False),
    ], parent=(0x05342861, 0x8A3B9F0F, 0x1))
    lt = dbpf.build_ltext("Hello, Sims")
    recs = [(dbpf.T_EXEMPLAR, 0xA8FBD372, 0x12345678, ex), (dbpf.T_LTEXT, 0x6A231EAA, 0x1, lt),
            (0x856DDBAC, 0x46A006B0, 0x2, bytes(range(256)) * 4)]
    p = tmp_path / "mcp_test.dat"
    dbpf.write_dbpf(str(p), recs)
    d = dbpf.DBPF(str(p))
    assert d.header.major == 1 and d.header.index_major == 7
    assert len([e for e in d if e.type != dbpf.T_DIR]) == 3
    for t, g, i, data in recs:
        assert d.read(d.get(t, g, i)) == data
    x = dbpf.parse_exemplar(d.read(d.get(dbpf.T_EXEMPLAR, 0xA8FBD372, 0x12345678)))
    assert x.kind == "exemplar" and x.parent == (0x05342861, 0x8A3B9F0F, 0x1)
    assert x.get(0x10) == 0x10 and x.get(0x20) == "MCP test lot"
    assert x.get(0x88EDC790) == [1, 2, 3, 4] and x.get(0x4A4A88F0) is True
    assert abs(x.get(0x27812810) - 0.5) < 1e-6
    assert dbpf.parse_ltext(d.read(d.get(dbpf.T_LTEXT, 0x6A231EAA, 0x1))) == "Hello, Sims"


def _fake_pe(stamp=identity.TIME_DATE_STAMP, laa=False):
    d = bytearray(identity.FILE_SIZE)
    d[:2] = b"MZ"
    pe = 0x140
    struct.pack_into("<I", d, 0x3C, pe)
    d[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHI", d, pe + 4, 0x14C, 7, stamp)
    struct.pack_into("<H", d, pe + 22, 0x10F | (0x20 if laa else 0))
    struct.pack_into("<H", d, pe + 24, 0x10B)
    struct.pack_into("<I", d, pe + 24 + 28, identity.IMAGE_BASE)
    struct.pack_into("<I", d, pe + 24 + 56, identity.SIZE_OF_IMAGE)
    return bytes(d)


def test_identity_refuses_other_builds(tmp_path):
    p = tmp_path / "SimCity 4.exe"
    p.write_bytes(_fake_pe(stamp=0x3F000000))
    r = identity.check_exe(str(p))
    assert not r["ok"] and "unsupported build" in r["reason"]
    p.write_bytes(_fake_pe())           # right header, wrong code bytes
    r = identity.check_exe(str(p))
    assert not r["ok"] and "differs" in r["reason"]


@pytest.mark.skipif(not os.path.exists(identity.exe_path()), reason="SimCity 4 not installed")
def test_identity_installed_game():
    r = identity.check_exe()
    assert r["ok"], r
