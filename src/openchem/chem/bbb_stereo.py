"""BBB Score descriptors, and stereo descriptor analysis.

BBB SCORE -- THE INPUTS SHIP, THE SCORE DOES NOT.

Gupta et al. (2019, J. Med. Chem. 62, 9824) combine five descriptors --
aromatic ring count, heavy atom count, MWHBN, TPSA and the most basic pKa
-- through stepwise and polynomial weight functions into a 0-6 score,
where 4-6 indicates a CNS drug.

All five INPUTS are reproducible here and were checked against ChemAxon's
own worked example for sildenafil: aromatic rings 3 (exact), heavy atoms
33 (exact), and MWHBN 0.3672 against their 0.37 -- which incidentally
confirms MWHBN = (HBD + HBA) / sqrt(MW), a definition the docs never spell
out. TPSA comes out 113.42 against their 109.13; a real ~4% difference
between two TPSA implementations, noted rather than hidden.

The five WEIGHT FUNCTIONS are not published in ChemAxon's documentation,
and unlike CNS MPO -- where the docs gave per-component scores that pinned
each function individually -- the BBB page gives only component VALUES and
one total. Five unknown curves against one data point cannot be validated:
a reconstruction hitting 3.05 would prove nothing, because five free
functions can be tuned to hit any single number. So the descriptors ship
with the classification bands stated, and the composite score does not.

That is the same call already made for HLB and the steric indices.

The fifth input, the most basic pKa, comes from pkasolver and does NOT
agree with ChemAxon on the example: 9.15 against their 6.59 for
sildenafil's piperazine. That is a disagreement between two pKa models,
not a defect in this calculator -- the number is reported as what our own
predictor says, with the predictor named, rather than adjusted toward
theirs. Literature values for sildenafil cluster nearer 6.5, so ChemAxon
is likely closer here.

STEREO DESCRIPTORS are RDKit's own CIP assignment, which is a real
implementation of the Cahn-Ingold-Prelog rules rather than an
approximation of one.
"""

from __future__ import annotations

import math
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors

from openchem.chem.calculator_options import apply_microspecies, decimals, microspecies_note
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import AlertResult

# Gupta et al.'s bands. Reported because they are the useful part of the
# paper that IS published, even without the weight functions.
BBB_CNS_THRESHOLD = 4.0


def mwhbn(mol: Chem.Mol) -> float:
    """(HBD + HBA) / sqrt(MW).

    Confirmed against ChemAxon's sildenafil example: 8 / sqrt(474.59) =
    0.3672 versus their reported 0.37. Their docs do not state the
    definition, so this was recovered from the worked example.
    """
    hydrogen_bond_count = Lipinski.NumHDonors(mol) + Lipinski.NumHAcceptors(mol)
    molecular_weight = Descriptors.MolWt(mol)
    if molecular_weight <= 0:
        return 0.0
    return hydrogen_bond_count / math.sqrt(molecular_weight)


def bbb_descriptors(mol: Chem.Mol) -> dict[str, float]:
    """The five inputs Gupta et al.'s BBB Score is built from."""
    return {
        "aromatic_rings": float(rdMolDescriptors.CalcNumAromaticRings(mol)),
        "heavy_atoms": float(mol.GetNumHeavyAtoms()),
        "mwhbn": mwhbn(mol),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
    }


