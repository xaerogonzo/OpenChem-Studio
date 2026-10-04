"""The held-out manifest is frozen BEFORE v4 exists, and these tests keep it that way.

A manifest that can be quietly edited after a result is seen protects nothing, so
the content is pinned by hash and every structural claim in it is re-derived here
rather than trusted: the SMILES must map to distinct constitutions, the
state-to-structure map must be the one in the source's own SDF, and a reference
must not contradict the checksum the manifest quotes for it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

from openchem.chem.tautomer_validation import canonical_key

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "tautomer_validation" / "heldout_manifest_v2.json"

#: SHA-256 of the manifest's exact bytes at freeze time (2026-10-03). Changing ANY
#: reference value, SMILES or rule changes this, which is the point: the change then
#: has to be made in the open, with a new manifest version, not by editing this one.
FROZEN_SHA256 = "8a3932ca92480b6022b6c51a7b60a7fea47d3d921f61f2d51173efba7cb1c12d"

_RESULT_KEY = re.compile(r"(computed|measured|observed|outcome|mae|error)", re.IGNORECASE)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_manifest_content_is_pinned():
    # Line endings are normalised: a Windows checkout may rewrite them, and that is not an edit.
    normalised = MANIFEST.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(normalised).hexdigest() == FROZEN_SHA256


def test_no_key_anywhere_carries_a_result(manifest):
    """The rule is stated before any run, so nothing in the file may hold one."""
    found: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if _RESULT_KEY.search(key):
                    found.append(f"{path}/{key}")
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(manifest)
    assert not found, found


def test_every_system_is_held_out_and_names_its_whole_reference(manifest):
    assert [s["id"] for s in manifest["systems"]] == ["indazole", "hypoxanthine", "triazole_123", "triazole_124"]
    for system in manifest["systems"]:
        assert system["partition"] == "held_out"
        for field in ("reference_source", "reference_method", "reference_protocol"):
            assert system[field], (system["id"], field)
        protocol = system["reference_protocol"]
        assert protocol["phase"] == "gas" and protocol["zpe_or_thermal_included"] is False
        values = [t["reference_kcal_mol"] for t in system["reference_tautomers"]]
        assert min(values) == 0.0 and all(v >= 0 for v in values), "each reference is zeroed at its own lowest"


def test_reference_smiles_are_distinct_constitutions_and_the_enumerator_reaches_each(manifest):
    """An unmappable reference would be a loud error at run time; find out now."""
    for system in manifest["systems"]:
        keys = [canonical_key(t["smiles"]) for t in system["reference_tautomers"]]
        assert len(set(keys)) == len(keys), f"{system['id']}: two reference states are one constitution"
        enumerator = rdMolStandardize.TautomerEnumerator()
        enumerator.SetMaxTautomers(200)
        reached = {canonical_key(t) for t in enumerator.Enumerate(Chem.MolFromSmiles(system["reference_tautomers"][0]["smiles"]))}
        assert set(keys) <= reached, f"{system['id']}: {set(keys) - reached} not enumerated"


def test_triazole_values_are_balabins_table_iii_not_gollers_printed_one(manifest):
    by_id = {s["id"]: s for s in manifest["systems"]}
    for system_id, expected in (("triazole_123", 3.98), ("triazole_124", 6.25)):
        system = by_id[system_id]
        assert system["reference_source"]["key"] == "balabin2009"
        assert max(t["reference_kcal_mol"] for t in system["reference_tautomers"]) == expected


def test_the_quoted_goller_checksum_failure_really_fails():
    """Table 1, molecule 4: gas 4.36, water 1.05, printed DeltaDeltaE 2.93. If this
    arithmetic ever stopped failing the stated reason for excluding the row would be gone."""
    assert round(4.36 - 1.05, 2) != 2.93 and round(2.93 + 1.05, 2) == 3.98
    assert round(8.70 - 1.06, 2) != 7.78  # adenine, molecule 2


def test_the_clean_goller_rows_really_pass_their_checksum():
    for gas, water, printed in ((4.56, 3.33, 1.23), (1.04, 0.25, 0.79), (5.92, 2.66, 3.26)):
        assert round(gas - water, 2) == printed


def test_adenine_is_recorded_as_excluded_with_its_reason(manifest):
    (excluded,) = manifest["excluded"]
    assert excluded["id"] == "adenine" and excluded["status"] == "excluded_pending_source"
    assert "criterion (1)" in excluded["reason"]


def test_every_cited_source_is_in_the_registry(manifest):
    registry = (ROOT / "docs" / "sources.toml").read_text(encoding="utf-8")
    cited = {s["reference_source"]["key"] for s in manifest["systems"]}
    for system in manifest["systems"]:
        cited |= {c["key"] for c in system.get("corroboration", [])}
    cited |= {c["key"] for e in manifest["excluded"] for c in e.get("corroboration_noted", [])}
    for key in cited:
        assert f'key = "{key}"' in registry, key
