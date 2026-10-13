"""The registered Lewis calculator returns what it always did, whatever is added around it.

`docs/RECIPES_DESIGN.md` section 4 moves the body of `compute_lewis_adduct` into a function that can also take
evidence from stored quantum-chemistry runs, and says the registered calculator "keeps its signature and its
output, byte for byte". This is that pin: a panel of 21 calls (every branch of the body: a pair resolved by the
Drago table, by structural admissibility and by the user; an unresolved pair that reports both ways round; a pi
donor; both kinds of refusal; and the parameter failures), recorded from the code BEFORE it was moved, in
`tests/fixtures/lewis_adduct_reports.json`.

**WHAT IS COMPARED IS A PROJECTION, NOT THE ENCODED OBJECT.** The lines, each fact's label, value, unit, basis,
source and evidence, the error, the cache state, the identity fields and the provenance. A new defaulted field on
`Fact` changes the encoding of every report in the application and says nothing about this calculator, so a pin on
the encoding would fail for a reason that is not this one's.

To re-record (only if the calculator's output is MEANT to change, and say so in the commit):

    OPENCHEM_DATA_ROOT=<empty dir> uv run python tests/test_lewis_adduct_pin.py --record
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdkit import Chem

from openchem.chem.lewis_adduct import compute_lewis_adduct

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lewis_adduct_reports.json"

#: (name, subject smiles, parameters).
PANEL = [
    ("iodine + triethylamine, auto", "II", {"partner_smiles": "CCN(CC)CC"}),
    ("triethylamine + iodine, auto", "CCN(CC)CC", {"partner_smiles": "II"}),
    ("iodine + pyridine, acid", "II", {"partner_smiles": "c1ccncc1", "role": "acid"}),
    ("iodine + pyridine, base", "II", {"partner_smiles": "c1ccncc1", "role": "base"}),
    ("iodine + benzene (pi donor), auto", "II", {"partner_smiles": "c1ccccc1"}),
    ("water + water, auto (unresolved)", "O", {"partner_smiles": "O"}),
    ("methanol + ammonia, auto", "CO", {"partner_smiles": "N"}),
    ("borane + carbon monoxide, auto", "B", {"partner_smiles": "[C-]#[O+]"}),
    ("carbon monoxide + borane, auto", "[C-]#[O+]", {"partner_smiles": "B"}),
    ("BF3 + carbon monoxide, acid", "FB(F)F", {"partner_smiles": "[C-]#[O+]", "role": "acid"}),
    ("BF3 + carbon monoxide, base", "FB(F)F", {"partner_smiles": "[C-]#[O+]", "role": "base"}),
    ("BF3 + trimethylamine, auto", "FB(F)F", {"partner_smiles": "CN(C)C"}),
    ("methane + ethane, auto (neither)", "C", {"partner_smiles": "CC"}),
    ("methane + ethane, acid (refused by predict)", "C", {"partner_smiles": "CC", "role": "acid"}),
    ("ammonia + phosphine, auto", "N", {"partner_smiles": "P"}),
    ("phenol + pyridine, auto", "Oc1ccccc1", {"partner_smiles": "c1ccncc1"}),
    ("no partner", "II", {}),
    ("unparseable partner", "II", {"partner_smiles": "not a molecule"}),
    ("unknown role", "II", {"partner_smiles": "CCN(CC)CC", "role": "stronger"}),
    ("a stored role label (legacy)", "II", {"partner_smiles": "CCN(CC)CC", "role": "This molecule is the acid"}),
    ("no parameters at all", "II", None),
]


def _plain(value):
    """JSON-safe, with enums as their values and tuples as lists."""
    if hasattr(value, "value") and not isinstance(value, (str, int, float)):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return value


def project(report) -> dict:
    """Everything that says what the calculator concluded, and nothing that says how a report is stored."""
    provenance = report.provenance
    return {
        "report_id": report.report_id,
        "name": report.name,
        "category": report.category,
        "molecule_uuid": report.molecule_uuid,
        "cache_state": _plain(report.cache_state),
        "error": report.error,
        "severity": _plain(report.severity),
        "matched": list(report.matched),
        "provenance": None if provenance is None else {
            "created_by": provenance.created_by,
            "method": provenance.method,
            "parameters": _plain(provenance.parameters),
        },
        "facts": [
            {
                "category": _plain(f.category), "label": f.label, "value": _plain(f.value),
                "display_value": f.display_value, "source": f.source, "basis": _plain(f.basis),
                "units": f.units, "evidence": _plain(f.evidence), "limitations": _plain(f.limitations),
            }
            for f in report.facts
        ],
    }


def run_panel() -> dict:
    out = {}
    for name, smiles, parameters in PANEL:
        mol = Chem.MolFromSmiles(smiles)
        assert mol is not None, smiles
        out[name] = {"smiles": smiles, "parameters": parameters, "report": project(compute_lewis_adduct(mol, "uuid-1", parameters))}
    return out


def test_the_registered_calculator_returns_what_it_returned_before_it_was_moved():
    recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = run_panel()
    assert set(now) == set(recorded), "the panel and the recording are out of step; re-record deliberately"
    for name in recorded:
        assert now[name]["report"] == recorded[name]["report"], f"{name}: the calculator's output changed"


def test_the_pin_actually_reaches_every_branch_it_claims():
    """A pin over a panel that never reached a branch pins nothing about it."""
    recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    text = {name: "\n".join(case["report"]["matched"]) for name, case in recorded.items()}
    assert "Role: as you set it" in text["iodine + pyridine, acid"]
    assert "from the Drago-Wayland table" in text["iodine + triethylamine, auto"]
    assert "from the structures" in text["BF3 + trimethylamine, auto"]
    assert "BOTH orientations are reported" in text["water + water, auto (unresolved)"]
    assert "Orientation 1" in text["water + water, auto (unresolved)"]
    assert "pi system" in text["iodine + benzene (pi donor), auto"]
    states = {name: case["report"]["cache_state"] for name, case in recorded.items()}
    assert set(states.values()) == {"completed", "failed"}
    assert any("Could not parse" in (c["report"]["error"] or "") for c in recorded.values())
    assert any("unknown role" in (c["report"]["error"] or "") for c in recorded.values())
    assert any("Choose or enter the partner" in (c["report"]["error"] or "") for c in recorded.values())


if __name__ == "__main__":
    if "--record" not in sys.argv:
        raise SystemExit(__doc__)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(run_panel(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("recorded", len(PANEL), "cases to", FIXTURE)
