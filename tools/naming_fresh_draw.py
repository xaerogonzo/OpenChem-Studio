"""Draws `fresh_v1`: a 2,000-row FROZEN naming population, to measure the engine on molecules nothing has been fixed against.

    python tools/naming_fresh_draw.py --cache <scratch>/fresh_raw.jsonl     # needs network, ~30 min; resumable
    python tools/naming_stage_artifact.py --stage <name> --final-evaluation --only fresh_v1    # the ONE scoring

**WHY IT EXISTS.** The frequency census (naming round 9) was drawn unenriched, but it has been read row by row since:
every round from 12 on took its targets from its failing rows, and the 98.35% it scores now is a number measured on a sample the
engine was fixed against. That is a tuning score. This is the other kind: a sample drawn BEFORE anything is known about it, scored
ONCE, in aggregate, and never opened row by row.

## Protocol (committed before the draw; nothing below may be changed after the sample exists)

* **Sample.** PubChem CIDs `1000 * k + 875`, k ascending, the first 2,000 that pass the census's own filter (`naming_census_build._admit`:
  SMILES and IUPACName present, parses, one component, has carbon, 6-40 heavy atoms, no isotope), minus every structure in a registered
  population, the B2 battery AND the census. 875 is the midpoint of the last free gap (750-1000) beside the used offsets 0, 500, 250,
  750, 125, 375 (held-out sets) and 625 (the census), so its CIDs are disjoint from all of them by construction; the lock tests measure it.
* **No trust filter.** Unlike `build_heldout.py`, a row is not required to have a PubChem name that parses back: that filter keeps only
  molecules PubChem and OPSIN already agree on, which are the easy ones. The score is the round trip, not agreement with a name.
* **The engine and OPSIN are not consulted** while drawing, and the progress output carries counts only.
* **Scoring.** Once, with the engine as it is when this lands (no naming round 38 change), by
  `naming_stage_artifact.py --final-evaluation --only fresh_v1`. Reported in AGGREGATE (outcome counts); the per-row records are sealed
  by hash beside the stage artifact and read by no tracked script. After that, only the blind `--frozen-impact` check may look at it again.
* **What it can claim.** The share of ordinary PubChem molecules (6-40 heavy atoms, one component) the engine names so that OPSIN reads the
  name back to the input. Not: that the names are the preferred ones (verbatim agreement with PubChem is reported, and is not that).
* **What happens next.** No fix is made to a row of this sample. It is spent as evaluation, never as tuning: when it is, a round says so in
  this file's meta and draws the next one.

**RATE LIMITS (measured 2026-10-10).** The first version asked for one CID per request at 4 a second, got about 400 answers, and was then
answered `429 Too Many Requests` for every request, including CIDs that had just worked. Worse, `naming_census_build._fetch` reads any
status but 500/503 as "no such compound", so every later candidate was recorded as absent and the draw would have gone on to select a
sample shaped by WHEN the throttle began. This tool asks for 100 CIDs per request (about 25 requests for the whole draw), waits out a 429
using `Retry-After` and backs off from there, and records a CID as absent ONLY when PubChem answered and did not have it (404, bisected so
one missing CID cannot blank its neighbours). If throttling persists it stops with a resumable error rather than carry on.

Resumable because a long draw must not be lost to one busy server: `--cache` is a JSONL of the RAW PubChem answers by CID. Selection
is a pure function of those answers in CID order, so resuming from a cache selects exactly what an uninterrupted run would.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import naming_census_build as census  # noqa: E402
import naming_census_scan as census_scan  # noqa: E402
import naming_populations as registry  # noqa: E402

BENCH = ROOT / "benchmarks" / "naming"
OUT = BENCH / "fresh_v1.json"
META = BENCH / "fresh_v1.meta.json"

CID_STRIDE = census.CID_STRIDE
OFFSET = 875
CID_COUNT = 12000
TARGET_ROWS = 2000
BATCH = 100           # CIDs per request: the whole draw is about 25 requests, far under NCBI's 5 a second and 400 a minute
PAUSE_SECONDS = 3.0   # between requests, because the limit that bit was not the one the documentation states
ATTEMPTS = 6
_RETRYABLE = (429, 500, 502, 503, 504)


def fetch_batch(cids: list[int], *, urlopen=urllib.request.urlopen, sleep=time.sleep) -> dict[int, dict | None]:
    """`{cid: PubChem's record, or None if PubChem answered and does not have it}`.

    A CID is None ONLY on an answer: a 200 that omits it, or a 404 for that CID alone (a 404 for several is bisected, since PubChem may
    answer 404 for a whole list in which none, or only some, exist). A throttle (429) or a server error is waited out and retried, never
    read as absence; after `ATTEMPTS` it raises `ServerBusy` and the cache keeps what was already got.
    """
    url = f"{census._BASE}/compound/cid/{','.join(str(c) for c in cids)}/property/{census._PROPS}/JSON"
    request = urllib.request.Request(url, headers={"User-Agent": "OpenChemStudio/0.9 (naming benchmark, fresh_v1 draw)"})
    for attempt in range(ATTEMPTS):
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            found = {p["CID"]: p for p in payload.get("PropertyTable", {}).get("Properties") or []}
            return {cid: found.get(cid) for cid in cids}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                if len(cids) == 1:
                    return {cids[0]: None}
                middle = len(cids) // 2
                return {**fetch_batch(cids[:middle], urlopen=urlopen, sleep=sleep), **fetch_batch(cids[middle:], urlopen=urlopen, sleep=sleep)}
            if exc.code not in _RETRYABLE:
                raise
            wait = int(exc.headers.get("Retry-After") or 0) if exc.headers else 0
            print(f"  HTTP {exc.code}; waiting {wait or 60 * 2 ** attempt} s (attempt {attempt + 1}/{ATTEMPTS})", file=sys.stderr, flush=True)
            sleep(wait or 60 * 2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"  {type(exc).__name__}; retrying (attempt {attempt + 1}/{ATTEMPTS})", file=sys.stderr, flush=True)
            sleep(30 * (attempt + 1))
    raise census.ServerBusy(f"PubChem still throttling or busy after {ATTEMPTS} attempts (first CID {cids[0]})")


def _excluded() -> set[str]:
    """Every structure the sample must not repeat: the registered populations and the battery, and the census."""
    from rdkit import Chem

    already = census._excluded_smiles()
    already |= {Chem.MolToSmiles(Chem.MolFromSmiles(row["smiles"])) for row in census_scan.load_sample()}
    return already


def _load_cache(path: Path | None) -> dict[int, dict | None]:
    cache: dict[int, dict | None] = {}
    if path is not None and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                cache[entry["cid"]] = entry["record"]
    return cache


def draw(cache_path: Path | None, *, fetch=fetch_batch, sleep=time.sleep) -> list[dict]:
    """The sample, from PubChem (or the cache of raw answers). `fetch` and `sleep` are parameters so a test can run the selection offline.

    `fetch(cids)` answers a list at once. Candidates are fetched a block at a time, in CID order, and every answer is cached as it arrives.
    """
    already = _excluded()
    print(f"{len(already)} structures excluded (registered populations, the B2 battery, the census)", file=sys.stderr)
    cache = _load_cache(cache_path)
    if cache:
        print(f"{len(cache)} raw answers already cached", file=sys.stderr)

    rows: list[dict] = []
    seen: set[str] = set()
    rejected: dict[str, int] = {}
    handle = cache_path.open("a", encoding="utf-8") if cache_path is not None else None
    try:
        for k in range(1, CID_COUNT + 1):
            if len(rows) >= TARGET_ROWS:
                break
            cid = CID_STRIDE * k + OFFSET
            if cid not in cache:
                block = [CID_STRIDE * j + OFFSET for j in range(k, min(k + BATCH, CID_COUNT + 1))]
                block = [c for c in block if c not in cache]
                for got_cid, got in fetch(block).items():
                    cache[got_cid] = got
                    if handle is not None:
                        handle.write(json.dumps({"cid": got_cid, "record": got}) + "\n")
                if handle is not None:
                    handle.flush()
                sleep(PAUSE_SECONDS)
            record = cache[cid]
            if record is None:
                continue
            mol, verdict = census._admit(record, already | seen)
            if mol is None:
                clause = "heavy-atom range" if "heavy atoms" in verdict else verdict
                rejected[clause] = rejected.get(clause, 0) + 1
                continue
            seen.add(verdict)
            rows.append({"label": f"fresh{cid}", "smiles": verdict, "pubchem_cid": cid, "pubchem_name": record["IUPACName"].strip()})
            if len(rows) % 100 == 0:
                print(f"  ...{len(rows)}/{TARGET_ROWS} admitted ({k}/{CID_COUNT} candidates tried)", file=sys.stderr, flush=True)
    finally:
        if handle is not None:
            handle.close()
    print(f"admitted {len(rows)}; rejected by clause: {dict(sorted(rejected.items()))}", file=sys.stderr)
    return rows


def meta_for(rows: list[dict], digest: str) -> dict:
    from rdkit import rdBase

    return {
        "artifact_schema_version": 1,
        "variant": "fresh_v1",
        "purpose": "a frozen, scored-once measurement of the engine on unenriched PubChem molecules; see the docstring of tools/naming_fresh_draw.py",
        "selection_rule": f"PubChem CIDs {CID_STRIDE} * k + {OFFSET} for k = 1..{CID_COUNT}, ascending, admitting the first {TARGET_ROWS} rows that pass the filter",
        "admission_filter": [
            "PubChem returns both SMILES and a non-empty IUPACName",
            "RDKit parses the SMILES",
            "single component (no '.')",
            "at least one carbon",
            f"{census.MIN_HEAVY_ATOMS} <= heavy atoms <= {census.MAX_HEAVY_ATOMS}",
            "no explicit isotope label",
            "canonical SMILES not in any registered population, the B2 battery, or the census",
        ],
        "not_filtered": ["element composition beyond 'has carbon'", "charge", "ring count", "stereochemistry",
                         "whether PubChem's name parses back (no trust filter)"],
        "engine_consulted": False,
        "opsin_consulted": False,
        "selection_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rows": len(rows),
        "heldout_sha256": digest,  # the key naming_stage_artifact reads for a frozen population; the name is historical
        "membership_salt": registry.MEMBERSHIP_SALT,
        "membership_sha256": registry.membership_hashes(rows),
        "pubchem_property": census._PROPS,
        "rdkit_version": rdBase.rdkitVersion,
        "inspection_policy": "evaluation only: drawn before anything was known about it, scored once by naming_stage_artifact.py "
                             "--final-evaluation --only fresh_v1 as aggregates, never inspected row by row",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, help="JSONL of the raw PubChem answers by CID; makes the draw resumable")
    args = parser.parse_args()
    if OUT.exists():
        raise SystemExit(f"{OUT.name} exists; a drawn population is not re-run")
    try:
        rows = draw(args.cache)
    except census.ServerBusy as exc:
        raise SystemExit(f"{exc}\nNothing was lost: re-run with the same --cache to resume.")
    if len(rows) < TARGET_ROWS:
        raise SystemExit(f"only {len(rows)} of {TARGET_ROWS} rows admitted; not writing a short population")
    # write_bytes, not write_text: the digest is over exactly these bytes (see naming_census_build.py for the CRLF lesson).
    payload = json.dumps(rows, indent=1).encode("utf-8")
    OUT.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    META.write_bytes(json.dumps(meta_for(rows, digest), indent=1).encode("utf-8"))
    print(f"{len(rows)} rows, sha256 {digest}\n-> {OUT.name}, {META.name}")


if __name__ == "__main__":
    main()
