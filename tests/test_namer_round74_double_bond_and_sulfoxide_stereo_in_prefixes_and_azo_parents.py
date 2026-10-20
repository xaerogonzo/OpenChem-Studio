"""Naming round 74 (D-337 .. D-339): the stereoisomers a STEREO population finds.

The population is new for these bonds. A random OTHER stereoisomer of each census molecule that has stereo (RDKit's `EnumerateStereoisomers`) is named, read back through OPSIN and
compared on the full InChIKey, which carries the stereo layer. 600 + 1,400 isomers: 73 of the first 600 read back as another stereoisomer, after this round 23 (and 37 of 1,400), and what is
left is the enumerator's impossible bridgehead isomers, a phosphate's P, and the pseudoasymmetric `(1r,4r)` of a cyclohexane, which OPSIN cannot read.

* D-337 The E/Z of a C=N bond was cited only when BOTH atoms were in the parent (`(1E)-N-hydroxyethanimine`). A hydrazone, a Schiff base or a ketimine named as an ylidene PREFIX
  (`N'-benzylideneacetohydrazide`, `2-[(benzylidene)amino]aniline`) was carved away from the bond it hangs from and named both isomers alike. The ylidene now carries its descriptor,
  `N'-[(E)-phenylmethylidene]acetohydrazide`; an ylidene with descriptors of its own cites the new one at the locant of its attachment atom (`(1Z,2Z)-3-phenylprop-2-en-1-ylidene`),
  because an unlocated one would read as either bond.
* D-338 The same for N=N: `diphenyldiazene` and `4-(phenyldiazenyl)phenol` named azobenzene and its cis isomer alike. `(E)-diphenyldiazene`, `4-[(Z)-phenyldiazenyl]phenol`.
* D-339 A sulfoxide sulfur with three different groups is a stereocentre, and its sulfinyl prefix was carved away from the tag: omeprazole and esomeprazole had one name.
  `[(S)-methylsulfinyl]benzene`. The same sulfur (or P, Se, As) in a SUFFIX group (a sulfinamide's, as in Ellman's `2-methylpropane-2-sulfinamide`) or in a group prefix
  (`(aminosulfinyl)`) has no locant, and is cited unlocated: `(S)-2-methylpropane-2-sulfinamide`, `(2S,R)-butane-2-sulfinamide`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("an acyl hydrazone, E", "CC(=O)N/N=C/c1ccccc1", "N'-[(E)-phenylmethylidene]acetohydrazide"),
    ("...Z", "CC(=O)N/N=C\\c1ccccc1", "N'-[(Z)-phenylmethylidene]acetohydrazide"),
    ("a ketone's acyl hydrazone", "CC(=O)N/N=C(C)/c1ccccc1", "N'-[(E)-1-phenylethan-1-ylidene]acetohydrazide"),
    ("a Schiff base named as an ylidene-amino prefix, E", "Nc1ccccc1/N=C/c1ccccc1", "2-{[(E)-phenylmethylidene]amino}aniline"),
    ("...Z", "Nc1ccccc1/N=C\\c1ccccc1", "2-{[(Z)-phenylmethylidene]amino}aniline"),
    ("...beside an acid", "OC(=O)c1ccccc1/N=C/c1ccccc1", "2-{[(E)-phenylmethylidene]amino}benzoic acid"),
    ("an ylidene with a double bond of its own", "COc1ccccc1/C=C\\C=N/NC(=O)c1ccc[nH]1", "N'-[(1Z,2Z)-3-(2-methoxyphenyl)prop-2-en-1-ylidene]-1H-pyrrole-2-carbohydrazide"),
    ("...the other C=C", "COc1ccccc1/C=C/C=N\\NC(=O)c1ccc[nH]1", "N'-[(1Z,2E)-3-(2-methoxyphenyl)prop-2-en-1-ylidene]-1H-pyrrole-2-carbohydrazide"),
    ("a fused ring's ylidene amide (a hand-built name), Z", "Cn1c2c(s/c1=N\\C(=O)c1cccs1)CCc1ccccc1-2", "N-[(Z)-1-methyl-1,2,4,5-tetrahydronaphtho[1,2-d][1,3]thiazol-2-ylidene]thiophene-2-carboxamide"),
    ("...E", "Cn1c2c(s/c1=N/C(=O)c1cccs1)CCc1ccccc1-2", "N-[(E)-1-methyl-1,2,4,5-tetrahydronaphtho[1,2-d][1,3]thiazol-2-ylidene]thiophene-2-carboxamide"),
    ("azobenzene, E", "c1ccccc1/N=N/c1ccccc1", "(E)-diphenyldiazene"),
    ("...Z", "c1ccccc1/N=N\\c1ccccc1", "(Z)-diphenyldiazene"),
    ("a dialkyl diazene", "CC/N=N/CC", "(E)-diethyldiazene"),
    ("a diazenyl prefix, E", "Oc1ccc(/N=N/c2ccccc2)cc1", "4-[(E)-phenyldiazenyl]phenol"),
    ("...Z", "Oc1ccc(/N=N\\c2ccccc2)cc1", "4-[(Z)-phenyldiazenyl]phenol"),
    ("a sulfoxide, S", "C[S@](=O)c1ccccc1", "[(S)-methylsulfinyl]benzene"),
    ("...R", "C[S@@](=O)c1ccccc1", "[(R)-methylsulfinyl]benzene"),
    ("omeprazole's sulfoxide", "COc1ccc2[nH]c(nc2c1)[S@@](=O)Cc1ncc(C)c(OC)c1C", "5-methoxy-2-[(S)-(4-methoxy-3,5-dimethylpyridin-2-yl)methanesulfinyl]-1H-benzimidazole"),
    ("...the other enantiomer", "COc1ccc2[nH]c(nc2c1)[S@](=O)Cc1ncc(C)c(OC)c1C", "5-methoxy-2-[(R)-(4-methoxy-3,5-dimethylpyridin-2-yl)methanesulfinyl]-1H-benzimidazole"),
    ("a sulfoxide beside an amino acid centre", "O=C(O)[C@@H](N)CC[S@](C)=O", "(2S)-2-amino-4-[(S)-methylsulfinyl]butanoic acid"),
    ("two sulfoxides", "C[S@](=O)CCCC[S@@](C)=O", "1-[(R)-methylsulfinyl]-4-[(S)-methylsulfinyl]butane"),
    ("a sulfinamide (Ellman's auxiliary), S", "CC(C)(C)[S@](=O)N", "(S)-2-methylpropane-2-sulfinamide"),
    ("...R", "CC(C)(C)[S@@](=O)N", "(R)-2-methylpropane-2-sulfinamide"),
    ("a sulfinamide beside a carbon centre", "CC[C@H](C)[S@@](=O)N", "(2S,R)-butane-2-sulfinamide"),
    ("a sulfinamide as a prefix", "O=C(O)C[S@](=O)N", "[(S)-aminosulfinyl]acetic acid"),
    ("...R", "O=C(O)C[S@@](=O)N", "[(R)-aminosulfinyl]acetic acid"),
    ("a sulfinamide on an imine, N-sulfinyl", "CC(C)(C)[S@@](=O)/N=C/c1ccccc1", "(1E)-N-[(R)-2-methylpropan-2-ylsulfinyl]-1-phenylmethanimine"),
]

KEPT = [
    ("a hydrazone with no geometry given", "CC(=O)NN=Cc1ccccc1", "N'-benzylideneacetohydrazide"),
    ("a Schiff base with none", "Nc1ccccc1N=Cc1ccccc1", "2-[(benzylidene)amino]aniline"),
    ("an azo compound with none", "c1ccccc1N=Nc1ccccc1", "diphenyldiazene"),
    ("a diazenyl with none", "Oc1ccc(N=Nc2ccccc2)cc1", "4-(phenyldiazenyl)phenol"),
    ("a sulfoxide with no tag", "CS(=O)c1ccccc1", "(methanesulfinyl)benzene"),
    ("an oxime, cited at the parent's locant as before", "C/C=N/O", "(1E)-N-hydroxyethanimine"),
    # the far end of this bond is in the parent, so `_collect_stereo_descriptors` cites it and the ylidene must not cite it again
    ("an exocyclic bond on a ring parent is cited once", "OC1CC/C(=C/c2ccccc2)C1", "(3Z)-3-benzylidenecyclopentan-1-ol"),
    ("a sulfinamide with no tag", "CC(C)(C)S(=O)N", "2-methylpropane-2-sulfinamide"),
    ("...as a prefix", "O=C(O)CS(=O)N", "(aminosulfinyl)acetic acid"),
    ("a carbon centre beside an untagged sulfinamide", "CC[C@H](C)S(=O)N", "(2S)-butane-2-sulfinamide"),
    # LEFT OPEN (KNOWN_LIMITATIONS, "What round 74 left open"): two unlocated descriptors read as neither centre, and the sulfurs have no locants of their own, so a group with
    # TWO such centres stays uncited, as before, rather than gain a guess
    ("two sulfinamide centres are not cited", "N[S@](=O)CC[S@@](N)=O", "ethane-1,2-disulfinamide"),
    ("a sulfone has no stereocentre", "CS(=O)(=O)c1ccccc1", "(methanesulfonyl)benzene"),
]

ALL = NAMED + KEPT


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name_reads_back_to_the_same_stereoisomer(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert _key(back) == _key(smiles), (expected, back)
