"""Score the naming benchmark in CI, and fail the build if it moved.

A SEPARATE SCRIPT RATHER THAN INLINE YAML, for two reasons. A multi-line
shell block inside a workflow is quoted twice over and is the classic place
for a CI-only bug that reproduces nowhere else. And this has real logic in
it -- the working-directory dance below is not decoration.

WHY IT RUNS FROM A DIFFERENT DIRECTORY. `py2opsin` writes a fixed temp
filename (`py2opsin_temp_input.txt`) into the CURRENT working directory and
deletes it afterwards, so two OPSIN callers sharing a directory delete each
other's file. The symptom is a `PermissionError` on Windows deep inside a
library nobody was thinking about. The test suite has already run OPSIN in
the repository root by the time this executes, so scoring happens in a
sibling directory.

WHY IT REGENERATES PREDICTIONS instead of scoring the committed file.
`benchmarks/naming/score.py` takes a predictions file, and the point of a
gate is to check what the CODE DOES NOW, not to re-score a recording of what
it did once.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

#: What the benchmark has scored since the corpus reached 181 molecules.
#: Anything else -- higher or lower -- means the naming engine changed and
#: somebody needs to look, so this is an equality check rather than a floor.
EXPECTED = "181/181"


def main() -> int:
    from openchem.vendor.iupac_namer import name_smiles

    corpus = json.loads(
        (REPO / "benchmarks" / "naming" / "corpus.json").read_text(encoding="utf-8")
    )

    predictions = []
    for row in corpus:
        try:
            predictions.append(str(name_smiles(row["smiles"]) or ""))
        except Exception as exc:  # noqa: BLE001 - recorded, so the scorer sees it
            predictions.append(f"<ERROR {type(exc).__name__}>")

    # A TEMPORARY DIRECTORY, not one beside the repository. The first
    # version put both the predictions file and the scratch directory in
    # the tree and in its PARENT -- which on CI is harmless and on a
    # developer's machine drops a stray folder next to their checkout and
    # leaves an untracked file plus a modified tracked `results.json`
    # behind. Running the gate locally should cost nothing and leave
    # nothing; found by running it rather than by reading it.
    with tempfile.TemporaryDirectory(prefix="naming-gate-") as scratch:
        out = Path(scratch) / "predictions_ci.json"
        out.write_text(
            # Labelled "check" to match what the documented manual
            # workflow produces. `score.py` records the run label in the
            # tracked `results.json`, so a different label here would
            # churn that file on every CI run for no reason -- a
            # one-line diff that trains people to ignore diffs.
            json.dumps({"check": {"predictions": predictions}}, indent=1),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(REPO / "benchmarks" / "naming" / "score.py"), str(out)],
            cwd=scratch,
            capture_output=True,
            text=True,
        )

    print(result.stdout)
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print("The naming benchmark did not complete.", file=sys.stderr)
        return 1
    if EXPECTED not in result.stdout:
        print(
            f"Naming benchmark is not {EXPECTED}. This gates every change: a "
            f"drop here outranks any number of narrow tests a change fixed, "
            f"and a RISE means the corpus or the scorer moved and the new "
            f"number needs recording rather than silently accepting.",
            file=sys.stderr,
        )
        return 1

    print(f"Naming benchmark holds at {EXPECTED}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
