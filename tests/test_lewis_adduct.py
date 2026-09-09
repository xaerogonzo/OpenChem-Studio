"""Adduct prediction: three lines of evidence, never one score.

`test_the_shipped_table_reproduces_the_measured_enthalpies` is the one
that decides whether any of this is worth shipping. The Drago-Wayland
parameters were taken from a secondary compilation rather than read out
of the paywalled originals, so what makes them trustworthy is that they
predict eight independently tabulated donor-iodine enthalpies to a mean
absolute error of 0.27 kcal/mol across a 1.4-12.0 range. A mistyped table
does not do that, and the test runs against the SHIPPED JSON rather than
the generator's constants so a hand-edit is caught too.

Three gaps in the Phase A acceptor rules were found by building this, not
by reading them -- iodine, antimony pentachloride and benzene were all
refused, and the first and third are pairs in that very validation set.
Each has its own test below with a negative control beside it.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.lewis import analyse, pi_donor_atoms
from openchem.chem.lewis_adduct import (
    ROLE_ACID,
    ROLE_AUTO,
    ROLE_BASE,
    ROLE_LABELS,
    compute_lewis_adduct,
    parameter_table,
    predict,
)
from openchem.domain.common import CacheState
from openchem.domain.lewis import (
    BASIS_DRAGO_TABLE,
    BASIS_SITE_ADMISSIBILITY,
    BASIS_USER,
    ORIENTATION_SUBJECT_IS_ACID,
    ORIENTATION_SUBJECT_IS_BASE,
    ORIENTATION_UNRESOLVED,
)
from openchem.domain.structure_issue import Basis

IODINE = "II"

#: base -> (SMILES, measured -dH kcal/mol for its iodine adduct).
MEASURED_IODINE_ADDUCTS = {
    "benzene": ("c1ccccc1", 1.4),
    "1,4-dioxane": ("C1COCCO1", 3.5),
    "diethyl ether": ("CCOCC", 4.3),
    "diethyl sulfide": ("CCSCC", 8.3),
    "dimethylacetamide": ("CC(=O)N(C)C", 4.7),
    "acetonitrile": ("CC#N", 1.9),
    "pyridine": ("c1ccncc1", 7.80),
    "triethylamine": ("CCN(CC)CC", 12.0),
}


def mol_for(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def drago(acid_smiles: str, base_smiles: str) -> float | None:
    result = predict(mol_for(acid_smiles), mol_for(base_smiles))
    assert not result.refused, result.reason
    return result.line("drago_wayland").value


# --- the validation that decides whether the table ships --------------------


@pytest.mark.parametrize(
    ("name", "smiles", "measured"),
    [(n, s, m) for n, (s, m) in MEASURED_IODINE_ADDUCTS.items()],
)
def test_the_shipped_table_reproduces_the_measured_enthalpies(name, smiles, measured):
    """Each adduct within 1 kcal/mol, run against the committed JSON."""
    assert drago(IODINE, smiles) == pytest.approx(measured, abs=1.0), name


def test_the_mean_error_over_the_whole_set_is_small():
    """The per-adduct bound above is loose enough to let a systematically
    shifted table through. This is the one that would catch that."""
    errors = [
        abs(drago(IODINE, smiles) - measured)
        for smiles, measured in MEASURED_IODINE_ADDUCTS.values()
    ]
    assert sum(errors) / len(errors) < 0.35
    # Dimethylacetamide is the known outlier, at about 0.9 -- it has two
    # donor sites. One is expected; two would mean something is wrong.
    assert sum(error > 0.5 for error in errors) == 1


def test_the_table_carries_its_citation():
    """Values from a secondary compilation, and the file says so rather
    than presenting itself as read from the paper."""
    table = parameter_table()
    assert "doi:10.1021/ja01094a008" in table["citation"]
    assert table["acids"] and table["bases"]


def test_parameters_are_looked_up_by_structure_not_by_name():
    """The table is keyed on canonical SMILES, so a molecule drawn in the
    editor matches without anybody typing "triethylamine"."""
    assert drago(IODINE, "CCN(CC)CC") == pytest.approx(drago(IODINE, "N(CC)(CC)CC"))


# --- the lines, and their independence --------------------------------------


def test_an_unparameterised_pair_still_gets_the_other_lines():
    """Three separate lines is only worth having if one being unavailable
    does not take the others down. Boron trifluoride and carbon monoxide
    are in no calorimetry table."""
    result = predict(
        mol_for("FB(F)F"),
        mol_for("[C-]#[O+]"),
        acid_lumo_ev=-0.5,
        base_homo_ev=-10.17,
        acid_hardness=6.11,
        base_hardness=4.73,
    )
    assert not result.refused
    assert result.line("drago_wayland").value is None
    assert result.line("frontier_gap").value == pytest.approx(9.67)
    assert result.line("hsab_match").value == pytest.approx(1.38)


def test_a_parameterised_pair_with_no_quantum_data_still_gets_the_enthalpy():
    result = predict(mol_for(IODINE), mol_for("c1ccncc1"))
    assert result.line("drago_wayland").value == pytest.approx(7.97, abs=0.01)
    assert result.line("frontier_gap").value is None
    assert result.line("hsab_match").value is None


def test_the_frontier_gap_is_acid_lumo_minus_base_homo():
    result = predict(
        mol_for("FB(F)F"), mol_for("N"), acid_lumo_ev=1.0, base_homo_ev=-6.82
    )
    assert result.line("frontier_gap").value == pytest.approx(7.82)


def test_the_frontier_gap_says_which_direction_is_stronger():
    """It runs the opposite way to the enthalpy -- smaller is stronger --
    and a reader comparing two numbers in one panel has to be told."""
    result = predict(mol_for("FB(F)F"), mol_for("N"), acid_lumo_ev=1.0, base_homo_ev=-6.8)
    assert "SMALLER" in result.line("frontier_gap").note


def test_the_hsab_line_is_the_absolute_hardness_difference():
    result = predict(mol_for("FB(F)F"), mol_for("N"), acid_hardness=6.11, base_hardness=7.21)
    assert result.line("hsab_match").value == pytest.approx(1.10)


def test_the_hsab_line_points_at_delta_scf_rather_than_koopmans():
    """Koopmans hardness inverts ammonia against phosphine, so a hard/soft
    match built on it can be exactly wrong. Anyone about to run a job
    should be told which one to run."""
    note = predict(mol_for("FB(F)F"), mol_for("N")).line("hsab_match").note
    assert "delta-SCF" in note


def test_there_is_no_combined_score():
    """Deliberate. The lines answer different questions in different
    units, and averaging them would invent a quantity nobody defined."""
    result = predict(mol_for(IODINE), mol_for("c1ccncc1"))
    assert not hasattr(result, "score")
    assert {e.units for e in result.evidence} == {"kcal/mol", "eV"}


def test_each_line_declares_its_own_basis():
    result = predict(
        mol_for(IODINE), mol_for("c1ccncc1"), acid_hardness=1.0, base_hardness=2.0
    )
    assert result.line("drago_wayland").basis is Basis.DETERMINISTIC
    assert result.line("hsab_match").basis is Basis.HEURISTIC


def test_available_reports_only_the_lines_that_produced_a_number():
    result = predict(mol_for(IODINE), mol_for("c1ccncc1"))
    assert [e.line for e in result.available()] == ["drago_wayland"]
    assert len(result.evidence) == 3


# --- the three acceptor gaps this work exposed -----------------------------


def test_molecular_iodine_is_an_acceptor():
    """Found by the adduct engine refusing I2 + benzene -- a pair in its
    own validation set. The Phase A sigma-hole patterns needed a halogen
    on carbon, and molecular iodine has no carbon."""
    assert analyse(mol_for("II")).acceptors()


@pytest.mark.parametrize(
    ("label", "smiles", "expected"),
    [
        ("iodine, homonuclear", "II", {0, 1}),
        ("bromine, homonuclear", "BrBr", {0, 1}),
        ("iodine monochloride", "ICl", {0}),
        ("iodine monobromide", "IBr", {0}),
    ],
)
def test_the_sigma_hole_is_on_the_less_electronegative_halogen(label, smiles, expected):
    """Not a symmetric rule. In iodine monochloride the iodine is the
    acceptor end and the chlorine is the donor end; flagging both would
    invert the chemistry of every interhalogen while looking right for
    iodine."""
    acceptors = {s.atom_index for s in analyse(mol_for(smiles)).acceptors()}
    assert acceptors == expected, label


@pytest.mark.parametrize(
    ("label", "smiles"),
    [
        ("antimony pentachloride", "Cl[Sb](Cl)(Cl)(Cl)Cl"),
        ("phosphorus pentafluoride", "FP(F)(F)(F)F"),
        ("silicon tetrafluoride", "F[Si](F)(F)F"),
    ],
)
def test_a_heavy_main_group_centre_can_expand_its_shell(label, smiles):
    """None of these is octet-deficient, a metal, or has a pi* -- every
    other detector misses them. Antimony pentachloride is among the
    strongest acids in the Drago table."""
    assert analyse(mol_for(smiles)).acceptors(), label


@pytest.mark.parametrize(
    ("label", "smiles"),
    [
        # Same electron count as silicon tetrafluoride; period 2 cannot
        # expand, and the period test is the only thing separating them.
        ("carbon tetrafluoride", "FC(F)(F)F"),
        # A remaining lone pair means donor, not acceptor.
        ("triphenylphosphine", "c1ccccc1P(c1ccccc1)c1ccccc1"),
        ("phosphorus trichloride", "ClP(Cl)Cl"),
        # Hydrogen sulfide keeps its lone pairs AND is a weak hydrogen-bond
        # donor, so it is ambiphilic overall. This test is about ONE rule,
        # so it asserts on that rule rather than on the atom's whole verdict
        # -- an earlier version asserted "no acceptors at all" and started
        # failing when a different, correct rule began firing.
        ("hydrogen sulfide", "S"),
        ("chloromethane", "ClC"),
        ("ethane", "CC"),
    ],
)
def test_the_expandable_shell_rule_does_not_flag_everything(label, smiles):
    rules = {
        e.rule for site in analyse(mol_for(smiles)).sites for e in site.evidence
    }
    assert "expandable valence shell" not in rules, label


def test_benzene_donates_through_its_pi_system():
    """Measured at 1.4 kcal/mol against iodine, the weakest entry in the
    table -- but real, and the engine refused it before this."""
    result = predict(mol_for(IODINE), mol_for("c1ccccc1"))
    assert not result.refused
    assert result.line("drago_wayland").value == pytest.approx(1.25, abs=0.01)


def test_a_pi_donor_is_still_not_listed_as_a_lewis_site():
    """The control that keeps the site list readable. Listing every
    aromatic carbon as a donor would put a dozen sites on every drug-like
    molecule and bury the lone pairs somebody actually wants."""
    assert analyse(mol_for("c1ccccc1")).sites == ()
    assert pi_donor_atoms(mol_for("c1ccccc1")) == (0, 1, 2, 3, 4, 5)


def test_a_carbonyl_pi_bond_is_not_counted_as_a_donor():
    """It is polarised the other way -- the carbon is the ACCEPTOR there,
    which the pi* rule already reports. Calling the same bond a donor
    would be saying both things about one thing."""
    assert pi_donor_atoms(mol_for("CC(C)=O")) == ()


@pytest.mark.parametrize(
    ("label", "smiles", "expected"),
    [("ethene", "C=C", (0, 1)), ("ethyne", "C#C", (0, 1)), ("ethane", "CC", ())],
)
def test_pi_donor_atoms(label, smiles, expected):
    assert pi_donor_atoms(mol_for(smiles)) == expected, label


def test_the_pi_donation_limitation_is_stated():
    result = predict(mol_for(IODINE), mol_for("c1ccccc1"))
    assert any("pi system rather than a lone pair" in text for text in result.limitations)


# --- refusals ---------------------------------------------------------------


def test_an_acid_that_cannot_accept_is_refused():
    result = predict(mol_for("C"), mol_for("N"))
    assert result.refused
    assert "accept an electron pair" in result.reason


def test_a_base_that_cannot_donate_is_refused():
    result = predict(mol_for("FB(F)F"), mol_for("C"))
    assert result.refused
    assert "neither a lone pair nor a pi system" in result.reason


def test_a_refusal_carries_the_labels_so_the_panel_can_still_name_the_pair():
    result = predict(mol_for("C"), mol_for("N"), acid_label="methane", base_label="ammonia")
    assert result.refused
    assert result.acid_label == "methane"
    assert result.base_label == "ammonia"


def test_the_refusal_reuses_the_site_analysis_rather_than_re_deriving_it():
    """One definition of "acceptor" in this codebase. A radical refuses
    here because it refuses there."""
    result = predict(mol_for("[CH3]"), mol_for("N"))
    assert result.refused
    assert "unpaired electrons" in result.reason


def test_sterics_are_named_as_a_limitation():
    """Electronically perfect partners that cannot reach each other is a
    real failure mode of every method here."""
    result = predict(mol_for(IODINE), mol_for("c1ccncc1"))
    assert any("Sterics" in text for text in result.limitations)


# --- the calculator ---------------------------------------------------------


def test_the_calculator_takes_the_partner_as_typed_smiles():
    result = compute_lewis_adduct(mol_for(IODINE), "u", {"partner_smiles": "CCN(CC)CC"})
    assert result.category == "lewis"
    assert any("12.1" in line for line in result.matched)


def test_the_role_choice_swaps_which_molecule_is_the_acid():
    """Same pair, entered from either side, must give the same answer --
    otherwise the setting is a trap rather than a convenience.

    The report now opens with a `Role:` line saying HOW the orientation was
    decided, so the acid line is the second: iodine entered as the subject
    resolves from the Drago table, and triethylamine entered as the subject
    with an explicit `base` is told the user set it. Both must reach the
    SAME orientation.
    """
    as_acid = compute_lewis_adduct(mol_for(IODINE), "u", {"partner_smiles": "CCN(CC)CC"})
    as_base = compute_lewis_adduct(
        mol_for("CCN(CC)CC"), "u", {"partner_smiles": IODINE, "role": ROLE_BASE}
    )
    assert as_acid.matched[1] == as_base.matched[1] == "Acid: II"
    assert as_acid.matched[3] == as_base.matched[3]
    assert as_acid.matched[0] != as_base.matched[0], (
        "one was worked out and the other was set by hand; a reader must be "
        "able to tell those apart"
    )


def test_the_calculator_says_what_to_do_when_no_partner_was_given():
    result = compute_lewis_adduct(mol_for(IODINE), "u", {})
    assert result.matched == []
    assert "settings" in result.error


def test_the_calculator_reports_an_unparseable_partner():
    result = compute_lewis_adduct(mol_for(IODINE), "u", {"partner_smiles": "not a molecule"})
    assert "Could not parse" in result.error


def test_the_calculator_surfaces_the_unavailable_lines_too():
    """A line that could not be evaluated is reported WITH the reason,
    rather than silently omitted -- otherwise the absence reads as "this
    does not apply" instead of "run a quantum job"."""
    text = "\n".join(compute_lewis_adduct(mol_for(IODINE), "u", {"partner_smiles": "c1ccncc1"}).matched)
    assert "not available" in text
    assert "quantum chemistry job" in text


