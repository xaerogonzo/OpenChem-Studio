"""Naming round 28: a name must keep every nuclide the molecule has (D-193), and the placement and readability of the labels (D-195, D-196).

`[15NH2]c1ccccc1` was named `aniline`, `[15N]#CCC(=O)O` `cyanoacetic acid`, `C[18O]CC(=O)O` `methoxyacetic acid`: each a name for the UNLABELLED compound, with nothing in
the output to say a label was lost. `collect_isotope_labels` drops a label for an atom it cannot locate ("drop the label rather than emit a guess"), and `isotopic_prefix`
labelled only a prefix that is one atom, so every route that builds a name from parts of the molecule could lose a nuclide without anyone knowing.

The fix is two things, and they are tested apart:

* **the guard** (`engine._check_nuclides_named`), a net under EVERY route: a name that cites fewer atoms of a nuclide than the molecule has is refused, so the next
  route nobody has found raises instead of denoting another compound;
* **the routes** that label their atoms: a retained parent's unnumbered atom (`(15N)aniline`, `(18O)phenol`, `(15N)benzonitrile`), a multi-atom prefix (`(15N)cyano`,
  `(81Br)bromocarbonyl`), an ether oxygen (`(18O)methoxy`), the halogen of a hypohalous amide, an isotopic hydrogen on a hydroxy or amino prefix (`(O-2H)hydroxy`), the
  heteroatom of a suffix group (`1-phenylethan-1-(18O)one`), and the parent's own bracket placed before the part it modifies (`1-bromo(4-13C)butane`, D-196).

Every name pinned here was read back through OPSIN to its input on canonical SMILES and InChIKey (isotopes are in the InChIKey).
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import engine, name_smiles
from openchem.vendor.iupac_namer.isotope import isotopic_prefix

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name). Each is a shape a different route builds.
NAMED = [
    ("retained parent: aniline's nitrogen", "[15NH2]c1ccccc1", "(15N)aniline"),
    ("the same with a prefix: the bracket goes after the prefixes", "[15NH2]c1ccc(Cl)cc1", "4-chloro(15N)aniline"),
    ("the same with two prefixes", "[18OH]c1ccc(Br)cc1Cl", "4-bromo-2-chloro(18O)phenol"),
    ("retained parent: phenol's oxygen has no locant", "[18OH]c1ccccc1", "(18O)phenol"),
    ("retained parent: both atoms of benzonitrile's nitrile", "[15N]#Cc1ccccc1", "(15N)benzonitrile"),
    ("multi-atom prefix: cyano", "[15N]#CCC(=O)O", "(15N)cyanoacetic acid"),
    ("multi-atom prefix: bromocarbonyl through the generic route", "O=C([81Br])CCC(=O)O", "3-[(81Br)bromocarbonyl]propanoic acid"),
    ("an ether oxygen in a prefix", "C[18O]CC(=O)O", "(18O)methoxyacetic acid"),
    ("two nuclides in one prefix share a bracket", "[13CH3][18O]CC(=O)O", "[(1-13C,18O)methoxy]acetic acid"),
    ("the halogen of a hypohalous amide", "CN(C)[81Br]", "dimethyl(81Br)hypobromous amide"),
    ("...the bare parent", "[81Br]N", "(81Br)hypobromous amide"),
    ("a deuterium on a hydroxy prefix", "[2H]OCCC(=O)O", "3-[(O-2H)hydroxy]propanoic acid"),
    ("a deuterium on an amino prefix", "[2H]NCCC(=O)O", "3-[(N-2H)amino]propanoic acid"),
    ("two deuteriums on an amino prefix", "[2H]N([2H])CCC(=O)O", "3-[(N,N-2H2)amino]propanoic acid"),
    ("D-196a: the parent's bracket is cited before the parent name", "[13CH3]CCCBr", "1-bromo(4-13C)butane"),
    ("D-196b: a suffix heteroatom's nuclide before the suffix word", "[18O]=C(C)c1ccccc1", "1-phenylethan-1-(18O)one"),
    ("...with a prefix on the parent", "[18O]=C(C)c1ccc(Cl)cc1", "1-(4-chlorophenyl)ethan-1-(18O)one"),
    ("...with a parent label as well", "[18O]=C([13CH3])c1ccccc1", "1-phenyl(2-13C)ethan-1-(18O)one"),
    ("a parent starting with a locant keeps its hyphen after the bracket", "Clc1ccc2[15nH]ccc2c1", "5-chloro(1-15N)-1H-indole"),
    ("D-195: a hypervalent centre with no hydrogen and only single bonds", "CP(C)(C)(C)C", "pentamethyl-lambda5-phosphane"),
    ("...the book's own example, p. 770", "COP(OC)(OC)(OC)OC", "pentamethoxy-lambda5-phosphane"),
    ("...arsenic", "C[As](C)(C)(C)C", "pentamethyl-lambda5-arsane"),
]

# Not changed by this round, and pinned so a change to the guard or the placement shows here.
UNCHANGED = [
    ("a perdeuterated parent with no prefix", "[2H]C([2H])([2H])O[2H]", "(1,1,1-2H3,O-2H)methanol"),
    ("a label on the parent beside a stereocentre", "C[C@H](O)[13CH3]", "(2S)-(1-13C)propan-2-ol"),
    ("a label under a multiplier counts for each atom", "[81Br]CC[81Br]", "1,2-di[(81Br)bromo]ethane"),
    ("a hydroxy on the parent keeps its heteroatom locant", "[2H]OC", "(O-2H)methanol"),
    ("a double-bonded centre says its own number: no lambda added", "CP(C)(C)=O", "trimethyl-lambda5-phosphanone"),
    ("...and as a substituent", "CP(C)(=O)CC(=O)O", "[dimethyl(oxo)phosphanyl]acetic acid"),
]

# Refused by the guard: no verified name keeps every label, so the engine raises and the application withholds a name that would be the unlabelled compound's.
REFUSED = [
    ("two deuteriums on an aromatic amine: the retained name has one N and the hydrogens cannot be placed", "[2H]N([2H])c1ccccc1"),
    ("an isotopic oxygen of a nitro group", "[18O-][N+](=O)c1ccccc1"),
    ("two atoms of one element in the retained group (both nitrogens)", "[15NH2]c1ccc([15NH2])cc1"),
    ("a bare (13C) would not say which of benzonitrile's seven carbons (OPSIN: position ambiguous)", "N#[13C]c1ccccc1"),
    ("an ether oxygen that is one of two oxygens of the prefix", "COc1ccc([18O]CC(=O)O)cc1"),
    ("an amino nitrogen that is one of two nitrogens of the fragment", "NCC[15NH]CCC(=O)O"),
    ("`(15N)carbamoylamino` would not say which of its two nitrogens", "NC(=O)[15NH]CCC(=O)O"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_keeps_the_nuclide(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_labelled_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected
    assert Chem.MolToSmiles(Chem.MolFromSmiles(back)) == Chem.MolToSmiles(Chem.MolFromSmiles(smiles)), expected


@pytest.mark.parametrize("label,smiles", REFUSED, ids=[row[0] for row in REFUSED])
def test_a_name_that_would_lose_a_nuclide_is_refused(label, smiles):
    with pytest.raises(ValueError, match="isotopic labelling"):
        name_smiles(smiles)


def test_the_application_shows_the_refusal_not_a_wrong_name():
    from openchem.chem import naming_providers

    with pytest.raises(naming_providers.NamingError) as raised:
        naming_providers.derived_name_for_structure(Chem.MolFromSmiles("[2H]N([2H])c1ccccc1"))
    assert "isotopic labelling" in str(raised.value)


# --- the guard on its own -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("(2H4)methanol", {("H", 2): 4}),
    ("(1,1,1-2H3)ethane", {("H", 2): 3}),                                    # a locant list, then the count
    ("(1-2H,2-13C)ethanol", {("H", 2): 1, ("C", 13): 1}),
    ("(O-2H)methanol", {("H", 2): 1}),                                       # a heteroatom locant
    ("1,2-di[(81Br)bromo]ethane", {("Br", 81): 2}),                          # the multiplier encloses the bracket
    ("bis{2-[(81Br)bromo]ethyl} ether", {("Br", 81): 2}),                    # ...at a deeper level
    ("tris[(15N)amino]benzene", {("N", 15): 3}),
    ("(2S)-butan-2-ol", {}),                                                 # a stereodescriptor shaped like sulfur-2
    ("(1R,2S)-cyclohexane-1,2-diol", {}),
    ("2H-pyran", {}),                                                        # an indicated hydrogen is outside any bracket
    ("3-(15N)aminopropanoic acid", {("N", 15): 1}),
    ("potassium tritide", {("H", 3): 1}),                                     # the retained isotope-specific names carry the nuclide in the word
    ("calcium ditritide", {("H", 3): 2}),
    ("sodium deuteride", {("H", 2): 1}),
    ("potassium hydride", {}),
])
def test_the_nuclides_a_name_cites(name, expected):
    assert engine._nuclides_named(name) == expected


def test_a_name_that_cites_fewer_atoms_than_the_molecule_has_is_refused():
    mol = Chem.MolFromSmiles("[13CH3][13CH2]O")
    engine._check_nuclides_named(mol, "(1,2-13C2)ethanol")                   # both cited: fine
    with pytest.raises(ValueError, match="2 x 13C|1 x 13C"):
        engine._check_nuclides_named(mol, "(1-13C)ethanol")                  # one of two
    with pytest.raises(ValueError, match="13C"):
        engine._check_nuclides_named(mol, "ethanol")


def test_a_molecule_without_a_nuclide_is_never_refused():
    engine._check_nuclides_named(Chem.MolFromSmiles("CCO"), "ethanol")
    engine._check_nuclides_named(Chem.MolFromSmiles("CCO"), "(2S)-whatever")


def test_a_visible_failure_is_not_refused_twice():
    engine._check_nuclides_named(Chem.MolFromSmiles("[13CH3]O"), "[NAMING ERROR: No valid naming plan found for [13CH3]O]methane")


def test_more_mentions_than_atoms_is_not_a_refusal():
    """A count is not proof of placement: the guard refuses only what is certainly lost."""
    engine._check_nuclides_named(Chem.MolFromSmiles("[13CH3]O"), "(1-13C)(13C)methanol")


# --- isotopic_prefix with hydrogens ------------------------------------------------------------------------------------------

def _atom(smiles: str, symbol: str):
    mol = Chem.MolFromSmiles(smiles)
    return next(a for a in mol.GetAtoms() if a.GetSymbol() == symbol)


def test_a_prefix_cites_the_hydrogens_on_its_atom_with_the_atoms_symbol():
    assert isotopic_prefix("hydroxy", _atom("[2H]O", "O")) == "(O-2H)hydroxy"
    assert isotopic_prefix("amino", _atom("[2H]N[2H]", "N")) == "(N,N-2H2)amino"
    assert isotopic_prefix("hydroxy", _atom("O", "O")) == "hydroxy"                     # nothing labelled: unchanged
    assert isotopic_prefix("bromo", _atom("[81Br]C", "Br")) == "(81Br)bromo"           # as before


def test_the_atoms_own_nuclide_and_its_hydrogens_share_one_bracket():
    assert isotopic_prefix("hydroxy", _atom("[2H][18OH]", "O")) == "(18O,O-2H)hydroxy"


def test_a_prefix_already_in_a_bracket_takes_the_new_nuclide_into_it():
    assert isotopic_prefix("(1-13C)methoxy", _atom("[18O]", "O")) == "(1-13C,18O)methoxy"
    # a prefix that starts with an enclosing mark and not a nuclide bracket gets its own bracket in front (nothing to merge with)
    assert isotopic_prefix("[(1-13C)methyl]oxy", _atom("[18O]", "O")) == "(18O)[(1-13C)methyl]oxy"
