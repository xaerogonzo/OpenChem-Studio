"""What `ResonanceMolSupplier` can and cannot tell a Lewis structure.

**THE GATE for the full Lewis diagram.** The whole feature rests on one
idea -- a delocalised bond still has a localised sigma component, and only
the excess is delocalised:

    localised pairs on a bond = its MINIMUM order across every
                                resonance structure
    delocalised electrons     = (kekulised total - localised) x 2

Every claim below is measured against the real RDKit, and the ones that
FAIL are as important as the ones that pass: they are the cases the
diagram must decline rather than answer.

**THE TOTAL MUST COME FROM A KEKULISED COPY.** Summing bond orders over
the aromatic form counts 1.5 per bond, and naphthalene then reports 11
delocalised electrons against a textbook 10. Integer orders throughout.

**`KEKULE_ALL` ALONE, and that is measured rather than chosen.** Adding
`ALLOW_CHARGE_SEPARATION` does not fix the five-membered aromatics it
looks like it should, and it breaks amide -- which gains 2 delocalised
electrons from a charge-separated contributor that a Lewis structure has
no business drawing.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

#: How many resonance structures to enumerate. Measured: no fixture here
#: reaches even 16, so this is headroom rather than a working limit --
#: but the truncation path is still implemented and tested, because
#: "no input I tried hit it" is not "no input can".
MAX_STRUCTURES = 256


def delocalised_electrons(smiles: str, flags=Chem.KEKULE_ALL, limit=MAX_STRUCTURES):
    """The measured quantity, and the arithmetic the feature will use."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    orders: dict[tuple[int, int], set[int]] = {}
    structures = 0
    for resonance in Chem.ResonanceMolSupplier(mol, flags, maxStructs=limit):
        if resonance is None:
            continue
        structures += 1
        for bond in resonance.GetBonds():
            key = (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
            orders.setdefault(key, set()).add(int(bond.GetBondTypeAsDouble()))
    if not orders:
        return None
    kekulised = Chem.Mol(mol)
    Chem.Kekulize(kekulised, clearAromaticFlags=True)
    total = sum(int(b.GetBondTypeAsDouble()) for b in kekulised.GetBonds())
    localised = sum(min(v) for v in orders.values())
    return {
        "delocalised": (total - localised) * 2,
        "localised_pairs": localised,
        "kekule_total": total,
        "structures": structures,
        "truncated": structures >= limit,
    }


#: TEXTBOOK counts, authored by hand from the electron budget.
#:
#: **TWO OF THESE WERE WRONG WHEN FIRST WRITTEN.** Nitrate and carbonate
#: were put down as 4 from intuition; both are 2 -- three sigma bonds and
#: ONE pi pair delocalised over three oxygens, with the rest of the
#: budget in lone pairs. The code was right and the oracle was not, which
#: is exactly the direction this project warns about: an oracle derived
#: from a run cannot catch a classifier bug, and an oracle written
#: carelessly invents one.
CORRECT = {
    "benzene": ("c1ccccc1", 6),
    "pyridine": ("c1ccncc1", 6),
    "naphthalene": ("c1ccc2ccccc2c1", 10),
    "anthracene": ("c1ccc2cc3ccccc3cc2c1", 14),
    "acetate": ("CC(=O)[O-]", 2),
    "nitromethane": ("C[N+](=O)[O-]", 2),
    "nitrate": ("[N+](=O)([O-])[O-]", 2),
    "carbonate": ("C(=O)([O-])[O-]", 2),
    "guanidinium": ("NC(N)=[NH2+]", 2),
    "allyl anion": ("[CH2-]C=C", 2),
    "ozone": ("[O-][O+]=O", 2),
    "ethanol": ("CCO", 0),
    "ethene": ("C=C", 0),
    "ethyne": ("C#C", 0),
    "carbon dioxide": ("O=C=O", 0),
    "amide": ("CC(=O)N", 0),
}

#: Aromatic rings whose sextet is completed by a heteroatom LONE PAIR
#: rather than by a varying bond order. The bond-order method cannot see
#: them and must not pretend to.
LONE_PAIR_AROMATICS = {
    "pyrrole": "c1cc[nH]c1",
    "furan": "c1ccoc1",
    "thiophene": "c1ccsc1",
}

#: Expanded-octet species. Whether they are drawn with expanded octets or
#: as charge-separated is genuinely contested, and this application has no
#: position to take.
HYPERVALENT = {
    "sulfate": "[O-]S(=O)(=O)[O-]",
    "phosphate": "[O-]P(=O)([O-])[O-]",
    "sulfur hexafluoride": "FS(F)(F)(F)(F)F",
    "dimethyl sulfoxide": "CS(=O)C",
    "sulfite": "[O-]S(=O)[O-]",
    "phosphine oxide": "CP(=O)(C)C",
}


def expanded_octets(mol) -> list[str]:
    """Atoms carrying more than eight electrons, by the count itself.

    **NOT by RDKit's valence list**, which was the first rule and does not
    work: `GetValenceList(16)` is `[2, 4, 6]`, so sulfur(VI) is a
    perfectly NORMAL valence to RDKit and sulfate goes undetected. The
    octet is the thing actually in question, so the octet is what is
    counted -- and it needs no element list, which would rot.
    """
    from openchem.chem.lewis import lone_pairs

    mol.UpdatePropertyCache(strict=False)
    flagged = []
    for atom in mol.GetAtoms():
        if atom.GetSymbol() in ("H", "He"):
            continue
        pairs = lone_pairs(atom)
        if pairs is None:
            continue
        if 2 * (int(atom.GetTotalValence()) + pairs) > 8:
            flagged.append(atom.GetSymbol())
    return flagged


@pytest.mark.parametrize("case", list(CORRECT), ids=list(CORRECT))
def test_the_delocalised_electron_count_matches_the_textbook(case):
    smiles, expected = CORRECT[case]

    result = delocalised_electrons(smiles)

    assert result is not None, f"{case}: nothing was analysed"
    assert result["delocalised"] == expected, (
        f"{case}: {result['delocalised']} delocalised electrons, expected {expected} "
        f"({result['localised_pairs']} localised pairs, kekule total "
        f"{result['kekule_total']}, {result['structures']} structures)"
    )


def test_the_total_must_come_from_a_KEKULISED_copy():
    """Naphthalene is the case that proves it.

    Summed over the aromatic form its bonds count 1.5 each, giving 16.5
    and 11 delocalised electrons against a textbook 10. The error is
    small enough to look like a rounding wobble and is a whole electron.
    """
    mol = Chem.MolFromSmiles("c1ccc2ccccc2c1")
    aromatic_total = sum(b.GetBondTypeAsDouble() for b in mol.GetBonds())
    kekulised = Chem.Mol(mol)
    Chem.Kekulize(kekulised, clearAromaticFlags=True)
    kekule_total = sum(int(b.GetBondTypeAsDouble()) for b in kekulised.GetBonds())

    assert aromatic_total == pytest.approx(16.5)
    assert kekule_total == 16
    assert delocalised_electrons("c1ccc2ccccc2c1")["delocalised"] == 10


@pytest.mark.parametrize("case", list(LONE_PAIR_AROMATICS), ids=list(LONE_PAIR_AROMATICS))
def test_a_lone_pair_aromatic_reports_ZERO_and_must_therefore_ABSTAIN(case):
    """**THE LIMIT THAT SHAPES THE FEATURE.**

    Pyrrole has one Kekule structure, so no bond order varies, so the
    arithmetic says zero electrons are delocalised. The truth is six --
    four from the two C=C and two from the nitrogen's lone pair, which is
    IN the ring. `ResonanceMolSupplier` does not enumerate the
    contributors that move it there.

    So the diagram may not report a number here. The bonds are flagged
    delocalised by aromaticity perception; the COUNT is
    `UNKNOWN(reason)` -- never 0, which would be a lie, and never a
    fabricated 6.

    Asserted as a DEFECT on purpose: if a future RDKit starts
    enumerating those contributors, this fails and the abstention can go.
    """
    result = delocalised_electrons(LONE_PAIR_AROMATICS[case])

    assert result["structures"] == 1, result
    assert result["delocalised"] == 0, result
    assert Chem.MolFromSmiles(LONE_PAIR_AROMATICS[case]).GetBondWithIdx(0).GetIsAromatic()


def test_charge_separation_does_not_help_and_actively_hurts():
    """Why the flags are `KEKULE_ALL` and nothing else.

    `ALLOW_CHARGE_SEPARATION` looks like the fix for the case above and
    is not: pyrrole and furan are unchanged at zero. What it does change
    is AMIDE, which gains two delocalised electrons from a
    charge-separated contributor -- a real resonance form, but not one a
    Lewis structure draws, and the neutral form is the representation.
    """
    both = Chem.KEKULE_ALL | Chem.ALLOW_CHARGE_SEPARATION

    assert delocalised_electrons("c1cc[nH]c1", both)["delocalised"] == 0
    assert delocalised_electrons("c1ccoc1", both)["delocalised"] == 0
    assert delocalised_electrons("CC(=O)N", both)["delocalised"] == 2
    assert delocalised_electrons("CC(=O)N", Chem.KEKULE_ALL)["delocalised"] == 0


@pytest.mark.parametrize("case", list(HYPERVALENT), ids=list(HYPERVALENT))
def test_an_expanded_octet_looks_LOCALISED_and_must_abstain(case):
    """Sulfate's four S-O bonds are equivalent; the arithmetic sees one
    resonance structure and would report them cleanly localised, with
    zero delocalised electrons.

    That is not wrong so much as a position this application has not
    taken -- expanded octet versus charge-separated is contested, and the
    diagram abstains with that reason rather than picking one.
    """
    mol = Chem.MolFromSmiles(HYPERVALENT[case])
    result = delocalised_electrons(HYPERVALENT[case])

    assert result["structures"] == 1, result
    assert result["delocalised"] == 0, result
    assert expanded_octets(mol), f"{case}: nothing looks hypervalent, so the rule cannot fire"


def test_a_charge_separated_perchlorate_is_NOT_hypervalent():
    """The control, and what stops the rule flagging anything with an
    oxygen on it.

    Written `[O-][Cl+3]([O-])([O-])[O-]` the chlorine has four single
    bonds and no lone pair -- eight electrons, the octet obeyed exactly.
    That representation needs no abstention, which is worth knowing: the
    contested question is the EXPANDED-OCTET DRAWING, not the species.
    """
    assert expanded_octets(Chem.MolFromSmiles("[O-][Cl+3]([O-])([O-])[O-]")) == []
    for ordinary in ("O", "c1ccccc1", "CC(=O)[O-]", "[N+](=O)([O-])[O-]", "CCO"):
        assert expanded_octets(Chem.MolFromSmiles(ordinary)) == [], ordinary


def _charge_vectors(smiles: str) -> set[tuple[int, ...]]:
    mol = Chem.MolFromSmiles(smiles)
    return {
        tuple(a.GetFormalCharge() for a in resonance.GetAtoms())
        for resonance in Chem.ResonanceMolSupplier(mol, Chem.KEKULE_ALL, maxStructs=64)
        if resonance is not None
    }


def test_FORMAL_CHARGES_DO_MOVE_so_they_come_from_the_input():
    """**A first probe said the opposite, on a sample that could not show
    it.** It tried anthracene, pentacene, porphine and the hypervalent
    set -- all neutral, most symmetric -- and reported that the charge
    vector is identical in every contributor. Acetate says otherwise: the
    negative sits on one oxygen or the other,

        (0, 0, -1, 0)  and  (0, 0, 0, -1)

    which is the entire point of drawing it delocalised.

    So a per-atom formal charge must be read from the INPUT molecule,
    where it is well defined, and never from whichever contributor the
    supplier happened to yield first. Neutral systems are asserted
    alongside it, because "charges are stable" is true for exactly the
    sample that hid this.
    """
    assert _charge_vectors("CC(=O)[O-]") == {(0, 0, -1, 0), (0, 0, 0, -1)}
    assert len(_charge_vectors("C(=O)([O-])[O-]")) > 1, "carbonate too"

    for neutral in ("c1ccccc1", "c1ccc2ccccc2c1", "CCO", "CC(=O)N"):
        assert len(_charge_vectors(neutral)) == 1, neutral

    # And the input's own charges are the ones that balance the books.
    acetate = Chem.MolFromSmiles("CC(=O)[O-]")
    assert sum(a.GetFormalCharge() for a in acetate.GetAtoms()) == -1


def test_the_enumeration_is_small_and_fast_on_hard_systems():
    """Anthracene 4, pentacene 6, porphine 2 -- and none reaches even 16.

    So the cap is headroom rather than a working limit, which is what
    makes the fail-closed branch a safety net instead of everyday
    behaviour.

    **This measurement is why that branch was for a long time SHIPPED AND
    NEVER RUN.** No ordinary input reaches the cap, so nothing exercised
    it, and a mutation making it unreachable survived the whole suite.
    `test_lewis_builder.py::test_a_TRUNCATED_enumeration_fails_closed`
    now reaches it by lowering the cap instead of by hunting a monstrous
    molecule; this test is its control, and the two only mean something
    together.
    """
    for smiles, expected in (
        ("c1ccc2cc3ccccc3cc2c1", 4),
        ("c1ccc2cc3cc4cc5ccccc5cc4cc3cc2c1", 6),
        ("C1=CC2=CC3=CC=C(N3)C=C4C=CC(=N4)C=C5C=CC(=N5)C=C1N2", 2),
    ):
        result = delocalised_electrons(smiles, limit=16)
        assert result["structures"] == expected, (smiles, result)
        assert not result["truncated"]


def test_a_molecule_with_no_heavy_atom_BONDS_has_nothing_to_measure():
    """Methane. The whole analysis has to run on the EXPLICIT-HYDROGEN
    molecule, which is what a Lewis structure depicts anyway -- on the
    heavy-atom graph it has no bonds at all and the arithmetic has
    nothing to work with."""
    assert delocalised_electrons("C") is None

    with_hydrogens = Chem.AddHs(Chem.MolFromSmiles("C"))
    assert with_hydrogens.GetNumBonds() == 4