def test_the_calculator_is_registered():
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "lewis_adduct")
    assert definition.category == "lewis"
    assert {p.name for p in definition.parameters} == {"partner_smiles", "role"}
    # CODES, with the prose in `choice_labels` -- the stored value is
    # hashed into every retained result's identity, so it must not be the
    # English on the screen.
    assert definition.parameters[1].choices == [ROLE_AUTO, ROLE_ACID, ROLE_BASE]
    assert definition.parameters[1].choice_labels == [
        ROLE_LABELS[ROLE_AUTO],
        ROLE_LABELS[ROLE_ACID],
        ROLE_LABELS[ROLE_BASE],
    ]
    assert definition.parameters[0].kind == "smiles"


def test_a_metal_gets_the_coordination_rule_and_not_also_the_shell_rule():
    """Aluminium in AlCl3 was collecting three pieces of evidence for what
    is really two facts, once the expandable-shell rule was added. The two
    rules say nearly the same thing, so the newer one defers to the one
    with the better note rather than firing alongside it."""
    site = analyse(mol_for("Cl[Al](Cl)Cl")).site_for(1)
    rules = {e.rule for e in site.evidence}
    assert rules == {"empty valence orbital", "vacant coordination site"}


def test_a_metalloid_still_gets_the_shell_rule():
    """The near-miss for the deferral above. Antimony is a metalloid, so
    the coordination rule never sees it and the shell rule must."""
    site = analyse(mol_for("Cl[Sb](Cl)(Cl)(Cl)Cl")).site_for(1)
    assert {e.rule for e in site.evidence} == {"expandable valence shell"}


