"""The primary-arm runner of the proton-affinity benchmark (`benchmarks/proton_affinity/run_pa.py`): the structures it builds, the ORCA output it reads and the selection it makes, on real ORCA output (water and H3O+, trimmed) and synthetic records. Nothing here runs ORCA."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "proton_affinity"
_FIXTURES = Path(__file__).parent / "fixtures" / "orca"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# run_pa imports `judge` and `pa_core` by their plain names from its own directory
sys.path.insert(0, str(_DIRECTORY))
try:
    run = _load("proton_affinity_run", "run_pa.py")
finally:
    sys.path.remove(str(_DIRECTORY))
core = sys.modules["pa_core"]
judge = sys.modules["judge"]

REFERENCE = json.loads((_DIRECTORY / "nist_values.json").read_text(encoding="utf-8"))["bases"]
WATER = (_FIXTURES / "pa_water_optfreq.out").read_text(encoding="utf-8")
HYDRONIUM = (_FIXTURES / "pa_h3o_optfreq.out").read_text(encoding="utf-8")


def _sites(name: str) -> list[tuple[str, str]]:
    mol = run.base_molecule(name)
    return [(mol.GetAtomWithIdx(s["atom"]).GetSymbol(), s["kind"]) for s in run.candidate_sites(mol)]


# --- the data ---------------------------------------------------------------------------------------------------------------


def test_every_reference_base_has_a_smiles_and_no_other_does():
    assert set(run.BASES) == {r["name"] for r in REFERENCE}
    assert len(run.BASES) == 28


# --- protonation sites ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("water", [("O", "lone_pair")]),
        ("ammonia", [("N", "lone_pair")]),  # three equivalent lone-pair directions are one site; the hydrogens are not sites
        ("benzene", [("C", "pi_carbon")]),  # six equivalent carbons
        ("carbon monoxide", [("C", "lone_pair")]),  # the oxygen carries the positive charge and is not a site
        ("hydrogen cyanide", [("N", "lone_pair")]),  # C#N is not a carbon-carbon multiple bond
        ("acetonitrile", [("N", "lone_pair")]),
        ("formamide", [("N", "lone_pair"), ("O", "lone_pair")]),
        ("acetic acid", [("O", "lone_pair"), ("O", "lone_pair")]),  # carbonyl and hydroxyl oxygen
    ],
)
def test_candidate_sites_of_the_small_bases(name, expected):
    assert sorted(_sites(name)) == sorted(expected)


def test_a_ring_carbon_bonded_only_to_heteroatoms_is_a_site():
    # the rule says every carbon of an aromatic ring: pyrimidine C2 and imidazole C2 sit between two nitrogens
    pyrimidine = _sites("pyrimidine")
    assert sorted(pyrimidine) == sorted([("N", "lone_pair")] + [("C", "pi_carbon")] * 3)  # C2, C4/6, C5
    imidazole = _sites("imidazole")
    assert sorted(imidazole) == sorted([("N", "lone_pair")] * 2 + [("C", "pi_carbon")] * 3)  # C2, C4, C5 (the two nitrogens differ)


def test_aniline_has_the_amine_and_four_ring_classes():
    assert sorted(_sites("aniline")) == sorted([("N", "lone_pair")] + [("C", "pi_carbon")] * 4)  # ipso, ortho, meta, para


# --- the proton's starting position -----------------------------------------------------------------------------------------


def _embedded(name: str):
    mol = run.base_molecule(name)
    return mol, run.conformers_of(mol)[0]


def test_a_proton_on_water_is_placed_on_the_lone_pair_side_at_an_oxygen_hydrogen_distance():
    mol, xyz = _embedded("water")
    site = run.candidate_sites(mol)[0]
    symbols, ion = run.add_proton(mol, xyz, site)

    assert symbols == ["O", "H", "H", "H"] and len(ion) == 4
    assert np.allclose(ion[:3], xyz)  # the base's atoms are untouched and the proton is last
    assert np.linalg.norm(ion[3] - xyz[0]) == pytest.approx(0.97, abs=1e-6)
    assert np.dot(ion[3] - xyz[0], (xyz[1] - xyz[0]) + (xyz[2] - xyz[0])) < 0  # away from the two hydrogens, not on top of one


def test_a_proton_on_a_pi_carbon_stands_perpendicular_to_the_plane():
    mol, xyz = _embedded("benzene")
    site = run.candidate_sites(mol)[0]
    _, ion = run.add_proton(mol, xyz, site)
    plane = np.cross(xyz[1] - xyz[0], xyz[2] - xyz[0])
    plane /= np.linalg.norm(plane)
    bond = ion[-1] - xyz[site["atom"]]

    assert abs(np.dot(bond / np.linalg.norm(bond), plane)) == pytest.approx(1.0, abs=1e-3)
    assert np.linalg.norm(bond) == pytest.approx(1.09, abs=1e-6)


def test_a_proton_on_carbon_monoxide_goes_on_the_axis_away_from_oxygen():
    mol, xyz = _embedded("carbon monoxide")
    site = run.candidate_sites(mol)[0]
    _, ion = run.add_proton(mol, xyz, site)
    axis = (xyz[0] - xyz[1]) / np.linalg.norm(xyz[0] - xyz[1])  # from O towards C, and beyond

    assert (ion[-1] - xyz[0]) / np.linalg.norm(ion[-1] - xyz[0]) == pytest.approx(axis, abs=1e-6)


# --- the structure list -----------------------------------------------------------------------------------------------------


def test_the_structure_list_covers_every_base_and_every_site_and_is_reproducible():
    first = run.build_structures()
    second = run.build_structures()

    assert [s["id"] for s in first] == [s["id"] for s in second]
    assert all(np.allclose(a["coordinates"], b["coordinates"]) for a, b in zip(first, second, strict=True))  # the seed is pinned
    for name in run.BASES:
        base = [s for s in first if s["base"] == name and s["role"] == "base"]
        ions = [s for s in first if s["base"] == name and s["role"] == "ion"]
        sites = run.candidate_sites(run.base_molecule(name))
        assert 1 <= len(base) <= run.KEEP
        assert len(ions) == len(sites) * len(base)
    assert all(s["charge"] == (1 if s["role"] == "ion" else 0) for s in first)
    assert len({s["id"] for s in first}) == len(first)


def test_an_ion_start_has_one_more_hydrogen_than_its_base():
    structures = run.build_structures()
    ion = next(s for s in structures if s["role"] == "ion" and s["base"] == "ammonia")
    base = next(s for s in structures if s["role"] == "base" and s["base"] == "ammonia")
    assert ion["symbols"] == base["symbols"] + ["H"]


# --- the ORCA input ---------------------------------------------------------------------------------------------------------


def test_the_input_is_the_preregistered_one_and_a_retry_adds_the_hessian():
    structure = {"charge": 1, "symbols": ["O", "H"], "coordinates": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.97]]}
    text = run.orca_input(structure, cores=4)
    retried = run.orca_input(structure, cores=4, retry=True)

    assert text.startswith("! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq\n%pal nprocs 4 end\n%maxcore 3000\n")
    assert "* xyz 1 1\n" in text
    assert "Calc_Hess" not in text
    assert "%geom\n  Calc_Hess true\nend" in retried


# --- reading ORCA's output ---------------------------------------------------------------------------------------------------


def test_the_water_and_hydronium_outputs_are_read_as_printed():
    water, hydronium = run.parse_output(WATER), run.parse_output(HYDRONIUM)

    assert (water["enthalpy"], water["gibbs"], water["sigma_orca"]) == (-76.40397512, -76.42539298, 2)
    assert (hydronium["enthalpy"], hydronium["gibbs"], hydronium["sigma_orca"]) == (-76.66319385, -76.68619414, 1)
    assert hydronium["symbols"] == ["O", "H", "H", "H"] and len(hydronium["coordinates"]) == 4
    assert hydronium["frequencies"][6] == 807.65 and len(hydronium["frequencies"]) == 12
    assert water["orca_version"] == "6.1.1"


def test_the_proton_affinity_of_water_from_the_real_outputs_is_what_the_smoke_run_gave():
    water, hydronium = run.parse_output(WATER), run.parse_output(HYDRONIUM)
    pa_kj = core.proton_affinity(water["enthalpy"], hydronium["enthalpy"]) * core.HARTREE_TO_KCAL * 4.184

    assert pa_kj == pytest.approx(686.8, abs=0.2)  # the preregistration's disclosed smoke number


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda t: t.replace("THE OPTIMIZATION HAS CONVERGED", "NOT DONE"), "did not converge"),
        (lambda t: t.replace("Total enthalpy", "Total energy"), "enthalpy"),
        (lambda t: t.replace("298.15 K", "300.00 K"), "300.00 K"),
        (lambda t: t.replace("1.00 atm", "2.00 atm"), "2.00 atm"),
        (lambda t: t.replace("VIBRATIONAL FREQUENCIES", "VIBRATIONAL"), "frequencies"),
    ],
)
def test_an_output_missing_something_is_refused_naming_it(mutation, message):
    with pytest.raises(ValueError, match=message):
        run.parse_output(mutation(WATER))


# --- what is computed from one output ---------------------------------------------------------------------------------------


def test_orcas_symmetry_number_of_hydronium_is_replaced_and_the_gibbs_energy_corrected():
    structure = {"base": "water", "role": "ion", "charge": 1}
    result = run.finish(structure, run.parse_output(HYDRONIUM))

    assert result["sigma_orca"] == 1 and result["sigma_true"] == 3
    assert result["symmetry_correction"] * core.HARTREE_TO_KCAL == pytest.approx(0.65, abs=0.01)
    assert result["gibbs_corrected"] == pytest.approx(result["gibbs"] + result["symmetry_correction"])
    assert result["site_assigned"] == 0  # the oxygen gained the hydrogen


def test_water_needs_no_symmetry_correction_and_a_base_has_no_site():
    result = run.finish({"base": "water", "role": "base", "charge": 0}, run.parse_output(WATER))

    assert result["sigma_true"] == 2 and result["symmetry_correction"] == 0.0
    assert "site_assigned" not in result


def test_a_proton_that_left_the_base_is_no_site():
    parsed = run.parse_output(HYDRONIUM)
    parsed["coordinates"][3] = [8.0, 8.0, 8.0]  # one hydrogen far away: the base plus a free proton
    assert run.assigned_site({"base": "water"}, parsed) is None


def test_a_proton_that_moved_to_another_heavy_atom_is_assigned_to_where_it_ended():
    # methanol protonated at O, started as if on C: the count of hydrogens decides, not the start
    mol = run.base_molecule("methanol")
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    xyz = run.conformers_of(mol)[0]
    oxygen = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "O")
    ion_symbols, ion = run.add_proton(mol, xyz, {"atom": oxygen, "kind": "lone_pair"})

    assert run.assigned_site({"base": "methanol"}, {"symbols": ion_symbols, "coordinates": ion.tolist()}) == oxygen
    assert symbols == ion_symbols[:-1]


# --- which structures count, and the selection -------------------------------------------------------------------------------


def _record(structure, base, role, enthalpy, gibbs=None, lowest=0.0, site=0, completed=True, retry=False, commit="abc", dirty=False):
    return {"structure": structure, "base": base, "role": role, "retry": retry, "commit": commit, "dirty": dirty, "completed": completed, "enthalpy": enthalpy,
            "gibbs_corrected": enthalpy - 0.02 if gibbs is None else gibbs, "gibbs": 0.0, "lowest_frequency": lowest, "sigma_orca": 1, "sigma_true": 1, "symmetry_correction": 0.0,
            "site_assigned": site if role == "ion" else None}


def test_an_imaginary_frequency_excludes_a_structure_and_a_retry_replaces_it():
    first = _record("w|base|0", "water", "base", -76.40, lowest=-60.0)
    retried = _record("w|base|0", "water", "base", -76.41, lowest=10.0, retry=True)
    other = _record("w|base|1", "water", "base", -76.30, lowest=-30.0)
    failed = _record("w|base|2", "water", "base", 0.0, completed=False)

    assert accepted_ids([first, other, failed]) == []
    assert accepted_ids([first, retried, other, failed]) == ["w|base|0"]
    assert accepted_ids([retried, first]) == []  # the later record is the structure's current state


def accepted_ids(records):
    return sorted(r["structure"] for r in run.accepted(records))


def test_the_proton_affinity_uses_the_lowest_enthalpy_structure_of_each_species_and_gb_chooses_independently():
    records = [
        _record("b0", "x", "base", -100.00, gibbs=-100.05),
        _record("b1", "x", "base", -99.99, gibbs=-100.08),  # higher H, lower G: GB takes this one, PA does not
        _record("i0", "x", "ion", -100.30, gibbs=-100.33, site=1),
        _record("i1", "x", "ion", -100.28, gibbs=-100.36, site=2),  # lower G on another site
    ]
    h_proton, _, g_proton = core.proton_terms()

    pa = run.select(records, "x", "pa")
    gb = run.select(records, "x", "gb")

    assert pa["value_eh"] == pytest.approx(-100.00 + h_proton + 100.30)
    assert pa["site_atom"] == 1
    assert gb["value_eh"] == pytest.approx(-100.08 + g_proton + 100.36)
    assert gb["site_atom"] == 2


def test_a_base_missing_either_species_has_no_value_and_a_lost_proton_is_not_an_ion():
    base = _record("b0", "x", "base", -100.0)
    ion = _record("i0", "x", "ion", -100.3)
    lost = dict(_record("i1", "x", "ion", -105.0), site_assigned=None)

    assert run.select([base], "x", "pa") is None
    assert run.select([ion], "x", "pa") is None
    assert run.select([base, lost], "x", "pa") is None  # a structure whose proton left is not a conjugate acid
    assert run.select([base, ion, lost], "x", "pa")["structures"] == 2


# --- the report -------------------------------------------------------------------------------------------------------------


def _all_records(commit="abc", dirty=False, error_kcal=0.0, skip=()):
    """A record set in which every base's computed PA and GB are the reference plus `error_kcal` (built by inverting the arithmetic)."""
    h_proton, _, g_proton = core.proton_terms()
    records = []
    for ref in REFERENCE:
        if ref["name"] in skip:
            continue
        pa_eh = (ref["pa_kj"] / 4.184 + error_kcal) / core.HARTREE_TO_KCAL
        gb_eh = (ref["gb_kj"] / 4.184 + error_kcal) / core.HARTREE_TO_KCAL
        records.append(_record(f"{ref['name']}|base|0", ref["name"], "base", -100.0, gibbs=-100.0, commit=commit, dirty=dirty))
        records.append(_record(f"{ref['name']}|ion|0", ref["name"], "ion", -100.0 + h_proton - pa_eh, gibbs=-100.0 + g_proton - gb_eh, commit=commit, dirty=dirty))
    return records


