"""Energetic formulations: several substances, one composite CaHbNcOd.

**THE FEATURE EXISTS BECAUSE THE COMPONENTS ARE INDIVIDUALLY REFUSED.**
Kamlet-Jacobs' arbitrary decomposition is stated only for a compound with
enough oxygen to burn its hydrogen to water but not more than would also
burn its carbon to CO2, and the classic formulation ingredients each fall
outside it -- ammonium nitrate over-oxidised, nitroglycerin over-oxidised,
a fuel oil with no oxygen at all. Their MIXTURES land inside. So this
reaches cases the single-substance path structurally cannot answer rather
than being a convenience over it.

**THE METHOD IS STATED FOR MIXTURES BY ITS OWN AUTHORS**, so compositing
is an application of Kamlet-Jacobs rather than a liberty taken with it:
[source:kamlet1968_iii] evaluates the pressure equation against Table I's
"13 explosive compounds and 14 binary mixtures of three general types",
and [source:kamlet1968_iv] does the same for the velocity.

**BUT NEITHER IS THE ORACLE BELOW, AND THE ORACLE'S PROVENANCE IS THE
WEAKEST THING IN THIS FILE.** The three formulations in
`test_published_formulations_are_reproduced` -- Composition B, Cyclotol,
Pentolite -- carry velocities and pressures that are widely published and
that NOTHING HERE CITES. They were not read out of either paper. This
project has shipped a fixture labelled "verbatim from a real run" whose
energies were typed from memory, and an unsourced number that happens to
be roughly right is that failure exactly.

Recorded rather than quietly relied on, and the tolerances are set to
match: rel=0.04 on velocity and rel=0.08 on pressure are loose enough
that the test is a SANITY CHECK on the compositing -- it would catch a
mixture coming out at half its real speed -- and are not a claim that
Kamlet-Jacobs reproduces these three to that accuracy. Tightening them
without first sourcing the values would be asserting more than is known.

The route to closing it is in [source:kamlet1968_iii]'s own Table I, which
prints measured C-J pressures for RDX/TNT mixtures. It is a scan whose
text layer is OCR-damaged, so transcribing it needs the
render-at-magnification treatment CLAUDE.md requires of any table taken
from a scan -- three separate one-digit OCR errors are on record in this
project from exactly that shortcut.

The load-bearing guard is `test_the_composite_is_mole_weighted_not_mass_weighted`.
Treating the stated MASS fractions as MOLE fractions is silent: it gives a
composite wrong by a few percent per element, still inside the arbitrary's
window, and a perfectly ordinary pressure. Nothing but the composite
formula itself can tell the two apart.
"""

from __future__ import annotations

import pytest

from openchem.chem.energetics import (
    DetonationRefusal,
    FormulationRefusal,
    build_formulation_report,
    composite_formula,
    detonation,
    detonation_of_formulation,
)
from openchem.domain.formulation import FormulationComponent, FormulationModel
from openchem.domain.project import ProjectModel

RDX = "C1N(CN(CN1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]"
TNT = "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]"
PETN = "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]"
AMMONIUM_NITRATE = "[NH4+].[N+](=O)([O-])[O-]"
FUEL_OIL = "CCCCCCCCCCCC"  # dodecane, the usual proxy
NITROGLYCERIN = "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]"


def _c(smiles, fraction, enthalpy, name=""):
    return FormulationComponent(smiles, fraction, enthalpy, name)


ANFO = (_c(AMMONIUM_NITRATE, 0.945, -87.3, "AN"), _c(FUEL_OIL, 0.055, -83.9, "fuel oil"))
COMP_B = (_c(RDX, 0.60, 14.7, "RDX"), _c(TNT, 0.40, -16.0, "TNT"))


# ---------------------------------------------------------------------------
# Why the feature exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles, name",
    [(AMMONIUM_NITRATE, "ammonium nitrate"), (NITROGLYCERIN, "nitroglycerin"), (FUEL_OIL, "fuel oil")],
)
def test_each_formulation_component_is_refused_on_its_own(smiles, name):
    """The single-substance path cannot answer for any of these.

    Asserting the setup for the test below: if these ever start being
    accepted, "the mixture reaches what the component cannot" stops being
    the reason this feature exists and somebody should find out why.
    """
    from rdkit import Chem

    result = detonation(Chem.MolFromSmiles(smiles), 1.0, -50.0)
    assert result.refusal is DetonationRefusal.OUTSIDE_THE_ARBITRARY, name


def test_but_their_mixture_is_answered():
    """ANFO: two refusals in, one answer out."""
    result = detonation_of_formulation(ANFO, 0.85)
    assert result.applicable
    assert result.pressure_kbar > 0
    assert result.velocity_mm_per_us > 0


