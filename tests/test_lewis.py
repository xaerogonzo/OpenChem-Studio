"""Lewis donor and acceptor sites, and where the rules decline to answer.

Every verdict below was MEASURED from a real run before it was asserted,
and the first run corrected four things that had looked obviously right
while being written:

- Iron(III) was REFUSED as a radical. High-spin Fe(III) genuinely has five
  unpaired d electrons, but it is also the textbook hard Lewis acid, and
  refusing on it would have thrown away most of coordination chemistry.
  The unpaired-electron guard now applies only where the electron-PAIR
  arithmetic actually runs, which is main-group atoms.
- Carbon tetrabromide flagged two of its four equivalent bromines. That
  was RDKit's match uniquifying, not chemistry -- see `_motif_sites`.
- Carbon monoxide came out a pure donor, missing the pi acceptance that
  makes it interesting at all.
- Nitro nitrogen was flagged as an acceptor, which it is not.

The negative controls are load-bearing. Methane, ethane and benzene must
report nothing, or a rule that flags every carbon would pass the rest of
this file.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.lewis import analyse, compute_lewis_sites, lone_pairs, octet_deficiency
from openchem.domain.lewis import AcceptorMechanism, LewisRole, LewisStrength
from openchem.domain.structure_issue import Basis

EMPTY = AcceptorMechanism.EMPTY_ORBITAL
PI_STAR = AcceptorMechanism.LOW_LYING_PI_STAR
SIGMA_STAR = AcceptorMechanism.LOW_LYING_SIGMA_STAR
VACANT = AcceptorMechanism.VACANT_COORDINATION_SITE


def mol_for(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def unsanitized_mol_for(smiles: str):
    """For structures RDKit refuses to sanitize, which is most of the point.

    Diborane cannot be parsed normally at all -- its bridging hydrogen has
    two bonds and sanitization rejects the boron's valence. A structure
    that will not sanitize is exactly the kind this module has to REFUSE
    gracefully rather than crash on, so it has to be able to receive one.
    Matches `test_oxidation_states.mol_for`, which parses this way for the
    same reason.
    """
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    assert mol is not None, smiles
    mol.UpdatePropertyCache(strict=False)
    return mol


def roles(smiles: str) -> dict[str, LewisRole]:
    """Role per atom, labelled `Symbol+index` so a failure reads."""
    mol = mol_for(smiles)
    result = analyse(mol)
    assert not result.refused, f"unexpectedly refused: {result.reason}"
    return {f"{s.symbol}{s.atom_index}": s.role for s in result.sites}


def mechanisms_at(smiles: str, atom_index: int) -> set[AcceptorMechanism]:
    site = analyse(mol_for(smiles)).site_for(atom_index)
    assert site is not None, f"no site at atom {atom_index} of {smiles}"
    return set(site.mechanisms)


# --- the verdict table ------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "smiles", "atom_index", "mechanism"),
    [
        # An atom short of a filled shell has somewhere to put a pair.
        ("boron trifluoride", "FB(F)F", 1, EMPTY),
        ("aluminium trichloride", "Cl[Al](Cl)Cl", 1, EMPTY),
        ("tert-butyl cation", "C[C+](C)C", 1, EMPTY),
        # A metal centre with room in its coordination sphere. None of
        # these has an "empty p orbital", which is why that framing was
        # rejected in favour of naming the mechanism.
        ("iron(III)", "[Fe+3]", 0, VACANT),
        ("zinc(II)", "[Zn+2]", 0, VACANT),
        ("titanium tetrachloride", "Cl[Ti](Cl)(Cl)Cl", 1, VACANT),
        # A filled shell and still a strong acid -- only the pi* rule can
        # find these, which is the whole reason it exists.
        ("sulfur trioxide", "O=S(=O)=O", 1, PI_STAR),
        ("acetone carbonyl", "CC(C)=O", 1, PI_STAR),
        ("methyl vinyl ketone, beta carbon", "C=CC(C)=O", 0, PI_STAR),
        ("acetonitrile carbon", "CC#N", 1, PI_STAR),
        # The sigma hole opposite a polarised bond -- halogen bonding.
        ("iodobenzene", "Ic1ccccc1", 0, SIGMA_STAR),
        ("carbon tetrabromide", "BrC(Br)(Br)Br", 0, SIGMA_STAR),
    ],
)
def test_each_acceptor_mechanism_is_found_where_it_should_be(
    label, smiles, atom_index, mechanism
):
    assert mechanism in mechanisms_at(smiles, atom_index), label


@pytest.mark.parametrize(
    ("label", "smiles", "atom_index"),
    [
        ("ammonia", "N", 0),
        ("water", "O", 0),
        ("pyridine", "c1ccncc1", 3),
        ("diethyl ether", "CCOCC", 2),
        ("triphenylphosphine", "c1ccccc1P(c1ccccc1)c1ccccc1", 6),
        ("acetone oxygen", "CC(C)=O", 3),
    ],
)
def test_lone_pair_bearing_atoms_are_donors(label, smiles, atom_index):
    site = analyse(mol_for(smiles)).site_for(atom_index)
    assert site is not None, label
    assert site.role in (LewisRole.DONOR, LewisRole.AMBIPHILIC), label
    assert site.lone_pairs, label


@pytest.mark.parametrize(
    ("label", "smiles"),
    [("methane", "C"), ("ethane", "CC"), ("benzene", "c1ccccc1")],
)
def test_a_saturated_hydrocarbon_has_no_lewis_site_at_all(label, smiles):
    """The control that stops every other test in this file being free.

    A rule flagging any carbon, or counting a bonding pair as a lone pair,
    lights all three of these up.
    """
    assert analyse(mol_for(smiles)).sites == (), label


# --- ambiphilic, by all three routes ---------------------------------------


def test_carbon_monoxide_is_ambiphilic_on_carbon():
    """The molecule this whole feature exists for.

    A negligible Bronsted base that forms an isolable adduct with borane.
    It has to come out as a donor AND an acceptor on the same atom, or the
    tool repeats the mistake it was built to fix.
    """
    result = analyse(mol_for("[C-]#[O+]"))
    carbon = result.site_for(0)
    assert carbon.role is LewisRole.AMBIPHILIC
    assert carbon.lone_pairs == 1
    assert PI_STAR in carbon.mechanisms


def test_carbon_monoxide_reports_both_candidate_donors_without_choosing():
    """The honest limit, asserted so it cannot quietly become a guess.

    Carbon and oxygen each carry a lone pair and the arithmetic cannot
    separate them; CO donates through carbon because its HOMO is
    carbon-localised, which needs a wavefunction. Two candidates are
    reported and the limitation says so.
    """
    result = analyse(mol_for("[C-]#[O+]"))
    assert {s.atom_index for s in result.donors()} == {0, 1}
    assert any("donates through carbon" in text for text in result.limitations)


def test_a_halogen_bond_donor_is_ambiphilic_not_merely_an_acceptor():
    """Iodine here is a halogen-bond donor along C-I and a nucleophile
    perpendicular to it. Both are true at once, which is what the role
    exists to express."""
    site = analyse(mol_for("Ic1ccccc1")).site_for(0)
    assert site.role is LewisRole.AMBIPHILIC
    assert SIGMA_STAR in site.mechanisms
    assert site.lone_pairs == 3


def test_a_singlet_carbene_is_ambiphilic_by_arithmetic_alone():
    """The empty-orbital route to ambiphilic, with no motif involved.

    Constructed rather than parsed, because RDKit CANNOT represent a
    singlet carbene: sanitization recomputes a divalent neutral carbon as
    two radical electrons, and re-adds them even after they are cleared.
    Zeroing them post-sanitize is the only route, and is exactly why a
    carbene drawn in the editor is refused instead.
    """
    mol = mol_for("CN1C=CN(C)[C]1")
    carbene = next(a for a in mol.GetAtoms() if a.GetNumRadicalElectrons())
    carbene.SetNoImplicit(True)
    carbene.SetNumRadicalElectrons(0)

    assert lone_pairs(carbene) == 1
    assert octet_deficiency(carbene) == 2

    site = analyse(mol).site_for(carbene.GetIdx())
    assert site.role is LewisRole.AMBIPHILIC
    assert EMPTY in site.mechanisms
    assert {e.basis for e in site.evidence} == {Basis.DETERMINISTIC}


# --- evidence ---------------------------------------------------------------


def test_an_atom_that_two_rules_agree_on_keeps_both_reasons():
    """Aluminium in AlCl3 is short of an octet AND has coordination room --
    it dimerises to Al2Cl6 through exactly that. Evidence is a list so
    "why is this atom highlighted" has a real answer; collapsing to the
    word "acceptor" would throw it away.
    """
    site = analyse(mol_for("Cl[Al](Cl)Cl")).site_for(1)
    assert set(site.mechanisms) == {EMPTY, VACANT}
    assert len({e.rule for e in site.evidence}) == 2


def test_every_piece_of_evidence_names_its_own_rule_and_basis():
    for smiles in ("FB(F)F", "CC(C)=O", "Cl[Ti](Cl)(Cl)Cl", "Ic1ccccc1"):
        for site in analyse(mol_for(smiles)).sites:
            assert site.evidence, f"{smiles} atom {site.atom_index} has a role but no reason"
            for evidence in site.evidence:
                assert evidence.rule.strip(), smiles
                assert evidence.note.strip(), smiles
                assert isinstance(evidence.basis, Basis), smiles


def test_arithmetic_rules_are_deterministic_and_motif_rules_are_not():
    """The two bases are not decoration: an octet count is arithmetic, and
    "this looks like a Michael acceptor" is judgement. A reader has to be
    able to tell which they are looking at."""
    boron = analyse(mol_for("FB(F)F")).site_for(1)
    assert [e.basis for e in boron.evidence] == [Basis.DETERMINISTIC]

    michael = analyse(mol_for("C=CC(C)=O")).site_for(0)
    assert [e.basis for e in michael.evidence] == [Basis.HEURISTIC]


def test_strength_is_never_claimed_offline():
    """Nothing here can rank two donors, so nothing here says it can."""
    for smiles in ("FB(F)F", "N", "[C-]#[O+]", "Cl[Ti](Cl)(Cl)Cl", "CC(C)=O"):
        for site in analyse(mol_for(smiles)).sites:
            assert site.strength is LewisStrength.UNKNOWN, smiles


def test_the_heuristic_limitation_appears_only_when_a_motif_rule_fired():
    """A near-miss for the limitation text itself. BF3 is all arithmetic,
    so claiming a motif caveat there would be noise."""
    motif = "found by structural motif"
    assert any(motif in text for text in analyse(mol_for("CC(C)=O")).limitations)
    assert not any(motif in text for text in analyse(mol_for("FB(F)F")).limitations)


# --- the arithmetic ---------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "smiles", "atom_index", "expected"),
    [
        ("ammonia nitrogen", "N", 0, 1),
        ("water oxygen", "O", 0, 2),
        ("fluoride on boron", "FB(F)F", 0, 3),
        ("boron itself", "FB(F)F", 1, 0),
        ("carbonyl oxygen", "CC(C)=O", 3, 2),
        ("ammonium nitrogen", "[NH4+]", 0, 0),
    ],
)
def test_lone_pair_counts(label, smiles, atom_index, expected):
    atom = mol_for(smiles).GetAtomWithIdx(atom_index)
    assert lone_pairs(atom) == expected, label


def test_lone_pairs_declines_on_a_metal_rather_than_inventing_two():
    """Measured before the guard was written: the naive arithmetic gives
    iron(III) "two lone pairs" when it is d5 with five UNPAIRED electrons,
    which is not a donor pair at all. RDKit reports iron's valence list as
    [-1] -- no defined valence -- which is the same signal the valence
    checker and the oxidation-state module already act on."""
    for smiles in ("[Fe+3]", "[Zn+2]", "Cl[Ti](Cl)(Cl)Cl"):
        mol = mol_for(smiles)
        metal = next(a for a in mol.GetAtoms() if a.GetSymbol() in ("Fe", "Zn", "Ti"))
        assert lone_pairs(metal) is None, smiles
        assert octet_deficiency(metal) is None, smiles


@pytest.mark.parametrize(
    ("label", "smiles", "atom_index", "expected"),
    [
        ("boron in BF3, two short", "FB(F)F", 1, 2),
        ("carbocation, two short", "C[C+](C)C", 1, 2),
        ("ammonia nitrogen, complete", "N", 0, 0),
        ("methane carbon, complete", "C", 0, 0),
        # Hydrogen fills at two, not eight -- without the duet rule every
        # hydrogen in every structure reads as six electrons short.
        ("hydrogen in water", "O", 0, 0),
    ],
)
def test_octet_deficiency(label, smiles, atom_index, expected):
    atom = mol_for(smiles).GetAtomWithIdx(atom_index)
    assert octet_deficiency(atom) == expected, label


def test_hydrogen_is_not_reported_as_electron_deficient():
    """The duet rule, checked on explicit hydrogens rather than implicit
    ones. Against a hard-coded octet every hydrogen in the tree becomes an
    acceptor, which would bury every real finding."""
    mol = Chem.AddHs(mol_for("O"))
    for atom in mol.GetAtoms():
        if atom.GetSymbol() == "H":
            assert octet_deficiency(atom) == 0
    assert not [s for s in analyse(mol).sites if s.symbol == "H"]


# --- symmetry ---------------------------------------------------------------


def test_symmetry_equivalent_atoms_all_get_the_same_verdict():
    """A regression on RDKit's match uniquifying, which reported two of
    carbon tetrabromide's four equivalent bromines as halogen-bond donors
    and two as plain donors. Nothing chemical distinguishes them; it was
    which match happened to be kept."""
    result = analyse(mol_for("BrC(Br)(Br)Br"))
    bromines = [s for s in result.sites if s.symbol == "Br"]
    assert len(bromines) == 4
    assert {s.role for s in bromines} == {LewisRole.AMBIPHILIC}


# --- refusals, each with a near-miss ---------------------------------------


def test_an_open_shell_main_group_centre_is_refused():
    result = analyse(mol_for("[CH3]"))
    assert result.refused
    assert "unpaired electrons" in result.reason


def test_but_an_open_shell_metal_is_not():
    """The near-miss for the guard above, and the bug it was written from.

    Iron(III) carries five unpaired electrons and is still the textbook
    hard Lewis acid. The pair arithmetic never runs on a metal, so nothing
    about it is invalidated.
    """
    result = analyse(mol_for("[Fe+3]"))
    assert not result.refused, result.reason
    assert VACANT in mechanisms_at("[Fe+3]", 0)


def test_a_query_atom_is_refused():
    mol = Chem.MolFromSmiles("*c1ccccc1")
    result = analyse(mol)
    assert result.refused
    assert "query or R-group" in result.reason


def test_a_structure_our_bonding_model_cannot_describe_is_refused():
    """Diborane's 3c-2e bridges. The reason comes from `oxidation_states`
    rather than being re-derived here, so the two cannot drift apart."""
    result = analyse(unsanitized_mol_for("[H]B1([H])[H]B([H])([H])[H]1"))
    assert result.refused
    assert "bridg" in result.reason.lower()


def test_the_near_miss_for_that_refusal_still_answers():
    """A plain borane adduct is not a cluster and must not be swept up."""
    result = analyse(mol_for("FB(F)F"))
    assert not result.refused, result.reason


def test_a_refusal_carries_a_reason_and_no_sites():
    result = analyse(mol_for("[CH3]"))
    assert result.sites == ()
    assert result.reason
    assert not result  # __bool__ follows OxidationStates


# --- the registry-facing calculator ----------------------------------------


def test_the_calculator_reports_sites_grouped_by_role():
    result = compute_lewis_sites(mol_for("[C-]#[O+]"), "uuid-1")
    assert result.category == "lewis"
    text = "\n".join(result.matched)
    assert "Ambiphilic sites" in text
    # The ambiphilic carbon appears ONCE. `donors()` and `acceptors()` both
    # include it -- right for a caller asking "can this donate", and
    # duplicated noise when the same line is read top to bottom.
    assert text.count("C1: ambiphilic") == 1


def test_the_calculator_surfaces_assumptions_and_limitations():
    text = "\n".join(compute_lewis_sites(mol_for("CC(C)=O"), "uuid-1").matched)
    assert "Assumption:" in text
    assert "Limitation:" in text


def test_the_calculator_fails_loudly_on_a_refusal():
    result = compute_lewis_sites(mol_for("[CH3]"), "uuid-1")
    assert result.matched == []
    assert "unpaired electrons" in result.error


def test_the_calculator_is_registered_in_the_lewis_category():
    """Registered rather than merely importable -- a direct-import test
    once passed while the registration bound to a shadowed function."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "lewis_sites"
    )
    assert definition.category == "lewis"
    result = definition.execution.compute(mol_for("FB(F)F"), "uuid-1", {})
    assert any("empty valence orbital" in line for line in result.matched)


