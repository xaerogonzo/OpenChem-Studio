"""`tools/fork_port.py`: what it ports, what it refuses to, and that its three-way merge means what VENDORING.md says.

The fork sync is done once a round, by hand, at the end, when nobody has time to debug the tool. Every rule below was learned from a
sync that went wrong: a hand-kept test list that missed `test_namer_preference_key.py` (the fork's stale copy failed 24 times while every
ported engine file was fine), a classifier that judged a test by a WORD in its prose, and a merge whose base was the wrong commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import fork_port as port  # noqa: E402

NAMER = "openchem.vendor.iupac_namer"


def test_the_rewrite_is_the_inverse_of_the_vendoring_substitution():
    text = (
        f"from {NAMER} import name_smiles\n"
        f"from {NAMER}.perception import charge_perception\n"
        f"import {NAMER}.engine as engine\n"
        "os.environ['OPENCHEM_NAMER_DEBUG'] = '1'\n"
        "os.environ['OPENCHEM_NAMER_OWNERSHIP'] = 'record'\n"
        "see src/openchem/vendor/KNOWN_LIMITATIONS.md\n"
    )
    out = port.rewrite(text)
    assert "openchem" not in out.lower(), out
    assert "from iupac_namer import name_smiles" in out
    assert "from iupac_namer.perception import charge_perception" in out
    assert "import iupac_namer.engine as engine" in out
    assert "IUPAC_NAMER_DEBUG" in out and "IUPAC_NAMER_OWNERSHIP" in out
    assert "see KNOWN_LIMITATIONS.md" in out


@pytest.mark.parametrize(
    "source, expected",
    [
        # reaches the engine through the vendored namer only
        (f"from {NAMER} import name_smiles\ndef test_a():\n    assert name_smiles('C')\n", "portable"),
        # a comment or docstring that CITES the benchmark tree does not read it (the first classifier judged by prose)
        (f'"""benchmarks/naming/heldout.json"""\nfrom {NAMER} import name_smiles\n# see tools/naming_probe.py\n', "portable"),
        (f'from {NAMER} import name_smiles\ndef test_a():\n    """tools/naming_probe.py"""\n', "portable"),
        # any other layer of openchem is a layer the fork does not have
        (f"from {NAMER} import name_smiles\nfrom openchem.chem import naming_providers\n", "app-reading"),
        (f"import {NAMER}\nimport openchem.services.foo\n", "app-reading"),
        # a repository tool
        (f"from {NAMER} import name_smiles\nimport naming_populations\n", "app-reading"),
        # a path built from the repository layout, in code
        (f"from {NAMER} import name_smiles\nP = ROOT / 'x'\nQ = 'benchmarks/naming/corpus.json'\n", "app-reading"),
        (f"from {NAMER} import name_smiles\nQ = 'src\\\\openchem\\\\vendor'\n", "app-reading"),
        # never touches the namer
        ("import json\ndef test_a():\n    assert json.dumps([])\n", "unrelated"),
        # unparseable: not ported silently
        ("def broken(:\n", "app-reading"),
    ],
)
def test_a_test_is_classified_by_its_syntax(source, expected):
    assert port.classify_test(source) == expected


def test_paths_land_where_the_fork_keeps_them():
    text_portable = f"from {NAMER} import name_smiles\n"
    text_app = f"from {NAMER} import name_smiles\nfrom openchem.chem import naming_providers\n"
    assert port.fork_path("src/openchem/vendor/iupac_namer/engine.py") == "iupac_namer/engine.py"
    assert port.fork_path("src/openchem/vendor/data/functional_groups.json") == "data/functional_groups.json"
    assert port.fork_path("tests/vendor/iupac_namer/test_x.py") == "tests/test_x.py"
    assert port.fork_path("tests/test_namer_known_defects.py", text_portable) == "tests/test_namer_known_defects.py"
    assert port.fork_path("tests/test_namer_probe_shapes.py", text_app) is None, "an app-reading test is not ported"
    assert port.fork_path("tests/test_anything.py") is None, "a test whose text was not supplied cannot be judged portable"
    for written in ("CHANGELOG.md", "KNOWN_LIMITATIONS.md", "BENCHMARK_HISTORY.md", "VENDORING.md"):
        assert port.fork_path(f"src/openchem/vendor/{written}") is None, written
    assert port.fork_path("tools/naming_probe.py") is None
    assert port.fork_path("benchmarks/naming/corpus.json") is None


def test_the_three_way_merge_keeps_the_forks_own_lines_and_takes_the_repositorys_change():
    base = "a\nb\nc\nd\ne\n"
    ours = "a\nb\nc\nd\ne\nFORK-ONLY\n"  # a difference the fork holds on purpose
    theirs = "a\nB\nc\nd\ne\n"  # this repository's change since the base
    merged, conflicts = port.merge_file(ours, base, theirs)
    assert conflicts == 0
    assert merged == "a\nB\nc\nd\ne\nFORK-ONLY\n"


def test_a_conflict_is_counted_not_hidden():
    merged, conflicts = port.merge_file("a\nFORK\nc\n", "a\nb\nc\n", "a\nREPO\nc\n")
    assert conflicts == 1
    assert "<<<<<<<" in merged and "FORK" in merged and "REPO" in merged


def test_a_wrong_base_reads_as_conflicts_not_as_a_clean_merge():
    """The base is the commit whose src the fork ALREADY HOLDS. Give the merge the wrong one and the same two edits collide, which is
    how a wrong `--base` announces itself, rather than merging the wrong delta quietly."""
    right_base = "x = 1\ny = 2\n"
    ours = "x = 1\ny = 2\n"  # the fork already holds the base
    theirs = "x = 1\ny = 3\n"
    assert port.merge_file(ours, right_base, theirs) == ("x = 1\ny = 3\n", 0)
    wrong_base = "x = 0\ny = 0\n"  # a commit the fork does not hold
    merged, conflicts = port.merge_file(ours, wrong_base, theirs)
    assert conflicts >= 1


def test_the_merge_preserves_line_endings(tmp_path):
    crlf_ours = "a\r\nb\r\n"
    merged, conflicts = port.merge_file(crlf_ours, "a\r\nb\r\n", "a\r\nB\r\n")
    assert conflicts == 0
    assert merged == "a\r\nB\r\n"


def test_numstat_sums_added_and_removed_lines_between_two_commits(tmp_path):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    git("config", "core.autocrlf", "false")
    (tmp_path / "engine.py").write_text("1\n2\n3\n", encoding="utf-8", newline="")
    git("add", ".")
    git("commit", "-qm", "base")
    (tmp_path / "engine.py").write_text("1\nTWO\n3\n4\n", encoding="utf-8", newline="")
    git("commit", "-qam", "head")
    # line 2 rewritten (one removed, one added) and line 4 appended (one added)
    assert port.numstat(tmp_path, "HEAD~1", "HEAD", ["engine.py"]) == (2, 1)


def test_merge_into_keeps_the_forks_crlf_and_merges_against_lf_history(tmp_path):
    """The fork's working copy is CRLF on Windows and this repository's text comes from git as LF. Merging the raw bytes would
    make every line differ and turn the merge into one conflict; writing LF back would rewrite every line ending of a file the fork
    keeps as it is. (Mutation: skip the normalisation, or the write-back, and one of the two assertions fails.)"""
    dest = tmp_path / "engine.py"
    dest.write_bytes(b"a\r\nb\r\nc\r\nFORK-ONLY\r\n")
    conflicts = port.merge_into(dest, "a\nb\nc\n", "a\nB\nc\n")
    assert conflicts == 0
    assert dest.read_bytes() == b"a\r\nB\r\nc\r\nFORK-ONLY\r\n"


def test_merge_into_leaves_an_lf_file_lf_and_a_dry_run_writes_nothing(tmp_path):
    dest = tmp_path / "engine.py"
    dest.write_bytes(b"a\nb\nc\n")
    assert port.merge_into(dest, "a\nb\nc\n", "a\nB\nc\n", write=False) == 0
    assert dest.read_bytes() == b"a\nb\nc\n"
    assert port.merge_into(dest, "a\nb\nc\n", "a\nB\nc\n") == 0
    assert dest.read_bytes() == b"a\nB\nc\n"


def test_merge_into_reports_a_conflict_and_still_writes_the_markers(tmp_path):
    dest = tmp_path / "engine.py"
    dest.write_bytes(b"a\nFORK\nc\n")
    assert port.merge_into(dest, "a\nb\nc\n", "a\nREPO\nc\n") == 1
    assert b"<<<<<<<" in dest.read_bytes()
