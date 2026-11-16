"""WS5 P3: NL-071 — 2-azaallenium `C=[N+]=C` stays a charge refusal.

Programme disposition (2026-11-15): **closed** as an honest refusal. The namer
raises rather than emit a neutral name (`N-methylidenemethanimine`) for the cation.
"""

from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer import name_smiles

AZAALLENIUM = "C=[N+]=C"
REFUSAL_FRAGMENT = "positive charge"


def test_nl071_azaallenium_is_refused():
    with pytest.raises(ValueError, match=REFUSAL_FRAGMENT):
        name_smiles(AZAALLENIUM)