"""One stereoisomer, one name, when the parent can be any of several chains that differ only in configuration (P-44.4.1.12).

The Blue Book's own example for CIP Sequence Rule 4b (P-92.5.2.2 example 5, BlueBookV2.pdf p. 900) is a molecule with six equal
arms, three on each of two quaternary carbons joined through a carbinol. Any arm at each end can be the chain, so there are nine
chains, all `nonan-5-ol` and all the same constitution; they differ in the configuration of the stereocentres they carry. The book
names the one whose descriptors are `(2R,3R,5R,7R,8R)`. Measured 2026-10-06 over random spellings of that ONE stereoisomer (each
spelling checked to be it by InChIKey):

    master 66f112ed                              8 names over 10 spellings
    + the cache fix (#229)                      16 names over 30
    + the "R precedes S" follow-up (#232)        4 names over 30
    + this change                                1 name  over 40, the book's

The first row hid two defects, and only the second is this file's:

* **A substituent's tree was reused for a different substituent** (#229, `context_stereo_key`): a (2R,3R) arm was printed (2S,3R)
  because both arms print as one SMILES once cut from the chain. That is a name for another compound. After it, every descriptor
  in every one of the 16 names is RDKit's label for the atom it describes: those are 16 CORRECT names of one molecule, each on a
  different chain, which is why a round trip or a per-descriptor check cannot see this defect and a count of names can.
* **The chain was chosen by atom order.** #232 added the choice of parent by configuration (`_break_parent_stereo_tie`: "like before
  unlike, then r before s, then R before S", P-44.4.1.12.2, BlueBookV2.pdf p. 413), and it did not engage here, for two reasons it
  could not have seen on the diether and diamide it was built on:
    1. It named every tied parent side by side, up to four, and there are nine. Only FOUR are different: the two arms of a
       quaternary carbon that carry the same configuration are one choice, since either gives the same name.
    2. It compared two parents only when their names were equal "once the descriptors are set aside", by removing the descriptors
       from the FINISHED text. The descriptors decide how prefixes merge, so the chain through one arm reads `4,4-bis[(2S,3R)-...]` and
       the chain through another `4-[(2R,3R)-...]-4-[(2S,3R)-...]`: different texts for names that differ in nothing but configuration.

Both are fixed at the cause: `engine._plan_identity` counts parents the molecule's own symmetry cannot tell apart once, and
`assembly.assemble_without_stereo` sets the descriptors aside while the name is assembled, so the prefixes merge as they would
without them. The choice itself is #232's, unchanged.

The oracle is RDKit's `rdCIPLabeler` on the WHOLE molecule, not a name: every descriptor the engine prints for the parent, and for
each prefix through the `atom_origin` that maps the prefix's own atoms back, must be that label for that atom, and the stereocentres
so described must be exactly the labelled ones, each once. OPSIN cannot read the book's name ("Failed to assign CIP stereochemistry"),
so it is no oracle here.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from rdkit import Chem, rdBase
from rdkit.Chem import rdCIPLabeler

from openchem.vendor.iupac_namer import engine, name_smiles
from openchem.vendor.iupac_namer.assembly import assemble, assemble_without_stereo, without_stereo_descriptors
from openchem.vendor.iupac_namer.strategy import default_strategy
from openchem.vendor.iupac_namer.types import Locant

SEED = 20261006

# Built from the book's descriptors with RDKit's CIP labeler; every labelled centre below is checked against it per atom.
BOOK_SMILES = (
    "C[C@H](Cl)[C@@H](C)[C@@]([C@H](O)[C@@]([C@H](C)[C@@H](C)Cl)([C@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl)"
    "([C@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl"
)
BOOK_NAME = (
    "(2R,3R,5R,7R,8R)-2,8-dichloro-4,4-bis[(2S,3R)-3-chlorobutan-2-yl]-6,6-bis[(2S,3S)-3-chlorobutan-2-yl]-3,7-dimethylnonan-5-ol"
)

# Eight more stereoisomers of the same skeleton, enumerated with RDKit (seed 5) and pinned. Between them: a chain whose own end is
# unlike (`7R,8S`), pseudoasymmetric centres on a quaternary carbon (`4s`, `4r`, `6s`, `6r`), and both at once.
ISOMERS = [
    "C[C@H](Cl)[C@H](C)C([C@@H](O)C([C@@H](C)[C@H](C)Cl)([C@@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl)([C@H](C)[C@@H](C)Cl)[C@H](C)[C@@H](C)Cl",
    "C[C@H](Cl)[C@@H](C)C([C@H](O)C([C@H](C)[C@H](C)Cl)([C@@H](C)[C@H](C)Cl)[C@@H](C)[C@H](C)Cl)([C@H](C)[C@H](C)Cl)[C@@H](C)[C@H](C)Cl",
    "C[C@H](Cl)[C@@H](C)[C@]([C@H](C)[C@@H](C)Cl)([C@H](O)C([C@@H](C)[C@H](C)Cl)([C@@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl",
    "C[C@H](Cl)[C@@H](C)[C@@]([C@@H](C)[C@H](C)Cl)([C@@H](C)[C@@H](C)Cl)[C@@H](O)C([C@H](C)[C@@H](C)Cl)([C@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl",
    "C[C@H](Cl)[C@@H](C)[C@@]([C@H](O)C([C@@H](C)[C@H](C)Cl)([C@@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl)([C@@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl",
    "C[C@H](Cl)[C@H](C)C([C@@H](O)[C@]([C@H](C)[C@@H](C)Cl)([C@@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl)([C@@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl",
    "C[C@H](Cl)[C@@H](C)C([C@H](C)[C@H](C)Cl)([C@@H](C)[C@@H](C)Cl)[C@H](O)[C@]([C@H](C)[C@H](C)Cl)([C@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl",
    "C[C@H](Cl)[C@@H](C)[C@]([C@@H](O)[C@]([C@H](C)[C@@H](C)Cl)([C@@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl)([C@H](C)[C@@H](C)Cl)[C@@H](C)[C@H](C)Cl",
]


def _spellings(smiles: str, count: int = 24) -> list[str]:
    """`count` distinct random roots and atom orders of one structure, each checked to BE that structure by InChIKey."""
    mol = Chem.MolFromSmiles(smiles)
    key = Chem.MolToInchiKey(mol)
    rdBase.SeedRandomNumberGenerator(SEED)
    out = [smiles]
    while len(out) < count:
        spelling = Chem.MolToSmiles(mol, doRandom=True)
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(spelling)) == key, spelling
        if spelling not in out:
            out.append(spelling)
    return out


def _names(smiles: str, count: int = 24) -> set[str]:
    return {name_smiles(spelling) for spelling in _spellings(smiles, count)}


def _disagreements_with_rdkit(smiles: str, name: str) -> list[str]:
    """What the name says that RDKit's whole-molecule CIP labels do not, or the other way round; empty when the name is right per atom.

    The parent's descriptors are in the molecule's own atom indices. A prefix's are in its fragment's, so each goes through the prefix's
    `atom_origin` (fragment atom -> atom of the molecule named at this level, which for a top-level prefix is the whole molecule).
    A prefix tree shared by two equal arms is checked once per arm, each through its own `atom_origin`. `name` is what `name_smiles` returned
    for `smiles`; the tree read here must assemble to it, or this would be checking some other name.
    """
    mol = Chem.MolFromSmiles(smiles)
    rdCIPLabeler.AssignCIPLabels(mol)
    label = {atom.GetIdx(): atom.GetProp("_CIPCode") for atom in mol.GetAtoms() if atom.HasProp("_CIPCode")}
    tree = engine.name(Chem.MolFromSmiles(smiles), default_strategy())
    assert assemble(tree) == name, "the tree read here is not the one the name was written from"
    problems: list[str] = []
    described: list[int] = []

    def check(descriptors, to_molecule, where):
        for descriptor in descriptors or ():
            atom = to_molecule(descriptor.stereo_center.atom_idx)
            described.append(atom)
            if label.get(atom) != descriptor.descriptor:
                problems.append(f"{where}: the name says {descriptor.locant}{descriptor.descriptor} for atom {atom}; RDKit says {label.get(atom)}")

    check(tree.stereo_descriptors, lambda index: index, "parent")
    for entry in tree.prefixes:
        origin = dict(entry.atom_origin)
        check(getattr(entry.tree, "stereo_descriptors", None), origin.__getitem__, f"prefix at {[str(loc) for loc in entry.locants]}")
    if sorted(described) != sorted(label):
        problems.append(f"the name describes atoms {sorted(described)}; RDKit labels {sorted(label)}")
    return problems


# --- the book's own molecule ------------------------------------------------------------------------------------------------

def test_the_blue_books_example_is_one_name_over_every_spelling_and_it_is_the_books():
    assert _names(BOOK_SMILES) == {BOOK_NAME}


def test_every_descriptor_of_that_name_is_rdkits_label_for_the_atom_it_describes():
    for spelling in _spellings(BOOK_SMILES, 8):
        assert _disagreements_with_rdkit(spelling, name_smiles(spelling)) == [], spelling


# --- the same skeleton, other configurations --------------------------------------------------------------------------------

@pytest.mark.parametrize("smiles", ISOMERS, ids=[f"isomer{index}" for index in range(len(ISOMERS))])
def test_each_stereoisomer_of_the_skeleton_is_one_name_and_right_per_atom(smiles):
    names = set()
    for spelling in _spellings(smiles, 4):
        name = name_smiles(spelling)
        names.add(name)
        assert _disagreements_with_rdkit(spelling, name) == [], spelling
    assert len(names) == 1, names


# --- what each half of the fix is for ---------------------------------------------------------------------------------------

def test_without_the_cross_parent_choice_the_same_spellings_give_several_names(monkeypatch):
    """The defect, kept alive: with the choice between tied parents switched off (`_break_parent_tie`) the chain is the later-generated plan, which
    follows atom order. If this ever stops disagreeing, the fixture no longer reaches the tie and the tests above prove nothing."""
    monkeypatch.setattr(engine, "_break_parent_tie", lambda *args, **kwargs: None)
    assert len(_names(BOOK_SMILES)) > 1


def _chain_choices(monkeypatch) -> list:
    """The trees `_choose_by_configuration` is asked to choose between when the book's molecule is named."""
    seen: list = []
    real = engine._choose_by_configuration

    def spy(trees):
        seen.append(list(trees))
        return real(trees)

    monkeypatch.setattr(engine, "_choose_by_configuration", spy)
    name_smiles(BOOK_SMILES)
    return seen[0]


