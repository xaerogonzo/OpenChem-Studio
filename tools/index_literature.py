"""Check the energetics literature manifest against the local PDF library, and count it.

`docs/research/literature.toml` records, for each paper the thermophysical / density / enthalpy /
detonation survey reads, what the paper PRINTS about itself, what we ASSIGN it, whether the file is
held, and a sha256 of the file that was read. This tool answers two questions and nothing else:

    --check    is each held file still the file that was identified?   (sha256, one per held entry)
    --counts   how many entries are in each access state, property and role?
    --link-kv  which Knowledge Vista document is each held file?       (proposes `kv_document_id`; `--write` records it)

**COUNTS ARE GENERATED, NEVER TYPED.** Every number a document quotes about the literature comes from
`--counts`, because a hand-typed "37 papers" is what rots the moment one is added. The tests forbid the
README from quoting one.

**IT CHECKS ARTIFACT INTEGRITY, NOT SCIENTIFIC CORRECTNESS**, the same line `index_pdf_library.py` draws.
A matching hash says the file has not changed since somebody read its first page; it says nothing about
whether the paper supports a claim. The identity itself -- DOI, title, venue -- was established by reading
each file's own first page (`printed.*`), which no tool here repeats, because a DOI is often not printed in
a paper at all (measured on the sources registry: the declared DOI appears in the file for 24 of 44).

**A RENAMED FILE IS NOT A CHANGED FILE.** `file` is a locator in the maintainer's library and drifts the moment a PDF is renamed or
moved. When the recorded name is gone and Knowledge Vista (`kv`, a separate program; see docs/research/README.md) is installed, the tool
asks it where the bytes with that sha256 are now -- and then **hashes that path itself**, because KV answers from a catalog that may be
a day stale. A file found that way is reported as `MOVED` and is not a problem; the identified bytes are still held, only the locator is
old. A file that is genuinely gone, or genuinely different, is still a problem. KV absent, unreachable, slow, or speaking a protocol this
tool was not taught changes nothing about what is checked: it is reported once and the check proceeds as it always did.

**A MACHINE WITH NO LIBRARY SKIPS, LOUDLY.** `--check` returns 0 and says it skipped when
`OPENCHEM_PDF_LIBRARY` is unset, so CI and every contributor who is not the maintainer are not failed by a
folder they do not have.

    OPENCHEM_PDF_LIBRARY="D:/Xaero Stuff/Documents/Sci Downloads" python tools/index_literature.py --check
    python tools/index_literature.py --counts
    python tools/index_literature.py --link-kv            # dry run: the `kv_document_id` lines it would add
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import tomllib
from collections import Counter
from collections.abc import Callable
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
    "enthalpy_fusion", "detonation", "sensitivity", "data_compendium", "ml_general", "solubility", "tautomerism",
})

#: What we use a paper for. OUR classification (`assigned.role`).
ROLES = frozenset({
    "candidate_method", "data_layer", "equation_source", "benchmark_reference", "review", "context_only",
})


def _load_sibling(name: str):
    """Import a sibling tool by path; `tools/` is not a package, so tests cannot import it by name."""
    path = Path(__file__).with_name(f"{name}.py")
    cached = sys.modules.get(name)
    if cached is not None and getattr(cached, "__file__", None) == str(path):
        return cached  # ONE module object per sibling: an exception class compared across two loads is two classes
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    return tomllib.loads(path.read_text(encoding="utf-8"))["source"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _found_elsewhere(entry: dict, locate: Callable | None, said: set[str]) -> tuple[Path | None, str | None]:
    """Where Knowledge Vista says this entry's bytes are now, VERIFIED by hashing that path here; else (None, why not).

    `locate` is `kv_client.locate_sha256` or None. KV's answer is a lead: the path it names is read and hashed, so a stale catalog
    can cost a missed lead but can never make a wrong file pass.
    """
    if locate is None:
        return None, None
    kv = _load_sibling("kv_client")
    try:
        located = locate(entry["sha256"])
    except kv.KvUnavailable as exc:
        reason = f"Knowledge Vista could not be asked ({exc})"
        if reason not in said and kv.configured():  # an installed-but-unset KV is silent: absence is the normal case
            said.add(reason)
            print("NOTE:", reason)
        return None, reason if kv.configured() else None
    if located is None:
        return None, "Knowledge Vista has never seen these bytes"
    for candidate in located.paths:
        path = Path(candidate)
        if path.is_file() and _sha256(path) == entry["sha256"]:
            return path, None
    if located.paths:
        return None, "Knowledge Vista names a path, but it does not hold these bytes (its catalog is out of date: run `kv scan`)"
    return None, f"Knowledge Vista knows these bytes ({located.status}) but no copy is reachable (if the file was renamed since its last scan, run `kv scan`)"


def check(library: Path | None, entries: list[dict], locate: Callable | None = None) -> int:
    """0 when every held file is the one that was read (or there is no library to say otherwise).

    A file that is not at its recorded name is looked for by `locate` (Knowledge Vista, by sha256) and counts as present if the bytes
    are found and verified; see the module docstring."""
    if library is None:
        print(
            "SKIPPED: no PDF library here (set OPENCHEM_PDF_LIBRARY). Nothing was checked, "
            "which is not the same as everything being fine."
        )
        return 0
    held = [e for e in entries if e["access"] in HELD_STATES]
    problems, moved, said = [], [], set()
    for entry in held:
        path = library / entry["file"]
        if path.is_file() and _sha256(path) == entry["sha256"]:
            continue
        what = "is not in the library" if not path.is_file() else "is not the file that was identified (sha256 differs)"
        there, why = _found_elsewhere(entry, locate, said)
        if there is not None:
            moved.append(f"{entry['id']}: {entry['file']} {what}; the identified file is now {there}")
        else:
            problems.append(f"{entry['id']}: {entry['file']} {what}" + (f"; {why}" if why else ""))
    for line in moved:
        print("MOVED:", line)
    for line in problems:
        print("MISMATCH:", line)
    print(f"checked {len(held)} held files: {len(problems)} problem(s)" + (f", {len(moved)} found elsewhere by Knowledge Vista (the recorded `file` is stale)" if moved else ""))
    return 1 if problems else 0


_BLOCK_START = re.compile(r"^\[\[source\]\]\s*$")


def link_kv(entries: list[dict], locate: Callable, write: bool, manifest: Path = MANIFEST) -> int:
    """Propose (or, with `write`, record) `kv_document_id` for held entries that lack one. Never guesses: an entry is linked only when
    Knowledge Vista has the entry's exact bytes under a document, and the path it names hashes to the entry's sha256 -- the same
    verification `--check` makes."""
    kv = _load_sibling("kv_client")
    proposals: list[tuple[str, str, str]] = []
    skipped = 0
    for entry in (e for e in entries if e["access"] in HELD_STATES and not e.get("kv_document_id")):
        try:
            located = locate(entry["sha256"])
        except kv.KvUnavailable as exc:
            print(f"STOPPED: Knowledge Vista could not be asked ({exc})")
            return 1
        verified = located is not None and located.document_id and any(Path(c).is_file() and _sha256(Path(c)) == entry["sha256"] for c in located.paths)
        if verified:
            proposals.append((entry["id"], entry["sha256"], located.document_id))
        else:
            skipped += 1
    for entry_id, _, document_id in proposals:
        print(f"LINK: {entry_id}  kv_document_id = \"{document_id}\"")
    print(f"{len(proposals)} entr{'y' if len(proposals) == 1 else 'ies'} can be linked; {skipped} not (Knowledge Vista does not have the verified bytes)")
    if write and proposals:
        text = manifest.read_bytes().decode()
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.replace("\r\n", "\n").split("\n")
        for entry_id, sha, document_id in proposals:
            start = next(i for i, line in enumerate(lines) if line.strip() == f'id = "{entry_id}"')
            at = next(i for i in range(start, len(lines)) if lines[i].startswith(f'sha256 = "{sha}"'))
            if any(_BLOCK_START.match(line) for line in lines[start:at]):
                raise SystemExit(f"{entry_id}: its sha256 line is not in its own block; refusing to edit")
            lines.insert(at + 1, f'kv_document_id = "{document_id}"')
        manifest.write_bytes(newline.join(lines).encode())
        print(f"wrote {len(proposals)} line(s) to {manifest.name}")
    elif proposals:
        print("(dry run: add --write to record them)")
    return 0


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
    parser.add_argument("--no-kv", action="store_true", help="with --check: do not ask Knowledge Vista where a missing file went")
    parser.add_argument("--link-kv", action="store_true", help="propose kv_document_id for held entries (dry run unless --write)")
    parser.add_argument("--write", action="store_true", help="with --link-kv: record the proposals in the manifest")
    args = parser.parse_args(argv)
    entries = load_manifest()
    status = 0
    if args.counts or not (args.check or args.link_kv):
        for group, values in counts(entries).items():
            print(f"{group}: " + ", ".join(f"{k}={v}" for k, v in sorted(values.items())))
    if args.check:
        library = _load_sibling("index_pdf_library").library_path()
        locate = None
        if not args.no_kv:
            kv = _load_sibling("kv_client")
            locate = kv.locate_sha256 if kv.command() is not None else None
        status = check(library, entries, locate)
    if args.link_kv:
        kv = _load_sibling("kv_client")
        if kv.command() is None:
            print("SKIPPED: Knowledge Vista (`kv`) was not found: install it, or set OPENCHEM_KV to its path.")
        else:
            status = link_kv(entries, kv.locate_sha256, args.write) or status
    return status


if __name__ == "__main__":
    raise SystemExit(main())
