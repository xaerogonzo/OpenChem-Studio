"""One calculator run, without a window: the Qt-free twin of `_CalculationTask._run`.

`services.descriptor_service._CalculationTask` is what the application does for one
calculator, and it is a `QRunnable` that publishes events -- so it cannot be imported
without Qt. Everything it does *around* the call is small and Qt-free, and is
reproduced here step for step, in the same order:

    1. look the definition up                      `CalculatorRegistry.get`
    2. resolve the structure the calculator is     `resolve_calculation_input`
       handed (the drawing, or a stored 3D one)
    3. note which geometry that is                 `geometry_provenance`
    4. compute (scope, parameters, components)     `CalculatorRegistry.compute`
    5. merge geometry and parameters into the      `_with_geometry_provenance`
       result's provenance
    6. a `CalculationRefusal` is a decline, not a crash, and carries a kind

**Two paths that must agree are only the same until somebody changes one.**
`tests/test_cli.py` runs the real task beside this and compares what each produced,
for calculators that succeed, refuse and need input -- the discipline
`tools/calculator_census.py` documents ("through the service, not by import"), kept
here by a test instead of by routing the CLI through Qt.

What is deliberately left out, and why:

* **`_bind_settings`.** The sidecar calculators (pKa, ADMET) read their interpreter
  path from the person's settings store, which is `QSettings` -- on Windows, the
  registry. A command line must neither read nor write that, so those calculators
  run unconfigured and refuse as `needs_setup`, which is the true state of a machine
  with no interpreter named.
* **`structure_version`.** It is the editor's revision counter; a one-shot run has
  no revisions.
* **Events, the thread pool, and `ResultRecorded`.** Nothing is retained.
"""

from __future__ import annotations

REACHED_BY = (
    "console_script: imported only by openchem.cli.commands, which is itself entered "
    "by the `openchem-cli` console script rather than by an import from openchem.main"
)

import logging
from dataclasses import dataclass, replace
from typing import Any

from openchem.chem.calculation_input import (
    INPUT_PREFIX,
    geometry_provenance,
    recordable_parameters,
    resolve_calculation_input,
)
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.engine import ChemistryEngine
from openchem.domain import result_status as rs
from openchem.domain.calculator import CalculationRefusal, CalculatorDefinition, RegistryExecution
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.refusal_kinds import RefusalKind
from openchem.services.calculator_registry import CalculatorRegistry

logger = logging.getLogger("openchem.cli")

#: Fixed identities, so two runs of one question produce one document. A molecule's
#: uuid and a conformer's id are `uuid4()` by default and end up inside every
#: result's provenance, which would make the output differ run to run for no reason.
CLI_MOLECULE_UUID = "00000000-0000-4000-8000-00000000c11a"
CLI_CONFORMER_ID = "00000000-0000-4000-8000-00000000c11b"

#: The conformer seed used when none is given. The embedder's own default is "draw
#: from the global RNG", which is right for a random search and wrong for a tool whose
#: answers are meant to be repeated.
DEFAULT_CONFORMER_SEED = 1

#: Calculators the command line will not run, with the reason. **Measured, not
#: assumed:** every registered calculator was run on ethanol and aspirin with
#: `open`, `subprocess.Popen` and `socket.connect` recording, and exactly one touched
#: anything -- `iupac_name` reached the network, started Java twice and wrote two temp
#: files. `tests/test_cli.py::test_no_other_calculator_has_a_side_effect` repeats the
#: measurement, so a calculator that gains one fails there instead of silently
#: breaking the `pure_read` promise every command here makes.
EXTERNAL_EFFECT_CALCULATORS: dict[str, str] = {
    "iupac_name": (
        "it starts Java (OPSIN), reaches the network and writes temporary files, "
        "which a pure_read command may not"
    ),
}


class StructureError(ValueError):
    """The structure could not be built from what was given."""


def runnable_reason(definition: CalculatorDefinition) -> str:
    """Why the command line will not run this calculator, or ``""``."""
    if not isinstance(definition.execution, RegistryExecution):
        return f"it is run by {definition.execution.service_name}, not through the registry"
    return EXTERNAL_EFFECT_CALCULATORS.get(definition.calculator_id, "")


def build_registry() -> CalculatorRegistry:
    """Every built-in calculator, registered in the application's own order."""
    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        registry.register(definition)
    return registry


