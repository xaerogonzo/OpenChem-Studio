"""The low-temperature density correction study (`benchmarks/energetics_props/epb_density_correction.py`, `PREREGISTRATION.md` 15.8).

Everything here runs on SYNTHETIC pairs whose expansion is known exactly, so the fits, the choice, the bar, the bootstrap and the lock are checked
without a real label. The committed pairs file is read for its shape and its partition counts only: no pair is scored.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "benchmarks" / "energetics_props"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dc = _load("epb_density_correction", DIR / "epb_density_correction.py")
corpus = _load("epb_cod_corpus", DIR / "epb_cod_corpus.py")
vr = _load("validation_rows", ROOT / "tools" / "validation_rows.py")


def pair(key="K", t_low=100.0, t_rt=293.0, alpha=1.5e-4, rho_rt=1.700, noise=0.0, b=0.0, sg="P 1", z=4.0, code="1"):
    """A pair whose room-temperature density is exact for `alpha + b (t_low - 120)`, then moved by `noise`."""
    a = alpha + b * (t_low - dc.T_CENTRE_K)
    rho_low = rho_rt * (1.0 + a * (t_rt - t_low))
    ratio = rho_low / rho_rt
    return dc.Pair(key, sg, z, code, code + "r", t_low, t_rt, rho_low, rho_rt + noise, ratio)


def as_row(p: dc.Pair) -> dict:
    return {"key": p.key, "space_group": p.space_group, "z": p.z, "low_code": p.low_code, "rt_code": p.rt_code, "t_low": p.t_low, "t_rt": p.t_rt,
            "rho_low": p.rho_low, "rho_rt": p.rho_rt, "volume_ratio": p.volume_ratio}


def spread(n, *, alpha=1.5e-4, b=0.0, noise=0.0, prefix="K"):
    """n pairs with different keys and low temperatures 85..155 K; the noise alternates in sign so it does not bias."""
    return [pair(f"{prefix}{i}", t_low=85.0 + 70.0 * i / max(n - 1, 1), alpha=alpha, b=b, rho_rt=1.5 + 0.01 * i, noise=noise * (-1) ** i, code=str(i))
            for i in range(n)]


# ------------------------------------------------------------------------------------------------------ the fits
def test_the_constant_form_recovers_its_coefficient_exactly():
    fit = dc.fit_constant(spread(12, alpha=1.7e-4))
    assert fit.params[0] == pytest.approx(1.7e-4, rel=1e-9)


def test_the_linear_form_recovers_both_parameters_exactly():
    fit = dc.fit_linear(spread(12, alpha=1.5e-4, b=2e-7))
    assert fit.params[0] == pytest.approx(1.5e-4, rel=1e-9)
    assert fit.params[1] == pytest.approx(2e-7, rel=1e-6)


def test_the_linear_form_is_unavailable_when_the_low_temperatures_cannot_separate_its_parameters():
    assert dc.fit_linear([pair(f"K{i}", t_low=100.0, code=str(i)) for i in range(6)]) is None
    assert dc.fit_linear(spread(2)) is None


def test_the_centre_of_the_linear_form_does_not_change_what_it_predicts(monkeypatch):
    """Moving the centre is a reparametrisation: refitting the same noisy pairs about another centre predicts the same densities."""
    data = spread(15, b=3e-7, noise=0.002)
    at_120 = dc.fit_linear(data)
    expected = [dc.correct_density(at_120, p.rho_low, p.t_low, p.t_rt) for p in data]
    monkeypatch.setattr(dc, "T_CENTRE_K", 95.0)
    at_95 = dc.fit_linear(data)
    assert at_95.params != at_120.params
    for p, e in zip(data, expected):
        assert dc.correct_density(at_95, p.rho_low, p.t_low, p.t_rt) == pytest.approx(e, rel=1e-10)


def test_correction_inverts_the_expansion_and_a_non_positive_volume_factor_is_refused():
    p = pair(alpha=1.5e-4)
    assert dc.correct_density(dc.Fit("constant", (1.5e-4,), 1), p.rho_low, p.t_low, p.t_rt) == pytest.approx(p.rho_rt, rel=1e-12)
    with pytest.raises(ValueError):
        dc.correct_density(dc.Fit("constant", (-1.0,), 1), 1.7, 100.0, 293.0)


def test_a_correction_error_is_added_in_quadrature():
    assert dc.combined_error(0.03, 0.04) == pytest.approx(0.05)


# ------------------------------------------------------------------------------------------------------ the pairs
GOOD = {"key": "K", "space_group": "P 1", "z": 4, "low_code": "1", "rt_code": "2", "t_low": 100.0, "t_rt": 293.0, "rho_low": 1.75, "rho_rt": 1.7, "volume_ratio": 1.03}


@pytest.mark.parametrize("change,fragment", [
    ({"t_low": 170.0}, "low temperature"), ({"t_low": 79.9}, "low temperature"), ({"t_rt": 250.0}, "room temperature"), ({"t_rt": 310.0}, "room temperature"),
    ({"volume_ratio": 0.99}, "volume ratio"), ({"volume_ratio": 1.09}, "volume ratio"), ({"rho_low": 0.0}, "finite positive"),
    ({"rho_rt": float("nan")}, "finite positive"), ({"space_group": None}, "space group"), ({"key": ""}, "entity key"), ({"z": None}, "space group"),
])
def test_a_row_outside_the_rules_of_15_8_is_named_not_filtered(change, fragment):
    assert dc.pair_problem(GOOD) is None
    assert fragment in dc.pair_problem({**GOOD, **change})


def test_a_missing_field_is_a_problem_and_a_bad_file_is_refused_whole(tmp_path):
    assert dc.pair_problem({k: v for k, v in GOOD.items() if k != "rho_low"}) is not None
    f = tmp_path / "pairs.json"
    f.write_text(json.dumps([GOOD, {**GOOD, "key": "L", "t_rt": 250.0}]), encoding="utf-8")
    with pytest.raises(ValueError, match="room temperature"):
        dc.read_pairs(f)


def test_two_pairs_of_one_form_are_refused(tmp_path):
    f = tmp_path / "pairs.json"
    f.write_text(json.dumps([GOOD, {**GOOD, "low_code": "3"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="one form is one pair"):
        dc.read_pairs(f)
    f.write_text(json.dumps([GOOD, {**GOOD, "z": 8}]), encoding="utf-8")
    assert len(dc.read_pairs(f)) == 2


def test_the_inclusive_edges_of_every_window_are_admitted():
    for change in ({"t_low": 80.0}, {"t_low": 160.0}, {"t_rt": 273.0}, {"t_rt": 303.0}, {"volume_ratio": 1.0}, {"volume_ratio": 1.08}):
        assert dc.pair_problem({**GOOD, **change}) is None


# ------------------------------------------------------------------------------------------------------ the split
def test_pairs_are_split_by_the_entity_hash_and_a_forced_compound_goes_to_development():
    data = [pair(f"key-{i}", code=str(i)) for i in range(60)]
    parts = dc.split_pairs(data, {})
    assert sum(len(v) for v in parts.values()) == 60
    for name, ps in parts.items():
        assert all(vr.partition_for(p.key) == name for p in ps)
    forced_key = next(p.key for p in parts["holdout"])
    moved = dc.split_pairs(data, {forced_key: "an earlier survey"})
    assert forced_key in {p.key for p in moved["development"]}
    assert forced_key not in {p.key for p in moved["holdout"]}


def test_counts_state_the_entities_needed_and_whether_the_study_can_be_evaluated():
    few = dc.counts({"development": spread(30), "selection": spread(10, prefix="S"), "holdout": spread(dc.MIN_HELD_OUT_ENTITIES - 1, prefix="H")})
    assert few["evaluable"] is False and few["holdout"]["entities"] == dc.MIN_HELD_OUT_ENTITIES - 1
    enough = dc.counts({"development": [], "selection": [], "holdout": spread(dc.MIN_HELD_OUT_ENTITIES, prefix="H")})
    assert enough["evaluable"] is True
    assert enough["entities_in_all_partitions_needed_at_20_percent"] == math.ceil(dc.MIN_HELD_OUT_ENTITIES / 0.2)


def test_the_minimum_follows_the_derivation_in_section_13():
    assert dc.MIN_HELD_OUT_ENTITIES == math.ceil((3 * 1.96) ** 2)
    assert dc.UPPER_CEILING == pytest.approx(dc.MAE_CEILING * 4 / 3, abs=1e-12)


# ------------------------------------------------------------------------------------------------------ choosing a form
def test_the_linear_form_is_chosen_only_when_it_beats_the_constant_one():
    chosen = dc.develop(spread(30, b=4e-7), spread(12, b=4e-7, prefix="S"))
    assert chosen["chosen"] == "linear" and chosen["selection_mae"]["linear"] < chosen["selection_mae"]["constant"]
    tie = dc.develop(spread(30, b=0.0), spread(12, b=0.0, prefix="S"))
    assert tie["chosen"] == "constant"


def test_when_the_linear_form_cannot_be_fitted_the_constant_one_is_chosen():
    dev = [pair(f"K{i}", t_low=100.0, code=str(i)) for i in range(8)]
    out = dc.develop(dev, spread(5, prefix="S"))
    assert out["fits"]["linear"] is None and out["selection_mae"]["linear"] is None and out["chosen"] == "constant"


def test_choosing_never_reads_a_held_out_pair():
    """develop takes two lists; a held-out pair cannot reach it. Its signature is the contract."""
    import inspect

    assert list(inspect.signature(dc.develop).parameters) == ["development", "selection"]


# ------------------------------------------------------------------------------------------------------ the bar
def test_a_perfect_model_passes_with_enough_entities_and_is_not_evaluable_with_too_few():
    fit = dc.fit_constant(spread(20))
    full = dc.judge(fit, spread(dc.MIN_HELD_OUT_ENTITIES, prefix="H"))
    assert full["status"] == "PASS" and full["mae"] < 1e-9 and full["uncorrected_mae"] > 0.02
    short = dc.judge(fit, spread(dc.MIN_HELD_OUT_ENTITIES - 1, prefix="H"))
    assert short["status"] == "NOT_EVALUABLE" and "not relaxed" in short["reason"]
    assert short["mae"] is not None  # the numbers are still reported, labelled as not a verdict


def test_an_error_above_the_bar_fails_even_with_enough_entities():
    fit = dc.fit_constant(spread(20))
    out = dc.judge(fit, spread(dc.MIN_HELD_OUT_ENTITIES + 5, noise=0.04, prefix="H"))
    assert out["status"] == "FAIL" and out["mae"] > dc.MAE_CEILING


def test_a_point_estimate_inside_the_bar_with_an_interval_above_it_fails():
    """The upper end of the interval is part of the bar: a few large errors among many tiny ones pass on the mean and fail on the bound."""
    fit = dc.fit_constant(spread(20))
    held = spread(dc.MIN_HELD_OUT_ENTITIES, prefix="H")
    held[0] = pair("H0", t_low=85.0, rho_rt=1.5, noise=0.2, code="0")
    held[1] = pair("H1", t_low=90.0, rho_rt=1.51, noise=-0.2, code="1")
    out = dc.judge(fit, held)
    assert out["mae"] <= dc.MAE_CEILING < dc.UPPER_CEILING < out["interval"][1] and out["status"] == "FAIL"


def test_no_held_out_pair_is_not_evaluable_and_does_not_crash():
    out = dc.judge(dc.fit_constant(spread(5)), [])
    assert out["status"] == "NOT_EVALUABLE" and out["mae"] is None


def test_the_bootstrap_is_deterministic_and_resamples_entities_not_pairs():
    fit = dc.fit_constant(spread(20))
    held = spread(dc.MIN_HELD_OUT_ENTITIES, noise=0.01, prefix="H")
    errs = dc.errors(held, fit)
    assert dc.entity_bootstrap(held, errs) == dc.entity_bootstrap(held, errs)
    # one entity with three forms and one with a single form: resampling pairs could give a mix, resampling entities gives only these two means
    two = [pair("A", z=1.0, code="a1", rho_rt=1.5, noise=0.1), pair("A", z=2.0, code="a2", rho_rt=1.5, noise=0.1),
           pair("A", z=3.0, code="a3", rho_rt=1.5, noise=0.1), pair("B", rho_rt=1.5, noise=0.0, code="b")]
    lo, hi = dc.entity_bootstrap(two, [0.1, 0.1, 0.1, 0.0], resamples=2000)
    assert lo == pytest.approx(0.0, abs=1e-12) and hi == pytest.approx(0.1, abs=1e-12)


def test_the_interval_is_the_2_5_to_97_5_percentile_of_a_plain_resampling_loop():
    import numpy as np

    # errors that differ from entity to entity, or every percentile would be the same number
    held = [pair(f"H{i}", t_low=85.0 + i, rho_rt=1.5 + 0.01 * i, noise=0.003 * ((i * 7) % 11), code=str(i)) for i in range(40)]
    held.append(pair("H3", z=9.0, code="x", noise=0.05))
    errs = [abs(e) for e in dc.errors(held, dc.fit_constant(spread(20)))]
    keys = list(dict.fromkeys(p.key for p in held))  # first-seen order, the order dc.entity_bootstrap draws over
    per = {k: [e for p, e in zip(held, errs) if p.key == k] for k in keys}
    rng = np.random.default_rng(dc.BOOTSTRAP_SEED)
    draw = rng.integers(0, len(keys), size=(300, len(keys)))
    order = list(per)
    vals = [sum(sum(per[order[i]]) for i in row) / sum(len(per[order[i]]) for i in row) for row in draw]
    lo, hi = dc.entity_bootstrap(held, errs, resamples=300)
    assert (lo, hi) == pytest.approx(tuple(np.percentile(vals, [2.5, 97.5])), rel=1e-9)


def test_the_minimum_counts_entities_not_pairs():
    """Forms of one entity are not independent held-out units: many pairs from few keys is still too few."""
    fit = dc.fit_constant(spread(20))
    held = [pair(f"H{i % 5}", z=float(i + 1), code=str(i)) for i in range(dc.MIN_HELD_OUT_ENTITIES * 2)]
    assert len(held) >= dc.MIN_HELD_OUT_ENTITIES and len({p.key for p in held}) == 5
    assert dc.judge(fit, held)["status"] == "NOT_EVALUABLE"


def test_one_entity_gives_a_degenerate_interval():
    one = [pair("A", code="1"), pair("A", z=2.0, code="2")]
    lo, hi = dc.entity_bootstrap(one, [0.01, 0.03])
    assert lo == hi == pytest.approx(0.02)


def test_a_wrong_form_is_penalised_by_the_selection_it_is_judged_on():
    """The data have a strong temperature dependence; the constant form leaves a visible error the linear one does not."""
    held = spread(40, b=6e-7, prefix="H")
    constant = dc.judge(dc.fit_constant(spread(30, b=6e-7)), held)
    linear = dc.judge(dc.fit_linear(spread(30, b=6e-7)), held)
    assert linear["mae"] < constant["mae"] / 10


# ------------------------------------------------------------------------------------------------------ freeze, lock, holdout
@pytest.fixture
def study(tmp_path, monkeypatch):
    """A pairs file of synthetic pairs, a freeze made from it, and the git and hash probes pinned so the holdout can be refused for exactly one reason."""
    data = spread(60, noise=0.0, prefix="entity-")
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([as_row(p) for p in data]), encoding="utf-8")
    monkeypatch.setattr(dc, "file_hashes", lambda: {"a.py": "h1"})
    monkeypatch.setattr(dc, "git_commit", lambda: "c0ffee")
    monkeypatch.setattr(dc, "git_dirty", lambda: False)
    monkeypatch.setattr(dc._corpus(), "previously_examined_keys", dict)
    freeze = tmp_path / "results" / "freeze.json"
    dc.stage_freeze(pairs_file, freeze)
    return pairs_file, freeze, tmp_path / "results" / "holdout.json"


def test_the_freeze_records_the_choice_the_counts_and_the_hashes(study):
    _, freeze, _ = study
    frozen = json.loads(freeze.read_text(encoding="utf-8"))
    assert frozen["chosen"] in dc.FORMS and frozen["file_hashes"] == {"a.py": "h1"} and frozen["commit"] == "c0ffee"
    assert frozen["counts"]["development"]["pairs"] + frozen["counts"]["selection"]["pairs"] + frozen["counts"]["holdout"]["pairs"] == 60
    assert frozen["fits"]["constant"]["n"] == frozen["counts"]["development"]["pairs"]


def test_the_holdout_is_refused_without_confirmation_and_writes_nothing(study):
    pairs_file, freeze, out = study
    with pytest.raises(SystemExit, match="confirm-holdout-once"):
        dc.stage_holdout(freeze, pairs_file, out, confirmed=False)
    assert not out.exists() and not (freeze.parent / "holdout_scored.lock").exists()


def test_the_holdout_is_scored_once_and_a_second_attempt_is_refused(study):
    pairs_file, freeze, out = study
    first = dc.stage_holdout(freeze, pairs_file, out, confirmed=True)
    assert first["status"] in ("PASS", "NOT_EVALUABLE") and json.loads(out.read_text(encoding="utf-8")) == first
    assert (freeze.parent / "holdout_scored.lock").read_text(encoding="utf-8").endswith("at c0ffee\n")
    with pytest.raises(SystemExit, match="already scored"):
        dc.stage_holdout(freeze, pairs_file, out, confirmed=True)


def test_the_holdout_is_refused_when_a_frozen_file_changed(study, monkeypatch):
    pairs_file, freeze, out = study
    monkeypatch.setattr(dc, "file_hashes", lambda: {"a.py": "h2"})
    with pytest.raises(SystemExit, match="changed since the freeze"):
        dc.stage_holdout(freeze, pairs_file, out, confirmed=True)
    assert not (freeze.parent / "holdout_scored.lock").exists()


def test_the_holdout_is_refused_on_a_dirty_tree_and_the_lock_is_not_written(study, monkeypatch):
    pairs_file, freeze, out = study
    monkeypatch.setattr(dc, "git_dirty", lambda: True)
    with pytest.raises(SystemExit, match="uncommitted"):
        dc.stage_holdout(freeze, pairs_file, out, confirmed=True)
    assert not (freeze.parent / "holdout_scored.lock").exists()


def test_the_frozen_file_list_names_files_that_exist_and_this_module_is_among_them():
    assert "benchmarks/energetics_props/epb_density_correction.py" in dc.FROZEN_FILES
    for rel in dc.FROZEN_FILES:
        assert (ROOT / rel).is_file(), rel
    assert set(dc.file_hashes()) == set(dc.FROZEN_FILES)


# ------------------------------------------------------------------------------------------------------ the committed pairs
def test_the_committed_pairs_obey_the_rules_and_the_real_counts_are_what_the_study_must_report():
    """Counts only: no density of a committed pair is compared with anything here."""
    data = dc.read_pairs()  # refuses a pair outside 15.8
    assert len(data) == json.loads((DIR / "cod_corpus_summary.json").read_text(encoding="utf-8"))["pairs"]["pairs"]
    manifest = json.loads((DIR / "cod_split_manifest.json").read_text(encoding="utf-8"))
    parts = dc.split_pairs(data, corpus.previously_examined_keys())
    for name, ps in parts.items():
        for p in ps:
            if p.key in manifest:  # an entity with a resolved label is in the manifest; its partition must agree
                assert manifest[p.key] == name
    c = dc.counts(parts)
    assert c["development"]["pairs"] + c["selection"]["pairs"] + c["holdout"]["pairs"] == len(data)
    assert c["evaluable"] is (c["holdout"]["entities"] >= dc.MIN_HELD_OUT_ENTITIES)
