"""The resonance option of the typed EEM models: checks R1 to R7 of `benchmarks/charges/models/eem_resonance_typing_design.md`, registered before this code was written.

R1  `averaged` gives the same charges however the structure is drawn (every resonance form drawn as the structure, and random SMILES spellings and atom orders carried back
    onto the same coordinates); `as_drawn` does NOT, and that failure is asserted as the demonstration. (The registered text said "random SMILES spellings" for the
    drawings; a spelling keeps the bond orders it is given, so the drawings that matter are the resonance forms, and the spellings test the atom bookkeeping.);
R2  the two atoms of one group get exactly equal parameters;
R3  the averaged difference within a group is never larger than the drawn one;
R4  a molecule with no variable atom gives bit-identical charges under all three values;
R5  a symmetric geometry gives the two oxygens equal charges once their parameters are equal (and unequal ones as drawn);
R6  a cap that is reached makes `averaged` refuse and leaves `as_drawn` alone;
R7  an independent solve (`eem_second_models_oracle.oracle_charges_resonance`) agrees to 1e-6 e.
"""

from __future__ import annotations

import numpy as np
import pytest
import test_eem_second_models as base
from rdkit import Chem

from openchem.chem import resonance_forms as rf
from openchem.chem import typed_eem as te

N = te.NEEMP2016_CCD_GEN_NPA
J = te.JIROUSKOVA2009_B3LYP_MK
oracle = base.oracle


@pytest.fixture(scope="module")
def molecules() -> dict[str, Chem.Mol]:
    built = {}
    for smiles in base.PANEL:
        mol = oracle.embedded(smiles)
        if mol is not None:
            built[smiles] = mol
    return built


def charges(mol, resonance, model=N) -> te.TypedEEMResult:
    return rf.typed_eem_for_molecule(mol, model, resonance=resonance)


def groups(mol, result) -> list[tuple[int, int]]:
    """Two variable atoms of one element bonded to the same single neighbour: the two oxygens of one nitro group or carboxylate."""
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]

    def neighbours(i):
        return {n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors()}

    var = result.variable_atoms
    return [(i, j) for k, i in enumerate(var) for j in var[k + 1 :] if symbols[i] == symbols[j] and len(neighbours(i)) == 1 and neighbours(i) == neighbours(j)]


def as_drawing(mol: Chem.Mol, form: Chem.Mol) -> Chem.Mol:
    """`form` (an RDKit resonance form: other bond orders and formal charges, same atoms) with `mol`'s coordinates."""
    variant = Chem.Mol(form)
    variant.RemoveAllConformers()
    conformer = Chem.Conformer(mol.GetConformer())
    variant.AddConformer(conformer, assignId=True)
    return variant


# --- R1 ------------------------------------------------------------------------------------------------------------------------------------


def _mapped_respelling(mol: Chem.Mol):
    """(variant molecule, permutation) where variant atom k is original atom permutation[k]."""
    tagged = Chem.Mol(mol)
    for atom in tagged.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    smiles = Chem.MolToSmiles(tagged, doRandom=True)
    params = Chem.SmilesParserParams()
    params.removeHs = False
    parsed = Chem.MolFromSmiles(smiles, params)
    assert parsed is not None and parsed.GetNumAtoms() == mol.GetNumAtoms()
    permutation = [atom.GetAtomMapNum() - 1 for atom in parsed.GetAtoms()]
    conformer = Chem.Conformer(parsed.GetNumAtoms())
    positions = mol.GetConformer().GetPositions()
    for k, original in enumerate(permutation):
        conformer.SetAtomPosition(k, tuple(float(v) for v in positions[original]))
    parsed.AddConformer(conformer, assignId=True)
    for atom in parsed.GetAtoms():
        atom.SetAtomMapNum(0)
    return parsed, permutation


def test_averaged_charges_do_not_depend_on_how_the_structure_is_drawn(molecules):
    checked = 0
    worst = 0.0
    for smiles, mol in molecules.items():
        base_result = charges(mol, "averaged")
        if base_result.status != "converged":
            continue
        checked += 1
        # 1. every resonance form drawn as the structure (RDKit's own forms: consistent bonds and formal charges, same atoms and coordinates)
        work = Chem.Mol(mol)
        Chem.Kekulize(work, clearAromaticFlags=True)
        for form in Chem.ResonanceMolSupplier(work):
            again = charges(as_drawing(mol, form), "averaged")
            assert again.status == "converged", smiles
            worst = max(worst, float(np.max(np.abs(again.charges - base_result.charges))))
        # 2. random SMILES spellings and atom orders, carried back onto the same coordinates
        for _ in range(6):
            variant, permutation = _mapped_respelling(mol)
            again = charges(variant, "averaged")
            assert again.status == "converged", smiles
            reordered = np.empty(len(permutation))
            for k, original in enumerate(permutation):
                reordered[original] = again.charges[k]
            worst = max(worst, float(np.max(np.abs(reordered - base_result.charges))))
    assert checked >= 60
    assert worst <= 1e-8, worst


