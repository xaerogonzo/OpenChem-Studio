"""The ring table's atom -> locant maps, held to what a map has to be.

Naming round 4 found eleven entries whose map was stored INVERTED (locant ->
atom: "4: 0", "5: 1"), so one ring atom had no locant and the others were
misplaced; for 2,3-dihydrofuran and 2,3-dihydro-1H-pyrrole the engine then
named a different molecule ("3-fluoro-2,3-dihydrofuran" for the 4-fluoro
compound). Nothing checked a map's SHAPE, which is what inversion breaks.

The second half checks `fusion_locants.derive_fusion_locants`, which fills
the fusion carbons an entry leaves out, against the entries that already
give them.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.vendor.iupac_namer import data_loader
from openchem.vendor.iupac_namer.ring_naming.fusion_locants import derive_fusion_locants


def _maps():
    for smiles, record in data_loader._RING_CURATED_SMILES.items():
        locants = record.get("atom_locants")
        mol = Chem.MolFromSmiles(smiles)
        if locants and mol is not None:
            yield record["name"], smiles, mol, locants


def test_every_map_goes_from_ring_atom_to_a_real_locant():
    wrong = []
    checked = 0
    for name, smiles, mol, locants in _maps():
        checked += 1
        n = mol.GetNumAtoms()
        keys_ok = all(isinstance(k, int) and 0 <= k < n and mol.GetAtomWithIdx(k).IsInRing() for k in locants)
        no_zero = all(str(v) != "0" for v in locants.values())
        unique = len({str(v) for v in locants.values()}) == len(locants)
        if not (keys_ok and no_zero and unique):
            wrong.append(f"{name} {smiles}: {locants}")
    # A guard over nothing passes for the wrong reason; 280+ maps were
    # measured on 2026-09-18.
    assert checked > 250, checked
    assert not wrong, "\n".join(wrong)


def test_the_fusion_walk_reproduces_the_table_where_the_table_is_complete():
    # The RAW table: the lookup's own copy already carries derived letters.
    reproduced, differ = 0, []
    for name, smiles, mol, locants in _maps():
        ring = {a.GetIdx() for a in mol.GetAtoms() if a.IsInRing()}
        lettered = {a: v for a, v in locants.items() if not str(v).isdigit()}
        if ring - set(locants) or not lettered:
            continue
        numerals = {a: v for a, v in locants.items() if str(v).isdigit()}
        derived = derive_fusion_locants(mol, numerals)
        if derived is None:
            continue  # the entry letters a fusion HETEROatom; the walk declines
        if all(str(derived.get(a)) == str(v) for a, v in lettered.items()):
            reproduced += 1
        else:
            differ.append(name)
    # Measured 2026-09-18 on 186 complete entries: 161 reproduced, 10 declined,
    # 15 differ -- special numberings (tetracene trione, dibenz[a,h]-
    # anthracene) or entries whose own letters contradict their numerals
    # (isochromenylium's "4a" is bonded to 8 and 1); see
    # ring_naming/fusion_locants.py.
    assert reproduced >= 161, (reproduced, differ)
    assert len(differ) <= 15, differ


def test_the_walk_never_overwrites_a_locant_the_entry_gives():
    for name, smiles, mol, locants in _maps():
        derived = derive_fusion_locants(mol, locants)
        if derived is None:
            continue
        for atom, value in locants.items():
            assert str(derived[atom]) == str(value), (name, atom)


def test_isoquinoline_fusion_atoms_and_a_heteroatom_gap():
    mol = Chem.MolFromSmiles("c1ccc2cnccc2c1")
    numerals = {4: 1, 5: 2, 6: 3, 7: 4, 9: 5, 0: 6, 1: 7, 2: 8}
    derived = derive_fusion_locants(mol, numerals)
    assert derived[8] == "4a" and derived[3] == "8a"
    # A missing fusion HETEROatom takes a numeral of its own (indolizine's
    # N4), so the walk declines rather than letter it.
    indolizine = Chem.MolFromSmiles("c1ccn2cccc2c1")
    assert derive_fusion_locants(indolizine, {0: 7, 1: 6, 2: 5, 4: 3, 5: 2, 6: 1, 8: 8}) is None
