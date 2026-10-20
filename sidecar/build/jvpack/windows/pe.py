# SPDX-License-Identifier: AGPL-3.0-or-later
"""The DLLs a Windows program loads: a small PE import reader (no extra packages).

Used to copy only what a bundled program needs (pdftotext from the poppler
build, tesseract from the UB Mannheim installer) and nothing else, so every
file in a package has a known licence.
"""

from __future__ import annotations

import struct
from pathlib import Path

# Part of Windows 10/11 itself; never copied into a package.
SYSTEM_PREFIXES = ("api-ms-win-", "ext-ms-win-")
SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll", "cfgmgr32.dll", "comctl32.dll", "comdlg32.dll",
    "crypt32.dll", "dbghelp.dll", "dnsapi.dll", "dwrite.dll", "gdi32.dll", "gdiplus.dll", "imm32.dll",
    "iphlpapi.dll", "kernel32.dll", "msimg32.dll", "msvcrt.dll", "ncrypt.dll", "netapi32.dll", "normaliz.dll",
    "ntdll.dll", "ole32.dll", "oleaut32.dll", "psapi.dll", "rpcrt4.dll", "secur32.dll", "setupapi.dll",
    "shell32.dll", "shlwapi.dll", "user32.dll", "userenv.dll", "usp10.dll", "uxtheme.dll", "version.dll",
    "winhttp.dll", "wininet.dll", "winmm.dll", "winspool.drv", "ws2_32.dll", "wsock32.dll", "wldap32.dll",
    "ucrtbase.dll", "mpr.dll", "powrprof.dll", "propsys.dll", "dwmapi.dll", "d3d11.dll", "dxgi.dll",
    "opengl32.dll", "glu32.dll", "comsvcs.dll", "authz.dll", "wtsapi32.dll", "netutils.dll", "srvcli.dll",
    "kernelbase.dll", "sspicli.dll", "mswsock.dll",
}


class PEError(Exception):
    pass


def is_system(name: str) -> bool:
    n = name.lower()
    return n in SYSTEM_DLLS or n.startswith(SYSTEM_PREFIXES)


def machine(path: Path) -> int:
    data = path.read_bytes()[:4096]
    if data[:2] != b"MZ":
        raise PEError(f"{path.name} er ikke en PE-fil")
    off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[off:off + 4] != b"PE\0\0":
        raise PEError(f"{path.name} er ikke en PE-fil")
    return struct.unpack_from("<H", data, off + 4)[0]


def imports(path: Path) -> list[str]:
    """Names of the DLLs in the import and delay-import tables."""
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise PEError(f"{path.name} er ikke en PE-fil")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise PEError(f"{path.name} er ikke en PE-fil")
    n_sections = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dd = opt + (112 if magic == 0x20B else 96)
    sections = []
    sec = opt + opt_size
    for i in range(n_sections):
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, sec + i * 40 + 8)
        sections.append((vaddr, max(vsize, rsize), raddr))

    def rva(r: int) -> int:
        for vaddr, size, raddr in sections:
            if vaddr <= r < vaddr + size:
                return r - vaddr + raddr
        raise PEError(f"{path.name}: ugyldig RVA")

    def cstr(r: int) -> str:
        o = rva(r)
        return data[o:data.index(b"\0", o)].decode("ascii", "replace")

    names: list[str] = []
    imp_rva, imp_size = struct.unpack_from("<II", data, dd + 8 * 1)
    if imp_rva:
        o = rva(imp_rva)
        while True:
            name_rva = struct.unpack_from("<I", data, o + 12)[0]
            if name_rva == 0:
                break
            names.append(cstr(name_rva))
            o += 20
    delay_rva, _ = struct.unpack_from("<II", data, dd + 8 * 13)
    if delay_rva:
        o = rva(delay_rva)
        while True:
            name_rva = struct.unpack_from("<I", data, o + 4)[0]
            if name_rva == 0:
                break
            names.append(cstr(name_rva))
            o += 32
    return names


def closure(programs: list[Path], search: list[Path]) -> tuple[dict[str, Path], set[str]]:
    """(DLLs found in `search`, by lower-case name; DLLs found nowhere).

    System DLLs (Windows itself) are skipped. A DLL that is neither a system
    DLL nor in `search` is returned in the second set so the build can stop.
    """
    index: dict[str, Path] = {}
    for d in search:
        if d.is_dir():
            for p in d.iterdir():
                if p.suffix.lower() == ".dll":
                    index.setdefault(p.name.lower(), p)
    found: dict[str, Path] = {}
    missing: set[str] = set()
    todo = list(programs)
    while todo:
        for name in imports(todo.pop()):
            key = name.lower()
            if is_system(key) or key in found or key in missing:
                continue
            p = index.get(key)
            if p is None:
                missing.add(key)
                continue
            found[key] = p
            todo.append(p)
    return found, missing
