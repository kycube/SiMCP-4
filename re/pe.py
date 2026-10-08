"""Static RE helpers for SimCity 4 1.1.641 (STATIC ONLY: never touches the running game).

Usage from another script:
    import sys; sys.path.insert(0, r"<repo>\\re")
    from pe import Image
    im = Image()                          # Apps\\SimCity 4.exe (or Image(path) for a plugin DLL)
    for va in im.find_str("LoadRegion"): print(hex(va), [hex(x) for x in im.xrefs(va)])
    print(im.dis(0x401000, 40))
    print([hex(c) for c in im.calls_to(0x401000)])

Addresses are VAs at the module's preferred base (the exe: 0x400000; it is never relocated).
The exe was built with MSVC 7.x (/GR- except a few exception classes) and STLport; many functions have no
`push ebp` frame, so function starts come from the set of direct call targets and vtable slots (func_start).
"""
from __future__ import annotations

import os
import re
import struct
import sys

import capstone
import numpy as np
import pefile

GAME = os.environ.get("SC4_GAME_DIR") or r"C:\Program Files\GOG Galaxy\Games\SimCity 4 Deluxe Edition"
EXE = os.path.join(GAME, "Apps", "SimCity 4.exe")


class Image:
    def __init__(self, path: str | None = None):
        path = path or EXE
        self.path = path
        self.name = os.path.basename(path)
        self.pe = pefile.PE(path, fast_load=False)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.mem = self.pe.get_memory_mapped_image()
        self.names: dict[int, str] = {}
        self.imports: dict[int, str] = {}
        if hasattr(self.pe, "DIRECTORY_ENTRY_IMPORT"):
            for entry in self.pe.DIRECTORY_ENTRY_IMPORT:
                dll = entry.dll.decode(errors="replace")
                for imp in entry.imports:
                    nm = imp.name.decode(errors="replace") if imp.name else f"#{imp.ordinal}"
                    self.imports[imp.address] = f"{dll}!{nm}"
                    self.names[imp.address] = f"[{dll}!{nm}]"
        self.exports: dict[str, int] = {}
        if hasattr(self.pe, "DIRECTORY_ENTRY_EXPORT"):
            for e in self.pe.DIRECTORY_ENTRY_EXPORT.symbols:
                nm = e.name.decode() if e.name else f"#{e.ordinal}"
                self.exports[nm] = self.base + e.address
                self.names[self.base + e.address] = nm
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        self.md.detail = False
        self.texts = [s for s in self.pe.sections if s.Characteristics & 0x20000000]
        self._calls = None      # (src array, dst array) of direct E8/E9 branches
        self._starts = None     # sorted array of known function starts

    # ---- addressing
    def rva(self, va):
        return va - self.base

    def read(self, va, n):
        o = va - self.base
        return self.mem[o:o + n]

    def u32(self, va):
        return struct.unpack_from("<I", self.mem, va - self.base)[0]

    def cstr(self, va, maxlen=512):
        return self.read(va, maxlen).split(b"\0", 1)[0].decode("latin-1")

    def wstr(self, va, maxlen=512):
        b = self.read(va, maxlen * 2)
        end = next((i for i in range(0, len(b) - 1, 2) if b[i] == 0 and b[i + 1] == 0), len(b))
        return b[:end].decode("utf-16-le", errors="replace")

    def section_of(self, va):
        r = va - self.base
        for s in self.pe.sections:
            if s.VirtualAddress <= r < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.Name.rstrip(b"\0").decode()
        return None

    def is_code(self, va):
        r = va - self.base
        return any(s.VirtualAddress <= r < s.VirtualAddress + s.Misc_VirtualSize for s in self.texts)

    # ---- searching
    def find_bytes(self, pat: bytes):
        return [self.base + m.start() for m in re.finditer(re.escape(pat), self.mem)]

    def find_str(self, s, wide=False, exact=True):
        """VAs of a string. exact=True requires NUL termination."""
        enc = s.encode("utf-16-le") if wide else s.encode("latin-1")
        term = b"\0\0" if wide else b"\0"
        res = []
        for va in self.find_bytes(enc):
            o = va - self.base
            if exact and self.mem[o + len(enc):o + len(enc) + len(term)] != term:
                continue
            res.append(va)
        return res

    def strings(self, minlen=5):
        """Printable ASCII strings in non-code sections: [(va, str)]."""
        out = []
        for s in self.pe.sections:
            if s in self.texts:
                continue
            o, n = s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData)
            for m in re.finditer(rb"[\x20-\x7e\t\r\n]{%d,}" % minlen, self.mem[o:o + n]):
                out.append((self.base + o + m.start(), m.group().decode("latin-1")))
        return out

    def xrefs(self, va):
        """Code locations whose instruction contains imm/disp32 == va (push, mov, lea, cmp...)."""
        pat = struct.pack("<I", va)
        res = set()
        for s in self.texts:
            o, n = s.VirtualAddress, s.Misc_VirtualSize
            for m in re.finditer(re.escape(pat), self.mem[o:o + n]):
                ins = self.insn_containing(self.base + o + m.start())
                if ins:
                    res.add(ins[0])
        return sorted(res)

    def data_refs(self, va):
        """Non-code locations holding the dword va (vtable slots, pointer tables)."""
        pat = struct.pack("<I", va)
        res = []
        for s in self.pe.sections:
            if s in self.texts:
                continue
            o, n = s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData)
            res += [self.base + o + m.start() for m in re.finditer(re.escape(pat), self.mem[o:o + n])]
        return res

    def _call_index(self):
        if self._calls is None:
            srcs, dsts = [], []
            for s in self.texts:
                o, n = s.VirtualAddress, s.Misc_VirtualSize
                blob = np.frombuffer(bytes(self.mem[o:o + n]), dtype=np.uint8)
                idx = np.nonzero((blob[:-4] == 0xE8) | (blob[:-4] == 0xE9))[0]
                rel = (blob[idx + 1].astype(np.int64) | (blob[idx + 2].astype(np.int64) << 8) |
                       (blob[idx + 3].astype(np.int64) << 16) | (blob[idx + 4].astype(np.int64) << 24))
                rel = np.where(rel >= 1 << 31, rel - (1 << 32), rel)
                src = self.base + o + idx
                dst = (src + 5 + rel) & 0xFFFFFFFF
                srcs.append(src); dsts.append(dst)
            self._calls = (np.concatenate(srcs), np.concatenate(dsts))
        return self._calls

    def calls_to(self, target):
        """Direct E8 call / E9 jmp sites to target (byte-pattern based: confirm with dis()), plus
        call/jmp [iat] when target is an IAT slot."""
        src, dst = self._call_index()
        res = set(int(x) for x in src[dst == target])
        if target in self.imports:
            res |= set(self.xrefs(target))
        return sorted(res)

    def function_starts(self):
        """Sorted array of likely function starts: direct call targets that land in code, plus vtable slots."""
        if self._starts is None:
            src, dst = self._call_index()
            lo =self.base + min(s.VirtualAddress for s in self.texts)
            hi = self.base + max(s.VirtualAddress + s.Misc_VirtualSize for s in self.texts)
            cand = dst[(dst >= lo) & (dst < hi)]
            vt = [f for v in self.vtable_starts() for (_, f, _) in self.vtable(v, 400, args=False)]
            self._starts = np.unique(np.concatenate([cand, np.array(vt, dtype=np.int64)]))
        return self._starts

    def func_start(self, va):
        """Nearest known function start at or before va (see function_starts)."""
        st = self.function_starts()
        i = np.searchsorted(st, va, side="right") - 1
        return int(st[i]) if i >= 0 else None

    def insn_containing(self, va, back=15):
        """An instruction that decodes cleanly and contains byte va (heuristic)."""
        for start in range(va - back, va + 1):
            insns = list(self.md.disasm(self.read(start, 16), start, count=1))
            if insns and insns[0].address <= va < insns[0].address + insns[0].size:
                if len(list(self.md.disasm(self.read(start, 48), start, count=4))) >= 3:
                    return (start, insns[0])
        return None

    # ---- disassembly
    def annotate(self, ins):
        txt = f"{ins.mnemonic} {ins.op_str}"
        notes = []
        for m in re.finditer(r"0x[0-9a-f]{5,8}", ins.op_str):
            v = int(m.group(), 16)
            if v in self.names:
                notes.append(self.names[v])
            elif self.base <= v < self.base + len(self.mem) and self.section_of(v) in (".rdata", ".data"):
                s = self.cstr(v, 80)
                if len(s) >= 3 and all(32 <= ord(c) < 127 or c in "\r\n\t" for c in s):
                    notes.append(repr(s))
                else:
                    w = self.wstr(v, 60)
                    if len(w) >= 3 and all(32 <= ord(c) < 127 for c in w):
                        notes.append("L" + repr(w))
        return txt + (("    ; " + " ".join(notes)) if notes else "")

    def dis(self, va, count=30, stop_at_ret=False):
        out = []
        for ins in self.md.disasm(self.read(va, count * 16), va):
            out.append(f"{ins.address:08x}  {ins.bytes.hex():<20} {self.annotate(ins)}")
            count -= 1
            if count <= 0 or (stop_at_ret and ins.mnemonic.startswith("ret")):
                break
        return "\n".join(out)

    def around(self, va, before=0x60, after=0x80):
        """Disassemble a window around va, synced from the enclosing function start."""
        f = self.func_start(va) or (va - before)
        if va - f > 0x2000:
            f = va - before
        out = []
        for ins in self.md.disasm(self.read(f, va - f + after), f):
            if ins.address >= va - before:
                mark = ">>" if ins.address <= va < ins.address + ins.size else "  "
                out.append(f"{mark}{ins.address:08x}  {self.annotate(ins)}")
        return "\n".join(out)

    def follow_jmp(self, f):
        """Follow leading `jmp rel32` thunks."""
        for _ in range(4):
            b = self.read(f, 5)
            if b[0] != 0xE9:
                break
            f = (f + 5 + struct.unpack("<i", b[1:5])[0]) & 0xFFFFFFFF
        return f

    def stack_args(self, f, limit=0x3000):
        """Stack args a thiscall/stdcall function pops (from its first `ret N`; cdecl -> 0)."""
        f = self.follow_jmp(f)
        for ins in self.md.disasm(self.read(f, limit), f):
            if ins.mnemonic == "ret":
                return int(ins.op_str, 16) // 4 if ins.op_str else 0
            if ins.mnemonic == "jmp" and ins.op_str.startswith("dword ptr ["):
                return None
        return None

    def vtable(self, va, maxn=200, args=True):
        """[(slot, fn, nargs)] for a vtable at va, stopping at the first non-code entry. Vtables are contiguous
        in .rdata; the last slots may belong to the next vtable (check data_refs of the following addresses)."""
        out = []
        for i in range(maxn):
            f = self.u32(va + 4 * i)
            if not self.is_code(f):
                break
            out.append((i, f, self.stack_args(f) if args else None))
        return out

    def vtable_starts(self):
        """{vtable_va: [code addrs]} from constructor stores `mov dword ptr [reg(+disp8)], imm32`."""
        if getattr(self, "_vts", None) is None:
            res = {}
            for s in self.texts:
                o, n = s.VirtualAddress, s.Misc_VirtualSize
                blob = self.mem[o:o + n]
                for m in re.finditer(rb"\xc7[\x00-\x07](....)|\xc7[\x40-\x47].(....)", blob, re.S):
                    v = struct.unpack("<I", m.group(1) or m.group(2))[0]
                    if self.base <= v < self.base + len(self.mem) and not self.is_code(v) and \
                            self.section_of(v) == ".rdata" and self.is_code(self.u32(v)):
                        res.setdefault(v, []).append(self.base + o + m.start())
            self._vts = res
        return self._vts


def main():
    im = Image(sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--image" else None)
    args = sys.argv[3:] if sys.argv[1:2] == ["--image"] else sys.argv[1:]
    cmd = args[0]
    if cmd == "str":
        for va in im.find_str(args[1], exact=False):
            print(hex(va), im.section_of(va), [hex(x) for x in im.xrefs(va)])
    elif cmd == "dis":
        print(im.dis(int(args[1], 16), int(args[2]) if len(args) > 2 else 40))
    elif cmd == "around":
        print(im.around(int(args[1], 16)))
    elif cmd == "xref":
        print([hex(x) for x in im.xrefs(int(args[1], 16))])
    elif cmd == "calls":
        print([hex(x) for x in im.calls_to(int(args[1], 16))])
    elif cmd == "vtable":
        for slot, f, n in im.vtable(int(args[1], 16)):
            print("%3d +0x%03x %08x args=%s" % (slot, slot * 4, f, n))


if __name__ == "__main__":
    main()