def test_turning_off_motif_sites_leaves_only_the_arithmetic():
    """Acetone's carbonyl carbon is found by motif and its oxygen by
    arithmetic. Asking for arithmetic only must drop the first and keep
    the second, rather than dropping both or neither."""
    both = "\n".join(compute_lewis_sites(mol_for("CC(C)=O"), "u", {}).matched)
    assert "C2: acceptor" in both

    strict = "\n".join(
        compute_lewis_sites(mol_for("CC(C)=O"), "u", {"include_heuristic": False}).matched
    )
    assert "C2: acceptor" not in strict
    assert "O4: donor" in strict
    assert "[heuristic]" not in strict


def test_dropping_motif_evidence_also_re_derives_the_role():
    """Iodine in iodobenzene is ambiphilic only because a motif matched
    alongside its lone pairs. With motifs off it is a plain donor -- the
    stale label would be a worse answer than not offering the option."""
    strict = "\n".join(
        compute_lewis_sites(mol_for("Ic1ccccc1"), "u", {"include_heuristic": False}).matched
    )
    assert "I1: donor" in strict
    assert "ambiphilic" not in strict


def test_protonation_state_changes_the_donor_set():
    """Not a cosmetic setting, and measured against the real Dimorphite-DL.

    Methylamine donates through nitrogen. Its ammonium at pH 2 has no lone
    pair and does not donate AT ALL -- a different answer rather than the
    same one restated. pH 11 is the near-miss that stops this passing for
    a version that simply returns nothing whenever microspecies is on.

    Written first with a parameter name that does not exist
    (`microspecies_ph`), which `apply_microspecies` ignored silently: the
    run looked identical to the neutral one and the option was dead. The
    real names are `major_microspecies` and `pH`.
    """
    neutral = compute_lewis_sites(mol_for("CN"), "u", {})
    assert any("N2: donor" in line for line in neutral.matched)

    acidic = compute_lewis_sites(mol_for("CN"), "u", {"major_microspecies": True, "pH": 2.0})
    assert any("microspecies at pH 2" in line for line in acidic.matched), (
        "microspecies never ran, so the chemistry below would be vacuous"
    )
    assert not any("N2: donor" in line for line in acidic.matched)
    assert not any(line.startswith("Donor sites:") for line in acidic.matched)

    basic = compute_lewis_sites(mol_for("CN"), "u", {"major_microspecies": True, "pH": 11.0})
    assert any("N2: donor" in line for line in basic.matched)


def test_the_lewis_category_has_a_label_and_a_place_in_the_order():
    from openchem.ui.panels.property_panel import _CATEGORY_LABELS, _CATEGORY_ORDER

    assert _CATEGORY_LABELS["lewis"] == "Lewis Acid/Base"
    # Immediately after pKa: the Bronsted answer and the point where it
    # stops being the whole answer belong next to each other.
    assert _CATEGORY_ORDER.index("lewis") == _CATEGORY_ORDER.index("pka") + 1
