"""Will this Lewis acid bind this Lewis base, and how strongly.

Three independent lines of evidence, reported side by side and never
collapsed into one score:

| line | answers | available when |
| --- | --- | --- |
| Drago-Wayland | how much enthalpy, in kcal/mol | both are in the parameter table |
| Frontier gap | how strong the orbital interaction is | orbital energies exist |
| HSAB match | whether the pairing is favoured at all | hardness exists for both |

**Why no aggregate score.** They answer different questions and which one
is informative depends on the pair. Drago gives a real enthalpy but only
for the ~50 species anybody has calorimetry for; the frontier gap applies
to anything a quantum job has touched but is not an energy; HSAB is a
compatibility statement, not a magnitude. Averaging them would invent a
quantity nobody defined, and would block the electrostatic, dispersion,
Pauli and charge-transfer terms that an energy decomposition would add
later.

**The pair this exists for.** Carbon monoxide is a negligible Bronsted
base -- no pKa table has anything useful to say about it -- and forms an
isolable adduct with borane. One correction worth carrying: BF3 binds CO
only WEAKLY, because BF3's boron is pi-stabilised by the fluorine lone
pairs and is a hard acid, while borane is softer and matches CO's soft
carbon donor. "CO + BH3 strong, CO + BF3 weak" is HSAB doing visible
work, which is why the HSAB line is here at all.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from openchem.chem.lewis import analyse, pi_donor_atoms
from openchem.domain.common import CacheState, Provenance
from openchem.domain.lewis import AdductEvidence, LewisAdduct
from openchem.domain.scientific_result import AlertResult
from openchem.domain.structure_issue import Basis

_DATA = Path(__file__).resolve().parent / "data" / "lewis_parameters.json"

METHOD = "Lewis adduct evidence"

_ASSUMPTIONS = (
    "Each line of evidence is reported on its own terms. There is no combined "
    "score, because the three answer different questions and no accepted way "
    "of weighing them against each other exists.",
    "Drago-Wayland enthalpies are for the 1:1 adduct in a poorly-coordinating "
    "solvent or the gas phase. A coordinating solvent competes with the base "
    "and the measured value drops.",
)


@lru_cache(maxsize=1)
def parameter_table() -> dict[str, Any]:
    """The committed Drago-Wayland table, or empty if it is not present.

    Missing is a supported state rather than an error: Phase A and B work
    without this file, and a build that ships without it should lose the
    kcal/mol line and nothing else.
    """
    if not _DATA.exists():
        return {"acids": {}, "bases": {}, "citation": ""}
    return json.loads(_DATA.read_text(encoding="utf-8"))


def _canonical(mol: Any) -> str:
    from rdkit import Chem

    return Chem.MolToSmiles(mol)


def _drago_line(acid: Any, base: Any) -> AdductEvidence:
    """-dH = E_A*E_B + C_A*C_B + W, in kcal/mol.

    Lookup is BY STRUCTURE rather than by name: the table is keyed on
    canonical SMILES, so a molecule drawn in the editor matches without
    anybody typing "trimethylamine".
    """
    table = parameter_table()
    acid_entry = table["acids"].get(_canonical(acid))
    base_entry = table["bases"].get(_canonical(base))
    if acid_entry is None or base_entry is None:
        missing = []
        if acid_entry is None:
            missing.append("the acid")
        if base_entry is None:
            missing.append("the base")
        return AdductEvidence(
            line="drago_wayland",
            label="Drago-Wayland enthalpy",
            basis=Basis.DETERMINISTIC,
            units="kcal/mol",
            note=(
                f"No tabulated E and C parameters for {' and '.join(missing)}. "
                "The table covers the species with published calorimetry, which is "
                "a few dozen, not a general method."
            ),
        )
    # -dH = E_A*E_B + C_A*C_B + W, with W ADDED. It is a constant cost of
    # getting the acid into a state that can bind at all -- cleaving a
    # dimer, mostly -- and carries its own negative sign where that cost
    # is real: the rhodium dimer's is -10.39 kcal/mol.
    #
    # This was written with W SUBTRACTED and every test still passed,
    # because every acid exercised in them has W = 0. A surviving mutation
    # is what found it, which is the entire argument for running them.
    value = (
        acid_entry["E"] * base_entry["E"]
        + acid_entry["C"] * base_entry["C"]
        + acid_entry.get("W", 0.0)
    )
    return AdductEvidence(
        line="drago_wayland",
        label="Drago-Wayland enthalpy",
        basis=Basis.DETERMINISTIC,
        value=value,
        units="kcal/mol",
        note=(
            f"{acid_entry['name']} + {base_entry['name']}. An empirical model, not "
            "a calculation from first principles: the parameters reproduce measured "
            "donor-iodine enthalpies to about 0.3 kcal/mol, and the observed values "
            "in Drago and Wayland's original 1965 paper to 0.36 (iodine) and 0.77 "
            "(phenol) kcal/mol."
        ),
    )


def _frontier_gap_line(
    acid_lumo_ev: float | None, base_homo_ev: float | None
) -> AdductEvidence:
    """E_LUMO(acid) - E_HOMO(base): the frontier orbital separation.

    SMALLER is a stronger interaction, which is the opposite direction to
    every other number here and is why the note says so explicitly.
    """
    if acid_lumo_ev is None or base_homo_ev is None:
        return AdductEvidence(
            line="frontier_gap",
            label="Frontier orbital gap",
            basis=Basis.HEURISTIC,
            units="eV",
            note=(
                "Needs the acid's LUMO energy and the base's HOMO energy. Run a "
                "quantum chemistry job on both molecules and these appear."
            ),
        )
    return AdductEvidence(
        line="frontier_gap",
        label="Frontier orbital gap",
        basis=Basis.HEURISTIC,
        value=acid_lumo_ev - base_homo_ev,
        units="eV",
        note=(
            "E_LUMO(acid) - E_HOMO(base). SMALLER means a stronger orbital "
            "interaction -- the opposite direction to the enthalpy above. It "
            "ignores overlap and symmetry, so two pairs with the same gap can "
            "interact very differently."
        ),
    )


def _hsab_line(acid_hardness: float | None, base_hardness: float | None) -> AdductEvidence:
    """|eta(acid) - eta(base)|: how well matched the pair is.

    HSAB says hard prefers hard and soft prefers soft, so a SMALL
    difference is a favourable match. It is a compatibility statement and
    not a magnitude -- a well-matched pair of weak partners still binds
    weakly, which is why this never appears without the other lines.

    **Measured, and it gets the headline case wrong.** On real ORCA
    B3LYP/def2-SVP delta-SCF runs of the pair this whole feature exists
    for:

        BH3 + CO   frontier gap  8.13 eV   |d eta|  1.63 eV
        BF3 + CO   frontier gap 10.90 eV   |d eta|  0.89 eV

    Borane binds carbon monoxide strongly enough to isolate the adduct and
    boron trifluoride barely binds it at all. The frontier gap says so;
    this line says the opposite, because CO's computed hardness (8.40 eV)
    lands near BF3's (9.29) rather than reflecting the softness that the
    qualitative argument assigns it. A single number on the eta scale is
    not the same thing as Pearson's soft/hard classification.

    **It is the metric, not the calculation.** Pearson's own experimental
    values (Inorg. Chem. 1988, 27, 734, Table II) put carbon monoxide at
    eta = 7.9 eV and boron trifluoride at 9.7 -- 1.8 eV apart, with CO
    genuinely high on the scale. So substituting perfect hardness numbers
    would not rescue this line: a single point on the eta axis is not
    Pearson's soft/hard classification, and CO is the case that shows the
    difference. The delta-SCF values used above (8.40 and 9.29) are within
    0.5 eV of those experimental ones.

    That disagreement is REPORTED rather than resolved, and it is the
    strongest argument for the no-combined-score design: an average of
    these two lines would have quietly split the difference on a case
    where one of them is simply right.
    `test_the_two_orbital_lines_disagree_on_carbon_monoxide` pins it.
    """
    if acid_hardness is None or base_hardness is None:
        return AdductEvidence(
            line="hsab_match",
            label="HSAB hardness match",
            basis=Basis.HEURISTIC,
            units="eV",
            note=(
                "Needs the chemical hardness of both. Run a quantum chemistry "
                "job on each -- prefer the delta-SCF calc type, since Koopmans "
                "hardness inverts ammonia against phosphine."
            ),
        )
    return AdductEvidence(
        line="hsab_match",
        label="HSAB hardness match",
        basis=Basis.HEURISTIC,
        value=abs(acid_hardness - base_hardness),
        units="eV",
        note=(
            f"|eta(acid) {acid_hardness:.2f} - eta(base) {base_hardness:.2f}|. "
            "Hard prefers hard and soft prefers soft, so SMALLER is a better "
            "match. This says whether the pairing is favoured, not how much "
            "energy it releases -- two well-matched weak partners still bind "
            "weakly."
        ),
    )


def _refuse(reason: str, **labels: str) -> LewisAdduct:
    return LewisAdduct(
        refused=True,
        reason=reason,
        summary=f"No prediction. {reason}",
        assumptions=_ASSUMPTIONS,
        **labels,
    )


def predict(
    acid: Any,
    base: Any,
    *,
    acid_uuid: str = "",
    base_uuid: str = "",
    acid_label: str = "",
    base_label: str = "",
    acid_lumo_ev: float | None = None,
    base_homo_ev: float | None = None,
    acid_hardness: float | None = None,
    base_hardness: float | None = None,
) -> LewisAdduct:
    """Every line of evidence about this pair that can be evaluated.

    The QM inputs are optional and independent: a pair with no quantum
    data still gets the Drago line, and a pair outside the parameter
    table still gets whatever the quantum data supports. Nothing here
    fails because one line is unavailable -- that is what makes three
    separate lines worth having.
    """
    labels = {
        "acid_uuid": acid_uuid,
        "base_uuid": base_uuid,
        "acid_label": acid_label or _canonical(acid),
        "base_label": base_label or _canonical(base),
    }

    # The acid must actually be able to accept and the base to donate.
    # Checked through the Phase A site analysis rather than re-derived, so
    # "what counts as an acceptor" has one definition in this codebase.
    acid_sites = analyse(acid)
    base_sites = analyse(base)
    if acid_sites.refused:
        return _refuse(f"The acid could not be analysed. {acid_sites.reason}", **labels)
    if base_sites.refused:
        return _refuse(f"The base could not be analysed. {base_sites.reason}", **labels)
    if not acid_sites.acceptors():
        return _refuse(
            "Nothing in the acid can accept an electron pair -- no empty valence "
            "orbital, no low-lying pi* or sigma*, no vacant coordination site.",
            **labels,
        )
    pi_donors = pi_donor_atoms(base)
    if not base_sites.donors() and not pi_donors:
        return _refuse(
            "The base has neither a lone pair nor a pi system to donate from.", **labels
        )

    evidence = (
        _drago_line(acid, base),
        _frontier_gap_line(acid_lumo_ev, base_homo_ev),
        _hsab_line(acid_hardness, base_hardness),
    )
    limitations = list(_limitations(evidence))
    if not base_sites.donors():
        limitations.append(
            "This base donates from a pi system rather than a lone pair, so there "
            "is no single donor ATOM -- the interaction is with the face of the "
            "pi cloud and its geometry is not what a lone-pair adduct's would be."
        )
    return LewisAdduct(
        evidence=evidence,
        summary=_summarise(evidence),
        assumptions=_ASSUMPTIONS,
        limitations=tuple(limitations),
        **labels,
    )


ROLE_ACID = "This molecule is the acid"
ROLE_BASE = "This molecule is the base"


def compute_lewis_adduct(
    mol: Any, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "lewis" category's two-molecule calculator.

    Takes the partner as a typed SMILES, the way `alignment_3d` takes its
    reference structure -- so an adduct prediction can be a column in a
    batch table rather than only a thing done in a panel.
    """
    from rdkit import Chem

    parameters = parameters or {}
    provenance = Provenance(created_by="core", method="lewis_adduct")
    partner_smiles = str(parameters.get("partner_smiles") or "").strip()

    def failed(error: str) -> AlertResult:
        return AlertResult(
            alert_id="lewis_adduct",
            name="Lewis Adduct",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="lewis",
            cache_state=CacheState.FAILED,
            error=error,
            provenance=provenance,
        )

    if not partner_smiles:
        return failed(
            "Enter the partner molecule as SMILES in this calculator's settings. "
            "An adduct needs two molecules and this one only has one."
        )
    partner = Chem.MolFromSmiles(partner_smiles)
    if partner is None:
        return failed(f"Could not parse the partner SMILES: {partner_smiles!r}")

    this_is_acid = str(parameters.get("role", ROLE_ACID)) == ROLE_ACID
    acid, base = (mol, partner) if this_is_acid else (partner, mol)
    result = predict(
        acid,
        base,
        acid_uuid=molecule_uuid if this_is_acid else "",
        base_uuid="" if this_is_acid else molecule_uuid,
    )
    if result.refused:
        return failed(result.reason)

    lines = [
        f"Acid: {result.acid_label}",
        f"Base: {result.base_label}",
        result.summary,
    ]
    for item in result.evidence:
        if item.value is None:
            lines.append(f"  {item.label}: not available -- {item.note}")
        else:
            lines.append(
                f"  {item.label}: {item.value:.2f} {item.units} [{item.basis.value}] -- {item.note}"
            )
    lines.extend(f"Assumption: {text}" for text in result.assumptions)
    lines.extend(f"Limitation: {text}" for text in result.limitations)

    return AlertResult(
        alert_id="lewis_adduct",
        name="Lewis Adduct",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="lewis",
        provenance=provenance,
    )


