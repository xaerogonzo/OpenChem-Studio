"""Print the pytest arguments for a scope of the naming-consumer manifest.

    python tools/naming_consumers.py --session app --args      # core + benchmark + app: ONE pytest process
    python tools/naming_consumers.py --session vendor --args   # the vendored suite: ITS OWN pytest process
    python tools/naming_consumers.py --scope core,benchmark    # files, one per line

The manifest is `tests/naming_consumers.toml`. A stage's routine runs `core` and `benchmark` after every
change and every session at a milestone, so "the whole naming-consuming test set" is a list a stage can be
checked against and not a phrase.

**THE VENDORED SUITE IS A SEPARATE PYTEST SESSION, AND THIS TOOL NOW REFUSES TO PRINT ONE LINE THAT MIXES THEM.**
`tests/vendor/iupac_namer/conftest.py` replaces `py2opsin.py2opsin` for the whole process, so collected beside
`tests/test_opsin_isolation.py` it turns that file's signature check into a KeyError on `tmp_fpath`. Naming round 8's
gate hit exactly that: the default scope list ended in the vendored directory as its FIRST token, a `sed` written to
strip it silently did not match (no leading space), and a 28-minute run failed on a test that passes alone and passes
in CI, where the vendored suite has its own job. The fix is not a better `sed`; a list that cannot be wrong is one
this tool will not print (`--allow-mixed` is there for the reader who knows why).
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "naming_consumers.toml"
SCOPES = ("core", "benchmark", "app", "vendor")

#: One entry per pytest PROCESS. The two never share one: see the module docstring.
SESSIONS = {
    "app": ("core", "benchmark", "app"),
    "vendor": ("vendor",),
}


def consumers() -> list[dict]:
    return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))["consumer"]


def select(scopes: set[str]) -> list[str]:
    unknown = scopes - set(SCOPES)
    if unknown:
        raise SystemExit(f"unknown scope(s) {sorted(unknown)}; the scopes are {list(SCOPES)}")
    return [c["file"] for c in consumers() if c["scope"] in scopes]


def session_files(session: str) -> list[str]:
    """The files of ONE pytest process."""
    if session not in SESSIONS:
        raise SystemExit(f"unknown session {session!r}; the sessions are {list(SESSIONS)}")
    return select(set(SESSIONS[session]))


def refuse_mixed(scopes: set[str]) -> None:
    """A single runnable line may not hold the vendored suite AND anything else."""
    if "vendor" in scopes and scopes - {"vendor"}:
        raise SystemExit(
            "refusing to print ONE pytest line that mixes the vendored suite with the app tests: its conftest replaces "
            "py2opsin.py2opsin for the whole process (see this file's docstring). Use --session app and --session vendor "
            "as two runs, or pass --allow-mixed if you know why."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", default=None, help=f"comma-separated scopes {list(SCOPES)} (default: all, for a listing)")
    parser.add_argument("--session", choices=sorted(SESSIONS), help="the files of one pytest process")
    parser.add_argument("--args", action="store_true", help="print one space-separated line, ready for `python -m pytest`")
    parser.add_argument("--allow-mixed", action="store_true", help="allow --args to hold the vendored suite beside app tests")
    args = parser.parse_args()
    if args.session and args.scope:
        parser.error("--session and --scope are alternatives")
    scopes = set(SESSIONS[args.session]) if args.session else {
        s.strip() for s in (args.scope or ",".join(SCOPES)).split(",") if s.strip()
    }
    if args.args and not args.allow_mixed:
        refuse_mixed(scopes)
    files = select(scopes)
    print(" ".join(files) if args.args else "\n".join(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
