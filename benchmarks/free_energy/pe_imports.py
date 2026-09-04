"""Name the missing DLL, rather than guessing at it.

Windows reports a failed load as

    ImportError: DLL load failed while importing _C: The specified module
    could not be found.

and never says WHICH module. One message covers a dozen unrelated causes --
a missing runtime, a wrong architecture, a broken install, a search-order
problem -- so every fix for it is a guess, and the guesses are expensive.
A DLL's own import table says exactly what it needs. Reading it is about
sixty lines of struct unpacking and no new dependency.

**IT EARNED ITS PLACE IMMEDIATELY.** conda-forge's win-64 `pytorch` 2.10.0
would not import in the environment this benchmark's Windows half runs in,
and the recorded diagnosis was that PyTorch's extension does not work on
Windows -- a platform incompatibility, and a wall. It is not. `torch_cpu.dll`
has 26 imports, 25 of them resolvable and exactly one absent:

    libomp140.x86_64.dll        MISSING

LLVM's OpenMP runtime under the name MSVC-built binaries link it by. Neither
`pytorch` nor `libtorch` declares any OpenMP dependency, so nothing installs
it and the solve looks clean. `conda install llvm-openmp` plus a copy under
the name the binary wants is the whole fix, and the wall was a missing file.

Two guesses were eliminated by this before it found the answer, and both are
what somebody would have tried first: PATH (since CPython 3.8 it no longer
resolves an extension module's dependencies at all) and a truncated install
(`torch/lib` holds zero DLLs, which is the ordinary conda-forge layout --
the libraries are in `Library\\bin`, and conda's manifest reports 0 files
missing of 9111).

    python pe_imports.py torch_cpu.dll
    python pe_imports.py C:/path/to/some.dll another.pyd

Run it with the interpreter whose environment is in question: the search
directories are derived from `sys.prefix`, so the answer is about that
environment rather than about the machine.
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
from pathlib import Path

#: Where a conda environment keeps the libraries an extension module links.
#: Derived from `sys.prefix` rather than passed in, so the report is about the
#: interpreter running it and cannot silently describe a different install.
SEARCH_SUBDIRECTORIES = (
    ("Library", "bin"),
    ("Library", "mingw-w64", "bin"),
    ("Library", "usr", "bin"),
    (),
    ("DLLs",),
    ("Lib", "site-packages", "torch", "lib"),
)

_search_directories: list[Path] = []


def imports_of(path: Path) -> list[str]:
    """Every DLL named in a PE image's import directory.

    Parsed from the file rather than obtained by loading it, because loading
    is the thing that fails -- and a loader failure reports one name where
    the table reports all of them.
    """
    data = path.read_bytes()
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise ValueError(f"{path.name} is not a PE image")

    coff = e_lfanew + 4
    n_sections, = struct.unpack_from("<H", data, coff + 2)
    size_optional, = struct.unpack_from("<H", data, coff + 16)
    optional = coff + 20
    magic, = struct.unpack_from("<H", data, optional)
    # PE32+ puts the data directories 112 bytes into the optional header;
    # PE32 puts them at 96. Getting this wrong reads a plausible RVA out of
    # the wrong field and reports imports that do not exist.
    directories = optional + (112 if magic == 0x20B else 96)
    import_rva, _size = struct.unpack_from("<II", data, directories + 8)
    if not import_rva:
        return []

    sections = []
    base = optional + size_optional
    for index in range(n_sections):
        entry = base + index * 40
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
            "<IIII", data, entry + 8)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def offset_of(rva: int) -> int | None:
        for virtual_address, size, raw_pointer in sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_pointer + (rva - virtual_address)
        return None

    names: list[str] = []
    cursor = offset_of(import_rva)
    if cursor is None:
        return []
    while True:
        descriptor = data[cursor:cursor + 20]
        if len(descriptor) < 20 or descriptor == b"\0" * 20:
            break
        name_rva = struct.unpack_from("<I", descriptor, 12)[0]
        name_offset = offset_of(name_rva)
        if name_offset is not None:
            end = data.index(b"\0", name_offset)
            names.append(data[name_offset:end].decode("ascii", "replace"))
        cursor += 20
    return names


def where_is(name: str) -> str:
    """The environment first, then the system, then MISSING."""
    for directory in _search_directories:
        if (directory / name).is_file():
            return str(directory)
    try:
        ctypes.WinDLL(name)
        return "system"
    except OSError:
        return "MISSING"


def _resolve(argument: str) -> Path:
    candidate = Path(argument)
    if candidate.is_absolute():
        return candidate
    for directory in _search_directories:
        if (directory / argument).is_file():
            return directory / argument
    return candidate


def main() -> int:
    if os.name != "nt":
        print("PE import tables are a Windows question; nothing to do here.")
        return 0
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    prefix = Path(sys.prefix)
    for parts in SEARCH_SUBDIRECTORIES:
        directory = prefix.joinpath(*parts)
        if directory.is_dir():
            _search_directories.append(directory)
            os.add_dll_directory(str(directory))
    print(f"environment: {prefix}")

    exit_code = 0
    for argument in sys.argv[1:]:
        target = _resolve(argument)
        print(f"\n=== {target.name} ===")
        if not target.is_file():
            print("  not on disk in this environment")
            exit_code = 1
            continue
        missing = []
        for name in sorted(set(imports_of(target)), key=str.lower):
            location = where_is(name)
            marker = "   <-- MISSING" if location == "MISSING" else ""
            print(f"  {name:<36}{location}{marker}")
            if location == "MISSING":
                missing.append(name)
        print(f"  ---> {len(missing)} missing: "
              f"{', '.join(missing) if missing else 'none'}")
        if missing:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
