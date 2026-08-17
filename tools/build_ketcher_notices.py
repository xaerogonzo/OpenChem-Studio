"""Generate `resources/ketcher/THIRD-PARTY-NOTICES.txt` from the lockfile.

`resources/ketcher/dist/` is a BUNDLE, not a library. EPAM's Miew 0.11.1 is
in there and so is three.js, against a build tree of 429 packages -- and
**their notices are not recoverable from the artifact**. The vite build
strips comments even with minification off, so exactly two licence banners
survive in 35 MB. Registering Ketcher's own Apache-2.0 licence is necessary
and was never sufficient.

So the notices are produced HERE, from `tools/ketcher-host/package-lock.json`
plus the licence files in `node_modules/`, and committed alongside the dist
for the same reason the dist is committed: CI has no node, and a fresh clone
must carry what it redistributes.

WHAT THIS INCLUDES, AND WHY IT IS AN OVER-APPROXIMATION
-------------------------------------------------------
Every package the lockfile does NOT mark `dev: true` -- 318 of 429. That is
deliberately more than the bundle contains, for two reasons worth knowing:

  * A build-time tool can be a runtime DEPENDENCY of a runtime package.
    `@emotion/babel-plugin` is a normal dependency of `@emotion/react`, and
    drags the whole `@babel/*` set in with it. Those run at build time and
    are not in the output.
  * vite tree-shakes, so some genuine runtime dependencies contribute no
    code to the bundle at all.

Narrowing it would mean deciding, per package, whether any of its code
survived into a 35 MB comment-stripped artifact. **Over-attribution is the
safe direction and under-attribution is not**, so the list is not narrowed
and this paragraph says so rather than implying precision the method does
not have.

RUN IT after `npm install` in `tools/ketcher-host/`, alongside `npm run
build`:

    uv run --no-sync python tools/build_ketcher_notices.py
    uv run --no-sync python tools/build_ketcher_notices.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCKFILE = ROOT / "tools" / "ketcher-host" / "package-lock.json"
NODE_MODULES = ROOT / "tools" / "ketcher-host"
OUTPUT = ROOT / "src" / "openchem" / "resources" / "ketcher" / "THIRD-PARTY-NOTICES.txt"

HEADER_MARKER = "GENERATED FROM tools/ketcher-host/package-lock.json"
HASH_MARKER = "LOCKFILE SHA256: "

#: Filenames that carry a licence text, in the order they are preferred.
LICENCE_NAMES = ("LICENSE", "LICENCE", "LICENSE.md", "LICENCE.md", "LICENSE.txt", "COPYING")


def _normalised(path: Path) -> str:
    """Text with line endings normalised.

    The hash must not depend on the checkout's line endings: this repository
    has `core.autocrlf=true` and no `.gitattributes`, so the same commit is
    CRLF on Windows and LF on a Linux runner. `build_sources_doc.py` carries
    the same note for the same reason -- hashing raw bytes made `--check`
    fail on CI for a reason unrelated to content.
    """
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _lockfile_hash() -> str:
    return hashlib.sha256(_normalised(LOCKFILE).encode("utf-8")).hexdigest()


def _runtime_packages() -> dict[str, dict]:
    lock = json.loads(_normalised(LOCKFILE))
    if lock.get("lockfileVersion") != 3:
        raise SystemExit(
            f"lockfileVersion {lock.get('lockfileVersion')} -- this tool reads the "
            f"`dev` flags of a v3 lockfile and has not been checked against others"
        )
    return {
        key: meta
        for key, meta in sorted(lock["packages"].items())
        if key and not meta.get("dev")
    }


def _licence_text(package_dir: Path) -> tuple[str, str] | None:
    """The package's own licence file, as (filename, text)."""
    if not package_dir.is_dir():
        return None
    by_name = {f.name.upper(): f for f in package_dir.iterdir() if f.is_file()}
    for preferred in LICENCE_NAMES:
        hit = by_name.get(preferred.upper())
        if hit:
            return hit.name, _normalised(hit).strip()
    # Anything else that looks like one, so an oddly-named file still counts.
    for name, path in sorted(by_name.items()):
        if name.startswith(("LICENSE", "LICENCE", "COPYING")):
            return path.name, _normalised(path).strip()
    return None


def _declared(meta: dict) -> str:
    licence = meta.get("license")
    if isinstance(licence, str):
        return licence
    if isinstance(licence, dict) and licence.get("type"):
        return str(licence["type"])
    return "not declared"


