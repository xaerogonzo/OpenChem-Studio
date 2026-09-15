# Charge models beyond EEM and QEq: triage (2026-09-14)

Nothing here is a calculator. Each record says whether a published model can
be validated well enough to pre-register one, following the EEM and QEq
precedent in [`../rappe_goddard/`](../rappe_goddard/README.md). Section 2's
checks are pre-registered below **before any of them runs**; git order is the
evidence.

## Status schema

- **GO-CANDIDATE** needs all four of:
  - equations complete, errata included;
  - parameters complete for the elements claimed;
  - a reproducible numeric oracle: coordinates or a reconstructable geometry,
    plus printed numbers;
  - a feasible implementation path.
- **HOLD** names each missing element.
- **NO** gives the reason: not transferable, insufficient parameters, or the
  wrong product surface.
- **Evidence basis** is one of: full PDF with figures inspected; PDF plus
  supplement; text layer only; web metadata. An unanswered question is written
  "none found", never left blank.

## Reuse, stated once

Every model here can reuse:
- the `PerAtomDataset` result;
- provenance;
- the GEOMETRY input policy and its refusals;
- the result store.

None of them should inherit QEq's solver. Each needs its own abstraction:

| Model family | What is specific to it |
|---|---|
| Oda–Hirono | a pair-kernel choice (NM, NMW, Ohno, Ohno–Klopman, DasGupta–Huzinaga) inside an EEM-shaped linear system |
| SQE (Nistor, Mathieu) | bond-space split-charge variables and bond hardness; Mathieu also adds a pair energy penalty |
| QTPIE | charge-transfer variables attenuated by ns Slater *overlap*, with a rank-deficient system solved by pseudoinverse |
| PQEq | core–shell charges with shell positions relaxed, and Gaussian shielding |
| Periodic EQeq/PQEq | lattice sums; see ROADMAP, "Periodic charge equilibration (deferred)" |

## 1. Records

### SQE: Nistor, Polihronov, Müser & Mosey 2006

`nistor2006.pdf` plus `nistor2006_si.pdf.pdf` (the archived UWO group site).
- **Evidence basis:** PDF plus supplement.
- **Equations:** complete; eq 4 gives methods i–iv, and the supplement's "SQE
  Methods" page restates them.
- **Parameters:** complete for H, C, O and Si, for all four methods.
  - Parameter sets: the all-family set, the Si–O–H and C–O–H family sets, and
    sets fitted to ESP surfaces and to Mulliken charges (supplement pp 3–7).
  - Slater orbitals: n and ζ (Å⁻¹) for H 1/2.315, C 2/1.618, O 2/1.842 and
    Si 3/1.818 (p 8). The paper credits Sefcik et al. 2002 for Si and H.
- **Numeric oracle:** for all 41 molecules, atomic number, x/y/z, B3LYP ESP
  charge, method i–iv charges and a per-molecule Sigma. The paper's Table IV
  (hexamethyldisiloxane) serves as a cross-check.
- **Runnable reference:** none found.
- **Scope fit:** molecular, H/C/O/Si.
- **Licence of the supplement:** "All information is licenced under the GNU:
  Reproduction by nonprofit organizations or for academic use." The numbers
  are transcribed with attribution, and this line is recorded with the source.
- **Verdict (after check 2.1): HOLD on geometry.** The charges are complete.
  The last hydrogen of every one of the 41 molecules has lost its coordinates
  in the archived pages (section 3). The site links each table to
  `molecules/Mnnn.xyz`, which would restore the geometry; the Internet Archive
  was offline when this was checked. Once those files are found, it is the
  first implementation PR.

### SQE: Mathieu 2007

`mathieu2007.pdf` plus the `mathieu2007_si/` EPAPS folder (README.TXT plus
194 EQ and 55 TS `.xyz` files).
- **Evidence basis:** PDF plus supplement.
- **Equations:** complete (eqs 10–14: split charges, the hardness kernel, the
  energy penalty).
- **Parameters:** Table II, models A–D, for C, H, N, O and F. Model B's χ and
  η are Bultinck et al.'s, identical to this application's shipped EEM table
  (measured: χ relative to H is C 4.25, N 7.80, O 13.72, F 14.00; η is
  C 9.00, H 17.95, N 9.39, O 14.34, F 19.77).
