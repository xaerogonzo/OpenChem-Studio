"""The freeze of the restart-v3 preregistration (`PREREGISTRATION.md` section 11): what is hashed, how, and the check.

    python freeze.py write      write freeze.json from the files as they are NOW (the freeze, or an amendment: see below)
    python freeze.py check      print every difference between the files and freeze.json

`freeze.json` holds the SHA-256 of each file that decides what an arm computes or how it is read, and of the preregistration's text as frozen. Hashes are taken over the file with its line endings normalised to LF, so a Windows checkout and a Linux one agree.
`tests/test_restart_v3_freeze.py` fails if any of them differs from freeze.json, if the frozen text of the preregistration is not still the START of the file, or if the number of `## Amendment` sections is not the number of amendments freeze.json lists.

CHANGING A FROZEN FILE IS AN AMENDMENT, never an edit: append a dated `## Amendment N` section to the preregistration that says what changed and why, change the file, run `freeze.py write --amend "one line"` in the same commit, and say so in the commit message. The preregistration's own earlier text is never edited (a typo is an amendment too); results already seen are not re-read under an amended rule.
Not hashed, on purpose: `LITERATURE_LOG.md`, `RESULT*.md`, `artifacts/` (data and write-ups, which follow the arms), and the tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FREEZE = HERE / "freeze.json"

#: Every file whose bytes decide what an arm computes or how its result is read.
FILES = [
    "benchmarks/restart_v3/restart_v3_core.py",
    "benchmarks/restart_v3/run_restart_v3.py",
    "benchmarks/restart_v3/thermal_step.py",
    "benchmarks/restart_v3/freeze.py",
    "benchmarks/restart_v3/references.json",
    "benchmarks/restart_v2/run_restart.py",
    "benchmarks/restart_v2/restart_core.py",
    "benchmarks/bde/run_bde.py",
    "benchmarks/bde/bde_core.py",
    "benchmarks/bde/judge.py",
    "benchmarks/proton_affinity/run_pa.py",
    "benchmarks/proton_affinity/pa_core.py",
    "benchmarks/bde_heldout/candidates_halogen.json",
]
PREREGISTRATION = "benchmarks/restart_v3/PREREGISTRATION.md"
AMENDMENT_HEADING = "\n## Amendment "


def normalised(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current() -> dict:
    prereg = normalised(REPO / PREREGISTRATION)
    return {"files": {rel: sha256(normalised(REPO / rel)) for rel in FILES}, "preregistration": {"bytes": len(prereg), "sha256": sha256(prereg)}}


def amendment_count(text: bytes) -> int:
    return text.decode("utf-8").count(AMENDMENT_HEADING)


def problems(frozen: dict) -> list[str]:
    """Every way the files differ from what freeze.json froze: empty when nothing has changed."""
    out = []
    listed = frozen["files"]
    if sorted(listed) != sorted(FILES):
        out.append(f"the list of hashed files changed: only in freeze.json {sorted(set(listed) - set(FILES))}, only in freeze.py {sorted(set(FILES) - set(listed))}")
    for rel, digest in listed.items():
        path = REPO / rel
        if not path.exists():
            out.append(f"{rel} is missing")
        elif sha256(normalised(path)) != digest:
            out.append(f"{rel} differs from the freeze")
    text = normalised(REPO / PREREGISTRATION)
    n = frozen["preregistration"]["bytes"]
    if len(text) < n or sha256(text[:n]) != frozen["preregistration"]["sha256"]:
        out.append("the frozen text of PREREGISTRATION.md is no longer the start of the file (only appended Amendment sections are allowed)")
    elif amendment_count(text) != len(frozen.get("amendments", [])):
        out.append(f"PREREGISTRATION.md has {amendment_count(text)} Amendment section(s) and freeze.json lists {len(frozen.get('amendments', []))}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["write", "check"])
    parser.add_argument("--amend", help="write: one line saying what this amendment changes (omit for the first freeze)")
    parser.add_argument("--date", default="2026-10-28")
    args = parser.parse_args()
    if args.command == "check":
        found = problems(json.loads(FREEZE.read_text(encoding="utf-8")))
        print("\n".join(found) if found else "nothing differs from the freeze")
        raise SystemExit(1 if found else 0)
    old = json.loads(FREEZE.read_text(encoding="utf-8")) if FREEZE.exists() else None
    now = current()
    amendments = list(old.get("amendments", [])) if old else []
    if old and not args.amend:
        raise SystemExit("freeze.json exists: a change to a frozen file is an amendment, so pass --amend 'what changed'")
    if args.amend:
        amendments.append({"date": args.date, "what": args.amend})
    if amendment_count(normalised(REPO / PREREGISTRATION)) != len(amendments):
        raise SystemExit(f"PREREGISTRATION.md has {amendment_count(normalised(REPO / PREREGISTRATION))} Amendment section(s) but {len(amendments)} would be listed: write the section first")
    frozen = {"frozen": old["frozen"] if old else args.date, "note": "see benchmarks/restart_v3/freeze.py and PREREGISTRATION.md section 11", **now, "amendments": amendments}
    FREEZE.write_text(json.dumps(frozen, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FREEZE.name}: {len(now['files'])} files, preregistration {now['preregistration']['bytes']} bytes, {len(amendments)} amendment(s)")


if __name__ == "__main__":
    main()
