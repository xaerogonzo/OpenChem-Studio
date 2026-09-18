"""Two OPSIN calls at once must not clobber each other's input.

**py2opsin WRITES ITS INPUT TO A FIXED RELATIVE FILENAME**, `tmp_fpath`,
whose default is `py2opsin_temp_input.txt` resolved against the current
working directory -- no lock, no per-call uniqueness. Every caller in a
process shared it.

The symptom is not a crash. The loser of a collision reads a name it was not
given, or an empty file, so OPSIN reports failure -- and
`verify_name_round_trip` reads that as MISMATCH, which
`derived_name_for_structure` turns into WITHHOLDING A CORRECT NAME. The app
looks unable to name a structure it names perfectly well.

It is reachable here because descriptor computation is asynchronous: two
naming calculations can be in flight together. It was also reachable in the
test suite, which is how it was found -- measured 2026-09-17, the same four
naming test files passed, passed, then failed on an unchanged tree, and every
failure was an OPSIN round-trip assertion.

Measured directly, 16 concurrent calls over 4 threads alternating two names:

    shared default path     5/16 parsed back to the right structure
    isolated per call      16/16

The losing calls come back as an empty string, or raise FileNotFoundError --
py2opsin removes `tmp_fpath` in a `finally`, so one caller deletes the file
another is still using. That cleanup is also why the shared file does not
normally linger: the copy that ended up committed to this repository came
from an interrupted run, not from ordinary operation.

These tests are skipped without a JRE, because without one every OPSIN call
fails for an unrelated reason and the assertions would pass vacuously.
"""

from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import naming_providers

pytestmark = pytest.mark.skipif(
    shutil.which("java") is None,
    reason="OPSIN needs a bare `java` on PATH; without it these pass vacuously",
)

SHARED_DEFAULT = "py2opsin_temp_input.txt"

# Two structures whose names are long enough that a clobbered input cannot
# accidentally still parse to the right thing.
BENZOIC = ("OC(=O)c1ccccc1", "benzoic acid")
CAFFEINE = ("Cn1cnc2c1c(=O)n(C)c(=O)n2C", "1,3,7-trimethylpurine-2,6-dione")


def test_the_scratch_file_is_unique_per_call_and_cleaned_up():
    seen = []
    for _ in range(3):
        with naming_providers._opsin_scratch() as path:
            seen.append(path)
            assert os.path.exists(path), "the file should exist inside the scope"
        assert not os.path.exists(path), "the file should be gone after the scope"

    assert len(set(seen)) == len(seen), f"paths repeated: {seen}"


def test_a_naming_call_leaves_nothing_in_the_working_directory(tmp_path, monkeypatch):
    """THE DEFECT, ASSERTED AS AN ABSENCE. Nothing may be written to the CWD
    under py2opsin's shared default name."""
    monkeypatch.chdir(tmp_path)

    naming_providers.opsin_structure_for_name("benzoic acid")

    assert not (tmp_path / SHARED_DEFAULT).exists(), (
        "a naming call still writes py2opsin's shared default file into the "
        "working directory, so two callers can still collide"
    )
    assert list(tmp_path.iterdir()) == [], (
        f"unexpected files left behind: {[p.name for p in tmp_path.iterdir()]}"
    )


def test_concurrent_callers_each_get_their_own_answer():
    """The contract, exercised the way the app reaches it.

    Interleaved on purpose and repeated, because a collision is a race: a
    single pass can miss it. With the shared filename this failed; the point
    of repeating is that "passed once" was never evidence.
    """
    requests = [BENZOIC, CAFFEINE] * 6

    def resolve(pair):
        smiles, name = pair
        parsed = naming_providers.opsin_structure_for_name(name)
        got = Chem.MolFromSmiles(parsed.smiles)
        want = Chem.MolFromSmiles(smiles)
        return name, Chem.MolToSmiles(got) == Chem.MolToSmiles(want)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(resolve, requests))

    wrong = [name for name, ok in results if not ok]
    assert not wrong, f"{len(wrong)} of {len(results)} concurrent calls got the wrong structure: {set(wrong)}"


def test_a_correct_name_is_not_withheld_under_concurrency():
    """The user-visible half: the round-trip verdict is what decides whether
    a name is shown, so a collision has to be shown not to reach it."""
    novel = Chem.MolFromSmiles("O=C(Nc1ccc(-c2ccncc2)cc1)Nc1cccc(C(F)(F)F)c1")
    aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")

    def derive(mol):
        return naming_providers.derived_name_for_structure(mol).name

    with ThreadPoolExecutor(max_workers=4) as pool:
        names = list(pool.map(derive, [novel, aspirin] * 4))

    assert all(names), "a naming call returned nothing under concurrency"
    assert any("urea" in n for n in names)


def test_py2opsins_default_is_still_a_path_every_caller_would_share():
    """Breaking the guard rather than trusting it -- and deterministically.

    The hazard is structural: `tmp_fpath` defaults to a bare relative
    filename, so every caller in a process resolves it to the same file.
    Asserting that directly beats re-running the race, which is exactly the
    kind of test that passes 5 times in 16 and proves nothing.

    If py2opsin ever ships a safe default this fails, which is the right
    alarm: the isolation above would then be redundant rather than wrong.
    """
    import inspect

    py2opsin = pytest.importorskip("py2opsin").py2opsin
    default = inspect.signature(py2opsin).parameters["tmp_fpath"].default

    assert default == SHARED_DEFAULT, f"py2opsin default changed to {default!r}"
    assert Path(default).parent == Path("."), (
        f"{default!r} now names a directory, so callers may no longer share it"
    )