- **Numeric oracle:** the deposited geometries with B3LYP/6-31G\* Mulliken
  charges. Table I prints R² per element and σ_q for the EEM and SQE rows on
  EQ, TS and NL. It is an aggregate oracle, not per-atom.
- **Runnable reference:** none found.
- **Scope fit:** molecular, C/H/N/O/F, including transition states.
- **Verdict: GO-CANDIDATE** for SQE model B with the aggregate oracle. Check 2.2
  also gives the **shipped EEM** an external test.

### Oda & Hirono 2003

`oda2003.pdf`.
- **Evidence basis:** full PDF.
- **Equations:** complete (eqs 14–18: NM, NMW with f_r = 1.2, Ohno,
  Ohno–Klopman, and DasGupta–Huzinaga with k = 0.4).
- **Parameters:** methods 1–5 use Rappé–Goddard Table I (held); method 6 uses
  Bakowies–Thiel QEq/PD (transcribed).
- **Numeric oracle:** Table 9 gives per-atom charges for α- and β-D-idose under
  all six methods and HF-ESP.
  - Geometries are "optimized using ab initio HF calculations, with 6-31G\*\*
    basis sets" and are **not printed**; neither is the conformer.
  - Tables 4–8 give RMSD and correlations over 87 compounds, whose geometries
    are not printed either.
- **Runnable reference:** none found. The "original QEq" charges came from
  ArgusLab 3.0.
- **Verdict: HOLD** on two separate properties:
  - **geometry reproducibility** (check 2.3);
  - **source-method reproducibility**: whether "HF-ESP" can be matched to
    their fitting scheme, and whether the atom labels map to structure.
    Robustness across conformers alone does not make Table 9 an oracle.

### QTPIE: Chen & Martínez 2007, and the 2008 erratum

`chen2007.pdf`, `chen2008.pdf` (the one-page erratum), `chen2008framework.pdf`.
- **Evidence basis:** full PDF plus erratum.
- **Equations:** complete (eqs 5–10), using Rappé–Goddard parameters unchanged,
  without the hydrogen correction ("QEq(-H)").
- **What the literature currently supports:**
  - *2007 paper:* Table 1 gives polarizability eigenvalues for NaCl, H₂O and
    phenol under QEq(-H), QTPIE and MP2.
  - *2008 erratum:* the QTPIE column "is incorrect due to a programming
    error", and QEq(-H) and QTPIE "should have identical polarizabilities
    given the same parameters". The predicted charges are unaffected.
  - *Therefore:* the 2007 QTPIE polarizability column is retracted and is
    **never** a benchmark. The QEq(-H) and MP2 columns stand.