def test_nine_chains_are_four_choices(monkeypatch):
    """Three arms at each end of the chain, but the two arms of a quaternary carbon that carry one configuration are one choice."""
    assert len(_chain_choices(monkeypatch)) == 4


def test_p_45_2_3_cannot_tell_the_four_choices_apart(monkeypatch):
    """The two rules meet here (#235 with #239). The four chains differ in nothing but configuration, and P-45.2.3 reads the prefixes' locants
    "ignoring the configuration symbols" (P-45.6.2): so it must leave all four to the configuration comparison. Read off the assembled prefixes
    WITH their descriptors, the arms merged differently (`4,4-bis[...]` against `4-[...]-4-[...]`), the flattened locants differed (`4,4,6,6`
    against `4,6,4,6`), and the rule ruled two of the four out on that, before the comparison that should choose."""
    offered_and_kept: list = []
    real = engine._senior_by_citation_locants

    def spy(trees):
        kept = real(trees)
        offered_and_kept.append((len(trees), None if kept is None else len(kept)))
        return kept

    monkeypatch.setattr(engine, "_senior_by_citation_locants", spy)
    assert _names(BOOK_SMILES, 4) == {BOOK_NAME}
    assert offered_and_kept and all(offered == 4 and kept in (None, 4) for offered, kept in offered_and_kept), offered_and_kept


