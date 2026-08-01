"""Severity-A regression suite for the vendored IUPAC engine.

SEVERITY A MEANS THE ENGINE NAMED THE WRONG MOLECULE. Not a debatable
choice between two valid names -- a name that denotes something else.
The benzyl cation came out as `methylbenzene`, which is toluene; the
phthaloyl dication as `1,2-bis(oxomethyl)benzene`, which is
phthalaldehyde. Both were emitted with complete confidence and nothing in
the output to suggest a problem.

That is why this file lives in the DEFAULT test suite rather than in
tests/vendor/, which is excluded from the normal run because it takes
seven minutes. A wrong-molecule regression must surface on every run, not
only when somebody remembers to invoke the vendored suite. Everything
here is a single `name_smiles` call, so the whole file costs a second or
two.

Each expected name below was verified through the engine's own
correctness criterion -- parse it back with OPSIN and confirm it yields
the input structure, checked on canonical SMILES AND full InChIKey. That
verification needs a JRE, so it lives in the vendored suite; what is
pinned here is the resulting string, which needs nothing but RDKit.

`former` records what the engine used to emit. It is not decoration: when
one of these regresses, the failure message shows the wrong answer it
regressed to, which is usually enough to identify the cause without
bisecting.

OPEN defects are marked xfail(strict=True). If one starts passing the
test FAILS, which is the intended alarm -- it means somebody fixed it and
this file needs updating rather than silently drifting out of date.
"""

from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer import name_smiles

