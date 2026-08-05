from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rdkit import Chem


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


def validate_smarts(pattern: str) -> str:
    """Validates a SMARTS substructure-query pattern via RDKit and reports
    the result as plain text for the assistant to read back to the user --
    the exact "safe read operation like SMARTS validation" docs/ARCHITECTURE.md
    names as Phase 5's deferred tool-calling example. Read-only: never
    touches the user's project.
    """
    mol = Chem.MolFromSmarts(pattern)
    if mol is None:
        return f"Invalid SMARTS pattern: {pattern!r} could not be parsed."
    return (
        f"Valid SMARTS pattern: {pattern!r} parses to "
        f"{mol.GetNumAtoms()} atom(s) and {mol.GetNumBonds()} bond(s)."
    )


VALIDATE_SMARTS_TOOL = ToolDefinition(
    name="validate_smarts",
    description=(
        "Validate a SMARTS substructure query pattern and report whether it "
        "parses, plus its atom/bond count. Use this before presenting a SMARTS "
        "pattern to the user, to confirm it is syntactically valid rather than "
        "guessing."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "The SMARTS pattern to validate."},
        },
        "required": ["pattern"],
    },
)

# All tools the assistant may request, and the local (never-remote) handler
# that actually executes each one -- the assistant only ever sees a name +
# JSON input schema; execution always happens here, in this process, not
# on the assistant's side.
AVAILABLE_TOOLS: list[ToolDefinition] = [VALIDATE_SMARTS_TOOL]
TOOL_REGISTRY: dict[str, Callable[..., str]] = {"validate_smarts": validate_smarts}
