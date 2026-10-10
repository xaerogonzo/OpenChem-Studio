"""Name EVERY row of the frozen census sample and read each name back: the true remaining failure rate.

    python tools/naming_census_scan.py                          # summary of all 2000 rows
    python tools/naming_census_scan.py --out scan.json          # also one record per row
    python tools/naming_census_scan.py --list mismatch_formula  # print the rows of one class
    python tools/naming_census_scan.py --compare old_scan.json  # what moved since a previous scan
    python tools/naming_census_scan.py --names-only             # skip the OPSIN read-back (no JRE needed)

**WHY IT EXISTS.** Rounds 9-12 fixed shapes that EARLIER backlogs had named, and each fix was small.
`naming_census_count.py` can only count a shape someone already wrote a query for. Naming round 13's
prelude ran the engine over the whole sample instead and found, in one pass, the largest wrong-molecule
cluster in the census (a 1,3,4-oxadiazol/thiadiazol-*3*-yl locant on 21 of 25 such names, 1.05%), which no
backlog row mentioned and which had been there since round 6. A backlog names what somebody saw; a scan
measures what is there. Run it at the START of a round to choose targets, and again at the end.

**THE CLASSES** (each row lands in exactly one):

    exact                   the name reads back to the input, stereo included (InChIKey)
    same_connectivity       reads back to the same connectivity, differing in stereo / tautomer / indicated H
                            -- NOT triaged: read a few before calling any of these correct
    mismatch_formula        reads back to a structure with a DIFFERENT molecular formula: a wrong molecule
    mismatch_same_formula   reads back to a different structure of the same formula (a wrong locant, most often)
    unparsable              OPSIN cannot read the name
    naming_error            the engine emitted an embedded `[NAMING ERROR: ...]` (a VISIBLE failure); the
                            message stem is clustered in the summary
    refused                 the engine raised (the refusal guard); never a wrong molecule

**WHAT IT DOES NOT SAY.** OPSIN is the oracle, and it is not always right: it reads an anion name such as
`...sulfonamidate` as the neutral acid, so a mismatch is a CANDIDATE defect, and the summary says so. The
`same_connectivity` class is the least examined and the most likely to hide a real problem.

**IT NAMES CANONICAL SMILES**, which is what the application names, so a row's name here is its name in the
app. The sample is checked against `census_sample.meta.json`'s hash before anything runs. The census is NOT a
frozen naming population (its meta says `engine_consulted: false`), so reading its rows here is allowed.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import re
import shutil
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
CENSUS = BENCH / "census_sample.json"
META = BENCH / "census_sample.meta.json"

sys.path.insert(0, str(ROOT / "src"))

#: The order the summary prints them in; the failures a round can act on first.
CLASSES = (
    "exact",
    "same_connectivity",
    "mismatch_formula",
    "mismatch_same_formula",
    "unparsable",
    "naming_error",
    "refused",
)

_ERROR_STEM = re.compile(r"\[NAMING ERROR: (.{0,110})")
_LONG_TOKEN = re.compile(r"\S{25,}")
_DIGITS = re.compile(r"\d+")
_BATCH = 100


def load_sample() -> list[dict]:
    """The census rows, refused if the file is not the one the meta hashes."""
    # Over LF text, because that is what the draw hashed and what git stores: this repo's Windows working copy is CRLF
    # (core.autocrlf), and hashing it raw would read as tampering (tests/test_naming_census_lock.py says the same).
    raw = CENSUS.read_bytes().replace(b"\r\n", b"\n")
    want = json.loads(META.read_text(encoding="utf-8"))["census_sha256"]
    if hashlib.sha256(raw).hexdigest() != want:
        raise SystemExit("census_sample.json does not match census_sample.meta.json's hash; refusing to scan a different sample")
    return json.loads(raw)


@contextlib.contextmanager
def _engine_logging_silenced():
    """Silence RDKit and `logging` for the length of a scan, then put both back.

    This used to switch them off and leave them off. It is called in-process by tests, so every later
    test in the same pytest run lost its WARNING records, and the calculator census (which counts
    them) read "w" cells as "c" -- but only when the two files shared a process, which CI's shards do not.
    """
    import logging

    from rdkit import RDLogger, rdBase

    status = dict(line.split(":") for line in rdBase.LogStatus().splitlines())
    was_disabled = logging.root.manager.disable
    RDLogger.DisableLog("rdApp.*")
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(was_disabled)
        for channel, state in status.items():
            (RDLogger.EnableLog if state == "enabled" else RDLogger.DisableLog)(channel)


def name_rows(rows: list[dict]) -> dict[str, dict]:
    """`{label: {smiles, name}}` with the engine's own refusal recorded as a name, never raised."""
    from rdkit import Chem

    out: dict[str, dict] = {}
    with _engine_logging_silenced():
        from openchem.vendor.iupac_namer import name_smiles

        for row in rows:
            smiles = Chem.MolToSmiles(Chem.MolFromSmiles(row["smiles"]))
            try:
                name = name_smiles(smiles)
            except Exception as exc:  # noqa: BLE001 - the refusal guard raises ValueError on purpose
                name = f"RAISED: {type(exc).__name__}: {str(exc)[:100]}"
            out[row["label"]] = {"smiles": smiles, "name": name}
    return out