# ---------------------------------------------------------------------------
# THE load-bearing guard
# ---------------------------------------------------------------------------


def test_the_composite_is_mole_weighted_not_mass_weighted():
    """A formulation is mixed by MASS; `CaHbNcOd` is per MOLE.

    Treating the stated mass fractions as mole fractions is silent --
    measured on ANFO 94.5/5.5:

        mass -> mole (correct)   C0.3195 H4.5857 N1.9468 O2.9201
        mass AS mole (wrong)     C0.6600 H5.2100 N1.8900 O2.8350

    Both land inside Eq. (12)'s window and the oxygen counts differ by 3%,
    so no domain check catches it and the pressure looks ordinary either
    way. Only this assertion does.
    """
    composite = composite_formula(ANFO)
    assert composite.applicable
    assert composite.carbon == pytest.approx(0.3195, abs=5e-4)
    assert composite.hydrogen == pytest.approx(4.5857, abs=5e-4)
    assert composite.nitrogen == pytest.approx(1.9468, abs=5e-4)
    assert composite.oxygen == pytest.approx(2.9201, abs=5e-4)

    # ...and explicitly NOT the mass-as-mole answer.
    assert composite.carbon != pytest.approx(0.66, abs=0.01)


def test_the_mean_molar_mass_is_carried_rather_than_recomputed():
    """It is the bridge between the mole-weighted formula and per-gram Q.

    Two implementations of it would drift, and the drift would be a few
    percent in Q -- invisible.
    """
    composite = composite_formula(ANFO)
    # 1 / sum(w_i / M_i) is the mixture's mean molar mass by definition.
    expected = 1.0 / (0.945 / 80.043 + 0.055 / 170.34)
    assert composite.mean_molar_mass == pytest.approx(expected, rel=1e-3)


def test_the_composite_enthalpy_is_mole_weighted_over_EVERY_component():
    """WRITTEN FROM A SURVIVING MUTATION, which is why it exists at all.

    Dropping every component's ΔHf but the first -- `weighted[:1]` in the
    enthalpy sum -- passed the entire file. It moves Composition B's
    composite from 2.58 to 8.90 kcal/mol, which is a factor of three, and
    NOTHING NOTICED: ΔHf enters Q divided by the mean molar mass, so 6.3
    kcal/mol over ~224 g/mol is about 2% on Q, ~1% on P and ~0.5% on D.
    The published-formulation tolerances are rel=0.08 and rel=0.04, so the
    error fits comfortably underneath them.

    That is the loose-oracle trade named in the module docstring, seen
    from the other side: an oracle slack enough to tolerate an unsourced
    reference value is also slack enough to tolerate a real arithmetic
    fault. So the weighting is asserted DIRECTLY here rather than left to
    be inferred from a pressure.

    Composition B rather than ANFO because its two components carry
    enthalpies of OPPOSITE SIGN (+14.7 and −16.0), so a dropped term moves
    the answer across zero rather than nudging it -- ANFO's two are −87.3
    and −83.9 and would separate far less.
    """
    composite = composite_formula(COMP_B)
    n_rdx, n_tnt = 0.60 / 222.117, 0.40 / 227.132
    expected = (n_rdx * 14.7 + n_tnt * -16.0) / (n_rdx + n_tnt)
    assert composite.enthalpy_kcal_per_mol == pytest.approx(expected, rel=1e-3)

    # ...and explicitly NOT the first component's value alone, which is
    # what dropping a term from the sum produces.
    first_only = (n_rdx * 14.7) / (n_rdx + n_tnt)
    assert composite.enthalpy_kcal_per_mol != pytest.approx(first_only, rel=0.05)


