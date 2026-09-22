"""The B3 frequency census is not a population, and that is enforced the same way the heldout lock enforces
"please don't look": `tests/test_naming_heldout_lock.py` for populations, this file for the census.

The census exists to answer "how common is this shape in ordinary chemistry" -- `NATURAL_FREQUENCY`, never
`REGRESSION_COVERAGE`. If any naming tool started reading it as a population (naming it as a `--stage` input,
scoring the engine against it, adjudicating a row), that distinction would collapse and every frequency
number downstream would secretly be enriched by whatever the engine got fixed to handle. So:

* only `tools/naming_census_build.py` (draws it) and `tools/naming_census_count.py` (counts shapes in it)
  may name `census_sample.json` anywhere in the tracked tree;
* it shares no CID and no canonical-SMILES structure with any registered population or with the B2 battery
  (`benchmarks/naming/battery_r9.toml`) -- a repeat there would not be a fresh, unenriched read;
* `benchmarks/naming/populations.toml` never lists it, so no population-enumerating tool can pick it up
  by accident.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BENCH = ROOT / "benchmarks" / "naming"
CENSUS = BENCH / "census_sample.json"
CENSUS_META = BENCH / "census_sample.meta.json"

THIS_TEST = "tests/test_naming_census_lock.py"
ALLOWED_NAMERS = {"tools/naming_census_build.py", "tools/naming_census_count.py", THIS_TEST}

EXCLUDE_JSON = (
    "corpus.json", "heldout.json", "heldout2.json", "heldout3.json", "heldout4.json",
    "heldout5.json", "heldout6.json", "bluebook_tuning.json", "bluebook_frozen.json",
)


def _scripts_naming(filename: str) -> set[str]:
    result = subprocess.run(
        ["git", "grep", "-l", filename, "--", "*.py"], cwd=ROOT, capture_output=True, text=True
    )
    return set(result.stdout.split())


def test_the_registry_never_lists_the_census():
    populations_toml = (BENCH / "populations.toml").read_text(encoding="utf-8")
    assert "census_sample" not in populations_toml, (
        "the census must never become a registered population -- see this file's module docstring"
    )


def test_no_other_tracked_script_names_the_census_file():
    stray = _scripts_naming("census_sample.json") - ALLOWED_NAMERS
    assert not stray, f"only {sorted(ALLOWED_NAMERS)} may name census_sample.json; also found: {sorted(stray)}"


def test_a_stray_script_naming_the_census_is_caught():
    """The guard above only means something if it can fail. A synthetic third namer, written to a scratch
    directory (never the real tree), must be reported by the same scan `git grep --no-index` would use."""
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        scratch_path = Path(scratch)
        (scratch_path / "stray_reader.py").write_text(
            "CENSUS = 'benchmarks/naming/census_sample.json'\n", encoding="utf-8"
        )
        result = subprocess.run(
            ["git", "grep", "-l", "--no-index", "census_sample.json", "--", "*.py"],
            cwd=scratch_path, capture_output=True, text=True,
        )
        assert "stray_reader.py" in result.stdout


def _canonical_smiles(rows, key="smiles"):
    return {row[key] for row in rows}


def test_the_census_shares_no_structure_with_any_population_or_the_b2_battery():
    if not CENSUS.exists():
        import pytest

        pytest.skip("census_sample.json has not been drawn yet")

    census_rows = json.loads(CENSUS.read_text(encoding="utf-8"))
    census_smiles = _canonical_smiles(census_rows)
    census_cids = {row["pubchem_cid"] for row in census_rows}

    for name in EXCLUDE_JSON:
        path = BENCH / name
        if not path.exists():
            continue
        other_rows = json.loads(path.read_text(encoding="utf-8"))
        other_smiles = _canonical_smiles(other_rows)
        overlap = census_smiles & other_smiles
        assert not overlap, f"{len(overlap)} structure(s) shared between census_sample.json and {name}"
        other_cids = {row.get("pubchem_cid") for row in other_rows if row.get("pubchem_cid")}
        cid_overlap = census_cids & other_cids
        assert not cid_overlap, f"{len(cid_overlap)} CID(s) shared between census_sample.json and {name}"

    battery_path = BENCH / "battery_r9.toml"
    if battery_path.exists():
        battery_rows = tomllib.loads(battery_path.read_text(encoding="utf-8"))["row"]
        overlap = census_smiles & _canonical_smiles(battery_rows)
        assert not overlap, f"{len(overlap)} structure(s) shared between census_sample.json and battery_r9.toml"


def test_the_census_has_no_duplicate_structure_within_itself():
    if not CENSUS.exists():
        import pytest

        pytest.skip("census_sample.json has not been drawn yet")
    rows = json.loads(CENSUS.read_text(encoding="utf-8"))
    smiles = [row["smiles"] for row in rows]
    assert len(smiles) == len(set(smiles)), "the census admits the same structure twice"


def test_the_meta_hash_matches_the_file_it_describes():
    """Over LF text, because that is what the draw hashed and what git stores: the Windows working copy
    is CRLF under this repo's `core.autocrlf=true`, and hashing it raw reads as tampering when it is only
    a checkout setting -- the same normalisation test_naming_heldout_lock.py's own hash check applies."""
    if not CENSUS_META.exists():
        import pytest

        pytest.skip("census_sample.meta.json has not been written yet (run with --freeze)")
    import hashlib

    meta = json.loads(CENSUS_META.read_text(encoding="utf-8"))
    raw = CENSUS.read_bytes().replace(b"\r\n", b"\n")
    assert meta["census_sha256"] == hashlib.sha256(raw).hexdigest()


def test_the_meta_says_no_engine_and_no_opsin_were_consulted():
    if not CENSUS_META.exists():
        import pytest

        pytest.skip("census_sample.meta.json has not been written yet (run with --freeze)")
    meta = json.loads(CENSUS_META.read_text(encoding="utf-8"))
    assert meta["engine_consulted"] is False
    assert meta["opsin_consulted"] is False
