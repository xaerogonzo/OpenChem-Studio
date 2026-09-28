"""RDX / HMX / TNT / PETN and a diagnostic extension corpus through Marrero-Gani (2001), against the
app's real Joback and against measured melting points -- Track 1 of the plan at
`docs/research/literature.toml`'s marrero2001 entry.

**This is a survey script, not a calculator.** Nothing here changes what the app ships; see
docs/research/README.md for why a comparison is not a promotion, and docs/CALCULATOR_MATURITY.md for
what promoting Thermophysical's coverage would actually require.

**Development vs. diagnostic, not one undifferentiated "holdout".** RDX/HMX/TNT/PETN are the
DEVELOPMENT set: scoring them first is what produced the ring-N + generic-NO2 decomposition hypothesis
and the suspicion of a per-nitramine bias. Every other row below is DIAGNOSTIC: drawn from
`tests/fixtures/census_panel.toml` (frozen before any calculator ran over it, but examined while
planning this extension), so it can stress-test the decomposition and characterize behavior, but is not
a blind holdout and must not be reported as one. Neither role level supports a promotion claim on its
own -- see `docs/CALCULATOR_MATURITY.md`.

**Why only Tm.** Both Klapoetke (klapotke2017, p. 303) and Agrawal (2010, Table 3.6) agree that several
of these compounds decompose at or near their melting point, so Tb/Tc/Pc/Vc describe a state most of
them never reach. Tm is the one property with a real measured value below the decomposition point for
most rows, so it is the only property this script compares -- and even Tm is scored only for rows whose
`transition_type` is exactly `"melting"` (`tools/validation_rows.py`'s `admit_to_melting_point_set`): a
reported decomposition or "estimated" melting temperature is a different, or unmeasured, quantity and is
never silently compared against a Tm prediction.

**Group assignments are cross-checked, not just hand-asserted.** Each row's `groups` dict is verified
against `benchmarks/thermophysical/energetics_groups.py`'s independent SMARTS-based counter, which was
itself checked for representation invariance (`tests/test_energetics_groups.py`) -- so a decomposition
here is a claim about the molecule, not about how this one file happens to write its SMILES. A row with
`groups: None` is a genuine refusal (no complete first-order decomposition exists), recorded with the
specific atoms that could not be claimed, never a partial sum.

First-order only, for every row, always: Table 7 has no second-order correction for a ring N bonded to
NO2 at all (checked while transcribing it), and TNT's own aromatic substitution pattern -- worked out
canonically this session from its parent name's own numbering (methyl anchors position 1, giving
substituent set {1,2,4,6}) and cross-checked against every one of Table 7's 9 AROMRING patterns, none of
which cover a {1,2,4,6} set -- has no applicable second-order correction either. So "first-order only"
is not a shortcut here, it is the paper's own complete answer for every molecule in this corpus.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


marrero = _load("marrero2001_table", "marrero2001_table.py")
energetics_groups = _load("energetics_groups", "energetics_groups.py")


#: name, SMILES, role (development/diagnostic), stratum (matches census_panel.toml where the row comes
#: from there), first-order groups (or None for a genuine refusal, with `refusal_atoms` naming what
#: could not be claimed), and the measured-Tm citation chain: `transition_type`
#: (melting/decomposition/melting_with_decomposition/not_observed -- tools/validation_rows.py's own
#: vocabulary), `value_source` (primary/secondary), `primary_reference` (furthest-back citation traced,
#: even if unread), `secondary_reference` (the handbook actually read).
MOLECULES = {
    # --- development set: already scored, shaped the hypotheses under test -----------------------
    "RDX": {
        "smiles": "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
        "role": "development",
        "stratum": "nitramine",
        "groups": {"CH2 (cyclic)": 3, "N (cyclic)": 3, "NO2 except as above": 3},
        "measured_tm_k": 478.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "Yinon & Zitrin (1981), The Analysis of Explosives, Ch. 9, p. 136 -- not held",
        "secondary_reference": "Agrawal (2010) Table 3.6, p. 189: mp 205 C (ignition 229 C, a 24 C gap)",
    },
    "HMX": {
        "smiles": "O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "role": "development",
        "stratum": "nitramine",
        "groups": {"CH2 (cyclic)": 4, "N (cyclic)": 4, "NO2 except as above": 4},
        "measured_tm_k": 548.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "not traced beyond Agrawal 2010's own Ref. [46] (Yinon & Zitrin 1981)",
        "secondary_reference": (
            "Agrawal (2010) Table 3.6, p. 189: beta-HMX mp 275 C (ignition 279-281 C, only a 4-6 C gap "
            "-- consistent with Klapoetke klapotke2017 p. 303's 'lie close together', but a real "
            "separately-measured value, not an absence of one)"
        ),
    },
    "TNT": {
        "smiles": "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "role": "development",
        "stratum": "nitroaromatic",
        "groups": {"aC-CH3": 1, "aC-NO2": 3, "aCH": 2},
        "measured_tm_k": 354.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "not traced beyond Agrawal 2010's own Ref. [46]",
        "secondary_reference": (
            "Agrawal (2010) Table 3.6, p. 189: mp 81 C; matches Klapoetke klapotke2017 p. 303's "
            "'melts at approx. 80 C' and Agrawal's own prose (Sec. 2.2.2, p. 72 area): 'low melting "
            "point (80.4 C)'"
        ),
    },
    "PETN": {
        "smiles": "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",
        "role": "development",
        "stratum": "nitrate_ester",
        "groups": {"C": 1, "CH2": 4, "ONO2": 4},
        "measured_tm_k": 413.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "not traced beyond Agrawal 2010's own Ref. [46]",
        "secondary_reference": (
            "Agrawal (2010) Table 3.6, p. 189: mp 140 C (ignition 203 C, a 63 C gap); matches Agrawal's "
            "own prose (Sec. 2.2.6, p. 73): 'm.p. 140 C' -- two independent passages in the same book "
            "agreeing, not one number repeated"
        ),
    },
    # --- diagnostic set: frozen in census_panel.toml before any calculator ran, examined while ------
    # --- planning this extension -- extends and stress-tests the decomposition, not a blind holdout --
    "dinitrodiazetidine": {
        "smiles": "O=[N+]([O-])N1CN([N+](=O)[O-])C1",
        "role": "diagnostic",
        "stratum": "nitramine",
        "groups": {"N (cyclic)": 2, "NO2 except as above": 2, "CH2 (cyclic)": 2},
        "measured_tm_k": None,
        "transition_type": None,
        "value_source": None,
        "primary_reference": "",
        "secondary_reference": (
            "still no measured Tm found. Expanded search 2026-09-28: this compound's actual export- "
            "control abbreviation is DNAD, not DNAZ (found via a general web search hit on the EU "
            "Common Military List) -- CAS 78246-06-7. Checked under that identity: NIST Chemistry "
            "WebBook has no entry for the CAS number or the formula C2H4N4O4 (that formula resolves to "
            "a different compound, FOX-7/DADNE); ChemicalBook's own data page for CAS 78246-06-7 lists "
            "only a PREDICTED boiling point and density, no melting point at all, measured or "
            "predicted. Genuinely deferred, not merely unchecked."
        ),
    },
    "tetryl": {
        "smiles": "CN(c1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "role": "diagnostic",
        "stratum": "nitramine",  # census_panel.toml: "an aromatic nitramine, no ring N-N"
        "groups": {"aC-NO2": 3, "aC-N": 1, "aCH": 2, "NO2 except as above": 1, "CH3": 1},
        "measured_tm_k": 402.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "not traced",
        "secondary_reference": (
            "Agrawal (2010) Table 3.6, p. 189: mp 129 C; independently confirmed by Agrawal's own prose "
            "(Sec. 2.2.3, p. 72): 'm.p. 129 C' -- two independent passages agreeing"
        ),
    },
    "tatb": {
        "smiles": "Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]",
        "role": "diagnostic",
        "stratum": "nitroaromatic",
        "groups": {"aC-NO2": 3, "aC-NH2": 3},
        "measured_tm_k": None,
        "transition_type": "not_observed",
        "value_source": "secondary",
        "primary_reference": "",
        "secondary_reference": (
            "Klapoetke (klapotke2017, p. 303-304, Fig. 10.7 discussion): 'other energetic compounds "
            "such as NQ or TATB decompose at much lower temperatures than their ESTIMATED melting "
            "points' -- TATB's melting point is explicitly an estimate it never reaches, not a "
            "measurement; entered here as a decomposition-behavior / group-assignment control, not a "
            "numeric Tm row (tools/validation_rows.py's admit_to_melting_point_set excludes it)"
        ),
    },
    "nitroguanidine": {
        "smiles": "NC(=N)N[N+](=O)[O-]",
        "role": "diagnostic",
        "stratum": "energetic",
        "groups": None,
        "refusal_atoms": "the guanidine core (C=N, and the N-NO2 nitramide N) -- no group in Table 6 "
        "covers a C=N outside an aldazine/ketazine context; its NH2 alone IS covered (row 65) but that "
        "does not make the whole molecule decomposable",
        "measured_tm_k": 537.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "not traced",
        "secondary_reference": "Agrawal (2010) Table 3.6, p. 189: mp 264 C",
    },
    "ammonium_nitrate": {
        "smiles": "[NH4+].[O-][N+](=O)[O-]",
        "role": "diagnostic",
        "stratum": "energetic",
        "groups": None,
        "refusal_atoms": "the whole molecule -- an ammonium cation and a nitrate anion are inorganic "
        "and ionic; Marrero-Gani's groups describe organic covalent structures",
        "measured_tm_k": 442.15,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": "not traced",
        "secondary_reference": "Agrawal (2010) Table 3.6, p. 189: mp 169 C (listed in the Melting point column)",
    },
    "nitroglycerin": {
        "smiles": "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]",
        "role": "diagnostic",
        "stratum": "nitrate_ester",
        "groups": {"ONO2": 3, "CH2": 2, "CH": 1},
        "measured_tm_k": 285.5,
        "transition_type": "melting",
        "value_source": "secondary",
        "primary_reference": (
            "Acree, W.E. (1991), 'Thermodynamic properties of organic compounds: enthalpy of fusion "
            "and melting point temperature compilation', Thermochimica Acta 189, 37-56 -- not held"
        ),
        "secondary_reference": (
            "NIST Chemistry WebBook (webbook.nist.gov, CAS 55-63-0), Phase change data: DfusH = 21.87 "
            "kJ/mol AT 285.5 K, citing Acree (1991). Found 2026-09-28 after Agrawal's own NG section "
            "(Sec. 2.2.4, p. 72-73) turned up density/VOD but no melting point. 285.5 K = 12.35 C is "
            "close to the commonly-cited ~13 C 'stable' polymorph value, but NIST's own table does not "
            "say which of NG's two known polymorphs (a labile form near 2 C, a stable form near 13 C) "
            "this reading is -- recorded as found, not silently assigned to the stable form."
        ),
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
        groups = spec["groups"]
        if groups is not None:
            # Cross-check against the independent SMARTS counter -- a mismatch is a bug somewhere in
            # this file or in energetics_groups.py, never silently trusted either way.
            checked = energetics_groups.count_groups(spec["smiles"])
            if checked != groups:
                raise AssertionError(f"{name}: hand groups {groups} != energetics_groups {checked}")
            mg_tm = marrero.estimate("Tm", groups)
        else:
            mg_tm = None

        joback_tf, joback_refusal = run_joback(spec["smiles"])
        measured = spec["measured_tm_k"]
        scoreable = groups is not None and measured is not None and spec.get("transition_type") == "melting"

        rows.append(
            {
                "name": name,
                "role": spec["role"],
                "stratum": spec["stratum"],
                "groups": groups,
                "refusal_atoms": spec.get("refusal_atoms"),
                "marrero_gani_tm_k": mg_tm,
                "marrero_gani_error_k": (mg_tm - measured) if scoreable else None,
                "joback_tf_k": joback_tf,
                "joback_refusal": joback_refusal,
                "joback_error_k": (joback_tf - measured)
                if (joback_tf is not None and measured is not None and spec.get("transition_type") == "melting")
                else None,
                "measured_tm_k": measured,
                "transition_type": spec.get("transition_type"),
                "value_source": spec.get("value_source"),
                "primary_reference": spec.get("primary_reference", ""),
                "secondary_reference": spec.get("secondary_reference", ""),
                "scoreable": scoreable,
            }
        )
    return rows


def stratified_report(rows: list[dict]) -> dict[str, dict]:
    """Coverage and accuracy, kept SEPARATE, grouped by `stratum` -- an aggregate error can hide a poor
    energetic class (docs/CALCULATOR_MATURITY.md)."""
    by_stratum: dict[str, dict] = {}
    for row in rows:
        s = by_stratum.setdefault(
            row["stratum"], {"total": 0, "mg_covered": 0, "mg_scoreable": 0, "mg_errors": [], "refused": 0}
        )
        s["total"] += 1
        if row["groups"] is not None:
            s["mg_covered"] += 1
        else:
            s["refused"] += 1
        if row["scoreable"]:
            s["mg_scoreable"] += 1
            s["mg_errors"].append(row["marrero_gani_error_k"])
    return by_stratum


def _print_report(rows: list[dict]) -> None:
    for row in rows:
        print(f"\n{row['name']}  [{row['role']}, stratum={row['stratum']}]")
        if row["groups"] is None:
            print(f"  Marrero-Gani:       REFUSES -- {row['refusal_atoms']}")
        else:
            print(f"  Marrero-Gani Tm:    {row['marrero_gani_tm_k']:.1f} K  (groups {row['groups']})")
        if row["measured_tm_k"] is not None:
            print(
                f"  measured Tm:        {row['measured_tm_k']!r} K  "
                f"(transition_type={row['transition_type']}, source={row['value_source']})"
            )
            print(f"    secondary_reference: {row['secondary_reference']}")
            if row["primary_reference"]:
                print(f"    primary_reference:   {row['primary_reference']}")
        else:
            print(f"  measured Tm:        none -- {row['secondary_reference']}")
        if row["scoreable"]:
            print(f"  Marrero-Gani error: {row['marrero_gani_error_k']:.1f} K")
        if row["joback_refusal"]:
            print(f"  Joback:             refused ({row['joback_refusal']})")
        elif row["joback_error_k"] is not None:
            print(f"  Joback Tf:          {row['joback_tf_k']:.2f} K  (error {row['joback_error_k']:.1f} K)")
        else:
            print(f"  Joback Tf:          {row['joback_tf_k']:.2f} K  (not scoreable against this row)")

    print("\n--- stratified summary (coverage and accuracy kept separate) ---")
    for stratum, s in sorted(stratified_report(rows).items()):
        mean_abs = sum(abs(e) for e in s["mg_errors"]) / len(s["mg_errors"]) if s["mg_errors"] else None
        print(
            f"{stratum:15s}  total={s['total']}  Marrero-Gani covered={s['mg_covered']}  "
            f"refused={s['refused']}  scoreable={s['mg_scoreable']}  "
            f"mean|error|={mean_abs:.1f} K" if mean_abs is not None else
            f"{stratum:15s}  total={s['total']}  Marrero-Gani covered={s['mg_covered']}  "
            f"refused={s['refused']}  scoreable={s['mg_scoreable']}  mean|error|=n/a"
        )


if __name__ == "__main__":
    _print_report(compare())
