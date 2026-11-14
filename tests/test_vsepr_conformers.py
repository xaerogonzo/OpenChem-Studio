"""Hypervalent molecules through the REAL conformer pipeline: built from the VSEPR template, labelled as such.

Before this, XeF2 came out bent (112 degrees), SF6 with 42 degree angles, and ClF3/BrF3 could not be
embedded at all. The pipeline pieces under test are the real ones (`search_conformers`,
`distinct_conformers`, `select_for_return`, `ConformerService`).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem

from openchem.chem.conformer_providers import (
    STOP_TEMPLATE,
    GenerationOptions,
    GeometryUnsupportedError,
    RDKitConformerProvider,
    distinct_conformers,
    search_conformers,
    select_for_return,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.conformer import (
    VSEPR_TEMPLATE,
    ConformerModel,
    conformer_choice_text,
)
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.services.conformer_service import ConformerService
from tests.test_chem_engine import _hypervalent_molblock
from tests.test_conformer_service import _drain


def _angle(mol: Chem.Mol, a: int, b: int, c: int) -> float:
    conf = mol.GetConformer()
    u = np.array(conf.GetAtomPosition(a)) - np.array(conf.GetAtomPosition(b))
    v = np.array(conf.GetAtomPosition(c)) - np.array(conf.GetAtomPosition(b))
    return math.degrees(math.acos(float(np.clip(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v)), -1.0, 1.0))))


def _search(mol: Chem.Mol, **kwargs):
    return search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions(), **kwargs)


def test_xef2_is_linear_not_bent():
    """RDKit's own embedding gave 112 degrees (measured, Phase 0)."""
    outcome = _search(Chem.MolFromSmiles("F[Xe]F"))
    ((mol, energy),) = outcome.pool
    assert _angle(mol, 0, 1, 2) == pytest.approx(180.0, abs=1e-6)
    assert energy is None, "a template has no energy; none may be invented"
    assert mol.GetConformer().Is3D()


def test_the_search_reports_a_template_not_a_force_field_run():
    outcome = _search(Chem.MolFromSmiles("F[Xe](F)(F)F"))
    assert outcome.stop_reason == STOP_TEMPLATE
    assert (outcome.attempted, outcome.embedded, outcome.batches) == (1, 1, 1)
    assert outcome.converged == 0, "`converged` means reached a minimum; this did not"
    assert outcome.convergence_failures == outcome.embedding_failures == 0
    assert outcome.unoptimised == 1
    assert outcome.geometry_method == VSEPR_TEMPLATE
    assert "not optimised" in outcome.geometry_note and "square planar" in outcome.geometry_note


def test_clf3_which_rdkit_cannot_embed_is_built_and_survives_the_pool_stages():
    """The Mol the engine's opt-in path returns, through the same stages the service runs."""
    mol = ChemistryEngine().hypervalent_mol_from_molblock(_hypervalent_molblock("Cl", "F", 3))
    outcome = _search(mol)
    pool = distinct_conformers(outcome.pool, rms_threshold=0.5)
    kept = select_for_return(pool, 10)
    assert len(kept) == 1
    built, energy = kept[0]
    assert energy is None
    assert [a.GetSymbol() for a in built.GetAtoms()] == ["Cl", "F", "F", "F"]
    angles = sorted(round(_angle(built, i, 0, j), 2) for i, j in ((1, 2), (1, 3), (2, 3)))
    assert angles == [87.45, 87.45, 174.9]


def test_a_recognised_molecule_without_a_geometry_fails_loudly_instead_of_embedding():
    with pytest.raises(GeometryUnsupportedError) as caught:
        _search(Chem.MolFromSmiles("ClI(Cl)Cl"))  # ICl3: RDKit accepts it and embeds it planar; no reference recorded
    assert "wrong shape" in str(caught.value)


def test_ordinary_molecules_still_use_the_search():
    outcome = search_conformers(
        RDKitConformerProvider(random_seed=1),
        Chem.MolFromSmiles("CCO"),
        True,
        GenerationOptions(max_embeddings=10, embedding_batch_size=5),
    )
    assert outcome.stop_reason != STOP_TEMPLATE
    assert outcome.unoptimised == 0 and outcome.geometry_method == ""
    assert outcome.converged > 0 and all(energy is not None for _, energy in outcome.pool)


def test_the_template_is_deterministic_and_the_input_untouched():
    mol = Chem.MolFromSmiles("FS(F)(F)F")
    before = Chem.MolToMolBlock(mol)
    first = _search(mol).pool[0][0]
    second = _search(mol).pool[0][0]
    assert Chem.MolToMolBlock(first) == Chem.MolToMolBlock(second)
    assert Chem.MolToMolBlock(mol) == before
    assert mol.GetNumConformers() == 0


