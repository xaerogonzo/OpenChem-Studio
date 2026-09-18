"""Builds the HELD-OUT naming corpus. Run once; the result is committed.

**WHY THIS IS A SEPARATE FILE FROM `build_corpus.py`.** The regression corpus
is deliberately enriched with families the engine gets wrong -- that is what
makes it a good regression corpus and what makes it useless for measuring
whether the engine got better. A set chosen because it exposes today's bugs
cannot also be the evidence that tomorrow's fixes generalise.

**THE ENGINE IS NEVER IMPORTED HERE, AND THAT IS THE POINT.** Selection must
not be conditioned on what the namer does, and whoever wrote this script had
already seen the 60 disagreements that opened naming round 3 -- so their
judgement about "an interesting molecule" was contaminated before the first
line existed. The defence is to remove that judgement from the loop entirely:
the rule below picks the rows, and it was stated before any name was generated.

## The selection rule, declared in advance

    PubChem CIDs 1000 * k, for k = 1..120, in ascending order.

Nothing about the structures is chosen by hand. A stride over CID space is
arbitrary with respect to nomenclature difficulty, which is exactly the
property wanted.

## The admission filter, mechanical and in this order

A row is admitted only if all of these hold. Every clause is about the
structure or the availability of ground truth, never about naming:

 1. PubChem returns both a `SMILES` and a non-empty `IUPACName`.
 2. RDKit parses the SMILES.
 3. Single component -- no dot in the canonical SMILES -- because a salt or a
    mixture is a different naming problem and not one this engine claims.
 4. At least one carbon: this is an organic nomenclature engine.
 5. 6 <= heavy atoms <= 40. Below 6 the row is a smoke test; above 40 the
    naming cost stops being representative and the structure is usually a
    peptide or a natural product nobody names systematically.
 6. No explicit isotope label. Isotopes are in the regression corpus on
    purpose; admitting them here by accident would mix a known-weak family
    into the held-out measurement.
 7. The canonical SMILES does not already appear in `corpus.json`. The two
    populations must not overlap, or the held-out number is partly a
    restatement of the regression number.

Deliberately NOT filtered: element composition beyond "has carbon", charge,
ring count, stereochemistry. Narrowing those would be a judgement about which
chemistry is fair, and every such judgement is a way to smuggle the engine's
known weaknesses out of the sample.

## Ground truth

The PubChem string is kept only when OPSIN parses it back to the structure it
was fetched for -- the same gate `build_corpus._trusted_pubchem_name` applies,
for the same reason. OPSIN is a parser, not this project's namer, so using it
does not breach the "engine never imported" rule. A row that fails the gate is
still admitted, marked `UNTRUSTED`: it can never score exact, which costs
nothing, because the round trip is the real gate.

## Freezing

`--freeze` writes `heldout.meta.json`: the rule, the filter, the selection
timestamp and the sha256 of `heldout.json`. After that, a change to the row
set shows up as a hash mismatch rather than as a quiet improvement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

from rdkit import Chem

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

# `naming_providers` is imported for its OPSIN wrapper ONLY. It reaches the
# namer exclusively through a function-local import inside
# `derived_name_for_structure`, which is never called here.
from openchem.chem import naming_providers as n  # noqa: E402

# CIDs 1000, 2000, ... 120000.  See the module docstring: a stride over CID
# space, fixed before any naming.
CID_STRIDE = 1000
CID_COUNT = 120
TARGET_ROWS = 40

MIN_HEAVY_ATOMS = 6
MAX_HEAVY_ATOMS = 40

_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
# `SMILES` is the live isomeric property. `CanonicalSMILES` still resolves but
# now answers with `ConnectivitySMILES`, which has stereochemistry STRIPPED --
# measured 2026-09-17, and already recorded in `naming_providers`. Asking for
# the wrong one would silently build a stereo-free held-out set.
_PROPS = "SMILES,IUPACName"


def _fetch(cid: int) -> dict | None:
    url = f"{_BASE}/compound/cid/{cid}/property/{_PROPS}/JSON"
    request = urllib.request.Request(
        url, headers={"User-Agent": "OpenChemStudio/0.9 (naming benchmark)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001  network, 404, malformed -- all "skip"
        print(f"  cid {cid}: unavailable ({type(exc).__name__})")
        return None
    records = payload.get("PropertyTable", {}).get("Properties") or []
    return records[0] if records else None


def _admit(record: dict, already: set[str]) -> tuple[Chem.Mol | None, str]:
    """The filter, clause by clause.

    Returns `(mol, canonical_smiles)` on admission and `(None, reason)` on
    rejection, so the log says why every skipped CID was skipped.
    """
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
        return None, "already in the regression corpus"
    return mol, canonical


def _trusted(mol: Chem.Mol, name: str) -> bool:
    """Does OPSIN parse the PubChem string back to this structure?

    PubChem resolves a structure it does not hold to the nearest one it does,
    so an untested string can enshrine a different molecule as the reference.
    """
    try:
        parsed = n.opsin_structure_for_name(name)
    except Exception:  # noqa: BLE001
        return False
    back = Chem.MolFromSmiles(parsed.smiles)
    if back is None:
        return False
    return Chem.MolToSmiles(back) == Chem.MolToSmiles(mol)


def _has_stereo(mol: Chem.Mol) -> bool:
    if Chem.FindMolChiralCenters(mol, includeUnassigned=False):
        return True
    return any(
        bond.GetStereo() != Chem.BondStereo.STEREONONE for bond in mol.GetBonds()
    )


def build() -> list[dict]:
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    already = {row["smiles"] for row in corpus}
    print(f"{len(already)} structures in the regression corpus will be excluded\n")

    rows: list[dict] = []
    seen: set[str] = set()
    for k in range(1, CID_COUNT + 1):
        if len(rows) >= TARGET_ROWS:
            break
        cid = CID_STRIDE * k
        record = _fetch(cid)
        time.sleep(0.25)  # NCBI asks for no more than 5 requests/second
        if record is None:
            continue
        mol, verdict = _admit(record, already | seen)
        if mol is None:
            print(f"  cid {cid}: rejected -- {verdict}")
            continue
        canonical = verdict
        seen.add(canonical)
        name = record["IUPACName"].strip()
        trusted = _trusted(mol, name)
        kekule = None
        try:
            copy = Chem.Mol(mol)
            Chem.Kekulize(copy, clearAromaticFlags=True)
            kekule = Chem.MolToSmiles(copy, kekuleSmiles=True)
        except Exception:  # noqa: BLE001
            pass
        rows.append(
            {
                "label": f"cid{cid}",
                "category": "heldout",
                "smiles": canonical,
                "kekule_smiles": kekule,
                "has_stereo": _has_stereo(mol),
                "pubchem_name": name,
                "pubchem_cid": cid,
                "pubchem_retrieved": time.strftime("%Y-%m-%d"),
                "pubchem_name_kind": "PubChem IUPACName property",
                # TWO target-status fields, never one: a PubChem string can
                # exist and be untrusted while an adjudicated preferred name
                # exists, and one generic field cannot say that.
                # `preferred_target_status` stays ABSENT until a row is
                # adjudicated, which for a held-out row is recorded with its
                # own timestamp.
                "pubchem_target_status": "TRUSTED" if trusted else "UNTRUSTED",
                "preferred_target_status": "ABSENT",
                "preferred_name": None,
            }
        )
        flag = "ok " if trusted else "-- "
        print(f"  {flag}cid {cid}: {name[:70]}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the held-out naming corpus.")
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="write heldout.meta.json with the rule, the filter and the sha256",
    )
    args = parser.parse_args()

    rows = build()
    out = HERE / "heldout.json"
    payload = json.dumps(rows, indent=1)
    out.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    trusted = sum(1 for r in rows if r["pubchem_target_status"] == "TRUSTED")
    stereo = sum(1 for r in rows if r["has_stereo"])
    print(
        f"\n{len(rows)} held-out molecules | {trusted} with a trusted PubChem "
        f"target | {stereo} carrying stereochemistry"
    )
    print(f"sha256 {digest}")
    print(f"-> {out}")

    if args.freeze:
        import rdkit

        meta = {
            "artifact_schema_version": 1,
            "selection_rule": (
                f"PubChem CIDs {CID_STRIDE} * k for k = 1..{CID_COUNT}, ascending, "
                f"admitting the first {TARGET_ROWS} rows that pass the filter"
            ),
            "admission_filter": [
                "PubChem returns both SMILES and a non-empty IUPACName",
                "RDKit parses the SMILES",
                "single component (no '.')",
                "at least one carbon",
                f"{MIN_HEAVY_ATOMS} <= heavy atoms <= {MAX_HEAVY_ATOMS}",
                "no explicit isotope label",
                "canonical SMILES not already in corpus.json",
            ],
            "not_filtered": [
                "element composition beyond 'has carbon'",
                "charge",
                "ring count",
                "stereochemistry",
            ],
            "engine_consulted": False,
            "selection_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "rows": len(rows),
            "heldout_sha256": digest,
            "pubchem_property": _PROPS,
            "rdkit_version": rdkit.__version__,
        }
        meta_path = HERE / "heldout.meta.json"
        meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(f"-> {meta_path} (frozen)")


if __name__ == "__main__":
    main()
