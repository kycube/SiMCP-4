"""DBPF files (SimCity 4's .dat / .sc4 / .SC4Lot / .SC4Desc / .SC4Model / .cfg containers) and the records in them.

A DBPF file is a header, the records' data and an index of {type, group, instance, offset, size} entries (TGI keys).
Compressed records start with a u32 total length followed by a QFS (EA RefPack) stream; the file's DIR record
(type 0xE86B1EEF) lists which records are compressed and their uncompressed sizes.

Also here: QFS compression, exemplar / cohort records (binary "EQZB1###" / "CQZB1###" and text "EQZT1###") and
LTEXT strings. Nothing in this module talks to the running game.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

MAGIC = b"DBPF"
HEADER_SIZE = 0x60

# Well-known record types (names as the modding community uses them; VERIFY each against the game's own data).
T_DIR = 0xE86B1EEF
T_EXEMPLAR = 0x6534284A
T_COHORT = 0x05342861
T_LTEXT = 0x2026960B
T_FSH = 0x7AB50E44
T_S3D = 0x5AD0E817
T_PNG = 0x856DDBAC
T_LUA = 0xCA63E2A3
T_RUL = 0x0A5BCF4B
T_SC4PATH = 0x296678F7
T_SC4PATH_3D = 0xA966883F
T_EFFDIR = 0xEA5118B0
T_KEYCFG = 0xA2E3D533
T_INI = 0x00000000           # generic / UI and INI text live under type 0 with various groups

TYPE_NAMES = {
    T_DIR: "DIR", T_EXEMPLAR: "Exemplar", T_COHORT: "Cohort", T_LTEXT: "LTEXT", T_FSH: "FSH", T_S3D: "S3D",
    T_PNG: "PNG", T_LUA: "Lua", T_RUL: "RUL", T_SC4PATH: "SC4Path", T_SC4PATH_3D: "SC4Path3D", T_EFFDIR: "EffectDir",
    T_KEYCFG: "KeyConfig",
}


# ------------------------------------------------------------------------------------------------- QFS (RefPack)
def qfs_decompress(src: bytes) -> bytes:
    """EA RefPack stream (starts with 10 FB + 3-byte big-endian size; variants with a 4-byte size handled)."""
    flags = src[0] << 8 | src[1]
    if flags & 0xFF != 0xFB:
        raise ValueError("not a QFS / RefPack stream")
    w = 4 if flags & 0x8000 else 3
    i = 2 + (w if flags & 0x0100 else 0)
    size = int.from_bytes(src[i:i + w], "big")
    i += w
    out = bytearray()
    n = len(src)
    while i < n:
        b0 = src[i]
        if b0 < 0x80:
            b1 = src[i + 1]; i += 2
            plain = b0 & 3; cnt = ((b0 >> 2) & 7) + 3; off = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[i + 1], src[i + 2]; i += 3
            plain = b1 >> 6; cnt = (b0 & 0x3F) + 4; off = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[i + 1], src[i + 2], src[i + 3]; i += 4
            plain = b0 & 3; cnt = ((b0 & 0x0C) << 6) + b3 + 5; off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            i += 1; plain = ((b0 & 0x1F) << 2) + 4; cnt = 0; off = 0
        else:
            i += 1; plain = b0 & 3
            out += src[i:i + plain]
            break
        out += src[i:i + plain]; i += plain
        if cnt:
            start = len(out) - off
            if start < 0:
                raise ValueError("QFS back-reference before the start of the output")
            if off >= cnt:
                out += out[start:start + cnt]
            else:
                for k in range(cnt):
                    out.append(out[start + k])
    if len(out) < size:
        raise ValueError("QFS stream ended early (%d < %d)" % (len(out), size))
    return bytes(out[:size])


def qfs_compress(src: bytes, max_chain: int = 24) -> bytes:
    """Greedy LZ77 RefPack encoder (10 FB + 3-byte size), decodable by the game's and by qfs_decompress.
    SC4's decoder limits back-references to 128 KiB, which this encoder respects."""
    n = len(src)
    if n >= 1 << 24:
        raise ValueError("too large for a 3-byte QFS size")
    out = bytearray(b"\x10\xfb" + n.to_bytes(3, "big"))
    head: dict[bytes, int] = {}
    prev = [-1] * n
    lit = 0
    i = 0

    def flush_literals(upto, keep):
        nonlocal lit
        while upto - lit > keep:
            k = min(112, (upto - lit - keep) & ~3) if (upto - lit - keep) >= 4 else 0
            if k == 0:
                break
            out.append(0xE0 + (k >> 2) - 1)
            out.extend(src[lit:lit + k])
            lit += k

    def insert(p):
        if p + 3 <= n:
            key = src[p:p + 3]
            prev[p] = head.get(key, -1)
            head[key] = p

    while i < n:
        best_l = 0
        best_off = 0
        if i + 3 <= n:
            j = head.get(src[i:i + 3], -1)
            chain = 0
            maxl = min(1028, n - i)
            while j >= 0 and chain < max_chain:
                off = i - j
                if off > 131072:
                    break
                if best_l < maxl and src[j + best_l] == src[i + best_l]:
                    ln = 3
                    while ln < maxl and src[j + ln] == src[i + ln]:
                        ln += 1
                    ok = ln >= 5 if off > 16384 else (ln >= 4 if off > 1024 else True)
                    if ok and ln > best_l:
                        best_l, best_off = ln, off
                        if ln == maxl:
                            break
                j = prev[j]
                chain += 1
        if best_l >= 3:
            flush_literals(i, (i - lit) & 3)
            plain = i - lit
            ln, o = best_l, best_off - 1
            if ln <= 10 and o < 1024:
                out += bytes((((o >> 3) & 0x60) | ((ln - 3) << 2) | plain, o & 0xFF))
            elif ln <= 67 and o < 16384:
                out += bytes((0x80 | (ln - 4), (plain << 6) | (o >> 8), o & 0xFF))
            else:
                out += bytes((0xC0 | ((o >> 16) << 4) | (((ln - 5) >> 8) << 2) | plain, (o >> 8) & 0xFF, o & 0xFF,
                              (ln - 5) & 0xFF))
            out += src[lit:i]
            for p in range(i, i + ln):
                insert(p)
            i += ln
            lit = i
        else:
            insert(i)
            i += 1
    rem = (n - lit) & 3
    flush_literals(n, rem)
    out.append(0xFC + (n - lit))
    out += src[lit:n]
    return bytes(out)