- **Numeric oracle:** the QEq(-H) polarizability column (geometry "computed
  with MP2/cc-pVDZ", not printed) and two analytic properties: charge transfer
  vanishes at dissociation (eq 10), and the erratum's equal-polarizability
  identity. Charges appear only in figures.
- **Runnable reference:** LAMMPS `fix qtpie/reaxff` (since 19Nov2024). Whether
  it uses the 2007 overlap form is unverified.
- **Verdict: HOLD**, on a charge-level numeric oracle.
- `chen2008framework.pdf` is theory (atom-space and bond-space); its EPAPS is
  combinatorics. No oracle.

### ACKS2: Verstraelen, Ayers, Van Speybroeck & Waroquier 2013

`verstraelen2013.pdf`.
- **Evidence basis:** full PDF.
- **Parameters:** only a pair fitted to H–F dissociation (Table I: μ_H − μ_F,
  η_H + η_F, 1/X0, τ).
- **Numeric oracle:** none found; Fig. 3 is a plot.
- **Runnable reference:** LAMMPS `fix acks2/reaxff` (ReaxFF-parameterised).
- **Verdict: NO** as a molecular calculator now: there are no transferable
  parameters.

### PQEq: Naserifar, Brooks, Goddard & Cvicek 2017

`naserifar2017.pdf`, `SupplementaryMaterial-PQEq.pdf`, and
`SupplementaryMaterial-PQEq-par.txt` / `-PQEq1-par.txt`.
- **Evidence basis:** PDF plus supplement, figures inspected.
- **Parameters:** complete across the periodic table (Tables S1 and S2, and the
  parameter files). Hydrogen has J = 12.98410 eV and no charge dependence.
- **Numeric oracle:** none found. SI §5's 30 structures are schematic images
  (B3LYP/6-311G\*\*), and the §6–8 charge and energy comparisons are image
  plots.
- **Runnable reference:** none found.
- **Verdict: HOLD** on a numeric oracle or a runnable implementation.

### EQeq: Wilmer, Kim & Snurr 2012

`wilmer2012.pdf`, `wilmer2012_si.pdf`.
- **Evidence basis:** PDF plus supplement.
- **Parameters:** SI S2 (ionisation energies to Z = 84) and S3 (inputs).
- **Numeric oracle:** SI S5 gives per-atom charges for 12 MOFs, periodic only.
- **Runnable reference:** numat/EQeq (GPL-2.0, deprecated, crystals).
- **Verdict: NO as a molecular calculator.** The periodic version is recorded
  on the roadmap.

### Context, not a model: Sefcik, Demiralp, Çağın & Goddard 2002

`sefcik2002.pdf`.
- Goddard's group re-fitted QEq's Si and H to B3LYP ESP charges, with SiH₄ in
  the training set, and replaced the iterated hydrogen with a quadratic
  (Table 1).
- It prints no SiH₄ charge. It supports A7's conclusion that the group moved
  away from the 1991 Si/H treatment, and is not an oracle.

## 2. Checks, pre-registered before they run

### 2.1 Nistor supplement extraction

`nistor_extract.py` reads the 41 molecule pages positionally
(`get_text("words")`, grouped by row) into
`tests/fixtures/charge_models/nistor2006_si_molecules.csv`. That file is hashed in
the same commit as its checks, and records molecule, index, Z, x, y, z, ESP,
and methods i to iv.
1. **Count:** 41 molecule tables, each atom count consistent with the formula
   in the index.
2. **Sum check:** every charge column sums to the net charge, 0 for all 41
   neutral molecules. The paper constrains ESP charges "to have net zero
   charge". The tolerance is n × 0.5 × 10^(−d), where n is the atom count and
   d the printed decimals of that column (4 in the samples read).
3. **Sigma check.** The paper's eq 18 defines
   Δ_n² = Σ_i (Q_i − Q_i^qc)² / Σ_i (Q_i^qc)², over all atoms. The printed
   per-molecule "Sigma" is a percentage. Its exact form is identified, not
   assumed:
   - **candidates:** 100·Δ_n and 100·Δ_n²;
   - **decision rule:** the candidate matching every molecule and method within
     the rounding bound wins. The bound is the printed charges' ±0.5 × 10^(−d),
     propagated to first order through the candidate formula, plus the
     Sigma's own printed rounding;
   - **failure:** if neither candidate matches all, the check fails and the
     mismatches are listed.
4. **Suspect coordinates:** any atom at exactly (0, 0, 0) that is not the first
   atom is classified.
   - **VALID** if its distance to its nearest atom lies within 0.85–1.25 × the
     sum of covalent radii (RDKit's periodic table) and it is ≥ 0.7 Å from every
     other atom.
   - **SUSPECT** otherwise.
   - A SUSPECT molecule is excluded from any geometry-based oracle and listed.
     M111 (hydrogen 15) is the known case.
5. **Cross-check:** the extracted hexamethyldisiloxane table equals the paper's
   Table IV for ESP and methods i–iv, every printed cell.

### 2.2 Mathieu Table I, the EEM EQ row, against the shipped EEM

`mathieu_eem_check.py` freezes `mathieu2007_si/A6.11.108.EPAPS/EQ/*.xyz` into
`tests/fixtures/charge_models/mathieu2007_eq.csv` (molecule, index, element, x, y, z,
Mulliken charge), hashed in the same commit.
1. **Identity first, then metrics.** Section II's EEM energy is transcribed:
   the Coulomb kernel, whether any κ applies to the EEM rows, the η versus 2η
   convention, and any hydrogen special case.
   - A full match with `ce.eem_charges` (eq 3: 2η\* diagonal, 1/R) is labelled
     **EXTERNAL ORACLE FOR THE SHIPPED EEM**.
   - Any mismatch is labelled **RELATED EEM IMPLEMENTATION**, and the metrics
     are still reported.
2. **Population:**
   - all 194 EQ molecules, each at net charge 0 unless its file says otherwise;
   - a molecule with any element outside H/C/N/O/F is excluded and counted;
   - the count is compared with anything the paper states.
3. **Metrics:**
   - R² is the squared Pearson correlation between EEM and Mulliken charges,
     over all atoms of that element in the population;
   - "All" is R² over every atom;
   - σ_q is the unweighted RMS of (EEM − Mulliken) over every atom.
4. **Acceptance:** each reconstructed R² equals Table I's printed "EEM EQ"
   value within ±0.005 (two-decimal rounding), and σ_q within ±0.00005.
   - A pass is recorded under the identity label from step 1.
   - A miss is recorded as found. It never adjusts the shipped EEM.

### 2.3 Oda–Hirono geometry pre-flight (ORCA)

Frozen before any quantum-chemistry run.
- **Structures:** α- and β-D-idose (pyranose; SMILES written in the script,
  with stereo checked against the IUPAC name by RDKit's CIP labels).
- **Conformers:**
  - RDKit ETKDGv3 with seeds 1–20, then MMFF94 pre-optimisation;
  - uniqueness at heavy-atom RMSD ≥ 0.5 Å, keeping at most the 10
    lowest-MMFF94-energy unique conformers per anomer.
- **Quantum chemistry:** each conformer optimised at HF/6-31G\*\*
  (`! HF 6-31G** Opt`), then CHELPG charges at the same level.
- **Report:** per atom, the spread (max − min) of charges across conformers,
  and the labelled Table 9 HF-ESP value beside them.
- **Decision rule, fixed now:** Table 9 can serve as a per-atom oracle only if
  both hold:
  - the maximum per-atom spread across conformers is ≤ 0.02 e;
  - source-method identity is established, meaning the charge scheme and atom
    labels are matched to the paper's text.

  Otherwise it may serve only as a ranking and sign oracle. Either way, the
  outcome is recorded here.

## 3. Results

### 3.1 Nistor supplement extraction (2026-09-14)

`nistor_extract.py`, run once, wrote three fixtures. Their LF-normalised
SHA-256 values are recorded here:
- `nistor2006_si_molecules.csv` (689 atom rows):
  `ca72f18a0f67c882dbb0ca336282b1321fffcd60beb1d1c4e0bf552ceff0468f`
- `nistor2006_si_sigma.csv` (41 rows):
  `923d67e86953d9f1e7f139600d729c00a490cbf0b18c0f736b6ea5f567751197`
- `nistor2006_table4.csv` (27 rows):
  `e12e338042fd8aa95ccab8c145288f27505fb59104ed68c68026ef428e6fa5b8`

The checks live in `tests/test_charge_models_triage.py`. Every failed check is
a strict xfail, and its contents are pinned by
`test_nistor_the_measured_departures_are_exactly_these`.

| Check | Result |
|---|---|
| 1. 41 tables, atom counts match the index formula | **FAILED on one name.** All 41 tables are present, and 40 match. Molecule 28 is printed "SiH(CH2)3" (SiC₃H₇), but its table holds C₄H₁₀Si; the site's label is wrong, not the extraction. |
| 2. every charge column sums to 0 within n × 0.5e-4 | **FAILED on 4 of 205 columns**, all fitted methods: molecule 5 ii (−0.0012 against 0.0009), 5 iv (+0.0011), 14 ii (−0.0012 against 0.00105), 18 ii (−0.0016 against 0.0012). Every ESP column passes. |
| 3. Sigma is one form of eq 18 | **PASSED: Sigma = 100·Δ_n** on all 164 molecule × method cells. 100·Δ_n² misses all 164. |
| 4. atoms at (0, 0, 0) | **Wider than expected.** The last atom of **all 41** tables is at exactly (0, 0, 0), always a hydrogen. The frozen rule calls 31 SUSPECT and 10 VALID; the 10 are coincidences of where the origin falls (molecule 16's "hydrogen" sits 1.166 Å from two oxygens at once). **A page-export artifact: every geometry is missing one hydrogen.** |
| 5. hexamethyldisiloxane equals the paper's Table IV | **FAILED on 1 of 135 cells.** Atom 15, method i: 0.0929 in the paper, 0.0930 in the supplement. The other 134 match exactly. |

**What it means for SQE:**
- Per-atom charges for all 41 molecules and all four methods are usable as an
  oracle, with the four sum departures and the one Table IV cell recorded as
  source inconsistencies at the 1e-3 e level.
- The geometries are not usable as they stand. Rebuilding a hydrogen position
  would be a reconstruction, not the source, so it is not done here.
