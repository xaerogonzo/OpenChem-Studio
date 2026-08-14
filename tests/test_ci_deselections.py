"""A `--deselect` in CI must still name a real test.

**IT FAILS OPEN, AND SILENTLY.** Measured against this pytest: an unknown
node id is not an error and not a warning -- the run collects everything
and exits 0.

    --deselect tests/test_naming_providers.py::test_pubchem_...opsin
        30/31 tests collected (1 deselected)
    --deselect tests/test_naming_providers.py::test_pubchem_...opsinX
        31 tests collected                              exit 0
    --deselect tests/test_naming_providerz.py::test_pubchem_...opsin
        31 tests collected                              exit 0

So renaming the test, or moving it to another file, silently puts it back
into the gating run -- and because that job runs three benchmark gates
AFTER the suite, and GitHub skips later steps once one fails, the next
NCBI outage would disable those gates again while reporting them as
`skipped`. That is the exact failure this deselection exists to prevent,
so nothing about its return would look new.

Nobody renaming a test would think to check a workflow file, which is why
this is a test and not a comment. Same shape as
`tests/test_workflow_safety.py`, and textual for the same stated reason:
`pyyaml` is not a dependency of this project, and the property being
checked is a string in a file.

NEITHER PARAMETRIZED NOR SKIPPING, and both are deliberate. An empty
`parametrize` makes pytest SKIP, so the version of this file that used one
turned its own "no deselections found" case into a skip -- which this
project's notes call neither caught nor survived. And an assertion inside a
parametrize helper raises at COLLECTION, which reports as an error rather
than as a named failure. A plain loop plus the canary below fails loudly in
both cases.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
REPO = Path(__file__).resolve().parent.parent

#: `--deselect <path>::<name>`, however the workflow spells the value --
#: literally, or through `${{ env.NAME }}`, which is how tests.yml avoids
#: repeating the id in two jobs.
#:
#: **THE OPTIONAL QUOTES ARE LOAD-BEARING**, and were added after this
#: file's first version cost a full-suite run. The workflow quotes the
#: expansion so the value is one argument under both pwsh (Windows) and
#: bash (Linux); without `["']?` here the literal branch matched `"${{`
#: and the guard failed on a workflow that was perfectly correct. It
#: failed CLOSED, which is the right direction -- but a parser of someone
#: else's syntax has to accept the forms that syntax really allows.
_DESELECT = re.compile(
    r"""--deselect\s+["']?(?:\$\{\{\s*env\.(?P<var>\w+)\s*\}\}|(?P<literal>[^\s"']+))["']?"""
)

#: `NAME: path::test_name` in a workflow `env:` block.
_ENV_NODE_ID = re.compile(r"^\s*(?P<var>\w+):\s*(?P<node>\S+\.py::\S+)\s*$", re.MULTILINE)


def _workflows() -> list[Path]:
    found = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert found, f"no workflows found under {WORKFLOWS} -- has the path moved?"
    return found


def _node_ids() -> list[tuple[str, str | None, str]]:
    """(workflow, node id or None, what was written) per deselection.

    Resolves `${{ env.VAR }}` against the same file's `env:` block, since
    that indirection is the whole reason two jobs can share one id. An
    unresolvable reference yields None rather than raising, so the failure
    is reported by a test instead of by a collection error.
    """
    found: list[tuple[str, str | None, str]] = []
    for path in _workflows():
        text = path.read_text(encoding="utf-8")
        variables = {m.group("var"): m.group("node") for m in _ENV_NODE_ID.finditer(text)}
        for match in _DESELECT.finditer(text):
            if match.group("literal"):
                found.append((path.name, match.group("literal"), match.group("literal")))
            else:
                name = match.group("var")
                found.append((path.name, variables.get(name), f"${{{{ env.{name} }}}}"))
    return found


def test_every_ci_deselection_still_names_a_real_test() -> None:
    """Each node id resolves to a test that exists, in the file it names."""
    for workflow, node_id, written in _node_ids():
        assert node_id is not None, (
            f"{workflow} deselects `{written}`, but no `env:` entry in that "
            "file carries a node id for it. GitHub expands an undefined "
            "variable to an EMPTY STRING, so pytest would receive a bare "
            "`--deselect` and the test would be back in the gating run."
        )
        path_part, _, test_name = node_id.partition("::")
        assert test_name, f"{workflow}: `{node_id}` names no test after `::`"

        target = REPO / path_part
        assert target.is_file(), (
            f"{workflow} deselects `{node_id}`, but {path_part} does not "
            "exist. pytest ignores an unknown --deselect SILENTLY and exits "
            "0, so this deselection does nothing and the test is back in the "
            "gating run."
        )
        assert re.search(
            rf"^def {re.escape(test_name)}\(", target.read_text(encoding="utf-8"), re.MULTILINE
        ), (
            f"{workflow} deselects `{node_id}`, but {path_part} defines no "
            f"`{test_name}`. It was probably renamed. pytest ignores an "
            "unknown --deselect silently, so CI is running it again with "
            "nothing saying so."
        )


def test_the_network_test_is_still_deselected_somewhere() -> None:
    """Guards the check above against passing vacuously.

    With no deselections found its loop body never runs, so this file
    would go green having verified nothing -- the same canary
    `test_workflow_safety.py` keeps for the same reason.

    Removing the deselection IS legitimate: it is only there because
    PubChem's availability could otherwise switch off three benchmark
    gates, and a CI that stops depending on NCBI should drop it. If that
    is what happened, delete this test with it rather than loosening it.
    """
    deselected = {node for _workflow, node, _written in _node_ids() if node}
    assert any("test_pubchem_name_round_trips_back_through_opsin" in n for n in deselected), (
        "No workflow deselects the PubChem round-trip test any more. If that "
        "is deliberate, remove this canary; otherwise CI can be reddened by "
        "NCBI being busy, which skips the naming and regulatory gates behind "
        "it and reports them as `skipped` rather than as anything alarming."
    )
