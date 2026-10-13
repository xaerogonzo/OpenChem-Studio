"""The method/basis presets and solvents a quantum-chemistry job is offered, as plain strings.

**WHY THIS IS IN `domain/`.** They were in `chem/orca_engine.py`, and the quantum-chemistry panel, the calculator
registrations and the tests read them from there. A recipe (`domain/recipe.py`) has to offer the same list as a
choice, and a domain module cannot import the chemistry layer, so the strings moved to the layer both can see.
`chem.orca_engine` re-exports them under the same names, and nothing that imported them from there changed.
The comments below moved with them: the reasons for the NMR presets are measurements, not decoration.
"""

from __future__ import annotations

# General-purpose presets first, then two aimed specifically at NMR.
#
# Why NMR needs its own: shielding is dominated by electron density in the
# CORE region, and the general-purpose valence bases above carry no tight
# core functions, so they get absolute shieldings meaningfully wrong.
# Jensen's pcSseg-n family is built for exactly this. Confirmed live
# against a real ORCA 6.1.1 run -- "Your calculation utilizes the basis:
# pcSseg-1" -- and the difference is not cosmetic: water's 1H shielding
# moved 1.3 ppm between B3LYP/def2-SVP and B3LYP/pcSseg-1 with CPCM, which
# in a 1H window of roughly 0-12 ppm is the gap between calling a proton
# aromatic or vinyl.
METHOD_BASIS_PRESETS = [
    "B3LYP def2-SVP",
    "PBE0 def2-TZVP",
    "M062X def2-TZVP",
    "B3LYP 6-31G(d)",
    "B3LYP pcSseg-1",
    "B3LYP pcSseg-2",
]

# CPCM solvents, as ORCA names them. Real spectra are recorded in solvent,
# not gas phase, and the difference is largest exactly where it is most
# visible -- exchangeable protons like COOH/OH. Confirmed live that
# `CPCM(Chloroform)` is accepted and activates ORCA's solvation model.
# "" means gas phase, which stays the default so existing behaviour and
# every previously-cached TMS reference remain valid.
SOLVENTS = ["", "Chloroform", "DMSO", "Water", "Methanol", "Acetone", "Toluene", "Benzene"]
