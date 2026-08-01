"""Round-trip helper the vendored tests import but upstream never shipped.

Three test files (`test_fr_orientation_numbering`, `test_retained_rings`,
`test_skeletal_chain_replacement`) do `from tests.audit._audit_helpers
import assert_round_trip`, but `tests/audit/` is absent from the upstream
repository at the vendored commit -- so collecting the suite failed
outright until this was written.

Reconstructed from how the callers use it, and from the engine's own
stated correctness criterion: a generated name is right when parsing it
back yields the structure it came from.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.naming_providers import NamingError, opsin_structure_for_name
from openchem.vendor.iupac_namer import name_smiles


def assert_round_trip(smiles: str) -> str:
    """Name `smiles`, parse the name back, and assert it is the same
    molecule. Returns the name so callers can assert further on it."""
    original = Chem.MolFromSmiles(smiles)
    assert original is not None, f"test input is not valid SMILES: {smiles}"

    name = name_smiles(smiles)
    assert name, f"no name was generated for {smiles}"

    try:
        parsed = opsin_structure_for_name(str(name))
    except NamingError as exc:
        raise AssertionError(f"OPSIN could not parse {name!r} (from {smiles}): {exc}") from exc

    round_tripped = Chem.MolFromSmiles(parsed.smiles)
    assert round_tripped is not None, f"OPSIN returned unparseable SMILES for {name!r}"
    assert Chem.MolToSmiles(round_tripped) == Chem.MolToSmiles(original), (
        f"{name!r} parses back to a different structure:\n"
        f"  expected {Chem.MolToSmiles(original)}\n"
        f"  got      {Chem.MolToSmiles(round_tripped)}"
    )
    return str(name)
