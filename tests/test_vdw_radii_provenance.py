"""Which van der Waals radii this application actually uses, held to the table they were identified with.

The surface, volume, projection and steric calculators ask RDKit for their radii (`GetRvdw`), and for a long
time the code and docs called that "Bondi radii". They are not Bondi's. `docs/VDW_RADII_ASSESSMENT.md` has
the whole investigation; the short version is:

* RDKit's table since 2019.09 (rdkit/rdkit#2154) is the Blue Obelisk Data Repository's, and BODR cites no
  source for it. It equals Batsanov's recommended crystallographic radii (Inorganic Materials 2001, Table 9)
  for every one of the 65 elements that table lists, exactly. That identification is by comparison, not by
  anything RDKit or BODR says, which is why it is pinned here.
* Before that RDKit carried a different table again (carbon 1.95, nitrogen 1.85, oxygen 1.70), so this
  quantity has already changed silently once under a dependency upgrade.
* Bondi's own recommended list (1964) differs for N, O, F, P, Cl, Br and I; the docking module keeps its own
  table, which is Bondi's with the CRC Handbook's hydrogen.

THIS FILE FAILS WHEN RDKIT'S TABLE MOVES, which is the point: radii enter every area, volume and buried volume
the application reports, so an RDKit upgrade that changes them must be a decision, not a surprise. It also
fails if RDKit ever adopts Bondi's values, because then the explainers' and the assessment's statement that
they differ is no longer true and must be rewritten.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from rdkit import Chem

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vdw" / "batsanov2001_table9.csv"

#: Bondi 1964, as printed (read from the paper's pages and cross-checked against Poater et al. 2009 Table 1 and
#: Batsanov's Table 1): the recommended radius for each element RDKit's table disagrees with, and the ones it
#: agrees with, so the comparison is complete for the elements a drug-like molecule contains.
BONDI_1964 = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "P": 1.80, "S": 1.80, "Cl": 1.75, "Br": 1.85, "I": 1.98}


def _batsanov() -> dict[str, float]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        rows = csv.DictReader(line for line in handle if not line.startswith("#"))
        return {row["symbol"]: float(row["radius_angstrom"]) for row in rows}


def test_the_fixture_has_the_whole_table():
    """65 elements: a transcription that dropped a row would make the equality test below weaker, quietly."""
    table = _batsanov()

    assert len(table) == 65
    assert table["C"] == 1.7 and table["P"] == 1.95 and table["I"] == 2.1


@pytest.mark.parametrize("symbol", sorted(_batsanov()))
def test_rdkits_radius_is_batsanovs_recommended_crystallographic_radius(symbol):
    """Equal for all 65. If this fails after an RDKit upgrade, the radii the application reports areas from
    have changed: read docs/VDW_RADII_ASSESSMENT.md before touching the number."""
    assert Chem.GetPeriodicTable().GetRvdw(symbol) == pytest.approx(_batsanov()[symbol], abs=1e-9)


def test_rdkit_hydrogen_is_one_point_two():
    """Hydrogen is not in Batsanov's Table 9; RDKit's 1.20 is Bondi's own hydrogen, and the CRC Handbook's 1.10
    (Rowland and Taylor) is the one that would shrink every area by 3 to 7 percent."""
    assert Chem.GetPeriodicTable().GetRvdw("H") == pytest.approx(1.20)


@pytest.mark.parametrize("symbol", ["N", "O", "F", "P", "Cl", "Br", "I"])
def test_rdkits_radius_is_not_bondis_for_these_elements(symbol):
    """The statement the explainers make. If RDKit ever adopts Bondi's list this fails and the statement must go."""
    assert Chem.GetPeriodicTable().GetRvdw(symbol) != pytest.approx(BONDI_1964[symbol], abs=1e-9)


@pytest.mark.parametrize("symbol", ["H", "C", "S"])
def test_rdkit_agrees_with_bondi_for_hydrogen_carbon_and_sulfur(symbol):
    assert Chem.GetPeriodicTable().GetRvdw(symbol) == pytest.approx(BONDI_1964[symbol], abs=1e-9)


def test_the_docking_modules_own_table_is_bondis_with_the_crc_hydrogen():
    """The application has TWO radius tables. This one, in `pose_analysis`, is the one that really is Bondi's
    (hydrogen 1.10 as in the CRC Handbook, 1.20 in the paper), so contact detection and the surface
    calculators do not share a definition of how big an atom is."""
    from openchem.chem.pose_analysis import _VDW_RADII

    for symbol, expected in {"C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80, "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98}.items():
        assert _VDW_RADII[symbol] == pytest.approx(expected)
    assert _VDW_RADII["H"] == pytest.approx(1.10)
