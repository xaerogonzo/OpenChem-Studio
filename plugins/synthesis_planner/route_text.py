"""The words the synthesis panel shows about a route, as pure functions (no Qt), so what a person is told is tested without a window.

THREE RULES FOLLOW THE ROUTE DOMAIN. A field the planner did not supply is `None` and is shown as "not provided" (`shown`), never as an empty cell or a zero. A number the planner supplied is named
for what it is: the policy's probability for the template is "the model's score for this template", never a yield or a chance the step works. And a route is called "proposed", never "validated" or
"recommended": the panel states what the planner said and what was checked about it, and `RouteSet.all_limitations` says what neither means.
"""

from __future__ import annotations

from openchem.domain.synthesis_route import Check, MappingStatus, Route, RouteStep, StockStatus, ValidationReport, shown


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def route_title(route: Route) -> str:
    """One line for the route list: its place in the planner's order, its length and its starting materials."""
    score = "" if route.score is None else f", planner score {route.score:.3g}"
    return f"Route {route.rank}: {_plural(route.length, 'step')}, {_plural(len(route.starting_materials), 'starting material')}{score}"


def step_title(index: int, step: RouteStep) -> str:
    """One line for the step list. `index` is 1-based, in the order the steps would be run."""
    return f"Step {index}: {' + '.join(step.reactants)}  >>  {step.product}"


def step_text(step: RouteStep) -> str:
    """What the planner said about one step, field by field, each absent field as "not provided"."""
    probability = shown(None if step.policy_probability is None else f"{step.policy_probability:.3g} (the model's score for this template, not a yield and not a chance that the step works)")
    lines = [
        f"Makes: {step.product}",
        f"From: {' + '.join(step.reactants)}",
        f"Template: {shown(step.template_id)}",
        f"Policy: {shown(step.policy_name)}",
        f"Policy probability: {probability}",
        "Conditions, reagents and yield: not provided (the planner does not supply them).",
    ]
    return "\n".join(lines)


def starting_materials_text(route: Route) -> str:
    """The molecules the route begins from, each with whether the stock lists it (as the planner said, or not provided)."""
    if not route.starting_materials:
        return "Starting materials: not provided"
    stock = {True: "in stock", False: "NOT in stock", None: "stock status not provided"}
    rows = [f"  {material.smiles}   ({stock[material.in_stock]})" for material in route.starting_materials]
    return "Starting materials:\n" + "\n".join(rows)


_CHECK_WORDS = {Check.PASS: "passed", Check.FAIL: "FAILED", Check.NOT_ASSESSABLE: "could not be assessed"}
_MAPPING_WORDS = {MappingStatus.COMPLETE: "complete", MappingStatus.PARTIAL: "partial", MappingStatus.ABSENT: "absent"}
_STOCK_WORDS = {StockStatus.ALL_IN_STOCK: "all in stock", StockStatus.SOME_NOT_IN_STOCK: "some NOT in stock", StockStatus.NOT_PROVIDED: "not provided"}


def validation_text(report: ValidationReport | None) -> str:
    """The separate outcomes of checking one route, as they are: diagnostics about its own bookkeeping and never a verdict on the chemistry."""
    if report is None:
        return "Internal consistency: not checked."
    lines = [
        "Internal consistency (the route's own bookkeeping, not the chemistry):",
        f"  molecules parse: {_CHECK_WORDS[report.molecules]}",
        f"  reactions parse: {_CHECK_WORDS[report.reactions]}",
        f"  atom mapping: {_MAPPING_WORDS[report.mapping]}",
        f"  atoms conserved: {_CHECK_WORDS[report.conservation]}",
        f"  starting materials: {_STOCK_WORDS[report.stock]}",
    ]
    lines.extend(f"  {text}" for text in report.diagnostics)
    lines.extend(f"  missing: {text}" for text in report.missing)
    return "\n".join(lines)


def route_text(route: Route) -> str:
    """Everything the panel shows beside a route's steps: where it begins, and how it was checked."""
    return f"{starting_materials_text(route)}\n\n{validation_text(route.validation)}"
