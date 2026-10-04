"""Tautomer NMR: which structures to calculate, and how a tautomer's jobs become its spectrum.

**WHAT THIS IS FOR.** A tautomer-distribution result already holds, for each tautomer, the geometry ORCA's
optimization ended at (`optimized_molblock`) and its energy. P5 runs NMR on those structures
(`docs/TAUTOMER_NMR_DESIGN.md`). This module is the part that needs no ORCA: choosing the structures out of a
stored result, and combining one tautomer's conformer spectra into its own spectrum.

**ONE STRUCTURE PER TAUTOMER BY DEFAULT.** The structure is the one the distribution already uses to
represent the tautomer: its lowest calculated candidate. With `per_conformer`, the jobs are every succeeded
conformer of THAT stereoisomer, which share one atom order (they are embeddings of the same molecule) and so
can be Boltzmann-averaged atom by atom. Conformers of a DIFFERENT stereoisomer are never averaged in:
diastereomers are different compounds, and the distribution already gives each tautomer one stereoisomer.

**NOTHING IS GUESSED.** A tautomer whose structure was not stored (a result computed before the geometry was
kept), or whose representative did not succeed, is reported as a problem and left out, never given a
substitute geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.scientific_result import StructureSetResult


@dataclass(frozen=True)
class NmrJob:
    """One structure to run NMR on: a succeeded candidate's optimized geometry."""

    candidate_fingerprint: str
    optimized_molblock: str
    absolute_energy_hartree: float


@dataclass(frozen=True)
class TautomerNmrTarget:
    """One tautomer's NMR work: one job, or one per conformer of its representative stereoisomer."""

    tautomer_fingerprint: str
    #: The tautomer's SMILES as the distribution labelled it, without the stereo/conformer marks.
    label: str
    #: The drawing the distribution result showed for it (2D, as drawn).
    display_molblock: str
    jobs: tuple[NmrJob, ...]


def _label_of(entry_label: str) -> str:
    """`CC(O)=C [2 of 3] [conf 1/3]` -> `CC(O)=C`: the structure, not which job of it this was."""
    return entry_label.split(" [", 1)[0]


def targets_from_distribution(
    result: StructureSetResult, *, per_conformer: bool = False
) -> tuple[list[TautomerNmrTarget], list[str]]:
    """The tautomers of `result` that NMR can be run on, in order of ascending relative energy, and a list of
    problems for the ones it cannot.

    A tautomer is taken from its representative (`is_lowest_calculated_for_tautomer`). Its geometry must have
    been stored; with `per_conformer`, so must every other succeeded conformer of that stereoisomer, or the
    tautomer is reported rather than averaged over a subset (a subset would silently weight it differently).
    """
    by_tautomer: dict[str, list] = {}
    for entry in result.entries:
        by_tautomer.setdefault(entry.metadata.get("tautomer_fingerprint", ""), []).append(entry)

    targets: list[TautomerNmrTarget] = []
    problems: list[str] = []
    for tautomer, entries in by_tautomer.items():
        succeeded = [e for e in entries if e.metadata.get("status") == "succeeded"]
        representative = next((e for e in succeeded if e.metadata.get("is_lowest_calculated_for_tautomer")), None)
        name = _label_of(entries[0].label) or tautomer[:12]
        if representative is None:
            problems.append(f"{name}: no candidate of this tautomer succeeded, so there is no geometry to run NMR on")
            continue
        chosen = [representative]
        if per_conformer:
            stereo = representative.metadata.get("stereo_fingerprint")
            chosen = [e for e in succeeded if e.metadata.get("stereo_fingerprint") == stereo]
            chosen.sort(key=lambda e: (e.metadata.get("conformer_index", 0), e.metadata["fingerprint"]))
        missing = [e for e in chosen if not e.metadata.get("optimized_molblock")]
        if missing:
            problems.append(
                f"{name}: the optimized geometry was not stored for {len(missing)} of {len(chosen)} job(s) "
                f"(a result computed before geometries were kept); rerun the tautomer distribution"
            )
            continue
        jobs = tuple(
            NmrJob(
                candidate_fingerprint=e.metadata["fingerprint"],
                optimized_molblock=e.metadata["optimized_molblock"],
                absolute_energy_hartree=float(e.metadata["absolute_energy_hartree"]),
            )
            for e in chosen
        )
        targets.append(
            TautomerNmrTarget(
                tautomer_fingerprint=tautomer,
                label=name,
                display_molblock=representative.molblock,
                jobs=jobs,
            )
        )
    relative = {
        e.metadata.get("tautomer_fingerprint", ""): e.energy
        for e in result.entries
        if e.metadata.get("is_lowest_calculated_for_tautomer")
    }
    targets.sort(
        key=lambda t: (relative.get(t.tautomer_fingerprint) is None, relative.get(t.tautomer_fingerprint) or 0.0,
                       t.tautomer_fingerprint)
    )
    return targets, problems
