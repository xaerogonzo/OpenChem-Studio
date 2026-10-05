"""Tautomer NMR: which structures to calculate, and how a tautomer's jobs become its spectrum.

**WHAT THIS IS FOR.** A tautomer-distribution result already holds, for each tautomer, the geometry ORCA's
optimization ended at (`optimized_molblock`) and its energy. P5 runs NMR on those structures
(`docs/TAUTOMER_NMR_DESIGN.md`). This module is the part that needs no ORCA: choosing the structures out of a
stored result, combining one tautomer's conformer spectra into its own spectrum, and the population-weighted
fast-exchange average across tautomers (`average_tautomer_nmr`).

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

from collections.abc import Sequence
from dataclasses import dataclass

from rdkit import Chem

from openchem.domain.scientific_result import StructureSetResult, TautomerNmrEntry, TautomerNmrResult


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
        missing = [
            e for e in chosen
            if not e.metadata.get("optimized_molblock") or e.metadata.get("absolute_energy_hartree") is None
        ]
        if missing:
            problems.append(
                f"{name}: the optimized geometry or energy was not stored for {len(missing)} of {len(chosen)} job(s) "
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


# --- the population-weighted fast-exchange average --------------------------------------------------------

#: The only element whose hydrogens are averaged. Hydrogens on N, O, S or any other heteroatom exchange with
#: solvent and with each other, so a gas-phase shift for them would mislead.
_CARBON = "C"


@dataclass(frozen=True)
class AveragedPeak:
    """One peak of the fast-exchange average, defined per HEAVY atom (the atom whose index survives tautomerism)."""

    nucleus: str  # "13C" or "1H"
    heavy_atom: int
    element: str
    shift_ppm: float
    #: Hydrogens this peak stands for (the carbon's, identical in every tautomer); 0 for a 13C peak.
    hydrogen_count: int
    #: `(tautomer fingerprint, that tautomer's own shift)`, so the average can be traced to its parts.
    per_tautomer: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class NotAveraged:
    """A heavy atom's peak that is deliberately left out of the average, and why. Never dropped silently."""

    nucleus: str
    heavy_atom: int
    element: str
    reason: str


@dataclass(frozen=True)
class TautomerAverage:
    """The fast-exchange average of a tautomer NMR result, or why there is none."""

    available: bool
    #: Why it is not available (empty when it is).
    reason: str = ""
    #: `(tautomer fingerprint, population)` used, in the NMR result's order.
    weights: tuple[tuple[str, float], ...] = ()
    peaks: tuple[AveragedPeak, ...] = ()
    not_averaged: tuple[NotAveraged, ...] = ()


def _unavailable(reason: str) -> TautomerAverage:
    return TautomerAverage(available=False, reason=reason)


def _molecule_of(distribution: StructureSetResult, entry: TautomerNmrEntry) -> Chem.Mol | None:
    """The hydrogen-explicit structure `entry`'s spectrum is indexed on: the optimized geometry of its first
    job, parsed exactly as the NMR run parsed it, so the atom indices are the spectrum's."""
    wanted = entry.job_fingerprints[0] if entry.job_fingerprints else ""
    for candidate in distribution.entries:
        if candidate.metadata.get("fingerprint") == wanted and candidate.metadata.get("optimized_molblock"):
            return Chem.MolFromMolBlock(candidate.metadata["optimized_molblock"], removeHs=False)
    return None


def _hydrogens(mol: Chem.Mol, heavy: int) -> list[int]:
    return [n.GetIdx() for n in mol.GetAtomWithIdx(heavy).GetNeighbors() if n.GetAtomicNum() == 1]


