"""Downloads the deposits and RCSB's own generated assemblies.

Split out from building and scoring because it is the only step that
touches the network, and because WHAT WAS DOWNLOADED IS PART OF THE
RESULT. RCSB regenerates assembly files when a deposit is revised, so a
gate that silently re-fetches could start passing or failing for reasons
nothing in this repository changed. Every file's sha256, size and fetch
date go into `sources.json`, which IS committed; a later fetch that finds
different bytes says so instead of overwriting the record.

The cached structures themselves are NOT committed -- 10 files and 40 MB,
24 MB of it 1A34's 208,440-atom assembly alone, all re-fetchable from a
stable public URL.

Usage:
    python fetch.py            # fetch anything missing
    python fetch.py --recheck  # re-fetch and compare against sources.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
SOURCES = HERE / "sources.json"

#: Long enough for a 3 MB assembly file on a slow link, short enough that
#: a hung mirror fails the run rather than the day.
_TIMEOUT = 120


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:
        return response.read()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _wanted(corpus: dict) -> list[tuple[str, str]]:
    """(filename, url) for everything the gate needs."""
    template = corpus["reference"]["url_template"]
    out = []
    for entry in corpus["structures"]:
        pdb_id, assembly_id = entry["pdb_id"], entry["assembly_id"]
        out.append((f"{pdb_id}.pdb", f"https://files.rcsb.org/download/{pdb_id}.pdb"))
        out.append(
            (
                f"{pdb_id}-assembly{assembly_id}.cif",
                template.format(pdb_id=pdb_id, assembly_id=assembly_id),
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="re-fetch every file and report any whose bytes have changed",
    )
    args = parser.parse_args()

    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    CACHE.mkdir(exist_ok=True)
    recorded = (
        json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {}
    )

    changed = []
    for name, url in _wanted(corpus):
        path = CACHE / name
        if path.exists() and not args.recheck:
            print(f"  cached  {name}")
            continue
        try:
            payload = _download(url)
        except Exception as exc:  # noqa: BLE001 - the URL is the diagnosis
            print(f"  FAILED  {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        digest = _digest(payload)
        previous = recorded.get(name, {}).get("sha256")
        if previous and previous != digest:
            # Not an error: RCSB revises deposits. But it means any
            # result recorded against the old bytes describes a different
            # file, and that must be said out loud rather than absorbed.
            changed.append(name)
            print(f"  CHANGED {name}  {previous[:12]} -> {digest[:12]}")
        else:
            print(f"  fetched {name}  {len(payload) // 1024:,} kB")
        path.write_bytes(payload)
        recorded[name] = {
            "url": url,
            "sha256": digest,
            "bytes": len(payload),
            "fetched": date.today().isoformat(),
        }

    SOURCES.write_text(json.dumps(recorded, indent=1, sort_keys=True), encoding="utf-8")
    if changed:
        print(f"\n{len(changed)} file(s) changed upstream: {', '.join(changed)}")
        print("Re-score before trusting any previously recorded result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
