"""The structure-coverage hooks of the calculators that declare one (`CalculatorDefinition.preflight`).

Design: `docs/STRUCTURE_COVERAGE_DESIGN.md`. Each hook is a few lines that CALL the calculator's own refusal function
and read the verdict off what it returns, so none of them holds a rule of its own: when a calculator is changed to
refuse less, the same call answers differently and the indicator on the row follows with no edit here. They live in
one module so that a reviewer can see every claim the application makes about a structure before it is run, and so
a hook never adds an import to a calculator's own file.

A hook returns a `Coverage` only when the calculator's own function decided; anything it could not decide (an
unreadable structure, which is a fault and not a limit) is None, and the row says nothing.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem import aromaticity, bond_dissociation, hansen, hlb, joback, proton_affinity
from openchem.chem.energetics import OxygenBalanceRefusal, calculator_balance
from openchem.chem.energetics import refusal_text as oxygen_balance_refusal_text
from openchem.domain.structure_coverage import Coverage


def griffin_hlb_coverage(mol: Chem.Mol) -> Coverage | None:
    """Griffin's HLB: the refusal of `griffin_hlb` itself."""
    result = hlb.griffin_hlb(mol)
    if result.refusal is hlb.HlbRefusal.NOT_A_STRUCTURE:
        return None
    return Coverage.covered() if result.applicable else Coverage.refuses(hlb.refusal_text(result))


def oxygen_balance_coverage(mol: Chem.Mol) -> Coverage | None:
    """Oxygen balance: the refusal of `calculator_balance`, the call `compute_oxygen_balance` makes (an element the
    source gives no product for is named)."""
    result = calculator_balance(mol)
    if result.refusal is OxygenBalanceRefusal.NOT_A_STRUCTURE:
        return None
    return Coverage.covered() if result.applicable else Coverage.refuses(oxygen_balance_refusal_text(result))


def joback_coverage(mol: Chem.Mol) -> Coverage | None:
    """Joback: the refusal of `fragment` itself, which `compute_joback` also reads."""
    result = joback.fragment(mol)
    return Coverage.covered() if result.applicable else Coverage.refuses(joback.refusal_text(result))


def hansen_coverage(mol: Chem.Mol) -> Coverage | None:
    """Hansen: the refusal of `fragment`, and a limit where it runs but a parameter has no published contribution.

    The second is the calculator's own `parameter_value`, which `compute_hansen` reports as "not available"
    for that parameter, so a row saying "with limits" matches a result that shows a gap.
    """
    result = hansen.fragment(mol)
    if result.refusal is hansen.HansenRefusal.NOT_A_STRUCTURE:
        return None
    if not result.applicable:
        return Coverage.refuses(hansen.refusal_text(result))
    missing = [which for which in hansen.PARAMETERS if hansen.parameter_value(result, which).value is None]
    if missing:
        names = ", ".join(hansen._LABELS[which] for which in missing)
        return Coverage.caveat(f"no value will be available for {names}: a group in this molecule has no published contribution for it.")
    return Coverage.covered()


def homa_coverage(mol: Chem.Mol) -> Coverage | None:
    """HOMA: the refusal of `compute_homa` (a structure with no ring); a missing 3D structure is not this hook's to say."""
    result = aromaticity.compute_homa(mol)
    if result.refusal in aromaticity._FAULTS:
        return None
    if not result.applicable:
        return Coverage.refuses(aromaticity.refusal_text(result.refusal, result.detail))
    gaps = [ring for ring in result.rings if not ring.applicable]
    if gaps:
        return Coverage.caveat(f"{len(gaps)} ring(s) will be reported as not available: {aromaticity.refusal_text(gaps[0].refusal, gaps[0].detail)}.")
    return Coverage.covered()


def bird_coverage(mol: Chem.Mol) -> Coverage | None:
    """Bird: the refusal of `compute_bird` (a structure with no ring), and a limit for a ring size it has no reference for."""
    result = aromaticity.compute_bird(mol)
    if result.refusal in aromaticity._FAULTS:
        return None
    if not result.applicable:
        return Coverage.refuses(aromaticity.refusal_text(result.refusal, result.detail))
    gaps = [ring for ring in result.rings if not ring.applicable]
    if gaps:
        return Coverage.caveat(f"{len(gaps)} ring(s) will be reported as not available: {aromaticity.refusal_text(gaps[0].refusal, gaps[0].detail)}.")
    return Coverage.covered()


def proton_affinity_coverage(mol: Chem.Mol) -> Coverage | None:
    """Proton affinity: the `check_scope` the window and the service run before a single job is written."""
    try:
        proton_affinity.check_scope(Chem.AddHs(mol))
    except proton_affinity.OutOfScope as scope:
        return Coverage.refuses(f"proton affinity is not computed for this structure: {scope}.")
    return Coverage.covered()


def bond_dissociation_coverage(mol: Chem.Mol) -> Coverage | None:
    """X-H bond dissociation enthalpy: the `check_scope` the window and the service run before a single job is written."""
    try:
        bond_dissociation.check_scope(Chem.AddHs(mol))
    except proton_affinity.OutOfScope as scope:
        return Coverage.refuses(f"a bond dissociation enthalpy is not computed for this structure: {scope}.")
    return Coverage.covered()
