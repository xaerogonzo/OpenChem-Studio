"""Naming round 26: the esters of ONE polyol with ONE acid take the book's functional-class multiplicative name (P-65.6.3.3.3.1).

``CC(=O)OCCOC(C)=O`` is ``ethane-1,2-diyl diacetate (PIN)``, ``propane-1,3-diyl bis(chloroacetate)``, ``propane-1,2,3-triyl triacetate`` (pdf
p. 624). Until round 26 the engine wrote the acyloxy form (``2-(acetyloxy)ethyl acetate``), which the book calls acceptable in general
nomenclature only (P-65.6.3.3.3.2 method 2).

Building it needed the polyvalent organyl group named properly, and four things were wrong on that path (none had been reached before):

* ``render_free_valence_suffix`` prepended a multiplier to a suffix that already carried one: ``ethan-1,2-didiyl``, ``propan-1,2,3-tritriyl``;
* a retained substituent leaf (``phenyl``, ``cyclohexyl``) was used for a DIVALENT ring, naming a different molecule;
* the free valences were numbered by the FIRST one alone, so catechol came out ``1,6-phenylene`` (P-31.1.4.2.4 ranks them as a set);
* the retained ``methylene`` and ``1,2-/1,3-/1,4-phenylene`` (P-29.6.1) were written ``methane-1,1-diyl`` and ``benzene-1,4-diyl``.

NOT built, with the evidence: P-65.6.3.3.3.2 method (1), different anions on one polyol (``propane-1,2,3-triyl 1,2-diacetate 3-propanoate``).
OPSIN reads none of the forms of it (measured: ``methylene acetate formate``, ``1,4-phenylene acetate dichloroacetate`` and the book's three
other examples are all unparseable), so the oracle cannot confirm them and those molecules stay on the accepted acyloxy name, which it can.
"""
import shutil
from types import SimpleNamespace

import pytest
from rdkit import Chem, rdBase

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _organyl_cites_valences
from openchem.vendor.iupac_namer.types import Interpretation, _build_polyol_ester_decomposition

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, name). Every name here was read back by OPSIN to the identical structure, stereo included, when the row was written.
BOOK = [
    ("ethane-1,2-diyl", "CC(=O)OCCOC(C)=O", "ethane-1,2-diyl diacetate"),
    ("propane-1,3-diyl", "ClCC(=O)OCCCOC(=O)CCl", "propane-1,3-diyl bis(chloroacetate)"),
    ("propane-1,2,3-triyl", "CC(=O)OCC(OC(C)=O)COC(C)=O", "propane-1,2,3-triyl triacetate"),
]

MULTIPLIER = [
    # "di" for an unsubstituted anion, "bis" for a substituted one (P-65.6.3.3.3.1), and the enclosure of a name that carries a locant
    ("benzoate", "O=C(OCCOC(=O)c1ccccc1)c1ccccc1", "ethane-1,2-diyl dibenzoate"),
    ("formate", "O=COCCOC=O", "ethane-1,2-diyl diformate"),
    ("trifluoroacetate", "FC(F)(F)C(=O)OCCOC(=O)C(F)(F)F", "ethane-1,2-diyl bis(trifluoroacetate)"),
    ("acrylate", "C=CC(=O)OCCOC(=O)C=C", "ethane-1,2-diyl di(prop-2-enoate)"),
    ("methacrylate", "C=C(C)C(=O)OCCOC(=O)C(C)=C", "ethane-1,2-diyl bis(2-methylprop-2-enoate)"),
    ("tributyrin", "CCCC(=O)OCC(OC(=O)CCC)COC(=O)CCC", "propane-1,2,3-triyl tributanoate"),
    ("triolein", "CCCCCCCC/C=C\\CCCCCCCC(=O)OCC(OC(=O)CCCCCCC/C=C\\CCCCCCCC)COC(=O)CCCCCCC/C=C\\CCCCCCCC",
     "propane-1,2,3-triyl tri[(9Z)-octadec-9-enoate]"),
    ("sorbitol", "CC(=O)OCC(OC(C)=O)C(OC(C)=O)C(OC(C)=O)C(OC(C)=O)COC(C)=O", "hexane-1,2,3,4,5,6-hexayl hexaacetate"),
]