def is_compressed_record(raw: bytes) -> bool:
    """A DBPF record body is compressed when it is u32 total length + a QFS stream."""
    return len(raw) >= 9 and raw[4:6] == b"\x10\xfb" and struct.unpack_from("<I", raw)[0] == len(raw)


# ------------------------------------------------------------------------------------------------------- DBPF
@dataclass
class Entry:
    type: int
    group: int
    instance: int
    offset: int
    size: int
    resource: int = 0          # index 7.1 only (a fourth key)
    usize: int | None = None   # uncompressed size from the DIR record, if compressed

    @property
    def tgi(self) -> tuple[int, int, int]:
        return self.type, self.group, self.instance

    @property
    def compressed(self) -> bool:
        return self.usize is not None


@dataclass
class Header:
    major: int
    minor: int
    created: int
    modified: int
    index_major: int
    index_count: int
    index_offset: int
    index_size: int
    hole_count: int
    hole_offset: int
    hole_size: int
    index_minor: int


class DBPF:
    """Read-only access to a DBPF file. Records are read on demand (the file is not loaded whole)."""

    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as f:
            raw = f.read(HEADER_SIZE)
            if len(raw) < HEADER_SIZE or raw[:4] != MAGIC:
                raise ValueError("%s: not a DBPF file" % path)
            (major, minor) = struct.unpack_from("<2I", raw, 4)
            created, modified, imaj, icount, ioff, isize, hcount, hoff, hsize, imin = struct.unpack_from("<10I", raw, 0x18)
            self.header = Header(major, minor, created, modified, imaj, icount, ioff, isize, hcount, hoff, hsize, imin)
            f.seek(ioff)
            index = f.read(isize)
        width = isize // icount if icount else 20
        if width not in (20, 24):
            raise ValueError("%s: unexpected index entry size %d" % (path, width))
        self.entries: list[Entry] = []
        for k in range(icount):
            o = k * width
            if width == 20:
                t, g, i, off, sz = struct.unpack_from("<5I", index, o); r = 0
            else:
                t, g, i, r, off, sz = struct.unpack_from("<6I", index, o)
            self.entries.append(Entry(t, g, i, off, sz, r))
        self._by_tgi = {e.tgi: e for e in self.entries}
        d = self._by_tgi.get((T_DIR, T_DIR, 0x286B1F03))
        if d is not None:
            body = self._read_raw(d)
            w = 20 if width == 24 else 16
            for o in range(0, len(body) - w + 1, w):
                if w == 16:
                    t, g, i, us = struct.unpack_from("<4I", body, o); r = 0
                else:
                    t, g, i, r, us = struct.unpack_from("<5I", body, o)
                e = self._by_tgi.get((t, g, i))
                if e is not None:
                    e.usize = us

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def _read_raw(self, e: Entry) -> bytes:
        with open(self.path, "rb") as f:
            f.seek(e.offset)
            return f.read(e.size)

    def find(self, type_: int, group: int | None = None, instance: int | None = None) -> list[Entry]:
        return [e for e in self.entries if e.type == type_ and (group is None or e.group == group)
                and (instance is None or e.instance == instance)]

    def get(self, t: int, g: int, i: int) -> Entry | None:
        return self._by_tgi.get((t, g, i))

    def read(self, e: Entry) -> bytes:
        """The record's data, decompressed when the DIR record (or the body itself) says it is compressed."""
        raw = self._read_raw(e)
        if e.compressed or (e.type != T_DIR and is_compressed_record(raw)):
            return qfs_decompress(raw[4:])
        return raw


