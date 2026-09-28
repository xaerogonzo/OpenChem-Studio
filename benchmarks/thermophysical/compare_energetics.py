"""RDX / HMX / TNT / PETN through Marrero-Gani (2001), against the app's real Joback and against
measured melting points -- the comparison docs/research/literature.toml's marrero2001 entry asked for.

**This is a survey script, not a calculator.** Nothing here changes what the app ships; see
docs/research/README.md for why a comparison is not a promotion, and docs/CALCULATOR_MATURITY.md for
what promoting Thermophysical's coverage would actually require (a held-out set, not four molecules).

**What is being checked, and why only Tm.** docs/research/literature.toml's marrero2001 entry records
a caveat found while reading Klapoetke (already cited in docs/sources.toml as klapotke2017, p. 303):
"The melting and decomposition points of RDX and HMX lie close together" -- both compounds decompose
at or near their melting point, so Tb/Tc/Pc/Vc describe a state neither ever reaches, whichever method
produces the number. Tm is the one property with a real measured value below the decomposition point,
so it is the only property this script compares.

**Group assignments are HAND-DONE, not SMARTS-matched**, the same way the paper's own Appendix B
worked examples are -- there is no general-purpose group-contribution engine here, only four molecules
whose decomposition is unambiguous:

    RDX  (ring, C3H6N6O6):  3x CH2(cyclic) + 3x N(cyclic) + 3x NO2(except as above)
    HMX  (ring, C4H8N8O8):  4x CH2(cyclic) + 4x N(cyclic) + 4x NO2(except as above)
    TNT  (C7H5N3O6):        1x aC-CH3 + 3x aC-NO2 + 2x aCH   (Joback's own decomposition -- it
                            already runs TNT; this is a control, not new coverage)
    PETN (C5H8N4O12):       1x C (quaternary) + 4x CH2 + 4x ONO2   (the O-NO2 nitrate-ester group,
                            NOT the ether-context CH2O -- CH2O's own O would double-count the O that
                            ONO2's definition already carries, see the module docstring's atom count)

Each assignment accounts for every heavy atom exactly once; SMILES are Klapoetke Table 4.1's own
(tests/test_energetics.py's TABLE_4_1), so the molecule identity matches what's already shipped.

First-order only: no second-order correction is applied to any of the four. Table 7 has no
ring/nitro-specific second-order group for the nitramine motif (checked while reading the table --
see the literature.toml note), and for TNT's own aromatic ring pattern, working out which
AROMRINGs.. correction (if any) applies to a 1,2,4,6-type substitution requires a positional
convention this script does not try to verify -- reporting the first-order number only, as the paper
itself always does before showing any refinement, avoids asserting a correction that has not been
checked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("marrero2001_table", Path(__file__).parent / "marrero2001_table.py")
marrero = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = marrero
_spec.loader.exec_module(marrero)


#: name, SMILES (Klapoetke Table 4.1 / tests/test_energetics.py TABLE_4_1), first-order group
#: assignment, and the measured Tm this script checks against.
#:
#: Sourcing of the Tm values, honestly: TNT's "approx. 80 C" (353.5 K used here) is Klapoetke's own
#: text (p. 303, klapotke2017) prompted a second look. Verified 2026-09-27 against Agrawal (2010),
#: "High Energy Materials", Table 3.6 p. 189 (docs/research/literature.toml's agrawal2010 entry --
#: read directly this session, at the user's request for a primary-source check on RDX specifically).
#: That table gives melting point as its OWN column, separate from ignition/exotherm/decomposition,
#: for all four compounds -- so all four now carry a value read from that table, not a recollected
#: "standard literature value". Klapoetke's "lie close together" is directionally right for HMX (its
#: gap to ignition is ~4-6 C, the smallest of the four -- see RDX's own ~24 C gap below) but Agrawal's
#: table does give HMX a specific, separately-measured mp, so it is scored here too.
MOLECULES = {
    "RDX": {
        "smiles": "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
        "groups": {"CH2 (cyclic)": 3, "N (cyclic)": 3, "NO2 except as above": 3},
        "measured_tm_k": 478.15,
        "measured_tm_source": "Agrawal (2010) Table 3.6, p. 189: mp 205 C (ignition 229 C, a 24 C gap)",
    },
    "HMX": {
        "smiles": "O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "groups": {"CH2 (cyclic)": 4, "N (cyclic)": 4, "NO2 except as above": 4},
        "measured_tm_k": 548.15,
        "measured_tm_source": (
            "Agrawal (2010) Table 3.6, p. 189: beta-HMX mp 275 C (ignition 279-281 C, only a 4-6 C "
            "gap -- consistent with Klapoetke klapotke2017 p. 303's 'lie close together', but a real "
            "separately-measured value, not an absence of one"
        ),
    },
    "TNT": {
        "smiles": "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "groups": {"aC-CH3": 1, "aC-NO2": 3, "aCH": 2},
        "measured_tm_k": 354.15,
        "measured_tm_source": (
            "Agrawal (2010) Table 3.6, p. 189: mp 81 C; matches Klapoetke klapotke2017 p. 303's "
            "'melts at approx. 80 C'"
        ),
    },
    "PETN": {
        "smiles": "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",
        "groups": {"C": 1, "CH2": 4, "ONO2": 4},
        "measured_tm_k": 413.15,
        "measured_tm_source": "Agrawal (2010) Table 3.6, p. 189: mp 140 C (ignition 203 C, a 63 C gap)",
    },
}


def run_joback(smiles: str):
    """The app's own Joback, real code -- (Tf in K, or the refusal name)."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.chem.joback import compute_joback

    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.Compute2DCoords(mol)
    result = compute_joback(mol, "00000000-0000-0000-0000-000000000000")
    refusal = result.provenance.parameters.get("refusal")
    if refusal:
        return None, refusal
    for fact in result.facts:
        if fact.label == "Freezing point (normal)":
            return fact.value, None
    raise AssertionError("Joback ran but printed no freezing point fact")


def compare() -> list[dict]:
    rows = []
    for name, spec in MOLECULES.items():
        mg_tm = marrero.estimate("Tm", spec["groups"])
        joback_tf, joback_refusal = run_joback(spec["smiles"])
        measured = spec["measured_tm_k"]
        rows.append(
            {
                "name": name,
                "marrero_gani_tm_k": mg_tm,
                "marrero_gani_error_k": (mg_tm - measured) if measured is not None else None,
                "joback_tf_k": joback_tf,
                "joback_refusal": joback_refusal,
                "joback_error_k": (joback_tf - measured) if (joback_tf is not None and measured is not None) else None,
                "measured_tm_k": measured,
                "measured_tm_source": spec["measured_tm_source"],
            }
        )
    return rows


def _print_report(rows: list[dict]) -> None:
    for row in rows:
        print(f"\n{row['name']}")
        print(f"  measured Tm:        {row['measured_tm_k']!r} K  ({row['measured_tm_source']})")
        print(f"  Marrero-Gani Tm:    {row['marrero_gani_tm_k']:.1f} K  (error {row['marrero_gani_error_k']!r})")
        if row["joback_refusal"]:
            print(f"  Joback:             refused ({row['joback_refusal']})")
        else:
            print(f"  Joback Tf:          {row['joback_tf_k']:.2f} K  (error {row['joback_error_k']!r})")


if __name__ == "__main__":
    _print_report(compare())
