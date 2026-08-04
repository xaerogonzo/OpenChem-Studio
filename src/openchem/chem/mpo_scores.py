"""Multiparameter-optimisation scores and structural frameworks.

CNS MPO (Wager et al.) sums six desirability functions, each mapping one
property onto 0-1, for a total of 0-6. A score >= 4.0 is generally taken
as favourable for CNS exposure.

THE BREAKPOINTS ARE VALIDATED, not guessed. ChemAxon's documentation gives
a worked aspirin example -- MW 180.16, LogP 1.24, LogD -2.16, TPSA 63.60,
HBD 1.00, pKa -7.14, total 5.75, with every component 1.00 except
HBD_SCORE = 0.75. The functions below reproduce that total exactly, and
the HBD one is pinned by it: a linear fall from 1.0 at HBD 0 to 0.0 at
HBD 4 gives 0.75 at HBD 1, while the 0.5-3.5 window also seen in the
literature gives 0.833 and does NOT match. One documented data point
discriminated between two plausible published forms.

The pKa term wants the most BASIC centre's pKa. Without a pKa predictor
configured there is no honest value for it, so that term is reported as
unavailable and the total is given out of 5 rather than silently scoring
it 1.0 -- which would inflate every basic compound's score.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold

from openchem.domain.common import Provenance
from openchem.domain.scientific_result import AlertResult, StructureEntry, StructureSetResult


def _ramp(value: float, good: float, bad: float) -> float:
    """1.0 at or below `good`, 0.0 at or above `bad`, linear between."""
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return (bad - value) / (bad - good)


def _hump(value: float, rise_start: float, rise_end: float, fall_start: float, fall_end: float) -> float:
    """0 outside, 1 in the middle plateau, linear on both shoulders."""
    if value <= rise_start or value >= fall_end:
        return 0.0
    if rise_end <= value <= fall_start:
        return 1.0
    if value < rise_end:
        return (value - rise_start) / (rise_end - rise_start)
    return (fall_end - value) / (fall_end - fall_start)


def cns_mpo_components(
    mol: Chem.Mol, logd: float | None = None, most_basic_pka: float | None = None
) -> dict[str, tuple[float, float | None]]:
    """Each property's raw value and its desirability score.

    A score of `None` means the property could not be computed, which is
    kept distinct from a score of 0.0 (computed, and unfavourable).
    """
    mol_wt = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    hbd = float(Lipinski.NumHDonors(mol))

    components: dict[str, tuple[float, float | None]] = {
        "MW": (mol_wt, _ramp(mol_wt, 360.0, 500.0)),
        "LogP": (logp, _ramp(logp, 3.0, 5.0)),
        "TPSA": (tpsa, _hump(tpsa, 20.0, 40.0, 90.0, 120.0)),
        "HBD": (hbd, _ramp(hbd, 0.0, 4.0)),
    }
    # logD falls back to logP when no pKa predictor is configured. That is
    # the correct limit for a non-ionizable molecule and an overestimate
    # for an ionizable one, so it is labelled rather than hidden.
    components["LogD"] = (
        logp if logd is None else logd,
        _ramp(logp if logd is None else logd, 2.0, 4.0),
    )
    components["pKa (most basic)"] = (
        most_basic_pka if most_basic_pka is not None else float("nan"),
        None if most_basic_pka is None else _ramp(most_basic_pka, 8.0, 10.0),
    )
    return components


def compute_cns_mpo(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
    interpreter_path: str | None = None,
) -> AlertResult:
    """The "admet" category's CNS MPO calculator."""
    logd = None
    most_basic_pka = None
    try:
        from openchem.chem.logd import classify_ionizable_centres, logd_from_pkas
        from openchem.chem.pka_providers import compute_pka, pka_predictor_available

        if pka_predictor_available(interpreter_path):
            pkas = sorted(p.value for p in (compute_pka(mol, interpreter_path) or []))
            if pkas:
                logd = logd_from_pkas(mol, 7.4, pkas)
                acids, _bases = classify_ionizable_centres(mol)
                # The BASIC centres are the higher pKa values, by the same
                # ordering convention logd_from_pkas already applies.
                basic = pkas[acids:]
                most_basic_pka = max(basic) if basic else None
    except Exception:  # noqa: BLE001 - the score is still useful without pKa
        logd, most_basic_pka = None, None

    components = cns_mpo_components(mol, logd=logd, most_basic_pka=most_basic_pka)
    scored = {name: score for name, (_value, score) in components.items() if score is not None}
    total = sum(scored.values())

    lines = []
    for name, (value, score) in components.items():
        if score is None:
            lines.append(f"{name}: unavailable (needs a configured pkasolver environment)")
        else:
            lines.append(f"{name}: {value:.2f} -> {score:.2f}")
    lines.append(f"CNS MPO score: {total:.2f} / {len(scored)}.00")
    if len(scored) < len(components):
        lines.append(
            "Scored out of 5, not 6: the pKa term is omitted rather than assumed favourable, "
            "which would inflate the score for every basic compound."
        )
    if logd is None:
        lines.append("LogD approximated by LogP (no pKa predictor configured).")
    lines.append("Favourable is generally taken as >= 4.0 (Wager et al.).")

    return AlertResult(
        alert_id="cns_mpo",
        name="CNS MPO Score",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="admet",
        provenance=Provenance(
            created_by="core",
            method="wager_cns_mpo",
            parameters={"total": total, "scored_terms": len(scored)},
        ),
    )


def compute_structural_frameworks(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    """Bemis-Murcko scaffolds -- the ring systems plus their connecting
    linkers, and the generic (all-carbon, all-single-bond) skeleton.

    Two entries because they answer different questions: the scaffold says
    what this molecule's core IS, the generic framework says what shape it
    is regardless of element or bond order, which is what groups
    structurally analogous series together.
    """
    from rdkit.Chem import AllChem

    entries: list[StructureEntry] = []
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    if scaffold is not None and scaffold.GetNumAtoms():
        prepared = Chem.Mol(scaffold)
        AllChem.Compute2DCoords(prepared)
        entries.append(
            StructureEntry(
                molblock=Chem.MolToMolBlock(prepared),
                label=f"Murcko scaffold: {Chem.MolToSmiles(scaffold)}",
                metadata={"smiles": Chem.MolToSmiles(scaffold), "kind": "scaffold"},
            )
        )
        # The generic framework answers a different question from the
        # scaffold -- what SHAPE this is, ignoring element and bond order.
        # Useful for grouping analogues, noise if you only wanted the core.
        generic = (
            MurckoScaffold.MakeScaffoldGeneric(scaffold)
            if (parameters or {}).get("include_generic", True)
            else None
        )
        if generic is not None and generic.GetNumAtoms():
            prepared_generic = Chem.Mol(generic)
            AllChem.Compute2DCoords(prepared_generic)
            entries.append(
                StructureEntry(
                    molblock=Chem.MolToMolBlock(prepared_generic),
                    label=f"Generic framework: {Chem.MolToSmiles(generic)}",
                    metadata={"smiles": Chem.MolToSmiles(generic), "kind": "generic"},
                )
            )

    name = "Structural Frameworks" if entries else "Structural Frameworks (acyclic - no scaffold)"
    return StructureSetResult(
        set_id="structural_frameworks",
        name=name,
        method="murcko",
        molecule_uuid=molecule_uuid,
        entries=entries,
        provenance=Provenance(created_by="core", method="murcko"),
    )
