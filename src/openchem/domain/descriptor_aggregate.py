"""The always-on descriptors as ONE reader entry, without flattening them.

Forty-one descriptors are computed the moment a molecule is selected --
molecular weight, LogP, TPSA, QED, the rule filters, the shape family. They
are `DescriptorValue`s, not `ScientificResult`s, so they reach neither the
results reader's fact model nor the clipboard.

**THE OBVIOUS BRIDGE FLATTENS SOMETHING REAL, WHICH IS WHY THIS IS A
CONTAINER RATHER THAN A CONVERSION.** Publishing the forty-one as a single
`ReportResult` would give them ONE `cache_state`, one `error` and one
`inapplicable` flag between them. Each descriptor has its own, and they
genuinely differ: with no 3D conformer the ten shape descriptors FAIL while
the other thirty-one succeed, so a molecule drawn flat produces exactly the
state a single flag cannot express:

    Molecular Properties
        Egan Filter    ok          NP-Likeness   failed
        Pfizer 3/75    ok          Sphericity    needs a 3D conformer

So this keeps the ORIGINALS and derives a flat fact view beside them --
exactly what `MergedResults` does with reports, and for the same reason. A
consumer wanting per-row status reads `descriptors`; a consumer wanting the
reader contract reads `facts`. Neither is a copy of the other.

**IT IS A PROJECTION, NOT A CALCULATOR.** It has no `calculator_id`, is never
offered as something to run, and never participates in a cache key. Its
`report_id` is a reserved identifier so a reader can focus it like any other
entry -- that is a display handle, not a computational identity. The
distinction matters because `parameters_key` hashes calculator identity into
every retained result, and a projection acquiring one would put a thing
nobody can run into the store.

Nothing here computes. A descriptor's value, its state and its reason all
come from the producer; this decides only how they are grouped and read.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.calculator_taxonomy import category_for
from openchem.domain.common import CacheState, describe_failure
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.report import (
    Basis,
    Fact,
    FactCategory,
    find_facts,
    group_facts_by_category,
)
from openchem.domain.result_ordering import ALWAYS_ON

#: The reader entry's id. **NOT A `calculator_id`** -- see the module
#: docstring. Reserved so nothing can register a calculator that collides
#: with it; `test_the_aggregate_id_is_not_a_registered_calculator` holds that.
DESCRIPTOR_AGGREGATE_ID = "molecular_properties"

#: What the entry is called on screen.
DESCRIPTOR_AGGREGATE_NAME = "Molecular Properties"

#: Descriptors whose value is exact arithmetic or a count over the structure.
#: `Basis`' own docstring draws the line: DETERMINISTIC is "it is right, or
#: the periodic table is wrong"; HEURISTIC "depends on a threshold somebody
#: chose".
#:
#: **CONSERVATIVE, AND IT ERRS TOWARDS UNDERSTATING.** Only the cases where
#: the claim is unambiguous are listed; everything else -- fitted contribution
#: schemes (LogP, molar refractivity, Labute ASA), models (QED, ESOL, SA
#: score) and the rule filters, whose thresholds are literally the docstring's
#: example of heuristic -- falls to HEURISTIC. That mislabels a few exact
#: quantities as judgement, which understates them.
#:
#: The alternative error is worse and is why the default runs this way:
#: labelling a fitted model deterministic would overstate a claim, which is
#: the failure this project spends its time removing. A per-descriptor
#: declaration by the producer would beat both and is not in scope here --
#: `_DESCRIPTOR_SPECS` carries no basis field today.
DETERMINISTIC_DESCRIPTORS = frozenset(
    {
        "formula",
        "mol_wt",
        "exact_mass",
        "heavy_atom_count",
        "ring_count",
        "formal_charge",
        "num_stereocenters",
    }
)


def _basis_for(descriptor: DescriptorValue) -> Basis:
    return (
        Basis.DETERMINISTIC
        if descriptor.descriptor_id in DETERMINISTIC_DESCRIPTORS
        else Basis.HEURISTIC
    )


def _display(descriptor: DescriptorValue) -> tuple[str, tuple[str, ...]]:
    """What the row shows, and what belongs behind it.

    **`describe_failure` OWNS THE SPLIT, NOT THIS FUNCTION.** It decides which
    string is the short cell form and which is the full explanation, and the
    Properties panel already renders both halves through it. Re-deciding here
    would be a second policy on one question -- and the reason that function
    exists is that a producer had exactly one string with which to be both a
    table cell and an explanation, and the cell lost.
    """
    if descriptor.cache_state is CacheState.FAILED:
        cell, reason = describe_failure(descriptor.error, descriptor.error_summary)
        return cell, (reason,) if reason else ()
    if descriptor.cache_state in (CacheState.QUEUED, CacheState.RUNNING):
        # A snapshot taken mid-batch is a real state, not a gap. Saying so
        # beats an empty cell, which reads as a value of nothing.
        return descriptor.cache_state.value.capitalize() + "...", ()
    # **THE ONLY RENDERING OF A DESCRIPTOR VALUE, AND IT USED TO BE ONE OF
    # TWO.** bool -> Pass/Fail, float -> `.4g`, None -> empty. The Properties
    # panel had `_format_value` doing the same job for its own row, so a
    # descriptor could show 247.3 in one place and 247.34 in the other --
    # a disagreement this area kept producing, held off by a test asserting
    # the two agreed. 2c removed the row and its renderer with it, so the
    # class is designed out rather than guarded: there is nothing left to
    # disagree with.
    #
    # What the panel's added was a status GLYPH and a Qt stylesheet -- the
    # green tick on a boolean -- which are presentation, and `domain/` holds
    # neither. That is the one thing genuinely lost with the row: the WORD
    # survives here and the glyph does not,
    # and `test_the_two_renderings_of_a_descriptor_value_agree` asserts that
    # rather than trusting this comment.
    value = descriptor.value
    if value is None:
        return "", ()
    if isinstance(value, bool):
        return "Pass" if value else "Fail", ()
    if isinstance(value, float):
        return f"{value:.4g}", ()
    return str(value), ()


def fact_for(descriptor: DescriptorValue) -> Fact:
    """One descriptor as a fact, keeping the units OUT of the label.

    `Fact.units` belongs to `value` -- its own comment says so -- and
    `value_with_units` composes the two. Folding them into the label instead
    is what made `report_adapter`'s 223 facts export "C: 60.00 % %", so the
    label is the plain name here and the units stay their own field.
    """
    display, limitations = _display(descriptor)
    return Fact(
        category=category_for(descriptor.category),
        label=descriptor.name,
        value=descriptor.value,
        display_value=display,
        source=descriptor.provider or "core",
        basis=_basis_for(descriptor),
        units=descriptor.units,
        limitations=limitations,
    )


@dataclass(frozen=True)
class DescriptorAggregate:
    """Every auto-computed descriptor for one molecule, as one reader entry.

    Satisfies the reader contract -- `report_id`, `facts`, `by_category()`,
    `find()` -- so it passes through the same admission door as a report
    rather than a side one, and holds the originals so nothing is lost.
    """

    #: **THE ONE ENTRY IN THIS APPLICATION THAT BELONGS TO NO SECTION.**
    #: Its 41 descriptors span TEN different calculator categories
    #: (medicinal chemistry 13, physicochemical 5, topology 5, admet 2, and
    #: six more with one apiece), so no single section is true of it --
    #: while every calculator result has exactly one. Declaring the band is
    #: what keeps `result_ordering` from having to guess, and what stops the
    #: only entry that is ALWAYS present sorting below every calculator that
    #: happens to have run.
    #:
    #: A class attribute rather than a field, deliberately: it is a property
    #: of the TYPE, not of an instance, so no aggregate can present itself as
    #: belonging to a section -- the same reason `report_id` is a read-only
    #: property here.
    display_band = ALWAYS_ON

    molecule_uuid: str
    #: The originals, untouched. Each keeps its own `cache_state`, `error`,
    #: `error_summary`, `inapplicable`, `provider` and `timestamp`.
    descriptors: tuple[DescriptorValue, ...] = ()
    #: The flat view a `FactView` consumes. A field rather than a property,
    #: mirroring `MergedResults`: built once by the factory below, so the
    #: originals and the view cannot be recomputed into disagreement.
    facts: tuple[Fact, ...] = ()
    structure_version: int = 0
    #: **PART OF THE READER CONTRACT, AND THEY WERE MISSING.** `FactView`
    #: reads `limitations` directly to build its status line and
    #: `report_format` reads both to export one, so without them this
    #: container passed the admission door and then raised in a PAINT path:
    #: focusing "Molecular Properties" gave `AttributeError: ... has no
    #: attribute 'limitations'`, and Copy report raised on three of its four
    #: formats. Nothing noticed because nothing focused it.
    #:
    #: Empty by default rather than filled with a sentence about descriptors
    #: in general: each one carries its OWN state and its own reason, which
    #: is the whole point of this being a container rather than a conversion.
    limitations: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    @property
    def report_id(self) -> str:
        """Read-only, so no instance can present itself as something else.

        A field with a default could be overridden per instance, and an
        aggregate wearing a calculator's id would be focusable as that
        calculator while containing none of its results.
        """
        return DESCRIPTOR_AGGREGATE_ID

    @property
    def name(self) -> str:
        return DESCRIPTOR_AGGREGATE_NAME

    def by_category(self) -> dict[FactCategory, tuple[Fact, ...]]:
        return group_facts_by_category(self.facts)

    def find(self, text: str) -> tuple[Fact, ...]:
        """**SHARED, BECAUSE THIS ONE HAD DRIFTED.** It searched the label and
        the value only, so the reader's one search box matched no evidence
        while it was focused here and did while it was focused on a
        calculator's report. Nobody could see that: the aggregate's facts
        carry no evidence today, so the divergence was latent and would have
        surfaced the day `fact_for` started attaching some."""
        return find_facts(self.facts, text)

    def descriptor_for(self, descriptor_id: str) -> DescriptorValue | None:
        """The ORIGINAL, for a consumer that needs its state.

        The reason this container exists rather than a conversion: a reader
        rendering a per-row status glyph asks here, not the flattened fact.
        """
        for descriptor in self.descriptors:
            if descriptor.descriptor_id == descriptor_id:
                return descriptor
        return None

    def failed(self) -> tuple[DescriptorValue, ...]:
        return tuple(d for d in self.descriptors if d.cache_state is CacheState.FAILED)

    def inapplicable(self) -> tuple[DescriptorValue, ...]:
        """A REFUSAL IS NOT A FAULT, and the existing field separates them.

        Kept apart from `failed()` because painting a method limit as a crash
        is what made two working calculators read as broken.
        """
        return tuple(d for d in self.descriptors if getattr(d, "inapplicable", False))


def aggregate_descriptors(
    molecule_uuid: str, descriptors, structure_version: int = 0
) -> DescriptorAggregate:
    """Build the aggregate, deriving the flat view once.

    **ONLY THIS MOLECULE'S DESCRIPTORS.** A descriptor naming a different
    molecule is dropped rather than folded in -- the panel holds values for
    whatever it last computed, and a stale one from a previous selection would
    appear under the current molecule's name with nothing saying otherwise.

    Order is the producer's. `_DESCRIPTOR_SPECS` is written in a deliberate
    reading order (formula, weight, LogP, TPSA...), and sorting alphabetically
    here would discard it for no gain -- the reader groups by category anyway.
    """
    kept = tuple(
        d for d in descriptors if getattr(d, "molecule_uuid", None) == molecule_uuid
    )
    return DescriptorAggregate(
        molecule_uuid=molecule_uuid,
        descriptors=kept,
        facts=tuple(fact_for(d) for d in kept),
        structure_version=structure_version,
    )