def test_as_drawn_charges_do_depend_on_how_the_structure_is_drawn_on_the_groups_the_design_names(molecules):
    """The demonstration R1 expects: the plain model fails the test `averaged` passes, so the option is not decoration. The ways of drawing the same structure are its
    resonance forms (a SMILES spelling keeps the bond orders it is given, so respelling does not move the double bond; drawing it the other way round does)."""
    spread = {}
    for smiles, mol in molecules.items():
        base_result = charges(mol, "as_drawn")
        if base_result.status != "converged" or not base_result.variable_atoms:
            continue
        work = Chem.Mol(mol)
        Chem.Kekulize(work, clearAromaticFlags=True)
        seen = [charges(as_drawing(mol, form), "as_drawn").charges for form in Chem.ResonanceMolSupplier(work)]
        spread[smiles] = float(np.max(np.ptp(np.array(seen), axis=0)))
    assert len(spread) >= 10  # the twelve of the exploration
    assert sum(1 for s in spread.values() if s > 0.005) >= 8, spread


# --- R2, R3 --------------------------------------------------------------------------------------------------------------------------------


def test_the_two_atoms_of_one_group_get_exactly_equal_parameters_when_averaged(molecules):
    found = 0
    for smiles, mol in molecules.items():
        averaged = charges(mol, "averaged")
        if averaged.status != "converged" or not averaged.variable_atoms:
            continue
        for i, j in groups(mol, averaged):
            found += 1
            assert averaged.parameters_used[i] == averaged.parameters_used[j], smiles
    assert found >= 12


def test_the_averaged_difference_inside_a_group_is_never_larger_than_the_drawn_one(molecules):
    found = 0
    for smiles, mol in molecules.items():
        drawn = charges(mol, "as_drawn")
        averaged = charges(mol, "averaged")
        if averaged.status != "converged" or not averaged.variable_atoms:
            continue
        worst_drawn = {}
        for form in rf.resonance_bond_forms(mol).forms:
            result = te.typed_charges([a.GetSymbol() for a in mol.GetAtoms()], mol.GetConformer().GetPositions(), form, N, sum(a.GetFormalCharge() for a in mol.GetAtoms()))
            for i, j in groups(mol, averaged):
                worst_drawn[(i, j)] = max(worst_drawn.get((i, j), 0.0), abs(result.charges[i] - result.charges[j]))
        for (i, j), gap in worst_drawn.items():
            found += 1
            assert abs(averaged.charges[i] - averaged.charges[j]) <= gap + 1e-12, (smiles, i, j)
        assert drawn.status == "converged"
    assert found >= 12


# --- R4 ------------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [J, N])
def test_a_molecule_with_no_variable_atom_is_bit_identical_under_every_value(molecules, model):
    compared = 0
    for smiles, mol in molecules.items():
        drawn = charges(mol, "as_drawn", model)
        if drawn.status != "converged" or drawn.variable_atoms:
            continue
        for value in ("averaged", "refuse"):
            other = charges(mol, value, model)
            assert other.status == "converged" and np.array_equal(other.charges, drawn.charges), (smiles, value)
        compared += 1
    assert compared >= 40


def test_the_atoms_outside_a_group_move_only_a_little_and_the_size_is_reported_not_asserted_as_a_limit(molecules):
    moves = []
    for smiles, mol in molecules.items():
        drawn, averaged = charges(mol, "as_drawn"), charges(mol, "averaged")
        if averaged.status == "converged" and averaged.variable_atoms:
            outside = [i for i in range(mol.GetNumAtoms()) if i not in averaged.variable_atoms]
            moves.append(float(np.max(np.abs(averaged.charges[outside] - drawn.charges[outside]))) if outside else 0.0)
    assert moves and all(np.isfinite(moves))


# --- R5 ------------------------------------------------------------------------------------------------------------------------------------