GROUPS = [
    # the organyl group itself: substituents, unsaturation, one carbon, geminal valences
    ("2-methylpropane-1,3-diyl", "CC(COC(C)=O)COC(C)=O", "2-methylpropane-1,3-diyl diacetate"),
    ("2-oxo", "CC(=O)OCC(=O)COC(C)=O", "2-oxopropane-1,3-diyl diacetate"),
    ("2-phenyl", "CC(=O)OCC(c1ccccc1)COC(C)=O", "2-phenylpropane-1,3-diyl diacetate"),
    ("lowest prefix locant", "CC(=O)OCC(C1CCCCC1)OC(C)=O", "1-cyclohexylethane-1,2-diyl diacetate"),
    ("butene E", "CC(=O)OC/C=C/COC(C)=O", "(2E)-but-2-ene-1,4-diyl diacetate"),
    ("butene Z", "CC(=O)OC/C=C\\COC(C)=O", "(2Z)-but-2-ene-1,4-diyl diacetate"),
    ("butyne", "CC(=O)OCC#CCOC(C)=O", "but-2-yne-1,4-diyl diacetate"),
    ("methylene", "CC(=O)OCOC(C)=O", "methylene diacetate"),
    ("ethane-1,1-diyl", "CC(OC(C)=O)OC(C)=O", "ethane-1,1-diyl diacetate"),
    ("propane-2,2-diyl", "CC(=O)OC(C)(C)OC(C)=O", "propane-2,2-diyl diacetate"),
    ("substituted methylene", "CC(=O)OC(OC(C)=O)c1ccccc1", "phenylmethylene diacetate"),
]

RINGS = [
    # P-29.6.1: 1,2-/1,3-/1,4-phenylene are the preferred prefixes, and stay substitutable; the free valences take the lowest SET of locants
    ("catechol", "CC(=O)Oc1ccccc1OC(C)=O", "1,2-phenylene diacetate"),
    ("resorcinol", "CC(=O)Oc1cccc(OC(C)=O)c1", "1,3-phenylene diacetate"),
    ("hydroquinone", "CC(=O)Oc1ccc(OC(C)=O)cc1", "1,4-phenylene diacetate"),
    ("2,6-dimethyl", "CC(=O)Oc1cc(C)c(OC(C)=O)c(C)c1", "2,6-dimethyl-1,4-phenylene diacetate"),
    ("2-chloro", "CC(=O)Oc1ccc(OC(C)=O)c(Cl)c1", "2-chloro-1,4-phenylene diacetate"),
    ("catechol dibenzoate", "O=C(Oc1ccccc1OC(=O)c1ccccc1)c1ccccc1", "1,2-phenylene dibenzoate"),
    ("pyrogallol", "CC(=O)Oc1cccc(OC(C)=O)c1OC(C)=O", "benzene-1,2,3-triyl triacetate"),
    ("cyclohexane-1,2", "CC(=O)OC1CCCCC1OC(C)=O", "cyclohexane-1,2-diyl diacetate"),
    ("cyclohexane-1,4", "CC(=O)OC1CCC(OC(C)=O)CC1", "cyclohexane-1,4-diyl diacetate"),
    ("cyclopentane-1,3", "O=C(OC1CCC(OC(=O)c2ccccc2)C1)c1ccccc1", "cyclopentane-1,3-diyl dibenzoate"),
    ("1-methylcyclohexane-1,2", "CC(=O)OC1CCCCC1(C)OC(C)=O", "1-methylcyclohexane-1,2-diyl diacetate"),
    ("inositol", "CC(=O)OC1C(OC(C)=O)C(OC(C)=O)C(OC(C)=O)C(OC(C)=O)C1OC(C)=O", "cyclohexane-1,2,3,4,5,6-hexayl hexaacetate"),
    ("naphthalene-2,6", "CC(=O)Oc1ccc2cc(OC(C)=O)ccc2c1", "naphthalene-2,6-diyl diacetate"),
    ("pyridine-2,5", "CC(=O)Oc1ccc(OC(C)=O)nc1", "pyridine-2,5-diyl diacetate"),
    ("oxolane-2,5", "CC(=O)OC1CCC(OC(C)=O)O1", "oxolane-2,5-diyl diacetate"),
]

