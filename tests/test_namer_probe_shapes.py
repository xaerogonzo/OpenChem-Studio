"""Shapes no corpus row contains: a snapshot of their names, and a read-back of each.

Naming round 8 rewrote the ring carve that every cation goes through, and its first draft of one rule made every bare +1 nitrogen a non-target. That lost
the retained ring name of every SATURATED quaternary ring cation ('1,1-dimethylpiperidin-1-ium' became '1,1-dimethylazinan-1-ium', and a quaternary
tetrahydroisoquinolinium became '(2-methyl-...-2-yl)methane'). The naming corpora, the addendum panels and the whole suite stayed green, because none of them
contains a saturated quaternary ring cation; only an ad-hoc probe found it.

TWO CHECKS, BECAUSE ONE IS NOT ENOUGH. A read-back through OPSIN sees a WRONG or unreadable name and cannot see a NON-PREFERRED one: the regression above still
read back as the right molecule, and a first version of this file that only read names back was shown, by putting the regression back, to miss it. So the
names are PINNED too: the fixture is `SMILES <TAB> name`, and any change fails the test until a person has looked at it and updated the fixture in the same
commit. That is deliberately rigid; the shapes are the ones this round found no other net for.

Each structure is named in the RDKit CANONICAL spelling, because `derived_name_for_structure` canonicalises and the engine's output depends on atom order (the
same guanidine was 'diaminomethyl' in one spelling and 'diaminomethylidene' in the other).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem, RDLogger

from openchem.chem import naming_providers as providers
from openchem.vendor.iupac_namer import name_smiles

FIXTURE = Path(__file__).parent / "fixtures" / "naming_cation_shapes.txt"


def _pinned() -> dict[str, str]:
    pinned: dict[str, str] = {}
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        smiles, _tab, name = line.partition("\t")
        assert name, f"a shape with no pinned name: {line!r}"
        assert smiles not in pinned, f"a shape is listed twice: {smiles}"
        pinned[smiles.strip()] = name.strip()
    return pinned


def _engine_name(smiles: str) -> str:
    return str(name_smiles(Chem.MolToSmiles(Chem.MolFromSmiles(smiles))))


def test_the_fixture_is_well_formed():
    pinned = _pinned()
    assert len(pinned) >= 100
    for smiles in pinned:
        assert Chem.MolFromSmiles(smiles) is not None, smiles


def test_no_pinned_name_has_moved():
    RDLogger.DisableLog("rdApp.*")
    moved = [
        f"{smiles}\n      pinned {pinned!r}\n      now    {now!r}"
        for smiles, pinned in _pinned().items()
        if (now := _engine_name(smiles)) != pinned
    ]
    assert not moved, (
        f"{len(moved)} pinned names moved. If each is an intended improvement, update tests/fixtures/naming_cation_shapes.txt in the same commit:\n  "
        + "\n  ".join(moved)
    )


def test_every_pinned_name_is_read_back_as_the_same_compound():
    if not providers.opsin_available():
        pytest.skip("OPSIN is not available")
    from py2opsin import py2opsin

    RDLogger.DisableLog("rdApp.*")
    pinned = _pinned()
    embedded = [f"{smiles} -> {name!r}" for smiles, name in pinned.items() if "NAMING ERROR" in name]
    assert not embedded, "an engine error is pinned as a name:\n  " + "\n  ".join(embedded)

    with providers._java_on_path():
        parsed = py2opsin(list(pinned.values()))
    failures = []
    for (smiles, name), got in zip(pinned.items(), parsed):
        mol = Chem.MolFromSmiles(smiles)
        candidate = Chem.MolFromSmiles(got) if got else None
        if candidate is None:
            failures.append(f"{smiles}\n      {name}\n      OPSIN could not read it")
        elif Chem.MolToSmiles(candidate) != Chem.MolToSmiles(mol) and not providers._same_compound(candidate, mol):
            failures.append(f"{smiles}\n      {name}\n      reads back as {got}")
    assert not failures, f"{len(failures)} of {len(pinned)} pinned names no longer read back:\n  " + "\n  ".join(failures)
