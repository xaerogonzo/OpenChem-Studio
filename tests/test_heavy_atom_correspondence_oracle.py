"""An oracle for `restore_heavy_atom_order` that does not use its scoring rule.

`restore_heavy_atom_order` is a CORRESPONDENCE POLICY: it picks the graph
correspondence that departs least from the drawing, and refuses when the
least-departing candidates disagree about what lands on an atom. The tests
beside it check element and adjacency index for index, and every
automorphism of the skeleton passes that -- including the one that puts a
carboxylate's charge on the wrong oxygen.

So the ground truth here is built WITHOUT the policy:

1. edit charges and hydrogen counts IN PLACE on named atoms of the drawing,
   so the right answer is known by construction;
2. scramble the atom order -- a canonical SMILES round trip, then seeded
   random permutations -- and assert that each really reorders;
3. hand the scrambled form to `restore_heavy_atom_order` and compare element,
   charge, total hydrogens and aromaticity per index, and every bond's order,
   against the in-place edit.

**When a refusal is expected is stated at the level of the DRAWING**: exactly
when the unedited drawing itself makes an edited atom indistinguishable from
an atom that ends up in a different state. Equivalence is RDKit's symmetry
classes (`CanonicalRankAtoms(breakTies=False)`), which see element, charge,
hydrogens and bond orders -- so a carboxyl's =O and -OH are different, and one
amine of ethylenediamine is the same as the other. A skeleton automorphism
would call the carboxyl oxygens equivalent and expect a refusal production
correctly does not make; "several least-departing candidates" would restate
the production rule. A disagreement between this oracle and production is a
FINDING, not a test to adjust.
"""

from __future__ import annotations

import random

import pytest
from rdkit import Chem

from openchem.chem.engine import InvalidStructureError
from openchem.chem.pka_providers import dominant_microspecies, restore_heavy_atom_order


def _edited(drawing: Chem.Mol, edits: dict[int, tuple[int, int]]) -> Chem.Mol:
    """The drawing with (hydrogens, charge) changed on the named atoms, in place."""
    rw = Chem.RWMol(drawing)
    for index, (d_hydrogens, d_charge) in edits.items():
        atom = rw.GetAtomWithIdx(index)
        atom.SetNumExplicitHs(atom.GetTotalNumHs() + d_hydrogens)
        atom.SetNoImplicit(True)
        atom.SetFormalCharge(atom.GetFormalCharge() + d_charge)
    truth = rw.GetMol()
    Chem.SanitizeMol(truth)
    return truth


def _state(mol: Chem.Mol) -> tuple:
    atoms = tuple(
        (a.GetAtomicNum(), a.GetFormalCharge(), a.GetTotalNumHs(), a.GetIsAromatic())
        for a in mol.GetAtoms()
    )
    return atoms


def _bond_orders(mol: Chem.Mol, reference: Chem.Mol) -> tuple:
    return tuple(
        str(mol.GetBondBetweenAtoms(b.GetBeginAtomIdx(), b.GetEndAtomIdx()).GetBondType())
        for b in reference.GetBonds()
    )


def _refusal_expected(drawing: Chem.Mol, truth: Chem.Mol, edits) -> bool:
    """An edited atom the drawing cannot tell from one that ends up different."""
    ranks = list(Chem.CanonicalRankAtoms(drawing, breakTies=False))
    final = _state(truth)
    for edited in edits:
        for other in range(drawing.GetNumAtoms()):
            if other != edited and ranks[other] == ranks[edited] and final[other] != final[edited]:
                return True
    return False


def _scrambles(truth: Chem.Mol, seeds=(1, 2, 3)):
    """The canonical SMILES round trip, then seeded random renumberings."""
    yield "canonical", Chem.MolFromSmiles(Chem.MolToSmiles(truth))
    for seed in seeds:
        order = list(range(truth.GetNumAtoms()))
        random.Random(seed).shuffle(order)
        yield f"seed {seed}", Chem.RenumberAtoms(truth, order)


