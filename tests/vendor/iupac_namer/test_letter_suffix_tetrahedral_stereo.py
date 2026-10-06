"""Tests for Stage 22 R22-C: letter-suffix tetrahedral R/S on fused parents.

R15-C had restricted tetrahedral stereo on fused ring parents to plain-
integer locants only (a follow-up extension to letter-suffix junction
locants like ``4a`` / ``6a`` / ``12a`` was reverted in R15-C-followup
because FDA-0605 — the galantamine derivative whose parent is
``[1]benzofuro[3a,3,2-ef][2]benzazepine`` — became OPSIN-unparseable
when the bridgehead ``12aS`` descriptor was emitted).

R22-C reopens the gate AND adds a post-assembly OPSIN-validation pass
in :func:`iupac_namer.engine.name_smiles`: the engine emits letter-
suffix R/S descriptors liberally, and when OPSIN cannot anchor one of
them the validator strips them and re-assembles.  This closes the ergot
/ lysergol family (parent ``indolo[4,3-fg]quinoline`` cleanly tolerates
``(6aR,9S)``) without regressing FDA-0605.

The 3 ergot rows are pinned via OPSIN round-trip. FDA-0605 (galantamine) was pinned to a
(6R)-only emit until naming round 25 found the cause: its curated locant table had 8a and 12a
swapped, so OPSIN rejected `12aS` and the validator stripped the letter-suffix pair. It is now
pinned to the full round-tripping `(4aS,6R,8aS)`.
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
    td = tempfile.mkdtemp(prefix="r22c_")
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


def _assert_roundtrips(smi: str) -> str:
    canon_in = _canon(smi)
    name = name_smiles(smi)
    assert name is not None and "NAMING ERROR" not in name, (
        f"naming error for {smi!r}: {name!r}"
    )
    rt = _opsin_rt(name)
    assert rt is not None, f"OPSIN rejected {name!r} from {smi!r}"
    assert _canon(rt) == canon_in, (
        f"round-trip mismatch for {smi!r}: emit={name!r} → "
        f"rt={_canon(rt)!r} expected={canon_in!r}"
    )
    return name


# --- Ergot / lysergol family: letter-suffix junction stereo MUST emit ---


def test_lysergol_S_emits_6aR_9S() -> None:
    """Lysergol (`OC[C@@H]1CN(C)[C@@H]2CC3=CNC4=CC=CC(C2=C1)=C34`) — both
    bridgeheads carry R/S.  C9 has a plain-integer locant; C6a is a
    letter-suffix junction.  Pre-R22-C the (6a) descriptor was dropped.
    OPSIN's `indolo[4,3-fg]quinoline` parent tolerates `6aR`, so the full
    `(6aR,9S)` prefix round-trips cleanly.
    """
    name = _assert_roundtrips("OC[C@@H]1CN(C)[C@@H]2CC3=CNC4=CC=CC(C2=C1)=C34")
    assert "6aR" in name and "9S" in name, f"expected (6aR,9S) in {name!r}"


def test_lysergic_acid_emits_6aR_9S() -> None:
    """Lysergic-acid analogue (`OC(=O)[C@@H]1CN(C)[C@@H]2...`) — same
    parent; the 9-CH2OH is replaced with 9-COOH so the parent is the
    direct `-9-carboxylic acid` rather than a `-9-yl` substituent.
    """
    name = _assert_roundtrips(
        "OC(=O)[C@@H]1CN(C)[C@@H]2CC3=CNC4=CC=CC(C2=C1)=C34"
    )
    assert "6aR" in name and "9S" in name, f"expected (6aR,9S) in {name!r}"


def test_lysergol_C9_inverted_emits_6aR_9R() -> None:
    """Same lysergol scaffold with C9 inverted — C6a stays R, C9 flips
    to R.  Confirms the descriptor on the letter-suffix locant is the
    correct one (not just any letter-suffix R/S that happened to round-
    trip).
    """
    name = _assert_roundtrips("OC[C@H]1CN(C)[C@@H]2CC3=CNC4=CC=CC(C2=C1)=C34")
    assert "6aR" in name and "9R" in name, f"expected (6aR,9R) in {name!r}"


# --- FDA-0605: galantamine keeps (4aS,6R,8aS) (naming round 25) ---


def test_fda_0605_galantamine_keeps_its_letter_suffix_stereo() -> None:
    """FDA-0605 is galantamine, whose parent `[1]benzofuro[3a,3,2-ef][2]benzazepine` was once said not to tolerate `12aS` / `4aS` in OPSIN.

    That was a defect in the curated locant table, not in OPSIN: it had the quaternary carbon as 12a and the aromatic carbon beside the CH2-N
    as 8a, the reverse of OPSIN's numbering (`8a-chloro-` is a valency error; `12a-chloro-` is the aromatic carbon). With the two swapped back
    the name round-trips exactly, and it is PubChem's published descriptor set for natural galantamine, `(4aS,6R,8aS)`. Before round 25 the
    validator stripped everything but `(6R)`; this test used to REQUIRE that.
    """
    name = _assert_roundtrips("COc1ccc2c3c1O[C@H]1C[C@@H](O)C=C[C@@]31CCN(C)C2")
    assert name.startswith("(4aS,6R,8aS)-3-methoxy-11-methyl"), f"expected (4aS,6R,8aS) in {name!r}"
    assert "12a" not in name, f"the old, wrong locant came back: {name!r}"
