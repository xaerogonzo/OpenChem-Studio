"""The closed vocabulary of result kinds the application presents.

**ONE VOCABULARY, SEVERAL PRESENTATIONS.** A calculator result is shown in at
least three ways -- summarised into the results reader, serialised to the
clipboard, and opened in a rich viewer -- and each of those had its own idea of
what kinds exist. `ui/result_clipboard.py` grew a type-keyed dispatch and is
described in its own header as "the third registry in this codebase to use it",
after `_VISUALIZATION_ADAPTERS` and `_RESULT_VIEW_FACTORIES`. Three registries
over one vocabulary is three chances to disagree about what a result IS.

**THE VOCABULARY IS HERE; THE ADAPTERS ARE NOT.** This module answers "what
kind of result is this". It does not answer "how is it summarised" or "which
window opens it" -- those are presentation concerns and live in
`ui/result_adapters.py`, because `domain/` knowing that a per-atom dataset
opens the Calculator Inspector would put UI routing in the scientific layer.
The split is deliberate:

    domain      this is a PerAtomDataset
    ui          a PerAtomDataset is summarised thus and opens that viewer

**REGISTERED BY CLASS IDENTITY, NEVER BY NAME.** This tree contains TWO
unrelated classes called `CorrelationResult` -- `chem/analytics.py`'s statistics
value (pearson/spearman/n/slope/intercept) and
`domain/scientific_result.py`'s 2D-NMR cross peaks. A registry keyed on
`__name__` would resolve one to the other's adapter, and both are plausible
enough that nothing downstream would complain.

**A SUBCLASS SHARES ITS BASE'S KIND UNLESS IT REGISTERS ITS OWN**, resolved
through the MRO so "nearest registered ancestor" falls out rather than being
computed. That rule is not new -- `result_to_text` already matched
`SpectrumResult` by isinstance so `NMRSpectrumResult` would not "silently fall
through to the generic fallback", in its own words.

What IS new is that the same mechanism had a victim. `VibrationalSpectrumResult`
also subclasses `SpectrumResult`, and the generic spectrum rendering is NMR
vocabulary -- an `Atom / Element / Shift` table keyed on atom index. A
vibrational result deliberately leaves `values` and `elements` EMPTY (its own
docstring says a vibrational peak is not a property of an atom; the data is in
`modes`), so copying an IR spectrum produced a header and no rows at all.
Measured on the shipped code:

    'IR Spectrum\\nAtom\\tElement\\tShift (cm^-1)'

Two lines, both modes dropped. So a specialization is registered for it, and
`test_a_vibrational_spectrum_is_not_treated_as_an_nmr_one` is the guard.

Unknown kinds are REFUSED LOUDLY rather than silently summarised to nothing --
a blank result is the failure this whole area keeps producing, and an exception
naming the class is what turns the next one into a test failure instead.
"""

from __future__ import annotations

#: A report of facts -- the results reader's native shape.
REPORT = "report"
#: A catalog or string-list result, bridged into facts by `report_adapter`.
ALERT = "alert"
#: One value per atom index. Rich view: the per-atom inspector.
PER_ATOM = "per_atom"
#: A spectrum keyed by atom index -- NMR today. See `VIBRATIONAL_SPECTRUM` for
#: why that qualifier matters.
SPECTRUM = "spectrum"
#: A harmonic vibrational spectrum. **ITS OWN KIND, NOT A SPECTRUM**, because
#: its data is per NORMAL MODE rather than per atom -- so every rendering that
#: assumes an atom-keyed spectrum produces an empty table for it.
VIBRATIONAL_SPECTRUM = "vibrational_spectrum"
#: A property sampled across a pH range.
PH_CURVE = "ph_curve"
#: A set of generated structures -- tautomers, stereoisomers, resonance forms.
STRUCTURE_SET = "structure_set"
#: A molecular-dynamics trajectory.
TRAJECTORY = "trajectory"

#: Every kind, and the ONLY list of them. Closed for the reason
#: `PARAMETER_KINDS` is: an unregistered kind reaching a dispatch matches no
#: branch and produces a silently empty presentation.
RESULT_KINDS = frozenset(
    {
        REPORT,
        ALERT,
        PER_ATOM,
        SPECTRUM,
        VIBRATIONAL_SPECTRUM,
        PH_CURVE,
        STRUCTURE_SET,
        TRAJECTORY,
    }
)


class UnknownResultKind(TypeError):
    """A result this application has no vocabulary for.

    Raised rather than defaulted. A default would produce a plausible-looking
    empty presentation, which is precisely the class of failure the results
    work exists to remove -- and the caller cannot tell it from a result that
    genuinely had nothing to say.
    """


def _registry() -> dict[type, str]:
    """Class -> kind, built on first use.

    Imported lazily so this module stays importable from anywhere in
    `domain/` without an import cycle through `domain/report.py`, which
    imports `domain/visualization.py`.
    """
    from openchem.domain.report import ReportResult
    from openchem.domain.scientific_result import (
        AlertResult,
        PerAtomDataset,
        PhCurveResult,
        SpectrumResult,
        StructureSetResult,
        TrajectoryResult,
        VibrationalSpectrumResult,
    )

    return {
        ReportResult: REPORT,
        AlertResult: ALERT,
        PerAtomDataset: PER_ATOM,
        SpectrumResult: SPECTRUM,
        # A SPECIALIZATION, and the reason the mechanism needs one. Without
        # this entry it resolves to SPECTRUM through the MRO and is rendered
        # as an atom-keyed table it has no atoms for.
        VibrationalSpectrumResult: VIBRATIONAL_SPECTRUM,
        PhCurveResult: PH_CURVE,
        StructureSetResult: STRUCTURE_SET,
        TrajectoryResult: TRAJECTORY,
    }


def kind_of(result: object) -> str:
    """Which kind `result` is, or raise `UnknownResultKind`.

    Resolved through the MRO, so an exact registration wins and anything else
    takes its nearest registered ancestor. `NMRSpectrumResult` is not
    registered and correctly shares `SPECTRUM`; `VibrationalSpectrumResult` is,
    and does not.

    By class identity rather than by name -- see the module docstring for the
    two `CorrelationResult` classes that make that distinction load-bearing.
    """
    registry = _registry()
    for ancestor in type(result).__mro__:
        kind = registry.get(ancestor)
        if kind is not None:
            return kind
    raise UnknownResultKind(
        f"no result kind registered for {type(result).__module__}."
        f"{type(result).__qualname__} -- register one in domain/result_kinds.py "
        f"rather than letting it fall through to an empty presentation"
    )


def kind_or_none(result: object) -> str | None:
    """`kind_of`, for a caller that legitimately handles "not one of ours".

    Separate from `kind_of` rather than a flag on it, so the refusing form
    stays the default. A caller that wants silence has to say so.
    """
    try:
        return kind_of(result)
    except UnknownResultKind:
        return None
