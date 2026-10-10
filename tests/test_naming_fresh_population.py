"""tools/naming_fresh_draw.py and `naming_stage_artifact.py --only`: the draw's selection, run offline, and the scoring door.

The draw is network code, so its fetch and sleep are parameters; everything here runs with a table of fake PubChem answers.
(That the frozen file, its meta and the registry agree is the job of tests/test_naming_heldout_lock.py, which this population is
now part of.)
"""

from __future__ import annotations

import email.message
import hashlib
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_fresh_draw as fresh  # noqa: E402
import naming_populations as registry  # noqa: E402
import naming_stage_artifact as stage  # noqa: E402

#: Eight-heavy-atom molecules, so the census's 6-40 heavy-atom filter admits them.
MOLECULES = ["CCCCCCCO", "CCCCCCCN", "CCCCCCCS", "CCCCCCCCl", "CCCCCCCF", "CCCCCCCBr", "CCCCCCC=O", "CCCCCCCC#N"]


def canon(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def answers(smiles_list=MOLECULES) -> dict[int, dict | None]:
    """A fake PubChem: the CID of the k-th candidate maps to the k-th molecule, with a name."""
    return {
        fresh.CID_STRIDE * k + fresh.OFFSET: {"SMILES": smiles, "IUPACName": f"name-{k}"}
        for k, smiles in enumerate(smiles_list, start=1)
    }


@pytest.fixture
def offline(monkeypatch):
    """No exclusions, three rows wanted, two CIDs to a request, and a fetch that is a table lookup that records each request."""
    monkeypatch.setattr(fresh, "_excluded", lambda: set())
    monkeypatch.setattr(fresh, "TARGET_ROWS", 3)
    monkeypatch.setattr(fresh, "CID_COUNT", len(MOLECULES))
    monkeypatch.setattr(fresh, "BATCH", 2)
    calls: list[list[int]] = []
    table = answers()

    def fetch(cids: list[int]):
        calls.append(list(cids))
        return {cid: table.get(cid) for cid in cids}

    return fetch, calls, table


def test_the_draw_takes_the_first_admitted_candidates_in_cid_order(offline):
    fetch, calls, _ = offline
    rows = fresh.draw(None, fetch=fetch, sleep=lambda _s: None)
    assert [r["pubchem_cid"] for r in rows] == [1875, 2875, 3875]
    assert [r["label"] for r in rows] == ["fresh1875", "fresh2875", "fresh3875"]
    assert [r["smiles"] for r in rows] == [canon(s) for s in MOLECULES[:3]]
    assert calls == [[1875, 2875], [3875, 4875]]  # a block at a time, and it stops asking once it has enough
    assert set(rows[0]) == {"label", "smiles", "pubchem_cid", "pubchem_name"}


def test_the_offset_is_not_one_the_other_draws_used():
    assert fresh.OFFSET < fresh.CID_STRIDE
    assert fresh.OFFSET not in (0, 500, 250, 750, 125, 375, 625)


def test_an_excluded_structure_and_a_repeat_within_the_draw_are_skipped(offline, monkeypatch):
    fetch, _, table = offline
    monkeypatch.setattr(fresh, "_excluded", lambda: {canon(MOLECULES[0])})
    table[fresh.CID_STRIDE * 3 + fresh.OFFSET] = {"SMILES": MOLECULES[1], "IUPACName": "again"}  # the same structure as candidate 2
    rows = fresh.draw(None, fetch=fetch, sleep=lambda _s: None)
    assert [r["smiles"] for r in rows] == [canon(MOLECULES[1]), canon(MOLECULES[3]), canon(MOLECULES[4])]


def test_a_candidate_pubchem_does_not_have_is_skipped_not_fatal(offline):
    fetch, _, table = offline
    table[1000 + fresh.OFFSET] = None
    rows = fresh.draw(None, fetch=fetch, sleep=lambda _s: None)
    assert rows[0]["pubchem_cid"] == 2875


def test_a_draw_that_died_resumes_to_exactly_what_an_uninterrupted_one_selects(offline, tmp_path):
    """The cache holds RAW answers, never decisions, so selection is a pure function of them in CID order."""
    fetch, _, table = offline
    uninterrupted = fresh.draw(None, fetch=fetch, sleep=lambda _s: None)

    cache = tmp_path / "raw.jsonl"
    asked: list[list[int]] = []

    def dies_on_the_second_request(cids: list[int]):
        asked.append(list(cids))
        if len(asked) == 2:
            raise fresh.census.ServerBusy("busy")
        return {cid: table.get(cid) for cid in cids}

    with pytest.raises(fresh.census.ServerBusy):
        fresh.draw(cache, fetch=dies_on_the_second_request, sleep=lambda _s: None)
    assert len(cache.read_text(encoding="utf-8").splitlines()) == 2  # the first request's answers were kept

    resumed_asked: list[list[int]] = []

    def counting(cids: list[int]):
        resumed_asked.append(list(cids))
        return {cid: table.get(cid) for cid in cids}

    resumed = fresh.draw(cache, fetch=counting, sleep=lambda _s: None)
    assert resumed == uninterrupted
    assert resumed_asked == [[3875, 4875]]  # only what it had not got


def test_the_cache_holds_raw_answers_and_nothing_about_selection(offline, tmp_path):
    fetch, _, _ = offline
    cache = tmp_path / "raw.jsonl"
    fresh.draw(cache, fetch=fetch, sleep=lambda _s: None)
    entries = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines()]
    assert all(set(e) == {"cid", "record"} for e in entries)
    assert entries[0]["record"] == {"SMILES": MOLECULES[0], "IUPACName": "name-1"}


