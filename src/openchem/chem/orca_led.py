"""ORCA's Local Energy Decomposition, parsed from what it actually prints.

Everything here was written against a real ORCA 6.1.1 run of BH3-CO
(`! DLPNO-CCSD(T) cc-pVDZ cc-pVDZ/C cc-pVTZ/JK TightPNO LED`, 15 seconds,
6 atoms, exit 0). That matters more than usual, because the design this
replaced assumed a term list ORCA does not print and a meaning for the
terms it does print that is not their meaning.

**THE `FINAL SUMMARY` BLOCK IS NOT AN INTERACTION DECOMPOSITION.** Its
correlation lines decompose the complex's TOTAL correlation energy into
dispersive and non-dispersive parts -- intra-fragment correlation included.
Verified by arithmetic against the same output, to the last digit:

    Non dispersion (strong pairs)  = intra strong pairs
                                   + (inter strong pairs - dispersion strong)
                                   + singles
    -0.414932699                   = -0.394372938 - 0.020556328 - 0.000003433

So reporting "Non dispersion (strong pairs)" as an interaction term gives
-260 kcal/mol where the real non-dispersive interaction is -12.9. Only the
REF lines are what they look like: `Electrostatics (REF.) + Exchange (REF.)`
does equal the inter-fragment reference interaction exactly.

**AND `Total interaction` IS NOT A BINDING ENERGY.** ORCA reports
-428.2 kcal/mol for BH3-CO, whose bond enthalpy is about -25. A single-point
LED partitions the complex's own energy; the inter-fragment part carries all
the nuclear-electron attraction between the fragments. A binding energy needs
the ISOLATED fragments as well, which is why `build_led_input` writes three
jobs and not one.

With those, the decomposition reconciles against the supermolecular energy:

    Electronic preparation (REF)   +380.18 kcal/mol
    Electrostatics                 -333.90
    Exchange                        -69.73
    Correlation preparation         +11.45
    Dispersion                      -11.68
    Charge transfer / non-disp      -12.90
    -------------------------------------
    sum                             -36.58
    E(complex) - E(A) - E(B)        -36.62      residual 0.05

The 0.05 kcal/mol residual is not slop: it is exactly the gap between the
LED's own total (-139.588478996) and `FINAL SINGLE POINT ENERGY`
(-139.588557162), i.e. how DLPNO splits the (T) correction between fragments.
`residual_kcal` carries it so a reader can see the decomposition is complete
to that much rather than having to trust it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from openchem.domain.lewis import AdductEvidence
from openchem.domain.structure_issue import Basis

#: ORCA prints energies in hartree. CODATA 2018.
HARTREE_KCAL = 627.5094740631

#: Written on the keyword line. `cc-pVTZ/JK` is the RIJK auxiliary basis and
#: `cc-pVDZ/C` the correlation-fitting one -- DLPNO-CCSD(T) needs both, and
#: omitting either makes ORCA stop rather than silently do something else.
LED_KEYWORDS = "DLPNO-CCSD(T) cc-pVDZ cc-pVDZ/C cc-pVTZ/JK TightPNO LED"

# --- what the real output looks like ------------------------------------
#
#     FINAL SUMMARY DLPNO-CCSD ENERGY DECOMPOSITION (Eh)
#     -------------------------------------------------
#
#     Intrafragment REF. energy:
#     Intra fragment   1 (REF.)              -26.128991519
#     Intra fragment   2 (REF.)              -112.372466811
#
#     Interaction of fragments  2 and  1:
#     Electrostatics (REF.)                  -0.532102458
#     Exchange (REF.)                        -0.111125405
#     ...
#
# Note the header is "DLPNO-CCSD", not CCSD(T), even for a CCSD(T) job.
_SUMMARY_HEADER = "FINAL SUMMARY DLPNO-CCSD ENERGY DECOMPOSITION"
_INTRA_REF_RE = re.compile(r"Intra fragment\s+(\d+)\s+\(REF\.\)\s+(-?\d+\.\d+)")
_ELECTROSTATICS_RE = re.compile(r"Electrostatics \(REF\.\)\s+(-?\d+\.\d+)")
_EXCHANGE_RE = re.compile(r"Exchange \(REF\.\)\s+(-?\d+\.\d+)")
_DISP_STRONG_RE = re.compile(r"Dispersion \(strong pairs\)\s+(-?\d+\.\d+)")
_DISP_WEAK_RE = re.compile(r"Dispersion \(weak pairs\)\s+(-?\d+\.\d+)")

# From the INTER- vs INTRA-FRAGMENT CORRELATION ENERGIES table. These ARE
# interaction terms, unlike the summary block's.
_INTER_STRONG_RE = re.compile(r"Inter strong pairs\s+(-?\d+\.\d+)")
_INTER_TRIPLES_RE = re.compile(r"Inter triples\s+(-?\d+\.\d+)")
_INTER_WEAK_RE = re.compile(r"Inter weak pairs\s+(-?\d+\.\d+)")

#: Per-fragment intra-fragment correlation, from the `INTER- vs
#: INTRA-FRAGMENT TOTAL ENERGIES` table. Two columns, one per fragment.
#: Read from the labelled row rather than from the anonymous
#: `... ... sum=` line below it, which matches several tables in this
#: output and would pick whichever came first.
_FRAGMENT_CORR_RE = re.compile(
    r"Intra Correlation energy\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)"
)

_FINAL_SP_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
_REF_ENERGY_RE = re.compile(r"E\(0\)\s+\.\.\.\s+(-?\d+\.\d+)")
_FINAL_CORR_RE = re.compile(r"Final correlation energy\s+\.\.\.\s+(-?\d+\.\d+)")

#: Beyond this magnitude the "interaction energy" is not one. A dative bond
#: like ammonia borane's is around -50 kcal/mol and the strongest single
#: covalent bonds reach roughly -200, so this refuses to call anything an
#: interaction that no chemistry could produce.
_IMPLAUSIBLE_KCAL = 300.0

#: ORCA prints this when the orbital localisation hits its iteration cap.
#: It appeared TWICE in the reference BH3-CO run and the job still finished
#: with a plausible answer, which is exactly why it must be surfaced -- a
#: warning that changes nothing visible is one nobody would otherwise see.
_LOCALIZATION_WARNING = "LOCALIZATION NOT CONVERGED"


@dataclass(frozen=True)
class LedTerm:
    """One line of the decomposition."""

    label: str
    hartree: float
    #: What this term is, in a sentence. Carried per term rather than in one
    #: block of prose because the terms are shown in a table and the reader
    #: needs it at the row, not in a footnote.
    meaning: str = ""

    @property
    def kcal(self) -> float:
        return self.hartree * HARTREE_KCAL


@dataclass(frozen=True)
class LedDecomposition:
    """A complete interaction-energy decomposition, or an explained refusal.

    `terms` sum to `interaction_hartree` up to `residual_hartree`. Both are
    reported: a decomposition whose parts do not add up to the whole is
    worth knowing about, and hiding a residual is how that goes unnoticed.
    """

    terms: tuple[LedTerm, ...] = ()
    interaction_hartree: float = 0.0
    residual_hartree: float = 0.0
    fragment_energies: tuple[float, ...] = ()
    complex_energy: float = 0.0
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    error: str = ""

    def __bool__(self) -> bool:
        return not self.error and bool(self.terms)

    @property
    def interaction_kcal(self) -> float:
        return self.interaction_hartree * HARTREE_KCAL

    @property
    def residual_kcal(self) -> float:
        return self.residual_hartree * HARTREE_KCAL


def build_led_input(
    coordinates: list[tuple[str, float, float, float]],
    fragments: list[int],
    charge: int = 0,
    multiplicity: int = 1,
    method_basis: str = LED_KEYWORDS,
    maxcore_mb: int = 2000,
) -> str:
    """Complex plus each isolated fragment, in ONE compound input.

    Three jobs rather than one because a single-point LED cannot produce a
    binding energy -- see the module docstring. `$new_job` is the same
    mechanism `_build_delta_scf_input` already uses and is confirmed live,
    so this needs no notion of chained runs in the service.

    **The fragments keep the geometry they have in the complex.** No
    relaxation, so the result is the vertical interaction energy and the
    preparation terms mean what they say. Optimising a fragment here would
    fold its relaxation energy into the decomposition invisibly.

    `fragments` is one 1-based fragment id per atom, parallel to
    `coordinates`. ORCA's own notation -- `B(1)`, `C(2)` -- is what the
    labels become.
    """
    if len(fragments) != len(coordinates):
        raise ValueError(
            f"{len(fragments)} fragment labels for {len(coordinates)} atoms"
        )
    distinct = sorted(set(fragments))
    if len(distinct) != 2:
        raise ValueError(
            "LED needs exactly two fragments; "
            f"got {len(distinct)} ({distinct}). ORCA supports more, but an "
            "interaction energy is between two things."
        )

    def block(header: str, rows: list[str], job_charge: int, job_multiplicity: int) -> list[str]:
        return [header, "", f"%maxcore {maxcore_mb}", "", f"* xyz {job_charge} {job_multiplicity}", *rows, "*"]

    labelled = [
        f"{symbol}({fragment}){'':<2}{x:>14.6f}{y:>14.6f}{z:>14.6f}"
        for (symbol, x, y, z), fragment in zip(coordinates, fragments)
    ]
    lines = block(f"! {method_basis}", labelled, charge, multiplicity)

    # The fragment jobs drop the LED keyword -- there is nothing to
    # decompose in a single molecule -- and add `PModel`.
    #
    # **`PModel` is what makes the compound job run at all**, and it is the
    # one thing `_build_delta_scf_input`'s otherwise-identical pattern does
    # not need. Inside `$new_job`, ORCA reads the previous job's orbitals as
    # its initial guess (`INITIAL GUESS: MOREAD`). delta-SCF's three blocks
    # are the same geometry with different charges, so that guess is valid
    # and helpful. A fragment has FEWER ATOMS, so ORCA stops:
    #
    #     [orca_guess/guess_restart.cpp, line 292]: Error: Input geometry
    #     does not match current geometry
    #     ORCA finished by error termination in GUESS
    #
    # Measured: exit code 55 with one energy printed instead of three.
    # `NOAUTOSTART` looks like the fix and is NOT -- it stops ORCA picking
    # up a .gbw left on disk from a previous run, not the restart from the
    # job before it in the same input, so the run failed identically with it
    # in place. `PModel` names the guess outright and overrides the restart;
    # confirmed against a two-job HF/STO-3G input, which returned both
    # energies and reported `INITIAL GUESS: MODEL POTENTIAL`.
    fragment_header = f"! {method_basis.replace(' LED', '')} PModel"
    for fragment_id in distinct:
        rows = [
            f"{symbol:<3}{x:>14.6f}{y:>14.6f}{z:>14.6f}"
            for (symbol, x, y, z), fragment in zip(coordinates, fragments)
            if fragment == fragment_id
        ]
        lines.extend(["", "$new_job"])
        # Neutral closed-shell fragments are assumed. A charged complex
        # split into charged fragments needs the user to say how the charge
        # divides, and guessing it would change the answer silently.
        lines.extend(block(fragment_header, rows, 0, 1))
    return "\n".join(lines) + "\n"


def parse_led(output_text: str) -> LedDecomposition:
    """Decompose the interaction energy from a compound LED output.

    Expects the three jobs `build_led_input` writes, in that order. The
    order is positional and load-bearing -- the same reason
    `test_the_three_delta_scf_blocks_are_written_in_parser_order` exists.
    """
    warnings: list[str] = []
    if _LOCALIZATION_WARNING in output_text:
        warnings.append(
            "ORCA reported that the orbital localisation did not converge. "
            "The job still produced numbers; treat them as indicative rather "
            "than converged, and re-run with a tighter localisation if the "
            "decomposition matters."
        )

    if _SUMMARY_HEADER not in output_text:
        return LedDecomposition(
            error=(
                "No LED decomposition in this output. Either the job failed "
                "before the analysis, or the LED keyword was missing."
            ),
            warnings=tuple(warnings),
        )

    # One chunk per job, each ending at its own final energy. Splitting
    # first means the count check and the per-job reads below use the same
    # notion of "a job" -- an earlier version counted `FINAL SINGLE POINT
    # ENERGY` separately here and then split again lower down, which is the
    # same test written twice and left one copy unreachable.
    jobs = _split_jobs(output_text)
    if len(jobs) < 3:
        return LedDecomposition(
            error=(
                f"Expected three jobs (the complex and two isolated fragments); "
                f"found {len(jobs)}. Without the fragments there is no "
                "interaction energy to decompose -- the LED block on its own "
                "partitions the complex's total energy, which for BH3-CO reads "
                "-428 kcal/mol against a bond enthalpy near -25."
            ),
            warnings=tuple(warnings),
        )
    total_energies = [float(value) for value in _FINAL_SP_RE.findall(output_text)]
    complex_energy, *fragment_energies = total_energies[:3]

    intra_reference = [float(v) for _, v in _INTRA_REF_RE.findall(output_text)]
    fragment_correlation_match = _FRAGMENT_CORR_RE.search(output_text)
    if len(intra_reference) < 2 or fragment_correlation_match is None:
        return LedDecomposition(
            error="The LED block is present but its per-fragment energies could not be read.",
            warnings=tuple(warnings),
        )
    intra_correlation = [float(v) for v in fragment_correlation_match.groups()]

    # Split into jobs FIRST, then read one energy per job.
    #
    # Taking `reference_energies[-2:]` off the whole text looks equivalent
    # and is not: DLPNO prints `E(0)` more than once per job (twice in the
    # reference run), so the last two both came from the LAST fragment and
    # the first fragment's reference energy was never read. Measured: an
    # electronic-preparation term of +86.99 Eh, against a true +0.61.
    jobs = _split_jobs(output_text)
    if len(jobs) < 3:
        return LedDecomposition(
            error=(
                f"Expected three jobs in this output; found {len(jobs)}. "
                "The fragment calculations did not run."
            ),
            warnings=tuple(warnings),
        )
    isolated_reference = [_last(_REF_ENERGY_RE, job) for job in jobs[1:3]]
    isolated_correlation = [_last(_FINAL_CORR_RE, job) for job in jobs[1:3]]
    if None in isolated_reference or None in isolated_correlation:
        return LedDecomposition(
            error="Could not read the isolated fragments' reference and correlation energies.",
            warnings=tuple(warnings),
        )

    electrostatics = _first(_ELECTROSTATICS_RE, output_text)
    exchange = _first(_EXCHANGE_RE, output_text)
    dispersion_strong = _first(_DISP_STRONG_RE, output_text)
    dispersion_weak = _first(_DISP_WEAK_RE, output_text)
    inter_strong = _first(_INTER_STRONG_RE, output_text)
    inter_triples = _first(_INTER_TRIPLES_RE, output_text)
    inter_weak = _first(_INTER_WEAK_RE, output_text)
    if None in (electrostatics, exchange, dispersion_strong, inter_strong):
        return LedDecomposition(
            error="The LED block is present but incomplete; its interaction terms are missing.",
            warnings=tuple(warnings),
        )

    dispersion_weak = dispersion_weak or 0.0
    inter_triples = inter_triples or 0.0
    inter_weak = inter_weak or 0.0

    electronic_preparation = sum(
        intra - isolated for intra, isolated in zip(intra_reference, isolated_reference)
    )
    correlation_preparation = sum(
        intra - isolated
        for intra, isolated in zip(intra_correlation, isolated_correlation)
    )
    # Dispersion as ORCA defines it: the genuinely dispersive part of the
    # inter-fragment correlation. The triples go here because they are an
    # inter-fragment correlation contribution with no separate dispersive /
    # non-dispersive split in the output.
    dispersion = dispersion_strong + dispersion_weak + inter_triples
    charge_transfer = (inter_strong - dispersion_strong) + (inter_weak - dispersion_weak)

    terms = (
        LedTerm(
            "Electronic preparation",
            electronic_preparation,
            "Cost of distorting each fragment's electron density from its "
            "isolated form into the one it has in the complex. Always "
            "unfavourable.",
        ),
        LedTerm(
            "Electrostatics",
            electrostatics,
            "Classical attraction between the fragments' unperturbed charge "
            "distributions.",
        ),
        LedTerm(
            "Exchange",
            exchange,
            "The quantum-mechanical exchange contribution at the reference level.",
        ),
        LedTerm(
            "Correlation preparation",
            correlation_preparation,
            "Change in each fragment's own correlation energy on forming the complex.",
        ),
        LedTerm(
            "Dispersion",
            dispersion,
            "London dispersion between the fragments, including the "
            "inter-fragment triples correction.",
        ),
        LedTerm(
            "Charge transfer and non-dispersive correlation",
            charge_transfer,
            "The rest of the inter-fragment correlation -- charge transfer and "
            "polarisation. Not separable from each other here.",
        ),
    )

    interaction = complex_energy - sum(fragment_energies)
    residual = sum(term.hartree for term in terms) - interaction

    limitations = [
        # ORCA's own words, from the manual section on LED.
        "Only the total energy is an observable; its decomposition is, to "
        "some extent, arbitrary.",
        "No counterpoise correction is applied, so basis-set superposition "
        "error inflates the interaction energy. For BH3-CO in cc-pVDZ the "
        "measured value was -36.6 kcal/mol against an experimental bond "
        "enthalpy near -25.",
        "The fragments are held at their geometry in the complex, so this is "
        "a vertical interaction energy and not a bond dissociation energy.",
    ]
    if abs(residual * HARTREE_KCAL) > 0.5:
        limitations.append(
            f"The terms do not add up to the interaction energy: they differ "
            f"by {residual * HARTREE_KCAL:.2f} kcal/mol. Treat the "
            "decomposition as unreliable."
        )
    if abs(interaction * HARTREE_KCAL) > _IMPLAUSIBLE_KCAL:
        # The backstop for the geometry check in `estimate_led_cost_for`.
        # That one runs before the job and catches the common cause;
        # this one catches whatever else produced a number no chemical
        # interaction can reach. Measured live: overlapping fragments gave
        # +40619 kcal/mol, reported as a plain number with nothing to say
        # it could not be real.
        limitations.append(
            f"An interaction energy of {interaction * HARTREE_KCAL:,.0f} kcal/mol "
            "is not physically possible -- the strongest single bonds are near "
            "-200. The input geometry is almost certainly wrong; the usual cause "
            "is two fragments overlapping. Do not use these numbers."
        )

    return LedDecomposition(
        terms=terms,
        interaction_hartree=interaction,
        residual_hartree=residual,
        fragment_energies=tuple(fragment_energies),
        complex_energy=complex_energy,
        warnings=tuple(warnings),
        limitations=tuple(limitations),
    )


@dataclass(frozen=True)
class LedCostEstimate:
    """What a job will cost, before it is launched.

    Scratch disk is here because it is the one that fails silently and
    badly: the service already gives every job a `tempfile.mkdtemp`, and a
    full drive mid-run loses hours of compute with an error that names the
    disk rather than the job that filled it.
    """

    atoms: int
    basis_functions: int
    minutes: float
    scratch_mb: float
    memory_mb: int
    advice: str = ""
    should_warn: bool = False
    #: How many disconnected species the structure has. LED needs exactly
    #: two, and reporting the count here keeps the UI from having to import
    #: RDKit to find out -- `tests/test_layering.py` forbids that, and
    #: caught it.
    fragment_count: int = 2
    #: Closest approach between the two fragments, in angstroms. 0.0 when
    #: there are not two fragments to measure between.
    closest_contact: float = 0.0
    #: Why the geometry cannot give a meaningful answer, or "".
    geometry_problem: str = ""
    fields: dict = field(default_factory=dict)

    @property
    def runnable(self) -> bool:
        return self.fragment_count == 2 and not self.geometry_problem


#: Basis functions per element in the basis this job actually uses, taken
#: from ORCA's own "Number of basis functions" line rather than from the
#: textbook cc-pVDZ contraction.
#:
#: The textbook numbers are 14 for a first-row atom and 5 for hydrogen, and
#: they are WRONG for this job -- they predict 57 functions for BH3-CO where
#: ORCA reports 75. Solving the two measured totals
#: (3 heavy + 3 H = 75, 7 heavy + 8 H = 180) gives 20 and 5, and that was
#: then confirmed against a third job the numbers were not fitted to: BH3
#: alone, predicted 20 + 3x5 = 35, reported 35.
_BASIS_FUNCTIONS = {
    "H": 5, "He": 5,
    "Li": 20, "Be": 20, "B": 20, "C": 20, "N": 20, "O": 20, "F": 20, "Ne": 20,
    # Second row is INFERRED, not measured -- scaled by the textbook
    # first-row:second-row ratio (14:18). Flagged because everything else
    # here was checked against a run and this was not.
    "Na": 26, "Mg": 26, "Al": 26, "Si": 26, "P": 26, "S": 26, "Cl": 26, "Ar": 26,
}
_DEFAULT_FUNCTIONS = 20

# Two jobs measured on this machine with the same sampling harness, disk
# polled while the job RAN:
#
#   system          atoms   basis functions   wall     peak scratch
#   BH3-CO            6            75           15 s        102 MB
#   benzene...H2O    15           180          595 s       1899 MB
#
# **Peak, not residual, and the difference is not small.** benzene-water
# leaves 3.3 MB behind after ORCA cleans up, having used 1899 MB while
# running -- a factor of 575. An estimate anchored on what is left on disk
# afterwards (as the first version of this was) under-predicts the thing
# that actually fills a drive by nearly three orders of magnitude.
#
# The exponents below are what those two points give: DLPNO-CCSD(T) is
# asymptotically linear-scaling and these systems are nowhere near that
# regime. Two points determine a power law exactly and cannot validate it,
# so this is a guide for choosing between "minutes", "hours" and "do not
# start it", not a prediction. It errs high, which is the safe direction.
_ANCHOR_FUNCTIONS = 75
_ANCHOR_MINUTES = 15.0 / 60
_ANCHOR_SCRATCH_MB = 102.0
_TIME_EXPONENT = 4.20
_SCRATCH_EXPONENT = 3.34


def estimate_led_cost(symbols: list[str]) -> LedCostEstimate:
    """Runtime, memory and scratch for a DLPNO-CCSD(T) LED job.

    Scaled from two measured jobs, so this is a guide to the ORDER of the
    cost, not a prediction. It exists to stop someone starting a week-long
    run by accident, which it can do while being a factor of three out.

    Takes only the element symbols: the cost depends on how many basis
    functions there are, not on how they are split into fragments.
    """
    atoms = len(symbols)
    functions = sum(_BASIS_FUNCTIONS.get(symbol, _DEFAULT_FUNCTIONS) for symbol in symbols)
    ratio = functions / _ANCHOR_FUNCTIONS if _ANCHOR_FUNCTIONS else 1.0

    minutes = _ANCHOR_MINUTES * ratio**_TIME_EXPONENT
    # The whole input is three jobs. Measured on BH3-CO: 15 s for the
    # complex alone against 23 s for the compound input, so the two
    # fragments together cost about half the complex again.
    minutes *= 1.5
    # Scratch is NOT multiplied by three. The jobs run one after another
    # and ORCA clears up between them, so the peak is the biggest single
    # job -- the complex.
    scratch_mb = _ANCHOR_SCRATCH_MB * ratio**_SCRATCH_EXPONENT
    memory_mb = max(2000, int(functions * 30))

    if minutes > 720:
        advice = (
            f"This job is estimated at {minutes / 60:.0f} hours and about "
            f"{_disk(scratch_mb)} of scratch disk. That is not a "
            "reasonable interactive calculation -- DLPNO-CCSD(T) is for "
            "small complexes, and this molecule is too large for it."
        )
        should_warn = True
    elif minutes > 30:
        advice = (
            f"Estimated {minutes / 60:.1f} hours and about "
            f"{_disk(scratch_mb)} of scratch disk. Worth starting only if "
            "you can leave it running."
        )
        should_warn = True
    elif scratch_mb > 1024:
        # A job that finishes in twenty minutes can still fill a laptop's
        # remaining disk. Time and scratch are separate reasons to warn,
        # and benzene-water is the measured case that is short but heavy:
        # 10 minutes, 1.9 GB.
        advice = (
            f"Estimated {_runtime(minutes)}, but about "
            f"{_disk(scratch_mb)} of scratch disk. Check there is "
            "room before starting."
        )
        should_warn = True
    else:
        advice = (
            f"Estimated {_runtime(minutes)} and about {_disk(scratch_mb)} "
            "of scratch disk."
        )
        should_warn = False

    return LedCostEstimate(
        atoms=atoms,
        basis_functions=functions,
        minutes=minutes,
        scratch_mb=scratch_mb,
        memory_mb=memory_mb,
        advice=advice,
        should_warn=should_warn,
        fields={
            "anchors": (
                "BH3-CO 6 atoms/75 functions: 15 s, 102 MB peak; "
                "benzene-water 15 atoms/180 functions: 595 s, 1899 MB peak"
            ),
            "time_exponent": _TIME_EXPONENT,
            "scratch_exponent": _SCRATCH_EXPONENT,
        },
    )


def led_evidence(decomposition: LedDecomposition) -> list[AdductEvidence]:
    """The decomposition, as evidence lines for an existing `LewisAdduct`.

    No shape change was needed, and that is not luck: `AdductEvidence` was
    built as an unranked list with no combined score precisely so terms
    like these could join it later. Its own docstring says so -- "would
    also make it impossible to add electrostatic, dispersion, Pauli and
    charge-transfer terms later without changing what the number means".

    `Basis.DETERMINISTIC` for every line. These are computed energies, not
    a threshold somebody chose -- which is a statement about the
    ARITHMETIC, not a claim that the partitioning is unique. That the
    partitioning is arbitrary is carried in the limitations, in ORCA's own
    words, where it belongs.
    """
    if not decomposition:
        return [
            AdductEvidence(
                line="led",
                label="Energy decomposition (LED)",
                basis=Basis.DETERMINISTIC,
                value=None,
                units="kcal/mol",
                note=decomposition.error or "not computed",
            )
        ]

    lines = [
        AdductEvidence(
            line="led_total",
            label="Interaction energy (DLPNO-CCSD(T))",
            basis=Basis.DETERMINISTIC,
            value=decomposition.interaction_kcal,
            units="kcal/mol",
            note="Vertical, no counterpoise correction.",
        )
    ]
    lines.extend(
        AdductEvidence(
            line=f"led_{term.label.split()[0].lower()}",
            label=term.label,
            basis=Basis.DETERMINISTIC,
            value=term.kcal,
            units="kcal/mol",
            note=term.meaning,
        )
        for term in decomposition.terms
    )
    return lines


#: Below this separation the two fragments are not two species in contact,
#: they are overlapping. Shorter than any real bond -- H-H is 0.74 A and
#: the B-N dative bond of ammonia borane is 1.66 -- so nothing legitimate
#: trips it.
_OVERLAP_ANGSTROM = 0.7

#: Past this there is nothing to decompose. Van der Waals contact is 3-4 A.
_TOO_FAR_ANGSTROM = 8.0


def estimate_led_cost_for(mol) -> LedCostEstimate:
    """`estimate_led_cost` for an RDKit molecule, plus what is wrong with it.

    Exists so the UI can decide whether to run an LED job without importing
    RDKit -- `tests/test_layering.py` forbids that, and caught it when the
    panel's confirmation dialog did exactly that to count fragments.

    **The geometry check is here because a live run needed it.** RDKit's
    `EmbedMolecule` does not separate disconnected fragments -- there are no
    constraints between them, so it packs them at the origin. Measured on an
    ammonia/borane pair built exactly as a user would: the N and the B came
    out **0.15 A apart**, interpenetrating. ORCA ran it happily and the app
    reported an interaction energy of **+40619 kcal/mol** as a plain number.
    The arithmetic was right and the answer was meaningless, which is the
    worst combination and the one this catches.
    """
    from rdkit import Chem

    estimate = estimate_led_cost([atom.GetSymbol() for atom in mol.GetAtoms()])
    pieces = Chem.GetMolFrags(mol)
    contact, problem = _geometry_problem(mol, pieces)
    return replace(
        estimate,
        fragment_count=len(pieces),
        closest_contact=contact,
        geometry_problem=problem,
    )


def _geometry_problem(mol, pieces) -> tuple[float, str]:
    """Closest inter-fragment approach, and why it is unusable.

    Returns (0.0, "") when there is nothing to measure -- no conformer, or
    not exactly two fragments. A missing conformer is not a geometry
    PROBLEM: the panel refuses that earlier, with its own message.
    """
    if len(pieces) != 2 or mol.GetNumConformers() == 0:
        return 0.0, ""

    conformer = mol.GetConformer()
    positions = [conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
    closest = min(
        positions[i].Distance(positions[j]) for i in pieces[0] for j in pieces[1]
    )

    if closest < _OVERLAP_ANGSTROM:
        return closest, (
            f"The two partners overlap -- their closest atoms are {closest:.2f} A "
            "apart, shorter than any real bond. Generating 3D coordinates for a "
            "structure drawn as two separate species does NOT push them apart, "
            "so they end up stacked at the origin. Place them in contact "
            "yourself, or optimise the pair first."
        )
    if closest > _TOO_FAR_ANGSTROM:
        return closest, (
            f"The two partners are {closest:.1f} A apart at their closest, which "
            "is too far to interact. There would be nothing to decompose."
        )
    return closest, ""


def _runtime(minutes: float) -> str:
    """"0 minutes" reads as "instant" and then the job takes 40 seconds."""
    if minutes < 1:
        return "under a minute"
    return f"{minutes:.0f} minutes"


def _disk(megabytes: float) -> str:
    """MB below a gigabyte, GB above. "32225 MB" is a number nobody reads."""
    if megabytes >= 1024:
        return f"{megabytes / 1024:.1f} GB"
    return f"{megabytes:.0f} MB"


def _first(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    return float(match.group(1)) if match else None


def _last(pattern: re.Pattern[str], text: str) -> float | None:
    found = pattern.findall(text)
    return float(found[-1]) if found else None


def _split_jobs(output_text: str) -> list[str]:
    """One chunk per job, each ending at its `FINAL SINGLE POINT ENERGY`.

    Cut at the final energy rather than at ORCA's `$new_job` banner because
    the banner's exact wording is a formatting detail that drifts between
    versions, while the energy line is the one string this whole file
    already depends on and which is verified against a real run.
    """
    chunks: list[str] = []
    start = 0
    for match in _FINAL_SP_RE.finditer(output_text):
        chunks.append(output_text[start : match.end()])
        start = match.end()
    return chunks
