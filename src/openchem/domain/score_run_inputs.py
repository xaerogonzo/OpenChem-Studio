"""What a run has to compute for the user's scores to have a column: the ids a person would tick (`docs/DERIVED_SCORES_DESIGN.md`, follow-ups of slice 4).

A score is worked out from the project table's own cells (`score_table.py`), so a score whose inputs were not in the run has no column and the table says which. This is the other half:
given the scores, which always-on properties and which calculators does a run need to include? It is the same answer the table asks of itself, asked before the run instead of after it.

Pure: it reads definitions and returns ids. Which of them a launcher offers, what is already ticked and what the run costs are the picker's business.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from openchem.domain.score_definition import ScoreDefinition

#: The prefix of an always-on property's batch column id, which is what a score names (`score_outputs.ApprovedOutput.output_id`): `descriptor:<id>`.
DESCRIPTOR_PREFIX = "descriptor:"
#: The prefix of a calculator's batch column id: `calculator:<calculator id>:<fact label>`.
CALCULATOR_PREFIX = "calculator:"


@dataclass(frozen=True)
class ScoreRunInputs:
    """The ids the scores read, split by what a picker ticks."""

    #: How many scores were read.
    scores: int = 0
    #: Always-on properties (the ids the descriptor provider knows), sorted.
    descriptor_ids: tuple[str, ...] = ()
    #: Registry calculators (the id, not the fact label), sorted.
    calculator_ids: tuple[str, ...] = ()
    #: Output ids that name neither kind: a definition from a build that approved something this one does not know. Nothing can be ticked for them, and they are said so, not dropped.
    unreadable: tuple[str, ...] = ()


def run_inputs_of(definitions: Sequence[ScoreDefinition]) -> ScoreRunInputs:
    """The always-on properties and calculators that `definitions` read, each once."""
    descriptors: set[str] = set()
    calculators: set[str] = set()
    unreadable: set[str] = set()
    for definition in definitions:
        for _name, output_id in definition.inputs:
            if output_id.startswith(DESCRIPTOR_PREFIX) and output_id[len(DESCRIPTOR_PREFIX) :]:
                descriptors.add(output_id[len(DESCRIPTOR_PREFIX) :])
            elif output_id.startswith(CALCULATOR_PREFIX) and output_id[len(CALCULATOR_PREFIX) :].split(":", 1)[0]:
                calculators.add(output_id[len(CALCULATOR_PREFIX) :].split(":", 1)[0])
            else:
                unreadable.add(output_id)
    return ScoreRunInputs(len(definitions), tuple(sorted(descriptors)), tuple(sorted(calculators)), tuple(sorted(unreadable)))