def _reorders(truth: Chem.Mol, scrambled: Chem.Mol) -> bool:
    return any(
        truth.GetAtomWithIdx(i).GetAtomicNum() != scrambled.GetAtomWithIdx(i).GetAtomicNum()
        or {n.GetIdx() for n in truth.GetAtomWithIdx(i).GetNeighbors()}
        != {n.GetIdx() for n in scrambled.GetAtomWithIdx(i).GetNeighbors()}
        for i in range(truth.GetNumAtoms())
    )


#: (name, drawn SMILES, edits {drawn atom index: (delta H, delta charge)}).
#: Indices are read off the SMILES as written; each case asserts its own
#: edited atoms are the element it names, so a miscounted index fails loudly.
CORPUS = [
    ("acetic acid -> acetate", "CC(=O)O", {3: (-1, -1)}, "O"),
    ("succinic acid, one carboxyl", "OC(=O)CCC(=O)O", {0: (-1, -1)}, "O"),
    ("succinic acid, both carboxyls", "OC(=O)CCC(=O)O", {0: (-1, -1), 7: (-1, -1)}, "O"),
    ("phenol -> phenolate", "Oc1ccccc1", {0: (-1, -1)}, "O"),
    ("4-nitrophenol -> phenolate", "Oc1ccc(cc1)[N+](=O)[O-]", {0: (-1, -1)}, "O"),
    ("imidazole -> imidazolide", "c1c[nH]cn1", {2: (-1, -1)}, "N"),
    ("imidazole -> imidazolium", "c1c[nH]cn1", {4: (1, 1)}, "N"),
    ("pyridine -> pyridinium", "c1ccncc1", {3: (1, 1)}, "N"),
    ("pyrimidine, one nitrogen", "c1ncncc1", {1: (1, 1)}, "N"),
    ("nitromethane, nothing moved", "C[N+](=O)[O-]", {}, ""),
    ("ethylenediamine, one amine", "NCCN", {0: (1, 1)}, "N"),
    ("ethylenediamine, both amines", "NCCN", {0: (1, 1), 3: (1, 1)}, "N"),
    ("piperazine, one nitrogen", "C1CNCCN1", {2: (1, 1)}, "N"),
    ("piperazine, both nitrogens", "C1CNCCN1", {2: (1, 1), 5: (1, 1)}, "N"),
    ("the reported ring O-O-C=N", "O1OC=N1", {3: (1, 1)}, "N"),
    ("the reported ring O-O-C-N", "O1OCN1", {3: (1, 1)}, "N"),
    ("trimesic acid, one carboxyl", "OC(=O)c1cc(cc(c1)C(=O)O)C(=O)O", {0: (-1, -1)}, "O"),
    (
        "trimesic acid, all three",
        "OC(=O)c1cc(cc(c1)C(=O)O)C(=O)O",
        {0: (-1, -1), 11: (-1, -1), 14: (-1, -1)},
        "O",
    ),
]


@pytest.mark.parametrize("name, smiles, edits, element", CORPUS, ids=[c[0] for c in CORPUS])
def test_the_policy_recovers_the_known_correspondence(name, smiles, edits, element):
    drawing = Chem.MolFromSmiles(smiles)
    for index in edits:
        assert drawing.GetAtomWithIdx(index).GetSymbol() == element, (
            f"{name}: atom {index} is {drawing.GetAtomWithIdx(index).GetSymbol()}, not {element}"
        )
    truth = _edited(drawing, edits)
    expect_refusal = _refusal_expected(drawing, truth, edits)

    for label, scrambled in _scrambles(truth):
        if label != "canonical":
            # A permutation of a tiny molecule can land on the identity or
            # on an automorphism; only an order that genuinely differs tests
            # anything, so the setup asserts it for every seeded case.
            if not _reorders(truth, scrambled):
                continue
        if expect_refusal:
            with pytest.raises(InvalidStructureError):
                restore_heavy_atom_order(drawing, scrambled)
            continue
        restored = restore_heavy_atom_order(drawing, scrambled)
        assert _state(restored) == _state(truth), (name, label)
        assert _bond_orders(restored, drawing) == _bond_orders(truth, drawing), (name, label)