def render() -> str:
    packages = _runtime_packages()
    entries, without_text = [], []

    for key, meta in packages.items():
        name = key.replace("node_modules/", "").replace("/node_modules/", " > ")
        version = meta.get("version", "?")
        declared = _declared(meta)
        found = _licence_text(NODE_MODULES / key)

        block = [
            "-" * 78,
            f"{name}  {version}",
            f"License: {declared}",
        ]
        if found:
            filename, text = found
            block += [f"Source: {filename}", "", text]
        else:
            without_text.append(f"{name} {version} ({declared})")
            block += [
                "",
                "    The package ships no licence file. The identifier above is what",
                "    its package.json declares; the full text is that standard licence.",
            ]
        entries.append("\n".join(block))

    lines = [
        "=" * 78,
        "THIRD-PARTY NOTICES for the bundled Ketcher editor",
        "=" * 78,
        "",
        f"{HEADER_MARKER}",
        f"{HASH_MARKER}{_lockfile_hash()}",
        "DO NOT EDIT -- regenerate with tools/build_ketcher_notices.py",
        "",
        "`src/openchem/resources/ketcher/dist/` is a bundle. Its build strips",
        "comments, so almost no licence banner survives into the artifact and an",
        "accurate notice list cannot be recovered from it. This file is produced",
        "from the lockfile and the licence files in node_modules/ instead.",
        "",
        f"It lists all {len(packages)} packages the lockfile does not mark as",
        "development-only. That is deliberately MORE than the bundle contains: a",
        "build-time tool can be a runtime dependency of a runtime package (the",
        "@babel/* set arrives this way, via @emotion/babel-plugin), and vite",
        "tree-shakes, so some listed packages contribute no code at all.",
        "Over-attribution is the safe direction; narrowing the list would mean",
        "deciding per package whether any of its code survived into a 35 MB",
        "comment-stripped artifact.",
        "",
        "Ketcher's own licence is at ../LICENSE.",
        "",
    ]
    if without_text:
        lines += [
            f"{len(without_text)} package(s) ship no licence file of their own, and are",
            "listed below with the identifier their package.json declares:",
            "",
        ]
        lines += [f"    {item}" for item in without_text]
        lines.append("")
    lines += ["=" * 78, ""]

    return "\n".join(lines) + "\n\n".join(entries) + "\n"


def check() -> int:
    if not OUTPUT.exists():
        print(f"MISSING: {OUTPUT.relative_to(ROOT)} has never been generated.")
        return 1

    current = _normalised(OUTPUT)
    problems: list[str] = []

    recorded = ""
    for line in current.splitlines():
        if line.startswith(HASH_MARKER):
            recorded = line[len(HASH_MARKER):].strip()
            break
    actual = _lockfile_hash()
    if not recorded:
        problems.append("the generated file records no lockfile hash at all")
    elif recorded != actual:
        problems.append(
            f"stale: generated from a lockfile hashing {recorded[:12]}, which is now "
            f"{actual[:12]} -- the dependencies changed, re-run without --check"
        )

    # Regenerating requires node_modules. On a machine without it every
    # licence text would come back empty and the comparison would report a
    # spurious mismatch, so this half is SKIPPED rather than failed -- and
    # says so, because a check that silently degrades is worse than one that
    # admits what it could not do.
    if (NODE_MODULES / "node_modules").is_dir():
        if current != _normalised_str(render()):
            problems.append(
                "the generated file does not match what the lockfile and "
                "node_modules/ build -- it was hand-edited, or the generator changed"
            )
    else:
        print("note: node_modules/ absent, so only the lockfile hash was checked.")

    for problem in problems:
        print(f"THIRD-PARTY-NOTICES.txt: {problem}")
    return 1 if problems else 0


def _normalised_str(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="verify the notices are current without writing them")
    args = parser.parse_args()

    if args.check:
        code = check()
        if code == 0:
            print(f"THIRD-PARTY-NOTICES.txt is current ({len(_runtime_packages())} packages).")
        return code

    if not (NODE_MODULES / "node_modules").is_dir():
        raise SystemExit(
            "tools/ketcher-host/node_modules/ is absent -- run `npm install` there "
            "first. The licence TEXTS come from it; the lockfile only names them."
        )
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(_runtime_packages())} packages).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
