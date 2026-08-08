"""Perceiving what a structure represents, not just what it contains.

The cases here are the ones that decide whether this is perception or a
pile of booleans: a salt it should be confident about, a salt-shaped thing
it must REFUSE, a mixture that is neither, and a sandwich complex that an
ionic rule reached first would confidently mislabel.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.substance import SubstanceKind, perceive

SODIUM_CHLORIDE = "[Na+].[Cl-]"
CALCIUM_CHLORIDE = "[Ca+2].[Cl-].[Cl-]"
FERROCENE = "[Fe+2].[cH-]1cccc1.[cH-]1cccc1"
METHYLFERROCENE = "[Fe+2].[cH-]1cccc1.Cc1ccc[cH-]1"
FOUR_IONS = "[Na+].[Cl-].[K+].[Br-]"
NEUTRAL_MIXTURE = "CCO.c1ccccc1"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _perceive(smiles: str):
    return perceive(Chem.MolFromSmiles(smiles))


# --- the confident cases ----------------------------------------------------


def test_sodium_chloride_is_a_one_to_one_ionic_salt():
    """What the app could not say before. Its numbers were all correct --
    formula ClNa, mass 58.443 -- and "Bond count: 0" is true of table salt
    and useless about it."""
    substance = _perceive(SODIUM_CHLORIDE)

    assert substance.kind is SubstanceKind.IONIC_SALT
    assert substance.formula_unit == "Na+ · Cl-"
    assert substance.total_charge == 0
    assert "stoichiometry 1:1" in " ".join(substance.evidence)


def test_calcium_chloride_counts_its_two_chlorides():
    """Identical components collapse to a count: CaCl2 is one Ca2+ and two
    Cl-, not three unrelated fragments."""
    substance = _perceive(CALCIUM_CHLORIDE)

    assert substance.kind is SubstanceKind.IONIC_SALT
    assert substance.formula_unit == "Ca2+ · 2 × Cl-"


def test_a_salt_carries_its_evidence():
    """Not a bare verdict. The evidence is what lets a reader disagree."""
    evidence = " | ".join(_perceive(SODIUM_CHLORIDE).evidence)

    assert "charged components" in evidence
    assert "cation Na+" in evidence
    assert "anion Cl-" in evidence


def test_an_ordinary_molecule_is_not_called_a_salt():
    substance = _perceive(ASPIRIN)

    assert substance.kind is SubstanceKind.MOLECULE
    assert substance.associations == ()
    assert substance.coordination is None


# --- the refusal, which is the point ----------------------------------------


def test_four_ions_are_refused_rather_than_guessed():
    """**NaCl + KBr, or NaBr + KCl, or a mixture of four ions.** Nothing in
    the graph decides, so the answer is that it cannot be decided.

    This is what stops the classifier decaying into
    `if charged_components: return "ionic salt"`.
    """
    substance = _perceive(FOUR_IONS)

    assert substance.kind is SubstanceKind.AMBIGUOUS_IONIC
    assert not substance.is_single_substance


def test_the_refusal_keeps_its_reason():
    """"Unknown" would be useless. The reason names what the structure
    fails to encode, which is the actionable half."""
    substance = _perceive(FOUR_IONS)

    assert "does not encode which ions" in substance.reason
    assert "2 distinct cations, 2 distinct anions" in " ".join(substance.evidence)


def test_ambiguous_and_mixture_stay_distinguishable():
    """Different statements: one says the components cannot be paired, the
    other that nothing suggests they are one substance at all. A
    disconnected graph is not one substance merely because its charges
    happen to cancel."""
    ambiguous = _perceive(FOUR_IONS)
    mixture = _perceive(NEUTRAL_MIXTURE)

    assert ambiguous.kind is SubstanceKind.AMBIGUOUS_IONIC
    assert mixture.kind is SubstanceKind.MIXTURE
    assert ambiguous.kind is not mixture.kind


def test_a_neutral_mixture_says_why_it_is_not_one_substance():
    substance = _perceive(NEUTRAL_MIXTURE)

    assert "Nothing in the structure says these are one substance" in substance.reason


# --- organometallic, which an ionic rule would get wrong --------------------


def test_ferrocene_is_organometallic_not_a_salt():
    """**Order matters.** Ferrocene's ionic form is three charged
    fragments whose charges cancel, so an ionic rule reached first would
    confidently call it a 1:2 salt."""
    substance = _perceive(FERROCENE)

    assert substance.kind is SubstanceKind.ORGANOMETALLIC
    assert substance.coordination is not None
    assert substance.coordination.metal_symbol == "Fe"
    assert substance.coordination.oxidation_state == 2


def test_ferrocene_reports_two_named_counts_not_one_coordination_number():
    """**"Coordination number 10" invites the wrong convention** -- it is
    the ten Cp carbons, not ten ligands. Both numbers are named, and
    neither is merged into a single ambiguous figure."""
    coordination = _perceive(FERROCENE).coordination

    assert coordination.ligand_count == 2
    assert coordination.donor_atom_count == 10
    assert [ligand.label for ligand in coordination.ligands] == ["eta5-Cp", "eta5-Cp"]


def test_a_substituted_metallocene_is_still_perceived():
    """The pinned table covers 27 exact structures and returns None for
    anything substituted; the general classifier underneath is what keeps
    methylferrocene from falling through to "ionic salt"."""
    substance = _perceive(METHYLFERROCENE)

    assert substance.kind is SubstanceKind.ORGANOMETALLIC
    labels = [ligand.label for ligand in substance.coordination.ligands]
    assert "eta5-methylCp" in labels


def test_perception_does_not_depend_on_the_namer_having_a_name():
    """**Classification is not naming.** Ferrocene is pinned and carries a
    name; methylferrocene is not and carries none -- and both are
    classified. A card that collapsed to "unknown" because one source came
    up empty would be worth much less."""
    pinned = _perceive(FERROCENE)
    unpinned = _perceive(METHYLFERROCENE)

    assert pinned.perceived_name == "ferrocene"
    assert unpinned.perceived_name == ""
    assert unpinned.kind is pinned.kind


# --- the four relationships, kept apart -------------------------------------


def test_an_ionic_association_is_not_a_bond():
    """`[Na+].[Cl-]` has no RDKit bond and must not grow one. The
    relationship is between COMPONENTS, and is qualitative."""
    substance = _perceive(SODIUM_CHLORIDE)
    molecule = Chem.MolFromSmiles(SODIUM_CHLORIDE)

    assert molecule.GetNumBonds() == 0
    assert len(substance.associations) == 1
    assert substance.associations[0].kind == "ionic"
    assert "opposite formal charges" in substance.associations[0].evidence


def test_an_association_carries_no_distance():
    """It must never acquire one. A distance between two ions needs a 3D
    structure and is a CONTACT measurement even then -- calling it a bond
    length would be wrong. This is what keeps the model coherent when
    crystals arrive, where the same pair has many distances."""
    association = _perceive(SODIUM_CHLORIDE).associations[0]

    assert not hasattr(association, "distance")
    assert not hasattr(association, "length")


def test_geometry_is_absent_without_a_conformer():
    """**Six things attached does not make something octahedral.** That is
    a claim about angles, and a flat drawing has none."""
    for smiles in (FERROCENE, "[Fe](Cl)(Cl)Cl"):
        substance = _perceive(smiles)
        if substance.coordination is not None:
            assert substance.coordination.geometry is None, smiles


# --- adjacent cases, which is where the category errors were ----------------


def test_a_lone_ion_is_an_ion_not_a_coordination_compound():
    """Found by walking the adjacent case rather than by a test failing:
    `[Na+]` came back as a coordination compound with zero ligands, which
    is a category error rather than a rounding one."""
    substance = _perceive("[Na+]")

    assert substance.kind is SubstanceKind.ION
    assert substance.coordination is None


def test_a_polyatomic_anion_is_an_ion():
    substance = _perceive("[O-]S(=O)(=O)[O-]")

    assert substance.kind is SubstanceKind.ION
    assert substance.total_charge == -2


def test_an_empty_structure_does_not_raise():
    assert perceive(Chem.MolFromSmiles("")).components == ()


# --- the cp1252 rule this project has been bitten by three times ------------


@pytest.mark.parametrize(
    "smiles", [SODIUM_CHLORIDE, CALCIUM_CHLORIDE, FERROCENE, FOUR_IONS, NEUTRAL_MIXTURE]
)
def test_every_reported_string_survives_a_windows_console(smiles):
    """These reach `Fact` values, exports and logs. A cp1252 stream raises
    on a typographic minus or an eta, and this project has hit that three
    times in one session. The pretty forms exist separately, for a UI that
    is not writing to a stream."""
    substance = _perceive(smiles)

    for text in (
        substance.formula_unit,
        substance.reason,
        *substance.evidence,
        *(a.describe() for a in substance.associations),
    ):
        text.encode("cp1252")
    if substance.coordination is not None:
        for ligand in substance.coordination.ligands:
            ligand.label.encode("cp1252")
