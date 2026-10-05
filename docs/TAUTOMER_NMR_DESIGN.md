# Tautomer peaks on the NMR spectrum (P5): design

**Status: design agreed 2026-10-04, building in stages (steps 1-4 built: the geometry is kept, the NMR run exists, the averaging is implemented in `chem/tautomer_nmr.py`, and the viewer draws it; step 5, a live ORCA check, remains).** The tautomer-distribution model is validated for one
setup (`docs/VALIDATION.md`), which is what unblocked this. Nothing here changes a model version or an
energy: it adds NMR calculations ON the tautomers the distribution already found.

## What the user sees

In the NMR viewer, for a molecule that has a tautomer-distribution result:

1. **One trace per tautomer**: that tautomer's own predicted peaks, coloured and labelled by tautomer, each
   toggleable. Always available once the NMR jobs have run. A tautomer's label carries its population only
   when the result is `validated`; otherwise it carries its relative energy and says populations are not
   validated.
2. **A population-weighted average trace**, offered ONLY for a `validated` and complete result, labelled
   "fast-exchange average, validated populations". It is what an experiment sees when the tautomers
   interconvert faster than the NMR timescale; the separate traces are what it sees when they do not. The
   viewer says which is which and does not choose for the user.

## Decisions, and why

| question | decision | why |
|---|---|---|
| which structure supplies the shifts | the **optimized geometry of each tautomer's lowest calculated conformer** (the one that already represents it in the distribution), one NMR job on it | no re-optimization, and "lowest calculated stereoisomer/conformer under the current policy" is exactly how the distribution represents a tautomer, so the NMR describes the same structure the energy does |
| conformer averaging | an **optional setting, off by default**: NMR on every optimized conformer of a tautomer, Boltzmann-weighted within the tautomer | ~3x the jobs; a refinement, not the baseline. Off keeps the default cost at one job per tautomer |
| NMR level | the method the user selects in the panel, exactly as for a single-molecule NMR, with the existing reference calibration and scaling | no second NMR pipeline to validate; the shifts are only as good as that method, and the overlay says so |
| what the weights are | the distribution's own normalized populations, at tautomer level | one weight per tautomer, already computed and validated |
| unvalidated or incomplete result | separate traces only; **no average trace** | a population that is not shown is not used to build a spectrum either |

## The averaging rule (the part that needs care)

A tautomer changes where hydrogens sit, so atoms do not correspond one-to-one across tautomers. Heavy atoms
do: the enumerator keeps every heavy atom's index. The average is therefore defined per **heavy atom**:

- **13C:** the weighted mean of that carbon's calibrated shift over all tautomers. Always defined.
- **1H on carbon:** the weighted mean over the tautomers, **only when the carbon carries the same number of
  hydrogens in every tautomer**; those hydrogens are averaged as one. A carbon whose hydrogen count changes
  (a keto CH2 against an enol CH) has no single averaged proton, so its protons appear only on the
  per-tautomer traces and are listed as not averaged.
- **Hydrogens on N, O or S:** not averaged and not drawn on the average trace. They exchange with solvent and
  with each other, so a gas-phase tautomer shift for them would mislead; they remain on the per-tautomer
  traces, marked labile.

Each excluded set is named on screen, never dropped silently.

Two consequences worth stating. The hydrogens on one carbon become ONE peak per tautomer (their mean), so a
carbon's diastereotopic hydrogens, which a real spectrum can resolve, are merged. And the average exists only
when every ingredient does: a validated and complete distribution, a complete NMR result computed from that same
distribution run, referenced shifts, and tautomers whose heavy atoms correspond. Otherwise `average_tautomer_nmr`
returns no average and the reason; it never returns a partial one.

## What it does not claim

Gas-phase shifts at one geometry per tautomer, from the user's NMR method, are not a solution spectrum: no
solvent, no vibrational averaging, no conformational averaging unless the option is on. The populations are
validated for a narrow benchmark (see `docs/VALIDATION.md`), not for every molecule. A fast-exchange average
is a model of a limit, not a measurement.

## Build order (each a separate, reviewable change)

1. **Keep the geometry.** The service reads each candidate's optimized geometry from ORCA's output and
   discards it; keep it on the candidate result and in the result entry, so NMR can run later from a stored
   result without recomputing anything.
2. **The calculation.** A sequential NMR run over the tautomers (and, with the option on, their conformers)
   using the existing single-job path per structure, one operation token, the usual cancellation and
   stale-callback guards, one retained result; a failed tautomer is reported and makes the average
   unavailable, never a partial average.
3. **The pure combination.** Per-heavy-atom weighted averaging with the exclusions above, tested without ORCA.
4. **The viewer.** Per-tautomer traces, the toggles, the average trace, the labels and the not-averaged list.
5. **Live check** with real ORCA on a small two-state system, and a magnified screenshot.
