"""A held ClF3 in the REAL main window: no fault, a stated limit, and a real T-shaped conformer.

The window is built exactly as `test_main_window_conformers` builds it. What is asserted is what a person
would have met: the molecule is ClF3 (not the previous molecule), the always-on properties say why they are
absent instead of logging a traceback, calculators refuse with the typed limit, and conformer generation
gives the T-shape and keeps it through selecting and rebuilding the window's panels.
"""

from __future__ import annotations

import logging
import sys

import pytest

from openchem.domain.calculator import DRAWING, CalculationRefusal
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.refusal_kinds import HYPERVALENT_UNSUPPORTED, RefusalKind
from openchem.events.events import ConformersReady, DescriptorComputed, RecalculationDue
from tests.test_chem_engine import _hypervalent_molblock
from tests.test_main_window_conformers import _build_window, _drain


@pytest.fixture
def log_errors():
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.ERROR:
                records.append(record)

    handler = _Collector()
    logging.getLogger().addHandler(handler)

    # An exception inside a Qt slot never reaches `logging`: it goes to `sys.excepthook` and is printed, which is
    # how the ORCA panel's strict parse of a held ClF3 went unseen by the first version of this test.
    previous = sys.excepthook

    def _hook(kind, value, traceback):
        records.append(logging.LogRecord("excepthook", logging.ERROR, "", 0, f"{kind.__name__}: {value}", None, None))

    sys.excepthook = _hook
    yield records
    sys.excepthook = previous
    logging.getLogger().removeHandler(handler)


def _clf3(services) -> MoleculeModel:
    molecule = MoleculeModel(display_name="ClF3")
    services.chemistry_engine.set_structure_from_molblock(
        molecule, _hypervalent_molblock("Cl", "F", 3), allow_hypervalent=True
    )
    return molecule


def test_the_shared_input_boundary_refuses_with_the_typed_limit(qapp, tmp_path):
    from openchem.chem.calculation_input import resolve_calculation_input

    _, services = _build_window(qapp, tmp_path)
    molecule = _clf3(services)
    with pytest.raises(CalculationRefusal) as caught:
        resolve_calculation_input(services.chemistry_engine, molecule, DRAWING)
    refusal = caught.value
    assert refusal.code == HYPERVALENT_UNSUPPORTED
    assert refusal.kind is RefusalKind.LIMIT and refusal.inapplicable and refusal.classified


def test_a_held_clf3_runs_the_window_without_a_fault(qapp, tmp_path, log_errors):
    window, services = _build_window(qapp, tmp_path)
    states: dict[str, tuple] = {}
    services.event_bus.subscribe(
        DescriptorComputed,
        lambda e: states.__setitem__(
            e.descriptor.descriptor_id, (e.descriptor.cache_state, e.descriptor.error, e.descriptor.value)
        ),
    )
    molecule = _clf3(services)
    window.add_molecule(molecule)
    _drain(qapp)

    assert molecule.canonical_smiles == "FCl(F)F"
    assert states, "the always-on properties must have been dispatched and reported"
    completed = {k for k, (state, _, _) in states.items() if state == CacheState.COMPLETED}
    assert completed == {"mol_wt", "exact_mass", "formula", "formal_charge", "heavy_atom_count"}, completed
    # the textbook values for ClF3: M 92.447, exact mass 91.964, Hill formula ClF3, neutral, four atoms
    assert states["mol_wt"][2] == pytest.approx(92.447, abs=1e-3)
    assert states["exact_mass"][2] == pytest.approx(91.96406, abs=1e-4)
    assert states["formula"][2] == "ClF3"
    assert states["formal_charge"][2] == 0 and states["heavy_atom_count"][2] == 4
    refused = {k: err for k, (state, err, _) in states.items() if state == CacheState.FAILED}
    # everything that came out meaningless on ClF3 (Crippen logP 1.95, TPSA 0.0, QED, rule passes) is refused
    for descriptor_id in ("mol_logp", "tpsa", "qed", "lipinski_pass", "sa_score"):
        assert "hypervalent" in (refused.get(descriptor_id) or ""), descriptor_id
    assert log_errors == [], [r.getMessage() for r in log_errors]


def test_conformer_generation_gives_the_t_shape_and_leaves_the_window_clean(qapp, tmp_path, log_errors):
    import math

    import numpy as np

    window, services = _build_window(qapp, tmp_path)
    molecule = _clf3(services)
    window.add_molecule(molecule)
    _drain(qapp)
    ready: list = []
    services.event_bus.subscribe(ConformersReady, lambda e: ready.append(e.conformers))

    services.conformer_service.request_conformers(molecule, num_conformers=5, optimize=True)
    _drain(qapp)
    _drain(qapp)

    assert len(molecule.conformers) == 1, [c.method for c in molecule.conformers]
    conformer = molecule.conformers[0]
    assert conformer.method == "vsepr_template" and conformer.energy is None
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(conformer.molblock, sanitize=False, removeHs=False)
    conf = mol.GetConformer()
    pts = [np.array(conf.GetAtomPosition(i)) for i in range(4)]
    centre = next(i for i, a in enumerate(mol.GetAtoms()) if a.GetSymbol() == "Cl")
    ligands = [i for i in range(4) if i != centre]
    angles = sorted(
        round(
            math.degrees(
                math.acos(
                    float(
                        np.dot(pts[i] - pts[centre], pts[j] - pts[centre])
                        / (np.linalg.norm(pts[i] - pts[centre]) * np.linalg.norm(pts[j] - pts[centre]))
                    )
                )
            ),
            2,
        )
        for n, i in enumerate(ligands)
        for j in ligands[n + 1 :]
    )
    assert angles == [87.45, 87.45, 174.9]
    assert log_errors == [], [r.getMessage() for r in log_errors]


def test_the_properties_header_does_not_keep_the_previous_molecules_formula(qapp, tmp_path, log_errors):
    """Found by driving the real window: redrawing ethanol as ClF3 left 'C2H6O Molecule' in the header.

    The header is the `substance_analysis` report; it used to be refused for ClF3, so nothing replaced the old card.
    """
    window, services = _build_window(qapp, tmp_path)
    ethanol = MoleculeModel(display_name="Ethanol")
    services.chemistry_engine.set_structure_from_smiles(ethanol, "CCO")
    window.add_molecule(ethanol)
    _drain(qapp)
    card = window._property_panel._substance_card
    assert card.data().formula == "C2H6O", "the control: the header does show a formula for a normal molecule"

    window._editor.apply_edited_molblock(_hypervalent_molblock("Cl", "F", 3))
    # A canvas edit waits out the quiet period before anything is recomputed; publish what the scheduler would.
    services.event_bus.publish(RecalculationDue(molecule_uuid=ethanol.uuid))
    _drain(qapp)

    assert ethanol.canonical_smiles == "FCl(F)F"
    # Substance analysis is verified on held structures (`HYPERVALENT_VERIFIED_CALCULATORS`), so the header now says what
    # the molecule IS; before that it fell back to the name alone, and before THAT it kept "C2H6O".
    assert card.data().formula == "ClF3" and "C2H6O" not in card.summary_text()
    assert log_errors == [], [r.getMessage() for r in log_errors]
