"""The strategy a caller passes is the strategy every part of the call uses.

Naming round 4 (A11). Eleven helpers used to build their own
``IUPACCanonical()`` whenever they were not handed one, and the session cache
key held no strategy, so ``name_smiles(smiles, strategy=X)`` changed the main
search while those helpers (radicals, organometallics, pre-validation, the
oxoacid composers) still decided with the default. See
``openchem.vendor.iupac_namer.strategy.active_strategy``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from openchem.vendor.iupac_namer.engine import name_smiles
from openchem.vendor.iupac_namer.strategy import (
    IUPACCanonical,
    active_strategy,
    default_strategy,
    using_strategy,
)
from openchem.vendor.iupac_namer.types import NamingSession, OutputForm

SRC = Path(__file__).resolve().parents[1] / "src" / "openchem"


class _Probe(IUPACCanonical):
    """IUPACCanonical under another identity, so a call made on the default
    instead of on this one is visible."""

    def cache_key(self) -> str:
        return "probe"


# One molecule per kind of helper that used to build its own strategy:
# a carbon radical (the -yl route), an undersubstituted metalloid radical, an
# organometallic, a radical cation (pre-validation) and an ordinary molecule.
_HELPER_CASES = [
    "C[CH2]",
    "[SiH2]c1ccccc1",
    "C[Mg]Br",
    "c1ccc(cc1)[NH2+]",
    "OC(=O)c1ccccc1",
    "CN(O)O",  # methylazonous acid: the oxoacid composer names its organyl
]


def _strategy_types_used(monkeypatch, smiles: str, strategy) -> set[str]:
    seen: set[str] = set()
    original = IUPACCanonical.interpretation_query

    def recording(self, mol):
        seen.add(type(self).__name__)
        return original(self, mol)

    monkeypatch.setattr(IUPACCanonical, "interpretation_query", recording)
    try:
        name_smiles(smiles, strategy=strategy)
    finally:
        monkeypatch.setattr(IUPACCanonical, "interpretation_query", original)
    return seen


@pytest.mark.parametrize("smiles", _HELPER_CASES)
def test_every_decision_uses_the_strategy_passed_in(monkeypatch, smiles):
    used = _strategy_types_used(monkeypatch, smiles, _Probe())
    assert used, "the probe saw no naming decision at all"
    assert used == {"_Probe"}, f"{smiles}: decisions also made on {used - {'_Probe'}}"


# The helpers that took ``strategy=None`` and built their own. Measured over
# both corpora (248 molecules) no caller ever omitted the strategy, so the
# pipeline tests above cannot reach these fallbacks: they are called here
# directly, the way a new caller would, with a probe bound.
_FALLBACK_HELPERS = [
    ("engine", "_name_ring_imino_amide", "CC(=O)N=c1sccn1C"),
    ("engine", "_name_lambda_locant_chain", "C[C]C"),
    ("engine", "_name_simple_alkyl_x_radical", "CC[O]"),
    ("engine", "_name_trisubstituted_metalloid_radical", "C[Si](C)C"),
    ("engine", "_name_undersubstituted_metalloid_radical", "[SiH2]c1ccccc1"),
    ("engine", "_name_carbon_radical_via_yl", "F[C]=C(F)F"),
    ("chalcogen", "compute_name", "CS(=O)(=S)O"),
]


@pytest.mark.parametrize("module,func,smiles", _FALLBACK_HELPERS)
def test_a_helper_called_without_a_strategy_uses_the_bound_one(monkeypatch, module, func, smiles):
    from rdkit import Chem

    from openchem.vendor.iupac_namer import engine
    from openchem.vendor.iupac_namer.perception.fg import chalcogen_acid_modifiers

    helper = getattr({"engine": engine, "chalcogen": chalcogen_acid_modifiers}[module], func)
    seen: set[str] = set()
    original = IUPACCanonical.interpretation_query

    def recording(self, mol):
        seen.add(type(self).__name__)
        return original(self, mol)

    monkeypatch.setattr(IUPACCanonical, "interpretation_query", recording)
    with using_strategy(_Probe()):
        result = helper(Chem.MolFromSmiles(smiles))
    assert result, f"{func} declined {smiles}, so this row tests nothing"
    assert seen == {"_Probe"}, f"{func}: decisions made on {seen}"


def test_x_then_y_then_x_gives_each_call_its_own_strategy(monkeypatch):
    smiles = "C[CH2]"
    first = _strategy_types_used(monkeypatch, smiles, _Probe())
    second = _strategy_types_used(monkeypatch, smiles, None)
    third = _strategy_types_used(monkeypatch, smiles, _Probe())
    assert (first, second, third) == ({"_Probe"}, {"IUPACCanonical"}, {"_Probe"})
    assert active_strategy() is default_strategy(), "the binding leaked out of the call"


@pytest.mark.parametrize("smiles", _HELPER_CASES)
def test_every_cache_entry_of_a_call_is_keyed_by_its_strategy(monkeypatch, smiles):
    """Helpers open sessions of their own and recurse with a session in hand,
    which does not rebind; only the binding at ``name_smiles`` keeps their
    cache entries under the caller's strategy."""
    keys: list[tuple] = []
    original = NamingSession._make_key

    def recording(self, *args, **kwargs):
        key = original(self, *args, **kwargs)
        keys.append(key)
        return key

    monkeypatch.setattr(NamingSession, "_make_key", recording)
    name_smiles(smiles, strategy=_Probe())
    assert keys, "no cache traffic, so this row tests nothing"
    assert {k[0] for k in keys} == {"probe"}


def test_the_session_cache_key_carries_the_strategy():
    session = NamingSession()
    with using_strategy(_Probe()):
        probe_key = session._make_key("CCO", OutputForm.STANDALONE, (), None)
    default_key = session._make_key("CCO", OutputForm.STANDALONE, (), None)
    assert probe_key != default_key
    assert "probe" in probe_key and "iupac" in default_key


def test_a_strategy_cannot_be_changed_after_creation():
    with pytest.raises(AttributeError):
        default_strategy().anything = 1


_CONSTRUCTION = re.compile(r"\bIUPACCanonical\(\)")


def test_no_module_builds_its_own_strategy():
    """Only strategy.py may construct one; everything else asks for the
    active strategy (engine) or the default (the app). Comments are skipped,
    so the rule can be explained where it applies."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "strategy.py" and path.parent.name == "iupac_namer":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if _CONSTRUCTION.search(code):
                offenders.append(f"{path.relative_to(SRC)}:{lineno}")
    assert not offenders, offenders