STEREO = [
    ("(2R,3R)", "CC(=O)O[C@H](C)[C@@H](C)OC(C)=O", "(2R,3R)-butane-2,3-diyl diacetate"),
    ("(S)-propane-1,2", "CC(=O)OC[C@H](C)OC(C)=O", "(2S)-propane-1,2-diyl diacetate"),
    ("trans ring", "CC(=O)O[C@H]1CCCC[C@@H]1OC(C)=O", "(1S,2S)-cyclohexane-1,2-diyl diacetate"),
    ("stereo acid", "CC[C@H](C)C(=O)OCCOC(=O)[C@@H](C)CC", "ethane-1,2-diyl bis[(2S)-2-methylbutanoate]"),
    ("heroin", "CC(=O)O[C@H]1C=C[C@H]2[C@H]3Cc4ccc(OC(C)=O)c5O[C@@H]1[C@]2(CCN3C)c45",
     "(5R,6S,9R,13S,14R)-4,5-epoxy-17-methyl-7,8-didehydromorphinan-3,6-diyl diacetate"),
]

NEW = BOOK + MULTIPLIER + GROUPS + RINGS + STEREO

# Shapes that must NOT take the new path, with the name they keep (each is read back by OPSIN too).
KEPT = [
    # different acids on one polyol: method (1) of P-65.6.3.3.3.2, which OPSIN cannot read, so the accepted method (2) stays
    ("different acids", "CC(=O)OCCOC(=O)CC", "2-(acetyloxy)ethyl propanoate"),
    ("three acids", "CC(=O)OCC(OC(C)=O)COC(=O)CC", "2,3-bis(acetyloxy)propyl propanoate"),
    # a senior group elsewhere: the ester is not the principal characteristic group
    ("free acid", "OC(=O)CCC(=O)OCCOC(C)=O", "4-[2-(acetyloxy)ethoxy]-4-oxobutanoic acid"),
    # one acid, several alcohols: the poly-acid reading of P-65.6.3.3.2, not this one
    ("diester of a diacid", "CCOC(=O)CCC(=O)OCC", "diethyl butanedioate"),
    ("mixed alcohols", "COC(=O)CCC(=O)OCCOC(C)=O", "methyl 4-[2-(acetyloxy)ethoxy]-4-oxobutanoate"),
    ("one ester", "CC(=O)OCCO", "2-hydroxyethyl acetate"),
    # the organyl group is not a single-parent group the generic path can name: declined, not misnamed
    ("four valences, one carbon", "CC(=O)OCC(COC(C)=O)(COC(C)=O)COC(C)=O", "3-(acetyloxy)-2,2-bis[(acetyloxy)methyl]propyl acetate"),
    ("ether link", "CC(=O)OCCOCCOC(C)=O", "2-[2-(acetyloxy)ethoxy]ethyl acetate"),
    ("bisphenol A", "CC(=O)Oc1ccc(C(C)(C)c2ccc(OC(C)=O)cc2)cc1", "4-{2-[4-(acetyloxy)phenyl]propan-2-yl}phenyl acetate"),
    ("1,2-phenylenedi(propan-3,1-yl)", "CC(=O)OCCCc1ccccc1CCCOC(C)=O", "3-{2-[3-(acetyloxy)propyl]phenyl}propyl acetate"),
    ("lactone", "CC(=O)OCC1CCC(=O)O1", "(5-oxooxolan-2-yl)methyl acetate"),
]


def _canon(smiles):
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol is not None else None


def _opsin_structure(name):
    from py2opsin import py2opsin

    out = py2opsin(name)
    return _canon(out) if out else None


@pytest.mark.parametrize("label,smiles,expected", NEW, ids=[r[0] for r in NEW])
def test_the_esters_of_one_polyol_take_the_multiplicative_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NEW + KEPT, ids=[r[0] for r in NEW + KEPT])
def test_opsin_reads_the_name_back_to_the_same_structure(label, smiles, expected):
    # the point of building only the forms OPSIN reads: a name here is a verified one, stereo included
    assert _opsin_structure(name_smiles(smiles)) == _canon(smiles)


@pytest.mark.parametrize("label,smiles,expected", KEPT, ids=[r[0] for r in KEPT])
def test_a_shape_the_rule_does_not_cover_keeps_its_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


