"""RDKit's PEOE against Gasteiger & Marsili's own published charges.

`docs/sources.toml` carried `gasteiger1980` at `verification = "citation"`
for the life of the project: the reference was right and **no number this
application produces had ever been checked against the paper**. The only
Gasteiger assertion in the suite was a relative ordering of two atoms.

That gap matters more here than for most methods, because a library's
implementation is not always the paper's -- RDKit's own SA and NP scores
document exactly that divergence in their headers. So this was measured
with both outcomes decided in advance: agreement pins the values and
upgrades the source entry; disagreement would have been recorded as a
finding with numbers and the entry left at `citation`.

MEASURED, and it agrees:

    n = 22 carbons over 17 compounds
    mean  -1.9 me      MAE 2.1 me      max |diff| 8.6 me

...where a millielectron is 0.001 e and the paper prints whole
millielectrons, so +-0.5 me is rounding before anything else. The three
largest deviations -- H2CO 8.6, *CH3CF3 7.2, CH3*CHO 6.6 -- are all
pi-containing or heavily fluorinated, which is where the paper's own
abstract says the treatment is an extension ("sigma-bonded and
nonconjugated pi-systems").

TABLE 3 WAS READ FROM A 320 dpi RENDER, NOT THE TEXT LAYER. This scan's
text layer is badly damaged -- it renders the paper's own page range as
"3219 to 3288" where ten pages from 3219 gives 3228 -- and this project is
three for three on finding a one-digit error in a scanned table that way.
"""

from __future__ import annotations

import statistics

import pytest
from rdkit import Chem
from rdkit.Chem import rdPartialCharges

#: Table 3, p3224. `atom_index` is the carbon the table stars; `published`
#: is the PEOE column in millielectrons. The `ab initio` and ESCA columns
#: beside it are other people's numbers and are deliberately not shipped.
TABLE_3 = [
    (1, "CH4", "C", 0, -78),
    (2, "CH3CH3", "CC", 0, -68),
    (3, "CH2=CH2", "C=C", 0, -106),
    (4, "HC#CH", "C#C", 0, -122),
    (5, "CH3F", "CF", 0, 79),
    (6, "CH2F2", "FCF", 1, 230),
    (7, "CHF3", "FC(F)F", 1, 380),
    (8, "CF4", "FC(F)(F)F", 1, 561),
    (9, "*CH3CH2F", "CCF", 0, -37),
    (10, "CH3*CH2F", "CCF", 1, 87),
    (11, "*CH3CF3", "CC(F)(F)F", 0, 39),
    (12, "CH3*CF3", "CC(F)(F)F", 1, 387),
    (13, "CH3OH", "CO", 0, 33),
    (14, "CH3OCH3", "COC", 0, 36),
    (15, "H2CO", "C=O", 0, 115),
    (16, "*CH3CHO", "CC=O", 0, -9),
    (17, "CH3*CHO", "CC=O", 1, 123),
    (18, "*CH3COCH3", "CC(C)=O", 0, -6),
    (19, "CH3*COCH3", "CC(C)=O", 1, 131),
    (20, "HCN", "C#N", 0, 51),
    (21, "*CH3CN", "CC#N", 0, 23),
    (22, "CH3*CN", "CC#N", 1, 60),
]

#: 15 me = 0.015 e. Chosen against the MEASUREMENT rather than picked: the
#: worst observed disagreement is 8.6 me, so this carries about 1.7x
#: headroom -- loose enough that the paper's whole-millielectron rounding
#: and a minor RDKit revision cannot redden it, tight enough that a changed
#: parameter set or a lost damping factor could not hide underneath. A
#: charge error of 0.015 e is far below anything chemically readable.
TOLERANCE_ME = 15.0


def _peoe_millielectrons(smiles: str, atom_index: int) -> float:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    rdPartialCharges.ComputeGasteigerCharges(mol)
    return mol.GetAtomWithIdx(atom_index).GetDoubleProp("_GasteigerCharge") * 1000


@pytest.mark.parametrize(
    "number, name, smiles, atom_index, published",
    TABLE_3,
    ids=[f"{n}-{name}" for n, name, *_ in TABLE_3],
)
def test_rdkits_peoe_reproduces_the_papers_table_3(
    number, name, smiles, atom_index, published
):
    got = _peoe_millielectrons(smiles, atom_index)
    assert abs(got - published) <= TOLERANCE_ME, (
        f"Table 3 entry {number} ({name}): the paper prints {published} me "
        f"and RDKit gives {got:.1f} me"
    )


def test_the_agreement_is_as_good_across_the_table_as_it_is_per_row():
    """A per-row tolerance can be met while the whole table drifts one way.

    The mean is asserted separately for that reason: a systematic offset
    that stayed inside 15 me on every row would still mean the model had
    moved, and the measured mean is -1.9 me.
    """
    diffs = [
        _peoe_millielectrons(smiles, index) - published
        for _n, _name, smiles, index, published in TABLE_3
    ]
    assert statistics.mean(map(abs, diffs)) < 5.0
    assert abs(statistics.mean(diffs)) < 5.0


def test_the_table_is_not_quietly_shrinking():
    """ASSERTS ITS OWN SETUP. The paper states its own count in prose --
    "these were 17 compounds and 22 values" -- so the corpus can be checked
    against the source rather than against itself."""
    assert len(TABLE_3) == 22
    assert len({smiles for _n, _name, smiles, _i, _p in TABLE_3}) == 17


# --- what the declared total rests on ---------------------------------------
#
# `_gasteiger_total`'s docstring asserts these in prose ("measured to 1e-6
# on an anion, a cation, a zwitterion and a neutral molecule") and nothing
# checked them. They are the reason the panel is entitled to call that sum
# a net charge at all.


@pytest.mark.parametrize(
    "name, smiles, formal",
    [
        ("acetate", "CC(=O)[O-]", -1),
        ("ammonium", "C[NH3+]", 1),
        ("glycine zwitterion", "[NH3+]CC(=O)[O-]", 0),
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", 0),
        ("guanidinium", "NC(N)=[NH2+]", 1),
    ],
)
def test_peoe_conserves_total_charge(name, smiles, formal):
    """WITH the hydrogens, the sum IS the formal charge -- which is what
    makes "Net calculated charge" an honest label rather than a coincidence
    somebody noticed once."""
    from openchem.chem.descriptor_providers import compute_gasteiger_charges

    total = sum(
        compute_gasteiger_charges(
            Chem.MolFromSmiles(smiles), include_hydrogens=True
        ).values()
    )
    assert total == pytest.approx(formal, abs=1e-6)


def test_the_heavy_atom_sum_is_NOT_the_formal_charge():
    """THE NUMBER THE DECLARATION EXISTS TO STOP PRINTING.

    RDKit keeps each heavy atom's implicit-hydrogen charge in a separate
    property, so with hydrogens excluded neutral aspirin's visible atoms
    sum to -0.6555 -- and a panel that summed what it could see would print
    that as the molecule's net charge. Ammonium is the sharper case: +1
    formal, and its visible atoms sum to about -0.30.
    """
    from openchem.chem.descriptor_providers import compute_gasteiger_charges

    aspirin = sum(
        compute_gasteiger_charges(
            Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"), include_hydrogens=False
        ).values()
    )
    assert aspirin == pytest.approx(-0.6555, abs=5e-4)

    ammonium = sum(
        compute_gasteiger_charges(
            Chem.MolFromSmiles("C[NH3+]"), include_hydrogens=False
        ).values()
    )
    assert ammonium < 0, "a +1 cation whose visible atoms sum negative"
