"""The command-line project argument a double-clicked .ocsproj arrives as."""

from __future__ import annotations

from openchem.main import project_argument


def test_first_existing_project_file_is_returned(tmp_path):
    first = tmp_path / "a.ocsproj"
    second = tmp_path / "b.ocsproj"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    assert project_argument(["-platform", "windows", str(first), str(second)]) == first


def test_upper_case_extension_counts(tmp_path):
    path = tmp_path / "A.OCSPROJ"
    path.write_text("{}", encoding="utf-8")
    assert project_argument([str(path)]) == path


def test_missing_wrong_type_or_no_arguments_open_nothing(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("x", encoding="utf-8")
    assert project_argument([]) is None
    assert project_argument([str(tmp_path / "gone.ocsproj")]) is None
    assert project_argument([str(other)]) is None
    assert project_argument([str(tmp_path)]) is None  # a folder is not a project
