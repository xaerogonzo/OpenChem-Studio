"""The ionisable-site summary: each centre pkasolver found, whether it is an acid or a base, and how
much of it is ionised at a pH.

`pKa` lists the values. This reads the SAME predictions and says what each means at a chosen pH, so
"which group is charged at 7.4" does not have to be worked out by hand from a list of numbers. It
computes no pKa of its own and asks the sidecar for nothing `pKa` does not: it takes the answer
`compute_pka` keeps for the structure.

**ACID OR BASE IS READ FROM THE MODEL'S OWN STATE, NOT FROM A NAME.** For each prediction pkasolver
reports the site atom's hydrogens and formal charge in the protonated form. Losing a proton lowers the
charge by one, so the form that holds the proton is neutral or anionic for an ACID (a carboxylic acid
becomes a carboxylate: 0 to -1) and cationic for a BASE (an ammonium becomes an amine: +1 to 0). The
rule is therefore the charge of the protonated form: `<= 0` is an acid, `>= +1` a base. A prediction
from an older payload with no microstate says so and gets no direction.

**THE FRACTION IS FOR THIS SITE ALONE.** Henderson-Hasselbalch for one site treats it as if the
others did not exist. Real sites interact (the second pKa of a diacid is raised by the first
ionisation), and the numbers here are macroscopic-looking values of a model trained on single sites, so
the fraction is a guide to which groups are mostly charged, not a species distribution. The whole
molecule's dominant form is `Major Microspecies`.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A site is an acid or a base, or its direction could not be read.
ACID = "acid"
#: The proton-holding form is a cation: an ammonium-like site whose pKa is its conjugate acid's.
BASE = "base"
#: The prediction carried no microstate, so which way it ionises is not known.
UNKNOWN = "unknown"

#: The charge of the proton-holding form at or below which a site is an ACID. Zero is a neutral acid
#: (AH to A-); a negative value is a further ionisation of an anion.
_ACID_CHARGE_AT_MOST = 0


@dataclass(frozen=True)
class IonisableSite:
    """One centre, read for a pH."""

    #: The site atom in the molecule's own numbering, or None where the model's atom could not be mapped.
    atom_index: int | None
    pka: float
    #: Pkasolver's own ensemble spread; 0.0 when the payload predates it.
    spread: float
    kind: str
    #: Of THIS site alone, the share that is charged at the pH (deprotonated for an acid, protonated for a
    #: base), or None when the kind is unknown.
    fraction_ionised: float | None
    #: The same share at pKa -/+ the spread, lowest first, or None when there is no spread or no kind.
    fraction_range: tuple[float, float] | None


def kind_of(protonated_site: tuple[int, int] | None) -> str:
    """Acid or base from the formal charge of the proton-holding form (see the module docstring)."""
    if protonated_site is None:
        return UNKNOWN
    return ACID if protonated_site[1] <= _ACID_CHARGE_AT_MOST else BASE


def fraction_ionised(kind: str, pka: float, ph: float) -> float | None:
    """The share of a single site that is ionised at `ph`.

    An acid is ionised when it has LOST its proton, which is the larger the more the pH exceeds the pKa;
    a base is ionised when it HOLDS one, the larger the more the pKa exceeds the pH. At pH = pKa both
    are one half.
    """
    if kind == ACID:
        return 1.0 / (1.0 + 10.0 ** (pka - ph))
    if kind == BASE:
        return 1.0 / (1.0 + 10.0 ** (ph - pka))
    return None


def read_site(prediction, ph: float) -> IonisableSite:
    """An `IonisableSite` from a `pka_providers.PkaPrediction`."""
    kind = kind_of(prediction.protonated_site)
    spread = float(prediction.stddev or 0.0)
    fraction = fraction_ionised(kind, prediction.value, ph)
    shown_range = None
    if spread and fraction is not None:
        low = fraction_ionised(kind, prediction.value - spread, ph)
        high = fraction_ionised(kind, prediction.value + spread, ph)
        shown_range = (min(low, high), max(low, high))
    return IonisableSite(
        atom_index=prediction.atom_index,
        pka=float(prediction.value),
        spread=spread,
        kind=kind,
        fraction_ionised=fraction,
        fraction_range=shown_range,
    )


def read_sites(predictions, ph: float) -> list[IonisableSite]:
    """Every site, lowest pKa first, the order `pKa` lists them in."""
    return [read_site(p, ph) for p in sorted(predictions, key=lambda p: p.value)]