def compute_bbb_descriptors(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
    interpreter_path: str | None = None,
) -> AlertResult:
    """The "admet" category's BBB Score input calculator."""
    parameters = parameters or {}
    target = apply_microspecies(mol, parameters)
    places = decimals(parameters)
    values = bbb_descriptors(target)

    most_basic_pka: float | None = None
    try:
        from openchem.chem.logd import classify_ionizable_centres
        from openchem.chem.pka_providers import compute_pka, pka_predictor_available

        if pka_predictor_available(interpreter_path):
            pkas = sorted(value for _index, value in (compute_pka(target, interpreter_path) or []))
            acids, _bases = classify_ionizable_centres(target)
            basic = pkas[acids:]
            most_basic_pka = max(basic) if basic else None
    except Exception:  # noqa: BLE001 - the other four descriptors remain valid
        most_basic_pka = None

    lines = [
        f"Aromatic rings: {values['aromatic_rings']:.0f}",
        f"Heavy atoms: {values['heavy_atoms']:.0f}",
        f"MWHBN: {values['mwhbn']:.{places}f}",
        f"TPSA: {values['tpsa']:.{places}f} A^2",
    ]
    lines.append(
        f"pKa (most basic): {most_basic_pka:.{places}f} (pkasolver)"
        if most_basic_pka is not None
        else "pKa (most basic): unavailable (needs a configured pkasolver environment)"
    )
    lines.extend(microspecies_note(parameters))
    lines.append(
        "These are the five inputs to the Gupta et al. (2019) BBB Score. The composite score "
        "itself is NOT computed: its stepwise and polynomial weight functions are not published "
        "in ChemAxon's documentation, and one worked example cannot validate five unknown "
        "curves. For reference, that score runs 0-6 with 4-6 indicating a CNS drug."
    )
    return AlertResult(
        alert_id="bbb_descriptors",
        name="BBB Score Descriptors",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="admet",
        provenance=Provenance(
            created_by="core",
            method="gupta_bbb_inputs",
            parameters={**values, "most_basic_pka": most_basic_pka, "decimal_places": places},
        ),
    )


def stereo_descriptors(mol: Chem.Mol) -> list[tuple[int, str, str]]:
    """(atom or bond index, kind, CIP label) for every perceived stereo
    element, using RDKit's own CIP labeller.

    Element PERCEPTION goes through `FindPotentialStereo`, not through the
    atoms' chiral tags. That distinction is the whole point of this
    calculator: a flat drawing of ibuprofen has a real, perceivable
    stereocentre carrying no chiral tag at all, so walking tags reports
    nothing and hides exactly the gap a chemist needs told about. The same
    API already backs the diastereotopic-proton test in `nmr_signals.py`.
    """
    working = Chem.Mol(mol)
    try:
        Chem.rdCIPLabeler.AssignCIPLabels(working)
    except Exception:  # noqa: BLE001 - unspecified elements still report below
        pass

    found: list[tuple[int, str, str]] = []
    for element in Chem.FindPotentialStereo(working):
        index = int(element.centeredOn)
        if element.type == Chem.StereoType.Atom_Tetrahedral:
            kind, holder = "tetrahedral", working.GetAtomWithIdx(index)
        elif element.type == Chem.StereoType.Bond_Double:
            kind, holder = "double bond", working.GetBondWithIdx(index)
        else:  # atropisomeric and other axial types RDKit may add later
            kind, holder = str(element.type), None

        if element.specified != Chem.StereoSpecified.Specified:
            found.append((index, kind, "undefined"))
        elif holder is not None and holder.HasProp("_CIPCode"):
            found.append((index, kind, holder.GetProp("_CIPCode")))
        else:
            # Specified but unlabellable -- a real state for stereochemistry
            # CIP has no descriptor for. Saying "defined" is honest; saying
            # "undefined" would be wrong.
            found.append((index, kind, "defined (no CIP label)"))
    return found


def compute_stereo_descriptors(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "stereochemistry" category's Stereo Analysis calculator.

    Complements the existing stereo COUNTS in Topology Analysis by naming
    each centre and its R/S or E/Z label -- the counts say how many exist,
    this says which is which.
    """
    parameters = parameters or {}
    elements = stereo_descriptors(mol)
    if not elements:
        return AlertResult(
            alert_id="stereo_descriptors",
            name="Stereo Descriptors",
            molecule_uuid=molecule_uuid,
            matched=["No stereo elements in this structure."],
            category="stereochemistry",
            provenance=Provenance(created_by="core", method="rdkit_cip"),
        )

    lines = []
    for index, kind, label in elements:
        where = f"atom {index}" if kind == "tetrahedral" else f"bond {index}"
        if label == "undefined":
            lines.append(f"{where} ({kind}): undefined in this structure")
        else:
            lines.append(f"{where} ({kind}): {label}")

    undefined = sum(1 for _i, _k, label in elements if label == "undefined")
    lines.append(f"{len(elements)} stereo element(s), {undefined} undefined.")
    return AlertResult(
        alert_id="stereo_descriptors",
        name="Stereo Descriptors",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="stereochemistry",
        provenance=Provenance(
            created_by="core",
            method="rdkit_cip",
            parameters={"element_count": len(elements), "undefined": undefined},
        ),
    )