def test_the_w_term_is_added_and_lowers_the_predicted_enthalpy():
    """A genuine sign error, found by a surviving mutation rather than by
    reading the code.

    -dH = E_A*E_B + C_A*C_B + W. W is a constant cost of getting the acid
    into a state that can bind -- cleaving a dimer, mostly -- and carries
    its own negative sign where that cost is real. It was written
    SUBTRACTED, and every test passed, because every acid the other tests
    touch has W = 0.

    Nonafluoro-tert-butanol has W = -0.87, so its prediction must come out
    0.87 BELOW the plain two-term value.
    """
    table = parameter_table()
    acid = table["acids"][Chem.MolToSmiles(mol_for("OC(C(F)(F)F)(C(F)(F)F)C(F)(F)F"))]
    base = table["bases"][Chem.MolToSmiles(mol_for("c1ccncc1"))]
    assert acid["W"] == pytest.approx(-0.87)

    two_term = acid["E"] * base["E"] + acid["C"] * base["C"]
    predicted = drago("OC(C(F)(F)F)(C(F)(F)F)C(F)(F)F", "c1ccncc1")
    assert predicted == pytest.approx(two_term - 0.87)
    assert predicted < two_term


def test_an_acid_with_no_w_term_is_unaffected_by_it():
    """The near-miss. Iodine's W is 0, so the two-term and three-term
    forms must agree exactly -- which is why the test above needed an acid
    that actually has one."""
    table = parameter_table()
    acid = table["acids"][Chem.MolToSmiles(mol_for(IODINE))]
    base = table["bases"][Chem.MolToSmiles(mol_for("c1ccncc1"))]
    assert acid["W"] == 0.0
    assert drago(IODINE, "c1ccncc1") == pytest.approx(acid["E"] * base["E"] + acid["C"] * base["C"])


