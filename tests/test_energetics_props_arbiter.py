"""The computed gas-phase enthalpy arbiter's pure part (`benchmarks/energetics_props/arbiter/arbiter_core.py`).

Held: every scheme conserves atoms, bond types and functional-group counts (so it is isodesmic, not just balanced); the
arithmetic that turns a reaction enthalpy into a formation enthalpy is the inverse of the one that builds it (a validation
scheme fed the experimental values returns the experimental value); the ensemble average and the uncertainty rule behave as the
plan says. No engine runs here.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "benchmarks" / "energetics_props" / "arbiter"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("epb_arbiter_core", DIR / "arbiter_core.py")


@pytest.mark.parametrize("scheme", sorted(core.SCHEMES))
def test_every_scheme_is_isodesmic(scheme):
    assert core.balance(scheme) == {"atoms": True, "bonds": True, "groups": True}


def test_a_reaction_that_changes_the_bonds_is_caught():
    core.SCHEMES["_bad"] = {"target": "pentaerythritol", "left": {"methane": 4}, "right": {"neopentane": 1, "ethane": 4}}
    try:
        assert not core.balance("_bad")["atoms"]
    finally:
        del core.SCHEMES["_bad"]


@pytest.mark.parametrize("scheme", [s for s in sorted(core.SCHEMES) if s.endswith("/V")])
def test_a_validation_scheme_fed_experiment_returns_experiment(scheme):
    spec = core.SCHEMES[scheme]
    target = spec["target"]
    reactants, products = core._sides(spec)
    # the reaction enthalpy the experimental values would give
    dh = sum(k * core.REFERENCES[n][1] for n, k in products.items()) - sum(k * core.REFERENCES[n][1] for n, k in reactants.items())
    value, _ = core.reaction_to_formation(scheme, dh)
    assert value == pytest.approx(core.REFERENCES[target][1], abs=1e-9)


def test_a_reactant_target_scheme_inverts_correctly():
    # pretend the target had a known value and build the reaction enthalpy from it
    known = -900.0
    spec = core.SCHEMES["pentaerythritol/A"]
    products = sum(k * core.REFERENCES[n][1] for n, k in spec["right"].items())
    reactants = sum(k * core.REFERENCES[n][1] for n, k in spec["left"].items()) + known
    value, u = core.reaction_to_formation("pentaerythritol/A", products - reactants)
    assert value == pytest.approx(known)
    # neopentane once, methanol four times, methane four times: each reference uncertainty times its coefficient, in quadrature
    assert u == pytest.approx(math.sqrt((1 * 0.38) ** 2 + (4 * 0.14) ** 2 + (4 * 0.042) ** 2))


def test_boltzmann_weights_sum_to_one_and_favour_the_lowest():
    w = core.boltzmann_weights([0.0, 2.0, 10.0])
    assert sum(w) == pytest.approx(1.0)
    assert w[0] > w[1] > w[2]
    assert core.boltzmann_weights([5.0, 5.0]) == [0.5, 0.5]


def test_ensemble_enthalpy_is_the_population_weighted_enthalpy():
    # two conformers, equal free energy: the plain mean of their enthalpies
    assert core.ensemble_enthalpy([10.0, 20.0], [0.0, 0.0]) == pytest.approx(15.0)
    # a conformer 50 kJ/mol higher in G contributes nothing
    assert core.ensemble_enthalpy([10.0, 20.0], [0.0, 50.0]) == pytest.approx(10.0, abs=1e-6)


def test_the_uncertainty_rule_and_its_floor():
    c = core.combine_schemes(-770.0, -780.0, 0.5, 0.6, 3.0)
    assert c["value"] == pytest.approx(-775.0)
    assert c["spread"] == pytest.approx(5.0)
    assert c["u"] == pytest.approx(math.sqrt(25 + 0.36 + 9))
    assert c["expanded"] == pytest.approx(2 * c["u"])
    assert core.validation_floor([0.5, -0.4, 0.3]) == 3.0          # small errors do not buy a number below the floor
    assert core.validation_floor([5.0, -5.0]) == pytest.approx(5.0)
    assert core.validation_floor([]) == 3.0


def test_a_sublimation_row_is_consistent_only_inside_the_expanded_band():
    assert core.consistent(-776.0, 10.0, -776.7)
    assert core.consistent(-776.0, 10.0, -786.0)
    assert not core.consistent(-776.0, 10.0, -789.2)


def test_the_references_carry_a_source_and_the_questions_carry_none():
    for name, (smiles, value, u, source) in core.REFERENCES.items():
        assert smiles and source
        assert (value is None) == (u is None), name
    assert core.REFERENCES["pentaerythritol"][1] is None and core.REFERENCES["nibtn"][1] is None
