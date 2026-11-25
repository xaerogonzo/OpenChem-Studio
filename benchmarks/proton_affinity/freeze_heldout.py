"""The freeze of the proton-affinity held-out size arm (`PREREGISTRATION_HELDOUT.md`).

    python freeze_heldout.py write      write freeze_heldout.json from the files as they are NOW
    python freeze_heldout.py check      print every difference between the files and freeze_heldout.json

Hashes are over bytes with CRLF normalised to LF. Changing a frozen file is an Amendment of the preregistration, never a silent edit. `run_pa.py` and `pa_core.py` are hashed because they ARE the protocol; do not edit them to add this arm (the wrapper is `run_pa_heldout.py`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FREEZE = HERE / "freeze_heldout.json"
PREREGISTRATION = "benchmarks/proton_affinity/PREREGISTRATION_HELDOUT.md"
FILES = [
    "benchmarks/proton_affinity/PREREGISTRATION_HELDOUT.md",
    "benchmarks/proton_affinity/heldout_values.json",
    "benchmarks/proton_affinity/heldout.py",
    "benchmarks/proton_affinity/run_pa_heldout.py",
    "benchmarks/proton_affinity/freeze_heldout.py",
    "benchmarks/proton_affinity/run_pa.py",
    "benchmarks/proton_affinity/pa_core.py",
    "benchmarks/proton_affinity/judge.py",
]


def normalised(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current() -> dict:
    return {"files": {rel: sha256(normalised(REPO / rel)) for rel in FILES}}


def problems(frozen: dict) -> list[str]:
    out = []
    listed = frozen["files"]
    if sorted(listed) != sorted(FILES):
        out.append(
            f"the list of hashed files changed: only in freeze_heldout.json {sorted(set(listed) - set(FILES))}, "
            f"only in freeze_heldout.py {sorted(set(FILES) - set(listed))}"
        )
    for rel, digest in listed.items():
        path = REPO / rel
        if not path.exists():
            out.append(f"{rel} is missing")
        elif sha256(normalised(path)) != digest:
            out.append(f"{rel} differs from the freeze")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["write", "check"])
    args = parser.parse_args()
    if args.command == "write":
        FREEZE.write_text(json.dumps(current(), indent=1) + "\n", encoding="utf-8")
        print(f"wrote {FREEZE.relative_to(REPO)}")
        return
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    found = problems(frozen)
    if found:
        print("\n".join(found))
        raise SystemExit(1)
    print("freeze intact")


if __name__ == "__main__":
    main()
