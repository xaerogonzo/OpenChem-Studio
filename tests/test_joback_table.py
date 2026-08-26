"""The Joback & Reid group-contribution table, guarded against its source.

This guards the TABLE, not a calculator -- `chem/joback.py` does not exist
yet, and the table is the thing that took a hand transcription from a 300 dpi
render and is therefore the thing that can be silently wrong.

**THE ACCEPTANCE ORACLE IS THE PAPER'S OWN WORKED EXAMPLE.** Joback & Reid
Tables IV and V (p239) estimate all eleven properties for p-dichlorobenzene
and print every intermediate summation as well as every result. Reproducing
those is a far stronger statement than "the numbers look plausible", and it
is what caught the discrepancy documented in `table_iii_is_rounded`.

The group COUNTS here come from the paper, deliberately. A SMARTS fragmenter
does not exist yet, and gating the table on one would test two things at once
and tell you neither.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

DATA = (Path(__file__).resolve().parent.parent
        / "src" / "openchem" / "chem" / "data" / "joback_groups.json")

PAYLOAD = json.loads(DATA.read_text(encoding="utf-8"))
GROUPS = {g["id"]: g for g in PAYLOAD["groups"]}

#: Every property column Table III carries.
FIELDS = ("tc", "pc", "vc", "tb", "tf", "hform", "gform",
          "a", "b", "c", "d", "hvap", "hfus", "eta_a", "eta_b")

#: p-dichlorobenzene, as the paper decomposes it (Table IV).
EXAMPLE_COUNTS = {"-Cl": 2, "ring=CH-": 4, "ring=C<": 2}
EXAMPLE_N_ATOMS = 12          # Table V footnote 2
EXAMPLE_MW = 147.0            # Table V footnote 3
EXAMPLE_TB_EXPERIMENTAL = 447.0   # Table V footnote 1


def _sum(field: str) -> float:
    return sum(n * GROUPS[gid][field] for gid, n in EXAMPLE_COUNTS.items())


# ---------------------------------------------------------------------------
# 1  the table's shape
# ---------------------------------------------------------------------------


def test_the_table_has_the_papers_41_groups():
    assert len(PAYLOAD["groups"]) == 41


def test_every_group_carries_every_property_column():
    """A group missing a column would sum as a KeyError at best and as a
    silent zero at worst."""
    for gid, g in GROUPS.items():
        missing = [f for f in FIELDS if f not in g]
        assert not missing, f"{gid} is missing {missing}"


def test_every_group_keeps_the_symbol_the_paper_printed():
    """Source row identity, as `tsei_radii.json` keeps it -- so a later audit
    is a line-by-line comparison against the page rather than a
    re-derivation."""
    for gid, g in GROUPS.items():
        assert g.get("printed"), f"{gid} does not record how the paper prints it"
        assert g.get("block"), f"{gid} does not record which block it is in"


def test_a_dash_in_the_paper_is_null_and_never_zero():
    """The paper prints a dash where a group has NO contribution for a
    property. Zero is a contribution; absent is not, and a molecule needing an
    absent one must be refused rather than summed as 0.

    Asserts its own setup -- if nothing were null this guard would be vacuous.
    """
    nulls = [(gid, f) for gid, g in GROUPS.items() for f in FIELDS if g[f] is None]
    assert nulls, "no null contributions at all -- the fixture has gone vacuous"
    # -N= (nonring) is the paper's most-abstained group.
    assert GROUPS["-N="]["vc"] is None
    assert GROUPS["-N="]["a"] is None
    # ...and a real zero survives as a zero.
    assert GROUPS["-CH2-"]["pc"] == 0.0


# ---------------------------------------------------------------------------
# 2  the paper's own worked example -- Table IV, the summations
# ---------------------------------------------------------------------------

# (label, field, the value Table IV prints, tolerance)
TABLE_IV = [
    ("Tb", "tb", 245.20, 1e-2),
    ("Tf", "tf", 133.66, 1e-2),
    ("Tc", "tc", 0.0824, 1e-4),
    ("Pc", "pc", -0.0038, 1e-4),
    ("Vc", "vc", 344, 1e-9),
    ("Hform", "hform", -41.88, 1e-2),
    ("Gform", "gform", 24.68, 1e-2),
    ("Cp a", "a", 41.54, 1e-2),
    ("Cp b", "b", 0.239, 1e-3),
    ("Cp d", "d", -1.27e-7, 1e-9),
    ("Hvap", "hvap", 25.36, 1e-2),
    ("Hfus", "hfus", 14.22, 1e-2),
    ("eta_a", "eta_a", 1798.0, 1e-1),
    ("eta_b", "eta_b", -4.612, 1e-3),
]


@pytest.mark.parametrize("label,field,printed,tol", TABLE_IV, ids=[r[0] for r in TABLE_IV])
def test_table_iv_summation_reproduces(label, field, printed, tol):
    assert _sum(field) == pytest.approx(printed, abs=tol)


def test_the_one_summation_that_does_NOT_reproduce_and_why():
    """TABLE III AND TABLE IV DISAGREE ON ONE COEFFICIENT, and this pins it.

    Table III prints the -Cl heat-capacity `c` as 1.87E-4; Table IV's worked
    example uses 1.874e-4. Confirmed from the PDF's own text layer -- '1.874'
    occurs on p239 and not on p237 -- and settled by the arithmetic below,
    since only the four-digit value reproduces the printed sum.

    This table ships Table III's value, because Table III is the reference
    table and the fourth digit is known for exactly one group of 41. The
    consequence is asserted rather than tolerated: `sum(c)` is 8.344e-5 here
    and 8.42e-5 in the paper.
    """
    three_figures = _sum("c")
    assert three_figures == pytest.approx(8.344e-5, abs=1e-8)

    four_figures = 2 * 1.874e-4 + 4 * GROUPS["ring=CH-"]["c"] + 2 * GROUPS["ring=C<"]["c"]
    assert four_figures == pytest.approx(8.42e-5, abs=1e-7), (
        "the four-digit -Cl value must be what reproduces Table IV's printed sum"
    )
    assert GROUPS["-Cl"]["c"] == 1.87e-4, "we ship Table III's rounded value"


# ---------------------------------------------------------------------------
# 3  the paper's own worked example -- Table V, the estimated values
# ---------------------------------------------------------------------------


def _cp(T: float) -> float:
    return (_sum("a") - 37.93
            + (_sum("b") + 0.210) * T
            + (_sum("c") - 3.91e-4) * T ** 2
            + (_sum("d") + 2.06e-7) * T ** 3)


def _eta(T: float) -> float:
    return EXAMPLE_MW * math.exp(
        (_sum("eta_a") - 597.82) / T + _sum("eta_b") - 11.202
    )


def test_table_v_boiling_and_freezing_points():
    assert 198.2 + _sum("tb") == pytest.approx(443.4, abs=0.1)
    assert 122.5 + _sum("tf") == pytest.approx(256, abs=0.5)


def test_table_v_critical_temperature_from_the_EXPERIMENTAL_boiling_point():
    """Eq. (4) takes Tb, and the paper's footnote 1 says the EXPERIMENTAL
    447 K was used -- estimating Tb instead gives 675 K rather than 681 K.
    Both arms are asserted, because using the wrong one still produces a
    plausible number."""
    denom = 0.584 + 0.965 * _sum("tc") - _sum("tc") ** 2
    assert EXAMPLE_TB_EXPERIMENTAL / denom == pytest.approx(681, abs=0.5)
    assert (198.2 + _sum("tb")) / denom == pytest.approx(675, abs=0.5)


def test_table_v_critical_pressure_uses_the_TOTAL_atom_count():
    """Eq. (5)'s n_A is every atom, hydrogens included -- 12 for
    p-dichlorobenzene, not the 8 heavy atoms. Every other equation is a bare
    group sum, which is what makes this easy to get wrong."""
    assert (0.113 + 0.0032 * EXAMPLE_N_ATOMS - _sum("pc")) ** -2 == pytest.approx(41.5, abs=0.05)
    heavy_atoms_only = (0.113 + 0.0032 * 8 - _sum("pc")) ** -2
    assert abs(heavy_atoms_only - 41.5) > 3, "8 vs 12 must be distinguishable"


def test_table_v_critical_volume_and_formation_properties():
    assert 17.5 + _sum("vc") == pytest.approx(362, abs=0.5)
    assert 68.29 + _sum("hform") == pytest.approx(26.41, abs=0.01)
    assert 53.88 + _sum("gform") == pytest.approx(78.56, abs=0.01)


def test_table_v_enthalpies_of_vaporization_and_fusion():
    assert 15.30 + _sum("hvap") == pytest.approx(40.66, abs=0.01)
    assert -0.88 + _sum("hfus") == pytest.approx(13.3, abs=0.05)


@pytest.mark.parametrize("T,printed", [(298, 112.3), (400, 139.2), (800, 206.8), (1000, 224.6)])
def test_table_v_heat_capacity_within_the_rounding_the_paper_carries(T, printed):
    """0.5% rather than exact, and the reason is the -Cl coefficient above --
    NOT slack. Tightening this to 0.05% fails, and it fails for a reason the
    paper owns rather than one this transcription introduced."""
    assert _cp(T) == pytest.approx(printed, rel=5e-3)


@pytest.mark.parametrize("T,printed", [(333.8, 7.26e-4), (374.4, 4.92e-4),
                                       (403.1, 3.91e-4), (423.3, 3.40e-4)])
def test_table_v_liquid_viscosity(T, printed):
    """The paper prints three significant figures, so the comparison is
    relative -- 3.40e-4 is a rounding of 3.394e-4."""
    assert _eta(T) == pytest.approx(printed, rel=3e-3)


# ---------------------------------------------------------------------------
# 4  provenance
# ---------------------------------------------------------------------------


def test_the_table_says_where_it_came_from_and_why_it_was_rendered():
    """The registry resolves `_source_key`; these two say the transcription
    could not have come from the text layer, which is the finding a future
    reader most needs and the one a bare citation cannot carry."""
    assert PAYLOAD["_source_key"] == "joback1987"
    assert "RENDER" in PAYLOAD["_read_from"]
    assert PAYLOAD["_why_rendered"]
    assert PAYLOAD["_notes"]["table_iii_is_rounded"]
