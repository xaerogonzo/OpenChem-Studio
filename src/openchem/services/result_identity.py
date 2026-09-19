"""The one route to a `ResultIdentity`.

**THE DISPATCHER KNOWS WHAT THE RESULT DOES NOT.** No result type in this
application carries the calculator that produced it, the parameters it ran
with, or which structure revision it describes (`PropertyPanel._result_for`
records that finding). Reconstructing those from a result's fields after the
fact is how a store ends up filing one calculation under another's key. So
the identity is built here, by the code that dispatched the work, from the
fingerprint `resolve_calculation_input` produced while choosing the molecule.

`parameters_key` is `result_cache.parameters_key` and nothing else -- one
parameter-serialisation recipe, for the reason `domain/batch.ResultKey`
already gives: two recipes is how two identical requests become two keys.
"""

from __future__ import annotations

from functools import lru_cache

from openchem.domain.result_store import CURRENT_METHOD_VERSIONS, ResultIdentity, result_id_of
from openchem.services.result_cache import parameters_key


def make_identity(
    *,
    molecule_uuid: str,
    result: object,
    calculation_input: str,
    input_fingerprint: str,
    producer: str,
    parameters: dict | None = None,
) -> ResultIdentity:
    result_id = result_id_of(result)
    return ResultIdentity(
        molecule_uuid=molecule_uuid,
        result_id=result_id,
        calculation_input=calculation_input,
        input_fingerprint=input_fingerprint,
        producer=producer,
        parameters_key=parameters_key(parameters),
        # Only results whose method is part of their identity carry one.
        method_version=CURRENT_METHOD_VERSIONS.get(result_id, ""),
    )


@lru_cache(maxsize=1)
def application_version() -> str:
    from openchem.build_info import _app_version

    return _app_version()