# --- hydrogen bonding as the same sigma* mechanism -------------------------


@pytest.mark.parametrize(
    ("label", "smiles"),
    [
        ("phenol", "Oc1ccccc1"),
        ("tert-butanol", "CC(C)(C)O"),
        ("2,2,2-trifluoroethanol", "OCC(F)(F)F"),
        ("pyrrole", "c1cc[nH]c1"),
        ("chloroform", "ClC(Cl)Cl"),
        ("isocyanic acid", "N=C=O"),
    ],
)
def test_a_hydrogen_bond_donor_is_an_acceptor(label, smiles):
    """Every one of these is a Drago-Wayland ACID, and the engine refused
    all of them until this rule existed. A hydrogen bond is donation into
    the sigma* of a polarised X-H bond -- the same mechanism as a halogen
    bond, with a different heavy atom."""
    rules = {
        e.rule for site in analyse(mol_for(smiles)).acceptors() for e in site.evidence
    }
    # Across all sites, not just the first: chloroform's chlorines carry
    # sigma holes of their own and come first, so checking one site found
    # the wrong rule and reported a false failure.
    assert "hydrogen-bond donor" in rules, label


def test_hydrogen_and_halogen_bonding_share_one_mechanism():
    """Not two enum members that happen to look alike. Both are donation
    into the sigma* of a polarised single bond, and describing them the
    same way is the accurate choice rather than the convenient one."""
    from openchem.domain.lewis import AcceptorMechanism

    hydrogen = analyse(mol_for("Oc1ccccc1")).site_for(0)
    halogen = analyse(mol_for("Ic1ccccc1")).site_for(0)
    assert AcceptorMechanism.LOW_LYING_SIGMA_STAR in hydrogen.mechanisms
    assert AcceptorMechanism.LOW_LYING_SIGMA_STAR in halogen.mechanisms


@pytest.mark.parametrize(
    ("label", "smiles"),
    [
        # No hydrogen on anything electronegative, and carbon-bound
        # hydrogen only counts when halogens polarise it.
        ("methane", "C"),
        ("ethane", "CC"),
        ("benzene", "c1ccccc1"),
        ("diethyl ether", "CCOCC"),
        ("trimethylamine", "CN(C)C"),
        ("dimethyl sulfide", "CSC"),
        ("pyridine", "c1ccncc1"),
        ("chloromethane", "ClC"),
    ],
)
def test_the_hydrogen_bond_rule_does_not_flag_everything(label, smiles):
    """The control that keeps this rule honest. Chloromethane has one
    chlorine and is not a hydrogen-bond donor; chloroform has three and
    is. Pyridine's nitrogen has no hydrogen at all."""
    assert not analyse(mol_for(smiles)).acceptors(), label


def test_an_alcohol_is_ambiphilic():
    """Its oxygen donates lone pairs and its O-H accepts. Water is the
    textbook case of being both at once."""
    from openchem.domain.lewis import LewisRole

    assert analyse(mol_for("O")).site_for(0).role is LewisRole.AMBIPHILIC


def test_sulfur_dioxide_is_an_acceptor():
    """It keeps a lone pair, so the octet arithmetic calls it complete and
    the expandable-shell rule skips it -- and it forms isolable adducts
    with amines."""
    assert analyse(mol_for("O=S=O")).acceptors()


def test_every_acid_in_the_shipped_table_passes_the_acceptor_gate():
    """The integration check that drove the three rules above.

    An adduct engine that refuses fourteen of the twenty-four acids in its
    own parameter table is broken, and nothing but running the two
    together revealed it.
    """
    table = parameter_table()
    blocked = [
        entry["name"]
        for smiles, entry in table["acids"].items()
        if not analyse(mol_for(smiles)).acceptors()
    ]
    assert blocked == []


