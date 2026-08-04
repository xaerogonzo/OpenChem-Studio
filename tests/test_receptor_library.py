"""The catalogue's own consistency, and the fetch/cache behaviour.

These tests never touch the network. Whether the 49 entries are
scientifically right was settled by fetching all of them from RCSB and
confirming each ligand code resolves to a box whose atom count matches
the ligand's known formula -- indinavir 45, donepezil 28, diazepam 20,
ergotamine 43, GABA 7. That is a one-off validation, not something to
re-run on every suite.

What IS worth guarding here is everything that can rot without anyone
noticing: a duplicated PDB id, a blank ligand code, a family that lost its
last member, or a search that stops finding a target by the name people
type.
"""

from __future__ import annotations

import pytest

from openchem.chem import receptor_library as library
from openchem.services import receptor_library_service as service


def test_every_entry_names_a_binding_site():
    """A blank `ligand_code` is a dead entry -- the user picks the target
    and the box derivation raises. This is the field that makes the
    catalogue worth having, so nothing may ship without it."""
    missing = [e.pdb_id for e in library.RECEPTOR_LIBRARY if not e.ligand_code.strip()]

    assert missing == []


def test_pdb_ids_are_unique_and_well_formed():
    ids = [e.pdb_id for e in library.RECEPTOR_LIBRARY]

    assert len(ids) == len(set(ids)), "a duplicate id would list the same structure twice"
    assert all(len(i) == 4 and i.isalnum() and i.isupper() for i in ids)


def test_ligand_codes_look_like_chemical_component_ids():
    """PDB component ids are 1-3 alphanumeric characters, upper case. A
    lower-case one silently fails to match, since the lookup upper-cases
    the structure's residue names but compares against this verbatim."""
    for entry in library.RECEPTOR_LIBRARY:
        code = entry.ligand_code
        assert 1 <= len(code) <= 3, f"{entry.pdb_id}: {code!r}"
        assert code == code.upper(), f"{entry.pdb_id}: {code!r} must be upper case"


def test_resolutions_are_plausible():
    """A zero or absurd resolution means a field was filled in by hand
    rather than read from the API."""
    for entry in library.RECEPTOR_LIBRARY:
        assert 0.5 <= entry.resolution_angstrom <= 6.0, entry.pdb_id


def test_the_catalogue_is_ascii():
    """Greek letters in a target name crash on a cp1252 stream -- a
    Windows console, or a log handler that did not ask for UTF-8. The
    names use spelled-out forms for that reason, and `search` folds the
    symbols so pasting them still works."""
    for entry in library.RECEPTOR_LIBRARY:
        text = f"{entry.target}{entry.family}{entry.ligand_name}{entry.caveat}{entry.state}"
        assert text.isascii(), f"{entry.pdb_id}: {entry.target}"


def test_families_are_covered_and_ordered():
    families = library.families()

    assert len(families) == len(set(families))
    assert all(library.by_family(f) for f in families), "no empty family"
    # Every entry belongs to a listed family, so nothing is unreachable by
    # browsing.
    assert {e.family for e in library.RECEPTOR_LIBRARY} == set(families)


def test_find_is_case_insensitive():
    assert library.find("4dkl") is library.find("4DKL")
    assert library.find("nope") is None


# --- search: the part a user actually touches ----------------------------


@pytest.mark.parametrize(
    ("query", "expected_pdb_id"),
    [
        ("mu-opioid", "4DKL"),
        ("mu opioid", "4DKL"),      # spacing folded away
        ("MuOpioid", "4DKL"),       # and case
        ("μ-opioid", "4DKL"),  # pasted Greek folds to the spelled form
        ("fentanyl", "8EF5"),       # searching by the LIGAND, not the target
        ("diazepam", "6HUP"),
        ("astemizole", "8ZYO"),
        ("5-HT2A", "6A93"),
        ("5ht2a", "6A93"),
        ("hERG", "8ZYO"),
        ("nav1.7", "6J8G"),
    ],
)
def test_search_finds_the_expected_entry(query, expected_pdb_id):
    assert expected_pdb_id in {e.pdb_id for e in library.search(query)}


def test_an_empty_query_returns_everything():
    assert len(library.search("   ")) == len(library.RECEPTOR_LIBRARY)


