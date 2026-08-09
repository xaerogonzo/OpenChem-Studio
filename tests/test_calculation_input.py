"""Which molecule a calculator is handed, and why it is not always the best one.

Every registered calculator ran on the 2D DRAWING -- the Properties panel
reported "The available conformer is 2D" while the 3D viewer showed
"Conformer 3/3". Closing that is not simply "give everyone the
conformer": a conformer molblock carries EXPLICIT HYDROGENS, and
ethylmorphine is 23 atoms as drawn against 46 as a conformer. Measured
across all 49 registered calculators, 8 return a different number for
that reason alone and are not wrong today.
"""

from __future__ import annotations

from functools import lru_cache

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculation_input import (
    canonical_conformer,
    geometry_provenance,
    select_calculation_input,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel

ETHYLMORPHINE = "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)OCC)O[C@H]3[C@H](C=C4)O"


def _drawing() -> str:
    mol = Chem.MolFromSmiles(ETHYLMORPHINE)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


@lru_cache(maxsize=None)
def _conformer_molblock(seed: int) -> str:
    """Cached: each embed-and-minimise of a 46-atom molecule is ~0.5 s and
    this file asks for the same few seeds repeatedly.

    The seed goes ON the params object -- `EmbedMolecule(mol, params,
    randomSeed=...)` is not a signature RDKit accepts, and passing it that
    way raises a Boost ArgumentError rather than being ignored.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles(ETHYLMORPHINE))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    return Chem.MolToMolBlock(mol)


def _model(conformers: list[ConformerModel] | None = None) -> MoleculeModel:
    return MoleculeModel(
        display_name="ethylmorphine", molblock=_drawing(), conformers=conformers or []
    )


@pytest.fixture(scope="module")
def engine() -> ChemistryEngine:
    return ChemistryEngine()


# --------------------------------------------------------------------------
# The 3 x 2 matrix. Written out rather than left implicit, because the old
# behaviour was `conformers[0] if conformers else drawing` and the new
# abstraction has to preserve it exactly where it was already right.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, 1, 3])
def test_a_drawing_calculator_always_receives_the_drawing(engine, count):
    """Including when conformers exist -- THE regression guard.

    Eight registered calculators (topology_analysis,
    topology_distance_degree, topology_eccentricity, crippen_logp_contrib,
    crippen_mr_contrib, bbb_descriptors, locants, oxidation_states) return
    a different number when handed a conformer, purely because it carries
    explicit hydrogens. A Wiener index over 46 atoms is a different number
    from one over 23; neither is wrong for its input, but only one matches
    what the app has always reported.

    Fails if the default ever flips to GEOMETRY.
    """
    conformers = [
        ConformerModel(molblock=_conformer_molblock(seed), energy=float(seed))
        for seed in range(1, count + 1)
    ]
    model = _model(conformers)
    mol = select_calculation_input(engine, model, DRAWING)
    assert mol.GetNumAtoms() == engine.mol_from_model(model).GetNumAtoms()
    assert not mol.GetConformer().Is3D()


def test_no_conformers_means_byte_identical_input_for_both_policies(engine):
    """The change is infrastructure-level; this protects everything that
    existed before it. A molecule with no conformers must reach every
    calculator exactly as it did, whatever the calculator declares."""
    model = _model()
    drawing = select_calculation_input(engine, model, DRAWING)
    geometry = select_calculation_input(engine, model, GEOMETRY)
    baseline = engine.mol_from_model(model)
    assert Chem.MolToMolBlock(drawing) == Chem.MolToMolBlock(baseline)
    assert Chem.MolToMolBlock(geometry) == Chem.MolToMolBlock(baseline)


def test_one_conformer_is_the_one_a_geometry_calculator_gets(engine):
    molblock = _conformer_molblock(1)
    model = _model([ConformerModel(molblock=molblock, energy=-3.0)])
    mol = select_calculation_input(engine, model, GEOMETRY)
    assert Chem.MolToMolBlock(mol) == Chem.MolToMolBlock(engine.mol_from_molblock(molblock))


def test_many_conformers_select_the_lowest_energy_one(engine):
    """...by ENERGY, not by position. The list is deliberately built out
    of order so that "conformers[0]" would pick the wrong one."""
    conformers = [
        ConformerModel(molblock=_conformer_molblock(1), energy=12.0),
        ConformerModel(molblock=_conformer_molblock(2), energy=-4.0),
        ConformerModel(molblock=_conformer_molblock(3), energy=7.0),
    ]
    model = _model(conformers)
    assert canonical_conformer(model) is conformers[1]
    mol = select_calculation_input(engine, model, GEOMETRY)
    assert Chem.MolToMolBlock(mol) == Chem.MolToMolBlock(
        engine.mol_from_molblock(conformers[1].molblock)
    )


# --------------------------------------------------------------------------
# Representation, not just Is3D()
# --------------------------------------------------------------------------


def test_a_geometry_calculator_receives_the_same_graph_with_hydrogens_and_coordinates(engine):
    """`Is3D() == True` ALONE DOES NOT PROVE THE CALCULATOR GOT THE RIGHT
    MOLECULE, and conflating geometry with hydrogen representation is the
    entire bug this policy exists for. All three properties are checked
    separately: same heavy-atom graph, plus explicit hydrogens, plus real
    coordinates.
    """
    model = _model([ConformerModel(molblock=_conformer_molblock(1), energy=0.0)])
    drawn = engine.mol_from_model(model)
    mol = select_calculation_input(engine, model, GEOMETRY)

    # ...the same heavy-atom graph
    def heavy(m):
        return sorted(a.GetAtomicNum() for a in m.GetAtoms() if a.GetAtomicNum() > 1)

    def heavy_charges(m):
        return sorted(a.GetFormalCharge() for a in m.GetAtoms() if a.GetAtomicNum() > 1)

    assert heavy(mol) == heavy(drawn)
    assert heavy_charges(mol) == heavy_charges(drawn)
    assert Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(mol))) == Chem.MolToSmiles(
        Chem.RemoveHs(Chem.Mol(drawn))
    )

    # ...plus explicit hydrogens
    hydrogens = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 1)
    assert hydrogens > 0
    assert mol.GetNumAtoms() > drawn.GetNumAtoms()

    # ...plus real 3D coordinates
    assert mol.GetConformer().Is3D()


# --------------------------------------------------------------------------
# Edge cases a saved project really contains
# --------------------------------------------------------------------------


def test_an_energyless_conformer_does_not_break_selection(engine):
    """A project saved before energies were recorded, or generated with
    optimize=False. Geometry is usable without an energy -- only the
    ORDERING needs one -- so this must select rather than crash."""
    conformers = [
        ConformerModel(molblock=_conformer_molblock(1), energy=None),
        ConformerModel(molblock=_conformer_molblock(2), energy=None),
    ]
    model = _model(conformers)
    assert canonical_conformer(model) is conformers[0]
    assert select_calculation_input(engine, model, GEOMETRY).GetConformer().Is3D()


def test_an_energised_conformer_wins_over_an_energyless_one(engine):
    """Mixed, which is what a project gains one regeneration at a time."""
    conformers = [
        ConformerModel(molblock=_conformer_molblock(1), energy=None),
        ConformerModel(molblock=_conformer_molblock(2), energy=5.0),
    ]
    assert canonical_conformer(_model(conformers)) is conformers[1]


def test_an_unparseable_conformer_falls_back_to_the_drawing(engine):
    """Rather than failing the calculation -- which is what
    `batch_service` already did for this case, and is the precedent."""
    model = _model([ConformerModel(molblock="not a molblock", energy=0.0)])
    mol = select_calculation_input(engine, model, GEOMETRY)
    assert Chem.MolToMolBlock(mol) == Chem.MolToMolBlock(engine.mol_from_model(model))


def test_a_flat_conformer_is_not_treated_as_geometry(engine):
    """`GetNumConformers() > 0` is true for anything drawn in the 2D
    editor and is useless as a check; `Is3D()` is what distinguishes
    them. A conformer that is somehow flat must not be presented to a
    geometry calculator as though it were real."""
    model = _model([ConformerModel(molblock=_drawing(), energy=0.0)])
    mol = select_calculation_input(engine, model, GEOMETRY)
    assert not mol.GetConformer().Is3D()
    assert Chem.MolToMolBlock(mol) == Chem.MolToMolBlock(engine.mol_from_model(model))


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_provenance_names_the_conformer_by_id_not_only_by_position():
    """Index 0 today is index 3 tomorrow. A result that cites only a
    position cannot be traced back to a geometry once anything re-sorts
    the list, so the stable id is what has to travel."""
    conformers = [
        ConformerModel(molblock=_conformer_molblock(1), energy=12.0),
        ConformerModel(molblock=_conformer_molblock(2), energy=-4.0),
    ]
    model = _model(conformers)
    recorded = geometry_provenance(model, GEOMETRY)
    assert recorded["geometry_source"] == "automatic_lowest_energy"
    assert recorded["conformer_id"] == conformers[1].conformer_id
    assert recorded["conformer_index"] == 1
    assert recorded["conformer_energy"] == -4.0


def test_provenance_says_drawing_when_that_is_what_was_used():
    model = _model()
    assert geometry_provenance(model, DRAWING)["geometry_source"] == "drawing"
    without = geometry_provenance(model, GEOMETRY)
    assert without["geometry_source"] == "drawing"
    assert "no conformer" in without["geometry_reason"]


# --------------------------------------------------------------------------
# The declaration, checked against what is REGISTERED rather than a list
# kept beside it -- the direction that caught the two missing help topics.
# --------------------------------------------------------------------------


def test_every_calculator_declares_a_known_calculation_input():
    """A closed vocabulary, for the same reason `applies_to` is one: a
    typo would route a calculator to the wrong representation and still
    look completely fine."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.calculator import CALCULATION_INPUTS

    offenders = [
        (d.calculator_id, d.calculation_input)
        for d in CALCULATOR_DEFINITIONS
        if d.calculation_input not in CALCULATION_INPUTS
    ]
    assert not offenders, f"unknown calculation_input: {offenders}"


def test_geometry_is_opt_in_and_the_default_is_the_drawing():
    """The default must stay DRAWING.

    Not a style point: eight registered calculators return a different
    number when handed a conformer purely because it carries explicit
    hydrogens, so flipping the default silently changes published values
    for molecules that happen to have conformers. A calculator registered
    without a thought keeps today's behaviour.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

    bare = CalculatorDefinition(
        calculator_id="x",
        display_name="x",
        category="x",
        description="x",
        execution=RegistryExecution(compute=lambda *a: None),
    )
    assert bare.calculation_input == DRAWING

    declared = {d.calculator_id for d in CALCULATOR_DEFINITIONS if d.calculation_input == GEOMETRY}
    # The set is small and every member was checked individually by
    # destroying the geometry (flattening z while keeping the same atoms
    # and explicit hydrogens) and confirming the answer changed. Four
    # candidates that looked geometry-sensitive were REJECTED that way --
    # resonance_forms, stereoisomers, tautomers and structural_frameworks
    # differ only because their StructureSetResult echoes coordinates into
    # its own output, and their chemistry is unchanged.
    assert declared == {
        "atom_sasa",
        "dipole_moment",
        "geometry_analysis",
        "interaction_analysis",
        "molecular_dynamics",
        "steric_analysis",
        "surface_analysis",
    }


def test_the_topological_calculators_stayed_on_the_drawing():
    """Named individually because these are the measured regression risk.

    Each returns a different number when handed a conformer, for a reason
    that has nothing to do with geometry: 46 atoms instead of 23.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    by_id = {d.calculator_id: d for d in CALCULATOR_DEFINITIONS}
    for calculator_id in (
        "topology_analysis",
        "topology_distance_degree",
        "topology_eccentricity",
        "crippen_logp_contrib",
        "crippen_mr_contrib",
        "bbb_descriptors",
        "locants",
        "oxidation_states",
    ):
        assert by_id[calculator_id].calculation_input == DRAWING, calculator_id