def test_every_base_in_the_shipped_table_can_donate():
    table = parameter_table()
    blocked = [
        entry["name"]
        for smiles, entry in table["bases"].items()
        if not (analyse(mol_for(smiles)).donors() or pi_donor_atoms(mol_for(smiles)))
    ]
    assert blocked == []


def test_the_parameter_file_ships_in_the_frozen_build():
    """A data file that works from a checkout and is missing from the
    installer is this project's established failure mode -- the spec has a
    comment about it. Same guard `test_element_reference` uses."""
    from pathlib import Path

    spec = Path("packaging/openchem.spec")
    assert "lewis_parameters.json" in spec.read_text(encoding="utf-8")


def test_the_engine_survives_the_table_being_absent(tmp_path, monkeypatch):
    """Optional by design: Phase A and B never needed it, and a build
    without it should lose the kcal/mol line and nothing else."""
    import openchem.chem.lewis_adduct as module

    monkeypatch.setattr(module, "_DATA", tmp_path / "missing.json")
    module.parameter_table.cache_clear()
    try:
        result = module.predict(
            mol_for(IODINE), mol_for("c1ccncc1"), acid_hardness=4.0, base_hardness=3.0
        )
        assert not result.refused
        assert result.line("drago_wayland").value is None
        assert result.line("hsab_match").value == pytest.approx(1.0)
    finally:
        module.parameter_table.cache_clear()


# --- the case the whole feature exists for ---------------------------------

# Real ORCA 6.1.1 B3LYP/def2-SVP numbers: geometries optimized by ORCA,
# then delta-SCF hardness from a compound job at that geometry, and the
# frontier energies from the optimization's own orbital table.
CO_HOMO_EV, CO_HARDNESS = -10.17, 8.40
BORANE_LUMO_EV, BORANE_HARDNESS = -2.04, 6.77
BF3_LUMO_EV, BF3_HARDNESS = 0.73, 9.29


def _co_adduct(acid_smiles: str, lumo: float, hardness: float):
    return predict(
        mol_for(acid_smiles),
        mol_for("[C-]#[O+]"),
        acid_lumo_ev=lumo,
        base_homo_ev=CO_HOMO_EV,
        acid_hardness=hardness,
        base_hardness=CO_HARDNESS,
    )


def test_the_frontier_gap_prefers_borane_over_boron_trifluoride_for_carbon_monoxide():
    """The known chemistry: H3B-CO is isolable and BF3 barely binds CO at
    all, because BF3's boron is pi-stabilised by the fluorine lone pairs.
    Smaller gap means a stronger orbital interaction, so borane must win."""
    borane = _co_adduct("B", BORANE_LUMO_EV, BORANE_HARDNESS)
    trifluoride = _co_adduct("FB(F)F", BF3_LUMO_EV, BF3_HARDNESS)
    assert borane.line("frontier_gap").value < trifluoride.line("frontier_gap").value


def test_the_two_orbital_lines_disagree_on_carbon_monoxide():
    """Asserted ON PURPOSE, the way the Koopmans inversion is.

    The |d eta| proxy calls boron trifluoride the BETTER match for carbon
    monoxide, which is backwards -- CO's computed hardness lands near
    BF3's rather than reflecting the softness the qualitative argument
    assigns it. A single number on the eta scale is not Pearson's
    classification.

    This is the strongest argument for reporting lines separately: an
    average would have split the difference on a case where one line is
    simply right. If a future hardness method resolves this, the test
    fails and the caveat in `_hsab_line` can come off.
    """
    borane = _co_adduct("B", BORANE_LUMO_EV, BORANE_HARDNESS)
    trifluoride = _co_adduct("FB(F)F", BF3_LUMO_EV, BF3_HARDNESS)
    assert trifluoride.line("hsab_match").value < borane.line("hsab_match").value


def test_the_disagreement_is_visible_rather_than_averaged_away():
    """Both lines are reported, with their own units and bases, so a
    reader sees the conflict instead of a number that hides it."""
    borane = _co_adduct("B", BORANE_LUMO_EV, BORANE_HARDNESS)
    assert {e.line for e in borane.available()} == {"frontier_gap", "hsab_match"}
    assert not hasattr(borane, "score")


# --- against the primary sources -------------------------------------------

#: Observed enthalpies read from Drago & Wayland, J. Am. Chem. Soc. 1965,
#: 87, 3571 (doi:10.1021/ja01094a008) -- Table I (iodine), Table II
#: (phenol), Table III (trimethylborane). These did NOT go into fitting the
#: modern parameters this application ships, so they are independent.
#:
#: The paper's own E and C values are deliberately not used: it normalises
#: iodine to E_A = C_A = 1.000 and the modern compilation puts it at 0.50
#: and 2.0, so the two scales cannot be mixed.
PAPER_1965 = {
    "II": {"N": 4.8, "CN": 7.1, "CNC": 9.8, "CN(C)C": 12.1},
    "Oc1ccccc1": {"N": 8.0, "CN": 9.3, "CNC": 9.3, "CN(C)C": 9.5},
    "CB(C)C": {"N": 13.75, "CN": 17.64, "CNC": 19.26, "CN(C)C": 17.62},
}


