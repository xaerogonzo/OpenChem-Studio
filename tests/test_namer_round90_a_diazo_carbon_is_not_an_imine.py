"""Naming round 90 (D-387): a diazo compound drawn `C=[N+]=[N-]` was named as an iminoazanium, a different molecule.

The engine perceived the group (a `diazo` functional group exists, P-61.4) but its C=N also matched `substituted_imine`, and an overlap with no
subsumption entry is treated as an ambiguity: the imine won, the `[N-]` was neutralised away and the name was `imino(methylidene)azanium`, which
OPSIN reads as CH3N2+. The other drawing, `[CH2-][N+]#N`, had its own classifier (D-019), so diazomethane was right in one Lewis form and wrong in
the other. Found in naming limitations inventory row NL-070 by re-measuring the benchmark section: six of six diazo shapes were wrong.

Measured on four diazo populations of 150 (a census molecule with one CH2 turned into `C=N2`; seeds 1 and 2 drove the fix, seeds 3 and 4 were not
looked at until it was done): exact read-back 26 and 27 of 150 before, 150 and 150 after on the first two; 148 and 150 on the unseen two. The
remaining unseen failures are stereo only (a retained morphinan name and a bis(dioxolo)pyran fusion name that OPSIN reads with the stereo it implies),
the same class as rounds 43 to 45.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, name). The first, the ethyl ester and the trimethylsilyl ketone are the Blue Book's own examples (P-61.4, pdf pp. 511-512).
NAMED = [
    ("diazomethane (book)", "C=[N+]=[N-]", "diazomethane"),
    ("ethyl diazoacetate (book)", "[N-]=[N+]=CC(=O)OCC", "ethyl diazoacetate"),
    ("1-diazo-1-(trimethylsilyl)propan-2-one (book)", "[N-]=[N+]=C([Si](C)(C)C)C(C)=O", "1-diazo-1-(trimethylsilyl)propan-2-one"),
    ("diazoacetone", "CC(=O)C=[N+]=[N-]", "1-diazopropan-2-one"),
    ("phenyldiazomethane", "c1ccccc1C=[N+]=[N-]", "(diazomethyl)benzene"),
    ("2-diazopropane", "CC(C)=[N+]=[N-]", "2-diazopropane"),
    ("a ring carbon", "[N-]=[N+]=C1CCCCC1", "diazocyclohexane"),
    ("two diazo groups", "[N-]=[N+]=C(C=[N+]=[N-])C", "1,2-didiazopropane"),
    ("a heteroatom on the diazo carbon, amino", "[N-]=[N+]=C(N)c1ccccc1", "[amino(diazo)methyl]benzene"),
    ("a heteroatom on the diazo carbon, sulfanyl", "[N-]=[N+]=C(S)c1ccccc1", "[diazo(sulfanyl)methyl]benzene"),
]

# What was already right and must not move: the other Lewis form of diazomethane (D-019), a diazonium, an organic azide.
UNCHANGED = [
    ("diazomethane, ylide form", "[CH2-][N+]#N", "methanidyldiazonium"),
    ("a diazonium", "C[N+]#N", "methanediazonium"),
    ("an azide, either drawing", "[N-]=[N+]=NC", "azidomethane"),
    ("an azide, N-first", "CN=[N+]=[N-]", "azidomethane"),
    ("an amidine is still an amidine", "N=C(N)c1ccccc1", "benzenecarboximidamide"),
    ("a substituted amidine keeps carbamimidoyl", "CCN=C(N(C)C)c1ccc(C(=O)O)cc1", "4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[r[0] for r in NAMED + UNCHANGED])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in NAMED], ids=[r[0] for r in NAMED])
def test_the_name_reads_back_to_the_input(label, smiles):
    """The point of the round: the old name read back to `N=[N+]=C`, CH3N2+, not CH2N2."""
    from py2opsin import py2opsin

    back = py2opsin(name_smiles(smiles), output_format="SMILES")
    assert back, (smiles, name_smiles(smiles))
    assert _key(back) == _key(smiles), (smiles, name_smiles(smiles), back)


@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in NAMED], ids=[r[0] for r in NAMED])
def test_no_name_invents_a_hydrogen_or_drops_a_charge(label, smiles):
    """OPSIN-free: whatever the spelling, the name must not be the iminoazanium shape the old fall-through produced."""
    name = name_smiles(smiles)
    assert "azanium" not in name and "azanylidene" not in name and "imino" not in name, name
    assert "diazo" in name, name


@needs_opsin
def test_a_diazo_carbon_beside_an_imine_still_names_the_imine():
    """The subsumption is for the diazo group's own C=N: a real imine elsewhere in the molecule is still the parent's imine."""
    from py2opsin import py2opsin

    smiles = "CC(=NC)C=[N+]=[N-]"
    name = name_smiles(smiles)
    assert name == "1-diazo-N-methylpropan-2-imine", name
    assert _key(py2opsin(name, output_format="SMILES")) == _key(smiles)
