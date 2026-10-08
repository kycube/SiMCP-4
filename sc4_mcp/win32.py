"""Minimal ctypes wrappers for talking to the 32-bit SimCity 4 process from 64-bit Python."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

# Read, write and enumerate modules; nothing more (no thread creation, no allocation).
PROCESS_ACCESS = 0x0010 | 0x0020 | 0x0008 | 0x0400  # VM_READ | VM_WRITE | VM_OPERATION | QUERY_INFORMATION
LIST_MODULES_32BIT = 0x01
SMTO_ABORTIFHUNG = 0x0002

k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD, ctypes.POINTER(wt.DWORD),
                                       wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
psapi.EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
u32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
u32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                    ctypes.POINTER(ctypes.c_size_t)]
u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.IsWindow.argtypes = [wt.HWND]
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]


class WinError(RuntimeError):
    pass


def _check(ok, what):
    if not ok:
        raise WinError(f"{what} failed (error {ctypes.get_last_error()})")
    return ok


def find_pids(exe_name: str) -> list[int]:
    arr = (wt.DWORD * 4096)()
    needed = wt.DWORD()
    _check(psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)), "EnumProcesses")
    pids = []
    for pid in arr[: needed.value // 4]:
        h = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wt.DWORD(260)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) and \
                    buf.value.rsplit("\\", 1)[-1].lower() == exe_name.lower():
                pids.append(pid)
        finally:
            k32.CloseHandle(h)
    return pids


class Process:
    """A handle on the running 32-bit game with memory read/write helpers."""

    def __init__(self, pid: int):
        self.pid = pid
        self.handle = k32.OpenProcess(PROCESS_ACCESS, False, pid)
        _check(self.handle, f"OpenProcess({pid})")

    def close(self):
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None

    def alive(self) -> bool:
        code = wt.DWORD()
        return bool(self.handle) and bool(k32.GetExitCodeProcess(self.handle, ctypes.byref(code))) and code.value == 259

    def read(self, addr: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        _check(k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)),
               f"ReadProcessMemory({addr:#x},{size})")
        return buf.raw[: got.value]

    def write(self, addr: int, data: bytes) -> None:
        got = ctypes.c_size_t()
        _check(k32.WriteProcessMemory(self.handle, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got)),
               f"WriteProcessMemory({addr:#x},{len(data)})")

    def u8(self, a): return self.read(a, 1)[0]
    def u16(self, a): return struct.unpack("<H", self.read(a, 2))[0]
    def i32(self, a): return struct.unpack("<i", self.read(a, 4))[0]
    def u32(self, a): return struct.unpack("<I", self.read(a, 4))[0]
    def f32(self, a): return struct.unpack("<f", self.read(a, 4))[0]

    def cstr(self, a: int, maxlen: int = 256) -> str:
        return self.read(a, maxlen).split(b"\0", 1)[0].decode("latin-1")

    def modules32(self) -> dict[str, tuple[int, str]]:
        """{lower-case base name: (base address, full path)} of the 32-bit modules."""
        arr = (wt.HMODULE * 1024)()
        needed = wt.DWORD()
        _check(psapi.EnumProcessModulesEx(self.handle, arr, ctypes.sizeof(arr), ctypes.byref(needed),
                                          LIST_MODULES_32BIT), "EnumProcessModulesEx")
        out = {}
        for hm in arr[: needed.value // ctypes.sizeof(wt.HMODULE)]:
            name = ctypes.create_unicode_buffer(260)
            path = ctypes.create_unicode_buffer(520)
            psapi.GetModuleBaseNameW(self.handle, hm, name, 260)
            psapi.GetModuleFileNameExW(self.handle, hm, path, 520)
            out[name.value.lower()] = (hm or 0, path.value)
        return out


k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def pe_exports(path: str) -> dict[str, int]:
    """{name: rva} of a PE file's export table (tiny parser, no dependencies)."""
    data = open(path, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dd = opt + (96 if magic == 0x10B else 112)
    exp_rva, _ = struct.unpack_from("<II", data, dd)
    sec = opt + struct.unpack_from("<H", data, pe + 20)[0]
    sections = [struct.unpack_from("<8sIIII", data, sec + i * 40) for i in range(nsec)]

    def off(rva):
        for _, vsize, va, rawsize, rawptr in sections:
            if va <= rva < va + max(vsize, rawsize):
                return rva - va + rawptr
        raise ValueError(f"rva {rva:#x} not in any section")

    if not exp_rva:
        return {}
    e = off(exp_rva)
    _, nnames, afuncs, anames, aords = struct.unpack_from("<IIIII", data, e + 20)
    out = {}
    for i in range(nnames):
        o = off(struct.unpack_from("<I", data, off(anames) + 4 * i)[0])
        name = data[o: data.index(b"\0", o)].decode()
        ordinal = struct.unpack_from("<H", data, off(aords) + 2 * i)[0]
        out[name] = struct.unpack_from("<I", data, off(afuncs) + 4 * ordinal)[0]
    return out


def send_message(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0, timeout_ms: int = 15000) -> int:
    result = ctypes.c_size_t()
    ok = u32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result))
    if not ok:
        raise WinError(f"SendMessageTimeout failed or timed out (error {ctypes.get_last_error()})")
    return ctypes.c_int32(result.value & 0xFFFFFFFF).value


def post_message(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> None:
    _check(u32.PostMessageW(hwnd, msg, wparam, lparam), "PostMessage")
