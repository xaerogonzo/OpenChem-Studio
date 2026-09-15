"""The pre-registered checks of benchmarks/charges/models/TRIAGE.md, section 2.

They read committed fixtures only. A check that fails is recorded in TRIAGE.md
section 3 and kept here as a strict xfail stop record, never loosened.
"""

from __future__ import annotations

import csv
import importlib.util
import math
import pathlib
import sys
from collections import defaultdict

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "charge_models"

_spec = importlib.util.spec_from_file_location("nistor_extract", ROOT / "benchmarks" / "charges" / "models" / "nistor_extract.py")
nx = importlib.util.module_from_spec(_spec)
sys.modules["nistor_extract"] = nx
_spec.loader.exec_module(nx)

METHODS = ("esp", "i", "ii", "iii", "iv")
SYMBOL = {1: "H", 6: "C", 8: "O", 14: "Si"}


def _rows(name: str) -> list[dict[str, str]]:
    lines = [l for l in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return list(csv.DictReader(lines))


def _molecules() -> dict[int, list[dict[str, str]]]:
    out: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in _rows("nistor2006_si_molecules.csv"):
        out[int(row["index"])].append(row)
    return dict(out)


def _decimals(value: str) -> int:
    return len(value.split(".")[1]) if "." in value else 0


# 2.1.1 -----------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="STOP RECORD 2.1.1: molecule 28's index name 'SiH(CH2)3' is Si1C3H7; its table holds C4H10Si")
def test_nistor_all_41_tables_are_present_and_match_their_index_formula():
    molecules = _molecules()
    assert sorted(molecules) == list(range(1, 42))
    for number, atoms in molecules.items():
        counts: dict[str, int] = defaultdict(int)
        for atom in atoms:
            counts[SYMBOL[int(atom["Z"])]] += 1
        assert dict(counts) == nx.formula_counts(nx.INDEX[number]), (number, nx.INDEX[number])
        assert [int(a["atom"]) for a in atoms] == list(range(1, len(atoms) + 1))


def test_the_index_formula_parser_reads_the_sites_unbalanced_names():
    assert nx.formula_counts("(CH3)3Si)2O") == {"C": 6, "H": 18, "Si": 2, "O": 1}
    assert nx.formula_counts("[(HO)3SiO](HO)2SiSi(OH)3") == {"H": 8, "O": 9, "Si": 3}
    assert nx.formula_counts("CH3-C(OH)3") == {"C": 2, "H": 6, "O": 3}


# 2.1.2 -----------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="STOP RECORD 2.1.2: 4 of 205 columns exceed n x 0.5e-4 (molecules 5 ii and iv, 14 ii, 18 ii; worst 18 ii, -0.0016 against 0.0012)")
def test_nistor_every_charge_column_sums_to_zero_within_printed_rounding():
    for number, atoms in _molecules().items():
        for method in METHODS:
            values = [a[method] for a in atoms]
            bound = len(values) * 0.5 * 10 ** (-min(_decimals(v) for v in values))
            total = sum(float(v) for v in values)
            assert abs(total) <= bound + 1e-12, (number, method, total, bound)


# 2.1.3 -----------------------------------------------------------------------


def _delta_squared(atoms, method) -> tuple[float, float]:
    """(Delta_n^2 of eq 18, its first-order rounding bound from +-5e-5 charges)."""
    qc = [float(a["esp"]) for a in atoms]
    q = [float(a[method]) for a in atoms]
    num = sum((x - y) ** 2 for x, y in zip(q, qc))
    den = sum(y * y for y in qc)
    h = 0.5 * 10 ** (-4)
    # d(num/den): |dnum| <= sum 2|q-qc|(2h); |dden| <= sum 2|qc|h
    dnum = sum(2 * abs(x - y) * 2 * h for x, y in zip(q, qc))
    dden = sum(2 * abs(y) * h for y in qc)
    ratio = num / den
    return ratio, (dnum + ratio * dden) / den


def _sigma_candidates_matching() -> dict[str, list]:
    sigma = {int(r["index"]): r for r in _rows("nistor2006_si_sigma.csv")}
    misses = {"100*Delta": [], "100*Delta^2": []}
    for number, atoms in _molecules().items():
        for method in ("i", "ii", "iii", "iv"):
            printed = float(sigma[number][method])
            printed_bound = 0.5 * 10 ** (-_decimals(sigma[number][method]))
            d2, bound = _delta_squared(atoms, method)
            d = math.sqrt(d2)
            d_bound = bound / (2 * d) if d > 0 else math.sqrt(bound)
            if abs(100 * d - printed) > 100 * d_bound + printed_bound:
                misses["100*Delta"].append((number, method, round(100 * d, 3), printed))
            if abs(100 * d2 - printed) > 100 * bound + printed_bound:
                misses["100*Delta^2"].append((number, method, round(100 * d2, 3), printed))
    return misses


def test_nistor_sigma_is_identified_as_one_form_of_eq_18_on_every_molecule():
    misses = _sigma_candidates_matching()
    winners = [name for name, m in misses.items() if not m]
    assert len(winners) == 1, {name: m[:6] for name, m in misses.items()}


# 2.1.4 -----------------------------------------------------------------------

COVALENT = {"H": 0.31, "C": 0.76, "O": 0.66, "Si": 1.11}


def _classify_origin_atoms() -> dict[tuple[int, int], str]:
    out = {}
    for number, atoms in _molecules().items():
        coords = [(float(a["x"]), float(a["y"]), float(a["z"])) for a in atoms]
        for k, atom in enumerate(atoms):
            if k == 0 or coords[k] != (0.0, 0.0, 0.0):
                continue
            element = SYMBOL[int(atom["Z"])]
            distances = sorted((math.dist(coords[k], coords[j]), SYMBOL[int(atoms[j]["Z"])]) for j in range(len(atoms)) if j != k)
            nearest, neighbour = distances[0]
            ideal = COVALENT[element] + COVALENT[neighbour]
            valid = 0.85 * ideal <= nearest <= 1.25 * ideal and all(d >= 0.7 for d, _ in distances)
            out[(number, int(atom["atom"]))] = "VALID" if valid else "SUSPECT"
    return out


def test_nistor_origin_atoms_are_classified_and_m111_is_among_them():
    """Measured 2026-09-14, and wider than the one case the triage expected: the
    LAST atom of all 41 tables sits at exactly (0, 0, 0), always a hydrogen.
    The rule, as frozen, calls 31 SUSPECT and 10 VALID, and the VALID ones are
    coincidences of where the origin falls (molecule 16's "hydrogen" is 1.166 A
    from two oxygens at once). The pattern is a page-export artifact, so every
    molecule's geometry is missing one hydrogen, whatever the rule says."""
    molecules = _molecules()
    classified = _classify_origin_atoms()
    assert set(classified) == {(n, len(atoms)) for n, atoms in molecules.items()}
    assert all(SYMBOL[int(molecules[n][a - 1]["Z"])] == "H" for n, a in classified)
    assert sorted(k for k, v in classified.items() if v == "VALID") == [
        (9, 13), (11, 12), (16, 14), (17, 19), (22, 14), (27, 24), (28, 15), (32, 11), (33, 7), (41, 15)]


# 2.1.5 -----------------------------------------------------------------------


def test_nistor_the_measured_departures_are_exactly_these():
    """The stop records' contents, pinned, so a re-extraction that changes any
    of them fails here rather than silently turning a stop record green."""
    sums = sorted((n, m) for n, atoms in _molecules().items() for m in METHODS
                  if abs(sum(float(a[m]) for a in atoms)) > len(atoms) * 0.5e-4 + 1e-12)
    assert sums == [(5, "ii"), (5, "iv"), (14, "ii"), (18, "ii")]
    table = _rows("nistor2006_table4.csv")
    atoms = _molecules()[23]
    differing = [(p["atom"], pc) for p, a in zip(table, atoms)
                 for pc, col in (("ab_initio", "esp"), ("i", "i"), ("ii", "ii"), ("iii", "iii"), ("iv", "iv")) if p[pc] != a[col]]
    assert differing == [("15", "i")]
    misses = _sigma_candidates_matching()
    assert misses["100*Delta"] == [] and len(misses["100*Delta^2"]) == 164


@pytest.mark.xfail(strict=True, reason="STOP RECORD 2.1.5: atom 15 method (i) is 0.0929 in the paper's Table IV and 0.0930 in the supplement")
def test_nistor_supplement_hexamethyldisiloxane_equals_the_papers_table_iv():
    table = _rows("nistor2006_table4.csv")
    assert len(table) == 27
    atoms = _molecules()[23]
    assert len(atoms) == 27
    for printed, extracted in zip(table, atoms):
        assert SYMBOL[int(extracted["Z"])] == printed["element"]
        for paper_col, si_col in (("ab_initio", "esp"), ("i", "i"), ("ii", "ii"), ("iii", "iii"), ("iv", "iv")):
            assert printed[paper_col] == extracted[si_col], (printed["atom"], paper_col)


# 2.2 -------------------------------------------------------------------------

_mspec = importlib.util.spec_from_file_location("mathieu_eem_check", ROOT / "benchmarks" / "charges" / "models" / "mathieu_eem_check.py")
mec = importlib.util.module_from_spec(_mspec)
sys.modules["mathieu_eem_check"] = mec
_mspec.loader.exec_module(mec)


@pytest.fixture(scope="module")
def mathieu_report():
    return mec.evaluate()


def test_mathieu_population_is_all_194_neutral_molecules_with_nothing_refused(mathieu_report):
    assert mathieu_report["molecules"] == 194
    assert mathieu_report["excluded"] == [] and mathieu_report["refused"] == []
    assert mathieu_report["nonzero_mulliken_sum"] == []
    assert mathieu_report["counts"] == {"C": 965, "H": 1812, "N": 92, "O": 133, "F": 62}


@pytest.mark.parametrize("key", ["C", "H", "N", "O", "F", "All"])
def test_the_shipped_eem_reproduces_mathieus_table_i_r_squared(mathieu_report, key):
    """Six printed R^2 values, reproduced by `ce.eem_charges` unchanged."""
    assert mec.verdict(mathieu_report)[key]


@pytest.mark.xfail(strict=True, reason="STOP RECORD 2.2: eq 15's Delta-q as printed (no root) gives 0.0045 against Table I's 0.0668")
def test_the_shipped_eem_reproduces_mathieus_table_i_delta_q(mathieu_report):
    assert mec.verdict(mathieu_report)["dq"]


def test_mathieu_delta_q_diagnostics_are_exactly_these(mathieu_report):
    """Pinned: the square root of eq 15 lands 6.6e-5 from the printed 0.0668,
    just outside the rounding bound; the all-atom RMS first guessed is far off."""
    assert mathieu_report["metrics"]["dq"] == pytest.approx(0.004453, abs=5e-7)
    assert mathieu_report["diagnostics"]["sqrt_dq"] == pytest.approx(0.066734, abs=5e-7)
    assert mathieu_report["diagnostics"]["all_atom_rms"] == pytest.approx(0.043558, abs=5e-7)


# 2.4 / 2.5: fixtures, manifests and the EEM arm -------------------------------------------------

_sspec = importlib.util.spec_from_file_location("mathieu_sqe_check", ROOT / "benchmarks" / "charges" / "models" / "mathieu_sqe_check.py")
sqc = importlib.util.module_from_spec(_sspec)
sys.modules["mathieu_sqe_check"] = sqc
_sspec.loader.exec_module(sqc)

#: LF-normalised SHA-256, as recorded in TRIAGE.md 3.4.
MATHIEU_HASHES = {
    "mathieu2007_eq.csv": "c63f1dd1f5f0195917377118ce1abca9e3ae5dee84d79a69d6c1674f605c28f7",
    "mathieu2007_eq_manifest.csv": "d932da7a8166cc57c20eda4fa8b38c86636eb835f978658abadee97892b1e0af",
    "mathieu2007_ts.csv": "c17f74d0d0e8e99c059ad1941356bb7361cb981afefff1f798a29e5dc603c40d",
    "mathieu2007_ts_manifest.csv": "37f75e9c6f1ced540112bd60550a46444b0f3452478d94ce889f813251b887c7",
}
MATHIEU_COUNTS = {"EQ": (194, 3064, {"C": 965, "H": 1812, "N": 92, "O": 133, "F": 62}),
                  "TS": (55, 1085, {"C": 327, "H": 592, "N": 15, "O": 146, "F": 5})}


@pytest.mark.parametrize("name", sorted(MATHIEU_HASHES))
def test_mathieu_fixture_and_manifest_hashes_are_the_recorded_ones(name):
    import hashlib
    data = (FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == MATHIEU_HASHES[name]
    assert MATHIEU_HASHES[name] in (ROOT / "benchmarks" / "charges" / "models" / "TRIAGE.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("set_name", ["EQ", "TS"])
def test_mathieu_csv_agrees_with_its_source_manifest(set_name):
    _, fixture, manifest = mec.SETS[set_name]
    rows = [r for r in csv.DictReader(l for l in manifest.read_text(encoding="utf-8").splitlines() if not l.startswith("#"))]
    assert [(r["kind"], r["file"]) for r in rows[:2]] == [("readme", "README.TXT"), ("archive", "A6.11.108.EPAPS.ZIP")]
    assert rows[1]["sha256"] == "NOT HELD" and len(rows[0]["sha256"]) == 64
    molecules = mec.molecules(fixture)
    sources = rows[2:]
    assert [r["file"] for r in sources] == [f"{name}.xyz" for name in molecules]
    for source in sources:
        atoms = molecules[source["file"][:-4]]
        assert int(source["atoms"]) == len(atoms)
        for element in mec.ELEMENTS:
            assert int(source[element]) == sum(1 for a in atoms if a["element"] == element)
        strings = [[a["element"], a["x"], a["y"], a["z"], a["mulliken"]] for a in atoms]
        assert mec.checksums(strings) == {k: source[k] for k in ("mulliken_sum", "coordinate_sum", "abs_charge_sum")}


@pytest.mark.parametrize("set_name", ["EQ", "TS"])
def test_mathieu_population_counts_supported_elements_and_unique_keys(set_name):
    population = sqc.population(sqc.SETS[set_name])
    files, atoms, counts = MATHIEU_COUNTS[set_name]
    assert len(population) == files and sum(len(s["elements"]) for s in population) == atoms
    elements = [e for s in population for e in s["elements"]]
    assert {e: elements.count(e) for e in counts} == counts and set(elements) <= set(sqc.ELEMENTS)
    keys = [(s["file"], a) for s in population for a in s["atoms"]]
    assert len(keys) == len(set(keys))


@pytest.fixture(scope="module")
def eem_eq():
    return sqc.eem_check("EQ")


@pytest.fixture(scope="module")
def eem_ts():
    return sqc.eem_check("TS")


def test_24_baseline_the_shipped_eem_through_population_still_gives_22s_values(eem_eq):
    assert eem_eq["excluded"] == [] and sqc.baseline_holds(eem_eq["values"])


@pytest.mark.parametrize("metric", ["C", "H", "N", "O", "All"])
def test_25_the_shipped_eem_reproduces_the_eem_ts_row(eem_ts, metric):
    assert eem_ts["gates"][metric]


@pytest.mark.xfail(strict=True, reason="STOP RECORD 2.5: TS fluorine (n = 5) gives R^2 0.3499, outside Table I's [0.355, 0.365)")
def test_25_the_shipped_eem_reproduces_the_eem_ts_fluorine_r_squared(eem_ts):
    assert eem_ts["gates"]["F"]


def test_25_the_measured_values_and_verdict_are_exactly_these(eem_ts):
    measured = {m: round(eem_ts["values"][m]["r2"], 4) for m in sqc.METRICS}
    assert measured == {"C": 0.9574, "H": 0.8597, "N": 0.9282, "O": 0.8639, "F": 0.3499, "All": 0.9581}
    assert eem_ts["verdict"] == "PARTIAL" and eem_ts["excluded"] == []
    assert eem_ts["values"]["dq"]["sqrt"] == pytest.approx(0.084425, abs=5e-7)
    fluorine = sqc.small_subgroup(eem_ts["rows"], "eem", "F")
    assert (fluorine["n"], round(fluorine["loo_r2_min"], 4), round(fluorine["loo_r2_max"], 4)) == (5, 0.2566, 0.6145)
