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

Two classifier bugs were found by these molecules rather than by tests, and
both are recorded in `chem/vibrational_modes.py`:

1. Requiring only two substituents *total* around a bond made every C–H bond
   a dihedral candidate, so **methane's bends came back as torsions** — and
   methane has no dihedral to twist.
2. The geometric test alone called 11 of acetone's 24 modes torsional,
   including bands at 1226 and 1372 cm⁻¹. A methyl deformation has nearly
   the same displacement pattern as a methyl torsion; separating them needs
   the change in dihedral *angle*, which this does not compute. The label is
   therefore bounded to soft modes (≤ 500 cm⁻¹), where it is physically
   defensible, rather than claiming a distinction the method cannot make.