def test_a_query_matching_nothing_returns_nothing():
    assert library.search("zzzznotarealtarget") == []


def test_the_state_is_searchable():
    inactive = library.search("inactive")

    assert inactive
    assert all(e.state == "inactive" for e in inactive)


def test_searching_active_also_returns_inactive_entries():
    """A consequence of substring matching, and left as it is on purpose.
    Narrowing "active" to whole-word matches would break "5ht2a" and
    "nav1.7", which only work BECAUSE punctuation and spacing are folded
    away -- and those are what people actually type. Someone searching a
    state can read the column; someone searching a target cannot be asked
    to guess the punctuation."""
    results = {e.state for e in library.search("active")}

    assert "active" in results and "inactive" in results


# --- the fetch/cache layer ------------------------------------------------


def test_cache_paths_use_the_right_suffix_per_format():
    assert service.cached_path("4dkl", "pdb").name == "4DKL.pdb"
    assert service.cached_path("4dkl", "mmcif").name == "4DKL.cif"


def test_a_cached_structure_is_returned_without_any_network_call(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "cache_directory", lambda: tmp_path)

    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("fetch_structure went to the network despite a cache hit")

    monkeypatch.setattr(service, "open_url", explode)
    (tmp_path / "4DKL.pdb").write_text("HEADER    CACHED\nEND\n", encoding="utf-8")

    text, source_format = service.fetch_structure("4DKL")

    assert "CACHED" in text
    assert source_format == "pdb"


def test_a_download_is_cached_for_next_time(tmp_path, monkeypatch):
    import io

    monkeypatch.setattr(service, "cache_directory", lambda: tmp_path)
    calls: list[str] = []

    def fake_open(url, timeout, headers=None):
        calls.append(url)
        return io.BytesIO(b"HEADER    DOWNLOADED\nEND\n")

    monkeypatch.setattr(service, "open_url", fake_open)

    first, _ = service.fetch_structure("1HSG")
    second, _ = service.fetch_structure("1HSG")

    assert "DOWNLOADED" in first and first == second
    assert len(calls) == 1, "the second call must be served from disk"


def test_mmcif_is_tried_when_no_pdb_exists(tmp_path, monkeypatch):
    """RCSB genuinely has no `.pdb` for deposits too large for the
    fixed-column format -- a normal outcome for big cryo-EM structures,
    not an error. 7B6W is one of them."""
    import io

    monkeypatch.setattr(service, "cache_directory", lambda: tmp_path)

    def fake_open(url, timeout, headers=None):
        if url.endswith(".pdb"):
            raise OSError("404")
        return io.BytesIO(b"data_7B6W\n")

    monkeypatch.setattr(service, "open_url", fake_open)

    text, source_format = service.fetch_structure("7B6W")

    assert source_format == "mmcif"
    assert "data_7B6W" in text
    assert (tmp_path / "7B6W.cif").is_file()


def test_a_total_failure_reports_how_to_proceed_manually(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "cache_directory", lambda: tmp_path)
    monkeypatch.setattr(
        service, "open_url", lambda *a, **k: (_ for _ in ()).throw(OSError("no network"))
    )

    with pytest.raises(RuntimeError, match="Import Macromolecule"):
        service.fetch_structure("4DKL")


def test_an_unwritable_cache_does_not_lose_the_download(tmp_path, monkeypatch):
    """Failing to cache must cost a re-download next time, not the
    structure the user just successfully fetched."""
    import io

    monkeypatch.setattr(service, "cache_directory", lambda: tmp_path)
    monkeypatch.setattr(service, "open_url", lambda *a, **k: io.BytesIO(b"HEADER  OK\nEND\n"))
    monkeypatch.setattr(
        service.Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only"))
    )

    text, _ = service.fetch_structure("4DKL")

    assert "OK" in text


def test_metadata_carries_the_ligand_code_forward():
    """Without it the docking panel cannot re-derive the box later, and
    the user is back to remembering which component defined the site."""
    entry = library.find("4DKL")

    metadata = service.entry_metadata(entry)

    assert metadata["ligand_code"] == entry.ligand_code
    assert metadata["pdb_id"] == "4DKL"
    assert "rcsb.org" in metadata["source_url"]