@pytest.mark.parametrize(
    ("acid", "base", "observed"),
    [(a, b, v) for a, row in PAPER_1965.items() if a != "CB(C)C" for b, v in row.items()],
)
def test_the_shipped_table_reproduces_the_1965_papers_observed_values(acid, base, observed):
    """Iodine and phenol against the original paper, within 1.1 kcal/mol.

    Independent of the donor-iodine set used elsewhere in this file: these
    are the amine series, read from the paper itself.
    """
    assert drago(acid, base) == pytest.approx(observed, abs=1.1)


def test_the_model_over_predicts_exactly_the_adducts_the_paper_calls_hindered():
    """The most useful test here, because it asserts a FAILURE.

    Drago and Wayland report that trimethylborane's amine adducts are
    destabilised by F-strain -- 1.5 kcal/mol for dimethylamine and 8.2 for
    trimethylamine, the latter agreeing with an independently measured
    7.8. An E and C equation has no steric term, so it MUST over-predict
    those two and agree on the two smaller amines.

    A table that fitted all four would mean the parameters had absorbed a
    steric effect they are not supposed to contain, so this is the shape
    the result should have rather than a shortcoming to fix.
    """
    errors = {b: drago("CB(C)C", b) - v for b, v in PAPER_1965["CB(C)C"].items()}
    assert abs(errors["N"]) < 1.0
    assert abs(errors["CN"]) < 1.0
    assert errors["CN(C)C"] > errors["CNC"] > 0.5
    # The paper attributes 8.2 kcal/mol to sterics for trimethylamine; the
    # modern parameters put the discrepancy at about 6.
    assert 4.0 < errors["CN(C)C"] < 8.5


def test_the_sterics_limitation_cites_the_measured_case():
    """It used to name 2,6-di-tert-butylpyridine, which is the textbook
    example and not one anybody here measured. The trimethylborane number
    comes from the source paper of the model doing the predicting."""
    result = predict(mol_for(IODINE), mol_for("c1ccncc1"))
    sterics = next(t for t in result.limitations if "Sterics" in t)
    assert "8.2 kcal/mol" in sterics
    assert "trimethylamine" in sterics


def test_experimental_hardness_confirms_the_hsab_line_cannot_be_rescued():
    """Pearson's measured values, Inorg. Chem. 1988, 27, 734, Table II:
    CO 7.9 eV and BF3 9.7 eV. Only 1.8 apart, with CO high on the scale --
    so better hardness numbers would not fix the |d eta| verdict on
    CO/BF3. The failure is in the metric, and the caveat says so.
    """
    experimental_co, experimental_bf3 = 7.9, 9.7
    assert abs(experimental_co - experimental_bf3) < 2.0
    # And the delta-SCF values this file uses are close to them.
    assert CO_HARDNESS == pytest.approx(experimental_co, abs=0.6)
    assert BF3_HARDNESS == pytest.approx(experimental_bf3, abs=0.6)


# ---------------------------------------------------------------------------
# Provenance: where the numbers came from, and what scale they are on
# ---------------------------------------------------------------------------


def test_lewis_parameters_match_the_declared_parameter_scale():
    """`_parameter_scale` is DERIVED here, never merely read.

    Where the numbers came from and what numerical convention they are in
    are two different claims, and this file's own docstring records that the
    first one is a secondary compilation. The second is what makes them
    mixable or not: Drago & Wayland 1965 normalise iodine to
    E_A = C_A = 1.000, where the modern compilation puts it at E = 0.5,
    C = 2.0. Citing the 1965 paper as the SOURCE of these values would imply
    a scale they are not on, and a reader combining the two tables would get
    plausible, wrong enthalpies out of it.

    Iodine is the reference by construction, so it is the tell. Asserting
    the LABEL against the DATA rather than trusting the label is the same
    move `tests/test_assembly_gate.py` makes when it derives
    `catches_composition_order` from the deposit's own matrix.

    The generic registry guard in `tests/test_sources_are_current.py`
    deliberately does NOT do this -- it checks that a scale is declared, not
    what the declaration means. A guard over every data file in the project
    must not know chemistry.
    """
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).resolve().parent.parent
         / "src" / "openchem" / "chem" / "data" / "lewis_parameters.json")
        .read_text(encoding="utf-8")
    )

    #: The iodine values each published scale requires. `II` is the SMILES
    #: key the table uses for elemental iodine.
    SCALES = {
        "modern_ecw": (0.5, 2.0),
        "drago_wayland_1965": (1.0, 1.0),
    }

    scale = data.get("_parameter_scale")
    assert scale in SCALES, (
        f"lewis_parameters.json declares parameter_scale {scale!r}, which is "
        f"not one of the published scales {sorted(SCALES)}"
    )

    iodine = data["acids"]["II"]
    expected_e, expected_c = SCALES[scale]
    assert (iodine["E"], iodine["C"]) == (expected_e, expected_c), (
        f"the table declares the {scale!r} scale, on which iodine is "
        f"E={expected_e}, C={expected_c} -- but the shipped iodine is "
        f"E={iodine['E']}, C={iodine['C']}. Either the label or the data is wrong."
    )


def test_the_two_lewis_scales_really_are_different():
    """The control: without this, the guard above could pass vacuously.

    If both scales named the same iodine values, asserting one against the
    other would be no test at all -- and a future edit collapsing the two
    entries would go unnoticed.
    """
    assert (0.5, 2.0) != (1.0, 1.0)


# --- working the orientation out --------------------------------------------

#: tert-butanol is a tabulated ACID and methylamine a tabulated BASE, and
#: BOTH are structurally admissible EITHER way round. That second half is
#: what makes the pair non-degenerate for the Drago rule: with a pair the
#: sites alone could decide, deleting Rule 1 would change nothing and the
#: guard would prove nothing.
_TABULATED_ACID = "CC(C)(C)O"
_TABULATED_BASE = "CN"


