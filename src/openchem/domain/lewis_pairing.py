"""The Lewis pairing: the first recipe, as a plan (`docs/RECIPES_DESIGN.md` section 4).

**IT WIRES, IT DOES NOT CALCULATE.** `compute_lewis_adduct` hands `predict` no quantum value, so in the application the
frontier-gap and HSAB lines have always read "not available". The numbers exist (ORCA's single point gives the
orbital energies, its delta-SCF job the hardness) and nothing connected them. This recipe is that connection, and
every equation stays where it was (`chem.lewis_adduct`).

**WHAT IT READS, AND WHAT IT CANNOT.** For each of two molecules: `orca.homo_energy` and `orca.lumo_energy` from a `sp`
run, and `orca.dscf_hardness` from a `delta_scf` run, all at the ONE method, basis and solvent chosen as recipe
parameters. It never picks the method that happens to have evidence: a recipe that did would find one method for
one molecule and another for its partner, which is the failure this record exists to prevent. It never reads the
Koopmans hardness (`orca.hardness`), which inverts ammonia against phosphine.

**THE SERVICE STEPS ARE THE JOBS THAT WOULD SUPPLY A GAP, NOT JOBS THIS RECIPE STARTS.** In this stage the recipe
evaluates over stored runs and reports what is missing, with the preview of the work that would fill it. Nothing
here starts ORCA (`RECIPES_DESIGN.md` section 8, Stage A); the person runs the jobs where they run them today.
"""

from __future__ import annotations

from openchem.domain.execution_policy import AiRun, ExecutionPolicy, ResourceClass
from openchem.domain.lewis import ROLE_ACID, ROLE_AUTO, ROLE_BASE
from openchem.domain.quantum_methods import METHOD_BASIS_PRESETS, SOLVENTS
from openchem.domain.recipe import (
    MOLECULE,
    MOLECULE_INPUT,
    REPORT,
    RUN_REFERENCE,
    Binding,
    Recipe,
    RecipeParameter,
    Slot,
    Step,
    StepKind,
    StepOutput,
    code,
    from_parameter,
    from_slot,
    from_step,
    scalar,
)

#: The recipe's id, as a stored run records it.
RECIPE_ID = "lewis_pairing"
#: Never repointed. A change of meaning is a new string, so a project saved with "1" is never reread with newer
#: methods (`recipe_run.assess` shows an unknown version as recorded and does not re-evaluate it).
VERSION = "1"

#: The single-point job on the first molecule (HOMO and LUMO).
SP_FIRST = "sp_first"
#: The delta-SCF job on the first molecule (hardness).
DSCF_FIRST = "dscf_first"
#: The single-point job on the second molecule.
SP_SECOND = "sp_second"
#: The delta-SCF job on the second molecule.
DSCF_SECOND = "dscf_second"
#: The evaluating step, whose inputs are the six numbers.
PAIR = "pair"

#: The report this recipe ends in.
RESULT_OUTPUT = "report"

#: Every number this recipe reads is in electronvolts, and the unit is part of the type.
_EV = scalar("eV")

#: An ORCA job: always approved by a person first, and it writes files of its own.
_ORCA = ExecutionPolicy(
    ResourceClass.LONG,
    AiRun.CONFIRM,
    external_tools=frozenset({"orca"}),
    writes_outside_results=True,
    why_confirm="Starts an ORCA job, which runs for as long as the molecule and method need and writes files of its own.",
)

#: The evaluating step: arithmetic over the bound numbers and the registered calculator's structural analysis.
_PURE = ExecutionPolicy(
    ResourceClass.INSTANT,
    AiRun.AUTO,
    measured=(
        "Arithmetic over six bound numbers plus the registered lewis_adduct calculator's own structural analysis, "
        "which benchmarks/calculator_cost measured at 0.004 s on real inputs."
    ),
)


