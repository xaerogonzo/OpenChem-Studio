"""The isotope envelope, against oracles this module did not produce.

**EVERY RATIO HERE IS DERIVED INDEPENDENTLY OF THE CONVOLUTION.** A
two-isotope element's pattern is the binomial expansion of its own
abundances and a three-atom one is the trinomial; both are computed in the
test from the shipped abundance table rather than from `isotope_envelope`,
so a fault in the convolution cannot also move the thing it is being
checked against. Remembering "Br2 is 1:2:1" and asserting that would be a
weaker test AND a citation nobody checked.

The one cross-tool check is the molecule in MarvinSketch's own output --
the same kind of comparison `chem/elemental_analysis.py`'s docstring
already records against that tool, and for the same reason.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import Descriptors

from openchem.chem.mass_spectrum import (
    DEFAULT_PRUNE_THRESHOLD,
    ELECTRON_MASS_DA,
    _convolve,
    base_peak_shift,
    element_counts,
    isotope_envelope,
    isotopes_of,
)
from openchem.domain.mass_spectrum import (
    DEFAULT_ION,
    AtomDelta,
    CompositionDelta,
    IonSpecies,
    SpectrumBasis,
    composition_delta,
    ion_by_label,
)


def _counts(smiles: str) -> dict[str, int]:
    return element_counts(Chem.AddHs(Chem.MolFromSmiles(smiles)))


def _relative(spectrum) -> dict[int, float]:
    return {peak.nominal_shift: peak.intensity for peak in spectrum.peaks}


def _fractions(symbol: str) -> list[float]:
    """One element's isotope fractions, lightest first, from the shipped
    table -- the independent half of every ratio oracle below."""
    return [fraction for _mass_number, _mass, fraction in isotopes_of(symbol)]


# --- the halogen patterns, against their own binomial expansions ---------


#: Both halogens' two stable isotopes are TWO mass numbers apart --
#: 79/81 and 35/37 -- so an n-atom pattern lands on shifts 0, 2, 4 ...
#: rather than on consecutive integers. This is visible in the
#: screenshot that motivated the feature (278, 280, 282) and it is why
#: `nominal_shift` is a mass-number shift and not a peak counter.
_HALOGEN_STEP = 2


@pytest.mark.parametrize("symbol", ["Br", "Cl"])
def test_two_atoms_of_a_two_isotope_element_follow_the_binomial_expansion(symbol):
    """(a + b)^2 = a^2 : 2ab : b^2, computed from the abundances rather
    than remembered as "1:2:1" and "9:6:1"."""
    a, b = _fractions(symbol)
    expected = [a * a, 2 * a * b, b * b]
    peak = max(expected)
    got = _relative(isotope_envelope({symbol: 2}, DEFAULT_ION))
    for index, value in enumerate(expected):
        assert got[index * _HALOGEN_STEP] == pytest.approx(value / peak, rel=1e-9)


def test_three_chlorines_follow_the_trinomial_expansion():
    """The three-atom case, which a two-atom fixture cannot see: it is the
    first that exercises convolving an already-convolved envelope."""
    a, b = _fractions("Cl")
    expected = [a**3, 3 * a * a * b, 3 * a * b * b, b**3]
    peak = max(expected)
    got = _relative(isotope_envelope({"Cl": 3}, DEFAULT_ION))
    for index, value in enumerate(expected):
        assert got[index * _HALOGEN_STEP] == pytest.approx(value / peak, rel=1e-9)


def test_the_carbon_satellite_is_computed_from_the_table_not_from_a_rule_of_thumb():
    """"M+1 is about 1.1% per carbon" is a SANITY CHECK, not the oracle.
    The oracle is n * (f13 / f12), which for a fixed n is exact."""
    n = 10
    f12, f13 = _fractions("C")
    got = _relative(isotope_envelope({"C": n}, DEFAULT_ION))
    assert got[1] == pytest.approx(n * f13 / f12, rel=1e-9)
    # And the rule of thumb agrees, which is what makes it a useful
    # eyeball check rather than a competing claim.
    assert got[1] == pytest.approx(0.011 * n, rel=0.05)


# --- the neutral / ion distinction --------------------------------------


def test_the_neutral_exact_mass_matches_a_value_already_trusted():
    """Ties the engine to `Descriptors.ExactMolWt`, which this application
    already reports from Elemental Analysis."""
    mol = Chem.AddHs(Chem.MolFromSmiles("OC(=O)c1cccc(Br)c1Br"))
    spectrum = isotope_envelope(element_counts(mol), DEFAULT_ION)
    assert spectrum.neutral_exact_mass == pytest.approx(Descriptors.ExactMolWt(mol), abs=1e-6)


def test_the_ion_m_over_z_is_not_the_neutral_exact_mass():
    """**THE DISTINCTION, IN A TEST RATHER THAN IN PROSE.** They differ by
    the electron even for the molecular ion, and by an adduct for
    everything else."""
    counts = _counts("CCO")
    spectrum = isotope_envelope(counts, ion_by_label("[M]+."))
    assert spectrum.monoisotopic_mz == pytest.approx(
        spectrum.neutral_exact_mass - ELECTRON_MASS_DA, abs=1e-9
    )
    assert spectrum.monoisotopic_mz != spectrum.neutral_exact_mass


def _hydrogen_mass() -> float:
    return Chem.GetPeriodicTable().GetMassForIsotope(1, 1)


def test_protonation_adds_one_proton_and_subtracts_one_electron():
    counts = _counts("CCO")
    neutral = isotope_envelope(counts, DEFAULT_ION).neutral_exact_mass
    spectrum = isotope_envelope(counts, ion_by_label("[M+H]+"))
    assert spectrum.monoisotopic_mz == pytest.approx(
        neutral + _hydrogen_mass() - ELECTRON_MASS_DA, abs=1e-9
    )


def test_deprotonation_removes_a_proton_and_the_electron_goes_the_other_way():
    counts = _counts("CCO")
    neutral = isotope_envelope(counts, DEFAULT_ION).neutral_exact_mass
    spectrum = isotope_envelope(counts, ion_by_label("[M-H]-"))
    assert spectrum.monoisotopic_mz == pytest.approx(
        neutral - _hydrogen_mass() + ELECTRON_MASS_DA, abs=1e-9
    )


def test_the_electron_is_applied_once_per_charge_and_not_twice():
    """Applying it twice, or forgetting it, are both a few tenths of a
    millidalton -- invisible on a plot and exactly where a high-resolution
    reader looks."""
    counts = _counts("CCO")
    neutral = isotope_envelope(counts, DEFAULT_ION).neutral_exact_mass
    spectrum = isotope_envelope(counts, ion_by_label("[M+2H]2+"))
    assert spectrum.monoisotopic_mz == pytest.approx(
        (neutral + 2 * _hydrogen_mass() - 2 * ELECTRON_MASS_DA) / 2, abs=1e-9
    )


# --- the multiply-charged case, which is structural ----------------------


def test_an_isotope_shift_moves_a_doubly_charged_ion_by_half_an_m_over_z():
    """**A STRUCTURAL TEST OF THE CHARGE MODEL, NOT ANOTHER CHEMISTRY
    FIXTURE.** `nominal_shift` is an integer in isotope space and the m/z
    coordinate is not: a +1 shift moves a 1+ ion by 1.0 and a 2+ ion by
    0.5. Collapsing the two works perfectly at charge 1 and silently draws
    every ESI spectrum at the wrong spacing."""
    counts = _counts("CCO")
    singly = isotope_envelope(counts, ion_by_label("[M+H]+"), unit_resolution=True)
    doubly = isotope_envelope(counts, ion_by_label("[M+2H]2+"), unit_resolution=True)

    def spacing(spectrum):
        by_shift = {p.nominal_shift: p.mz for p in spectrum.peaks}
        return by_shift[1] - by_shift[0]

    assert spacing(singly) == pytest.approx(1.0)
    assert spacing(doubly) == pytest.approx(0.5)


def test_nominal_binning_is_not_a_rounded_exact_mass():
    """Mass defect is composition-dependent, so rounding the final m/z is
    wrong in a way that depends on the molecule -- and a 2+ ion's peaks are
    half a unit apart, where rounding cannot put them at all."""
    doubly = isotope_envelope(_counts("CCO"), ion_by_label("[M+2H]2+"), unit_resolution=True)
    halves = [p.mz for p in doubly.peaks if p.nominal_shift % 2 == 1]
    assert halves, "asserts its own setup: there IS an odd shift to look at"
    assert all(abs(mz - round(mz)) == pytest.approx(0.5) for mz in halves)


# --- the adduct isotope rule --------------------------------------------


def test_protonation_introduces_no_hydrogen_envelope():
    """1H is named by definition, so `[M+H]+` and `[M]+.` differ by a mass
    and not by a pattern. Deuterium is 0.0115% of natural hydrogen -- small
    enough that a natural-abundance proton would look almost right, which
    is exactly why this is asserted rather than eyeballed."""
    counts = _counts("CCO")
    plain = _relative(isotope_envelope(counts, ion_by_label("[M]+.")))
    protonated = _relative(isotope_envelope(counts, ion_by_label("[M+H]+")))
    assert set(plain) == set(protonated)
    for shift, value in plain.items():
        assert protonated[shift] == pytest.approx(value, rel=1e-9)


def test_a_chloride_adduct_brings_its_own_three_to_one_envelope():
    """The case a scalar mass delta cannot express, which is why an ion is
    a composition."""
    a, b = _fractions("Cl")
    counts = _counts("CCO")
    plain = _relative(isotope_envelope(counts, ion_by_label("[M]+.")))
    chlorided = _relative(isotope_envelope(counts, ion_by_label("[M+Cl]-")))
    # Ethanol's own M+2 is 18O at about 0.2%, so the claim is that the
    # adduct DOMINATES it rather than that the molecule has none.
    assert plain[2] < 0.005
    assert chlorided[2] == pytest.approx(b / a, rel=0.02)
    assert chlorided[2] > 100 * plain[2]


def test_a_potassium_adduct_carries_its_own_satellite_too():
    """**NOT A CHLORIDE SPECIAL CASE.** Potassium is 6.7% 41K, so a
    cationic adduct shows an M+2 from the adduct alone -- and sodium,
    being monoisotopic, could never have shown that the rule is general."""
    fractions = _fractions("K")
    counts = _counts("CCO")
    potassiated = _relative(isotope_envelope(counts, ion_by_label("[M+K]+")))
    assert potassiated[2] == pytest.approx(fractions[2] / fractions[0], rel=0.05)
    # Sodium is monoisotopic, so the sodiated ion's M+2 is the molecule's
    # own 18O and nothing else -- an order of magnitude below potassium's.
    sodiated = _relative(isotope_envelope(counts, ion_by_label("[M+Na]+")))
    assert sodiated[2] < 0.005
    assert potassiated[2] > 10 * sodiated[2]


# --- pruning, and what it may not touch ---------------------------------


def test_pruning_leaves_every_summary_value_where_it_was():
    """**THE ONE RULE ABOUT WHAT PRUNING TOUCHES**: the reported peak list
    only. If a threshold could move a reported mass, the number on screen
    would depend on a display setting."""
    counts = _counts("OC(=O)c1cccc(Br)c1Br")
    unpruned = isotope_envelope(counts, DEFAULT_ION, prune_threshold=0.0)
    pruned = isotope_envelope(counts, DEFAULT_ION, prune_threshold=0.05)
    assert len(pruned.peaks) < len(unpruned.peaks), "asserts its own setup"
    for attribute in ("neutral_exact_mass", "monoisotopic_mz", "average_mz", "base_peak_mz"):
        assert getattr(pruned, attribute) == pytest.approx(
            getattr(unpruned, attribute), abs=1e-12
        )


def test_the_threshold_it_was_computed_with_travels_with_the_spectrum():
    """0.0 means no ALGORITHMIC pruning -- which is still not "exact", and
    the field is what lets a reader tell the two apart."""
    spectrum = isotope_envelope(_counts("CCO"), DEFAULT_ION, prune_threshold=0.0)
    assert spectrum.prune_threshold == 0.0
    assert isotope_envelope(_counts("CCO"), DEFAULT_ION).prune_threshold == (
        DEFAULT_PRUNE_THRESHOLD
    )


def test_every_reported_peak_survives_the_threshold_it_declares():
    spectrum = isotope_envelope(_counts("OC(=O)c1cccc(Br)c1Br"), DEFAULT_ION, prune_threshold=0.05)
    assert all(peak.intensity >= 0.05 for peak in spectrum.peaks)


# --- the reported invariants --------------------------------------------


def test_the_tallest_peak_is_exactly_one_and_the_list_is_never_empty():
    for smiles in ("CCO", "OC(=O)c1cccc(Br)c1Br", "C"):
        spectrum = isotope_envelope(_counts(smiles), DEFAULT_ION)
        assert spectrum.peaks
        assert max(peak.intensity for peak in spectrum.peaks) == pytest.approx(1.0)


def test_the_summary_masses_are_exact_even_when_the_peaks_are_binned():
    """**TWO REPRESENTATIONS, AND THIS IS WHERE THEY MEET.** The summary
    values come off the full distribution in EXACT terms; a
    unit-resolution peak's `mz` is the nominal coordinate of its bin. So
    `base_peak_mz` and `peaks[i].mz` are different quantities and must
    not be compared -- which cost this test one revision to notice, and
    is now written into `MassSpectrum` rather than left to be rediscovered."""
    binned = isotope_envelope({"Br": 1}, DEFAULT_ION, unit_resolution=True)
    exact = isotope_envelope({"Br": 1}, DEFAULT_ION, unit_resolution=False)
    assert binned.base_peak_mz == pytest.approx(exact.base_peak_mz, abs=1e-12)
    assert [p.mz for p in binned.peaks] == [79.0, 81.0]
    assert binned.base_peak_mz == pytest.approx(78.9178, abs=1e-3)
    assert exact.peaks[0].mz == pytest.approx(binned.base_peak_mz, abs=1e-12)


def test_the_base_peak_is_the_tallest_and_ties_go_to_the_lowest_mass():
    """Read in EXACT terms, so the summary value and the peak it names
    are the same quantity. Two branches of identical probability must
    resolve to the LOWER mass: a scientific value object may not depend
    on whichever the iteration happened to reach first."""
    spectrum = isotope_envelope({"Br": 1}, DEFAULT_ION, unit_resolution=False)
    tallest = max(peak.intensity for peak in spectrum.peaks)
    candidates = [p.mz for p in spectrum.peaks if p.intensity == tallest]
    assert spectrum.base_peak_mz == pytest.approx(min(candidates), abs=1e-12)


def test_a_calculated_spectrum_declares_that_it_is_calculated():
    """Never inferred by a consumer from the numbers -- the rule
    `ReportResult.spatial` already follows."""
    assert isotope_envelope(_counts("CCO"), DEFAULT_ION).basis is SpectrumBasis.CALCULATED


def test_the_ion_travels_with_the_spectrum():
    ion = ion_by_label("[M+Na]+")
    assert isotope_envelope(_counts("CCO"), ion).ion is ion


def test_the_average_mass_is_probability_weighted_over_the_whole_envelope():
    """Close to RDKit's `MolWt` and deliberately not asserted equal to it:
    that is computed from STANDARD ATOMIC WEIGHTS and this from the
    abundance table, which are different sources that IUPAC revises
    separately. `chem/elemental_analysis.py` records the same difference
    against Marvin."""
    mol = Chem.AddHs(Chem.MolFromSmiles("OC(=O)c1cccc(Br)c1Br"))
    spectrum = isotope_envelope(element_counts(mol), DEFAULT_ION)
    assert spectrum.average_mz == pytest.approx(Descriptors.MolWt(mol), abs=0.05)
    assert spectrum.average_mz > spectrum.monoisotopic_mz


# --- the cross-tool check ------------------------------------------------


def test_the_dibromobenzoic_acid_envelope_matches_marvins_own_output():
    """MarvinSketch's elemental analysis of 2,3-dibromobenzoic acid, read
    off its own window: 278 0.51, 279 0.04, 280 1.00, 281 0.08, 282 0.49,
    283 0.04, with an exact molecular weight of 277.857805.

    A CROSS-TOOL CHECK rather than the primary oracle -- the ratios above
    are pinned against binomial expansions of the shipped abundances, and
    this says a second implementation agrees. `elemental_analysis.py` was
    validated against the same tool the same way.
    """
    counts = _counts("OC(=O)c1cccc(Br)c1Br")
    spectrum = isotope_envelope(counts, DEFAULT_ION, unit_resolution=True)
    got = {int(round(peak.mz)): peak.intensity for peak in spectrum.peaks if peak.intensity > 0.005}
    assert got.keys() == {278, 279, 280, 281, 282, 283}
    assert got[278] == pytest.approx(0.51, abs=0.005)
    assert got[279] == pytest.approx(0.04, abs=0.005)
    assert got[280] == pytest.approx(1.00, abs=0.005)
    assert got[281] == pytest.approx(0.08, abs=0.005)
    assert got[282] == pytest.approx(0.49, abs=0.005)
    assert got[283] == pytest.approx(0.04, abs=0.005)
    assert spectrum.neutral_exact_mass == pytest.approx(277.857805, abs=1e-5)


# --- what it refuses -----------------------------------------------------


def test_an_element_with_no_natural_isotope_is_refused_rather_than_guessed():
    """Technetium has none. Inventing a distribution for it would produce a
    perfectly plausible spectrum of a molecule nobody can weigh."""
    with pytest.raises(ValueError, match="naturally occurring"):
        isotope_envelope({"Tc": 1}, DEFAULT_ION)


def test_an_ion_naming_an_isotope_that_does_not_exist_is_refused():
    """**RDKit KNOWS MORE NUCLIDES THAN OCCUR NATURALLY**, which is
    worth stating: it returns 5.03531 for hydrogen-5, an unbound
    nuclide. So this refuses a mass number its table has nothing for at
    all, rather than refusing "not one of the stable ones" -- an ion
    declaring a real but exotic nuclide is the caller's business, and
    the arithmetic is the same either way."""
    ion = IonSpecies(
        label="[M+999C]+",
        composition=composition_delta([AtomDelta("C", 1, 999)]),
        charge=1,
    )
    with pytest.raises(ValueError, match="no isotope"):
        isotope_envelope(_counts("CCO"), ion)


def test_an_ion_must_carry_a_charge():
    with pytest.raises(ValueError, match="charge"):
        IonSpecies(label="[M]", composition=CompositionDelta(), charge=0)


def test_every_supported_ion_computes_a_real_spectrum():
    """A vocabulary entry nothing can compute is a menu item that fails."""
    from openchem.domain.mass_spectrum import SUPPORTED_IONS

    counts = _counts("CCO")
    for ion in SUPPORTED_IONS:
        spectrum = isotope_envelope(counts, ion)
        assert spectrum.peaks
        assert math.isfinite(spectrum.monoisotopic_mz)
        assert spectrum.monoisotopic_mz > 0


# --- the ion's identity, and the rules that keep it canonical -----------


def test_two_ions_with_one_composition_and_charge_are_the_same_ion():
    """**IDENTITY IS `composition + charge`; THE LABEL IS DISPLAY TEXT.**
    On a frozen dataclass every field joins `__eq__` by default, so
    without `compare=False` two spellings of one ion would be two
    different ions -- and, worse, one spelling could stand in for two
    different compositions with nothing noticing."""
    proton = composition_delta([AtomDelta("H", 1, 1)])
    assert IonSpecies(label="[M+H]+", composition=proton, charge=1) == IonSpecies(
        label="protonated molecule", composition=proton, charge=1
    )


def test_one_label_over_two_compositions_is_two_ions():
    """The half that matters more: a display string must never be able to
    make two different ions compare equal."""
    assert IonSpecies(
        label="[M+X]+", composition=composition_delta([AtomDelta("H", 1, 1)]), charge=1
    ) != IonSpecies(
        label="[M+X]+", composition=composition_delta([AtomDelta("Na", 1)]), charge=1
    )


def test_charge_is_part_of_the_identity():
    proton = composition_delta([AtomDelta("H", 2, 1)])
    assert IonSpecies(label="a", composition=proton, charge=1) != IonSpecies(
        label="a", composition=proton, charge=2
    )


def test_an_ion_is_hashable_so_it_can_key_a_cache():
    proton = composition_delta([AtomDelta("H", 1, 1)])
    ions = {
        IonSpecies(label="[M+H]+", composition=proton, charge=1),
        IonSpecies(label="a different name", composition=proton, charge=1),
    }
    assert len(ions) == 1


def test_the_composition_is_canonically_ordered_however_it_was_written():
    """Without this, `(H, Na)` and `(Na, H)` are two identities for one
    ion -- which matters precisely because `IonSpecies` is compared and
    hashed."""
    one = composition_delta([AtomDelta("Na", 1), AtomDelta("H", 1, 1)])
    other = composition_delta([AtomDelta("H", 1, 1), AtomDelta("Na", 1)])
    assert one == other
    assert [change.symbol for change in one.changes] == ["H", "Na"]


def test_the_same_element_at_two_isotopes_is_not_a_duplicate():
    """The key is `(symbol, isotope)`, not the symbol: a deliberately
    labelled ion adding one 1H and one 2H is a real thing to write, and
    refusing it would be the canonical form overreaching."""
    mixed = composition_delta([AtomDelta("H", 1, 1), AtomDelta("H", 1, 2)])
    assert len(mixed.changes) == 2


def test_an_atom_delta_of_zero_is_refused():
    """An entry that changes nothing is either a mistake or noise in an
    identity that gets hashed."""
    with pytest.raises(ValueError, match="zero"):
        composition_delta([AtomDelta("H", 0, 1)])


def test_the_same_element_and_isotope_twice_is_refused_rather_than_merged():
    """Merging was the alternative and is worse: `(H +1, H -1)` would
    silently become "no change", which is a plausible ion nobody meant to
    write."""
    with pytest.raises(ValueError, match="twice"):
        composition_delta([AtomDelta("H", 1, 1), AtomDelta("H", -1, 1)])


def test_a_mass_number_must_be_positive():
    with pytest.raises(ValueError, match="mass number"):
        composition_delta([AtomDelta("H", 1, 0)])


def test_a_fractional_atom_count_is_refused():
    with pytest.raises(ValueError, match="whole number"):
        composition_delta([AtomDelta("H", 1.5, 1)])


# --- the base-peak tie, where it can be reached -------------------------


def test_a_base_peak_tie_resolves_to_the_lowest_mass():
    """**CONSTRUCTED, BECAUSE NO REAL INPUT CAN REACH IT.** No two elements
    give branches of exactly equal probability, so through the engine
    `min` and `max` are indistinguishable -- measured: mutating the rule
    left all 28 engine tests green. An unreachable branch is a question
    about where to assert, and the answer is the extracted function."""
    tied = {0: (100.0, 0.5), 2: (102.0, 0.5), 4: (104.0, 0.25)}
    assert base_peak_shift(tied) == 0


def test_the_base_peak_is_the_tallest_when_there_is_no_tie():
    assert base_peak_shift({0: (100.0, 0.1), 2: (102.0, 0.9)}) == 2


# --- the fold does not explode ------------------------------------------
#
# **NOT ONE OF THE 65 TESTS ABOVE COULD SEE THIS**, and the reason is the
# recorded one: a fixture is degenerate or not with respect to a specific
# defect. Every oracle here is a two- or three-atom expansion or a
# 15-atom acid, and the first implementation kept every isotopologue as a
# separate branch -- so the entry count was `k^n` in the ATOM count and
# only a drug-sized molecule could show it. Aspirin's 21 atoms built 10.6
# million branches in 4 seconds; ibuprofen's 33 reach 19 billion and
# never finish. All of them were then averaged away by the collapse.
#
# It was found by the full suite, where two `test_batch_service.py` tests
# ran real calculators over aspirin/caffeine/ibuprofen and blew their
# 120-second `waitForDone`. That file now runs in 4.5 seconds.


def _drug_sized_counts() -> dict[str, int]:
    """Ibuprofen, C13H18O2 -- 33 atoms with hydrogens.

    The composition that could not be computed at all before the fold
    merged as it went, so a guard built on anything smaller is asserting
    against a case the defect could survive.
    """
    counts = _counts("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    assert sum(counts.values()) == 33, "the fixture must stay drug-sized"
    return counts


def test_the_fold_carries_one_merged_bin_per_shift():
    """**THE GUARD FOR THE EXPONENTIAL FOLD.**

    A wall-clock bound is what this project forbids -- a timing assertion
    is a claim about the machine, and this file already records two
    guards that had to be rewritten for exactly that. So the property
    asserted has to be a STRUCTURAL one that the exponential form cannot
    satisfy however fast the machine is.
    """
    # **THE CHEAP COMPOSITION FIRST, AND THE ORDER IS LOAD-BEARING.**
    # Reverting the fold to list-append does not make the drug-sized case
    # FAIL, it makes it never return -- 19 billion branches is a hang or
    # an out-of-memory kill, and neither is a test result anybody can
    # read. Water folds to 12 branches under the exponential form, so the
    # shape assertion below lands in microseconds either way and the
    # mutation is caught before the expensive half runs.
    accumulated = {0: (0.0, 1.0)}
    for symbol, count in sorted(_counts("O").items()):
        accumulated = _convolve(accumulated, isotopes_of(symbol), count, 1)

    # **THE VALUES, NEVER `len(accumulated)`.** The exponential form keyed
    # on nominal shift as well, so its dict was exactly this long -- what
    # reached millions was what each key POINTED AT. A length assertion
    # would pass against the defect it is written for.
    #
    # Unpacking is the discriminator and needs no `isinstance` on a
    # container: a bin holding a list of branches cannot become two
    # floats, whatever its length. This is the half that catches a
    # revert to list-append.
    for shift, carried in accumulated.items():
        mass, probability = carried
        assert isinstance(mass, float), f"shift {shift} carries {carried!r}"
        assert isinstance(probability, float), f"shift {shift} carries {carried!r}"

    # **AND ONLY NOW THE DRUG-SIZED ONE**, which is the statement the
    # shape assertion cannot make: this composition can be folded AT ALL.
    # Under the exponential form it cannot, at any speed.
    drug = {0: (0.0, 1.0)}
    for symbol, count in sorted(_drug_sized_counts().items()):
        drug = _convolve(drug, isotopes_of(symbol), count, 1)

    # The answer really is small, which is the "not exponential"
    # statement rather than the discriminating one -- C13H18O2 can reach
    # 13*(13-12) + 18*(2-1) + 2*(18-16) = 35 shifts above the lightest
    # branch, so 36 bins is every one of them. Derived rather than
    # measured, so it cannot drift into a record of whatever the fold
    # happened to produce.
    assert len(drug) <= 36
    assert drug[min(drug)][1] > 0.0, "the lightest branch carries the monoisotopic peak"


def test_the_merged_fold_still_reproduces_the_marvin_envelope():
    """The CONTROL, and it is why the guard above is safe to tighten.

    Merging during the fold is exact rather than approximate, so the
    reported envelope must be byte-identical to the one this file's own
    Marvin fixture pins. If a future speed-up ever starts pruning inside
    the fold, this is what says so.
    """
    spectrum = isotope_envelope(_counts("OC(=O)c1cccc(Br)c1Br"), DEFAULT_ION)
    assert spectrum.neutral_exact_mass == pytest.approx(277.857804, abs=1e-6)
    intensities = [round(peak.intensity, 2) for peak in spectrum.peaks[:6]]
    assert intensities == [0.51, 0.04, 1.00, 0.08, 0.49, 0.04]


def test_a_zero_probability_branch_is_dropped_rather_than_dividing_by_zero():
    """**CONSTRUCTED, BECAUSE NO REAL COMPOSITION CAN REACH IT**, which is
    the same answer this file already gives for the base-peak tie.

    `isotopes_of` filters to `abundance > 0`, so every weight the engine
    can produce is positive and a mutation deleting the guard leaves all
    67 tests green -- measured. It is carried over verbatim from the
    collapse this fold replaced, and it is still right: a branch of zero
    probability is not a branch, and the alternative is a
    ZeroDivisionError on the mean.
    """
    weightless = ((1, 1.007825, 1.0), (2, 2.014102, 0.0))
    folded = _convolve({0: (0.0, 1.0)}, weightless, 1, 1)
    assert list(folded) == [0], "the zero-abundance branch must not survive"
    assert folded[0] == (pytest.approx(1.007825), pytest.approx(1.0))


# --- what "exact" resolution actually reports ---------------------------


def test_an_exact_peak_is_the_bins_MEAN_and_never_one_isotopologue():
    """**THE CONTRACT SAID "the isotopologue's own m/z" AND WAS WRONG.**

    Isotopologues sharing a mass-number shift are merged, so M+1 of a
    CHNO molecule is 13C, 17O and 2H at three different exact masses and
    ONE peak is reported for all of them. The oracle here is those three
    deltas taken straight from the shipped abundance table, computed
    without the convolution -- the reported value has to lie strictly
    between the smallest and the largest and equal none of them.

    Nothing else in this file could see it: every other assertion is at
    unit resolution, where the bin's mean is rounded away.
    """
    heavy = {}
    for symbol, light in (("C", 12), ("O", 16), ("H", 1)):
        masses = {n: m for n, m, _f in isotopes_of(symbol)}
        heavy[symbol] = masses[light + 1] - masses[light]

    deltas = sorted(heavy.values())
    assert len(set(deltas)) == 3, (
        "the fixture needs three DIFFERENT +1 deltas or the bin has "
        f"nothing to average: {heavy}"
    )

    counts = _counts("OC(=O)c1cccc(Br)c1Br")
    exact = isotope_envelope(counts, DEFAULT_ION, unit_resolution=False)
    monoisotopic = exact.peaks[0].mz
    shift_one = next(peak for peak in exact.peaks if peak.nominal_shift == 1)
    observed = shift_one.mz - monoisotopic

    assert deltas[0] < observed < deltas[-1], (
        f"M+1 reported {observed}, outside the {deltas[0]}..{deltas[-1]} "
        "span its own contributors define"
    )
    for symbol, delta in heavy.items():
        assert observed != pytest.approx(delta, abs=1e-9), (
            f"M+1 landed exactly on the {symbol} isotopologue, so the bin "
            "is not being averaged"
        )
