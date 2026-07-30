from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    """Raised when a plugin's manifest.toml is missing or malformed."""


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Static metadata read from a plugin's manifest.toml, without ever
    importing the plugin's own Python code.

    `plugin_id`/`dependencies` need to be known before any plugin code runs
    — for the dependency-ordered load below, and for listing/enabling
    plugins the user hasn't activated yet.
    """

    plugin_id: str
    version: str
    api_version: int
    display_name: str
    plugin_dir: Path
    dependencies: tuple[str, ...] = ()
    author: str = ""
    description: str = ""
    homepage: str = ""
    license: str = ""

    @classmethod
    def load(cls, plugin_dir: Path) -> PluginManifest:
        manifest_path = plugin_dir / "manifest.toml"
        if not manifest_path.exists():
            raise ManifestError(f"{plugin_dir} has no manifest.toml")
        with manifest_path.open("rb") as f:
            data = tomllib.load(f)
        try:
            plugin_id = data["plugin_id"]
            version = data["version"]
            api_version = data["api_version"]
            display_name = data["display_name"]
        except KeyError as exc:
            raise ManifestError(f"{manifest_path} missing required field: {exc}") from exc
        return cls(
            plugin_id=plugin_id,
            version=str(version),
            api_version=int(api_version),
            display_name=display_name,
            plugin_dir=plugin_dir,
            dependencies=tuple(data.get("dependencies", [])),
            author=data.get("author", ""),
            description=data.get("description", ""),
            homepage=data.get("homepage", ""),
            license=data.get("license", ""),
        )


def topological_order(
    manifests: list[PluginManifest],
) -> tuple[list[PluginManifest], dict[str, str]]:
    """Order manifests so every plugin loads after its declared dependencies.

    Returns `(ordered, skipped)` — `skipped` maps plugin_id -> a
    human-readable reason for every manifest that could not be placed in a
    valid order (a missing dependency, depending — directly or
    transitively — on something skipped, or a dependency cycle).
    """
    by_id = {m.plugin_id: m for m in manifests}
    skipped: dict[str, str] = {}
    valid_ids = set(by_id)

    # Repeatedly drop anything with a missing or already-skipped dependency,
    # so a plugin depending on a broken plugin is itself treated as broken
    # rather than silently loaded as if the dependency didn't matter.
    changed = True
    while changed:
        changed = False
        for plugin_id in list(valid_ids):
            manifest = by_id[plugin_id]
            missing = [dep for dep in manifest.dependencies if dep not in by_id]
            if missing:
                skipped[plugin_id] = f"missing dependencies: {', '.join(missing)}"
                valid_ids.discard(plugin_id)
                changed = True
                continue
            broken = [dep for dep in manifest.dependencies if dep in skipped]
            if broken:
                skipped[plugin_id] = f"depends on skipped plugin(s): {', '.join(broken)}"
                valid_ids.discard(plugin_id)
                changed = True

    remaining = {pid: by_id[pid] for pid in valid_ids}
    dependents: dict[str, list[str]] = {pid: [] for pid in remaining}
    in_degree: dict[str, int] = {}
    for plugin_id, manifest in remaining.items():
        deps = [dep for dep in manifest.dependencies if dep in remaining]
        in_degree[plugin_id] = len(deps)
        for dep in deps:
            dependents[dep].append(plugin_id)

    queue = sorted(pid for pid, degree in in_degree.items() if degree == 0)
    ordered: list[PluginManifest] = []
    seen: set[str] = set()
    while queue:
        plugin_id = queue.pop(0)
        if plugin_id in seen:
            continue
        seen.add(plugin_id)
        ordered.append(remaining[plugin_id])
        for dependent in dependents[plugin_id]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
        queue.sort()

    for plugin_id in remaining:
        if plugin_id not in seen:
            skipped[plugin_id] = "dependency cycle"

    return ordered, skipped