def build_model(
    engine: ChemistryEngine, smiles: str, *, conformer: bool, seed: int
) -> tuple[MoleculeModel, dict[str, Any]]:
    """A molecule from SMILES, optionally with one generated 3D conformer.

    The conformer is **not optimised** and is seeded: it is a starting geometry, which
    is what the Conformers panel's first embedding gives, and calling it anything more
    would be a claim. Calculators that need real 3D coordinates (the geometry, surface,
    dipole and aromaticity families) refuse a bare SMILES, correctly -- the 16 "failed"
    results in the survey were all that one sentence. `info` says what was done,
    including a failure to embed, which leaves the model without one.
    """
    model = MoleculeModel(uuid=CLI_MOLECULE_UUID)
    try:
        engine.set_structure_from_smiles(model, smiles)
    except ValueError as error:
        raise StructureError(str(error)) from None

    info: dict[str, Any] = {
        "requested": conformer, "generated": False, "optimized": False,
        "seed": seed if conformer else None, "error": "",
    }
    if not conformer:
        return model, info
    try:
        provider = RDKitConformerProvider(random_seed=seed)
        results = provider.generate_conformers(
            engine.mol_from_model(model), num_conformers=1, optimize=False
        )
        if not results:
            info["error"] = "the embedder returned no conformer"
        else:
            conformer_mol, _energy = results[0]
            model.conformers.append(ConformerModel(
                conformer_id=CLI_CONFORMER_ID,
                molblock=engine.mol_to_molblock(conformer_mol),
                timestamp=0.0,
            ))
            info["generated"] = True
    except Exception as error:  # noqa: BLE001 - recorded in `info`, never swallowed
        info["error"] = f"{type(error).__name__}: {error}"[:240]
    return model, info


@dataclass(frozen=True)
class Outcome:
    """What one run produced: a result, or a refusal, or an error -- never two."""

    status: str
    result: Any = None
    #: A refusal's code, both sentences, kind and missing inputs, as the calculator
    #: raised them.
    refusal: dict[str, Any] | None = None
    #: Set only for an exception that was not a refusal.
    error: str = ""
    #: The identity of the structure the calculator was handed, when it got that far.
    input_fingerprint: str | None = None


def with_geometry_provenance(
    result: Any, model: MoleculeModel, calculation_input: str, parameters: dict,
    geometry: dict,
) -> Any:
    """`_with_geometry_provenance`: which geometry and which parameters, merged in.

    The calculator still wins any key collision, as in the application. A result with
    no `provenance`, or one that will not take the replacement, comes back untouched:
    recording where a number came from must never be able to lose the number.
    """
    provenance = getattr(result, "provenance", None)
    if provenance is None:
        return result
    try:
        merged = dict(geometry)
        merged[f"{INPUT_PREFIX}parameters"] = recordable_parameters(parameters)
        merged.update(provenance.parameters)
        return replace(result, provenance=replace(provenance, parameters=merged))
    except Exception:  # noqa: BLE001 - never lose a result over its metadata
        logger.exception("Could not record geometry provenance for %s", model.uuid)
        return result


def refusal_status(refusal: CalculationRefusal) -> str:
    """The status a refusal reads as, in `status_of`'s own order.

    The application turns a refusal into a FAILED result carrying its kind and lets
    `status_of` read it back; the order below is that function's, so the two agree:
    needs-input and needs-setup first, then a limit, and a refusal with no kind at all
    is a fault.
    """
    if refusal.kind is RefusalKind.NEEDS_INPUT:
        return rs.NEEDS_INPUT
    if refusal.kind is RefusalKind.NEEDS_SETUP:
        return rs.NEEDS_SETUP
    if refusal.kind is RefusalKind.LIMIT or refusal.inapplicable:
        return rs.INAPPLICABLE
    return rs.FAILED


def refusal_data(refusal: CalculationRefusal) -> dict[str, Any]:
    return {
        "code": refusal.code,
        "summary": refusal.summary,
        "detail": refusal.detail,
        "kind": refusal.kind.value if refusal.kind is not None else None,
        "classified": refusal.classified,
        "missing_inputs": refusal.missing_inputs,
    }


def run_calculator(
    registry: CalculatorRegistry, engine: ChemistryEngine, model: MoleculeModel,
    calculator_id: str, parameters: dict[str, Any],
) -> Outcome:
    """One calculator on one molecule. Never raises for anything the calculator does."""
    definition = registry.get(calculator_id)
    if definition is None:
        return Outcome(rs.FAILED, error=f"Unknown calculator: {calculator_id}")
    fingerprint: str | None = None
    try:
        resolved = resolve_calculation_input(engine, model, definition.calculation_input)
        fingerprint = resolved.fingerprint
        geometry = geometry_provenance(model, definition.calculation_input)
        result = registry.compute(calculator_id, resolved.mol, model.uuid, parameters)
        result = with_geometry_provenance(
            result, model, definition.calculation_input, parameters, geometry
        )
    except CalculationRefusal as refusal:
        return Outcome(refusal_status(refusal), refusal=refusal_data(refusal),
                       input_fingerprint=fingerprint)
    except Exception as error:  # noqa: BLE001 - a bad calculator must not end the process
        logger.exception("Calculator %s failed", calculator_id)
        return Outcome(rs.FAILED, error=f"{type(error).__name__}: {error}",
                       input_fingerprint=fingerprint)
    return Outcome(rs.status_of(result), result=result, input_fingerprint=fingerprint)