def read_back(names: list[str]) -> list[str]:
    """OPSIN's SMILES for each name ('' where it cannot read one), in batches."""
    from py2opsin import py2opsin

    back: list[str] = []
    for i in range(0, len(names), _BATCH):
        batch = names[i:i + _BATCH]
        got = py2opsin(batch, output_format="SMILES") if len(batch) > 1 else [py2opsin(batch[0], output_format="SMILES")]
        back.extend(g or "" for g in got)
    return back


def _key(smiles: str) -> str | None:
    from rdkit import Chem
    from rdkit.Chem import inchi

    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return None
    try:
        return inchi.MolToInchiKey(mol)
    except Exception:  # noqa: BLE001
        return None


def _formula(smiles: str) -> str | None:
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula

    mol = Chem.MolFromSmiles(smiles) if smiles else None
    return CalcMolFormula(mol) if mol is not None else None


def classify(smiles: str, name: str, back: str | None) -> str:
    """One class for one row. `back` is None when the read-back was skipped (a name that failed is still classified)."""
    if name.startswith("RAISED"):
        return "refused"
    if "NAMING ERROR" in name:
        return "naming_error"
    if back is None:
        return "exact"  # only reachable with --names-only; the summary says the read-back was skipped
    if not back:
        return "unparsable"
    want, got = _key(smiles), _key(back)
    if want and want == got:
        return "exact"
    if want and got and want.split("-")[0] == got.split("-")[0]:
        return "same_connectivity"
    return "mismatch_formula" if _formula(smiles) != _formula(back) else "mismatch_same_formula"


#: What `delta` can say, in the order it is decided. A wrong-molecule row gets every label that applies, most specific first, and the
#: FIRST is the one `summarise` groups by. The two heteroatom labels carry the elements (`heteroatom_dropped:N`), because "an N went
#: missing" and "an O went missing" are different defects to chase.
DELTA_LABELS = (
    "charge_lost",
    "charge_changed",
    "heteroatom_dropped",
    "heteroatom_gained",
    "ring_atom_count_changed",
    "same_formula_connectivity_change",
    "other_formula_change",
)
#: The bucket for a record scanned before `delta` existed (r12-r14 scans): not invented, and not an error.
LEGACY_DELTA = "legacy/unknown"


def _delta_facts(mol) -> tuple[int, int, dict[str, int], int]:
    """(net charge, total |charge|, element counts excluding C and H, atoms that are in any ring)."""
    elements: collections.Counter = collections.Counter(
        a.GetSymbol() for a in mol.GetAtoms() if a.GetSymbol() not in ("C", "H")
    )
    charges = [a.GetFormalCharge() for a in mol.GetAtoms()]
    return sum(charges), sum(abs(c) for c in charges), dict(elements), sum(1 for a in mol.GetAtoms() if a.IsInRing())


def delta(smiles: str, back: str | None) -> tuple[str, ...]:
    """What a wrong-molecule read-back lost or changed, as labels (see `DELTA_LABELS`); a pure function of the two structures.

    It explains a `mismatch_*` row, it does not decide one: the class still comes from `classify`. It calls neither the engine nor
    OPSIN, and a read-back that is empty or does not parse gets the fallback rather than an exception.

    Element counts are compared per element, so a swap (an O where the input had an N) reads as one element dropped AND one
    gained, not as "no heteroatom change". The ring measure is the number of ATOMS in any ring, not RDKit's ring count: a ring
    opened or closed moves the first, a different decomposition of the same rings moves only the second.
    `same_formula_connectivity_change` deliberately does not say "wrong locant": two isomers of one formula differ by a locant,
    a skeleton, a functional group, and this function cannot tell which.
    """
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula

    want = Chem.MolFromSmiles(smiles) if smiles else None
    got = Chem.MolFromSmiles(back) if back else None
    if want is None or got is None:
        return ("other_formula_change",)
    net_w, abs_w, el_w, ring_w = _delta_facts(want)
    net_g, abs_g, el_g, ring_g = _delta_facts(got)
    labels: list[str] = []
    if abs_w and not abs_g:
        labels.append("charge_lost")
    elif (net_w, abs_w) != (net_g, abs_g):
        labels.append("charge_changed")
    dropped = sorted(e for e in el_w if el_g.get(e, 0) < el_w[e])
    gained = sorted(e for e in el_g if el_g[e] > el_w.get(e, 0))
    if dropped:
        labels.append("heteroatom_dropped:" + "+".join(dropped))
    if gained:
        labels.append("heteroatom_gained:" + "+".join(gained))
    if ring_w != ring_g:
        labels.append("ring_atom_count_changed")
    same_formula = CalcMolFormula(want) == CalcMolFormula(got)
    if same_formula:
        labels.append("same_formula_connectivity_change")
    return tuple(labels) or ("other_formula_change",)