def write_dbpf(path: str, records: list[tuple[int, int, int, bytes]], compress: bool = True,
               created: int = 0, modified: int = 0) -> None:
    """Write a DBPF 1.0 file (index 7.0) holding records [(type, group, instance, data)], QFS-compressing records
    that shrink (with a DIR record), the way the game's own files are laid out. Written to a temp file, then moved."""
    body = bytearray()
    index = bytearray()
    dir_rows = bytearray()
    off = HEADER_SIZE
    for t, g, i, data in records:
        blob = data
        if compress and len(data) > 16:
            c = qfs_compress(data)
            if len(c) + 4 < len(data):
                blob = struct.pack("<I", len(c) + 4) + c
                dir_rows += struct.pack("<4I", t, g, i, len(data))
        index += struct.pack("<5I", t, g, i, off, len(blob))
        body += blob
        off += len(blob)
    count = len(records)
    if dir_rows:
        index += struct.pack("<5I", T_DIR, T_DIR, 0x286B1F03, off, len(dir_rows))
        body += dir_rows
        off += len(dir_rows)
        count += 1
    hdr = bytearray(HEADER_SIZE)
    hdr[0:4] = MAGIC
    struct.pack_into("<2I", hdr, 4, 1, 0)
    struct.pack_into("<10I", hdr, 0x18, created, modified, 7, count, off, len(index), 0, 0, 0, 0)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(hdr); f.write(body); f.write(index)
    os.replace(tmp, path)


# -------------------------------------------------------------------------------------------- exemplars/cohorts
PT_UINT8, PT_UINT16, PT_UINT32, PT_SINT32, PT_SINT64, PT_FLOAT32, PT_BOOL, PT_STRING = (
    0x100, 0x200, 0x300, 0x700, 0x800, 0x900, 0xB00, 0xC00)
_PT_FMT = {PT_UINT8: "B", PT_UINT16: "H", PT_UINT32: "I", PT_SINT32: "i", PT_SINT64: "q", PT_FLOAT32: "f",
           PT_BOOL: "?"}
PT_NAMES = {PT_UINT8: "Uint8", PT_UINT16: "Uint16", PT_UINT32: "Uint32", PT_SINT32: "Sint32", PT_SINT64: "Sint64",
            PT_FLOAT32: "Float32", PT_BOOL: "Bool", PT_STRING: "String"}


@dataclass
class Property:
    id: int
    ptype: int
    values: list = field(default_factory=list)   # a str for String properties
    multi: bool = False

    @property
    def value(self):
        """The single value (or the string, or the list for multi-value properties)."""
        if self.ptype == PT_STRING or self.multi:
            return self.values
        return self.values[0] if self.values else None


@dataclass
class Exemplar:
    kind: str                       # "exemplar" or "cohort"
    parent: tuple[int, int, int]    # parent cohort TGI
    props: list[Property]

    def get(self, pid: int, default=None):
        for p in self.props:
            if p.id == pid:
                return p.value
        return default


def is_exemplar(data: bytes) -> bool:
    return data[:3] in (b"EQZ", b"CQZ")


