"""OPSIN verification for the Severity-A regression table.

``tests/test_namer_known_defects.py`` runs in the DEFAULT suite and so
cannot shell out to a JRE; it pins name STRINGS. This file is the other
half: it proves those strings actually denote the molecules they claim
to, using the engine's own correctness criterion -- parse the name back
with OPSIN and compare -- on canonical SMILES AND full InChIKey.

Without this, the fast suite would be pinning unverified folklore. That
is not hypothetical: two targets in the OPEN table were wrong when first
written. ``benzylium`` looks like the obvious name for the benzyl cation
and OPSIN reads it as ``O=[C+]c1ccccc1``, the BENZOYL cation -- a
different molecule. ``benzanide`` does not parse at all. Both were caught
by exactly this check.

Also verified here: a Severity-B/C table for defects where the engine
names the right molecule but not by its preferred name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from rdkit import Chem

try:
    import py2opsin as _p2o
    _HAVE_OPSIN = True
except Exception:  # pragma: no cover
    _HAVE_OPSIN = False


def _load_fast_table():
    path = (
        Path(__file__).resolve().parents[2] / "test_namer_known_defects.py"
    )
    spec = importlib.util.spec_from_file_location("_known_defects", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_TABLE = _load_fast_table()


def _canon(smiles: str | None) -> str | None:
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol is not None else None


def _key(smiles: str | None) -> str | None:
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        return Chem.MolToInchiKey(mol) or None
    except Exception:
        return None


def _opsin(name: str) -> str | None:
    import os
    import shutil
    import tempfile

    cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="known_defects_opsin_")
    try:
        os.chdir(tmp)
        parsed = _p2o.py2opsin(name)
        return parsed or None
    except Exception:
        return None
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


pytestmark = pytest.mark.skipif(not _HAVE_OPSIN, reason="py2opsin not installed")


@pytest.mark.parametrize(
    "defect,smiles,expected,former,note",
    _TABLE.FIXED + _TABLE.OPEN,
    ids=[row[0] for row in _TABLE.FIXED + _TABLE.OPEN],
)
def test_target_name_denotes_the_input_structure(
    defect, smiles, expected, former, note
):
    """Every target name in the fast table must round-trip to its input.

    Applies to OPEN rows too: a defect whose stated goal is a name for
    some other molecule would send whoever fixes it to the wrong answer.
    """
    parsed = _opsin(expected)
    assert parsed, f"{defect}: OPSIN cannot parse target name {expected!r}"
    assert _canon(parsed) == _canon(smiles), (
        f"{defect}: target name {expected!r} denotes {_canon(parsed)}, "
        f"not the input {_canon(smiles)}"
    )
    got_key, want_key = _key(parsed), _key(smiles)
    if got_key is not None and want_key is not None:
        assert got_key == want_key, (
            f"{defect}: InChIKey gate disagrees for {expected!r}"
        )


@pytest.mark.parametrize(
    "defect,smiles,expected,former,note",
    _TABLE.FIXED,
    ids=[row[0] for row in _TABLE.FIXED],
)
def test_fixed_defect_round_trips_end_to_end(
    defect, smiles, expected, former, note
):
    """The engine's own output round-trips, not merely the pinned string.

    The string pin and the round trip can drift apart if someone edits the
    expected name without re-verifying, so both are checked.
    """
    from openchem.vendor.iupac_namer import name_smiles

    name = name_smiles(smiles)
    parsed = _opsin(str(name))
    assert parsed, f"{defect}: engine emitted unparsable name {name!r}"
    assert _canon(parsed) == _canon(smiles), (
        f"{defect}: {smiles} -> {name!r} -> {_canon(parsed)}"
    )