def test_the_draw_pauses_between_requests_and_not_for_cached_ones(offline, tmp_path):
    fetch, _, _ = offline
    cache = tmp_path / "raw.jsonl"
    slept: list[float] = []
    fresh.draw(cache, fetch=fetch, sleep=slept.append)
    assert slept == [fresh.PAUSE_SECONDS] * 2 and fresh.PAUSE_SECONDS >= 1
    slept.clear()
    fresh.draw(cache, fetch=fetch, sleep=slept.append)
    assert slept == []


# --- the fetch: what a 429 did to the first version -----------------------------------------------------------------------------------

def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://pubchem.example/x", code, "msg", headers, io.BytesIO(b""))


class FakeResponse:
    def __init__(self, records: list[dict]):
        self._body = json.dumps({"PropertyTable": {"Properties": records}}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


def cids_of(request) -> list[int]:
    return [int(c) for c in request.full_url.split("/cid/")[1].split("/")[0].split(",")]


def record_for(cid: int) -> dict:
    return {"CID": cid, "SMILES": "CCCCCCCO", "IUPACName": f"n{cid}"}


def test_fetch_batch_returns_a_record_for_each_cid_and_none_for_one_pubchem_omitted():
    def urlopen(request, timeout):
        return FakeResponse([record_for(c) for c in cids_of(request) if c != 2])

    got = fresh.fetch_batch([1, 2, 3], urlopen=urlopen, sleep=lambda _s: None)
    assert got == {1: record_for(1), 2: None, 3: record_for(3)}


def test_a_429_is_waited_out_and_retried_never_recorded_as_absent():
    """THE DEFECT. The first version read every status but 500/503 as 'no such compound'; a throttle then blanked every later candidate."""
    attempts = []

    def urlopen(request, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise http_error(429, retry_after="7")
        return FakeResponse([record_for(c) for c in cids_of(request)])

    slept: list[float] = []
    got = fresh.fetch_batch([10, 20], urlopen=urlopen, sleep=slept.append)
    assert slept == [7, 7]  # Retry-After is honoured
    assert got == {10: record_for(10), 20: record_for(20)}


def test_a_429_without_retry_after_backs_off_and_persistent_throttling_stops_the_draw():
    slept: list[float] = []

    def urlopen(request, timeout):
        raise http_error(429)

    with pytest.raises(fresh.census.ServerBusy, match="throttling"):
        fresh.fetch_batch([10, 20], urlopen=urlopen, sleep=slept.append)
    assert len(slept) == fresh.ATTEMPTS
    assert slept == sorted(slept) and slept[0] >= 60 and slept[-1] > slept[0]


def test_a_404_for_a_list_is_bisected_so_one_missing_cid_cannot_blank_the_others():
    absent = {30}

    def urlopen(request, timeout):
        cids = cids_of(request)
        if absent & set(cids):
            raise http_error(404)
        return FakeResponse([record_for(c) for c in cids])

    got = fresh.fetch_batch([10, 20, 30, 40], urlopen=urlopen, sleep=lambda _s: None)
    assert got == {10: record_for(10), 20: record_for(20), 30: None, 40: record_for(40)}


def test_an_error_that_is_not_a_throttle_or_an_absence_is_raised_not_swallowed():
    def urlopen(request, timeout):
        raise http_error(400)

    with pytest.raises(urllib.error.HTTPError):
        fresh.fetch_batch([1], urlopen=urlopen, sleep=lambda _s: None)


def test_a_dropped_connection_is_retried():
    attempts = []

    def urlopen(request, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.URLError("reset")
        return FakeResponse([record_for(1)])

    assert fresh.fetch_batch([1], urlopen=urlopen, sleep=lambda _s: None) == {1: record_for(1)}


def test_a_draw_over_a_throttled_server_records_no_absence(offline, tmp_path):
    """End to end: a fetch that raises ServerBusy on its first request leaves an empty cache, so a resume cannot select from guesses."""
    cache = tmp_path / "raw.jsonl"

    def throttled(cids):
        raise fresh.census.ServerBusy("429")

    with pytest.raises(fresh.census.ServerBusy):
        fresh.draw(cache, fetch=throttled, sleep=lambda _s: None)
    assert cache.read_text(encoding="utf-8") == ""


def test_the_meta_describes_the_draw_without_a_row(offline):
    fetch, _, _ = offline
    rows = fresh.draw(None, fetch=fetch, sleep=lambda _s: None)
    meta = fresh.meta_for(rows, "0" * 64)
    assert meta["rows"] == 3 and meta["variant"] == "fresh_v1"
    assert meta["membership_sha256"] == registry.membership_hashes(rows)
    assert meta["membership_salt"] == registry.MEMBERSHIP_SALT
    assert meta["engine_consulted"] is False and "evaluation only" in meta["inspection_policy"]
    assert not any(row["smiles"] in json.dumps(meta) for row in rows)


# --- the scoring door -----------------------------------------------------------------------------------------------------------------

def test_only_needs_the_final_evaluation():
    with pytest.raises(SystemExit, match="--final-evaluation"):
        stage.build("x", allow_no_java=True, only="heldout_v6")


def test_only_refuses_a_population_that_is_not_in_the_final_evaluation():
    with pytest.raises(SystemExit, match="not a population of the final evaluation"):
        stage.build("x", allow_no_java=True, final_evaluation=True, only="not_a_population")


def test_only_scores_that_one_population_and_no_other(monkeypatch):
    loaded: list[str] = []

    def load(key, *, final_evaluation=False):
        loaded.append(key)
        return f"{key}.json", []

    monkeypatch.setattr(stage, "load_population", load)
    monkeypatch.setattr(stage, "_name_rows", lambda rows: [])
    monkeypatch.setattr(stage, "_classify", lambda rows, named: None)
    monkeypatch.setattr(stage, "_digest", lambda path: "0" * 64)
    key = next(k for k, _f, frozen in stage.POPULATIONS if frozen)
    artifact = stage.build("x", allow_no_java=True, final_evaluation=True, only=key)
    assert loaded == [key] and list(artifact["populations"]) == [key]
    loaded.clear()
    stage.build("x", allow_no_java=True, final_evaluation=True)
    assert len(loaded) == len([1 for _k, _f, frozen in stage.POPULATIONS if frozen]) + len([1 for _k, _f, frozen in stage.POPULATIONS if not frozen])


def test_a_population_hash_is_over_the_bytes_written(offline, tmp_path, monkeypatch):
    """The digest in the meta is of the exact bytes on disk (write_bytes), not of text the platform re-encodes."""
    fetch, _, _ = offline
    monkeypatch.setattr(fresh, "OUT", tmp_path / "fresh_v1.json")
    monkeypatch.setattr(fresh, "META", tmp_path / "fresh_v1.meta.json")
    # drive main() with the real draw over the fake PubChem
    real_draw = fresh.draw
    monkeypatch.setattr(fresh, "draw", lambda cache: real_draw(cache, fetch=fetch, sleep=lambda _s: None))
    monkeypatch.setattr(sys, "argv", ["naming_fresh_draw"])
    fresh.main()
    meta = json.loads((tmp_path / "fresh_v1.meta.json").read_text(encoding="utf-8"))
    assert meta["population_sha256"] == hashlib.sha256((tmp_path / "fresh_v1.json").read_bytes()).hexdigest()
    with pytest.raises(SystemExit, match="exists"):
        fresh.main()
