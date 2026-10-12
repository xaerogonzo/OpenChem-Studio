from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rdkit import Chem


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def validate_arguments(schema: dict[str, Any], arguments: Any) -> list[str]:
    """Every way `arguments` fails the tool's own `input_schema`, in words. Empty means acceptable.

    **THE PROVIDER'S SCHEMA IS GUIDANCE TO THE MODEL, NOT A BOUNDARY.** A model can send a missing
    required field, a string where a number belongs, or a field the tool never declared, and
    `handler(**arguments)` would then raise a `TypeError` about its own signature, or worse, run with a
    wrong value. So the loop checks the call against the schema first and returns the problems to the
    model without running anything. It understands the subset these tools use: `type`, `required`,
    `properties`, `enum`, `minimum`, `maximum` and array `items`; an undeclared property is refused.
    """
    if not isinstance(arguments, dict):
        return [f"the arguments must be an object, not {type(arguments).__name__}"]
    problems: list[str] = []
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in arguments:
            problems.append(f"{name} is required")
    for name, value in arguments.items():
        if name not in properties:
            allowed = ", ".join(properties) or "none"
            problems.append(f"{name!r} is not an argument of this tool; it takes: {allowed}")
            continue
        problems.extend(_check_value(name, properties[name], value))
    return problems


def _check_value(name: str, spec: dict[str, Any], value: Any) -> list[str]:
    expected = spec.get("type")
    if expected is not None:
        types = _JSON_TYPES.get(expected, ())
        # A bool is an int in Python and is not a JSON number; and a float with no fraction is a whole
        # number only for a model that wrote `3.0`, which a schema asking for an integer should refuse.
        wrong = (isinstance(value, bool) and expected != "boolean") or not isinstance(value, types)
        if wrong:
            return [f"{name} must be {expected}, not {type(value).__name__}"]
    problems: list[str] = []
    if "enum" in spec and value not in spec["enum"]:
        problems.append(f"{name} must be one of {spec['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            problems.append(f"{name} must be at least {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            problems.append(f"{name} must be at most {spec['maximum']}")
    if expected == "array" and isinstance(spec.get("items"), dict):
        for index, item in enumerate(value):
            problems.extend(_check_value(f"{name}[{index}]", spec["items"], item))
    return problems


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

def explain_naming(smiles: str) -> str:
    """Reports how the nomenclature engine actually named a structure.

    THE POINT IS THAT THIS IS NOT A GUESS. Asked "why is this carbon
    numbered 4?", a language model will produce a fluent and often wrong
    account of IUPAC rules. This hands it the engine's OWN derivation -- the
    parent it chose, the group that took the suffix slot, each substituent
    subtree, and the real atom-to-locant map -- so the answer is a reading
    of a record rather than a reconstruction from memory.

    A tool rather than something added to the standing context: a derivation
    is large, and most turns do not need one. Read-only, and local like
    every tool here -- nothing about the molecule leaves the process except
    in the reply the user is already reading.
    """
    from openchem.chem.structure_annotation import annotate, name_derivation

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return f"Could not parse SMILES {smiles!r}."

    derivation = name_derivation(mol)
    if derivation is None:
        return (
            f"The nomenclature engine could not name {smiles!r}, so there is "
            f"no derivation to report. Say so rather than inventing one."
        )

    lines = [f"Name: {derivation.name or '(none)'}", "", "Derivation:"]

    def walk(node, depth: int) -> None:
        bits = [f"{'  ' * (depth + 1)}{node.kind}: {node.name!r}"]
        if node.role:
            bits.append(f"({node.role})")
        if node.locants:
            bits.append(f"at {','.join(node.locants)}")
        if node.detail:
            bits.append(f"-- {node.detail}")
        lines.append(" ".join(bits))
        for child in node.children:
            walk(child, depth + 1)

    walk(derivation, 0)

    annotation = annotate(mol)
    lines.append("")
    if annotation.locants:
        lines.append("Atom numbering (RDKit atom index -> element, IUPAC locant):")
        for locant in annotation.locants:
            symbol = mol.GetAtomWithIdx(locant.atom_index).GetSymbol()
            lines.append(
                f"  atom {locant.atom_index}: {symbol}{locant.label}  "
                f"[{locant.source.value}]"
            )
        uncovered = mol.GetNumAtoms() - len(annotation.locants)
        if uncovered:
            lines.append(
                f"  ({uncovered} further atom(s) carry no locant -- they are "
                f"not part of the numbered parent. Do not invent numbers for "
                f"them.)"
            )
    else:
        lines.append(
            "No atom numbering is available for this structure: it is named "
            "by a retained name, which carries no derived numbering. Do NOT "
            "supply locants from memory -- say that the engine assigned none."
        )

    if annotation.groups:
        lines.append("")
        lines.append("Functional groups the engine detected:")
        for group in annotation.groups:
            lines.append(
                f"  {group.type} at atom {group.anchor} "
                f"(atoms {sorted(group.atoms)}, prefix {group.prefix_form!r},"
                f" suffix-eligible: {group.suffix_eligible})"
            )

    return "\n".join(lines)


EXPLAIN_NAMING_TOOL = ToolDefinition(
    name="explain_naming",
    description=(
        "Report how this application's IUPAC nomenclature engine actually named "
        "a structure: the parent it selected, which group took the suffix, each "
        "substituent, and the real atom-index-to-locant map. ALWAYS use this "
        "before answering any question about why a structure has a particular "
        "name, why an atom carries a particular locant, or which group is the "
        "principal characteristic group -- the engine's record is authoritative "
        "and your recollection of IUPAC rules is not. If it reports that no "
        "numbering is available, say so rather than supplying locants yourself."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "smiles": {
                "type": "string",
                "description": "SMILES of the structure to explain.",
            },
        },
        "required": ["smiles"],
    },
)


# All tools the assistant may request, and the local (never-remote) handler
# that actually executes each one -- the assistant only ever sees a name +
# JSON input schema; execution always happens here, in this process, not
# on the assistant's side.
AVAILABLE_TOOLS: list[ToolDefinition] = [VALIDATE_SMARTS_TOOL, EXPLAIN_NAMING_TOOL]
TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "validate_smarts": validate_smarts,
    "explain_naming": explain_naming,
}
