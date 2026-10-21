"""The words the synthesis panel shows about a route, as pure functions (no Qt), so what a person is told is tested without a window.

THREE RULES FOLLOW THE ROUTE DOMAIN. A field the planner did not supply is `None` and is shown as "not provided" (`shown`), never as an empty cell or a zero. A number the planner supplied is named
for what it is: the policy's probability for the template is "the model's score for this template", never a yield or a chance the step works. And a route is called "proposed", never "validated" or
"recommended": the panel states what the planner said and what was checked about it, and `RouteSet.all_limitations` says what neither means.
"""

from __future__ import annotations

from openchem.domain.synthesis_route import Check, MappingStatus, Route, RouteSet, RouteStep, StockStatus, ValidationReport, shown


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def route_title(route: Route, route_set: RouteSet | None = None) -> str:
    """One line for the route list: its place in the planner's order, its length and its starting materials, and, when the set has been screened, how many molecules carry a regulatory alert.

    No alert is never written as a good sign: a route whose molecules matched nothing says nothing about alerts, and one with molecules that could not be screened says so.
    """
    score = "" if route.score is None else f", planner score {route.score:.3g}"
    flags = ""
    if route_set is not None:
        screenings = route_set.screenings_for(route)
        alerts = sum(1 for s in screenings if s.has_alert)
        if alerts:
            flags += f", {_plural(alerts, 'molecule')} with a regulatory alert"
        if any(not s.screened for s in screenings):
            flags += ", some molecules not screened"
    return f"Route {route.rank}: {_plural(route.length, 'step')}, {_plural(len(route.starting_materials), 'starting material')}{score}{flags}"


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


def _role(route: Route, smiles: str) -> str:
    if smiles == route.target_smiles:
        return "the target"
    if any(step.product == smiles for step in route.steps):
        return "an intermediate"
    return "a starting material"


def alerts_text(route_set: RouteSet, route: Route) -> str:
    """What the wider regulatory rulesets say about each molecule of this route, as listings and never as a verdict.

    An alert is a match to a structural rule of a shipped (or your own) ruleset: it may be a controlled substance, a precursor list, a workplace exposure limit or a hazard listing, and each line names which. It is not a legal determination, and a molecule with no alert is not thereby free of obligations: the ruleset list is finite. A molecule that could not be screened says why and is never counted as having no alert. A set that was never screened says that, and nothing else.
    """
    screenings = route_set.screenings_for(route)
    if not screenings:
        return "Regulatory alerts: not checked."
    lines = ["Regulatory alerts (a listing in a ruleset, not a legal determination; no alert does not mean nothing applies):"]
    flagged = [s for s in screenings if s.has_alert]
    for screening in flagged:
        lines.append(f"  {screening.smiles}   ({_role(route, screening.smiles)})")
        for finding in screening.findings:
            where = ", ".join(part for part in (finding.jurisdiction, finding.section) if part)
            mine = ", your own ruleset" if finding.user_supplied else ""
            lines.append(f"    - {finding.display_name}   [{finding.rule_id}; {finding.ruleset_id}{mine}; {finding.domain}; {where}; confidence: {finding.confidence or 'not given'}]")
    for screening in screenings:
        if not screening.screened:
            lines.append(f"  {screening.smiles}: could not be screened: {screening.reason}")
    if not flagged:
        consulted = sorted({name for s in screenings if s.screened for name in s.rulesets_consulted})
        # "no molecule matched" would be false while one could not be screened: the claim is only about the ones that were
        subject = "no molecule of this route" if all(s.screened for s in screenings) else "none of the molecules that could be screened"
        lines.append(f"  {subject} matched a rule" + (f" in: {', '.join(consulted)}" if consulted else "") + ".")
    return "\n".join(lines)
