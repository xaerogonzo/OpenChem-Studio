"""The periodic charge calculator (EQeq), against its pre-registration.

`benchmarks/charges/periodic/calculator_preregistration.md` is the contract, and TRIAGE check 2.9 is
the oracle: it reproduced all 3,452 atoms of Wilmer 2012's twelve MOFs. Gate 1 of the
pre-registration is that the SRC path reproduces them too, so the corpus test below runs the same
comparison through `Crystal` and `compute_periodic_charges`. Those structures are ACS accompanying
files and are not in the repository, so that test skips when they are absent; the shipped regression
is the SI's own NaCl, which carries no published charges and is pinned as a regression, not an
oracle.
"""

from __future__ import annotations

import pathlib
import random

import numpy as np
import pytest

from openchem.chem import periodic_charges as pc
from openchem.chem.cif import read_cif
from openchem.domain.crystal import Crystal, Lattice, Site

SI = pathlib.Path(r"D:\Xaero Stuff\Documents\Sci Downloads\wilmer2012_si")
STRUCTURES = SI / "jz3008485_si_002" / "CrystalStructuresWithCharges"
NACL = SI / "jz301439a_si_001" / "SubmittedCode" / "NaCl.cif"
needs_si = pytest.mark.skipif(not STRUCTURES.exists(), reason="the Wilmer 2012 structures are not on this machine")
needs_nacl = pytest.mark.skipif(not NACL.exists(), reason="the Wilmer 2012 NaCl.cif is not on this machine")


def crystal_from_listing(path: pathlib.Path) -> tuple[Crystal, np.ndarray]:
    """One RASPA listing as a `Crystal`, plus its published charges.

    The lengths print under a "Fundcell_Info:" label as lengths, angles, origin; the coordinates are
    Cartesian, so they are converted to fractional for `Site`.
    """
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    count = int(lines[2])
    start = next(index for index, line in enumerate(lines) if "Fundcell_Info" in line)
    lengths, angles, _origin = ([float(value) for value in lines[start + offset].split()] for offset in (1, 2, 3))
    lattice = Lattice(*lengths, *angles)
    vectors = np.array([lattice.to_cartesian(*basis) for basis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))])
    inverse = np.linalg.inv(vectors.T)

    sites, charges = [], []
    for index, line in enumerate(lines[3:3 + count]):
        fields = line.split()
        cartesian = np.array([float(fields[1]), float(fields[2]), float(fields[3])])
        fractional = tuple(float(value) for value in (inverse @ cartesian))
        sites.append(Site(label=f"{fields[4]}{index + 1}", element=fields[4].replace("Mof_", ""), position=fractional))
        charges.append(float(fields[5]))
    return Crystal(lattice=lattice, sites=tuple(sites), name=path.stem), np.array(charges)


# --- the shipped regression -----------------------------------------------------------------------


@needs_nacl
def test_nacl_is_symmetric_neutral_and_pinned():
    """**A REGRESSION PIN AND TWO HAND CHECKS, NOT AN ORACLE**: the SI ships this structure but no
    charges for it. What can be checked without one is that every sodium takes one value and every
    chloride its negative, and that the cell is neutral."""
    result = pc.compute_periodic_charges(read_cif(NACL.read_text(encoding="utf-8")))
    assert not result.refusal
    sodium = {round(q, 6) for q, element in zip(result.charges, result.elements) if element == "Na"}
    chloride = {round(q, 6) for q, element in zip(result.charges, result.elements) if element == "Cl"}
    assert len(sodium) == len(chloride) == 1
    assert sodium.pop() == pytest.approx(-chloride.pop())
    assert abs(sum(result.charges)) < 1e-9
    assert result.charges[result.elements.index("Na")] == pytest.approx(1.793, abs=5e-4)


# --- gate 1: the source's own numbers, through the src path ----------------------------------------


