from __future__ import annotations

from pathlib import Path

import pytest

from openchem.plugins.manifest import ManifestError, PluginManifest, topological_order


def _write_manifest(dir_path: Path, plugin_id: str, dependencies: list[str] | None = None) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    deps = "[" + ", ".join(repr(d) for d in (dependencies or [])) + "]"
    (dir_path / "manifest.toml").write_text(
        f'plugin_id = "{plugin_id}"\n'
        f'version = "1.0.0"\n'
        f"api_version = 1\n"
        f'display_name = "{plugin_id}"\n'
        f"dependencies = {deps}\n"
    )
    return dir_path


def test_load_manifest_reads_required_and_optional_fields(tmp_path: Path):
    plugin_dir = _write_manifest(tmp_path / "a", "a")
    manifest = PluginManifest.load(plugin_dir)
    assert manifest.plugin_id == "a"
    assert manifest.version == "1.0.0"
    assert manifest.api_version == 1
    assert manifest.display_name == "a"
    assert manifest.dependencies == ()
    assert manifest.author == ""


def test_load_manifest_missing_directory_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        PluginManifest.load(tmp_path / "does_not_exist")


def test_load_manifest_missing_required_field_raises(tmp_path: Path):
    plugin_dir = tmp_path / "bad"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.toml").write_text('version = "1.0.0"\n')
    with pytest.raises(ManifestError):
        PluginManifest.load(plugin_dir)


def test_topological_order_valid_chain(tmp_path: Path):
    a = PluginManifest.load(_write_manifest(tmp_path / "a", "a"))
    b = PluginManifest.load(_write_manifest(tmp_path / "b", "b", ["a"]))
    c = PluginManifest.load(_write_manifest(tmp_path / "c", "c", ["b"]))

    ordered, skipped = topological_order([c, a, b])

    assert [m.plugin_id for m in ordered] == ["a", "b", "c"]
    assert skipped == {}


def test_topological_order_missing_dependency(tmp_path: Path):
    a = PluginManifest.load(_write_manifest(tmp_path / "a", "a", ["ghost"]))

    ordered, skipped = topological_order([a])

    assert ordered == []
    assert "missing dependencies" in skipped["a"]


def test_topological_order_cycle(tmp_path: Path):
    a = PluginManifest.load(_write_manifest(tmp_path / "a", "a", ["b"]))
    b = PluginManifest.load(_write_manifest(tmp_path / "b", "b", ["a"]))

    ordered, skipped = topological_order([a, b])

    assert ordered == []
    assert skipped["a"] == "dependency cycle"
    assert skipped["b"] == "dependency cycle"


def test_topological_order_transitively_broken(tmp_path: Path):
    a = PluginManifest.load(_write_manifest(tmp_path / "a", "a", ["ghost"]))
    b = PluginManifest.load(_write_manifest(tmp_path / "b", "b", ["a"]))

    ordered, skipped = topological_order([a, b])

    assert ordered == []
    assert "missing dependencies" in skipped["a"]
    assert "skipped plugin" in skipped["b"]
