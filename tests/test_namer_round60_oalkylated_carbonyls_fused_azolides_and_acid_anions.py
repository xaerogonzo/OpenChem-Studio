"""Naming round 60 (D-285 .. D-287): an O-alkylated carbonyl beside another charge, a fused azolide as a substituent, and the acid anion that must be the parent.

The round closed the list round 59 left open. The populations (`tools/naming_ion_populations.py`, now with an alkoxide, an anilide, and the oxygens of an ester, an acid, an aldehyde,
an ether and an alcohol) found:

D-285 (a visible `NAMING ERROR` inside the name, 120 ions): an O-alkylated amide or ketone beside another charge (`CC(NCC(=O)[O-])=[O+]C`). The unclaimed-`=O` fallback claimed the
  oxygen as a bare `oxo` and left its methyl unclaimed ('heavy atoms unclaimed'); the carved group then had no oxidanium parent either, because the perception gate read the fragment's
  valence without the radical electrons that stand for the bond the cut took. It is `(methyloxidaniumylidene)`, and `(methylsulfaniumylidene)` for sulfur, `(methylselaniumylidene)`
  for selenium. An S-PROTONATED thioamide beside another charge lost its charge instead (`thioxo`): `sulfaniumylidene`.
D-286 (a visible `NAMING ERROR`, 21 ions): a fused azolide (`pyrano[2,3-c]pyrazole`'s `[n-]`) as a SUBSTITUENT had no plan, because the fused-ring namer neutralised only +1 atoms. The ring is
  its neutral self less a hydrogen; the `-N-id-` infix of round 59 is then placed from the real molecule: `2,4-dihydropyrano[2,3-c]pyrazol-2-id-4-yl`. A lactam anion in a ring
  (a benzothiazinone `[N-]`) takes the same infix as a substituent.
D-287 (the right molecule on the wrong parent): with an acid anion AND a junior anion (an azolide, an amide's `[N-]`) the junior anion was the parent and the carboxylate or
  sulfonate a prefix (`3-{4-[oxido(oxo)methyl]phenyl}-1H-pyrazol-1-ide`). The acid anion is senior (P-41, P-72.7 e): `4-(1H-pyrazol-1-id-3-yl)benzoate`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.perception.charge_perception import acid_anion_route

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    # D-285
    ("an O-methyl amide beside a carboxylate", "CC(NCC(=O)[O-])=[O+]C", "{[1-(methyloxidaniumylidene)ethyl]amino}acetate"),
    ("an O-methyl imidate on an oxygen beside a carboxylate", "CC(OCC(=O)[O-])=[O+]C", "[1-(methyloxidaniumylidene)ethoxy]acetate"),
    ("an O-methyl formamide on an aryl amine", "C[O+]=CNc1ccccc1OCC(=O)[O-]", "(2-{[(methyloxidaniumylidene)methyl]amino}phenoxy)acetate"),
    ("an O-methyl amide on an amino acid", "C[O+]=C(C)N[C@@H](C)C(=O)[O-]", "(2S)-2-{[1-(methyloxidaniumylidene)ethyl]amino}propanoate"),
    ("an S-methyl thioamide", "CC(NCC(=O)[O-])=[S+]C", "{[1-(methylsulfaniumylidene)ethyl]amino}acetate"),
    ("an Se-methyl selenoamide", "CC(NCC(=O)[O-])=[Se+]C", "{[1-(methylselaniumylidene)ethyl]amino}acetate"),
    ("an S-protonated thioamide", "CC(NCC(=O)[O-])=[SH+]", "[(1-sulfaniumylideneethyl)amino]acetate"),
    ("an O-protonated amide", "CC(NCC(=O)[O-])=[OH+]", "[(1-oxidaniumylideneethyl)amino]acetate"),
    # D-286
    ("a fused azolide as a substituent of an anilinium", "[NH3+]c1ccc(C2C=COc3n[n-]cc32)cc1", "[4-(2,4-dihydropyrano[2,3-c]pyrazol-2-id-4-yl)phenyl]azanium"),
    ("a fused azolide with substituents beside an anilinium", "Cc1[n-]nc2c1C(c1ccc([NH3+])cc1)C(C#N)=C(N)O2",
     "6-amino-4-(4-azaniumylphenyl)-3-methyl-2,4-dihydropyrano[2,3-c]pyrazol-2-id-5-carbonitrile"),
    ("a lactam anion in a ring as a substituent of an acetate", "[O-]C(=O)Cc1ccccc1CC1Sc2ccccc2[N-]C1=O",
     "{2-[(3-oxo-3,4-dihydro-2H-1,4-benzothiazin-4-id-2-yl)methyl]phenyl}acetate"),
    # D-287
    ("a benzoate beside a pyrazolide", "[O-]C(=O)c1ccc(-c2cc[n-]n2)cc1", "4-(1H-pyrazol-1-id-3-yl)benzoate"),
    ("a benzoate beside an amide anion", "[O-]C(=O)c1ccc(C[N-]C(C)=O)cc1", "4-[(acetylazanidyl)methyl]benzoate"),
    ("a sulfonate beside a pyrazolide", "[O-]S(=O)(=O)c1ccc(-c2cc[n-]n2)cc1", "4-(1H-pyrazol-1-id-3-yl)benzene-1-sulfonate"),
    ("a benzoate beside a pyrazolide and an ammonium", "[O-]C(=O)c1ccc(-c2cc[n-]n2)c([NH3+])c1", "3-azaniumyl-4-(1H-pyrazol-1-id-3-yl)benzoate"),
    ("an acetate on a pyrrolide", "[O-]C(=O)CC1=CC=C[N-]1", "(1H-pyrrol-1-id-2-yl)acetate"),
    # D-288: an aryl amine anion beside a nitro group (the nitro is charge-separated and neutral)
    ("an anilide with a nitro group", "[NH-]c1ccc([N+](=O)[O-])cc1", "4-nitrobenzen-1-aminide"),
    ("an aminoimidazole anion with a nitro group", "Cn1cnc([N+](=O)[O-])c1[NH-]", "1-methyl-4-nitro-1H-imidazol-5-aminide"),
    # D-289: an acyl group with a second acid is not a diacyl
    ("a phthalamic acid on an anilinium", "C[NH2+]c1ccc(NC(=O)c2ccccc2C(=O)O)cc1", "4-{[(2-carboxyphenyl)(oxo)methyl]amino}-N-methylanilinium"),
    ("a camphoramic acid on an oxidanium", "CC[OH+]c1ccc(NC(=O)C2CCC(C)(C(=O)O)C2(C)C)cc1",
     "(4-{[(3-carboxy-2,2,3-trimethylcyclopentyl)(oxo)methyl]amino}phenyl)(ethyl)oxidanium"),
    # D-290: every stereo centre of a carved branch keeps its label from the whole molecule
    ("a carved branch whose centre is its attachment", "CC(C)[C@H]([N-]C(=O)C)C(=O)Nc1ccccc1", "acetyl[(2S)-1-anilino-3-methyl-1-oxobutan-2-yl]azanide"),
    ("a spiro centre beside a pyrazolide and an O-protonated lactam", "COc1ccc(OC)c(-c2[n-]nc3c2[C@]2(C(=[OH+])Nc4ccc(C)c(Br)c42)C(C#N)=C(N)O3)c1",
     "(4R)-6-amino-4'-bromo-3-(2,5-dimethoxyphenyl)-5'-methyl-2'-oxidaniumylidenespiro[2,4-dihydropyrano[2,3-c]pyrazole-4,3'-2,3-dihydro-1H-indole]-2-id-5-carbonitrile"),
]

# Unchanged: the neighbours of each change keep what they had.
KEPT = [
    ("an O-protonated ketone alone", "CC(=[OH+])C", "(propan-2-ylidene)oxidanium"),
    ("a carbamate ester keeps its oxo", "COC(=O)CC(=[OH+])C", "(4-methoxy-4-oxobutan-2-ylidene)oxidanium"),
    ("a phenolate and a pyrazolide: the phenolate stays the parent", "[O-]c1ccc(-c2cc[n-]n2)cc1", "4-(1H-pyrazol-1-id-3-yl)benzen-1-olate"),
    ("a pyrazolide alone", "Cc1ccn[n-]1", "5-methyl-1H-pyrazol-1-ide"),
    ("a fused azolide alone", "Cc1[n-]nc2c1CC(C#N)=C(N)O2", "6-amino-5-cyano-3-methylpyrano[2,3-c]pyrazol-2(4H)-ide"),
    ("a lactam anion alone", "CCC1Sc2ccccc2[N-]C1=O", "2-ethyl-3-oxo-2,3-dihydro-4H-1,4-benzothiazin-4-ide"),
    ("a dicarboxylate", "[O-]C(=O)CC(=O)[O-]", "propanedioate"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.GetFormalCharge(Chem.MolFromSmiles(back)) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert pop._inchikey(back, neutral=True) == pop._inchikey(smiles, neutral=True), (expected, back)


# --- the acid-anion route ---------------------------------------------------------------------------------------------------------------------------------------------
def test_a_junior_anion_beside_an_acid_anion_leaves_the_acid_anion_principal():
    assert acid_anion_route(Chem.MolFromSmiles("[O-]C(=O)c1ccc(-c2cc[n-]n2)cc1")) == "carved"
    assert acid_anion_route(Chem.MolFromSmiles("[O-]C(=O)c1ccc(C[N-]C(C)=O)cc1")) == "carved"


def test_a_carbanion_beside_an_acid_anion_is_not_made_a_prefix_this_way():
    # only a nitrogen anion is built as a prefix; any other junior anion keeps the route it had
    assert acid_anion_route(Chem.MolFromSmiles("[O-]C(=O)CC(C#N)[C-](C#N)C#N")) != "carved"


# --- the tool ----------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["alcohol", "aniline_nh"])
def test_the_new_acid_kinds_deprotonate_one_site(kind):
    assert kind in pop.ANION_SITES
    rows = [{"smiles": {"alcohol": "CCCO", "aniline_nh": "CNc1ccccc1"}[kind], "label": "x"}]
    made = [c for c in pop.generate("anion", rows) if c.kind == kind]
    assert [c.smiles for c in made] == [{"alcohol": "CCC[O-]", "aniline_nh": "C[N-]c1ccccc1"}[kind]]


@pytest.mark.parametrize("kind,parent,ion", [
    ("ester_o", "CC(=O)OC", "COC(C)=[OH+]"),
    ("acid_o", "CC(=O)O", "CC(O)=[OH+]"),
    ("aldehyde_o", "CC=O", "CC=[OH+]"),
    ("ether_o", "CCOCC", "CC[OH+]CC"),
    ("alcohol_o", "CCCO", "CCC[OH2+]"),
])
def test_the_new_base_kinds_protonate_one_site(kind, parent, ion):
    assert kind in pop.CATION_SITES
    made = [c for c in pop.generate("cation", [{"smiles": parent, "label": "x"}]) if c.kind == kind]
    assert [Chem.CanonSmiles(c.smiles) for c in made] == [Chem.CanonSmiles(ion)]


# --- the other changes -------------------------------------------------------------------------------------------------------------------------------------------------
def test_an_anilide_beside_a_second_amine_is_refused_and_not_put_on_the_wrong_nitrogen():
    # `...-N,N-dimethylbenzen-1-aminide` put the charge on the dimethylaniline
    with pytest.raises(ValueError):
        name_smiles("Cc1ccc([C@H]([N-]c2ccccc2)P(=O)(OC2CCCCC2)c2ccc(N(C)C)cc2)cc1")


def test_a_ring_that_begins_with_oxo_is_not_the_prefix():
    from openchem.vendor.iupac_namer.engine import _restore_dropped_oxidanium

    mol = Chem.MolFromSmiles("C(=[OH+])(NCC(=O)[O-])C1CCCO1")
    out = _restore_dropped_oxidanium(mol, "{[(oxo)(oxolan-2-yl)methyl]amino}acetate")
    assert "oxolan-2-yl" in out and "(oxidaniumylidene)" in out and "oxidaniumylidene)lan" not in out


def test_an_azolide_is_labelled_on_its_neutral_view():
    from openchem.vendor.iupac_namer.perception.stereo import label_azolide_on_neutral_view

    anion = Chem.MolFromSmiles("COc1ccc(OC)c(-c2[n-]nc3c2[C@]2(C(=O)Nc4ccc(C)c(Br)c42)C(C#N)=C(N)O3)c1")
    neutral = Chem.MolFromSmiles("COc1ccc(OC)c(-c2[nH]nc3c2[C@]2(C(=O)Nc4ccc(C)c(Br)c42)C(C#N)=C(N)O3)c1")
    from rdkit.Chem import rdCIPLabeler

    for m in (anion, neutral):
        Chem.AssignStereochemistry(m, cleanIt=True, force=True)
        rdCIPLabeler.AssignCIPLabels(m)
    label_azolide_on_neutral_view(anion)
    code = lambda m: next(a.GetProp("_CIPCode") for a in m.GetAtoms() if a.HasProp("_CIPCode"))  # noqa: E731
    assert code(anion) == code(neutral)


def test_a_diacid_has_no_amido_prefix():
    from openchem.vendor.iupac_namer.engine import _acid_name_to_amido

    assert _acid_name_to_amido("benzene-1,2-dicarboxylic acid") is None
    assert _acid_name_to_amido("hexanedioic acid") is None
    assert _acid_name_to_amido("cyclopentane-1-carboxylic acid") == "cyclopentane-1-carboxamido"


def test_a_centre_already_cited_is_not_cited_twice():
    from openchem.vendor.iupac_namer.perception.charge_perception import _with_attachment_stereo

    mol = Chem.MolFromSmiles("C[C@H](N)C(=O)O")
    once = _with_attachment_stereo(mol, 1, "propan-2-yl")
    twice = _with_attachment_stereo(mol, 1, once)
    assert once.startswith("(2") and twice == once