def average_tautomer_nmr(nmr: TautomerNmrResult, distribution: StructureSetResult) -> TautomerAverage:
    """The population-weighted fast-exchange average of `nmr`, using `distribution`'s validated populations.

    **WHEN THERE IS NONE.** The average is the claim "these tautomers interconvert faster than the NMR
    timescale and populate as the validated model says", so it exists only when every ingredient does: the
    distribution is `validated` and complete, the NMR result is complete and was computed from THAT
    distribution run, every spectrum is referenced (ppm shifts, not shieldings), and the tautomers' heavy atoms
    correspond. Anything else returns `available=False` with the reason; there is no partial average.

    **THE RULE** (`docs/TAUTOMER_NMR_DESIGN.md`), per heavy atom: a carbon's 13C shift is the weighted mean over
    the tautomers; a carbon's 1H peak is the weighted mean over the tautomers of the mean of its hydrogens'
    shifts, but ONLY when the carbon carries the same number of hydrogens in every tautomer; hydrogens on
    nitrogen, oxygen, sulfur or any other heteroatom are never averaged. Each left-out peak is reported in
    `not_averaged` with its reason.
    """
    params = distribution.provenance.parameters if distribution.provenance else {}
    if params.get("validation_branch") != "validated":
        return _unavailable("the tautomer populations are not validated for this model, so no average is offered")
    if not params.get("complete"):
        return _unavailable("the tautomer distribution is incomplete, so there are no populations to weight with")
    if not nmr.parent_run_id or nmr.parent_run_id != params.get("parent_run_id"):
        return _unavailable("this NMR result was not computed from this tautomer distribution")
    if not nmr.complete:
        return _unavailable("not every tautomer has an NMR spectrum")
    populations = {
        e.metadata.get("tautomer_fingerprint"): e.score
        for e in distribution.entries
        if e.metadata.get("is_lowest_calculated_for_tautomer") and e.score is not None
    }
    entries = nmr.entries
    if {e.tautomer_fingerprint for e in entries} != set(populations):
        return _unavailable("the NMR tautomers and the distribution's tautomers are not the same set")
    weights = tuple((e.tautomer_fingerprint, float(populations[e.tautomer_fingerprint])) for e in entries)
    if abs(sum(w for _fp, w in weights) - 1.0) > 1e-6:
        return _unavailable("the tautomer populations do not sum to one")
    for entry in entries:
        spectrum = entry.spectrum
        if spectrum is None or spectrum.spectrum_type == "nmr_raw_shielding" or spectrum.units != "ppm":
            return _unavailable("an NMR spectrum is not referenced to chemical shifts (ppm)")

    molecules = []
    for entry in entries:
        mol = _molecule_of(distribution, entry)
        if mol is None:
            return _unavailable(f"the structure behind {entry.label}'s spectrum is not stored")
        molecules.append(mol)
    skeleton = [[a.GetSymbol() for a in m.GetAtoms() if a.GetAtomicNum() > 1] for m in molecules]
    if any(s != skeleton[0] for s in skeleton[1:]):
        return _unavailable("the tautomers' heavy atoms do not correspond, so there is nothing to pair across them")

    weight = dict(weights)

    def mean(per_entry: Sequence[float]) -> float:
        return sum(weight[e.tautomer_fingerprint] * s for e, s in zip(entries, per_entry, strict=True))

    def parts(per_entry: Sequence[float]) -> tuple[tuple[str, float], ...]:
        return tuple((e.tautomer_fingerprint, s) for e, s in zip(entries, per_entry, strict=True))

    peaks: list[AveragedPeak] = []
    left_out: list[NotAveraged] = []
    for heavy, element in enumerate(skeleton[0]):
        counts = [len(_hydrogens(m, heavy)) for m in molecules]
        if element != _CARBON:
            if max(counts) > 0:
                left_out.append(NotAveraged(
                    "1H", heavy, element,
                    f"a hydrogen on {element} exchanges with solvent and other tautomers; it appears on each "
                    f"tautomer's own trace only",
                ))
            continue
        carbon = [e.spectrum.values.get(heavy) for e in entries]
        if any(s is None for s in carbon):
            left_out.append(NotAveraged("13C", heavy, element, "no 13C shift in every tautomer"))
        else:
            peaks.append(AveragedPeak("13C", heavy, element, mean(carbon), 0, parts(carbon)))
        if max(counts) == 0:
            continue
        if len(set(counts)) > 1:
            left_out.append(NotAveraged(
                "1H", heavy, element,
                "its hydrogen count changes between tautomers (" + ", ".join(str(c) for c in counts) + ")",
            ))
            continue
        per_tautomer = []
        for entry, mol in zip(entries, molecules, strict=True):
            values = [entry.spectrum.values.get(h) for h in _hydrogens(mol, heavy)]
            if any(v is None for v in values):
                per_tautomer = []
                break
            per_tautomer.append(sum(values) / len(values))
        if not per_tautomer:
            left_out.append(NotAveraged("1H", heavy, element, "no 1H shift for every hydrogen in every tautomer"))
            continue
        peaks.append(AveragedPeak("1H", heavy, element, mean(per_tautomer), counts[0], parts(per_tautomer)))
    return TautomerAverage(available=True, weights=weights, peaks=tuple(peaks), not_averaged=tuple(left_out))


# --- what the viewer draws --------------------------------------------------------------------------------

#: Element keys the NMR viewer uses for its nucleus choice ("H" for 1H, "C" for 13C).
NUCLEUS_ELEMENTS = ("H", "C")


@dataclass(frozen=True)
class TracePeak:
    """One stick of a trace: a carbon's 13C, a group of hydrogens on one heavy atom, or one averaged peak."""

    shift_ppm: float
    #: Stick height in the plot's own unit: the number of hydrogens it stands for (1 for a 13C peak), so a
    #: trace's heights mean the same thing as the molecule's own signals' integrations.
    weight: float
    heavy_atom: int
    #: A hydrogen on N, O, S or another heteroatom: drawn, but marked, because it is not averaged and
    #: exchanges with solvent.
    labile: bool = False