# A MESO group has two equally good descriptor sets, `(2R,3S)` and `(2S,3R)`, and the engine picks one by the order the atoms are written in --
# the same as for meso-butane-2,3-diol and meso-2,3-dichlorobutane, so it is general and was not introduced here (P-31.1.4.3.4 would choose
# R at the lowest locant; nothing implements that tie-break). What is pinned is that BOTH forms are the same molecule to OPSIN.
MESO = [
    ("meso butane", "CC(=O)O[C@H](C)[C@H](C)OC(C)=O", {"(2R,3S)-butane-2,3-diyl diacetate", "(2S,3R)-butane-2,3-diyl diacetate"}),
    ("cis ring", "CC(=O)O[C@H]1CCCC[C@H]1OC(C)=O",
     {"(1R,2S)-cyclohexane-1,2-diyl diacetate", "(1S,2R)-cyclohexane-1,2-diyl diacetate"}),
]


@pytest.mark.parametrize("label,smiles,either", MESO, ids=[r[0] for r in MESO])
def test_a_meso_group_is_named_with_either_descriptor_set(label, smiles, either):
    rdBase.SeedRandomNumberGenerator(20261006)
    mol = Chem.MolFromSmiles(smiles)
    names = {name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(8)}
    assert names <= either
    if shutil.which("java") is not None:
        assert {_opsin_structure(n) for n in either} == {_canon(smiles)}


ORDER_FREE = [r for r in NEW if r[0] in {"ethane-1,2-diyl", "propane-1,2,3-triyl", "catechol", "2,6-dimethyl", "(2R,3R)",
                                          "trans ring", "stereo acid", "heroin", "inositol", "1-methylcyclohexane-1,2"}]


@pytest.mark.parametrize("label,smiles,expected", ORDER_FREE, ids=[r[0] for r in ORDER_FREE])
def test_the_name_does_not_depend_on_the_order_the_atoms_are_written_in(label, smiles, expected):
    rdBase.SeedRandomNumberGenerator(20261006)
    mol = Chem.MolFromSmiles(smiles)
    assert {name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(10)} == {expected}


@pytest.mark.parametrize("organyl,valences,cited", [
    ("ethane-1,2-diyl", 2, True),
    ("propane-1,2,3-triyl", 3, True),
    ("cyclohexane-1,2,3,4,5,6-hexayl", 6, True),
    ("2,6-dimethyl-1,4-phenylene", 2, True),
    ("phenylmethylene", 2, True),
    ("methylene", 2, True),
    # the shape the generic path really produced for a two-valent group that lost one valence
    ("3-(2-propylphenyl)propane-1-diyl", 2, False),
    ("ethane-1,2-diyl", 3, False),
    ("propyl", 2, False),
])
def test_an_organyl_group_must_cite_every_valence_it_was_given(organyl, valences, cited):
    assert _organyl_cites_valences(organyl, valences) is cited


_ESTER = Chem.MolFromSmarts("[#6][OX2][CX3](=O)")


def _build(smiles):
    """The decomposition builder alone, on the ester groups a SMARTS finds (it needs only each group's atoms)."""
    mol = Chem.MolFromSmiles(smiles)
    return _build_polyol_ester_decomposition([SimpleNamespace(atoms=frozenset(m)) for m in mol.GetSubstructMatches(_ESTER)], mol)


@pytest.mark.parametrize("smiles", [
    "CC(=O)OCCOC(C)=O",
    "CC(=O)OCC(OC(C)=O)COC(C)=O",
    "O=C(OCCOC(=O)c1ccccc1)c1ccccc1",
    "CC(=O)Oc1ccc(OC(C)=O)cc1",
], ids=["diacetate", "triacetate", "dibenzoate", "phenylene"])
def test_the_builder_accepts_the_esters_of_one_polyol_with_one_acid(smiles):
    assert _build(smiles) is not None


@pytest.mark.parametrize("smiles", [
    "CC(=O)OCCO",                              # one ester
    "CC(=O)OCCOC(=O)CC",                       # two acids
    "CCOC(=O)CCC(=O)OCC",                      # two alcohols on one diacid: the components overlap
    "O=C1CCC(=O)OCCO1",                        # a macrocycle: cutting a ring bond leaves the acyl and alkyl carbons together
    "CC(=O)OCC1CCC(=O)O1",                     # a lactone beside an acetate
    "O=C1CCC(CC2CCC(=O)O2)O1",                 # two IDENTICAL lactones: the same acid, but each cut is in a ring
    "COC(=O)OC",                               # a carbonate: two ester groups on ONE acyl carbon
    "CC(=O)OCCOC(C)=O.O",                      # a stray fragment is not claimed by any component
    "CC(=O)OCC.CC(=O)OCC",                     # two alcohols in two molecules
], ids=["one ester", "two acids", "diacid diester", "macrocycle", "lactone + acetate", "two lactones", "carbonate",
        "stray fragment", "two molecules"])