def test_the_four_choices_differ_in_nothing_but_configuration_when_assembled_without_it(monkeypatch):
    trees = _chain_choices(monkeypatch)
    # Set aside AFTER assembly, the prefixes are merged the way the descriptors merged them: `4,4-bis[...]` against `4-[...]-4-[...]`.
    assert len({without_stereo_descriptors(assemble(tree)) for tree in trees}) > 1
    # Set aside DURING assembly, the arms are alike and merge alike.
    assert len({assemble_without_stereo(tree) for tree in trees}) == 1


def test_assembling_without_the_descriptors_leaves_no_trace_in_the_next_assembly(monkeypatch):
    tree = _chain_choices(monkeypatch)[0]
    plain = assemble_without_stereo(tree)
    assert without_stereo_descriptors(plain) == plain, "a descriptor group survived"
    assert assemble(tree).startswith("("), "the suppression leaked past the call"


def test_the_bound_counts_distinct_choices_not_chains(monkeypatch):
    """There are nine chains and four choices: a bound of four is enough only if equal chains count once, and three is not enough."""
    monkeypatch.setattr(engine, "_PARENT_TIE_HYPOTHESES", 4)
    assert _names(BOOK_SMILES, 12) == {BOOK_NAME}
    monkeypatch.setattr(engine, "_PARENT_TIE_HYPOTHESES", 3)
    assert len(_names(BOOK_SMILES, 12)) > 1


