"""Conceptual-DFT descriptors: hardness, softness, electrophilicity.

The quantities Pearson's HSAB principle is stated in, from the two
energies every quantum job already produces. Pure arithmetic, no ORCA --
the engine hands in numbers and this turns them into descriptors, so all
of it is testable without a quantum chemistry package installed.

**Koopmans and delta-SCF are not interchangeable, and the difference is
not academic.** Measured on real ORCA 6.1.1 B3LYP/def2-SVP runs of the
two textbook hard/soft pairs:

| eta (eV)          | Koopmans | delta-SCF | experiment |
| ----------------- | -------- | --------- | ---------- |
| water             | 4.57     | 8.06      | ~9.5       |
| hydrogen sulfide  | 3.90     | 6.93      | ~6.2       |
| ammonia           | 4.16     | 7.21      | ~8.2       |
| phosphine         | 4.27     | 7.02      | ~6.0       |

Koopmans gets water/hydrogen sulfide right and **INVERTS ammonia and
phosphine** -- it makes phosphine the harder of the two, when the
hard-nitrogen/soft-phosphorus pair is one of the most-used orderings in
all of coordination chemistry. Delta-SCF gets both pairs right and lands
its ionization potentials within a few tenths of an eV.

The cause is the electron affinity. Every molecule above has a NEGATIVE
electron affinity, so its "LUMO" is an unbound state whose energy is a
property of the basis set rather than of the molecule. Koopmans reads
that number directly; delta-SCF at least makes an error of similar size
in every molecule, which is why the ORDERING survives even though the
anion is no better described.

So `KOOPMANS` is offered because it is free from a job that has already
run, and it carries this warning wherever it is reported.

The experimental column is READ FROM THE PRIMARY SOURCE, not quoted from
memory: Pearson, Inorg. Chem. 1988, 27, 734 (doi:10.1021/ic00277a030,
[source:pearson1988]),
Table II, "Experimental Parameters for Molecules (eV)". Those values are
asserted in `test_conceptual_dft.py`, so the accuracy claims below are
checked rather than described.

Against that table, delta-SCF is good where it matters and honest about
where it is not:

    ionization potential   within 0.5 eV of experiment on all four
    hardness               mean error 1.05 eV, orderings preserved
    electron affinity      off by roughly 2 eV, always too positive

The electron affinity is the weak half and the caveat says so. Pearson
gives A(water) = -6.4 eV and A(ammonia) = -5.6 eV; delta-SCF/def2-SVP
returns about -3.8 for both, because a basis with no diffuse functions
cannot describe an unbound anion. The error is similar in every molecule,
which is why hardness ORDERINGS survive despite it -- and Koopmans, which
reads an orbital energy straight out, does not get that cancellation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: ORCA reports orbital energies in eV alongside Hartree, and every
#: descriptor here is conventionally quoted in eV, so eV is the unit
#: throughout and no conversion happens in this module.
HARTREE_TO_EV = 27.211386245988


class DescriptorMethod(str, Enum):
    """How I and A were obtained. Reported, never inferred by a reader."""

    KOOPMANS = "koopmans"
    DELTA_SCF = "delta_scf"


_KOOPMANS_CAVEAT = (
    "From Koopmans' theorem: I = -E(HOMO), A = -E(LUMO). Measured against "
    "real B3LYP/def2-SVP runs, this INVERTS the hardness of ammonia and "
    "phosphine -- it makes phosphine harder, when nitrogen is the hard "
    "donor and phosphorus the soft one. Use a delta-SCF run before "
    "reasoning about hard/soft matching."
)

_DELTA_SCF_CAVEAT = (
    "Vertical I and A from separate cation and anion energies at the "
    "neutral geometry. Reproduces both textbook hard/soft pairs. The "
    "electron affinity is still the weak half: without diffuse functions "
    "an anion of a negative-affinity molecule is an unbound state, so A "
    "is basis-set dependent and eta inherits that."
)


@dataclass(frozen=True)
class ConceptualDFT:
    """Global reactivity descriptors, in eV (softness in 1/eV).

    `refused` rather than partial numbers, following `OxidationStates` and
    `LewisAnalysis`: a non-positive hardness makes softness and
    electrophilicity meaningless rather than merely imprecise, and 1/eta
    would either divide by zero or return a confident negative.
    """

    method: DescriptorMethod
    ionization_potential: float = 0.0
    electron_affinity: float = 0.0
    electronegativity: float = 0.0
    chemical_potential: float = 0.0
    hardness: float = 0.0
    softness: float = 0.0
    electrophilicity: float = 0.0
    refused: bool = False
    reason: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return not self.refused


def _refuse(method: DescriptorMethod, reason: str) -> ConceptualDFT:
    return ConceptualDFT(method=method, refused=True, reason=reason)


def descriptors(
    ionization_potential: float,
    electron_affinity: float,
    method: DescriptorMethod,
    caveat: str = "",
) -> ConceptualDFT:
    """The standard set, from I and A however they were obtained.

        chi = (I + A) / 2      mu = -chi
        eta = (I - A) / 2      S = 1 / eta
        omega = mu^2 / (2 eta)

    `S = 1/eta` is the convention this project uses because the local
    softness in Yang and Parr's `s = S * f` [source:parr_pearson1983] is
    defined against it. Some
    literature uses `1/(2 eta)`; a number quoted from elsewhere may differ
    by exactly a factor of two for that reason and not be wrong.
    """
    hardness = (ionization_potential - electron_affinity) / 2.0
    if hardness <= 0.0:
        return _refuse(
            method,
            "Hardness came out non-positive, which means the electron affinity is "
            f"at or above the ionization potential ({electron_affinity:.3f} eV vs "
            f"{ionization_potential:.3f} eV). Softness and electrophilicity are "
            "1/eta and mu^2/2eta, so both would be meaningless rather than merely "
            "imprecise. This usually means the calculation did not converge to the "
            "state you intended.",
        )
    electronegativity = (ionization_potential + electron_affinity) / 2.0
    chemical_potential = -electronegativity
    return ConceptualDFT(
        method=method,
        ionization_potential=ionization_potential,
        electron_affinity=electron_affinity,
        electronegativity=electronegativity,
        chemical_potential=chemical_potential,
        hardness=hardness,
        softness=1.0 / hardness,
        electrophilicity=chemical_potential**2 / (2.0 * hardness),
        caveats=(caveat,) if caveat else (),
    )


def from_frontier_energies(
    homo_ev: float | None, lumo_ev: float | None
) -> ConceptualDFT:
    """Koopmans: I = -E(HOMO), A = -E(LUMO), both already in eV.

    Read the module docstring before trusting a hardness from here. It is
    offered because it is free from any job that has already run, not
    because it is the better estimate.
    """
    if homo_ev is None or lumo_ev is None:
        return _refuse(
            DescriptorMethod.KOOPMANS,
            "The output has no orbital energy table with both an occupied and an "
            "empty orbital, so there is no HOMO/LUMO pair to work from.",
        )
    return descriptors(-homo_ev, -lumo_ev, DescriptorMethod.KOOPMANS, _KOOPMANS_CAVEAT)


def from_delta_scf(
    neutral_hartree: float | None,
    cation_hartree: float | None,
    anion_hartree: float | None,
) -> ConceptualDFT:
    """Vertical I and A from three total energies at ONE geometry.

        I = E(cation) - E(neutral)      A = E(neutral) - E(anion)

    All three must be at the NEUTRAL geometry for these to be vertical
    quantities; relaxing the ions gives adiabatic values, which are a
    different thing and smaller. The caller is responsible for that, since
    only it knows how the jobs were set up.
    """
    if neutral_hartree is None or cation_hartree is None or anion_hartree is None:
        missing = [
            name
            for name, value in (
                ("neutral", neutral_hartree),
                ("cation", cation_hartree),
                ("anion", anion_hartree),
            )
            if value is None
        ]
        return _refuse(
            DescriptorMethod.DELTA_SCF,
            f"Delta-SCF needs all three energies and the {', '.join(missing)} "
            "calculation did not produce one.",
        )
    return descriptors(
        (cation_hartree - neutral_hartree) * HARTREE_TO_EV,
        (neutral_hartree - anion_hartree) * HARTREE_TO_EV,
        DescriptorMethod.DELTA_SCF,
        _DELTA_SCF_CAVEAT,
    )
