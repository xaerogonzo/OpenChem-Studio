"""The pose-agreement analysis: its counting and its test."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

_DIR = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("pose_agreement", _DIR / "pose_agreement.py")
agreement = importlib.util.module_from_spec(_spec)
sys.modules["pose_agreement"] = agreement
_spec.loader.exec_module(agreement)


def test_the_fisher_test_matches_a_hand_count():
    # 2x2 [[3, 1], [1, 3]]: P(at least 3 right in the first group) = (16 + 1) / 70
    assert agreement.one_sided_fisher(3, 1, 1, 3) == pytest.approx(17 / 70)
    assert agreement.one_sided_fisher(2, 2, 2, 2) == pytest.approx(53 / 70)
    assert agreement.one_sided_fisher(0, 0, 3, 3) == 1.0


def _block(shift: float) -> str:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=3)
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        x, y, z = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (x + shift, y, z))
    return Chem.MolToMolBlock(mol)


def test_k_counts_the_other_poses_within_two_angstrom_of_pose_one(tmp_path):
    pytest.importorskip("rdkit")
    blocks = [_block(0.0), _block(0.5), _block(8.0)]  # pose 2 agrees with pose 1, pose 3 does not
    (tmp_path / "poses.json").write_text(json.dumps(
        {"rmsd": [1.0, 3.0, 9.0], "molblocks": blocks}), encoding="utf-8")
    assert agreement.agreement(tmp_path) == (3, 1, True)


def test_a_receptor_without_a_measured_first_pose_is_left_out(tmp_path):
    (tmp_path / "poses.json").write_text(json.dumps({"rmsd": [None, 1.0], "molblocks": ["x", "y"]}),
                                         encoding="utf-8")
    assert agreement.agreement(tmp_path) is None