def test_a_set_that_reproduces_the_reference_passes_and_one_off_by_six_kcal_fails():
    text, verdict = run.report_text(_all_records(), REFERENCE)
    assert verdict["verdicts"] == {"pa": judge.PASS, "gb": judge.PASS} and verdict["problem"] is None
    assert "PA VERDICT PASS" in text

    _, off = run.report_text(_all_records(error_kcal=6.0), REFERENCE)
    assert off["verdicts"] == {"pa": judge.FAIL, "gb": judge.FAIL}


def test_a_report_with_more_than_two_missing_deciding_bases_is_not_evaluable():
    deciding = [r["name"] for r in REFERENCE if r["pa_kj"] > judge.LOW_BASICITY_KJ]
    _, ok = run.report_text(_all_records(skip=deciding[:2]), REFERENCE)
    _, many = run.report_text(_all_records(skip=deciding[:3]), REFERENCE)

    assert ok["verdicts"]["pa"] == judge.PASS  # two missing are allowed
    assert many["verdicts"] == {"pa": judge.NOT_EVALUABLE, "gb": judge.NOT_EVALUABLE}


def test_records_from_two_commits_or_a_dirty_tree_are_refused_even_when_perfect():
    mixed = _all_records()
    mixed[0] = dict(mixed[0], commit="def")
    dirty = _all_records(dirty=True)

    for records in (mixed, dirty):
        text, verdict = run.report_text(records, REFERENCE)
        assert verdict["verdicts"] == {"pa": judge.NOT_EVALUABLE, "gb": judge.NOT_EVALUABLE}
        assert verdict["problem"] and "REFUSED" in text


def test_the_report_says_how_often_orcas_symmetry_number_was_overridden():
    records = _all_records()
    records[1] = dict(records[1], sigma_orca=1, sigma_true=3, symmetry_correction=0.001)
    text, _ = run.report_text(records, REFERENCE)

    assert "differs from the one used in 1 of" in text
    assert "ORCA 1, used 3" in text
