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
    assert recorded["input_source"] == "automatic_lowest_energy"
    assert recorded["input_conformer_id"] == conformers[1].conformer_id
    assert recorded["input_conformer_index"] == 1
    assert recorded["input_conformer_energy"] == -4.0


def test_provenance_says_drawing_when_that_is_what_was_used():
    model = _model()
    assert geometry_provenance(model, DRAWING)["input_source"] == "drawing"
    without = geometry_provenance(model, GEOMETRY)
    assert without["input_source"] == "drawing"
    assert "no conformer" in without["input_reason"]


def test_every_routing_provenance_key_is_prefixed():
    """The prefix is the collision fix, so it has to hold for every key
    this layer emits -- including the two only reachable on the
    no-conformer path, which a happy-path test never sees.

    ASSERTS THE PREFIX IS NON-EMPTY FIRST, and that line is not
    ceremony: `"anything".startswith("")` is True, so an empty
    `INPUT_PREFIX` makes the loop below pass vacuously. Caught by
    mutation -- setting the constant to `""` left this test green while
    the collision guard correctly failed.
    """
    from openchem.chem.calculation_input import INPUT_PREFIX

    assert INPUT_PREFIX, "an empty prefix makes every key below pass trivially"

    emitted = set()
    emitted |= set(geometry_provenance(_model(), DRAWING))
    emitted |= set(geometry_provenance(_model(), GEOMETRY))
    emitted |= set(
        geometry_provenance(_model([ConformerModel(molblock=_conformer_molblock(1), energy=1.0)]), GEOMETRY)
    )
    assert emitted, "nothing was emitted -- the check would be vacuous"
    unprefixed = sorted(k for k in emitted if not k.startswith(INPUT_PREFIX))
    assert not unprefixed, f"routing keys must be namespaced: {unprefixed}"