#: The ten that reproduce, and how many of their sites the expansion moves into the cell. Co-MOF74 is
#: written entirely outside its cell and still reproduces, because the shift is UNIFORM; see
#: `test_wrapping_a_whole_structure_uniformly_changes_nothing` and amendment 4-A1.
IN_CELL = {"Co-MOF74": 162, "HKUST-1": 0, "IRMOF-1": 0, "IRMOF-3": 0, "MIL-47": 0, "Mg-MOF74": 0,
           "Pd-2-pymo": 0, "UMCM-150": 0, "UMCM-150N2": 0, "ZIF-8": 0}
#: The two whose atoms move by DIFFERENT lattice vectors, and the size of the difference that makes.
OUT_OF_CELL = {"Ni-MOF74": (106, 0.159), "Zn-MOF74": (108, 0.008)}


@needs_si
@pytest.mark.parametrize("name", sorted(IN_CELL))
def test_gate_the_src_path_reproduces_the_published_charges(name):
    """Pre-registration gate 1, as amendment 4-A1 narrows it: **every atom, at the printed 3 dp**,
    exactly as check 2.9 established through the benchmark path."""
    crystal, published = crystal_from_listing(STRUCTURES / f"{name}_EQeq.mol")
    result = pc.compute_periodic_charges(crystal)
    assert not result.refusal, result.message
    assert np.array_equal(np.array(result.charges), published)
    assert result.wrapped_sites == IN_CELL[name]


@needs_si
@pytest.mark.parametrize("name", sorted(OUT_OF_CELL))
def test_the_two_structures_written_outside_their_cell_differ_by_the_measured_amount(name):
    """**NOT A DEFECT IN THIS PATH, AND THAT WAS MEASURED** (amendment 4-A1): handed the wrapped
    coordinates, check 2.9's benchmark solver returns byte-identical charges to these. What the
    published numbers depend on is representatives a CIF cannot carry."""
    crystal, published = crystal_from_listing(STRUCTURES / f"{name}_EQeq.mol")
    result = pc.compute_periodic_charges(crystal)
    moved, difference = OUT_OF_CELL[name]
    assert result.wrapped_sites == moved
    assert float(np.max(np.abs(np.array(result.charges) - published))) == pytest.approx(difference, abs=1e-3)


@needs_si
@pytest.mark.parametrize("name", sorted(OUT_OF_CELL) + ["MIL-47", "HKUST-1"])
def test_the_two_paths_agree_atom_for_atom_on_the_same_atoms(name):
    """**THE EVIDENCE BEHIND AMENDMENT 4-A1**, and the strongest form gate 1 admits: check 2.9's
    benchmark solver, handed the coordinates the src path actually used, returns byte-identical
    charges -- on the two that disagree with the published numbers as much as on two that do. What
    differs for those two is the input, and this is what says so."""
    import importlib.util
    import sys

    root = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "eqeq_check_for_src", root / "benchmarks" / "charges" / "models" / "eqeq_check.py")
    benchmark = importlib.util.module_from_spec(spec)
    sys.modules["eqeq_check_for_src"] = benchmark
    spec.loader.exec_module(benchmark)

    crystal, _published = crystal_from_listing(STRUCTURES / f"{name}_EQeq.mol")
    result = pc.compute_periodic_charges(crystal)

    structure = benchmark.read_structure(STRUCTURES / f"{name}_EQeq.mol")
    structure["coordinates"] = np.array([crystal.lattice.to_cartesian(*atom.position)
                                         for atom in crystal.expand()])
    theirs = benchmark.round_charges(benchmark.solve(structure, benchmark.parameter_table(), 2, 1.0))
    assert np.array_equal(np.array(result.charges), theirs)