def _job(step_id: str, slot: str, calc_type: str, outputs: tuple[StepOutput, ...]) -> Step:
    return Step(
        step_id,
        StepKind.SERVICE,
        calc_type,
        bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot(slot)),
            Binding("method_basis", code(*METHOD_BASIS_PRESETS), from_parameter("method_basis")),
            Binding("solvent", code(*SOLVENTS), from_parameter("solvent")),
        ),
        outputs=outputs,
        policy=_ORCA,
        label=(
            f"Single point on the {slot} molecule: HOMO and LUMO energies"
            if calc_type == "sp"
            else f"Delta-SCF job on the {slot} molecule: hardness"
        ),
    )


def _number(slot: str, step_id: str, output: str) -> Binding:
    """One optional number. Optional because the three lines are independent evidence and `predict` already means
    "not available" by `None`; the state it ended in is recorded either way."""
    return Binding(f"{slot}_{output}", _EV, from_step(step_id, output), optional=True)


#: The Lewis pairing, as a plan. `recipe_catalogue` lists it; the validator checks it against the real registry.
LEWIS_PAIRING = Recipe(
    recipe_id=RECIPE_ID,
    version=VERSION,
    question="How well matched are these two molecules as a Lewis acid and base, on the evidence of stored quantum-chemistry runs?",
    slots=(Slot("first", "First molecule"), Slot("second", "Second molecule")),
    parameters=(
        RecipeParameter("method_basis", "Method and basis", tuple(METHOD_BASIS_PRESETS), METHOD_BASIS_PRESETS[0]),
        RecipeParameter("solvent", "Solvent (blank is gas phase)", tuple(SOLVENTS), SOLVENTS[0]),
        RecipeParameter("role", "Role of the first molecule", (ROLE_AUTO, ROLE_ACID, ROLE_BASE), ROLE_AUTO),
    ),
    steps=(
        _job(SP_FIRST, "first", "sp", (StepOutput("homo", _EV), StepOutput("lumo", _EV), StepOutput("run", RUN_REFERENCE))),
        _job(DSCF_FIRST, "first", "delta_scf", (StepOutput("hardness", _EV), StepOutput("run", RUN_REFERENCE))),
        _job(SP_SECOND, "second", "sp", (StepOutput("homo", _EV), StepOutput("lumo", _EV), StepOutput("run", RUN_REFERENCE))),
        _job(DSCF_SECOND, "second", "delta_scf", (StepOutput("hardness", _EV), StepOutput("run", RUN_REFERENCE))),
        Step(
            PAIR,
            StepKind.EVALUATE,
            "lewis_pair",
            bindings=(
                Binding("first", MOLECULE, from_slot("first")),
                Binding("second", MOLECULE, from_slot("second")),
                Binding("role", code(ROLE_AUTO, ROLE_ACID, ROLE_BASE), from_parameter("role")),
                _number("first", SP_FIRST, "homo"),
                _number("first", SP_FIRST, "lumo"),
                _number("first", DSCF_FIRST, "hardness"),
                _number("second", SP_SECOND, "homo"),
                _number("second", SP_SECOND, "lumo"),
                _number("second", DSCF_SECOND, "hardness"),
            ),
            outputs=(StepOutput(RESULT_OUTPUT, REPORT),),
            policy=_PURE,
            label="Resolve which molecule is the acid, and report the three lines from the evidence",
        ),
    ),
    result=from_step(PAIR, RESULT_OUTPUT),
    caveats=(
        "Drago-Wayland, the frontier gap and the HSAB match stay three separate lines. There is no combined score.",
        "The two orbital lines can disagree, on purpose: for carbon monoxide the frontier gap prefers borane over "
        "boron trifluoride and the HSAB match prefers boron trifluoride. Both are reported.",
        "A frontier energy is the orbital table of a single point at the geometry that run was given; the hardness is "
        "a delta-SCF value, never the Koopmans one. They may come from different inputs, and each says which.",
    ),
)

