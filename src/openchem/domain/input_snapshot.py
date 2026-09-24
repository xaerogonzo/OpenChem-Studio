"""What a calculation was DISPATCHED with, frozen on the thread that asked.

**A WORKER THAT READS THE LIVE MODEL IS COMPUTING ON WHATEVER THE GUI HAS
MADE OF IT SINCE.** `DescriptorService` handed a `MoleculeModel` to a task on
the thread pool, and the task read `model.molblock` and `model.conformers` at
several different moments while the GUI thread went on editing. Three things
follow, and the first two are latent bugs that a pause-then-refresh recompute
(which fires more, and later) makes reachable rather than theoretical:

* the fingerprint and the molecule handed to the calculator could come from
  two different reads, so a result was recorded against an input it was not
  computed on;
* a run begun on structure A that finished after an edit to B was stamped
  with B's structure version *when the result came back*, so a value computed
  for A read as current for B (`_with_structure_version`);
* a conformer search finishing mid-run changed which conformer "the canonical
  one" was between the resolution and the provenance.

`InputSnapshot` is taken on the GUI thread, before the task is queued, and
the task reads nothing else. It is a private copy: nothing else holds a
reference to it, so it is immutable in the only sense that matters here.

It deliberately reuses `MoleculeModel` rather than a parallel type. Every
function that resolves "which molecule does this calculator get"
(`chem.calculation_input`) already takes one, so the snapshot needs no second
implementation of that policy -- a second implementation is how the six
copies of it that `calculation_input` was written to end came about.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from openchem.domain.molecule import MoleculeModel


def snapshot_model(model: MoleculeModel) -> MoleculeModel:
    """A private copy of the parts of `model` a calculation reads.

    Every mutable container is copied, and every conformer, so a later
    in-place edit of the live model (a conformer appended by a search, a
    metadata write) cannot reach the copy.
    """
    return dataclasses.replace(
        model,
        metadata=dict(model.metadata),
        tags=list(model.tags),
        conformers=[dataclasses.replace(conformer) for conformer in model.conformers],
    )


@dataclass(frozen=True)
class InputSnapshot:
    """The molecule and the structure revision a calculation was dispatched with."""

    #: A private copy. See the module docstring for why it is a `MoleculeModel`.
    model: MoleculeModel
    #: `StructureCheckService.current_version` AT DISPATCH, or None when the
    #: service has no checker (a fixture) or it could not be consulted. This is
    #: the version a result is stamped with, never the counter's value when the
    #: result arrives.
    structure_version: int | None = None

    @classmethod
    def capture(cls, model: MoleculeModel, structure_version_of=None) -> InputSnapshot:
        """Snapshot `model` now. Call on the GUI thread, before queueing work.

        A counter that cannot be consulted costs the version, not the
        calculation: a result is never lost over its metadata.
        """
        version: int | None = None
        if structure_version_of is not None:
            try:
                version = int(structure_version_of(model.uuid))
            except Exception:  # noqa: BLE001 - never lose a calculation over its metadata
                version = None
        return cls(model=snapshot_model(model), structure_version=version)