def _summarise(evidence: tuple[AdductEvidence, ...]) -> str:
    available = [e for e in evidence if e.value is not None]
    if not available:
        return (
            "An adduct is possible on the structures alone, but no line of "
            "evidence could be evaluated. Run a quantum chemistry job on both "
            "molecules, or use a pair with tabulated Drago parameters."
        )
    return "; ".join(f"{e.label} {e.value:.2f} {e.units}" for e in available) + "."


def _limitations(evidence: tuple[AdductEvidence, ...]) -> tuple[str, ...]:
    limitations = [
        "Sterics are not considered, and the size of that gap is measured rather "
        "than hypothetical. Drago and Wayland's own 1965 paper reports "
        "trimethylborane binding trimethylamine 8.2 kcal/mol more weakly than the "
        "electronics predict, because the methyl groups collide; the same table "
        "gives 1.5 kcal/mol for dimethylamine and nothing for the two smaller "
        "amines. An E and C equation has no term for it.",
        "A 1:1 adduct is assumed. Nothing here predicts stoichiometry, and several "
        "of these acids are dimers until a base breaks them apart.",
    ]
    if not any(e.line == "drago_wayland" and e.value is not None for e in evidence):
        limitations.append(
            "Without tabulated parameters there is no energy here at all -- the "
            "remaining lines order pairs, they do not tell you whether the adduct "
            "forms."
        )
    return tuple(limitations)
