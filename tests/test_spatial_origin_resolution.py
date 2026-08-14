"""A spatial result must resolve back to the calculator that produced it.

The 3D overlay recomputes a result for the conformer actually on screen,
which means going from a `ReportResult` back to something runnable. That
resolution is `report_id -> CalculatorRegistry.get(...)`, and it is only
sound while every registry-executed calculator names its report after
itself. Measured when the overlay was designed: 49 registry-executable
calculators, 17 producing `ReportResult`s, zero mismatches.

**The RELATIONSHIP is the contract; those counts are not.** They may
change legitimately with any new calculator, so this enumerates from the
live registry -- the `test_declared_totals.py` pattern, which exists
because a hand-maintained list rotted into 27 wrong entries -- rather
than pinning numbers.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.domain.calculator import RegistryExecution
from openchem.domain.report import ReportResult


@pytest.fixture(scope="module")
def probe_molecule() -> Chem.Mol:
    """Something with a 3D conformer, so geometry calculators answer at
    all rather than failing before they can name themselves."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 1
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


@pytest.fixture(scope="module")
def produced_reports(probe_molecule) -> list[tuple[str, ReportResult]]:
    """`(calculator_id, result)` for every registry-executed calculator
    that returns a `ReportResult` on the probe molecule."""
    produced = []
    for definition in CALCULATOR_DEFINITIONS:
        if not isinstance(definition.execution, RegistryExecution):
            continue
        parameters = {p.name: p.default for p in definition.parameters}
        try:
            result = definition.execution.compute(probe_molecule, "probe", parameters)
        except Exception:  # noqa: BLE001 - a calculator declining this molecule is not the subject
            continue
        if isinstance(result, ReportResult):
            produced.append((definition.calculator_id, result))
    return produced


def test_every_report_names_itself_after_its_calculator(produced_reports):
    """The overlay's origin resolution, as a contract.

    A calculator whose `report_id` differs from its `calculator_id` would
    lose its overlay SILENTLY -- the result renders in the panel exactly
    as before and only the recompute fails to find it. This fails loudly
    instead, naming the offender.
    """
    mismatched = [
        (calculator_id, result.report_id)
        for calculator_id, result in produced_reports
        if result.report_id != calculator_id
    ]
    assert not mismatched, (
        "these calculators produce a report whose id does not match their own, so the "
        f"3D overlay could not resolve them back to anything runnable: {mismatched}"
    )


def test_the_probe_actually_produced_reports(produced_reports):
    """Assert the setup, never skip on it: with an empty list the guard
    above passes while checking nothing, which is the failure mode a
    vacuous enumeration always has."""
    assert len(produced_reports) >= 5, (
        f"only {len(produced_reports)} calculators returned a ReportResult; "
        "the guard above would be near-vacuous"
    )


def test_a_spatial_result_resolves_to_a_runnable_calculator(produced_reports):
    """The end the overlay actually needs: a result carrying geometry can
    be taken back to a `RegistryExecution` and run again."""
    by_id = {definition.calculator_id: definition for definition in CALCULATOR_DEFINITIONS}
    spatial = [(cid, r) for cid, r in produced_reports if r.spatial]
    assert spatial, "the probe molecule produced no spatial results, so this proves nothing"
    for calculator_id, _result in spatial:
        definition = by_id.get(calculator_id)
        assert definition is not None
        assert isinstance(definition.execution, RegistryExecution), (
            f"{calculator_id} produces spatial annotations but is service-executed, so the "
            "overlay cannot recompute it"
        )