# (defect id, SMILES, correct name, name formerly emitted, what went wrong)
FIXED: list[tuple[str, str, str, str, str]] = [
    # --- D-001: ring polyacylium named as its neutral aldehyde ----------
    # _diacid_name_to_polyacylium had no rule for a "-carboxylic acid"
    # parent, returned None, and None routes to the plan-search
    # neutralizer instead of failing.
    ("D-001a", "O=[C+]c1ccccc1[C+]=O", "benzene-1,2-dicarbonylium",
     "1,2-bis(oxomethyl)benzene", "charge dropped; phthalaldehyde"),
    ("D-001b", "O=[C+]c1cccc([C+]=O)c1", "benzene-1,3-dicarbonylium",
     "1,3-bis(oxomethyl)benzene", "charge dropped"),
    ("D-001c", "O=[C+]c1ccc([C+]=O)cc1", "benzene-1,4-dicarbonylium",
     "1,4-bis(oxomethyl)benzene", "charge dropped"),
    ("D-001d", "O=[C+]C1CCCCC1[C+]=O", "cyclohexane-1,2-dicarbonylium",
     "1,2-bis(oxomethyl)cyclohexane", "charge dropped"),
    ("D-001e", "O=[C+]c1ccc2ccccc2c1[C+]=O", "naphthalene-1,2-dicarbonylium",
     "1,2-bis(oxomethyl)naphthalene", "charge dropped"),
    ("D-001f", "O=[C+]c1ccncc1[C+]=O", "pyridine-3,4-dicarbonylium",
     "3,4-bis(oxomethyl)pyridine", "charge dropped"),
    ("D-001g", "O=[C+]c1cc([C+]=O)cc([C+]=O)c1", "benzene-1,3,5-tricarbonylium",
     "1,3,5-tris(oxomethyl)benzene", "charge dropped (trication)"),

    # --- D-005: -ylium / -ide locant hardcoded to 1 ---------------------
    # _render_simple_carbon assumed the charged carbon is always at
    # position 1. True for the four terminal-charge audit compounds it was
    # written against, false for everything else -- and because no test
    # exercised a non-terminal charge, the OPSIN round-trip never caught
    # it. Now the engine is asked to name the skeleton as a SUBSTITUENT
    # anchored at the charged atom, so its own parent selection and
    # numbering decide.
    ("D-005a", "C[CH+]C", "propan-2-ylium",
     "propan-1-ylium", "charge moved to C1; isopropyl vs n-propyl cation"),
    ("D-005b", "C[C-](C)C", "2-methylpropan-2-ide",
     "isobutan-1-ide", "charge moved to a methyl carbon"),
    ("D-005c", "C[C+](C)C", "2-methylpropan-2-ylium",
     "isobutan-1-ylium", "charge moved to a methyl carbon"),
    ("D-005d", "[CH2+]C1CCCCC1", "cyclohexylmethan-1-ylium",
     "methylcyclohexan-1-ylium", "charge moved onto the ring"),
    ("D-005e", "[CH2-]C1CCCCC1", "cyclohexylmethan-1-ide",
     "methylcyclohexan-1-ide", "charge moved onto the ring"),
    ("D-005f", "[CH2+]CC(C)C", "3-methylbutan-1-ylium",
     "2-methylbutan-1-ylium", "branch locant numbered from the wrong end"),
    ("D-005g", "CC[CH+]CC", "pentan-3-ylium",
     "pentan-1-ylium", "charge moved to C1"),
    ("D-005h", "[CH+]1CCCC(C)C1", "3-methylcyclohexan-1-ylium",
     "methylcyclohexan-1-ylium", "substituent locant dropped"),
    ("D-005i", "CC(C)[CH+]C(C)C", "2,4-dimethylpentan-3-ylium",
     "2,4-dimethylpentan-1-ylium", "charge moved to C1"),

    # --- D-002 family: charge next to unsaturation or aromaticity ------
    # _classify_simple_carbon_charge required every atom non-aromatic and
    # every bond single, so it claimed nothing here -- and an unclaimed
    # charge is not left alone, it falls through to the plan-search
    # neutralizer. The restriction bought nothing: the renderer drives the
    # engine in substituent mode, which names these skeletons perfectly
    # well (phenylmethan-1-yl, prop-2-en-1-yl, ethen-1-yl).
    ("D-002", "[CH2+]c1ccccc1", "phenylmethan-1-ylium",
     "methylbenzene", "charge dropped; toluene"),
    ("D-011", "[CH2-]c1ccccc1", "phenylmethan-1-ide",
     "methylbenzene", "charge dropped; toluene"),
    ("D-009", "[CH2+]C=C", "prop-2-en-1-ylium",
     "prop-1-ene", "charge dropped; propene"),
    ("D-012", "[CH2-]C=C", "prop-2-en-1-ide", "prop-1-ene", "charge dropped"),
    ("D-010", "[CH+]=C", "ethen-1-ylium", "ethene", "charge dropped"),
    ("D-014", "[CH+](c1ccccc1)c1ccccc1", "diphenylmethan-1-ylium",
     "(phenylmethyl)benzene", "charge dropped; diphenylmethane"),
    ("D-017", "[CH2+]C#C", "prop-2-yn-1-ylium",
     "prop-1-yne", "charge dropped; propyne"),

    # --- D-003: aromatic ring carbanion -------------------------------
    # No classifier claimed these, so the plan search neutralized them --
    # the phenyl anion lost its charge AND its aromaticity. An aromatic
    # ring carbanion needs the RING parent's numbering, which is exactly
    # why _classify_simple_carbon_charge refuses an aromatic charged atom.
    ("D-003", "c1ccc[c-]c1", "benzen-1-ide",
     "cyclohexane", "charge AND aromaticity dropped"),
    ("D-003b", "[c-]1cccc2ccccc12", "naphthalen-1-ide",
     "(unclaimed)", "generalises to fused rings"),
    ("D-003c", "[c-]1ccc2ccccc2c1", "naphthalen-2-ide",
     "(unclaimed)", "locant comes from the engine's own numbering"),
    ("D-003d", "[c-]1cccnc1", "pyridin-3-ide",
     "(unclaimed)", "generalises to heteroaromatic rings"),
    ("D-003e", "[c-]1ccccn1", "pyridin-2-ide", "(unclaimed)", "as above"),

    # --- D-004: guanidinium -------------------------------------------
    # _classify_amidinium requires the third substituent on the central
    # carbon to be a CARBON, so guanidinium -- whose third substituent is
    # another amino nitrogen -- fell through to the neutralizer.
    ("D-004", "[NH2+]=C(N)N", "guanidinium",
     "iminomethane-1,1-diamine", "charge dropped"),

    # --- D-016: azide -------------------------------------------------
    # No classifier claimed the N3 chain, so the plan search produced
    # "diiminoazanium" -- which denotes N=[N+]=N, a CATION. The same one
    # name came out for the anion (q=-1) AND its conjugate acid (q=0),
    # so one confident answer covered three different species and matched
    # none of them. Azide belongs with the other retained pseudohalides
    # (cyanide, thiocyanate, cyanate, isocyanate, isothiocyanate) in the
    # curated inorganic table, and simply was not there.
    ("D-016", "[N-]=[N+]=[N-]", "azide",
     "diiminoazanium", "named a cation for an anion"),
    ("D-016b", "N=[N+]=[N-]", "hydrogen azide",
     "diiminoazanium", "same wrong name as its conjugate base"),
    ("D-016c", "[Na+].[N-]=[N+]=[N-]", "sodium azide",
     "sodium diiminoazanium", "salt path inherited the wrong ion name"),

    # --- non-regression: the rest of the pseudohalide block ------------
    ("D-016x", "[C-]#N", "cyanide", "cyanide", "unchanged"),
    ("D-016y", "N#C[S-]", "thiocyanate", "thiocyanate", "unchanged"),
    ("D-016z", "[N-]=C=S", "isothiocyanate", "isothiocyanate", "unchanged"),
    # Organic azides never went through the ion table -- the azido
    # substituent prefix is a separate path and was always correct.
    ("D-016w", "CCN=[N+]=[N-]", "azidoethane", "azidoethane", "unchanged"),

    # --- non-regression: delocalised aromatic anions the ring-carbanion
    # classifier must NOT steal. Cyclopentadienide keeps its hydrogen and
    # is a delocalised pi anion with a retained name; benzenide is a sigma
    # carbanion with the hydrogen removed. Gating on "no H on the charged
    # carbon" is what separates them -- written as [cH-]1cccc1 the
    # cyclopentadienide is closed-shell, so a radical test does not.
    ("D-003x", "[cH-]1cccc1", "cyclopentadienide", "cyclopentadienide",
     "unchanged"),
    # Ferrocene reaches the ring-carbanion classifier one fragment at a
    # time, so a substituted cyclopentadienide arrives on its own. Two
    # cheaper gates were tried and both let it through: "no radical" (it
    # is closed-shell) and "no hydrogen on the charged carbon" (a chlorine
    # occupies that position rather than a proton having left it). With
    # the refusal guard in place, over-claiming here raised instead of
    # mis-naming -- louder, but still a regression.
    ("D-003y", "c1cc[cH-]c1.[Fe+2].c1cc[cH-]c1", "ferrocene", "ferrocene",
     "unchanged"),

    # --- non-regression: retained ring cations the relaxed gate must NOT
    # steal. These carry retained -ylium PINs owned by the retained-ring
    # lookup; claiming them in the simple-carbon classifier would quietly
    # replace a correct retained name with the systematic one
    # ("phenylium" -> "benzene-1-ylium"). A Kekule-written ring cation is
    # not flagged aromatic by RDKit, so the guard is ring saturation, not
    # the aromatic flag.
    ("D-002x", "[C+]1=CC=CC=C1", "phenylium", "phenylium", "unchanged"),
    ("D-002y", "[O+]1=CC=CC=C1", "pyrylium", "pyrylium", "unchanged"),
    ("D-002z", "[C+](C)=O", "acetylium", "acetylium", "unchanged"),

    # --- non-regression: shapes the locant fix must NOT disturb ---------
    ("D-005j", "[CH2+]C", "ethan-1-ylium", "ethan-1-ylium", "unchanged"),
    ("D-005k", "[CH2+]CCCC", "pentan-1-ylium", "pentan-1-ylium", "unchanged"),
    ("D-005l", "[CH+]1CCCCC1", "cyclohexan-1-ylium", "cyclohexan-1-ylium",
     "unchanged"),
    ("D-005m", "[CH3+]", "methylium", "methylium", "unchanged"),
    ("D-005n", "[CH3-]", "methanide", "methanide", "unchanged"),
]