@needs_si
def test_wrapping_a_whole_structure_uniformly_changes_nothing():
    """Co-MOF74 is the corpus's own control: all 162 of its atoms are written outside the cell, so
    all 162 move -- uniformly -- and every charge still reproduces. A truncated sum is invariant to
    translating the whole structure and not to translating one atom of it."""
    crystal, published = crystal_from_listing(STRUCTURES / "Co-MOF74_EQeq.mol")
    lines = [line for line in (STRUCTURES / "Co-MOF74_EQeq.mol").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    deposited = np.array([[float(f) for f in line.split()[1:4]] for line in lines[3:3 + int(lines[2])]])
    expanded = np.array([crystal.lattice.to_cartesian(*atom.position) for atom in crystal.expand()])
    shifts = expanded - deposited
    assert float(np.max(np.linalg.norm(shifts, axis=1))) > 1.0  # every atom really did move
    assert np.allclose(shifts, shifts[0], atol=1e-9)  # by the same vector
    assert np.array_equal(np.array(pc.compute_periodic_charges(crystal).charges), published)


@needs_si
def test_gate_conservation_holds_on_all_twelve_and_the_adjustment_is_reported():
    """Pre-registration gate 2, over the whole corpus, plus the count §3 says travels with the
    charges. It has to vary: a structure whose plain rounding already sums to zero reports 0, which
    is what separates a reported count from a constant."""
    counts = {}
    for path in sorted(STRUCTURES.glob("*_EQeq.mol")):
        crystal, _published = crystal_from_listing(path)
        result = pc.compute_periodic_charges(crystal)
        assert not result.refusal, f"{path.stem}: {result.message}"
        assert abs(sum(result.charges)) < 1e-9, path.stem
        counts[path.stem] = result.adjusted_atoms
    assert len(counts) == 12
    assert min(counts.values()) == 0 and max(counts.values()) > 0, counts


@needs_si
def test_the_charge_centre_table_is_reported_and_changes_the_answer(monkeypatch):
    """The centres are an INPUT the paper's two artifacts state differently, so the result names the
    centre used for every element, and dropping one changes the charges."""
    crystal, published = crystal_from_listing(STRUCTURES / "Pd-2-pymo_EQeq.mol")
    result = pc.compute_periodic_charges(crystal)
    assert result.centres["Pd"] == 2
    assert "text" in result.centre_sources["Pd"]  # absent from chargecenters.dat
    assert result.centre_sources["C"].startswith("not listed")

    monkeypatch.setattr(pc, "charge_centres", lambda: {})
    without = pc.compute_periodic_charges(crystal)
    assert not without.refusal
    assert without.centres["Pd"] == 0
    assert not np.array_equal(np.array(without.charges), published)


# --- gate 3: determinism, and the one place the atom order is felt ---------------------------------


def test_the_same_structure_gives_byte_identical_charges():
    """Pre-registration gate 3. A float solve repeated has no right to drift, and this says so."""
    first, second = pc.compute_periodic_charges(_nacl()), pc.compute_periodic_charges(_nacl())
    assert first.charges == second.charges


def test_reordering_the_sites_moves_only_the_roundings_own_nudge():
    """**THE PUBLISHED ROUNDING IS ORDER-DEPENDENT, AND THAT IS INHERITED DELIBERATELY.** After
    rounding to 3 dp the cell need no longer be neutral, and the source restores it by moving the
    FIRST atoms by 0.001 e -- so which atoms carry that 0.001 depends on the order they are written
    in. Measured on the perfluoro fixture: two orderings differ on the nudged atoms by exactly
    0.001 e and nowhere else, with the same count reported either way."""
    from dataclasses import replace

    crystal = read_cif((FIXTURES / "1504676.cif").read_text(encoding="utf-8", errors="replace"))
    order = list(range(len(crystal.sites)))
    random.Random(7).shuffle(order)
    reordered = replace(crystal, sites=tuple(crystal.sites[index] for index in order))

    first = pc.compute_periodic_charges(crystal)
    second = pc.compute_periodic_charges(reordered)
    assert first.adjusted_atoms == second.adjusted_atoms > 0
    assert sorted(first.charges) != sorted(second.charges)
    difference = max(abs(a - b) for a, b in zip(sorted(first.charges), sorted(second.charges)))
    assert difference == pytest.approx(0.001, abs=1e-9)
    assert abs(sum(second.charges)) < 1e-9


# --- refusals -------------------------------------------------------------------------------------


def _nacl(displace: tuple[int, int, int] = (0, 0, 0)) -> Crystal:
    """Rock salt as eight P1 sites, with the first sodium optionally written in another cell."""
    fractional = [(0, 0, 0), (.5, .5, 0), (.5, 0, .5), (0, .5, .5),
                  (.5, 0, 0), (0, .5, 0), (0, 0, .5), (.5, .5, .5)]
    elements = ["Na"] * 4 + ["Cl"] * 4
    sites = []
    for index, (element, position) in enumerate(zip(elements, fractional)):
        shift = displace if index == 0 else (0, 0, 0)
        sites.append(Site(label=f"{element}{index}", element=element,
                          position=tuple(float(value + offset) for value, offset in zip(position, shift))))
    return Crystal(lattice=Lattice(5.63, 5.63, 5.63), sites=tuple(sites), name="NaCl")


def _simple_cell(elements=("Na", "Cl"), occupancy=1.0, positions=((0.0, 0.0, 0.0), (0.5, 0.5, 0.5))) -> Crystal:
    sites = tuple(Site(label=f"{element}{index}", element=element, position=position, occupancy=occupancy)
                  for index, (element, position) in enumerate(zip(elements, positions)))
    return Crystal(lattice=Lattice(5.63, 5.63, 5.63), sites=sites, name="test")


def test_a_partially_occupied_site_is_refused_and_says_so():
    result = pc.compute_periodic_charges(_simple_cell(occupancy=0.5))
    assert result.refusal == pc.REFUSE_DISORDERED_STRUCTURE
    assert "partial occupancy" in result.message
    assert result.charges == ()


def test_coincident_atoms_are_refused_as_disorder():
    crystal = _simple_cell(positions=((0.0, 0.0, 0.0), (0.001, 0.0, 0.0)))
    result = pc.compute_periodic_charges(crystal)
    assert result.refusal == pc.REFUSE_DISORDERED_STRUCTURE
    assert "apart" in result.message


def test_an_unparameterised_element_is_refused_by_name():
    result = pc.compute_periodic_charges(_simple_cell(elements=("Na", "Og")))
    assert result.refusal == pc.REFUSE_ELEMENT_NOT_PARAMETERISED
    assert "Og" in result.message


def test_an_element_with_no_bound_affinity_at_a_neutral_centre_refuses_rather_than_using_zero(monkeypatch):
    """Magnesium and zinc print "<0" in the source. Both carry a +2 centre in the shipped table and
    never read the affinity, so the refusal is reached by emptying that table -- the path must exist
    even though the corpus never meets it."""
    assert pc.ionization_table()["Mg"]["electron_affinity_eV"] is None
    crystal = _simple_cell(elements=("Mg", "Cl"))
    assert not pc.compute_periodic_charges(crystal).refusal  # with its +2 centre it computes

    monkeypatch.setattr(pc, "charge_centres", lambda: {})
    result = pc.compute_periodic_charges(crystal)
    assert result.refusal == pc.REFUSE_NO_AFFINITY
    assert "Mg" in result.message and "invented" in result.message


def test_a_structure_with_no_cell_is_refused():
    crystal = Crystal(lattice=Lattice(0.0, 0.0, 0.0), sites=(Site(label="Na", element="Na", position=(0, 0, 0)),))
    assert pc.compute_periodic_charges(crystal).refusal == pc.REFUSE_NO_CELL


# --- the crystal report, which is how a user reaches this ------------------------------------------


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "cif"


def _report(name: str):
    from openchem.chem.crystal_report import build_crystal_report

    return build_crystal_report(read_cif((FIXTURES / name).read_text(encoding="utf-8", errors="replace")))


def _charge_rows(report) -> dict[str, object]:
    return {fact.label: fact for fact in report.facts
            if "EQeq" in fact.label or fact.label in ("  C", "  H", "  F", "  Charge balance")}


def test_the_crystal_report_carries_the_charges_and_says_whose_method_they_are():
    """The whole point of the feature: a CIF opened in the application produces charges a reader can
    see, attributed, with the model's distance from a DFT charge attached to them."""
    rows = _charge_rows(_report("1504676.cif"))
    summary = rows["Partial charges (EQeq)"]
    assert summary.value == 60
    # **NO UNITS ON ANY OF THESE ROWS, AND THE SCREEN IS WHAT SAID SO.** `units` is composed onto
    # `display_value` by its consumers, and these displays are sentences: with units="e" the summary
    # painted "60 atoms; F -0.371; H +0.122; C +0.062 e", labelling one element's mean and not the
    # others -- while its `value` is the atom count, which is not a charge at all.
    assert all(not fact.units for fact in rows.values())
    assert "F -0.371" in summary.display_value
    assert any("Wilmer" in line for line in summary.evidence)
    assert any("3,452 atoms" in line for line in summary.evidence)
    assert any("Charge centres used" in line for line in summary.evidence)
    assert any("0.11 to 0.24 e" in line for line in summary.limitations)

    assert rows["  F"].display_value.startswith("mean -0.371, -0.437 to -0.318 over 10 atoms")
    assert rows["  Charge balance"].display_value.startswith("sums to zero by construction")


def test_a_disordered_structure_gets_its_refusal_in_the_report_rather_than_silence():
    """Four of the six committed CIF fixtures refuse for partial occupancy, so this is the row most
    readers will actually meet. A missing section would read as the feature being broken."""
    from openchem.domain.report import Detail

    rows = _charge_rows(_report("1569411.cif"))
    assert "partial occupancy" in rows["Partial charges (EQeq)"].display_value
    assert "O1W" in rows["Partial charges (EQeq)"].display_value
    assert rows["Partial charges (EQeq)"].value is None
    # **AND AT STANDARD DETAIL, WHICH IS THE HALF A FACT-LIST TEST CANNOT SEE.** Written ADVANCED
    # first, and the real dialog then showed "0 of 45 facts match 'charge'" -- the row was in the
    # report and behind the default filter, which is the state this test's own first line claims to
    # rule out.
    assert rows["Partial charges (EQeq)"].detail is Detail.STANDARD


def test_a_cell_over_the_reports_budget_is_not_equilibrated_at_all(monkeypatch):
    """The cap has to stop the WORK, not just the printing -- it exists because the report is built
    synchronously every time a crystal is selected."""
    from openchem.chem import crystal_report

    calls = []
    monkeypatch.setattr(crystal_report, "CHARGE_MAX_ATOMS", 10)
    monkeypatch.setattr(pc, "compute_periodic_charges", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(
        AssertionError("the solver ran above the cap")))

    from openchem.domain.report import Detail

    row = _charge_rows(_report("1504676.cif"))["Partial charges (EQeq)"]
    assert calls == []
    assert "60 atoms in the cell" in row.display_value and "up to 10" in row.display_value
    assert row.detail is Detail.STANDARD  # see the disorder test: a refusal nobody can see is none


def test_nothing_was_added_to_the_molecular_calculator_registry():
    """**GATE 5, AS AMENDMENT 4-A2 REPLACES IT.** The pre-registration expected a registered
    calculator declaring CRYSTAL, and the measurement says a crystal cannot be addressed at all:
    `CalculationRequest` carries a `molecule_uuid` and `test_a_calculation_cannot_even_be_ADDRESSED_`
    `to_a_crystal` keeps it so deliberately. This ships where the powder pattern ships, and the
    inapplicable list is therefore unchanged."""
    from openchem.chem.crystal_report import inapplicable_calculators
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    assert set(inapplicable_calculators()) == {d.display_name for d in CALCULATOR_DEFINITIONS}
    assert not any("EQeq" in d.display_name or "eqeq" in d.calculator_id for d in CALCULATOR_DEFINITIONS)


# --- the model's own constants ---------------------------------------------------------------------


def test_the_published_constants_and_settings_are_pinned():
    assert (pc.COULOMB_EV_ANGSTROM, pc.COULOMB_SCALING) == (14.4, 1.2)
    assert pc.HYDROGEN_AFFINITY_EV == -2.0
    assert pc.LATTICE_SHELLS == 2  # TRIAGE 3.9: the published charges are this setting
    assert pc.CHARGE_DIGITS == 3


def test_the_orbital_term_carries_two_a():
    hardness, distance = np.array([[10.0]]), np.array([[1.5]])
    a = hardness / pc.COULOMB_EV_ANGSTROM
    as_article_prints_it = np.exp(-((a * distance) ** 2)) * (a - a * a * distance - 1.0 / distance)
    code = pc._orbital_overlap(hardness, distance, pc.COULOMB_EV_ANGSTROM)
    assert float(code[0, 0]) == pytest.approx(-0.00039, abs=1e-5)
    assert float(as_article_prints_it[0, 0]) == pytest.approx(-0.2350, abs=1e-4)


def test_a_truncated_sum_is_invariant_to_moving_the_structure_and_not_to_moving_one_atom():
    """**THE CAUSE OF AMENDMENT 4-A1, ON EIGHT SHIPPED ATOMS.** A direct sum of a 1/r kernel over a
    finite block of cells is conditionally convergent, so its value depends on the region summed: a
    rigid shift moves the region with the structure and changes nothing, and moving ONE atom by a
    cell edge changes that atom's pair terms by electronvolts. It is why the published charges for
    two of the twelve MOFs depend on representatives a CIF cannot carry."""
    edge = 5.63
    vectors = np.eye(3) * edge
    positions = edge * np.array([[0, 0, 0], [.5, .5, 0], [.5, 0, .5], [0, .5, .5],
                                 [.5, 0, 0], [0, .5, 0], [0, 0, .5], [.5, .5, .5]], dtype=float)
    hardness = np.full(8, 10.0)
    home = pc._pair_matrix(positions, vectors, hardness, pc.LATTICE_SHELLS)

    rigid = pc._pair_matrix(positions + vectors[0] + 2 * vectors[1], vectors, hardness, pc.LATTICE_SHELLS)
    assert np.array_equal(rigid, home)

    one_atom = positions.copy()
    one_atom[0] += vectors[0]
    moved = pc._pair_matrix(one_atom, vectors, hardness, pc.LATTICE_SHELLS)
    assert float(np.max(np.abs(moved - home))) == pytest.approx(3.23, abs=0.01)


def test_the_expansion_is_what_removes_that_freedom():
    """Which is why `wrapped_sites` is a count and not a refusal: whatever cell the file writes an
    atom in, the expansion reads it into the home cell, so the same structure gives the same charges.
    The published convention does not have that property."""
    home = pc.compute_periodic_charges(_nacl())
    translated = pc.compute_periodic_charges(_nacl(displace=(1, -2, 0)))
    assert translated.wrapped_sites == 1 and home.wrapped_sites == 0
    assert translated.charges == home.charges


def test_the_rounding_reports_how_many_atoms_it_moved():
    rounded, moved = pc.round_charges(np.array([0.0005, 0.0005, 0.0005, -0.0015]))
    assert abs(rounded.sum()) < 1e-9 and moved > 0
    rounded, moved = pc.round_charges(np.array([0.2, -0.2]))
    assert moved == 0


def test_both_data_files_ship_in_the_frozen_build():
    """A data file that works from a checkout and is missing from the installer is this project's
    established failure mode, and both of these are read unconditionally. Same guard
    `test_lewis_adduct` and `test_element_reference` use."""
    spec = (pathlib.Path(__file__).resolve().parent.parent / "packaging" / "openchem.spec").read_text(
        encoding="utf-8")
    assert "eqeq_ionization.json" in spec
    assert "eqeq_charge_centres.json" in spec


def test_the_ionisation_table_keeps_its_sources_and_its_absences():
    table = pc.ionization_table()
    assert table["C"]["electron_affinity_eV"] == pytest.approx(1.262118, abs=1e-6)
    assert table["N"]["electron_affinity_eV"] == pytest.approx(-0.07, abs=1e-6)
    assert table["Mg"]["electron_affinity_eV"] is None and table["Mg"]["affinity_as_printed"] == "<0"
    assert table["O"]["ionization_potentials_eV"][0] == 13.618
