"""A cage must not hang the von Baeyer decomposition (C60 froze the whole application).

The IUPAC-locant overlay calls the vendored naming engine on the UI thread; C60 sent
`vb_decompose` into a combinatorial search with no end in sight (no return in 40 s). The
search now has step budgets. Each case runs in a subprocess so a regression fails by
timeout instead of hanging the suite (a Python thread cannot stop native-time loops).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

C60 = (
    "c12c3c4c5c1c1c6c7c2c2c8c3c3c9c4c4c%10c5c5c1c1c6c6c%11c7c2c2c7c8c3c3c8c9c4c4c9c%10c5c5c1c1c6c6c%11"
    "c2c2c7c3c3c8c4c4c9c5c1c1c6c2c3c41"
)
ADAMANTANE = "C1C2CC3CC1CC(C2)C3"
DODECAHEDRANE = "C12C3C4C1C5C6C2C7C3C8C4C5C9C6C7C8C9"

_SCRIPT = textwrap.dedent(
    """
    import sys
    from rdkit import Chem
    from openchem.vendor.iupac_namer.ring_naming.vb_decompose import decompose_ring_system
    mol = Chem.MolFromSmiles(sys.argv[1])
    atoms = frozenset(a.GetIdx() for a in mol.GetAtoms() if a.IsInRing())
    print(len(decompose_ring_system(atoms, mol)))
    """
)

_LOCANTS = textwrap.dedent(
    """
    import sys
    from rdkit import Chem
    from openchem.chem.atom_numbering import labels_for_molblock
    mol = Chem.MolFromSmiles(sys.argv[1])
    from rdkit.Chem import rdDepictor
    rdDepictor.Compute2DCoords(mol)
    labels, note = labels_for_molblock(Chem.MolToMolBlock(mol), "locants")
    print(len(labels))
    """
)


def _run(script: str, smiles: str, timeout: float) -> int:
    done = subprocess.run(
        [sys.executable, "-I", "-c", script, smiles],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert done.returncode == 0, done.stderr[-800:]
    return int(done.stdout.strip().splitlines()[-1])


def test_c60_decomposition_returns_without_a_decomposition() -> None:
    assert _run(_SCRIPT, C60, timeout=60) == 0


def test_c60_locants_return_and_number_nothing() -> None:
    assert _run(_LOCANTS, C60, timeout=90) == 0


@pytest.mark.parametrize("smiles", [ADAMANTANE, DODECAHEDRANE])
def test_ordinary_cages_still_decompose(smiles: str) -> None:
    # The budgets must not cost a cage the vendored engine handled. Adamantane is the true
    # regression guard (it passed before the budgets); dodecahedrane timed out before them
    # (measured) and now returns, so it only guards against the budgets being set too low.
    assert _run(_SCRIPT, smiles, timeout=60) > 0