def scan(rows: list[dict], *, names_only: bool = False) -> dict[str, dict]:
    """Every row named, read back and classified: `{label: {smiles, name, back, cls}}`, plus `delta` on a `mismatch_*` row."""
    named = name_rows(rows)
    readable = [k for k, v in named.items() if "NAMING ERROR" not in v["name"] and not v["name"].startswith("RAISED")]
    back_of: dict[str, str] = {}
    if not names_only:
        back_of = dict(zip(readable, read_back([named[k]["name"] for k in readable])))
    out = {
        k: {**v, "back": back_of.get(k), "cls": classify(v["smiles"], v["name"], None if names_only else back_of.get(k))}
        for k, v in named.items()
    }
    for record in out.values():
        if record["cls"] in ("mismatch_formula", "mismatch_same_formula"):
            record["delta"] = list(delta(record["smiles"], record["back"]))
    return out


def summarise(records: dict[str, dict]) -> list[str]:
    """The printed report: counts per class, and the embedded-error messages clustered by stem."""
    total = len(records)
    counts = collections.Counter(r["cls"] for r in records.values())
    lines = [f"{total} rows"]
    for cls in CLASSES:
        if counts[cls]:
            lines.append(f"  {cls:22s} {counts[cls]:5d}  {100 * counts[cls] / total:5.2f}%")
    stems = collections.Counter(
        _DIGITS.sub("N", m.group(1))[:62] if (m := _ERROR_STEM.search(r["name"])) else "(no stem)"
        for r in records.values() if r["cls"] == "naming_error"
    )
    if stems:
        lines.append("  embedded-error stems (a stem is a MECHANISM only after reading its rows):")
        for stem, n in stems.most_common(8):
            lines.append(f"    {n:4d}  {_LONG_TOKEN.sub('<smiles>', stem)}")
    deltas = collections.Counter(
        (r["delta"][0] if r.get("delta") else LEGACY_DELTA)
        for r in records.values() if r["cls"] in ("mismatch_formula", "mismatch_same_formula")
    )
    if deltas:
        lines.append("  wrong-molecule rows by what the read-back changed (first label; a record scanned before `delta` existed is "
                     f"{LEGACY_DELTA}):")
        for label, n in deltas.most_common():
            lines.append(f"    {n:4d}  {label}")
    bad = counts["mismatch_formula"] + counts["mismatch_same_formula"]
    lines.append(f"  candidate wrong structures: {bad} ({100 * bad / total:.2f}%); visible failures: "
                 f"{counts['naming_error'] + counts['refused']} ({100 * (counts['naming_error'] + counts['refused']) / total:.2f}%)")
    lines.append("  a mismatch is a CANDIDATE: OPSIN reads some anion names as the neutral acid, so read the rows")
    return lines


def compare(previous: dict[str, dict], current: dict[str, dict]) -> list[str]:
    """Class movement between two scans, by count and by row (a name change with the same class is counted, not listed)."""
    moved = [(k, previous[k]["cls"], current[k]["cls"]) for k in current if k in previous and previous[k]["cls"] != current[k]["cls"]]
    renamed = sum(1 for k in current if k in previous and previous[k]["name"] != current[k]["name"])
    lines = [f"{len(moved)} rows changed class; {renamed} rows changed name"]
    for k, was, now in moved:
        lines.append(f"  {k}: {was} -> {now}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="write one record per row as JSON")
    parser.add_argument("--list", choices=CLASSES, help="print the rows of one class")
    parser.add_argument("--compare", type=Path, help="a previous --out file to compare against")
    parser.add_argument("--names-only", action="store_true", help="skip the OPSIN read-back (no JRE needed; every readable name counts as exact)")
    args = parser.parse_args(argv)

    if not args.names_only and shutil.which("java") is None:
        print("No bare `java` on PATH: OPSIN needs one, and without it every name reads as unparsable. Put the JRE on PATH "
              "(as `/c/...`, not `C:/...`, in bash) or pass --names-only.", file=sys.stderr)
        return 2
    warnings.filterwarnings("ignore")
    records = scan(load_sample(), names_only=args.names_only)
    for line in summarise(records):
        print(line)
    if args.names_only:
        print("  (read-back skipped: `exact` here means only that a name was produced)")
    if args.list:
        for label, r in records.items():
            if r["cls"] == args.list:
                print(f"{label}\t{r['smiles']}\t{r['name'][:140]}" + (f"\t[{','.join(r['delta'])}]" if r.get("delta") else ""))
    if args.compare:
        print()
        for line in compare(json.loads(args.compare.read_text(encoding="utf-8")), records):
            print(line)
    if args.out:
        args.out.write_text(json.dumps(records), encoding="utf-8")
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
