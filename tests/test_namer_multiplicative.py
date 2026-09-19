"""Multiplicative nomenclature, P-15.3 / P-51.3 (naming round 5, N4).

"Multiplicative nomenclature is preferred to substitutive nomenclature for
generating preferred IUPAC names to express multiple occurrences of
identical parent structures, other than alkanes" when the linking bonds, the
linker's substitution and every locant on the units are identical (P-51.3.1,
pdf p. 436). The engine had a `MultiplicativePlan` type that nothing built,
so each of these PINs came out substitutive ("phenoxybenzene",
"methane-1,1-diphosphonic acid").

`multiplicative.py` reads the decomposition off the molecule's symmetry and
declines outside its built class. Expected names are the book's, with its
page, primes written as the engine writes them ("'" for the book's U+2032).
Every one parses back through OPSIN to the structure it names -- the
vendored suite checks that (`test_multiplicative_round_trip.py`).
"""

from __future__ import annotations

import random

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import name
from openchem.vendor.iupac_namer.multiplicative import explain
from openchem.vendor.iupac_namer.strategy import default_strategy

BOOK = [
    ("OC(=O)c1ccc(Sc2ccc(C(O)=O)cc2)cc1", "4,4'-sulfanediyldibenzoic acid", 98),
    ("c1ccc(OOc2ccccc2)cc1", "1,1'-peroxydibenzene", 104),
    ("OCCSCCO", "2,2'-sulfanediyldi(ethan-1-ol)", 104),
    ("[SiH3]CCCCCCCCCCCCCCOCCCCCCCCCCCCCC[SiH3]",
     "[oxydi(tetradecane-14,1-diyl)]bis(silane)", 104),
    ("OC(=O)C1CCC(OC2CCC(C(O)=O)CC2)CC1", "4,4'-oxydi(cyclohexane-1-carboxylic acid)", 104),
    ("OS(=O)(=O)c1ccc(Oc2ccc(S(O)(=O)=O)cc2)cc1", "4,4'-oxydi(benzene-1-sulfonic acid)", 104),
    ("OC(=O)COCC(O)=O", "2,2'-oxydiacetic acid", 105),
    ("OC(=O)CCOCCC(O)=O", "3,3'-oxydipropanoic acid", 105),
    ("OC(=O)CP(CC(O)=O)CC(O)=O", "2,2',2''-phosphanetriyltriacetic acid", 105),
    ("OP(O)(=O)CNCP(O)(O)=O", "[azanediylbis(methylene)]bis(phosphonic acid)", 105),
    ("NCCOCCN", "2,2'-oxydi(ethan-1-amine)", 105),
    ("OC(=O)COCCOCCOCC(O)=O", "2,2'-[oxybis(ethane-2,1-diyloxy)]diacetic acid", 105),
    ("CC(=O)NNCNNC(C)=O", "N',N'''-methylenediacetohydrazide", 106),
    ("Nc1ccc(NCNc2ccc(N)cc2)cc1", "N1,N1'-methylenedi(benzene-1,4-diamine)", 107),
    ("Brc1ccc(Oc2ccc(Br)cc2)cc1", "1,1'-oxybis(4-bromobenzene)", 107),
    ("OC(=O)c1ccc(Oc2ccc(C(O)=O)c(Br)c2)cc1Br", "4,4'-oxybis(2-bromobenzoic acid)", 107),
    ("CN(C)C(=O)CCSCCC(=O)N(C)C", "3,3'-sulfanediylbis(N,N-dimethylpropanamide)", 108),
    ("c1ccccc1Cc1ccccc1", "1,1'-methylenedibenzene", 376),
    ("OC(=O)CSCC(O)=O", "2,2'-sulfanediyldiacetic acid", 436),
    ("OC(=O)COCCOCC(O)=O", "2,2'-[ethane-1,2-diylbis(oxy)]diacetic acid", 437),
    ("OC(=O)c1ccc(OCCOc2ccc(C(O)=O)cc2)cc1",
     "4,4'-[ethane-1,2-diylbis(oxy)]dibenzoic acid", 437),
    ("OC(=O)c1ccccc1CCOCCOCCOCCc1ccccc1C(O)=O",
     "2,2'-[oxybis(ethane-2,1-diyloxyethane-2,1-diyl)]dibenzoic acid", 437),
]


@pytest.mark.parametrize("smiles,expected,page", BOOK)
def test_the_book_multiplicative_pin_is_named_as_printed(smiles, expected, page):
    assert name_smiles(smiles) == expected


