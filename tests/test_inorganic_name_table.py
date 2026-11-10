"""Name tables that RDKit used to complain about while loading."""

from __future__ import annotations

import logging
import os
import tempfile

from openchem.vendor.iupac_namer.engine import (
    _build_inorganic_canonical_index,
    _lookup_inorganic_canonical,
    name_smiles,
)


def _stderr(function):
    saved = os.dup(2)
    descriptor, path = tempfile.mkstemp()
    os.dup2(descriptor, 2)
    os.close(descriptor)
    try:
        result = function()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    os.remove(path)
    return result, text


def test_hydronium_is_indexed_and_building_the_table_is_quiet(caplog):
    """`[H3O+]` does not parse, so the old key never matched and printed a
    parse error on the first name of a session. `[OH3+]` is the form RDKit
    writes, and the proton, hydride and uranium keys must not chatter either."""
    with caplog.at_level(logging.WARNING):
        index, stderr = _stderr(_build_inorganic_canonical_index)
    assert stderr.strip() == ""
    assert not caplog.records
    assert index["[OH3+]"]["name"] == "oxidanium"
    found = _lookup_inorganic_canonical("[OH3+]")
    assert found is not None and found["name"] == "oxidanium"
    assert name_smiles("[OH3+]") == "oxidanium"


def test_building_the_ring_table_does_not_print_a_kekulize_error():
    """The bare purine skeleton cannot kekulize. The table keeps the locants
    it was given and must not print that on the first atom-number request."""
    from openchem.vendor.iupac_namer.ring_naming.retained_lookup import (
        _build_curated_from_data_loader,
    )

    _table, stderr = _stderr(_build_curated_from_data_loader)
    assert "kekulize" not in stderr.lower()
    assert stderr.strip() == ""
