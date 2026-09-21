"""Run the charged-species panel and report it on two INDEPENDENT dimensions.

    python tools/charged_panel_report.py --out benchmarks/naming/charged_panel_baseline.json
    python tools/charged_panel_report.py --out ...r7-r3.json --compare ...baseline.json
    python tools/charged_panel_report.py --panel benchmarks/naming/charged_panel_r8.toml --out ...r8_baseline.json

`benchmarks/naming/charged_panel.toml` is built by class and frozen. This tool measures
what the engine does with each row and writes it to JSON; it never edits the panel.

`--panel` names another panel with the same row schema: naming round 8's addendum
(`charged_panel_r8.toml`) is measured by this same tool, so the two panels cannot drift into
two definitions of "structurally correct". Its extra columns (`site_vector`,
`structural_context`, `coverage_reason`) are carried into the records.

**Two dimensions, never one score.** A name that parses back to the right molecule and a
name that is the PREFERRED one are different claims, and a single "exact" number lets a
structural failure hide behind a preference comparison (or the reverse).

    structural   STRUCTURALLY_CORRECT | WRONG_MOLECULE | ORACLE_ERROR | ENGINE_ERROR
    preference   EXACT_PREFERRED | NON_PREFERRED | PREFERENCE_UNKNOWN | n/a

Reported worst-first, so an aggregate cannot bury the rows that matter:
WRONG_MOLECULE, then ENGINE_ERROR / ORACLE_ERROR, then STRUCTURALLY_CORRECT with
PREFERENCE_UNKNOWN, then NON_PREFERRED, then EXACT_PREFERRED.

**Ownership** (perception/charge_ownership.py) is recorded beside them: for an anion row,
whether exactly one route owns each site and whether the engine took it. A row whose
structural class has no owner is a HOLE, and that is a finding even when the name happens
to round-trip (lactate does).

A salt is also run with its components reversed (the name must not change) and with a water
between them (a different substance, recorded on its own terms, never compared for equality).

`target_basis` decides what "preferred" can mean: PRINTED and DERIVED rows are compared
with their target string exactly (whitespace-normalised only); NONE_VERIFIED rows constrain
structure and ownership but never the string.

Needs `java` on PATH (py2opsin shells out to a bare `java`), or every row classifies as
ORACLE_ERROR. The tool refuses to write in that state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "benchmarks" / "naming" / "charged_panel.toml"
sys.path.insert(0, str(ROOT / "src"))

#: Worst first: the order rows and counts are reported in.
REPORT_ORDER = (
    "WRONG_MOLECULE",
    "ENGINE_ERROR",
    "ORACLE_ERROR",
    "STRUCTURALLY_CORRECT/PREFERENCE_UNKNOWN",
    "STRUCTURALLY_CORRECT/NON_PREFERRED",
    "STRUCTURALLY_CORRECT/EXACT_PREFERRED",
)


def panel_sha256(panel: Path = PANEL) -> str:
    """Over LF text: the Windows working copy is CRLF under autocrlf, and git stores LF."""
    return hashlib.sha256(panel.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_panel(panel: Path = PANEL) -> list[dict]:
    return tomllib.loads(panel.read_text(encoding="utf-8"))["row"]


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


def permutations(smiles: str) -> list[tuple[str, str]]:
    """(label, smiles) with the components reversed, and with a water between them."""
    parts = smiles.split(".")
    if len(parts) < 2:
        return []
    return [
        ("reversed", ".".join(reversed(parts))),
        ("with_water", ".".join([parts[0], "O", *parts[1:]])),
    ]


def measure(smiles: str, target: str | None, basis: str) -> dict:
    """Name one structure and classify the name on both dimensions."""
    from rdkit import Chem

    from openchem.chem import naming_providers as providers
    from openchem.vendor.iupac_namer import name_smiles

    mol = Chem.MolFromSmiles(smiles)
    try:
        name = name_smiles(smiles)
    except Exception as exc:  # noqa: BLE001 - an engine refusal is a measurement
        return {"name": None, "roundtrip": "ENGINE_ERROR", "structural": "ENGINE_ERROR",
                "preference": "n/a", "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if not name:
        return {"name": None, "roundtrip": "NO_NAME", "structural": "ENGINE_ERROR",
                "preference": "n/a", "error": "the engine returned no name"}
    trip = providers.verify_name_round_trip(str(name), mol)
    if trip is providers.RoundTrip.MATCH:
        structural = "STRUCTURALLY_CORRECT"
    elif trip in (providers.RoundTrip.STEREO_OMITTED, providers.RoundTrip.STEREO_ADDED):
        structural = "STRUCTURALLY_CORRECT"  # same skeleton; the stereo note is kept below
    elif trip is providers.RoundTrip.TAUTOMER:
        structural = "STRUCTURALLY_CORRECT"  # the same compound (equal standard InChI); the tautomer note is kept below
    elif trip in (providers.RoundTrip.MISMATCH, providers.RoundTrip.STEREO_CONTRADICTED):
        structural = "WRONG_MOLECULE"
    else:
        structural = "ORACLE_ERROR"  # PARSER_FAILED / UNVERIFIED: the checker could not say
    if structural != "STRUCTURALLY_CORRECT":
        preference = "n/a"
    elif basis == "NONE_VERIFIED" or not target:
        preference = "PREFERENCE_UNKNOWN"
    else:
        preference = "EXACT_PREFERRED" if _norm(name) == _norm(target) else "NON_PREFERRED"
    return {"name": str(name), "roundtrip": trip.name, "structural": structural, "preference": preference}


def status_of(record: dict) -> str:
    if record["structural"] != "STRUCTURALLY_CORRECT":
        return record["structural"]
    return f"STRUCTURALLY_CORRECT/{record['preference']}"


def ownership(smiles: str) -> dict:
    """Per-component ownership of every structural anion site, plus the observed route."""
    from rdkit import Chem

    from openchem.vendor.iupac_namer.perception.charge_ownership import charged_owners

    mol = Chem.MolFromSmiles(smiles)
    frags = Chem.GetMolFrags(mol, asMols=True)
    reports = []
    for frag in frags:
        report = charged_owners(frag, measure=len(frags) == 1)
        if not any(a.GetFormalCharge() for a in frag.GetAtoms()):
            continue
        reports.append({
            "component": Chem.MolToSmiles(frag),
            "verdict": report.verdict.value if report.verdict else None,
            "owners": list(report.owners),
            "observed_route": report.observed.route if report.observed else None,
        })
    order = ("HOLE", "OVERLAP", "INCONSISTENT", "UNSUPPORTED", "OWNED")
    verdicts = {r["verdict"] for r in reports if r["verdict"]}
    worst = next((v for v in order if v in verdicts), None)
    return {"verdict": worst, "components": reports}


#: Columns a panel MAY carry beyond the round-7 schema; copied into the record when present.
EXTRA_COLUMNS = ("site_vector", "structural_context", "coverage_reason")


def run(*, only: str | None = None, panel: Path = PANEL) -> dict:
    rows = load_panel(panel)
    out = []
    for r in rows:
        if only and only not in r["id"]:
            continue
        target = r.get("target")
        m = measure(r["smiles"], target, r["target_basis"])
        rec = {
            "id": r["id"], "class": r["class"], "context": r["context"],
            "secondary_group": r["secondary_group"], "expected_owner": r["expected_owner"],
            "target_basis": r["target_basis"], "target": target, "smiles": r["smiles"],
            **m, "status": None,
        }
        for column in EXTRA_COLUMNS:
            if column in r:
                rec[column] = r[column]
        rec["status"] = status_of(rec)
        rec["ownership"] = ownership(r["smiles"])
        if r.get("permute"):
            perms = {}
            for label, smi in permutations(r["smiles"]):
                pm = measure(smi, target, r["target_basis"])
                perms[label] = {"smiles": smi, "name": pm["name"], "structural": pm["structural"],
                                "same_name_as_base": pm["name"] == m["name"]}
            rec["permutations"] = perms
            # ORDER independence is the reversed order only: the same substance must get the
            # same name whichever component is written first. The water variant is a DIFFERENT
            # substance (a hydrate), so it is recorded on its own terms and never compared for
            # equality; the first version of this check did, and flagged every salt.
            rec["order_independent"] = perms["reversed"]["same_name_as_base"]
            rec["water_variant_is_base_plus_water"] = (
                perms["with_water"]["name"] == f"{m['name']} water")
        out.append(rec)
    return {"panel": panel.name, "panel_sha256": panel_sha256(panel), "rows": len(out), "records": out}


def summarise(result: dict) -> str:
    recs = result["records"]
    lines = [f"panel {result['panel_sha256'][:12]}  rows={len(recs)}", ""]
    counts = Counter(r["status"] for r in recs)
    # The two dimensions, side by side and orthogonal. A row whose structure is wrong has NO preference
    # to report; it is EXCLUDED from the preference table (shown, never folded into "unknown" or
    # "non-preferred"), so the preference denominator is the same kind of number in every round.
    structure = Counter(r["structural"] for r in recs)
    ok = [r for r in recs if r["structural"] == "STRUCTURALLY_CORRECT"]
    preference = Counter(r["preference"] for r in ok)
    lines.append("structure  : " + ", ".join(f"{k}={structure.get(k, 0)}" for k in
                 ("STRUCTURALLY_CORRECT", "WRONG_MOLECULE", "ENGINE_ERROR", "ORACLE_ERROR")))
    lines.append("preference : " + ", ".join(f"{k}={preference.get(k, 0)}" for k in
                 ("EXACT_PREFERRED", "NON_PREFERRED", "PREFERENCE_UNKNOWN"))
                 + f"   (over {len(ok)} structurally correct rows; EXCLUDED, structure not correct: {len(recs) - len(ok)})")
    lines.append("")
    lines.append("outcome (worst first):")
    for status in REPORT_ORDER:
        lines.append(f"  {counts.get(status, 0):4d}  {status}")
    other = {k: v for k, v in counts.items() if k not in REPORT_ORDER}
    for k, v in sorted(other.items()):
        lines.append(f"  {v:4d}  {k}")
    verdicts = Counter((r["ownership"]["verdict"] or "n/a") for r in recs)
    lines += ["", "ownership verdict over rows with an anion site: "
              + ", ".join(f"{k}={v}" for k, v in sorted(verdicts.items()))]
    hole = [r["id"] for r in recs if r["ownership"]["verdict"] == "HOLE"]
    lines.append(f"  HOLE rows ({len(hole)}): {', '.join(hole)}")
    unsupported = [r["id"] for r in recs if r["ownership"]["verdict"] == "UNSUPPORTED"]
    lines.append(f"  declared UNSUPPORTED rows ({len(unsupported)}): {', '.join(unsupported)}")
    perm_bad = [r["id"] for r in recs if r.get("permutations") and not r["order_independent"]]
    lines.append(f"component-order dependent salts (reversed order changes the name): {len(perm_bad)} {perm_bad}")
    water_odd = [r["id"] for r in recs if r.get("permutations") and not r["water_variant_is_base_plus_water"]]
    lines.append(f"salts whose water variant is not '<name> water': {len(water_odd)} {water_odd}")
    lines += ["", "class x status (structural / preference):"]
    by_class: dict[str, Counter] = {}
    for r in recs:
        by_class.setdefault(r["class"], Counter())[r["status"].replace("STRUCTURALLY_CORRECT/", "ok/")] += 1
    for klass in sorted(by_class):
        cells = ", ".join(f"{k}={v}" for k, v in sorted(by_class[klass].items()))
        lines.append(f"  {klass:16} {cells}")
    return "\n".join(lines)


def compare(now: dict, before: dict) -> str:
    was = {r["id"]: r for r in before["records"]}
    lines = []
    for r in now["records"]:
        b = was.get(r["id"])
        if b is None:
            lines.append(f"  NEW      {r['id']}")
        elif (b["name"], b["status"], b["ownership"]["verdict"]) != (r["name"], r["status"], r["ownership"]["verdict"]):
            lines.append(
                f"  {r['id']}\n     name    {b['name']!r} -> {r['name']!r}\n"
                f"     status  {b['status']} -> {r['status']}\n"
                f"     owner   {b['ownership']['verdict']} -> {r['ownership']['verdict']}"
            )
    return "\n".join(lines) if lines else "  no row changed"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write the JSON here")
    ap.add_argument("--compare", type=Path, help="print every row that differs from this file")
    ap.add_argument("--only", help="only rows whose id contains this")
    ap.add_argument("--panel", type=Path, default=PANEL, help="which panel (default: the round-7 panel)")
    args = ap.parse_args()

    import shutil

    if shutil.which("java") is None:
        print("java is not on PATH: py2opsin needs it, and every row would read ORACLE_ERROR. Refusing.")
        return 2
    result = run(only=args.only, panel=args.panel)
    print(summarise(result))
    if args.compare:
        print("\nversus", args.compare.name)
        print(compare(result, json.loads(args.compare.read_text(encoding="utf-8"))))
    if args.out:
        args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