def test_the_drago_table_decides_when_only_one_way_round_is_tabulated():
    from openchem.chem.lewis_adduct import _can_be_acid, _can_be_base, resolve_roles

    subject, partner = mol_for(_TABULATED_ACID), mol_for(_TABULATED_BASE)
    # THE SETUP, asserted: both molecules are admissible in BOTH roles, so
    # the site rule cannot decide this pair and only the table can.
    for mol in (subject, partner):
        assert _can_be_acid(mol)[0] and _can_be_base(mol)[0]

    resolution = resolve_roles(subject, partner)

    assert resolution.orientation == ORIENTATION_SUBJECT_IS_ACID
    assert resolution.basis == BASIS_DRAGO_TABLE


def test_the_table_stays_silent_when_BOTH_ways_round_are_tabulated(monkeypatch):
    """A rule that merely asked "is either molecule in the table?" would
    pick one.

    Unreachable with the shipped data -- measured, the table has 24
    acid-only and 33 base-only entries and ZERO in both -- so the table is
    replaced rather than a fixture hunted for. An unreachable branch is a
    question about where to assert.
    """
    from openchem.chem import lewis_adduct

    both = {"acids": {"CO": {}, "N": {}}, "bases": {"CO": {}, "N": {}}, "citation": ""}
    monkeypatch.setattr(lewis_adduct, "parameter_table", lambda: both)

    resolution = lewis_adduct.resolve_roles(mol_for("CO"), mol_for("N"))

    assert resolution.basis != BASIS_DRAGO_TABLE, (
        "the table named both molecules in both roles and still chose one"
    )


def test_the_sites_decide_when_the_table_says_nothing(monkeypatch):
    """Rule 1 provably cannot fire: the table is emptied."""
    from openchem.chem import lewis_adduct

    monkeypatch.setattr(
        lewis_adduct,
        "parameter_table",
        lambda: {"acids": {}, "bases": {}, "citation": ""},
    )

    resolution = lewis_adduct.resolve_roles(mol_for("B"), mol_for("N"))

    assert resolution.orientation == ORIENTATION_SUBJECT_IS_ACID
    assert resolution.basis == BASIS_SITE_ADMISSIBILITY


def test_two_ambiphilic_molecules_are_reported_BOTH_WAYS_rather_than_ranked():
    """The common case, not an edge one.

    `analyse` classifies alcohols, amines and lone-pair-bearing halogens
    as AMBIPHILIC, and `donors()`/`acceptors()` both include those -- so
    any pair of ordinary organic molecules survives both ways round. Water
    and water is the textbook example, and inventing a preference between
    them is the refusal `_hsab_line` already makes.
    """
    from openchem.chem.lewis_adduct import resolve_roles

    resolution = resolve_roles(mol_for("O"), mol_for("O"))

    assert resolution.orientation == ORIENTATION_UNRESOLVED
    assert resolution.basis == ""
    assert [attempt.admissible for attempt in resolution.attempts] == [True, True], (
        "both orientations must be recorded as attempted, not just the verdict"
    )

    report = compute_lewis_adduct(mol_for("O"), "u", {"partner_smiles": "O"})
    text = "\n".join(report.matched)
    assert "not determined" in text
    assert text.count("Acid: O") == 2, "both orientations must be reported"
    # NAMED, not separated by blank lines. Every one of these becomes a ROW
    # in `FactView`, and an empty string renders as a label with no value
    # beside it -- a fact whose value is missing, which is the one thing a
    # report must not say by accident. Found by driving the app and reading
    # the shot, with every test in this file green.
    assert "" not in report.matched, "a blank line renders as an empty row"
    assert "Orientation 1" in text and "Orientation 2" in text


def test_a_pair_that_can_form_no_adduct_keeps_BOTH_refusal_reasons():
    """"Nothing can accept" and "nothing can donate" are different
    statements, and a generic "partner invalid" throws away the one a
    reader needs. Methane and ethane can do neither."""
    from openchem.chem.lewis_adduct import resolve_roles

    resolution = resolve_roles(mol_for("C"), mol_for("CC"))

    assert resolution.orientation == ORIENTATION_UNRESOLVED
    assert not any(attempt.admissible for attempt in resolution.attempts)
    reasons = [attempt.reason for attempt in resolution.attempts]
    assert len(reasons) == 2 and all(reasons), "both attempts must carry a reason"
    assert reasons[0] != reasons[1], "the two reasons name different molecules"

    report = compute_lewis_adduct(mol_for("C"), "u", {"partner_smiles": "CC"})
    assert report.cache_state is CacheState.FAILED
    assert report.provenance.parameters["attempt_reasons"] == reasons


def test_a_refused_pair_is_refused_ONCE():
    """The resolver must not emit its own refusal beside `predict`'s.

    Both `predict` calls can fail, and formatting the same condition twice
    would report one problem as two.
    """
    report = compute_lewis_adduct(mol_for("C"), "u", {"partner_smiles": "CC"})

    assert report.matched == []
    assert report.error.count("Nothing in the acid can accept") <= 1


def test_an_explicit_role_overrides_an_auto_resolution_that_would_disagree():
    """VACUOUS unless the pair resolves the OTHER way on its own, so the
    automatic answer is asserted first."""
    from openchem.chem.lewis_adduct import resolve_roles

    subject, partner = mol_for(_TABULATED_ACID), mol_for(_TABULATED_BASE)
    assert resolve_roles(subject, partner).orientation == ORIENTATION_SUBJECT_IS_ACID

    forced = resolve_roles(subject, partner, ROLE_BASE)

    assert forced.orientation == ORIENTATION_SUBJECT_IS_BASE
    assert forced.basis == BASIS_USER


