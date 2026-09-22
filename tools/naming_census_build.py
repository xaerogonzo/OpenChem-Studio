"""Draws the naming round 9 B3 frequency census: an UNENRICHED PubChem-stride sample, used only to answer
"how common is this shape in ordinary chemistry", never to test the engine against a name.

**THE CENSUS IS NOT A POPULATION.** It is deliberately never registered in `benchmarks/naming/populations.toml`,
never read by `tools/naming_stage_artifact.py` or `tools/naming_probe.py`, and carries no target name at
all -- unlike `build_heldout.py`'s draws, which exist to be named and scored. Nothing here consults the
engine or OPSIN. `tests/test_naming_census_lock.py` source-scans the tracked tree and fails if any file
other than this one and `tools/naming_census_count.py` names `census_sample.json`.

## Use

    python tools/naming_census_build.py            # draw the sample (needs network, ~20-30 min)
    python tools/naming_census_build.py --freeze    # also write census_sample.meta.json

## Why offset 625

`build_heldout.py`'s six draws (naming rounds 4-9) already used offsets 0, 500, 250, 750, 125, 375 at the
same CID_STRIDE. 625 is the midpoint of the largest unused gap (500-750) and is disjoint from every one of
them by construction -- a different offset below the stride can never land on the same CID. The lock test
still measures CID, canonical-SMILES and row-identity overlap against EVERY registered population AND
against the B2 battery (`battery_r9.toml`), because "disjoint by construction" is a claim and a check is a
measurement, exactly as `tests/test_naming_heldout_lock.py` already treats its own offsets.

## Why no OPSIN, no trust check, no target name

`build_heldout.py`'s `_trusted()` exists because a held-out row needs a target the engine can be scored
against, and PubChem's computed name can enshrine a different structure than intended. The census never
scores anything against a name -- every row is used only as a structure for `census_queries.toml`'s SMARTS
(and Python predicates) to match against -- so there is nothing to trust and no reason to pay for ~2000
OPSIN calls and their JVM overhead. This tool needs no JRE.
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

from rdkit import Chem

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BENCH = ROOT / "benchmarks" / "naming"

OUT = BENCH / "census_sample.json"
META = BENCH / "census_sample.meta.json"

CID_STRIDE = 1000
OFFSET = 625            # disjoint by construction from build_heldout.py's 0, 500, 250, 750, 125, 375
CID_COUNT = 12000        # headroom; the loop stops as soon as TARGET_ROWS is admitted
TARGET_ROWS = 2000

MIN_HEAVY_ATOMS = 6      # same bounds as build_heldout.py's populations, for a comparable "ordinary
MAX_HEAVY_ATOMS = 40     # organic structure" definition

_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_PROPS = "SMILES,IUPACName"

#: Every file whose canonical SMILES the census must never repeat: the registered populations
#: (build_heldout.py's own draws, the corpus, the Blue Book halves) plus the B2 battery -- not a
#: registered population, but a set of rows this round has already scrutinised, so a repeat there
#: would not be a fresh, unenriched read of ordinary chemistry.
EXCLUDE_JSON = (
    "corpus.json", "heldout.json", "heldout2.json", "heldout3.json", "heldout4.json",
    "heldout5.json", "heldout6.json", "bluebook_tuning.json", "bluebook_frozen.json",
)
EXCLUDE_TOML = ("battery_r9.toml",)  # read as an array of [[row]] tables, not JSON


class ServerBusy(RuntimeError):
    """PubChem kept answering 503 after every retry."""


def _fetch(cid: int) -> dict | None:
    url = f"{_BASE}/compound/cid/{cid}/property/{_PROPS}/JSON"
    request = urllib.request.Request(url, headers={"User-Agent": "OpenChemStudio/0.9 (naming benchmark, B3 census)"})
    for attempt in range(7):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (503, 500):
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except Exception:  # noqa: BLE001 -- malformed or dropped: skip this CID
            return None
    else:
        raise ServerBusy(f"cid {cid}: PubChem still busy after 7 attempts")
    records = payload.get("PropertyTable", {}).get("Properties") or []
    return records[0] if records else None


def _admit(record: dict, already: set[str]) -> tuple[Chem.Mol | None, str]:
    """The same filter clauses build_heldout.py's `_admit` uses, minus the OPSIN trust check this tool
    has no use for. Returns (mol, canonical_smiles) on admission, (None, reason) on rejection."""
    smiles = record.get("SMILES")
    name = (record.get("IUPACName") or "").strip()
    if not smiles:
        return None, "no SMILES"
    if not name:
        return None, "no IUPACName"
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, "RDKit cannot parse it"
    canonical = Chem.MolToSmiles(mol)
    if "." in canonical:
        return None, "multi-component"
    if not any(atom.GetSymbol() == "C" for atom in mol.GetAtoms()):
        return None, "no carbon"
    heavy = mol.GetNumHeavyAtoms()
    if heavy < MIN_HEAVY_ATOMS or heavy > MAX_HEAVY_ATOMS:
        return None, f"{heavy} heavy atoms, outside {MIN_HEAVY_ATOMS}-{MAX_HEAVY_ATOMS}"
    if any(atom.GetIsotope() for atom in mol.GetAtoms()):
        return None, "carries an isotope label"
    if canonical in already:
        return None, "already in an excluded population or the B2 battery"
    return mol, canonical


def _excluded_smiles() -> set[str]:
    import tomllib

    already: set[str] = set()
    for name in EXCLUDE_JSON:
        path = BENCH / name
        if path.exists():
            already |= {row["smiles"] for row in json.loads(path.read_text(encoding="utf-8"))}
    for name in EXCLUDE_TOML:
        path = BENCH / name
        if path.exists():
            already |= {row["smiles"] for row in tomllib.loads(path.read_text(encoding="utf-8"))["row"]}
    return already


def build() -> list[dict]:
    already = _excluded_smiles()
    print(f"{len(already)} structures from {', '.join(EXCLUDE_JSON + EXCLUDE_TOML)} excluded\n", file=sys.stderr)

    rows: list[dict] = []
    seen: set[str] = set()
    rejected: dict[str, int] = {}
    for k in range(1, CID_COUNT + 1):
        if len(rows) >= TARGET_ROWS:
            break
        cid = CID_STRIDE * k + OFFSET
        record = _fetch(cid)
        time.sleep(0.25)  # NCBI asks for no more than 5 requests/second
        if record is None:
            continue
        mol, verdict = _admit(record, already | seen)
        if mol is None:
            clause = "heavy-atom range" if "heavy atoms" in verdict else verdict
            rejected[clause] = rejected.get(clause, 0) + 1
            continue
        canonical = verdict
        seen.add(canonical)
        rows.append(
            {
                "label": f"census{cid}",
                "smiles": canonical,
                "pubchem_cid": cid,
                "pubchem_name": record["IUPACName"].strip(),
            }
        )
        if len(rows) % 100 == 0:
            print(f"  ...{len(rows)}/{TARGET_ROWS} admitted (cid {cid}, {k}/{CID_COUNT} candidates tried)", file=sys.stderr, flush=True)
    print(f"admitted {len(rows)}; rejected by clause: {dict(sorted(rejected.items()))}", file=sys.stderr)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", action="store_true", help="also write census_sample.meta.json with the rule, the filter and the sha256")
    args = parser.parse_args()

    if OUT.exists():
        raise SystemExit(f"{OUT.name} exists; a drawn census is not re-run")

    rows = build()
    payload = json.dumps(rows, indent=1)
    payload_bytes = payload.encode("utf-8")
    # write_bytes, not write_text: Path.write_text() translates '\n' to the platform line separator
    # (CRLF on Windows), so the file on disk would no longer be the same bytes the digest below is taken
    # over. Measured 2026-09-22: the first real draw wrote CRLF and its own meta's census_sha256 did not
    # match the file it described -- caught by test_naming_census_lock.py's own hash check.
    OUT.write_bytes(payload_bytes)
    digest = hashlib.sha256(payload_bytes).hexdigest()

    print(f"\n{len(rows)} census structures")
    print(f"sha256 {digest}")
    print(f"-> {OUT}")

    if args.freeze:
        meta = {
            "artifact_schema_version": 1,
            "purpose": "B3 natural-frequency census -- structural shape counting only, NOT a naming population",
            "selection_rule": f"PubChem CIDs {CID_STRIDE} * k + {OFFSET} for k = 1..{CID_COUNT}, ascending, admitting the first {TARGET_ROWS} rows that pass the filter",
            "admission_filter": [
                "PubChem returns both SMILES and a non-empty IUPACName",
                "RDKit parses the SMILES",
                "single component (no '.')",
                "at least one carbon",
                f"{MIN_HEAVY_ATOMS} <= heavy atoms <= {MAX_HEAVY_ATOMS}",
                "no explicit isotope label",
                f"canonical SMILES not already in {', '.join(EXCLUDE_JSON + EXCLUDE_TOML)}",
            ],
            "not_filtered": ["element composition beyond 'has carbon'", "charge", "ring count", "stereochemistry"],
            "engine_consulted": False,
            "opsin_consulted": False,
            "selection_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "rows": len(rows),
            "census_sha256": digest,
            "cid_list": [row["pubchem_cid"] for row in rows],
        }
        META.write_bytes(json.dumps(meta, indent=1).encode("utf-8"))
        print(f"-> {META} (frozen)")


if __name__ == "__main__":
    main()