# Measured, reproduced, not yet fixed. Every one of these currently names
# the WRONG MOLECULE. The common shape is a charged carbon next to
# unsaturation or aromaticity, which no classifier claims, so the charge
# is dropped and the neutral skeleton is named.
OPEN: list[tuple[str, str, str, str, str]] = [
    # NB "benzylium" would be the obvious target for a benzyl cation and is
    # WRONG: OPSIN reads it as O=[C+]c1ccccc1, the BENZOYL cation. Every
    # target here is checked by parsing it back
    # (tests/vendor/iupac_namer/test_known_defects.py), precisely to catch
    # that class of mistake before it becomes someone's goal.

    # Heteroatom-containing skeletons: the simple-carbon classifier gate
    # is all-carbon, so anything with N/O/S stays unclaimed. Widening it
    # means teaching the renderer about heteroatom parents, a larger
    # change.
    ("D-013", "[CH+]=O", "oxomethylium", "oxomethane", "charge dropped"),
    ("D-018", "[CH2+]c1ccncc1", "pyridin-4-ylmethan-1-ylium",
     "4-methylpyridine", "charge dropped; heteroaryl skeleton"),
    # Charge relocated rather than dropped.
    ("D-015", "[n-]1cccc1", "pyrrol-1-ide",
     "1H-pyrrol-2-ide", "charge relocated from N to C"),
    # Zwitterion: the engine protonates the carbanion half and keeps the
    # cation, so neutral CH2N2 comes out as the CH3N2+ methyldiazonium
    # CATION -- an invented hydrogen and a charge that is not there.
    # Benchmark row "diazomethane".
    ("D-019", "[CH2-][N+]#N", "methanidyldiazonium",
     "(azanylidyne)(methyl)azanium", "gains an H; emits the cation"),
    # N-SUBSTITUTED guanidinium. The parent (D-004) is fixed, but a
    # substituted one needs prefixes on the guanidine skeleton, so the
    # classifier deliberately does not claim it -- claiming without being
    # able to render would now raise rather than mis-name, which is better
    # but is still a regression on today's answer.
    ("D-020", "CNC(N)=[NH2+]", "methylguanidinium",
     "N-(aminoiminomethyl)methanamine", "charge dropped"),
]

