"""
tests/test_hydrazine_parents.py

Unit tests for hydrazine (N-N) as parent hydride and hydrazinyl as substituent form.
Covers: standalone, mono-substituted, di-substituted, fully-substituted,
        hydrazinyl as ring substituent, and non-regression for baseline cases.

These tests verify both Fix 1 (hydrazinyl substituent_form) and Fix 2
(N-N heteroatom_chain parent hydride).
"""
from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer.engine import name_smiles


@pytest.mark.parametrize("smi,expected", [
    # --- Fix 2: N-N as standalone parent ---
    ("NN", "hydrazine"),                          # must still match retained name

    # --- Fix 2: N-N as 2-atom parent with substituents ---
    # Naming round 5 (N4): "'1' is omitted ... in monosubstituted homogeneous
    # chains consisting of only two identical atoms" (P-14.3.4 (b), pdf p. 69).
    ("CNN", "methylhydrazine"),                   # methyl on N1
    ("CNNC", "1,2-dimethylhydrazine"),            # methyl on both N atoms
    ("CN(C)N(C)C", "1,1,2,2-tetramethylhydrazine"),  # fully substituted

    # --- Fix 1: N-N as substituent (hydrazinyl form) ---
    # Round 5 (N4): "phenylhydrazine (PIN)" (pdf p. 755). There is no PCG;
    # P-44.1.2's senior atom, N over C, chooses hydrazine over the ring.
    ("NNc1ccccc1", "phenylhydrazine"),

    # --- benzyl hydrazine ---
    # Round 5 (N4): the hydrazine parent, by the same P-44.1.2 rule as
    # phenylhydrazine; "benzyl" is the preferred prefix. Round-trips.
    ("NNCc1ccccc1", "benzylhydrazine"),

    # --- Regression: unsubstituted parent hydrides must still work ---
    ("P", "phosphane"),
    ("[SiH4]", "silane"),
    ("B", "borane"),

    # --- Regression: PCG-bearing carbon chain beats N-N parent ---
    # round 4: the retained acid stems, "formohydrazide (PIN)" and
    # "acetohydrazide (PIN)" (P-66.3.1, pdf p. 668)
    ("NNC=O", "formohydrazide"),           # hydrazide PCG on methane chain wins
    ("NNC(=O)C", "acetohydrazide"),        # propanohydrazide pattern

    # --- Regression: standard chain/ring naming unaffected ---
    ("CCO", "ethanol"),
    # P-64.2 (BlueBookV2 pdf p. 558): "1-phenylethan-1-one (PIN)" -- a
    # substituted ethane keeps its suffix locant (round 4, D-042).
    ("CC(=O)c1ccccc1", "1-phenylethan-1-one"),
    ("CC(O)c1ccccc1", "1-phenylethan-1-ol"),
])
def test_hydrazine_parent(smi: str, expected: str) -> None:
    """Name SMILES *smi* and check the result matches *expected*."""
    result = name_smiles(smi)
    assert result == expected, (
        f"SMILES {smi!r}: expected {expected!r}, got {result!r}"
    )
