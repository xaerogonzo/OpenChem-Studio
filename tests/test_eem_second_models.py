"""C2, C3 and C4 of `benchmarks/charges/models/eem_second_models_preregistration.md`: the solver of the two further EEM models, held to an independent one.

C2  an independent solve (`benchmarks/charges/models/eem_second_models_oracle.py`: fixtures read directly, types from RDKit's own bonds, a different algebra) agrees with
    `chem/typed_eem.py` to 1e-6 e on every molecule both accept, and the two ACCEPT THE SAME MOLECULES;
C3  the charges do not depend on atom order, nor on which Kekule form an aromatic ring is drawn in (and if a form changed a type, this fails);
C4  every shipped hardness is positive and the charges sum to the net charge.

The oracle is loaded BY PATH under its own module name: a bare `import` of a benchmark script has once returned another benchmark's file of the same name.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import tomllib

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import typed_eem as te
from openchem.chem.charge_equilibration import REFUSE_OVERLAPPING_ATOMS

ROOT = pathlib.Path(__file__).resolve().parents[1]
J, N = te.JIROUSKOVA2009_B3LYP_MK, te.NEEMP2016_CCD_GEN_NPA


def _load_oracle():
    path = ROOT / "benchmarks" / "charges" / "models" / "eem_second_models_oracle.py"
    spec = importlib.util.spec_from_file_location("eem_second_models_oracle_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oracle = _load_oracle()

#: Molecules chosen so every type of both models is met at least once, plus the ones each model must refuse. Fixed before the run.
HAND_BUILT = [
    "O", "C", "CC", "C=C", "CO", "CCO", "CN", "CF", "CCl", "CBr", "CS", "CSC", "CC(=O)O", "CC(=O)N", "COC", "NC(=O)N", "C=O", "O=C=O", "N", "NN", "CC=O",
    "c1ccccc1", "Cc1ccccc1", "Oc1ccccc1", "Nc1ccccc1", "c1ccncc1", "c1cc[nH]c1", "c1ccoc1", "c1ccsc1", "c1ccc2ccccc2c1", "c1ccc2[nH]ccc2c1", "c1c[nH]cn1",
    "OC(=O)c1ccccc1", "[O-][N+](=O)c1ccccc1", "Clc1ccccc1", "Brc1ccccc1", "Fc1ccccc1",
    "CC#N", "C#C", "CC#C", "N#N",  # C3 and N3
    "CS(C)(=O)=O", "CS(C)=O", "CC(=S)C", "NS(=O)(=O)c1ccccc1",  # S2
    "COP(=O)(OC)OC", "CP(C)C", "B(C)(C)C", "CI", "C[Si](C)(C)C",  # P2, P1, B, I, Si
    "CC(=O)[O-]", "C[NH3+]", "[NH4+]", "C[N+](C)(C)C", "c1cc[nH+]cc1",  # ions
]


def _census_smiles() -> list[str]:
    data = tomllib.loads((ROOT / "tests" / "fixtures" / "census_panel.toml").read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if "smiles" in node:
                found.append(node["smiles"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return [s for s in found if "." not in s]


PANEL = list(dict.fromkeys(_census_smiles() + HAND_BUILT))


def _bonds(mol: Chem.Mol) -> list[tuple[int, int, int]]:
    work = Chem.Mol(mol)
    Chem.Kekulize(work, clearAromaticFlags=True)
    return [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(round(b.GetBondTypeAsDouble()))) for b in work.GetBonds()]


def _run(mol: Chem.Mol, model: str, bonds=None) -> te.TypedEEMResult:
    elements = [a.GetSymbol() for a in mol.GetAtoms()]
    net = sum(a.GetFormalCharge() for a in mol.GetAtoms())
    return te.typed_charges(elements, mol.GetConformer().GetPositions(), bonds if bonds is not None else _bonds(mol), model, net)


@pytest.fixture(scope="module")
def molecules() -> dict[str, Chem.Mol]:
    built = {}
    for smiles in PANEL:
        mol = oracle.embedded(smiles)
        if mol is not None:
            built[smiles] = mol
    return built


# --- C2 --------------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [J, N])
def test_the_shipped_solver_and_the_independent_one_accept_the_same_molecules_and_agree_to_1e_6(molecules, model):
    accepted = 0
    worst = 0.0
    for smiles, mol in molecules.items():
        shipped = _run(mol, model)
        types, reference = oracle.oracle_charges(mol, model)
        assert (reference is not None) == (shipped.status == "converged"), (smiles, shipped.status, shipped.message)
        assert tuple(types) == shipped.atom_types, smiles
        if reference is not None:
            accepted += 1
            worst = max(worst, float(np.max(np.abs(shipped.charges - reference))))
    assert worst <= 1e-6, worst
    # A pass on a handful of molecules would be a vacuous pass: both models must accept a real share of the panel.
    assert accepted >= 40, accepted


def test_the_panel_is_not_degenerate_every_type_each_model_has_is_met(molecules):
    for model in (J, N):
        seen = set()
        for mol in molecules.values():
            types, reference = oracle.oracle_charges(mol, model)
            if reference is not None:
                seen.update(types)
        expected = set(te.parameters()[model]["types"]) - te.OUT_OF_SCOPE_TYPES[model]
        assert seen == expected, (model, sorted(expected - seen))


def test_hydrogen_chloride_matches_the_closed_form_of_the_two_atom_system(qapp=None):
    # With q_H = -q_Cl = q the two rows differ to q (B_H + B_Cl - 2 kappa / r) = A_Cl - A_H, so q_H = (A_Cl - A_H) / (B_H + B_Cl - 2 kappa / r), r in angstrom.
    entry = te.parameters()[J]
    (a_h, b_h), (a_cl, b_cl), kappa = entry["types"]["H1"], entry["types"]["Cl1"], entry["kappa"]
    r = 1.27
    result = te.typed_charges(["H", "Cl"], [[0, 0, 0], [0, 0, r]], [(0, 1, 1)], J)
    expected = (a_cl - a_h) / (b_h + b_cl - 2 * kappa / r)
    assert result.status == "converged"
    assert result.charges[0] == pytest.approx(expected, abs=1e-12) and result.charges[1] == pytest.approx(-expected, abs=1e-12)
    in_bohr = (a_cl - a_h) / (b_h + b_cl - 2 * kappa / (r / 0.529177210903))
    assert abs(expected - in_bohr) > 0.005  # the unit is not decoration: bohr would give a different charge


# --- C3 --------------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [J, N])
def test_charges_do_not_depend_on_the_order_of_the_atoms(molecules, model):
    rng = np.random.default_rng(7)
    for smiles, mol in list(molecules.items())[:40]:
        base = _run(mol, model)
        if base.status != "converged":
            continue
        order = rng.permutation(mol.GetNumAtoms())
        shuffled = Chem.RenumberAtoms(mol, [int(i) for i in order])
        again = _run(shuffled, model)
        assert again.status == "converged"
        assert np.max(np.abs(again.charges - base.charges[order])) <= 1e-8, smiles


AROMATIC = [
    "c1ccccc1", "Cc1ccccc1", "Oc1ccccc1", "Nc1ccccc1", "c1ccncc1", "c1cc[nH]c1", "c1ccoc1", "c1ccsc1", "c1ccc2ccccc2c1", "c1ccc2[nH]ccc2c1", "c1c[nH]cn1",
    "OC(=O)c1ccccc1", "Clc1ccccc1", "c1cc[nH+]cc1", "c1ccc2ncccc2c1", "O=c1cc[nH]cc1",
]


@pytest.mark.parametrize("model", [J, N])
def test_charges_do_not_depend_on_which_kekule_form_a_ring_is_drawn_in(molecules, model):
    checked_forms = 0
    for smiles in AROMATIC:
        mol = molecules.get(smiles) or oracle.embedded(smiles)
        forms = [Chem.Mol(f) for f in Chem.ResonanceMolSupplier(mol, Chem.KEKULE_ALL)]
        assert forms, smiles
        reference = _run(mol, model)
        for form in forms:
            bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(round(b.GetBondTypeAsDouble()))) for b in form.GetBonds()]
            result = _run(mol, model, bonds)
            assert result.atom_types == reference.atom_types, (smiles, "a Kekule form changed an atom's type")
            if reference.status == "converged":
                assert np.max(np.abs(result.charges - reference.charges)) <= 1e-8, smiles
            checked_forms += 1
    assert checked_forms > len(AROMATIC)  # several molecules have more than one form, so this is not a single-form pass


#: FINDING OF C3, NOT A PASS: a charge-separated group written either way round gives its two equivalent oxygens different types (O1 and O2), so the model gives
#: them different charges depending on which one the drawing made double-bonded. Measured on the 77-molecule panel: 12 molecules, every one a nitro group or a
#: carboxylate. The plan's registered rule was about aromatic rings, which pass; this one was not foreseen and its decision belongs to the adapter that chooses the bond list.
CHARGE_SEPARATED = [Chem.MolFromSmarts("[N+](=O)[O-]"), Chem.MolFromSmarts("C(=O)[O-]")]


def _types_over_resonance_forms(mol: Chem.Mol) -> set[tuple[str, ...]]:
    elements = [a.GetSymbol() for a in mol.GetAtoms()]
    found = set()
    for form in Chem.ResonanceMolSupplier(mol, Chem.KEKULE_ALL):
        bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(round(b.GetBondTypeAsDouble()))) for b in form.GetBonds()]
        found.add(te.atom_types(elements, bonds))
    return found or {te.atom_types(elements, _bonds(mol))}


def test_atom_types_depend_on_the_drawing_only_for_nitro_groups_and_carboxylates(molecules):
    varying, invariant = [], []
    for smiles, mol in molecules.items():
        (varying if len(_types_over_resonance_forms(mol)) > 1 else invariant).append(smiles)
    has_group = lambda smiles: any(Chem.MolFromSmiles(smiles).HasSubstructMatch(q) for q in CHARGE_SEPARATED)  # noqa: E731
    assert varying and all(has_group(s) for s in varying), [s for s in varying if not has_group(s)]
    assert not [s for s in invariant if has_group(s)], "a molecule with such a group was invariant: the finding changed, read it again"
    assert len(varying) >= 10  # 12 on the panel when this was written; fewer would mean the panel changed under it


# --- C4 --------------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [J, N])
def test_every_shipped_hardness_is_positive(model):
    assert all(b > 0 for _a, b in te.parameters()[model]["types"].values())


@pytest.mark.parametrize("model", [J, N])
def test_the_charges_sum_to_the_net_charge_for_neutral_molecules_and_ions(molecules, model):
    seen_ion = False
    for smiles, mol in molecules.items():
        result = _run(mol, model)
        if result.status != "converged":
            continue
        net = sum(a.GetFormalCharge() for a in mol.GetAtoms())
        seen_ion = seen_ion or net != 0
        assert abs(float(result.charges.sum()) - net) <= 1e-10, smiles
    assert seen_ion


# --- the refusals the plan names, and what the data is ---------------------------------------------------------------------------------------


def _by_smiles(smiles: str, model: str) -> te.TypedEEMResult:
    mol = oracle.embedded(smiles)
    return _run(mol, model)


def test_a_sulfone_is_refused_by_j_which_names_n_and_accepted_by_n():
    refused = _by_smiles("CS(C)(=O)=O", J)
    assert refused.status == te.REFUSE_TYPE_NOT_PARAMETERISED and "S2" in refused.message
    assert refused.alternative == N and "different model" in refused.message
    assert _by_smiles("CS(C)(=O)=O", N).status == "converged"


def test_a_nitrile_is_refused_by_j_for_both_its_types_and_accepted_by_n():
    refused = _by_smiles("CC#N", J)
    assert refused.status == te.REFUSE_TYPE_NOT_PARAMETERISED and "C3" in refused.message and "N3" in refused.message and refused.alternative == N
    assert _by_smiles("CC#N", N).status == "converged"


def test_boron_and_iodine_and_silicon_are_refused_by_both_and_name_no_alternative():
    for smiles, atom_type in [("B(C)(C)C", "B"), ("CI", "I"), ("C[Si](C)(C)C", "Si")]:
        for model in (J, N):
            refused = _by_smiles(smiles, model)
            assert refused.status == te.REFUSE_TYPE_NOT_PARAMETERISED and atom_type in refused.message and refused.alternative == ""


def test_trivalent_phosphorus_is_refused_by_n_and_a_phosphate_is_accepted():
    assert _by_smiles("CP(C)C", N).status == te.REFUSE_TYPE_NOT_PARAMETERISED
    assert _by_smiles("COP(=O)(OC)OC", N).status == "converged"
    assert _by_smiles("COP(=O)(OC)OC", J).alternative == N


def test_zinc_is_in_the_papers_table_and_still_refused_by_j():
    assert "Zn1" in te.parameters()[J]["types"]
    result = te.typed_charges(["Zn", "Cl", "Cl"], [[0, 0, 0], [2.2, 0, 0], [-2.2, 0, 0]], [(0, 1, 1), (0, 2, 1)], J)
    assert result.status == te.REFUSE_TYPE_NOT_PARAMETERISED and "Zn1" in result.message


def test_an_atom_with_no_bond_is_refused_and_the_message_says_what_order_zero_means():
    result = te.typed_charges(["Cl"], [[0, 0, 0]], [], J, net_charge=-1.0)
    assert result.status == te.REFUSE_TYPE_NOT_PARAMETERISED and "Cl0" in result.message and "no bond" in result.message


def test_a_bond_list_that_is_not_a_kekule_structure_is_refused_by_name():
    for bonds in ([(0, 1, 4)], [(0, 0, 1)], [(0, 5, 1)], [(0, 1, 0)]):
        assert te.typed_charges(["C", "C"], [[0, 0, 0], [1.5, 0, 0]], bonds, J).status == te.REFUSE_BAD_BONDS


def test_two_atoms_on_top_of_each_other_are_refused():
    result = te.typed_charges(["C", "C"], [[0, 0, 0], [0.01, 0, 0]], [(0, 1, 1)], J)
    assert result.status == REFUSE_OVERLAPPING_ATOMS


def test_an_unknown_model_is_a_programming_error_not_a_refusal():
    with pytest.raises(ValueError):
        te.typed_charges(["H", "H"], [[0, 0, 0], [0.74, 0, 0]], [(0, 1, 1)], "bultinck2002a")


def test_the_shipped_data_is_what_the_builder_makes_from_the_fixtures_and_carries_their_hashes():
    import hashlib

    spec = importlib.util.spec_from_file_location("build_eem_second_models_under_test", ROOT / "tools" / "build_eem_second_models.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    shipped = json.loads(te.PARAMETERS_PATH.read_text(encoding="utf-8"))
    assert shipped == builder.build()
    for entry in shipped["models"].values():
        assert hashlib.sha256((ROOT / entry["fixture"]).read_bytes()).hexdigest() == entry["fixture_sha256"]