# Observed but NOT tracked here, because this table requires a verified
# target name and these have none:
#
#   [C-]1C=CC=C1  ->  "cyclopenta-2,4-dien-1-ide"
#       The cyclopentadienyl RADICAL anion (no H, one unpaired electron),
#       which is a different species from cyclopentadienide -- different
#       InChIKey -- and the radical is dropped. "cyclopentadienide" was
#       tried as the target and rejected by the OPSIN check in
#       tests/vendor/iupac_namer/test_known_defects.py: it denotes the
#       closed-shell anion. No name for the radical anion was found that
#       OPSIN parses back to it, so stating one would be guessing.


@pytest.mark.parametrize(
    "defect,smiles,expected,former,note",
    FIXED,
    ids=[row[0] for row in FIXED],
)
def test_fixed_defect_stays_fixed(defect, smiles, expected, former, note):
    got = name_smiles(smiles)
    assert got == expected, (
        f"{defect} regressed ({note}).\n"
        f"  input:    {smiles}\n"
        f"  expected: {expected}\n"
        f"  got:      {got}\n"
        f"  (the original defect emitted {former!r})"
    )


@pytest.mark.parametrize(
    "defect,smiles,expected,former,note",
    OPEN,
    ids=[row[0] for row in OPEN],
)
@pytest.mark.xfail(strict=True, reason="known open defect, measured not guessed")
def test_open_defect_still_open(defect, smiles, expected, former, note):
    """Fails when the defect is fixed -- that is the point.

    A strict xfail turning green means the engine improved and this file
    is now lying about it. Move the row from OPEN to FIXED.
    """
    assert name_smiles(smiles) == expected