# Derived, not printed: each applies a printed rule to a unit the book
# does not show multiplied. The rule is cited beside it.
DERIVED = [
    ("OP(O)(=O)CP(O)(O)=O", "methylenebis(phosphonic acid)",
     "phosphonic acid takes 'bis', as in the p. 105 example"),
    ("NC(N)=NCCCCCCCCCCCCCCN=C(N)N", "N'',N'''''-(tetradecane-1,14-diyl)diguanidine",
     "cid45000: guanidine's imino N is N'' (p. 675); a second unit's nitrogens "
     "start after the first's three, as acetohydrazide's two do (P-15.3.2.2.1)"),
    ("C[Si](C)(C)CC[Si](C)(C)C", "(ethane-1,2-diyl)bis(trimethylsilane)",
     "as '(propane-1,2-diyl)bis(trimethylsilane) (PIN)' (p. 110)"),
    ("OC(=O)c1ccc(C(=O)c2ccc(C(O)=O)cc2)cc1", "4,4'-carbonyldibenzoic acid",
     "the acid outranks the ketone the carbonyl would be (P-41)"),
]


@pytest.mark.parametrize("smiles,expected,why", DERIVED)
def test_a_derived_multiplicative_name(smiles, expected, why):
    assert name_smiles(smiles) == expected, why


# Where the book keeps the substitutive name, or another construction.
CONVERSES = [
    ("c1ccc(Nc2ccccc2)cc1", "N-phenylaniline",
     "the amine N is the principal group, so it cannot be a linker"),
    ("O=C(c1ccccc1)c1ccccc1", "diphenylmethanone",
     "the ketone in the linker outranks two benzenes (P-15.3.3.2.2)"),
    ("Oc1ccc(C(=O)c2ccc(O)cc2)cc1", "bis(4-hydroxyphenyl)methanone",
     "ketone over alcohol (P-41)"),
    ("c1ccccc1[SiH2]c1ccccc1", "diphenylsilane", "Si is the senior parent (P-44.1.2)"),
    ("COC", "methoxymethane", "alkanes are not identical units (P-15.3.4.2)"),
    ("CCCSC(=CSCC)SCCC",
     "1-{[2-(ethylsulfanyl)-1-(propylsulfanyl)ethen-1-yl]sulfanyl}propane",
     "'alkanes are still not allowed to be identical units' (p. 111)"),
    ("CC(OCCC(O)=O)C(O)=O", "2-(2-carboxyethoxy)propanoic acid",
     "2,3'-locants: not identical, so substitutive (p. 106)"),
    ("N#Cc1ccc(Cl)cc1Cc1cccc(C#N)c1", "4-chloro-2-[(3-cyanophenyl)methyl]benzonitrile",
     "unequally substituted units (p. 108)"),
    ("C[Si](C)(C)O[Si](C)(C)C", "trimethyl(trimethylsilyloxy)silane",
     "Si-O-Si is a disiloxane chain, not two silanes (P-21.2.3); N5 names it"),
]


@pytest.mark.parametrize("smiles,expected,why", CONVERSES)
def test_the_substitutive_name_stands_where_the_book_keeps_it(smiles, expected, why):
    assert name_smiles(smiles) == expected, why


def _explain(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    return explain(mol, name(mol, default_strategy()))


# Outside the built class: declined, with the reason, never a partial name.
DECLINED = [
    ("O=C(N=Nc1ccccc1)N=Nc1ccccc1", "senior",
     "the book's own counterexample: not 1,1'-carbonylbis(2-phenyldiazene)"),
    ("Oc1ccc(OCC(C)COc2ccc(O)cc2)cc1", "substituted",
     "4,4'-[(2-methylpropane-1,3-diyl)bis(oxy)]diphenol: a substituted linker"),
    ("OC(=O)c1ccc(CC(c2ccc(C(O)=O)cc2)c2ccc(C(O)=O)cc2)cc1", "senior",
     "4,4',4''-(ethane-1,1,2-triyl)tribenzoic acid needs the unsymmetrical "
     "centre (P-15.3.3.1); the one symmetric pair leaves an acid in the linker"),
    ("C[C@H](O)COC[C@H](C)O", "stereo", "stereo is outside the class"),
]


@pytest.mark.parametrize("smiles,reason,why", DECLINED)
def test_outside_the_class_it_declines_and_says_why(smiles, reason, why):
    got = _explain(smiles)
    assert got.startswith("declined:") and reason in got, (why, got)


@pytest.mark.parametrize("smiles", [s for s, _e, _p in BOOK[:8]])
def test_the_name_does_not_depend_on_atom_order(smiles):
    mol = Chem.MolFromSmiles(smiles)
    want = name_smiles(smiles)
    rng = random.Random(20260919)
    for _ in range(3):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        shuffled = Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False)
        assert name_smiles(shuffled) == want