# ---------------------------------------------------------------------------
# The oracle: published formulations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, components, density, velocity, pressure",
    [
        ("Composition B 60/40", COMP_B, 1.717, 7.89, 295),
        ("Cyclotol 77/23", (_c(RDX, 0.77, 14.7), _c(TNT, 0.23, -16.0)), 1.743, 8.25, 313),
        ("Pentolite 50/50", (_c(PETN, 0.50, -128.7), _c(TNT, 0.50, -16.0)), 1.67, 7.47, 255),
    ],
)
def test_published_formulations_are_reproduced(name, components, density, velocity, pressure):
    """A SANITY CHECK ON THE COMPOSITING, not a validation of the method.

    These velocities and pressures are widely published and this file
    cites none of them -- see the module docstring. The tolerances are
    deliberately loose for that reason: they catch a composite formula
    that has gone wrong by a factor, which is what the mass-as-mole error
    would do to an unfamiliar recipe, and they assert nothing about how
    well Kamlet-Jacobs reproduces these three.

    **PENTOLITE IS NOT A THIRD EXAMPLE. IT IS THE ONLY ONE OF THE THREE
    THAT CAN SEE THE LOAD-BEARING ERROR, and that was measured rather than
    reasoned.** Mutating the mole conversion to mass-as-mole fails
    Pentolite and leaves Composition B AND Cyclotol passing -- because RDX
    (222.12) and TNT (227.13) are 2.3% apart in molar mass, so for any
    RDX/TNT recipe the mass fractions and the mole fractions very nearly
    coincide and the bug barely moves the answer. PETN (316.14) against
    TNT is 39% apart, and there it shows.

    So the two RDX/TNT rows are DEGENERATE with respect to the one defect
    this file exists to catch. Do not "simplify" the set by dropping the
    PETN row: the parametrisation would still read as three-way coverage
    and would have none. Same lesson as the assembly corpus that could not
    see a transposed matrix -- a fixture is not big or small, it is
    degenerate or not with respect to a specific mutation.
    """
    result = detonation_of_formulation(components, density)
    assert result.applicable, name
    assert result.velocity_mm_per_us == pytest.approx(velocity, rel=0.04), name
    assert result.pressure_kbar == pytest.approx(pressure, rel=0.08), name


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_fractions_that_do_not_sum_are_refused_rather_than_normalised():
    """94.5 + 5.0 renormalises to an ordinary-looking recipe that is not
    the one anybody meant, and hides the missing half-percent forever."""
    composite = composite_formula((_c(RDX, 0.60, 14.7), _c(TNT, 0.35, -16.0)))
    assert composite.refusal is FormulationRefusal.FRACTIONS_DO_NOT_SUM
    assert "0.95" in composite.detail


def test_an_empty_recipe_is_refused():
    assert composite_formula(()).refusal is FormulationRefusal.NO_COMPONENTS


def test_a_non_chno_component_is_refused_by_name():
    """The refusal names the RECIPE's fault, not the chemistry's.

    `FormulationRefusal` is separate from `DetonationRefusal` for this:
    somebody told "outside the arbitrary" about a recipe that contains an
    aluminium powder would look in entirely the wrong place.
    """
    composite = composite_formula((_c(RDX, 0.7, 14.7), _c("[Al]", 0.3, 0.0)))
    assert composite.refusal is FormulationRefusal.COMPONENT_NOT_CHNO
    assert composite.detail == "[Al]"


def test_the_loading_density_is_required_and_never_derived():
    """rho0 is the MEASURED bulk density of the charge.

    There is no source-backed route from a recipe to it, and pressure goes
    as its SQUARE -- so substituting a weighted average of the components'
    crystal densities would be a large error wearing a plausible number.
    """
    assert detonation_of_formulation(COMP_B, None).refusal is DetonationRefusal.NO_LOADING_DENSITY
    assert detonation_of_formulation(COMP_B, 0.0).refusal is DetonationRefusal.NO_LOADING_DENSITY


def test_a_mixture_can_still_fall_outside_the_arbitrary_and_says_MIXTURE():
    """Compositing does not exempt a recipe from Eq. (12)'s window.

    And the message has to say the MIXTURE is outside it, or a reader goes
    looking for the offending component.
    """
    result = detonation_of_formulation((_c(FUEL_OIL, 0.99, -83.9), _c(RDX, 0.01, 14.7)), 1.2)
    assert result.refusal is DetonationRefusal.OUTSIDE_THE_ARBITRARY
    assert "MIXTURE" in result.detail


# ---------------------------------------------------------------------------
# A SALT IS NOT A FORMULATION
# ---------------------------------------------------------------------------


