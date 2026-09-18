"""Tests for Stage 21 R21-A: aryl ring with heavy-atom substituent
(``[BiH2][c]1ccccc1`` — phenylbismuthane and similar).

Pre-fix: ``[BiH2][c]1ccccc1`` (audit row from
opsin_audit_substituents_raw.csv) emitted ``(bismuthanyl)cyclohexane``
— silently dropping the aromatic-ring perception when the carved ring
contained a ``[c]`` (no-implicit-H aromatic C, where the heavy
substituent had attached).

Root cause: ``ring_naming/common.py::_normalize_nh_fragment`` parsed
the carved ring fragment ``c1c[c]ccc1`` directly via ``MolFromSmiles``;
RDKit preserves the ``noImplicit`` property on the bracketed ``[c]``
atom, so the canonical SMILES of the extracted ring became
``[c]1ccccc1`` (NOT ``c1ccccc1``).  The retained-name lookup keys on
``c1ccccc1`` and missed; ``name_systematic_monocyclic`` then took the
"fully saturated" branch (no explicit double bonds in aromatic rings)
and emitted ``cyclohexane``.

Phenylsilane (``[SiH3]c1ccccc1``) doesn't trigger this — RDKit
canonicalises the Si-attached aromatic C as ``c`` (no brackets).
The bracket-vs-no-bracket asymmetry on aromatic ring atoms is an
RDKit canonicalisation idiosyncrasy that tracks with the substituent
element family.

R21-A: rewrite ``[c]`` → ``c`` (and ``[C]`` → ``C``) in the carved
ring fragment SMILES before the parse.  The rewrite gives RDKit a
chance to re-add the implicit H on the formerly-substituted aromatic
C, restoring the canonical match against the curated benzene entry.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from rdkit import Chem
from py2opsin import py2opsin

from openchem.vendor.iupac_namer.engine import name_smiles


def _opsin_rt(name: str) -> str | None:
    if not name:
        return None
    td = tempfile.mkdtemp(prefix="r21a_")
    cwd = os.getcwd()
    try:
        os.chdir(td)
        return py2opsin(name)
    except Exception:
        return None
    finally:
        os.chdir(cwd)
        try:
            shutil.rmtree(td)
        except Exception:
            pass


def _canon(s: str | None) -> str | None:
    m = Chem.MolFromSmiles(s) if s else None
    return Chem.MolToSmiles(m) if m else None


# THE PARENT IN THESE TWO NAMES CHANGED IN NAMING ROUND 3, and the strings
# below were updated rather than the engine.
#
# R21-A is about RING PERCEPTION: the carved ring must come back as benzene
# and not as cyclohexane. It asserted the whole emitted name to check that,
# so it also pinned the parent choice incidentally -- and that choice was
# wrong. `(silyl)benzene` makes the carbocycle the parent; BlueBookV2.pdf
# p. 375 P-44.1.2 reads "The senior parent structure, whether cyclic or
# acyclic, has the senior atom in accordance with the seniority of classes
# ... N > P > As > Sb > Bi > Si > Ge > Sn > Pb > B > Al > Ga > In > Tl > O >
# S > Se > Te > C. This criterion is applied to select the senior atom in
# parents AND TO CHOOSE BETWEEN RINGS AND CHAINS." Carbon is last in that
# order, and P-44.1.2.1 adds that "a single senior atom is sufficient". The
# same page gives Si(CH3)4 -> tetramethylsilane (PIN) "(Si is senior to C)".
#
# So the silane is the parent and `phenylsilane` is the name. Both forms
# round-trip, which is why nothing caught it: the round trip cannot see
# preference. The assertions now name the subject (the ring was perceived as
# benzene, not cyclohexane) separately from the full string, so a future
# parent change is not mistaken for an R21-A regression.


def test_phenylbismuthane_roundtrips() -> None:
    """The exact audit row: ``[BiH2][c]1ccccc1``."""
    smi = "[BiH2][c]1ccccc1"
    name = name_smiles(smi)
    assert name == "phenylbismuthane", f"got {name!r}"
    assert "cyclohex" not in name, "R21-A regression: the ring became cyclohexane"
    rt = _opsin_rt(name)
    assert _canon(rt) == _canon(smi)


def test_phenylsilane_unaffected() -> None:
    """Control: phenylsilane reaches the standard path (RDKit canonicalises
    Si-attached aromatic C as ``c``, no brackets, so the [c] normalisation is
    a no-op here)."""
    name = name_smiles("[SiH3]c1ccccc1")
    assert name == "phenylsilane", f"got {name!r}"
    assert "cyclohex" not in name, "R21-A regression: the ring became cyclohexane"


def test_benzene_unaffected() -> None:
    """Control: bare benzene unchanged."""
    assert name_smiles("c1ccccc1") == "benzene"


def test_naphthalene_unaffected() -> None:
    """Control: naphthalene (fused aromatic, junctions have 0 H natively)
    unchanged — the [c] normalisation only affects atoms that lost
    a substituent during carving, not native 0-H junctions which already
    use lowercase c in canonical form.
    """
    assert name_smiles("c1ccc2ccccc2c1") == "naphthalene"


def test_cyclohexane_unaffected() -> None:
    """Control: actual cyclohexane (saturated) still emits cyclohexane."""
    assert name_smiles("C1CCCCC1") == "cyclohexane"
