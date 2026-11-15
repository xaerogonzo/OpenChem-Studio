"""WP7 of docs/HYPERVALENT_COVERAGE_DESIGN.md: a structure the screen cannot read is never reported as "no matches".

Measured in the audit behind #598: the regulatory screen run on a held ClF3 (a structure RDKit refuses) answered "No matches in the 5 rulesets
consulted", a silent false negative: an unreadable structure matches nothing, and "no matches" reads as "not listed". The application's own
route refused it (the calculator is not on `HYPERVALENT_VERIFIED_CALCULATORS`), but the engine and the calculator function answered when handed such a Mol
directly. Every way a held structure can reach the screen is tested here and must refuse or fail closed; ordinary molecules are screened as before.

Nothing here reads a rule: the tests name no substance and assert nothing about any ruleset's content, only about whether a screen ran.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import HYPERVALENT_VERIFIED_CALCULATORS
from openchem.chem.regulatory.calculator import _shared_engine, compute_regulatory_screen
from openchem.chem.regulatory.engine import UnscreenableStructureError
from openchem.chem.synthesis_gate import GateOutcome, check_target, screen_nodes
from openchem.domain.calculator import CalculationRefusal
from openchem.domain.refusal_kinds import HYPERVALENT_UNSUPPORTED, RefusalKind
from tests.test_chem_engine import _hypervalent_molblock

HELD = {"ClF3": ("Cl", "F", 3), "BrF3": ("Br", "F", 3), "ClF5": ("Cl", "F", 5)}


@pytest.fixture(scope="module")
def rig():
    return build_service_container()


def _held(rig, spec) -> Chem.Mol:
    from openchem.domain.molecule import MoleculeModel

    model = MoleculeModel(display_name="held")
    rig.chemistry_engine.set_structure_from_molblock(model, _hypervalent_molblock(*spec), allow_hypervalent=True)
    return rig.chemistry_engine.mol_from_model(model, allow_hypervalent=True)


@pytest.mark.parametrize("name", HELD)
def test_the_engine_refuses_a_structure_it_cannot_read(rig, name):
    engine, _ = _shared_engine()
    with pytest.raises(UnscreenableStructureError):
        engine.screen(_held(rig, HELD[name]))


@pytest.mark.parametrize("name", HELD)
def test_the_calculator_refuses_instead_of_saying_no_matches(rig, name):
    with pytest.raises(CalculationRefusal) as caught:
        compute_regulatory_screen(_held(rig, HELD[name]), "u", {})
    assert caught.value.code == HYPERVALENT_UNSUPPORTED and caught.value.kind is RefusalKind.LIMIT
    assert "No matches" not in caught.value.detail


@pytest.mark.parametrize("name", HELD)
def test_the_gate_and_a_routes_node_screen_fail_closed(rig, name):
    smiles = Chem.MolToSmiles(_held(rig, HELD[name]))
    decision = check_target(smiles)
    assert decision.outcome is GateOutcome.UNSCREENED, "unscreened stops planning exactly as a refusal does"
    (node,) = screen_nodes([smiles])
    assert node.screened is False and node.findings == ()


def test_the_calculator_is_not_on_the_held_structure_list():
    assert "regulatory_screen" not in HYPERVALENT_VERIFIED_CALCULATORS


def test_through_the_service_a_held_structure_gets_a_refusal_and_no_report(rig, qapp):
    from openchem.events.events import PerAtomDataComputed, ReportComputed
    from tests.test_hypervalent_calculators import _held as _held_model
    from tests.test_hypervalent_calculators import _run_through_the_service

    molecule, _ = _held_model(rig, "ClF3")
    events = _run_through_the_service(rig, qapp, molecule, "regulatory_screen")
    assert not any(isinstance(e, ReportComputed) and e.report.report_id == "regulatory_screen" for e in events)
    failed = [e for e in events if isinstance(e, PerAtomDataComputed) and e.dataset.property_id == "regulatory_screen"]
    assert failed and "hypervalent" in (failed[-1].dataset.error or "")


@pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1", "FS(F)(F)(F)(F)F", "FP(F)(F)(F)F", "F[Xe]F", "[O-]Cl(=O)(=O)=O"])
def test_a_readable_structure_is_screened_as_before(smiles):
    """Including hypervalent ones RDKit accepts: they are readable, so they are screened."""
    mol = Chem.MolFromSmiles(smiles)
    engine, _ = _shared_engine()
    report = engine.screen(mol)
    assert report.rulesets_consulted, "the screen ran and says which rulesets it consulted"
    result = compute_regulatory_screen(mol, "u", {})
    assert result.error is None
