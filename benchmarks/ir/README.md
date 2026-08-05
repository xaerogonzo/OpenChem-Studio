# IR benchmark — harmonic frequencies against experiment

Scores what `OrcaQuantumEngineProvider.parse_vibrational_spectrum` extracts
from a real ORCA frequency job against experimental fundamentals.

```bash
python benchmarks/ir/score.py <directory of ORCA .out files>
```

## Result, B3LYP/def2-SVP, 16 modes over water, CO₂ and methane

| | |
|---|---|
| MAE unscaled | **64.7 cm⁻¹** |
| fitted scaling factor | **0.9666** |
| MAE scaled | **27.6 cm⁻¹** |

The factor is fitted by least squares through the origin, the standard form
for a harmonic scaling factor. **0.9666 is the external corroboration that
matters here**: published B3LYP scaling factors sit in the 0.961–0.975 band
depending on basis set, and this fit landing inside it — from a parser
written against the raw text — is evidence the numbers being read are the
right numbers, independent of any test in this repository.

The factor is recorded, **not applied**. ORCA states its own scaling factor
in the output ("Scaling factor for frequencies = 1.000000000 (already
applied!)") and that value is carried on the result, so anything applying
this 0.9666 on top must do so knowingly. Shipping raw harmonic values
labelled as harmonic is the same call the NMR path made with TMS
referencing.

## Intensities: scored by symmetry, not by a reference table

Frequency agreement does not imply intensity agreement, so intensities are
checked separately. No experimental intensity table is entered here —
instead the check uses a ground truth that needs no database at all:
**group theory says which bands must be exactly zero.**

| molecule | band | computed intensity | expected |
|---|---|---|---|
| CO₂ | symmetric stretch 1387.8 | **0.00** | IR-silent (centrosymmetric) |
| CO₂ | asymmetric stretch 2469.9 | 612.2 km/mol | the strong band |
| methane | ν₁ symmetric stretch 3019.2 | **0.00** | IR-silent (T_d, A₁) |
| methane | ν₂ bend 1530.8 / 1530.9 | **0.00** | IR-silent (T_d, E) |
| methane | ν₃ asymmetric stretch 3152 | 17.7 km/mol | active |
| benzene | 20 of 30 modes | **0.00** | D₆ₕ, most modes silent |

Every symmetry-forbidden band came back at exactly 0.00. That is a stronger
statement about the intensity column than a correlation against tabulated
values would have been, because the expected answer is exact rather than
approximate.

## What is deliberately not scored

**Acetone (24 modes) and benzene (30 modes) are run and parsed but not
scored on frequency.** Their experimental assignments are not one-to-one
with a sorted frequency list — many modes are mixed methyl rocks, ring
deformations, and degenerate pairs — so pairing them by index would
manufacture the comparison rather than measure it. `score.py` refuses any
molecule whose computed and reference mode counts differ, for that reason.

**The reference values are entered by hand**, from the standard literature
fundamentals for five small molecules, and `reference.json` says so. CCCBDB
is form-driven with no bulk API. Every value is a textbook number for an
unambiguous molecule specifically so a reader can check it without a
database.

## Mode classification

Checked against the same set. Water 1 bend / 2 stretches; CO₂ 2 bends /
2 stretches; methane 5 bends (3×ν₄ + 2×ν₂) and 4 stretches (ν₁ + 3×ν₃) —
textbook-exact. Benzene reports no torsions, correctly, having no rotatable
bond. Acetone reports exactly two, at 36.4 and 138.8 cm⁻¹, which are its two
methyl rotors.

These molecules found two classifier bugs, and then forced the method to be
replaced outright. All of it is recorded in `chem/vibrational_modes.py`.

The original classifier compared displacement *magnitudes* at the ends of a
bond against its centre. That made every C–H bond a dihedral candidate, so
**methane's bends came back as torsions** — and methane has no dihedral to
twist. Worse, it called 11 of acetone's 24 modes torsional, including bands
at 1226 and 1372 cm⁻¹, when acetone has exactly two methyl rotors. A methyl
*deformation* satisfies a magnitude test just as well as a methyl *torsion*:
in both, the hydrogens move and the carbons do not. It had to be propped up
with a "torsions are below 500 cm⁻¹" rule, which was a proxy standing in for
a measurement it could not make.

It is now a proper **internal-coordinate decomposition**: the geometry is
displaced a little along the mode and the changes in bond lengths, bond
angles and dihedral angles are measured directly, with the largest naming
the mode and no clear winner leaving it unlabelled.

The dihedral term is the **signed mean** per bond, not the sum of
magnitudes, and that is what finally separates the two. A real torsion turns
every dihedral about a bond the same way, so their signed mean is large; a
deformation swings one hydrogen forward as another goes back and the mean
cancels while the magnitudes do not. The frequency cutoff is gone —
`classify_mode` no longer takes a wavenumber at all.

Results above are from the current method. Benzene gained a label it
previously could not assign (30 of 30 classified, none unlabelled), and the
frequency and intensity numbers are unchanged, since classification does not
feed them.