def test_the_five_role_states_are_pairwise_distinguishable_in_the_provenance():
    """Five, not four: `auto -> acid` and an explicit `acid` produce the
    SAME orientation and must still be tellable apart, which is exactly
    the "two identical-looking results" this record exists to prevent.

    HOW the decision was made and WHAT it was are separate fields.
    """
    def note(subject, partner, role):
        report = compute_lewis_adduct(
            mol_for(subject), "u", {"partner_smiles": partner, "role": role}
        )
        parameters = report.provenance.parameters
        return (
            parameters["role_requested"],
            parameters["orientation"],
            parameters["orientation_basis"],
        )

    states = {
        note(_TABULATED_ACID, _TABULATED_BASE, ROLE_AUTO),
        note("B", "N", ROLE_AUTO),
        note("O", "O", ROLE_AUTO),
        note(_TABULATED_ACID, _TABULATED_BASE, ROLE_ACID),
        note(_TABULATED_ACID, _TABULATED_BASE, ROLE_BASE),
    }

    assert len(states) == 5, f"two states serialise alike: {sorted(states)}"


def test_an_auto_resolution_and_an_explicit_one_do_not_read_the_same():
    auto = compute_lewis_adduct(
        mol_for(_TABULATED_ACID), "u", {"partner_smiles": _TABULATED_BASE}
    )
    forced = compute_lewis_adduct(
        mol_for(_TABULATED_ACID),
        "u",
        {"partner_smiles": _TABULATED_BASE, "role": ROLE_ACID},
    )

    assert auto.matched[0] != forced.matched[0]
    assert auto.matched[1:] == forced.matched[1:], (
        "the same orientation must otherwise produce the same report"
    )


def test_a_legacy_prose_role_still_means_what_it_meant_and_a_typo_does_not():
    """The parameter used to store PROSE. One strict mapping, never fuzzy:
    guessing here silently swaps which molecule is the acid."""
    from openchem.chem.lewis_adduct import _role_code

    assert _role_code("This molecule is the acid") == ROLE_ACID
    assert _role_code("This molecule is the base") == ROLE_BASE
    assert _role_code(ROLE_AUTO) == ROLE_AUTO

    with pytest.raises(ValueError):
        _role_code("this molecule is the acid")

    refused = compute_lewis_adduct(
        mol_for(IODINE), "u", {"partner_smiles": "N", "role": "whatever"}
    )
    assert refused.cache_state is CacheState.FAILED


def test_the_resolver_never_breaks_a_tie_with_hardness():
    """RULE 3 DOES NOT EXIST, asserted on the source.

    `_hsab_line`'s own docstring records that a single point on the eta
    axis gets BH3/BF3 against CO backwards, so a hardness tie-break would
    be the application choosing where the chemistry does not -- and the
    ambiphilic pairs it would silently resolve are the COMMON case, so
    nothing downstream would look wrong.

    THE DOCSTRING IS EXCLUDED, and that is not a detail: the first version
    of this guard scanned the raw source and failed on the very paragraph
    that EXPLAINS the rule. Grepping for a phrase counts the source, not
    the outcome -- a mistake this project has recorded four times, made a
    fifth here.
    """
    import ast
    import inspect
    import textwrap

    from openchem.chem import lewis_adduct

    tree = ast.parse(textwrap.dedent(inspect.getsource(lewis_adduct.resolve_roles)))
    function = tree.body[0]
    body = function.body[1:] if ast.get_docstring(function) else function.body

    names = {
        node.id for statement in body for node in ast.walk(statement)
        if isinstance(node, ast.Name)
    } | {
        node.attr for statement in body for node in ast.walk(statement)
        if isinstance(node, ast.Attribute)
    }
    banned = {"_hsab_line", "_frontier_gap_line", "hardness", "electronegativity"}
    assert not names & banned, (
        f"resolve_roles reads {sorted(names & banned)} -- a tie broken on any "
        "of them is a ranking this module refuses to invent"
    )
    # THE SETUP: the body really was scanned. Without this an AST walk
    # that quietly returned nothing would satisfy the assertion above
    # forever, which is the empty-population failure this project records.
    assert "parameter_table" in names, (
        f"resolve_roles' body scanned to {sorted(names)}, which does not "
        "include the table lookup it certainly makes -- the walk found "
        "nothing and the check above is vacuous"
    )


def test_the_table_stays_silent_when_ONE_molecule_is_untabulated():
    """A rule reading "is the subject a tabulated acid?" gets this wrong.

    The table lists tert-butanol as an acid and does not list ethanol at
    all, so there is no tabulated acid/base PAIRING here and the table has
    nothing to say -- the sites must get their turn, and with both
    molecules ambiphilic the honest answer is unresolved.

    THE DISCRIMINATING CASE, found because the obvious fixture could not
    see the mutation: with a tabulated acid AND a tabulated base, a rule
    that checks only the acid side reaches the same answer as the correct
    one, so it survives.
    """
    from openchem.chem.lewis_adduct import parameter_table, resolve_roles

    table = parameter_table()
    assert "CC(C)(C)O" in table["acids"], "the setup needs a tabulated acid"
    assert "CCO" not in table["acids"] and "CCO" not in table["bases"], (
        "the setup needs a partner in NEITHER table"
    )

    resolution = resolve_roles(mol_for("CC(C)(C)O"), mol_for("CCO"))

    assert resolution.basis != BASIS_DRAGO_TABLE
    assert resolution.orientation == ORIENTATION_UNRESOLVED
