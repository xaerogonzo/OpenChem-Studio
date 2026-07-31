"""Boltzmann-weighted averaging of per-conformer NMR spectra.

A molecule in solution is not one geometry. It interconverts between
conformers fast on the NMR timescale, so the observed shift of an atom is
the population-weighted mean of its shift in each accessible conformer --
not its shift in the single lowest-energy one. For a flexible molecule
that difference is easily larger than the basis-set improvement from
pcSseg-1, because a rotatable bond can swing a proton between shielded and
deshielded environments.

The weights come from each ORCA job's own `FINAL SINGLE POINT ENERGY`
(`orca.scf_energy`), NOT from the MMFF energies RDKit assigned when it
embedded the conformers. Two reasons, and the first is the important one:
the SCF energy is computed at the SAME level of theory as the shieldings
being averaged, so the populations and the shifts are internally
consistent. Second, it is free -- every NMR job already parses it out.

Pure functions, no Qt and no ORCA -- the sequencing of the N jobs lives in
`services/quantum_chemistry_service.py`; this module only does the
arithmetic, so it is testable without running anything.
"""

from __future__ import annotations

import dataclasses
import math

from openchem.domain.scientific_result import NMRSpectrumResult

# CODATA values. Boltzmann constant in J/K, Hartree in J.
_BOLTZMANN_J_PER_K = 1.380649e-23
_HARTREE_J = 4.3597447222071e-18

STANDARD_TEMPERATURE_K = 298.15

# Above this the exponential underflows to zero anyway, and feeding
# math.exp a large negative number is fine -- this cap exists only to keep
# a pathological energy (a failed job that still parsed, say) from
# producing inf/nan rather than a harmless zero weight.
_MAX_EXPONENT = 700.0


def boltzmann_weights(
    energies_hartree: list[float], temperature_k: float = STANDARD_TEMPERATURE_K
) -> list[float]:
    """Normalized populations for conformers at `energies_hartree`.

    Energies are taken relative to the lowest, which is what makes this
    numerically safe: absolute SCF energies are large negative numbers
    (hundreds of Hartree) whose exponential would overflow immediately.
    Only the differences matter, and they cancel in the normalization.
    """
    if not energies_hartree:
        return []
    kt_hartree = _BOLTZMANN_J_PER_K * temperature_k / _HARTREE_J
    lowest = min(energies_hartree)
    unnormalized = [
        math.exp(-min((energy - lowest) / kt_hartree, _MAX_EXPONENT)) for energy in energies_hartree
    ]
    total = sum(unnormalized)
    if total <= 0.0:
        # Every conformer underflowed to zero -- can only happen if the
        # spread is absurd. An equal split is a more honest fallback than
        # dividing by zero or silently picking the first conformer.
        return [1.0 / len(energies_hartree)] * len(energies_hartree)
    return [value / total for value in unnormalized]


def boltzmann_average_spectrum(
    spectra: list[NMRSpectrumResult],
    energies_hartree: list[float],
    temperature_k: float = STANDARD_TEMPERATURE_K,
) -> NMRSpectrumResult:
    """Population-weighted mean of per-conformer shieldings/shifts.

    Conformers of one molecule share atom ordering (they are embeddings of
    the same `Chem.Mol`), so atom index i means the same atom in every
    spectrum and the averaging is a straight per-index weighted sum. An
    atom missing from any spectrum is dropped rather than averaged over a
    subset, which would silently weight it differently from its
    neighbours.

    The result keeps the first spectrum's identity (name, units, element
    map, provenance) and records the weights in `Provenance.parameters`,
    so a reader can see how lopsided the population was -- an average over
    conformers at 0.98/0.01/0.01 is really just the lowest-energy one, and
    that is worth being able to notice.
    """
    if not spectra:
        raise ValueError("Cannot Boltzmann-average an empty list of spectra")
    if len(spectra) != len(energies_hartree):
        raise ValueError(
            f"Got {len(spectra)} spectra but {len(energies_hartree)} energies -- "
            "every conformer needs exactly one of each."
        )
    if len(spectra) == 1:
        return spectra[0]

    weights = boltzmann_weights(energies_hartree, temperature_k)
    shared_atoms = set(spectra[0].values)
    for spectrum in spectra[1:]:
        shared_atoms &= set(spectrum.values)

    averaged = {
        index: sum(weight * spectrum.values[index] for weight, spectrum in zip(weights, spectra))
        for index in sorted(shared_atoms)
    }

    base = spectra[0]
    provenance = base.provenance
    if provenance is not None:
        provenance = dataclasses.replace(
            provenance,
            parameters={
                **provenance.parameters,
                "boltzmann_conformers": len(spectra),
                "boltzmann_weights": [round(weight, 4) for weight in weights],
                "boltzmann_temperature_k": temperature_k,
            },
        )
    return dataclasses.replace(
        base,
        values=averaged,
        elements={index: base.elements[index] for index in averaged if index in base.elements},
        couplings=_average_couplings(spectra, weights),
        provenance=provenance,
    )


def _average_couplings(
    spectra: list[NMRSpectrumResult], weights: list[float]
) -> dict[tuple[int, int], float] | None:
    """J values average the same way shifts do -- a coupling constant is
    just as conformer-dependent (Karplus), often more so.

    Only pairs present in every spectrum are averaged, for the same reason
    atoms are: a pair the parser found in three of four runs would come out
    weighted as if the fourth conformer had a coupling of zero.
    """
    if any(spectrum.couplings is None for spectrum in spectra):
        return None
    shared_pairs = set(spectra[0].couplings or {})
    for spectrum in spectra[1:]:
        shared_pairs &= set(spectrum.couplings or {})
    if not shared_pairs:
        return None
    return {
        pair: sum(weight * (spectrum.couplings or {})[pair] for weight, spectrum in zip(weights, spectra))
        for pair in sorted(shared_pairs)
    }