def test_progress_and_atom_tags_pass_through():
    from openchem.chem.atom_identity import recorded_drawing_ids, tag_drawing_atoms

    mol = Chem.MolFromSmiles("F[Xe]F")
    tag_drawing_atoms(mol)
    calls: list[tuple[int, int]] = []
    outcome = _search(mol, on_progress=lambda done, total: calls.append((done, total)))
    assert calls == [(1, 1)]
    assert recorded_drawing_ids(outcome.pool[0][0]) == recorded_drawing_ids(mol) == [0, 1, 2]


def test_the_service_labels_it_a_template_not_a_force_field_conformer(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "F[Xe](F)(F)F")
    states: list[ConformerJobStateChanged] = []
    bus.subscribe(ConformerJobStateChanged, states.append)
    ready: list[list[ConformerModel]] = []
    bus.subscribe(ConformersReady, lambda e: ready.append(e.conformers))

    service.request_conformers(model, num_conformers=10, optimize=True)
    _drain(qapp)

    assert states[-1].state == CacheState.COMPLETED
    assert "not optimised" in states[-1].message
    ((conformer,),) = ready
    assert conformer.method == VSEPR_TEMPLATE
    assert conformer.energy is None
    parameters = conformer.provenance.parameters
    assert parameters["force_field"] is None and parameters["energy_window"] is None
    assert parameters["geometry_method"] == VSEPR_TEMPLATE
    assert parameters["conformers_unoptimised"] == 1 and parameters["conformers_converged"] == 0
    assert conformer.drawing_atom_ids == [0, 1, 2, 3, 4]  # input order kept: F, Xe, F, F, F
    assert conformer_choice_text([conformer], 0) == "1 - idealised VSEPR geometry, not optimised"
    # the stored geometry is square planar, read back through the engine like every viewer does
    stored = engine.mol_from_molblock(conformer.molblock)
    centre = next(a.GetIdx() for a in stored.GetAtoms() if a.GetSymbol() == "Xe")
    ligands = [a.GetIdx() for a in stored.GetAtoms() if a.GetIdx() != centre]
    found = sorted(round(_angle(stored, i, centre, j)) for n, i in enumerate(ligands) for j in ligands[n + 1 :])
    assert found == [90] * 4 + [180] * 2


def test_the_service_reports_an_unsupported_structure_as_a_failure(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "ClI(Cl)Cl")
    states: list[ConformerJobStateChanged] = []
    bus.subscribe(ConformerJobStateChanged, states.append)

    service.request_conformers(model, num_conformers=3, optimize=True)
    _drain(qapp)

    assert states[-1].state == CacheState.FAILED
    assert "wrong shape" in states[-1].message


@pytest.mark.parametrize(
    ("smiles", "shape"),
    [
        ("F[Xe](F)(F)(F)=O", "square pyramidal"),
        ("F[Xe](F)(=O)=O", "seesaw"),
        ("FS(F)(F)(F)=O", "trigonal bipyramidal"),
        ("FS(F)(F)(F)(F)Cl", "octahedral"),
    ],
)
def test_oxo_and_mixed_ligand_molecules_are_built_from_their_measured_geometry(smiles, shape):
    """RDKit accepts these and, left to itself, embeds them with wrong angles; the template is used instead."""
    outcome = _search(Chem.MolFromSmiles(smiles))
    ((mol, energy),) = outcome.pool
    assert energy is None and outcome.geometry_method == VSEPR_TEMPLATE
    assert shape in outcome.geometry_note
    assert mol.GetConformer().Is3D()


def test_a_drawn_clf3o_which_rdkit_refuses_is_held_and_built():
    from rdkit.Chem import AllChem

    drawn = Chem.MolFromSmiles("FCl(F)(F)=O", sanitize=False)
    for atom in drawn.GetAtoms():
        atom.SetNoImplicit(True)
    drawn.UpdatePropertyCache(strict=False)
    AllChem.Compute2DCoords(drawn)
    mol = ChemistryEngine().hypervalent_mol_from_molblock(Chem.MolToMolBlock(drawn))
    outcome = _search(mol)
    ((built, energy),) = outcome.pool
    assert energy is None
    centre = next(a.GetIdx() for a in built.GetAtoms() if a.GetSymbol() == "Cl")
    oxygen = next(a.GetIdx() for a in built.GetAtoms() if a.GetSymbol() == "O")
    conf = built.GetConformer()
    length = np.linalg.norm(np.array(conf.GetAtomPosition(oxygen)) - np.array(conf.GetAtomPosition(centre)))
    assert length == pytest.approx(1.405, abs=1e-6)


def test_ordinary_oxo_molecules_still_use_the_search():
    outcome = search_conformers(
        RDKitConformerProvider(random_seed=1),
        Chem.MolFromSmiles("OS(=O)(=O)O"),
        True,
        GenerationOptions(max_embeddings=10, embedding_batch_size=5),
    )
    assert outcome.stop_reason != STOP_TEMPLATE and outcome.unoptimised == 0