def parse_exemplar(data: bytes) -> Exemplar:
    sig = data[:8]
    kind = "cohort" if sig[:1] == b"C" else "exemplar"
    if sig[3:4] == b"T":
        return _parse_text_exemplar(data, kind)
    if sig[3:4] != b"B":
        raise ValueError("not a binary exemplar: %r" % sig)
    parent = struct.unpack_from("<3I", data, 8)
    count = struct.unpack_from("<I", data, 20)[0]
    o = 24
    props = []
    for _ in range(count):
        pid, ptype, ktype = struct.unpack_from("<IHH", data, o); o += 8
        if ktype == 0x80:
            o += 1                                    # unused byte
            n = struct.unpack_from("<I", data, o)[0]; o += 4
            if ptype == PT_STRING:
                props.append(Property(pid, ptype, data[o:o + n].decode("latin-1"), True)); o += n
            else:
                fmt = _PT_FMT[ptype]; sz = struct.calcsize(fmt)
                props.append(Property(pid, ptype, list(struct.unpack_from("<%d%s" % (n, fmt), data, o)), True))
                o += n * sz
        else:
            o += 1                                    # repetitions byte (0 for a single value)
            if ptype == PT_STRING:
                raise ValueError("single-value string property 0x%08X" % pid)
            fmt = _PT_FMT[ptype]; sz = struct.calcsize(fmt)
            props.append(Property(pid, ptype, [struct.unpack_from("<" + fmt, data, o)[0]], False))
            o += sz
    return Exemplar(kind, parent, props)


def _parse_text_exemplar(data: bytes, kind: str) -> Exemplar:
    """Text exemplars ("EQZT1###"): ParentCohort=Key:{0x..,0x..,0x..} / PropCount=0x.. / then lines
    0xID:{"Name"}=Type:Reps:{values}. Rare in Maxis files; parsed for completeness."""
    import re
    text = data[8:].decode("latin-1")
    m = re.search(r"ParentCohort\s*=\s*Key:\{([^}]*)\}", text)
    parent = tuple(int(x, 16) for x in m.group(1).split(",")) if m else (0, 0, 0)
    props = []
    tnames = {v.lower(): k for k, v in PT_NAMES.items()}
    for pm in re.finditer(r"(0x[0-9A-Fa-f]{8}):\{\"[^\"]*\"\}=(\w+):(\d+):\{(.*?)\}\s*$", text, re.M):
        pid = int(pm.group(1), 16); ptype = tnames.get(pm.group(2).lower(), PT_UINT32); reps = int(pm.group(3))
        body = pm.group(4)
        if ptype == PT_STRING:
            props.append(Property(pid, ptype, body.strip().strip('"'), True)); continue
        vals = []
        for v in [x.strip() for x in body.split(",") if x.strip()]:
            if ptype == PT_FLOAT32:
                vals.append(float(v))
            elif ptype == PT_BOOL:
                vals.append(v.lower() in ("true", "1"))
            else:
                vals.append(int(v, 0))
        props.append(Property(pid, ptype, vals, reps > 0))
    return Exemplar(kind, parent, props)


def build_exemplar(props: list[Property], parent: tuple[int, int, int] = (0, 0, 0), kind: str = "exemplar") -> bytes:
    """A binary exemplar / cohort record."""
    out = bytearray((b"CQZB1###" if kind == "cohort" else b"EQZB1###"))
    out += struct.pack("<3I", *parent) + struct.pack("<I", len(props))
    for p in props:
        if p.ptype == PT_STRING:
            s = p.values.encode("latin-1") if isinstance(p.values, str) else bytes(p.values)
            out += struct.pack("<IHHBI", p.id, p.ptype, 0x80, 0, len(s)) + s
        elif p.multi:
            fmt = _PT_FMT[p.ptype]
            out += struct.pack("<IHHBI", p.id, p.ptype, 0x80, 0, len(p.values))
            out += struct.pack("<%d%s" % (len(p.values), fmt), *p.values)
        else:
            out += struct.pack("<IHHB", p.id, p.ptype, 0, 0) + struct.pack("<" + _PT_FMT[p.ptype], p.values[0])
    return bytes(out)


# --------------------------------------------------------------------------------------------------- LTEXT
def parse_ltext(data: bytes) -> str:
    """LTEXT: u16 character count, u16 0x1000, then UTF-16LE characters."""
    n, marker = struct.unpack_from("<HH", data)
    if marker != 0x1000:
        raise ValueError("not an LTEXT record")
    return data[4:4 + 2 * n].decode("utf-16-le", errors="replace")


def build_ltext(text: str) -> bytes:
    enc = text.encode("utf-16-le")
    return struct.pack("<HH", len(enc) // 2, 0x1000) + enc
