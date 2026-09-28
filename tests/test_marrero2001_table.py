"""Marrero and Gani (2001) Tables 6, 7 and 2, checked against the paper's own arithmetic.

The tables were transcribed from RENDERED PAGE IMAGES (the PDF's text layer is missing for pp. 194-200 --
see docs/research/literature.toml's marrero2001 entry): this file is the check that the transcription
reproduces what the paper itself computes in Appendix B, before anything is built on the table. It is not
a claim that Marrero-Gani has been promoted to a calculator -- see docs/CALCULATOR_MATURITY.md for what
that requires and docs/research/README.md for why a survey is not a calculator.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def table():
    path = ROOT / "benchmarks" / "thermophysical" / "marrero2001_table.py"
    spec = importlib.util.spec_from_file_location("marrero2001_table", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _by_symbol(rows, symbol):
    matches = [r for r in rows if r[1] == symbol]
    assert len(matches) == 1, f"{symbol!r} matched {len(matches)} rows, not 1"
    return matches[0]


def test_first_order_table_has_the_papers_182_groups(table):
    assert len(table.FIRST_ORDER) == 182


def test_second_order_table_has_the_papers_122_groups(table):
    assert len(table.SECOND_ORDER) == 122


def test_ids_are_consecutive_from_one(table):
    assert [r[0] for r in table.FIRST_ORDER] == list(range(1, 183))
    assert [r[0] for r in table.SECOND_ORDER] == list(range(1, 123))


def test_the_ring_nitrogen_group_joback_lacks_is_present(table):
    """The group this table was transcribed to check for: RDX/HMX's ring N-NO2 needs a ring
    nitrogen group, which Joback (1987) does not have at all (docs/CALCULATOR_MATURITY.md)."""
    row = _by_symbol(table.FIRST_ORDER, "N (cyclic)")
    assert row[2] == "N-methylpyrrolidine(1)"
    assert row[3] == pytest.approx(0.6040)   # Tm1i
    assert row[4] == pytest.approx(1.6541)   # Tb1i


def test_the_generic_nitro_group_is_present(table):
    row = _by_symbol(table.FIRST_ORDER, "NO2 except as above")
    assert row[2] == "Nitrocyclohexane(1)"


def test_a_dash_in_the_paper_is_null_and_never_zero(table):
    # Group 12 (CH=C=CH) prints "*****" for Tc1i, Pc1i, Vc1i, Gf1i, Hf1i, Hv1i -- a real gap in
    # the source data, not a zero contribution.
    row = _by_symbol(table.FIRST_ORDER, "CH=C=CH")
    assert row[5] is None   # Tc1i
    assert row[6] is None   # Pc1i
    assert row[-1] == pytest.approx(6.000)   # Hfus1i is NOT starred


def test_universal_constants_match_table_2(table):
    c = table.UNIVERSAL_CONSTANTS
    assert c["Tm0"] == pytest.approx(147.450)
    assert c["Tb0"] == pytest.approx(222.543)


def _tb_sum(table, symbols_with_counts):
    total = 0.0
    for symbol, n in symbols_with_counts:
        row = _by_symbol(table.FIRST_ORDER, symbol)
        total += n * row[4]   # Tb1i column
    return total


def _tm_sum(table, symbols_with_counts):
    total = 0.0
    for symbol, n in symbols_with_counts:
        row = _by_symbol(table.FIRST_ORDER, symbol)
        total += n * row[3]   # Tm1i column
    return total


def test_example_1_first_order_sum_reproduces_n_phenyl_1_4_benzenediamine(table):
    """Appendix B, Example 1: iNiTb1i = 15.8281, Tb = 222.543 ln(15.8281) = 614.62 K."""
    total = _tb_sum(table, [("aC-NH2", 1), ("aC-NH", 1), ("aC except as above", 1), ("aCH", 9)])
    assert total == pytest.approx(15.8281, abs=1e-3)
    tb = table.UNIVERSAL_CONSTANTS["Tb0"] * math.log(total)
    assert tb == pytest.approx(614.62, abs=0.02)


def test_example_3_first_order_sum_reproduces_4_aminobutanol(table):
    """Appendix B, Example 3: iNiTb1i = 7.508, Tb = 222.543 ln(7.508) = 448.64 K."""
    total = _tb_sum(table, [("OH", 1), ("CH2NH2", 1), ("CH2", 3)])
    assert total == pytest.approx(7.508, abs=1e-3)
    tb = table.UNIVERSAL_CONSTANTS["Tb0"] * math.log(total)
    assert tb == pytest.approx(448.64, abs=0.02)


def test_example_4_first_order_sum_reproduces_dicoumarol_tm(table):
    """Appendix B, Example 4: iNiTm1i = 25.1421, Tm = 147.450 ln(25.1421) = 475.46 K."""
    total = _tm_sum(
        table,
        [
            ("OH", 2),
            ("aC fused w/ nonaromatic subring", 4),
            ("aCH", 8),
            ("C=C (cyclic)", 2),
            ("CO (cyclic)", 2),
            ("O (cyclic)", 2),
            ("CH2", 1),
        ],
    )
    assert total == pytest.approx(25.1421, abs=1e-3)
    tm = table.UNIVERSAL_CONSTANTS["Tm0"] * math.log(total)
    assert tm == pytest.approx(475.46, abs=0.02)