def test_a_drawn_salt_is_one_substance_and_a_formulation_of_two_is_not():
    """The trap this feature could quietly create.

    `oxygen_balance` accepts a disconnected structure DELIBERATELY --
    ammonium nitrate is one of the source's own nine reference rows, and
    refusing salts would refuse the source's own fixture. So a drawn
    two-fragment structure is ALREADY one substance.

    A `Formulation` of two components is a different claim: a recipe, in
    stated proportions, whose proportions can be varied. Letting the two
    blur would give "mixture" two meanings -- exactly what the module's
    docstring refuses for the two oxygen-balance conventions.
    """
    from rdkit import Chem

    from openchem.chem.energetics import oxygen_balance

    # One substance: the salt, whose proportions are fixed by its formula.
    salt = oxygen_balance(Chem.MolFromSmiles(AMMONIUM_NITRATE))
    assert salt.applicable
    assert salt.nitrogen if hasattr(salt, "nitrogen") else True
    assert (salt.carbon, salt.hydrogen, salt.oxygen) == (0, 4, 3)

    # A formulation of the SAME salt with something else is a recipe, and
    # its composite is not the salt's formula.
    composite = composite_formula(ANFO)
    assert (composite.carbon, composite.oxygen) != (salt.carbon, salt.oxygen)

    # And a one-component "formulation" of the salt reproduces the salt,
    # which is what says the two models agree where they overlap.
    alone = composite_formula((_c(AMMONIUM_NITRATE, 1.0, -87.3),))
    assert alone.carbon == pytest.approx(salt.carbon)
    assert alone.hydrogen == pytest.approx(salt.hydrogen)
    assert alone.oxygen == pytest.approx(salt.oxygen)


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def test_a_formulation_stores_what_was_typed_not_what_was_derived():
    """`CrystalModel`'s rule: a later improvement to the compositing then
    reaches formulations already saved."""
    model = FormulationModel(display_name="ANFO", components=ANFO, loading_density=0.85)
    restored = FormulationModel.from_dict(model.to_dict())
    assert restored.components[0].mass_fraction == 0.945
    assert restored.components[1].mass_fraction == 0.055
    assert restored.loading_density == 0.85
    assert restored.uuid == model.uuid
    # The composite is NOT among the stored fields.
    assert "carbon" not in model.to_dict()
    assert "composite" not in model.to_dict()


def test_a_formulation_survives_a_project_round_trip():
    project = ProjectModel()
    model = FormulationModel(display_name="Comp B", components=COMP_B, loading_density=1.717)
    project.formulations.append(model)
    restored = ProjectModel.from_dict(project.to_dict())
    assert len(restored.formulations) == 1
    assert restored.find_formulation(model.uuid) is not None
    # ...and it is NOT in `molecules`, which every molecular calculator walks.
    assert restored.molecules == []


def test_the_stated_fractions_are_checked_on_the_document_too():
    good = FormulationModel(components=ANFO)
    bad = FormulationModel(components=(_c(RDX, 0.6, 14.7), _c(TNT, 0.35, -16.0)))
    assert good.fractions_are_consistent
    assert not bad.fractions_are_consistent
    assert not FormulationModel(components=()).fractions_are_consistent


def test_the_two_sides_check_the_same_tolerance_because_it_is_one_constant():
    """The document and the compositing both refuse fractions that do not
    sum, and a second literal of the bound would drift.

    The failure is silent and one-sided: loosen it here and not there, and
    a recipe the document calls consistent is refused by the arithmetic --
    or worse, the other way round, so a recipe with a missing binder is
    quietly composited. Asserting IDENTITY rather than equality is what
    makes re-declaring the literal fail, since a copied `1e-3` compares
    equal to the imported one.
    """
    from openchem.chem import energetics
    from openchem.domain import formulation

    assert (
        energetics.FORMULATION_FRACTION_TOLERANCE is formulation.FRACTION_TOLERANCE
    )


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def test_the_report_puts_the_composite_formula_on_its_face():
    """It is the one number that distinguishes a correct mole-weighting
    from the mass-as-mole error, which is invisible in the pressure."""
    report = build_formulation_report(
        FormulationModel(display_name="ANFO", components=ANFO, loading_density=0.85)
    )
    row = next(f for f in report.facts if f.label == "Composite formula")
    assert "C0.3194" in row.display_value or "C0.3195" in row.display_value
    assert any("MOLE-weighted" in e for e in row.evidence)


def test_a_charge_below_the_density_floor_says_so():
    """ANFO at 0.85 is below the paper's own tables, which stop at 1.0."""
    low = build_formulation_report(
        FormulationModel(display_name="ANFO", components=ANFO, loading_density=0.85)
    )
    high = build_formulation_report(
        FormulationModel(display_name="Comp B", components=COMP_B, loading_density=1.717)
    )
    assert any("Below 1 g/cm3" in l for l in low.limitations)
    assert not any("Below 1 g/cm3" in l for l in high.limitations)


def test_the_report_never_claims_the_density_was_derived():
    report = build_formulation_report(
        FormulationModel(display_name="Comp B", components=COMP_B, loading_density=1.717)
    )
    assert any("NOT a weighted average" in l for l in report.limitations)


def test_a_report_for_a_broken_recipe_computes_nothing():
    report = build_formulation_report(
        FormulationModel(components=(_c(RDX, 0.6, 14.7), _c(TNT, 0.35, -16.0)))
    )
    labels = {f.label for f in report.facts}
    assert "Detonation pressure (C-J)" not in labels
    assert any("Nothing was computed" in l for l in report.limitations)