# --- `_plan_identity`, on made-up plans ------------------------------------------------------------------------------------------

def _plan(numbering: dict[int, int]):
    """A stand-in for a plan: the parent atoms and the locants they take."""
    return SimpleNamespace(
        numbering=SimpleNamespace(atom_to_locant={atom: Locant.numeric(locant) for atom, locant in numbering.items()}),
        pcg_type=None,
        named_parent=SimpleNamespace(naming_method="chain"),
    )


def test_two_plans_a_symmetry_of_the_molecule_relates_have_one_identity():
    # Either end of a butane chain is locant 1, in any atom order: that is one name.
    mol = Chem.MolFromSmiles("CCCC")
    forward, backward = _plan({0: 1, 1: 2, 2: 3, 3: 4}), _plan({3: 1, 2: 2, 1: 3, 0: 4})
    assert engine._plan_identity(mol, forward) == engine._plan_identity(mol, backward)


def test_two_plans_that_name_different_atoms_have_different_identities():
    mol = Chem.MolFromSmiles("CCC(C)CC")  # 3-methylpentane: atoms 0,1 and 4,5 are the two ethyls, 3 the methyl
    pentane = _plan({0: 1, 1: 2, 2: 3, 4: 4, 5: 5})
    pentane_from_the_other_end = _plan({5: 1, 4: 2, 2: 3, 1: 4, 0: 5})
    butane_through_the_methyl = _plan({0: 1, 1: 2, 2: 3, 3: 4})
    assert engine._plan_identity(mol, pentane) == engine._plan_identity(mol, pentane_from_the_other_end)
    assert engine._plan_identity(mol, pentane) != engine._plan_identity(mol, butane_through_the_methyl)
    # the same atoms numbered from the other end are another name when the methyl is not in the middle: 2-methylbutane
    isopentane = Chem.MolFromSmiles("CC(C)CC")
    assert engine._plan_identity(isopentane, _plan({0: 1, 1: 2, 3: 3, 4: 4})) != engine._plan_identity(isopentane, _plan({4: 1, 3: 2, 1: 3, 0: 4}))
    # and the method that names the atoms is part of what is named
    other_method = _plan({0: 1, 1: 2, 2: 3, 4: 4, 5: 5})
    other_method.named_parent = SimpleNamespace(naming_method="skeletal")
    assert engine._plan_identity(mol, pentane) != engine._plan_identity(mol, other_method)


def test_a_carved_fragments_inherited_descriptor_is_part_of_a_plans_identity():
    """The stamp a SMILES cannot write: `CCCC` carved from `R`-`S` arms is the same text from either end, and not the same name."""
    mol = Chem.MolFromSmiles("CCCC")
    mol.GetAtomWithIdx(0).SetProp("_ParentCIPCode", "R")
    mol.GetAtomWithIdx(3).SetProp("_ParentCIPCode", "S")
    from_the_r_end, from_the_s_end = _plan({0: 1, 1: 2, 2: 3, 3: 4}), _plan({3: 1, 2: 2, 1: 3, 0: 4})
    assert engine._plan_identity(mol, from_the_r_end) != engine._plan_identity(mol, from_the_s_end)
    # and with no stamp they ARE one name, so the difference above is the stamp's and nothing else
    plain = Chem.MolFromSmiles("CCCC")
    assert engine._plan_identity(plain, from_the_r_end) == engine._plan_identity(plain, from_the_s_end)