def test_the_builder_declines_every_shape_that_is_not_one_polyol_one_acid(smiles):
    assert _build(smiles) is None


def test_the_polyol_reading_wins_whatever_order_the_decompositions_are_generated_in(monkeypatch):
    # The plan search tries the LAST-generated of equally scored plans first, and the polyol reading happens to be generated last. That is
    # an accident of `decomposition_candidates`, not a rule: the book's PIN is the multiplicative name, so `_break_ester_tie` must choose it
    # itself. (A round 26 mutant that dropped it from that function survived every other test for exactly this reason.)
    original = Interpretation.decomposition_candidates

    def reversed_candidates(self, mol):
        return iter(list(original(self, mol))[::-1])

    monkeypatch.setattr(Interpretation, "decomposition_candidates", reversed_candidates)
    assert name_smiles("CC(=O)OCCCCOC(C)=O") == "butane-1,4-diyl diacetate"


DECLINED = [
    ("diethylene glycol", "CC(=O)OCCOCCOC(C)=O"),
    ("bisphenol A", "CC(=O)Oc1ccc(C(C)(C)c2ccc(OC(C)=O)cc2)cc1"),
    ("pentaerythritol", "CC(=O)OCC(COC(C)=O)(COC(C)=O)COC(C)=O"),
    ("1,2-phenylenedi(propan-3,1-yl)", "CC(=O)OCCCc1ccccc1CCCOC(C)=O"),
    ("1,4-phenylenedimethylene", "CC(=O)OCc1ccc(COC(C)=O)cc1"),
]


@pytest.mark.parametrize("label,smiles", DECLINED, ids=[r[0] for r in DECLINED])
def test_a_polyol_ester_the_rule_declines_still_has_one_name_in_every_atom_order(label, smiles):
    # The polyol plan is BUILT for these and then declines at execution (its organyl group is not one parent). `_break_ester_tie` must still
    # run round 25's comparison of the single-ester readings: without it the search falls to raw generation order, which follows atom order, and
    # D-186 comes back for exactly these molecules. (A round 26 mutant that took polyol_ester out of that function's gate survived every other test.)
    rdBase.SeedRandomNumberGenerator(20261006)
    mol = Chem.MolFromSmiles(smiles)
    assert len({name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(12)}) == 1


# The same shapes, where the RULE and a canonical rank would choose different esters: `_break_ester_tie` compares the executed alcohol components
# (round 25, D-186: the lowest free-valence locant, so `propyl`, not `propan-2-yl`). If the polyol plan's decline skipped that comparison the
# names would still be stable, but they would be the rank's choice, and 7 of the 20 unsymmetric shapes measured here moved (`...butan-2-yl` for
# `...ethyl`). Each name was read back by OPSIN to the input structure.
DECLINED_RULE = [
    ("thioether", "CC(=O)OCCSCC(OC(C)=O)C", "2-{[2-(acetyloxy)propyl]sulfanyl}ethyl acetate"),
    ("ether", "CC(=O)OCCCOCC(OC(C)=O)C", "3-[2-(acetyloxy)propoxy]propyl acetate"),
    ("amine", "CC(=O)OCCN(C)CC(C)OC(C)=O", "2-{[2-(acetyloxy)propyl](methyl)amino}ethyl acetate"),
    ("branched ether", "CC(=O)OC(C)CCOCCOC(C)=O", "2-[3-(acetyloxy)butoxy]ethyl acetate"),
]


@pytest.mark.parametrize("label,smiles,expected", DECLINED_RULE, ids=[r[0] for r in DECLINED_RULE])
def test_a_declined_polyol_ester_keeps_the_lowest_locant_choice_of_round_25(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", DECLINED_RULE, ids=[r[0] for r in DECLINED_RULE])
def test_opsin_reads_the_declined_polyol_names_back(label, smiles, expected):
    assert _opsin_structure(name_smiles(smiles)) == _canon(smiles)