@dataclass(frozen=True)
class TautomerTrace:
    """One trace on the overlay: a tautomer's own peaks, or the fast-exchange average."""

    key: str  # the tautomer's fingerprint, or "average"
    label: str
    is_average: bool
    #: The validated population, or None (not validated, or the average itself).
    population: float | None
    relative_energy_kcal: float | None
    #: Peaks by nucleus element ("H" / "C"). Empty for a tautomer whose NMR failed.
    peaks: dict[str, tuple[TracePeak, ...]]
    failure: str = ""


@dataclass(frozen=True)
class TautomerOverlay:
    """Everything the viewer shows for a tautomer NMR result."""

    traces: tuple[TautomerTrace, ...]
    #: The fast-exchange average, or None when it is unavailable (`average_note` says why).
    average: TautomerTrace | None
    #: Why there is no average, or how much of the spectrum it covers and what it leaves out.
    average_note: str
    not_averaged: tuple[NotAveraged, ...] = ()


def _group_peaks(entry: TautomerNmrEntry, mol: Chem.Mol) -> dict[str, tuple[TracePeak, ...]]:
    """A tautomer's peaks grouped the way the average groups them: a 13C per carbon, and the hydrogens on each
    heavy atom as ONE stick (their mean shift, height = how many)."""
    spectrum = entry.spectrum
    carbon: list[TracePeak] = []
    hydrogen: list[TracePeak] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() <= 1:
            continue
        index = atom.GetIdx()
        if atom.GetSymbol() == _CARBON and index in spectrum.values:
            carbon.append(TracePeak(spectrum.values[index], 1.0, index))
        shifts = [spectrum.values[h] for h in _hydrogens(mol, index) if h in spectrum.values]
        if shifts and len(shifts) == len(_hydrogens(mol, index)):
            hydrogen.append(TracePeak(
                sum(shifts) / len(shifts), float(len(shifts)), index, labile=atom.GetSymbol() != _CARBON
            ))
    return {"C": tuple(carbon), "H": tuple(hydrogen)}


def tautomer_overlay(nmr: TautomerNmrResult, distribution: StructureSetResult) -> TautomerOverlay:
    """The traces for `nmr`, with populations and energies from `distribution` (the populations only when it
    is validated), and the fast-exchange average when `average_tautomer_nmr` offers one.

    A tautomer whose NMR failed still gets a trace, empty and carrying the reason, so it is listed and never
    silently absent. A tautomer whose stored structure cannot be read is treated the same way.
    """
    params = distribution.provenance.parameters if distribution.provenance else {}
    shown = params.get("validation_branch") == "validated" and bool(params.get("complete"))
    representative = {
        e.metadata.get("tautomer_fingerprint"): e
        for e in distribution.entries
        if e.metadata.get("is_lowest_calculated_for_tautomer")
    }
    traces: list[TautomerTrace] = []
    for entry in nmr.entries:
        rep = representative.get(entry.tautomer_fingerprint)
        population = rep.score if (shown and rep is not None) else None
        energy = rep.energy if rep is not None else None
        peaks: dict[str, tuple[TracePeak, ...]] = {}
        failure = entry.failure
        if entry.spectrum is not None:
            mol = _molecule_of(distribution, entry)
            if mol is None:
                failure = "the structure behind this spectrum is not stored"
            else:
                peaks = _group_peaks(entry, mol)
        traces.append(TautomerTrace(entry.tautomer_fingerprint, entry.label, False, population, energy, peaks, failure))

    average = average_tautomer_nmr(nmr, distribution)
    if not average.available:
        return TautomerOverlay(tuple(traces), None, average.reason)
    by_nucleus: dict[str, list[TracePeak]] = {"C": [], "H": []}
    for peak in average.peaks:
        by_nucleus["C" if peak.nucleus == "13C" else "H"].append(
            TracePeak(peak.shift_ppm, float(peak.hydrogen_count or 1), peak.heavy_atom)
        )
    trace = TautomerTrace(
        "average", "Fast-exchange average", True, None, None, {k: tuple(v) for k, v in by_nucleus.items()}
    )
    note = (
        f"Fast-exchange average of {len(nmr.entries)} tautomers, weighted by the validated populations: "
        f"{len(average.peaks)} peaks."
    )
    if average.not_averaged:
        note += f" {len(average.not_averaged)} left out (labile N/O/S hydrogens, and carbons whose hydrogen count changes)."
    return TautomerOverlay(tuple(traces), trace, note, average.not_averaged)
