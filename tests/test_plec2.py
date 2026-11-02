"""The second PLECscore test: its fidelity gate, the old tuple hash and the template rebuild."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_DIR = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"


def _load(name: str, filename: str):
    if str(_DIR) not in sys.path:
        sys.path.insert(0, str(_DIR))
    spec = importlib.util.spec_from_file_location(name, _DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("plec_core", "plec_core.py")
runner = _load("plec_rescore_runner_2", "plec_rescore_runner_2.py")


def test_the_fidelity_gate_needs_enough_receptors_and_a_high_enough_median():
    assert core.inputs_reproduce_training([0.6, 0.6, 0.6, 0.6]) is True
    assert core.inputs_reproduce_training([0.5, 0.5, 0.5, 0.5]) is True  # the boundary is inclusive
    assert core.inputs_reproduce_training([0.49, 0.49, 0.49, 0.49]) is False
    assert core.inputs_reproduce_training([0.9, 0.9, 0.9]) is False  # too few measured
    assert core.inputs_reproduce_training([]) is False


def test_the_gate_reads_the_median_not_the_mean():
    # one excellent receptor must not rescue four poor ones, nor one poor one sink four good ones
    assert core.inputs_reproduce_training([0.0, 0.0, 0.0, 0.0, 1.0]) is False
    assert core.inputs_reproduce_training([0.0, 0.7, 0.7, 0.7, 0.7]) is True


def test_the_sidecar_restates_the_training_set_it_cannot_import():
    assert set(runner.TRAINED_ON) == set(core.TRAINED_ON)


def test_the_restored_hash_gives_the_value_cpython_3_7_gave():
    # hash((1, 2, 3)) on CPython 3.7, 64-bit; 3.8 changed the algorithm and gives another number
    assert runner.python37_hash((1, 2, 3)) == 2528502973977326415
    assert hash((1, 2, 3)) != 2528502973977326415 or sys.version_info < (3, 8)


def test_the_restored_hash_handles_nested_tuples_and_negative_ints():
    inner = (6, 0, 2, 1, -1, 0, 1)
    assert runner.python37_hash(((inner,), 5)) == runner.python37_hash(((inner,), 5))
    assert runner.python37_hash(((6, 0, 2, 1, -1, 0, 1),)) != runner.python37_hash(((6, 0, 2, 1, 1, 0, 1),))
    # CPython hashes -1 as -2, so (-1,) and (-2,) collide by design
    assert runner.python37_hash((-1,)) == runner.python37_hash((-2,))
    assert 0 <= runner.python37_hash32(inner) <= 0xFFFFFFFF


@pytest.mark.parametrize(
    ("smiles", "formula"),
    [("OC(=O)c1ccccc1", "C7H6O2"), ("CC[NH3+]", "C2H8N+"), ("CC(=O)[O-]", "C2H3O2-")],
)
def test_a_pose_rebuilt_on_its_template_has_every_hydrogen_and_no_radicals(smiles, formula):
    pytest.importorskip("rdkit")
    openbabel = pytest.importorskip("openbabel")  # run_plec_test_2 imports the docking stack
    del openbabel
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem import rdMolDescriptors as descriptors

    second = _load("run_plec_test_2", "run_plec_test_2.py")
    template = Chem.MolFromSmiles(smiles)
    embedded = Chem.AddHs(template)
    AllChem.EmbedMolecule(embedded, randomSeed=7)
    # a pose as the PDBQT hands it back: heavy atoms and coordinates, every bond single
    pose = Chem.RWMol(Chem.RemoveHs(embedded))
    for bond in pose.GetBonds():
        bond.SetBondType(Chem.BondType.SINGLE)
        bond.SetIsAromatic(False)
    for atom in pose.GetAtoms():
        atom.SetIsAromatic(False)
        atom.SetFormalCharge(0)
        atom.SetNoImplicit(True)  # what a radical-prone, valence-unchecked read leaves behind
    rebuilt = second.on_template(Chem.RemoveHs(template), pose.GetMol())
    assert descriptors.CalcMolFormula(rebuilt) == formula
    assert all(atom.GetNumRadicalElectrons() == 0 for atom in rebuilt.GetAtoms())
