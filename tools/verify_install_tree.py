"""Check a built tree against the manifest that was made for it.

    uv run --no-sync python tools/verify_install_tree.py --manifest src/openchem/_integrity.py --root dist/OpenChemStudio/_internal

`build.ps1` runs this right after the freeze, while the generated manifest still
exists. It is the build-time half of the proof that the spec's source-to-installed
mapping is right: the same `install_check.verify` the running app uses, over the
tree PyInstaller actually produced. Exit 0 only for `verified`.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "src"))
    from openchem import install_check

    spec = importlib.util.spec_from_file_location("generated_integrity", args.manifest)
    if spec is None or spec.loader is None or not args.manifest.is_file():
        print(f"verify_install_tree: no manifest at {args.manifest}", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        files = install_check.validate_manifest(getattr(module, "SCHEMA", None), getattr(module, "FILES", None))
    except install_check.InstallCheckError as exc:
        print(f"verify_install_tree: bad manifest: {exc}", file=sys.stderr)
        return 2
    result = install_check.verify(files, args.root)
    print(f"verify_install_tree: {result.report()}")
    return 0 if result.status is install_check.Status.VERIFIED else 1


if __name__ == "__main__":
    sys.exit(main())