def test_no_calculator_provenance_key_collides_with_the_routing_layer():
    """Iterates the WHOLE REGISTRY, not the names anybody noticed.

    Two calculators collided before the prefix and only one was found by
    reading the code -- `steric_analysis` wrote `geometry_source` meaning
    how its cone-angle scan built its own conformers, and
    `molecular_dynamics` wrote `force_field` meaning what it ran the
    trajectory with. Neither is wrong; both wanted the same words for a
    different thing. A collision is silent: the calculator's value wins
    and the routing layer's is simply gone.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.services.calculator_registry import CalculatorRegistry

    engine = ChemistryEngine()
    model = _model([ConformerModel(molblock=_conformer_molblock(1), energy=-1.0)])
    routing_keys = set(geometry_provenance(model, GEOMETRY)) | set(
        geometry_provenance(model, DRAWING)
    )

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        try:
            registry.register(definition)
        except Exception:  # noqa: BLE001 - duplicate ids across runs
            pass

    checked, collisions = 0, []
    for definition in CALCULATOR_DEFINITIONS:
        mol = select_calculation_input(engine, model, definition.calculation_input)
        try:
            result = registry.compute(definition.calculator_id, mol, "u", {})
        except Exception:  # noqa: BLE001 - a calculator that refuses this molecule proves nothing
            continue
        provenance = getattr(result, "provenance", None)
        if provenance is None:
            continue
        checked += 1
        clash = routing_keys & set(provenance.parameters)
        if clash:
            collisions.append((definition.calculator_id, sorted(clash)))

    assert checked > 20, f"only {checked} calculators produced provenance -- the sweep is too thin"
    assert not collisions, f"calculator provenance keys collide with the routing layer: {collisions}"


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
    # and explicit hydrogens) and confirming the answer changed -- with a
    # positive control, since a test that cannot discriminate reports
    # "unchanged" for everything.
    #
    # Four candidates that looked geometry-sensitive were REJECTED, and
    # for a much stronger reason than the first pass recorded: a conformer
    # does not merely fail to help them, it BREAKS them. See the
    # structure-generator tests below.
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


# --------------------------------------------------------------------------
# Why the structure generators stayed on DRAWING.
#
# The first recorded reason was "they only differ because their
# StructureSetResult echoes coordinates into its output" -- true, and much
# too weak. Handing them a conformer BREAKS them, and these are the cases
# that show it. A future change that gives them GEOMETRY to be helpful is
# exactly what this guards against.
# --------------------------------------------------------------------------

UNDEFINED_STEREO = "CC(N)C(=O)O"  # alanine, stereocentre deliberately unspecified


def _conformer_of(smiles: str) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = 1
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    return Chem.MolToMolBlock(mol)


def _drawing_of(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _structure_smiles(calculator_id: str, molblock: str, engine: ChemistryEngine) -> list[str]:
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.services.calculator_registry import CalculatorRegistry

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        try:
            registry.register(definition)
        except Exception:  # noqa: BLE001 - duplicate ids across test runs
            pass
    result = registry.compute(calculator_id, engine.mol_from_molblock(molblock), "u", {})
    return sorted(entry.metadata.get("smiles", "?") for entry in result.entries)


def test_stereoisomer_enumeration_is_destroyed_by_a_conformer(engine):
    """A conformer has stereo PERCEIVED FROM ITS COORDINATES, so
    `onlyUnassigned=True` finds nothing left to vary.

    Alanine drawn without stereo has one undefined centre and two
    stereoisomers. Handed a conformer it has zero undefined centres and
    reports ONE -- whichever configuration the embedder happened to
    produce. That is not a worse answer, it is the feature silently not
    working: "what are the stereoisomers of what I drew" is the question,
    and the drawing is the only thing that can answer it.
    """
    drawing = _structure_smiles("stereoisomers", _drawing_of(UNDEFINED_STEREO), engine)
    conformer = _structure_smiles("stereoisomers", _conformer_of(UNDEFINED_STEREO), engine)
    assert len(drawing) == 2, drawing
    assert len(conformer) == 1, conformer


def test_tautomer_enumeration_is_corrupted_by_explicit_hydrogens(engine):
    """Not merely different -- WRONG. The conformer's explicit hydrogens
    send the enumerator into structures like `[H]O=C(O)...` and
    `[CH]([H])...` that are not tautomers of anything.

    Asserts the count grows AND that the drawing's forms are chemically
    clean, so a future RDKit that returns different-but-sane numbers
    fails loudly here rather than silently passing a weaker check.
    """
    drawing = _structure_smiles("tautomers", _drawing_of(UNDEFINED_STEREO), engine)
    conformer = _structure_smiles("tautomers", _conformer_of(UNDEFINED_STEREO), engine)
    assert len(conformer) > len(drawing), (drawing, conformer)
    assert not any("[H]" in smiles for smiles in drawing), drawing
    assert any("[H]" in smiles for smiles in conformer), conformer


def test_the_structure_generators_all_declare_drawing(engine):
    """The declaration, guarding the two behaviours above."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    by_id = {d.calculator_id: d for d in CALCULATOR_DEFINITIONS}
    for calculator_id in ("stereoisomers", "tautomers", "resonance_forms", "structural_frameworks"):
        assert by_id[calculator_id].calculation_input == DRAWING, calculator_id


def test_a_structure_generator_would_emit_3d_depictions_from_a_conformer(engine):
    """`structure_generators._entry` computes 2D coordinates only when the
    molecule has NO conformer, so a 3D input propagates straight into the
    structure grid -- which its own module docstring says renders as "a
    pile".

    `structural_frameworks` is immune because it calls `Compute2DCoords`
    unconditionally; the asymmetry is asserted so that if `_entry` is ever
    fixed to normalise coordinates, this test says so rather than quietly
    passing.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.services.calculator_registry import CalculatorRegistry

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        try:
            registry.register(definition)
        except Exception:  # noqa: BLE001
            pass

    def emitted_is_3d(calculator_id: str, molblock: str) -> list[bool]:
        result = registry.compute(
            calculator_id, engine.mol_from_molblock(molblock), "u", {}
        )
        flags = []
        for entry in result.entries:
            mol = Chem.MolFromMolBlock(entry.molblock, removeHs=False, sanitize=False)
            flags.append(bool(mol and mol.GetNumConformers() and mol.GetConformer().Is3D()))
        return flags

    conformer = _conformer_of(ETHYLMORPHINE)
    drawing = _drawing_of(ETHYLMORPHINE)
    for calculator_id in ("stereoisomers", "tautomers", "resonance_forms"):
        assert not any(emitted_is_3d(calculator_id, drawing)), calculator_id
        assert all(emitted_is_3d(calculator_id, conformer)), calculator_id
    # Immune: recomputes coordinates whatever it was given.
    assert not any(emitted_is_3d("structural_frameworks", conformer))