def test_the_corpus_contains_both_verdicts():
    """ASSERTS ITS OWN SETUP: a corpus where the oracle expects only
    acceptance would pass while never testing a refusal, and vice versa."""
    verdicts = {
        _refusal_expected(Chem.MolFromSmiles(s), _edited(Chem.MolFromSmiles(s), e), e)
        for _, s, e, _ in CORPUS
    }
    assert verdicts == {True, False}


def test_most_seeded_scrambles_really_reorder():
    """The skip above must not hollow the test out."""
    reordering = sum(
        _reorders(_edited(Chem.MolFromSmiles(s), e), scrambled)
        for _, s, e, _ in CORPUS
        for label, scrambled in _scrambles(_edited(Chem.MolFromSmiles(s), e))
        if label != "canonical"
    )
    assert reordering >= 2 * len(CORPUS), reordering


# --- a representation change with no proton moved --------------------------------


def test_a_kekule_drawing_against_an_aromatic_form_is_the_identity():
    """Bond orders that differ only by RDKit's aromatic perception must not
    be read as proton transfer: nothing moved, so every atom keeps its state."""
    drawing = Chem.MolFromSmiles("c1ncncc1")
    Chem.Kekulize(drawing, clearAromaticFlags=True)
    aromatic = Chem.MolFromSmiles(Chem.MolToSmiles(Chem.MolFromSmiles("c1ncncc1")))
    restored = restore_heavy_atom_order(drawing, aromatic)
    for index, atom in enumerate(drawing.GetAtoms()):
        out = restored.GetAtomWithIdx(index)
        assert (out.GetSymbol(), out.GetFormalCharge(), out.GetTotalNumHs()) == (
            atom.GetSymbol(), atom.GetFormalCharge(), atom.GetTotalNumHs()
        ), index


def test_the_reported_ring_comes_back_aromatic_with_no_proton_moved():
    """The real library's representation change: at pH 7.4 Dimorphite leaves
    O-O-C=N neutral but returns it aromatic."""
    drawing = Chem.MolFromSmiles("O1OC=N1")
    species = dominant_microspecies(drawing, 7.4).mol
    for index, atom in enumerate(drawing.GetAtoms()):
        out = species.GetAtomWithIdx(index)
        assert (out.GetSymbol(), out.GetFormalCharge(), out.GetTotalNumHs()) == (
            atom.GetSymbol(), atom.GetFormalCharge(), atom.GetTotalNumHs()
        ), index


# --- the real library, with the expected site stated by hand ----------------------


def test_4_nitrophenol_is_deprotonated_on_the_phenol_oxygen_not_a_nitro_oxygen():
    drawing = Chem.MolFromSmiles("Oc1ccc(cc1)[N+](=O)[O-]")
    species = dominant_microspecies(drawing, 7.4).mol
    assert species.GetAtomWithIdx(0).GetFormalCharge() == -1
    assert species.GetAtomWithIdx(0).GetTotalNumHs() == 0
    assert [species.GetAtomWithIdx(i).GetFormalCharge() for i in (7, 8, 9)] == [1, 0, -1]


def test_imidazole_loses_the_proton_its_nh_nitrogen_carried():
    drawing = Chem.MolFromSmiles("c1c[nH]cn1")
    species = dominant_microspecies(drawing, 7.4).mol
    assert (species.GetAtomWithIdx(2).GetFormalCharge(), species.GetAtomWithIdx(2).GetTotalNumHs()) == (-1, 0)
    assert species.GetAtomWithIdx(4).GetFormalCharge() == 0
