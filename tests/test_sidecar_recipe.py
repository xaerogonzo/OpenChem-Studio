"""A sidecar recipe is the freeze of how an environment was built, not the tree.

`tools/sidecar_recipe.py` loads, freezes and verifies. It never installs packages
or downloads models. A missing data file is `absent`, not a passing verify.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "sidecar_recipe_tool", ROOT / "tools" / "sidecar_recipe.py"
)
tool = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["sidecar_recipe_tool"] = tool
_spec.loader.exec_module(tool)

_LOCK = "aizynthfinder==4.4.1\npyarrow==20.0.0\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _recipe(tmp: Path, *, files: list[dict] | None = None, lock: str = _LOCK) -> Path:
    lock_path = tmp / "planner_env_lock.txt"
    lock_path.write_bytes(lock.encode("utf-8"))
    body = {
        "kind": "sidecar-recipe",
        "format": 1,
        "id": "probe",
        "python": "3.12",
        "lockfile": "planner_env_lock.txt",
        "lockfile_sha256": _sha(lock.encode("utf-8")),
        "pins": ["aizynthfinder==4.4.1", "pyarrow<21"],
        "obtain_data": "download_public_data",
        "files": files if files is not None else [],
        "smoke_package": "aizynthfinder",
        "smoke_version": "4.4.1",
    }
    path = tmp / "sidecar_recipe.json"
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def test_an_unknown_key_is_refused(tmp_path: Path) -> None:
    path = _recipe(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["extra"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(tool.RecipeError, match="unknown key"):
        tool.load(path)


def test_verify_without_data_does_not_claim_the_files_are_present(tmp_path: Path) -> None:
    blob = b"stock"
    path = _recipe(
        tmp_path,
        files=[{"path": "zinc_stock.hdf5", "sha256": _sha(blob), "bytes": len(blob)}],
    )
    report = tool.verify(path)
    assert report.ok is False
    assert report.lock == "ok"
    assert report.data == "absent"


def test_verify_passes_when_the_data_files_match(tmp_path: Path) -> None:
    blob = b"stock"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "zinc_stock.hdf5").write_bytes(blob)
    path = _recipe(
        tmp_path,
        files=[{"path": "zinc_stock.hdf5", "sha256": _sha(blob), "bytes": len(blob)}],
    )
    report = tool.verify(path, data_dir=data_dir)
    assert report.ok is True
    assert report.lock == "ok"
    assert report.data == "ok"


def test_a_wrong_hash_is_mismatch_not_ok(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "zinc_stock.hdf5").write_bytes(b"other")
    path = _recipe(
        tmp_path,
        files=[{"path": "zinc_stock.hdf5", "sha256": _sha(b"stock"), "bytes": 5}],
    )
    report = tool.verify(path, data_dir=data_dir)
    assert report.ok is False
    assert report.data == "mismatch"


def test_a_changed_lockfile_is_mismatch(tmp_path: Path) -> None:
    path = _recipe(tmp_path)
    (tmp_path / "planner_env_lock.txt").write_text("aizynthfinder==9.9.9\n", encoding="utf-8")
    report = tool.verify(path)
    assert report.ok is False
    assert report.lock == "mismatch"


def test_freeze_writes_hashes_from_the_data_folder(tmp_path: Path) -> None:
    path = _recipe(tmp_path, files=[{"path": "uspto_model.onnx", "sha256": "", "bytes": 0}])
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = b"onnx-bytes"
    (data_dir / "uspto_model.onnx").write_bytes(payload)
    tool.freeze(path, data_dir=data_dir)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["files"][0]["sha256"] == _sha(payload)
    assert written["files"][0]["bytes"] == len(payload)


def test_recreate_commands_install_from_the_lockfile_not_the_two_pins(tmp_path: Path) -> None:
    path = _recipe(tmp_path)
    lines = tool.recreate_commands(tool.load(path))
    joined = "\n".join(lines)
    assert "planner_env_lock.txt" in joined
    assert "uv pip install" in joined
    assert "aizynthfinder==4.4.1 pyarrow<21" not in joined


def test_committed_aizynth_recipe_matches_the_lock_and_the_setup_pins() -> None:
    from openchem.services.aizynth_setup import PLANNER_PACKAGE, PYARROW_PIN, _TARGET_PYTHON

    path = ROOT / "benchmarks" / "synthesis" / "sidecar_recipe.json"
    recipe = tool.load(path)
    assert recipe.python == _TARGET_PYTHON
    assert PLANNER_PACKAGE in recipe.pins
    assert PYARROW_PIN in recipe.pins
    report = tool.verify(path)
    assert report.lock == "ok"
    assert report.data in {"ok", "absent"}
    if report.data == "absent":
        assert report.ok is False
    else:
        assert report.ok is True