def _symmetric_acetate() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)[O-]"))  # atoms: C0 methyl, C1 carboxyl, O2 (=O), O3 (O-), H4 H5 H6
    positions = {0: (-1.50, 0.0, 0.0), 1: (0.0, 0.0, 0.0), 2: (0.65, 1.10, 0.0), 3: (0.65, -1.10, 0.0), 4: (-1.90, 0.0, 1.0), 5: (-1.90, 0.87, -0.5), 6: (-1.90, -0.87, -0.5)}
    conformer = Chem.Conformer(mol.GetNumAtoms())
    for index, xyz in positions.items():
        conformer.SetAtomPosition(index, xyz)
    mol.AddConformer(conformer, assignId=True)
    return mol


def test_a_mirror_symmetric_acetate_gets_equal_oxygen_charges_when_averaged_and_unequal_ones_as_drawn():
    mol = _symmetric_acetate()
    averaged, drawn = charges(mol, "averaged"), charges(mol, "as_drawn")
    assert abs(averaged.charges[2] - averaged.charges[3]) <= 1e-9
    assert abs(drawn.charges[2] - drawn.charges[3]) > 0.01


# --- R6 ------------------------------------------------------------------------------------------------------------------------------------


def test_a_cap_that_is_reached_refuses_averaged_and_leaves_as_drawn_alone():
    mol = oracle.embedded("Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]")
    assert rf.resonance_bond_forms(mol).complete
    result = rf.typed_eem_for_molecule(mol, N, resonance="averaged", cap=5)
    assert result.status == rf.REFUSE_TOO_MANY_RESONANCE_FORMS and "as_drawn" in result.message
    assert rf.typed_eem_for_molecule(mol, N, resonance="as_drawn", cap=5).status == "converged"


# --- R7 ------------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("resonance", ["averaged", "as_drawn"])
def test_the_independent_resonance_solve_agrees_to_1e_6_and_accepts_the_same_molecules(molecules, resonance):
    agreed = 0
    worst = 0.0
    for smiles, mol in molecules.items():
        shipped = charges(mol, resonance)
        types, reference = oracle.oracle_charges_resonance(mol, N, resonance)
        assert (reference is not None) == (shipped.status == "converged"), (smiles, shipped.status)
        if reference is not None:
            agreed += 1
            worst = max(worst, float(np.max(np.abs(shipped.charges - reference))))
    assert agreed >= 60 and worst <= 1e-6, (agreed, worst)


# --- what a person is told, and the refusals ----------------------------------------------------------------------------------------------


def test_the_three_values_say_what_they_are(molecules):
    nitro = molecules["[O-][N+](=O)c1ccccc1"]
    averaged, drawn, refused = charges(nitro, "averaged"), charges(nitro, "as_drawn"), charges(nitro, "refuse")
    assert averaged.status == drawn.status == "converged" and averaged.forms_used == 2
    assert "extension of the published model" in averaged.claim and averaged.warnings == ()
    assert drawn.claim == "" and drawn.warnings and "depend on how this structure was drawn" in drawn.warnings[0]
    assert refused.status == te.REFUSE_RESONANCE_DEPENDENT and "averaged" in refused.message and "as_drawn" in refused.message


def test_a_molecule_with_nothing_variable_carries_no_claim_and_no_warning(molecules):
    for value in ("averaged", "as_drawn", "refuse"):
        result = charges(molecules["CCO"], value)
        assert result.status == "converged" and result.claim == "" and result.warnings == () and result.variable_atoms == ()


def test_the_default_of_the_one_call_is_averaged():
    import inspect

    assert inspect.signature(rf.typed_eem_for_molecule).parameters["resonance"].default == te.RESONANCE_AVERAGED
    assert rf.typed_eem_for_molecule(oracle.embedded("[O-][N+](=O)c1ccccc1"), N).resonance == te.RESONANCE_AVERAGED


def test_the_molecule_level_refusals_are_named():
    assert rf.typed_eem_for_molecule(oracle.embedded("C[N+](C)(C)C.[Cl-]"), N).status == rf.REFUSE_MULTIPLE_COMPONENTS
    assert rf.typed_eem_for_molecule(oracle.embedded("[CH3]"), N).status == rf.REFUSE_UNPAIRED_ELECTRON
    with pytest.raises(ValueError):
        rf.typed_eem_for_molecule(Chem.AddHs(Chem.MolFromSmiles("CC")), N)  # no conformer
    with pytest.raises(ValueError):
        rf.typed_eem_for_molecule(oracle.embedded("CC"), N, resonance="words")


def test_the_option_is_stored_as_codes():
    assert te.RESONANCE_VALUES == ("averaged", "as_drawn", "refuse")
