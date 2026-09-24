"""Check the energetics literature manifest against the local PDF library, and count it.

`docs/research/literature.toml` records, for each paper the thermophysical / density / enthalpy /
detonation survey reads, what the paper PRINTS about itself, what we ASSIGN it, whether the file is
held, and a sha256 of the file that was read. This tool answers two questions and nothing else:

    --check    is each held file still the file that was identified?   (sha256, one per held entry)
    --counts   how many entries are in each access state, property and role?

**COUNTS ARE GENERATED, NEVER TYPED.** Every number a document quotes about the literature comes from
`--counts`, because a hand-typed "37 papers" is what rots the moment one is added. The tests forbid the
README from quoting one.

**IT CHECKS ARTIFACT INTEGRITY, NOT SCIENTIFIC CORRECTNESS**, the same line `index_pdf_library.py` draws.
A matching hash says the file has not changed since somebody read its first page; it says nothing about
whether the paper supports a claim. The identity itself -- DOI, title, venue -- was established by reading
each file's own first page (`printed.*`), which no tool here repeats, because a DOI is often not printed in
a paper at all (measured on the sources registry: the declared DOI appears in the file for 24 of 44).

**A MACHINE WITH NO LIBRARY SKIPS, LOUDLY.** `--check` returns 0 and says it skipped when
`OPENCHEM_PDF_LIBRARY` is unset, so CI and every contributor who is not the maintainer are not failed by a
folder they do not have.

    OPENCHEM_PDF_LIBRARY="D:/Xaero Stuff/Documents/Sci Downloads" python tools/index_literature.py --check
    python tools/index_literature.py --counts
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The manifest this tool reads.
MANIFEST = ROOT / "docs" / "research" / "literature.toml"

#: Access states. **AN ACCESS STATE IS NOT A VERDICT**: a paper that is only requested, or held only as
#: an accepted manuscript, has not been rejected -- there is deliberately no "rejected" here. A rejection is
#: a scientific decision recorded elsewhere, with a reason; a paywall is never one.
ACCESS_STATES = frozenset({
    "held",                      # the version of record, read
    "held_accepted_manuscript",   # an accepted manuscript, not the version of record
    "held_preproof",              # a journal pre-proof, not the version of record
    "held_si_only",               # the supplement is held, the article is not
    "not_held",                   # not held; where it can be fetched is in the note
    "requested",                  # asked of the authors; a date is recorded
})

#: The states in which a file is held, and so carries a `file`, a `sha256` and a page count.
HELD_STATES = frozenset({"held", "held_accepted_manuscript", "held_preproof"})

#: What a paper is about. OUR classification (`assigned.property`), never the paper's.
PROPERTIES = frozenset({
    "thermophysical", "density", "enthalpy_gas", "enthalpy_sublimation", "enthalpy_solid",
    "enthalpy_fusion", "detonation", "sensitivity", "data_compendium", "ml_general",
})

#: What we use a paper for. OUR classification (`assigned.role`).
ROLES = frozenset({
    "candidate_method", "data_layer", "equation_source", "benchmark_reference", "review", "context_only",
})


def _load_sibling(name: str):
    """Import a sibling tool by path; `tools/` is not a package, so tests cannot import it by name."""
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    return tomllib.loads(path.read_text(encoding="utf-8"))["source"]


def check(library: Path | None, entries: list[dict]) -> int:
    """0 when every held file is the one that was read (or there is no library to say otherwise)."""
    if library is None:
        print(
            "SKIPPED: no PDF library here (set OPENCHEM_PDF_LIBRARY). Nothing was checked, "
            "which is not the same as everything being fine."
        )
        return 0
    held = [e for e in entries if e["access"] in HELD_STATES]
    problems = []
    for entry in held:
        path = library / entry["file"]
        if not path.is_file():
            problems.append(f"{entry['id']}: {entry['file']} is not in the library")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"{entry['id']}: {entry['file']} is not the file that was identified (sha256 differs)")
    for line in problems:
        print("MISMATCH:", line)
    print(f"checked {len(held)} held files: {len(problems)} problem(s)")
    return 1 if problems else 0


def counts(entries: list[dict]) -> dict[str, dict[str, int]]:
    """The numbers any document may quote about the literature."""
    return {
        "entries": {"total": len(entries)},
        "access": dict(Counter(e["access"] for e in entries)),
        "property": dict(Counter(e["assigned"]["property"] for e in entries)),
        "role": dict(Counter(e["assigned"]["role"] for e in entries)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="verify held files against their sha256")
    parser.add_argument("--counts", action="store_true", help="print generated counts")
    args = parser.parse_args(argv)
    entries = load_manifest()
    status = 0
    if args.counts or not args.check:
        for group, values in counts(entries).items():
            print(f"{group}: " + ", ".join(f"{k}={v}" for k, v in sorted(values.items())))
    if args.check:
        library = _load_sibling("index_pdf_library").library_path()
        status = check(library, entries)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
