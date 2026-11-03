"""`tools/naming_ring_table_vs_opsin.py`: which pairs it probes, what it skips, and that a swapped pair is what it sees."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import naming_ring_table_vs_opsin as probe  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES  # noqa: E402

# the curated neutral quinoline, with its real labels
QUINOLINE, _ENTRY = next((s, e) for s, e in _RING_CURATED_SMILES.items() if e["name"] == "quinoline" and "+" not in s)
TRUE = dict(_ENTRY["atom_locants"])


def _table(labels, smiles=QUINOLINE, name="quinoline"):
    return {smiles: {"name": name, "atom_locants": labels}}


def test_a_pair_is_two_labelled_hydrogen_bearing_atoms():
    from rdkit import Chem

    mol = Chem.MolFromSmiles(QUINOLINE)
    carbons = [a for a in TRUE if mol.GetAtomWithIdx(a).GetTotalNumHs() >= 1]
    probes = probe.build_probes(_table(TRUE), cap=1000)
    assert len(probes) == len(carbons) * (len(carbons) - 1) // 2
    assert {p[3] for p in probes} >= {"2,3", "5,8"}


def test_the_cap_samples_and_the_seed_fixes_it():
    a = probe.build_probes(_table(TRUE), cap=5)
    assert len(a) == 5 and a == probe.build_probes(_table(TRUE), cap=5)


def test_a_charged_or_unlabelled_entry_is_skipped():
    assert probe.build_probes({"c1cc[nH+]cc1": {"name": "pyridinium", "atom_locants": {0: 4}}}) == []
    assert probe.build_probes({QUINOLINE: {"name": "quinoline"}}) == []


def test_the_name_asked_of_opsin_cites_the_locants_in_order():
    names = {p[2] for p in probe.build_probes(_table(TRUE), cap=1000)}
    assert "2,3-dichloro-quinoline" in names and "5,8-dichloro-quinoline" in names


@needs_opsin
def test_the_true_labels_agree_and_a_swapped_pair_does_not():
    bad, total, unread = probe.run(_table(TRUE), cap=1000)
    assert not bad and total["quinoline"] > 0 and not unread
    by_label = {str(v): k for k, v in TRUE.items()}
    swapped = dict(TRUE)
    swapped[by_label["2"]], swapped[by_label["5"]] = 5, 2   # C2 and C5 exchanged: a pair can tell
    bad, _, _ = probe.run(_table(swapped), cap=1000)
    assert bad
