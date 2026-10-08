"""The one game build SiMCP 4 supports, and the check that refuses any other.

Every address in notes/ and re/ is for this build: SimCity 4 Deluxe Edition 1.1.641 (the GOG digital release),
`Apps\\SimCity 4.exe` at its preferred base 0x400000. The 4GB patch only sets the LARGE_ADDRESS_AWARE header bit
and rewrites the PE checksum, so code addresses are the same with or without it; both variants are accepted.
"""

from __future__ import annotations

import hashlib
import os
import struct

DEFAULT_GAME_DIR = r"C:\Program Files\GOG Galaxy\Games\SimCity 4 Deluxe Edition"

EXE_NAME = "SimCity 4.exe"
TIME_DATE_STAMP = 0x4C12BFB7
IMAGE_BASE = 0x400000
SIZE_OF_IMAGE = 0x7C8000
FILE_SIZE = 7_524_352
FILE_VERSION = (1, 1, 641, 0)
SHA1 = {
    "ec64f671e227dc1640e85e3f303b28b0437a5792": "1.1.641 + 4GB patch (LARGE_ADDRESS_AWARE)",
    "c5607c745c727630af57b614fdbb71de044ed849": "1.1.641 as shipped by GOG",
}


def game_dir() -> str:
    return os.environ.get("SC4_GAME_DIR") or DEFAULT_GAME_DIR


def exe_path(root: str | None = None) -> str:
    return os.path.join(root or game_dir(), "Apps", EXE_NAME)


def pe_header(data: bytes) -> dict:
    """The PE fields the check uses, read straight from the file bytes (no pefile needed)."""
    if data[:2] != b"MZ":
        raise ValueError("not an MZ executable")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("no PE header")
    machine, nsec, stamp = struct.unpack_from("<HHI", data, pe + 4)
    characteristics = struct.unpack_from("<H", data, pe + 22)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic != 0x10B:
        raise ValueError("not a 32-bit PE")
    image_base, = struct.unpack_from("<I", data, opt + 28)
    size_of_image, = struct.unpack_from("<I", data, opt + 56)
    checksum, = struct.unpack_from("<I", data, opt + 64)
    return {"machine": machine, "sections": nsec, "time_date_stamp": stamp, "characteristics": characteristics,
            "large_address_aware": bool(characteristics & 0x20), "image_base": image_base,
            "size_of_image": size_of_image, "checksum": checksum}


def check_exe(path: str | None = None) -> dict:
    """Identify the executable. Returns {"ok", "path", "sha1", "variant", "large_address_aware", ...};
    "ok" is False (with "reason") for any build other than 1.1.641."""
    path = path or exe_path()
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return {"ok": False, "path": path, "reason": "cannot read the game executable: %s" % e}
    sha1 = hashlib.sha1(data).hexdigest()
    try:
        h = pe_header(data)
    except ValueError as e:
        return {"ok": False, "path": path, "sha1": sha1, "reason": str(e)}
    out = {"path": path, "sha1": sha1, "size": len(data), "large_address_aware": h["large_address_aware"],
           "time_date_stamp": "0x%08X" % h["time_date_stamp"], "variant": SHA1.get(sha1)}
    if h["time_date_stamp"] != TIME_DATE_STAMP or h["image_base"] != IMAGE_BASE or \
            h["size_of_image"] != SIZE_OF_IMAGE or len(data) != FILE_SIZE:
        out.update(ok=False, reason="unsupported build: SiMCP 4 supports only SimCity 4 Deluxe 1.1.641 "
                                    "(TimeDateStamp 0x%08X)" % TIME_DATE_STAMP)
        return out
    if out["variant"] is None:
        # Same build, but bytes differ from both known files: accept it only when clearing the large-address bit
        # and the PE checksum gives back the stock file (another 4GB tool, a different checksum).
        if normalized_sha1(data) != STOCK_SHA1:
            out.update(ok=False, reason="the executable's code differs from SimCity 4 1.1.641 (patched or "
                                        "damaged); restore the GOG original")
            return out
        out["variant"] = "1.1.641 with a modified PE header"
    out["ok"] = True
    return out


STOCK_SHA1 = "c5607c745c727630af57b614fdbb71de044ed849"


def normalized_sha1(data: bytes) -> str:
    """SHA-1 with LARGE_ADDRESS_AWARE cleared and the PE checksum zeroed (both 1.1.641 files give STOCK_SHA1)."""
    d = bytearray(data)
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    c = struct.unpack_from("<H", d, pe + 22)[0]
    struct.pack_into("<H", d, pe + 22, c & ~0x20)
    struct.pack_into("<I", d, pe + 24 + 64, 0)
    return hashlib.sha1(d).hexdigest()
