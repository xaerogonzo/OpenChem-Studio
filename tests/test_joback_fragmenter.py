"""The Joback fragmenter -- the part the paper does not supply.

`tests/test_joback_table.py` gates the transcribed table against the paper.
This gates the SMARTS that turn a molecule into group counts, which is this
project's reading of printed group names and therefore the part most able to
be confidently wrong.

**THE ACCEPTANCE TEST RUNS FROM A SMILES, NOT FROM GROUP COUNTS.** The table
test supplies the paper's own decomposition and checks the arithmetic; this
one starts at `Clc1ccc(Cl)cc1` and must arrive at it. A fragmenter that is
subtly wrong still produces plausible numbers, so the two halves have to be
tested from opposite ends.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import joback as J

# The paper's own example, Tables IV and V.
PDCB = "Clc1ccc(Cl)cc1"
PAPER_DECOMPOSITION = {"-Cl": 2, "ring=CH-": 4, "ring=C<": 2}


def _fragment(smiles: str) -> J.Fragmentation:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"the fixture SMILES {smiles!r} does not parse"
    return J.fragment(mol)


def _claimed_atoms(f: J.Fragmentation) -> int:
    return sum(J.GROUP_ATOM_COUNT.get(g, 1) * n for g, n in f.counts.items())


# ---------------------------------------------------------------------------
# 1  the paper's worked example, end to end from a structure
# ---------------------------------------------------------------------------


def test_the_papers_own_example_fragments_the_way_the_paper_does():
    f = _fragment(PDCB)
    assert f.applicable
    assert f.counts == PAPER_DECOMPOSITION


def test_the_papers_own_example_counts_every_atom_including_hydrogens():
    """Eq. (5) needs the TOTAL atom count and every other equation is a bare
    group sum, which is what makes this easy to miss. The paper's footnote 2
    says n_A = 12 for p-dichlorobenzene -- 8 heavy atoms and 4 hydrogens."""
    f = _fragment(PDCB)
    assert f.n_atoms == 12
    assert f.molecular_weight == pytest.approx(147.0, abs=0.05)


@pytest.mark.parametrize("name,got,printed,tol", [
    ("Tb", "boiling_point", 443.4, 0.1),
    ("Vc", "critical_volume", 362, 0.5),
    ("Hform", "enthalpy_of_formation", 26.41, 0.01),
    ("Gform", "gibbs_energy_of_formation", 78.56, 0.01),
    ("Hvap", "enthalpy_of_vaporization", 40.66, 0.01),
])
def test_table_v_from_a_smiles(name, got, printed, tol):
    f = _fragment(PDCB)
    assert getattr(J, got)(f) == pytest.approx(printed, abs=tol)


def test_critical_pressure_from_a_smiles():
    assert J.critical_pressure(_fragment(PDCB)) == pytest.approx(41.5, abs=0.05)


def test_critical_temperature_prefers_an_experimental_boiling_point():
    """Eq. (4) takes Tb and the paper's footnote 1 uses the MEASURED 447 K,
    giving 681 K where the estimated Tb gives 675 K. Both arms are asserted,
    because using the wrong one still produces a plausible number.

    That six-kelvin gap is not the interesting case. Measured over 34 of
    Lange's Table 6.5 entries, estimating Tb costs 20 K of Tc MAE against the
    paper's own 4.8 K -- and `dTc/dTb` comes out at 1.43-1.70 for every one
    of them, which is the amplification 1/D and says the whole discrepancy is
    Tb propagation rather than a fragmentation defect. Pc and Vc, which use
    the identical fragmentation, beat the paper's own regression errors.
    """
    f = _fragment(PDCB)
    assert J.critical_temperature(f, 447.0) == pytest.approx(681, abs=0.5)
    assert J.critical_temperature(f) == pytest.approx(675, abs=0.5)


# ---------------------------------------------------------------------------
# 2  the invariant that caught three real bugs
# ---------------------------------------------------------------------------


def test_no_pattern_claims_an_atom_outside_its_own_group():
    """Enforced in `_patterns()` at compile time; asserted here so the rule is
    visible as a rule rather than as an exception nobody triggers."""
    for group_id, patt, _why in J._patterns():
        assert patt.GetNumAtoms() == J.GROUP_ATOM_COUNT.get(group_id, 1), group_id


def test_the_atom_count_invariant_actually_REFUSES_a_greedy_pattern(monkeypatch):
    """THE NARROW HALF, and it is the load-bearing one.

    The test above passes just as happily with the check deleted, because
    with correct SMARTS it never fires -- mutating the check away survived the
    whole file. What the check is FOR is the pattern nobody has written yet,
    so the only way to test it is to write one.

    `[OX2H1][c]` is the real bug this guard was added for: it claims phenol's
    ipso carbon, which belongs to `ring=C<`.
    """
    greedy = (("-OH(phenol)", "[OX2H1][c]", "deliberately claims one atom too many"),)
    monkeypatch.setattr(J, "_SPEC", greedy)
    J._patterns.cache_clear()
    try:
        with pytest.raises(ValueError, match="claim an atom belonging to another"):
            J._patterns()
    finally:
        J._patterns.cache_clear()


def test_the_compile_check_also_refuses_an_unknown_group_and_bad_smarts(monkeypatch):
    """The other two arms of the same check, so a typo in `_SPEC` fails where
    it is written rather than by silently never matching anything."""
    for spec, expected in (
        ((("-NOT-A-GROUP-", "[#6]", "typo"),), "not in the shipped table"),
        ((("-CH3", "[#6", "unclosed bracket"),), "unparseable SMARTS"),
    ):
        monkeypatch.setattr(J, "_SPEC", spec)
        J._patterns.cache_clear()
        try:
            with pytest.raises(ValueError, match=expected):
                J._patterns()
        finally:
            J._patterns.cache_clear()


#: Every one of these was WRONG on the first run, and none of them refused --
#: the atom was claimed, just by the wrong group, so the coverage check could
#: not see it. They are regression fixtures, not examples.
REGRESSIONS = [
    # `[OX2H1][c]` claimed phenol's ipso carbon, which is its own ring=C<.
    ("phenol", "Oc1ccccc1", 7, {"-OH(phenol)": 1, "ring=C<": 1, "ring=CH-": 5}),
    # `[#6X2H1]#*` claimed propyne's internal alkyne carbon, so it contributed
    # nothing and Tb came out 231.0 K instead of 258.4 K.
    ("propyne", "CC#C", 3, {"-CH3": 1, "#C-": 1, "#CH": 1}),
    # `[#6X2H0](=*)=*` claimed both allene termini, so nothing matched at all.
    ("allene", "C=C=C", 3, {"=C=": 1, "=CH2": 2}),
    # `[SX2H0;R]` is ALIPHATIC-only, so thiophene's aromatic sulfur was
    # refused outright -- the same trap the carbons are written to avoid.
    ("thiophene", "c1ccsc1", 5, {"ring-S-": 1, "ring=CH-": 4}),
]


@pytest.mark.parametrize("name,smiles,heavy,expected", REGRESSIONS,
                         ids=[r[0] for r in REGRESSIONS])
def test_a_pattern_does_not_swallow_a_neighbouring_group(name, smiles, heavy, expected):
    f = _fragment(smiles)
    assert f.applicable, f"{name}: {f.refusal}"
    assert f.counts == expected
    assert _claimed_atoms(f) == heavy


def test_propyne_boiling_point_is_the_three_group_answer():
    """The number the swallowed-carbon bug got wrong, pinned. 198.2 + CH3 +
    triple-C + triple-CH, against the two-group 231.0 K it used to give."""
    assert J.boiling_point(_fragment("CC#C")) == pytest.approx(258.4, abs=0.1)


# ---------------------------------------------------------------------------
# 3  coverage across chemistry the patterns were not tuned on
# ---------------------------------------------------------------------------

COVERED = [
    ("ethane", "CC", 2), ("neopentane", "CC(C)(C)C", 5),
    ("cyclohexane", "C1CCCCC1", 6), ("benzene", "c1ccccc1", 6),
    ("naphthalene", "c1ccc2ccccc2c1", 10), ("toluene", "Cc1ccccc1", 7),
    ("ethanol", "CCO", 3), ("acetone", "CC(C)=O", 4),
    ("acetaldehyde", "CC=O", 3), ("acetic acid", "CC(=O)O", 4),
    ("ethyl acetate", "CCOC(C)=O", 6), ("diethyl ether", "CCOCC", 5),
    ("tetrahydrofuran", "C1CCOC1", 5), ("acetonitrile", "CC#N", 3),
    ("nitrobenzene", "[O-][N+](=O)c1ccccc1", 9), ("aniline", "Nc1ccccc1", 7),
    ("pyridine", "c1ccncc1", 6), ("pyrrole", "c1cc[nH]c1", 5),
    ("triethylamine", "CCN(CC)CC", 7), ("ethanethiol", "CCS", 3),
    ("dimethyl sulfide", "CSC", 3), ("chloroform", "ClC(Cl)Cl", 4),
    ("cyclohexanone", "O=C1CCCCC1", 7), ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", 13),
    ("propene", "CC=C", 3), ("benzoic acid", "OC(=O)c1ccccc1", 9),
    ("anisole", "COc1ccccc1", 8),
]


@pytest.mark.parametrize("name,smiles,heavy", COVERED, ids=[c[0] for c in COVERED])
def test_every_heavy_atom_is_claimed_exactly_once(name, smiles, heavy):
    """Joback is additive over a PARTITION, so an atom claimed twice or not
    at all is a different quantity rather than a rougher answer."""
    f = _fragment(smiles)
    assert f.applicable, f"{name} refused: {f.refusal} {f.detail}"
    assert _claimed_atoms(f) == heavy


# ---------------------------------------------------------------------------
# 4  the refusals, each of which is a real limit of the paper
# ---------------------------------------------------------------------------

REFUSED = [
    # The nitrogen block has >NH (ring) and -N= (ring) and NO ring tertiary
    # amine, so these have no decomposition at all. Mapping them onto the
    # nonring value is the obvious repair and would be an invention.
    ("N-methylpiperidine", "CN1CCCCC1", J.JobackRefusal.UNCOVERED_ATOM),
    ("N-methylpyrrole", "Cn1cccc1", J.JobackRefusal.UNCOVERED_ATOM),
    ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C", J.JobackRefusal.UNCOVERED_ATOM),
    # The table stops at divalent sulfur.
    ("DMSO", "CS(C)=O", J.JobackRefusal.UNCOVERED_ATOM),
    # No group is small enough: -CH3 is a methyl attached to something, and
    # -OH (alcohol) is an oxygen with one hydrogen.
    ("methane", "C", J.JobackRefusal.UNCOVERED_ATOM),
    ("water", "O", J.JobackRefusal.UNCOVERED_ATOM),
    # Not a pure component.
    ("sodium acetate", "CC(=O)[O-].[Na+]", J.JobackRefusal.NOT_A_PURE_COMPONENT),
    ("acetate anion", "CC(=O)[O-]", J.JobackRefusal.CHARGED),
]


@pytest.mark.parametrize("name,smiles,reason", REFUSED, ids=[r[0] for r in REFUSED])
def test_joback_refuses_rather_than_approximating(name, smiles, reason):
    f = _fragment(smiles)
    assert not f.applicable, f"{name} should not have been fragmented: {f.counts}"
    assert f.refusal is reason
    assert not f.counts


def test_a_refusal_says_which_atom_and_names_the_two_common_causes():
    f = _fragment("CN1CCCCC1")
    text = J.refusal_text(f)
    assert "N at index" in f.detail
    assert "ring tertiary amine" in text
    assert "partial sum" in text


def test_refusal_text_is_generated_in_one_place():
    """So `if "refused" in message` never becomes application logic -- the
    shape `IsotopeRefusal.refuse_isomer` already uses."""
    assert J.refusal_text(_fragment(PDCB)) == ""
    for _name, smiles, _reason in REFUSED:
        assert J.refusal_text(_fragment(smiles))


# ---------------------------------------------------------------------------
# 5  a dash in the table is absent, not zero
# ---------------------------------------------------------------------------


def test_a_group_with_no_contribution_refuses_that_property_alone():
    """`-N= (nonring)` has a Tb and a Hform and no Vc, no Tf, no Gform and no
    heat capacity. The molecule still gets the properties it can support --
    refusing everything would be as wrong as summing the dash as zero.

    Asserts its own setup: if that row ever gained a Vc this would go vacuous.
    """
    assert J.groups()["-N="]["vc"] is None
    assert J.groups()["-N="]["tb"] is not None

    f = _fragment("CC=NC")          # N-methylethanimine, an acyclic imine
    assert f.applicable
    assert "-N=" in f.counts

    assert J.critical_volume(f) is None
    assert J.freezing_point(f) is None
    assert J.gibbs_energy_of_formation(f) is None
    assert J.heat_capacity(f, 298) is None
    assert J.boiling_point(f) is not None
    assert J.enthalpy_of_formation(f) is not None
    assert f.groups_without("vc") == ["-N="]


def test_a_present_zero_is_not_confused_with_an_absent_value():
    """`-CH2-` has a Pc contribution of exactly 0. A fragmentation that is
    only CH2 groups must still return a Pc."""
    assert J.groups()["-CH2-"]["pc"] == 0.0
    f = _fragment("C1CCCCC1")
    assert f.total("pc") is not None


# ---------------------------------------------------------------------------
# 6  the table and the patterns cannot drift apart
# ---------------------------------------------------------------------------


def test_every_pattern_names_a_group_the_table_carries():
    known = set(J.groups())
    for group_id, _patt, _why in J._patterns():
        assert group_id in known


def test_every_group_in_the_table_is_reachable_by_some_pattern():
    """A row nothing can ever match is a row that was transcribed for nothing
    -- and would hide a fragmenter that quietly cannot see a whole family."""
    reachable = {group_id for group_id, _p, _w in J._patterns()}
    orphans = sorted(set(J.groups()) - reachable)
    assert not orphans, f"table rows no SMARTS can produce: {orphans}"


def test_the_papers_own_error_bars_are_carried_not_invented():
    """Table VI's regression errors, which are what a declared uncertainty on
    a Joback result has to be built from."""
    assert J.PAPER_ABSOLUTE_ERROR["Tc"] == (4.8, "K")
    assert J.PAPER_ABSOLUTE_ERROR["Tb"] == (12.9, "K")
    assert J.CP_RANGE_K == (273.0, 1000.0)
