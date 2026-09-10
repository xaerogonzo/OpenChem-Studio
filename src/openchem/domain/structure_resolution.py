"""Whether a result's structure-bound picture may be drawn, and against what.

**A DEPICTION CARRIES ATOM INDICES AND NO GEOMETRY.** That is deliberate --
an annotation holding an RDKit molecule would put a toolkit object in
`domain/` and give the report a second copy of the structure -- so the host
supplies the coordinates at render time. `FactView.set_structure_resolver` is
that injection point.

**AND THE OBVIOUS RESOLVER IS UNSAFE.** `project.find_molecule(uuid).molblock`
returns the CURRENT structure. A Lewis depiction, a per-atom dataset or a
spatial annotation describes the structure it was COMPUTED ON. Edit the
molecule and the old result stays visible, correctly marked stale -- while its
atom indices now address a different structure:

    result computed at structure version 12
    molecule edited to version 13
    result correctly marked stale, still on screen
    the depiction's atom 7 is now atom 7 of a different molecule

The picture looks entirely normal and highlights a chemically unrelated atom.
That is worse than refusing to draw it, and it is this repository's worst
recorded failure class: correct machinery producing a plausible-looking lie.

**REFUSAL IS THE ONLY HONEST OPTION HERE, AND THAT IS A MEASUREMENT RATHER
THAN A PREFERENCE.** `MoleculeModel` stores exactly one `molblock` and no
history, so there is no snapshot of version 12 to resolve against. If one is
ever kept, `StructureRequest` is where that route lands and the refusal
becomes a fallback rather than the answer.

**TWO IDENTITIES, KEPT SEPARATE.** They answer different questions and a
result can pass one while failing the other:

    structure version    is this the same STRUCTURE the result describes?
                         `report.structure_version` against the molecule's
    geometry identity    which CONFORMER did it run on?
                         `input_source` / `input_conformer_id` in provenance,
                         recorded by `geometry_provenance`

A result can be current for the molecule and computed on a stored conformer
that is not the one being displayed -- so a resolver that loads "whatever
conformer is on screen" is wrong even when nothing is stale. Collapsing the
two into one "is this fresh" flag is how that distinction gets lost.

Nothing here reads a project or a file: these are decisions about identity,
and the host performs the lookup only once they come back clear.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Provenance keys `geometry_provenance` writes. Named here rather than
#: re-derived, and NOT imported from `chem/` -- `domain/` does not depend on
#: the chemistry layer, and `INPUT_PREFIX` is a persisted key rather than a
#: private detail. `test_the_input_keys_match_geometry_provenance` asserts the
#: two agree, so a rename cannot make this quietly stop matching.
INPUT_SOURCE_KEY = "input_source"
#: Which conformer a geometry-based result ran on. The `#:` ratchet caught
#: this one orphaned under the block above -- the exact
#: `ENTHALPY_NOT_SUPPLIED` shape it was built for, where a doc comment ends up
#: describing the constant that happens to follow it.
INPUT_CONFORMER_KEY = "input_conformer_id"

#: What `input_source` says when the result was computed on the 2D drawing
#: rather than a conformer. Such a result is not conformer-bound, so a change
#: to the conformer set cannot invalidate its picture.
DRAWING_SOURCE = "drawing"


def is_stale(report_version: int, current_version: int) -> bool:
    """Whether a result describes a structure that has since changed.

    **THE ONE IMPLEMENTATION.** `MergedResults.is_stale` calls this rather
    than repeating the comparison, because staleness now decides whether a
    PICTURE is drawn as well as whether a badge is shown -- and two rules that
    are supposed to agree about that would be a bug nobody could see, since
    both answers look reasonable in isolation.

    A report stamped 0 against a current version above 0 counts as stale,
    which is the honest answer for "this one does not say when it was
    computed" -- and the reason every calculator result is stamped in ONE
    place rather than left at the default.
    """
    return report_version != current_version


@dataclass(frozen=True)
class StructureRequest:
    """What a host is being asked to resolve, and whether it may.

    A value rather than a bare molblock string, because "" cannot say whether
    it means "no structure" or "refused, and here is why" -- and a reader
    shown an empty frame with no reason is the silent failure this module
    exists to prevent.
    """

    #: The molecule to look up. Empty when the result names none.
    molecule_uuid: str = ""
    #: Why the picture must not be drawn, or "" when it may be. Reader-facing
    #: prose: it is shown where the picture would have been.
    refusal: str = ""
    #: The conformer the result was computed on, when it declares one.
    #: A host that has it should prefer it over whatever is displayed; a host
    #: that cannot find it refuses rather than substituting another.
    conformer_id: str = ""

    @property
    def allowed(self) -> bool:
        return not self.refusal and bool(self.molecule_uuid)


def structure_request(report, current_version: int) -> StructureRequest:
    """What may be drawn for `report`, and against which geometry.

    Pure: it reads the report's own identity and returns a decision. The host
    performs the lookup, and only when `allowed`.
    """
    uuid = getattr(report, "molecule_uuid", "") or ""
    if not uuid:
        # Not a refusal with a reason -- there is nothing to refuse. A report
        # naming no molecule has no structure-bound picture to get wrong.
        return StructureRequest()

    version = getattr(report, "structure_version", 0) or 0
    if is_stale(version, current_version):
        return StructureRequest(
            molecule_uuid=uuid,
            refusal=(
                "Visualization unavailable -- this result was calculated for "
                f"an earlier version of this structure (version {version}; "
                f"the molecule is now at {current_version}). Its atom numbering "
                "describes the structure at that time, so drawing it on the "
                "current one would point at the wrong atoms. Re-run the "
                "calculator to see the picture."
            ),
        )

    provenance = getattr(report, "provenance", None)
    parameters = getattr(provenance, "parameters", None) or {}
    source = parameters.get(INPUT_SOURCE_KEY)
    # A drawing-based result is not conformer-bound: regenerating conformers
    # cannot invalidate its picture, so it must not be refused for one.
    conformer_id = (
        "" if source in (None, DRAWING_SOURCE) else str(parameters.get(INPUT_CONFORMER_KEY) or "")
    )
    return StructureRequest(molecule_uuid=uuid, conformer_id=conformer_id)


@dataclass(frozen=True)
class ResolvedStructure:
    """What a host handed back: coordinates to draw on, or why not.

    **THE RESOLVER RETURNS THIS RATHER THAN A MOLBLOCK STRING**, because ""
    cannot distinguish "no structure" from "refused, and here is why" -- and a
    reader shown an empty frame with no reason is exactly the silent failure
    this module exists to prevent. A view renders `refusal` where the picture
    would have gone.
    """

    molblock: str = ""
    refusal: str = ""

    @classmethod
    def of(cls, molblock: str) -> "ResolvedStructure":
        return cls(molblock=molblock or "")

    @classmethod
    def refused(cls, reason: str) -> "ResolvedStructure":
        return cls(refusal=reason)

    @property
    def drawable(self) -> bool:
        return bool(self.molblock) and not self.refusal


def resolve_structure_for_report(report, project, current_version: int) -> ResolvedStructure:
    """The production resolver: coordinates for `report`'s depiction, or why not.

    **THE ONE PLACE BOTH IDENTITIES ARE ENFORCED**, so a host wires this in
    rather than writing `project.find_molecule(uuid).molblock` -- which is the
    unsafe resolver this module exists to replace, and the obvious thing to
    reach for.

        stale structure    refused, with the version numbers, because the
                           result's atom indices describe a molecule that no
                           longer exists
        conformer-bound    drawn on ITS conformer, found by id -- never on
                           whichever one happens to be displayed
        conformer gone     refused rather than substituted. A different
                           conformer is a different geometry, and drawing on
                           it silently would be the same class of wrong.
        drawing-based      the molecule's own molblock, which is what it was
                           computed on

    Refusals are reader-facing prose: they are rendered where the picture
    would have been, so they say what happened and what to do about it rather
    than naming an internal state.
    """
    request = structure_request(report, current_version)
    if request.refusal:
        return ResolvedStructure.refused(request.refusal)
    if not request.molecule_uuid:
        return ResolvedStructure()

    molecule = project.find_molecule(request.molecule_uuid) if project is not None else None
    if molecule is None:
        return ResolvedStructure.refused(
            "Visualization unavailable -- the molecule this result was "
            "calculated for is no longer in this project."
        )

    if request.conformer_id:
        conformer = next(
            (c for c in molecule.conformers if c.conformer_id == request.conformer_id), None
        )
        if conformer is None:
            return ResolvedStructure.refused(
                "Visualization unavailable -- this result was calculated on a "
                "conformer that is no longer in this project. Re-run the "
                "calculator to see the picture against a current geometry."
            )
        return ResolvedStructure.of(conformer.molblock or "")

    return ResolvedStructure.of(getattr(molecule, "molblock", "") or "")
