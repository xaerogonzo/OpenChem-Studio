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

`nistor2006.pdf` plus `nistor2006_si.pdf` (the archived UWO group site; first
saved as `nistor2006_si.pdf.pdf`, the name the fixture headers keep).
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
  `molecules/Mnnn.xyz`, which would restore the geometry. Once those files are
  found, it is a candidate for its own pre-registration.
- **The Internet Archive does not hold them** (CDX index queried 2026-09-15):
  - it lists 24 distinct URLs under `publish.uwo.ca/~mmuser/`, none an SQE
    page or an `.xyz` file;
  - the local supplement is itself a 2006 Acrobat Web Capture of the site.

  This is provenance only. The local supplement stays the primary source for
  the charges, and **no further hunting is planned**.
- **AIP's supplementary material holds no geometry files either** (checked by
  Alex, 2026-09-15). The publisher's download is this same PDF: 50 pages,
  Acrobat Web Capture dated 2006-05-23. **Every known route to the missing
  coordinates is exhausted**, so the geometry HOLD stands until a new source
  appears. Rebuilding the hydrogens would be a reconstruction, not the
  source.
- **Revised by check 2.7 (2026-09-15): PARTIAL.** No hydrogen is known to be
  missing: the coordinate column is displaced against the atom rows. One-row
  rotation recovers 6 molecules, and on them no method reproduces the printed
  charges (section 3.7).
  - Method i and iii R_eq10 come within 2e-3 e on SiH4 and CH4.
  - The larger molecules miss by up to 0.18 e.

### SQE: Mathieu 2007

`mathieu2007.pdf` plus the `mathieu2007_si/` EPAPS folder (README.TXT plus
194 EQ and 55 TS `.xyz` files).
- **Evidence basis:** PDF plus supplement.
- **Equations:** complete (eqs 6–14: split charges, the energy, the hardness
  kernel, the penalty). Eq 13 is printed with a sign error, and the model is
  defined by eq 8 (2.4a).
- **Parameters:** Table II, models A–D, for C, H, N, O and F. Model B's χ and
  η are Bultinck et al.'s, identical to this application's shipped EEM table
  (measured: χ relative to H is C 4.25, N 7.80, O 13.72, F 14.00; η is
  C 9.00, H 17.95, N 9.39, O 14.34, F 19.77).
- **Numeric oracle:** the deposited geometries with B3LYP/6-31G\* Mulliken
  charges. Table I prints R² per element and Δq (eq 15) for the EEM and SQE
  rows on EQ, TS and NL. The NL structures are not deposited. It is an
  aggregate oracle, not per-atom.
- **Runnable reference:** none found.
- **Scope fit:** molecular, C/H/N/O/F, including transition states.
- **Verdict (after check 2.4): HOLD.**
  - SQE model B, built from eq 8 with Table II's parameters, reproduces 7 of
    Table I's 12 SQE correlations. It misses H and F on EQ, and H, O and F on
    TS (section 3.5).
  - Its eq 13 as printed contradicts eq 8 and is indefinite on every
    structure.
  - Printed-parameter rounding moves R² by at most 0.0021, so it cannot
    explain the misses.
  - What does is not known.
- **The shipped EEM,** by contrast, reproduces all six EEM (EQ) values
  (2.2) and five of six EEM (TS) values (2.5; fluorine, n = 5, misses).
- **Identifiability context:** `verstraelen2011` shows a charge-only
  least-squares fit is in general ill-conditioned, so reproducing Mathieu's
  metrics validates his parameters in use, not their uniqueness.

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
  **Checked 2026-09-16 (3.10): it does not.** Its overlap is Chen's own Gaussian
  one from the thesis appendix, and its electrostatics are ReaxFF's, so it is
  NOT-SOURCE-EQUIVALENT and is not an oracle for QTPIE's charges.
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
- **Parameters:** SI S3 gives the run inputs. **S2 shows the ionisation
  energies only as plots**; the table itself is an accompanying file, not held
  on 2026-09-15 and **held since 2026-09-16** -- it is in the SI of the paper's
  own correction (`wilmer2012_correction`), along with the source, the charge
  centres and a sample CIF. The shipped table is still the reconstruction from
  Moore and Andersen, and was then shown identical to it.
- **Numeric oracle: HELD since 2026-09-15.** The accompanying zip is now on
  disk: 12 MOFs x 4 charge sets, each file carrying its unit cell and its
  per-atom charges. All 12 atom counts match the paper's Table 1 and every
  EQeq set sums to zero. (Before it arrived this row read "none held".)
- **Runnable reference:** numat/EQeq (GitHub reports GPL-2.0, archived as
  deprecated). It is a later fork, not the 2012 v1.00 code, and GPL-2.0 is not
  vendored here.
- **Verdict: NO as a molecular calculator.** The periodic version is recorded
  on the roadmap. Track 6's feasibility check
  (`benchmarks/charges/periodic/FEASIBILITY.md`) was **BLOCKED** when it ran
  and is **FEASIBLE** after the structures arrived (its section 8), with the
  ionisation table as a named substitution: it must be rebuilt from Andersen
  1999 and Moore 1970 and labelled a reconstruction.

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

**2.2 corrected before any metric was computed (2026-09-14).** Section II of
the paper was transcribed from the rendered pages.
- **EEM energy (eqs 1–2).** E = Σ_i (χ_i Q_i + η_i Q_i²) + Σ J_ij Q_i Q_j.
  The diagonal is therefore 2η, the same convention as the shipped EEM.
- **The pair term J_ij is never given an explicit form**; the text calls it
  "the Coulomb interaction" and cites Bultinck et al.
- **0.816 is not a Coulomb κ.** It is λ in the SQE pair penalty (eqs 7
  and 14).
- **Identity label, by the rule as frozen.** The kernel cannot be established
  from Mathieu's own text, so the label is **RELATED EEM IMPLEMENTATION**
  (Bultinck's kernel by citation). The shipped EEM uses 1/R, per Bultinck eq 3.
- **Table I's last column is Δq, eq 15:**
  Δq = (1/N_el) Σ_Z (1/N_Z) Σ_{i∈Z} (Q_i − Q_i^M)². That is the mean squared
  deviation per element, averaged over elements, **with no square root**. Step
  3's "unweighted RMS over every atom" was a wrong guess.

  Acceptance now uses eq 15's Δq (±0.00005). √Δq and the all-atom RMS are
  reported as diagnostics only.

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

### 2.4 Mathieu SQE model B against Table I's SQE EQ and SQE TS rows

Pre-registered 2026-09-15, before any SQE charge or corpus metric exists. The
reproduction is `mathieu_sqe_check.py`; its instrument tests are
`tests/test_mathieu_sqe_instrument.py`. Nothing here touches `src/`.

**Order, frozen:**
1. source audit (below);
2. instrument tests pass;
3. EEM baseline;
4. fixtures and check 2.5;
5. SQE corpus metrics;
6. verdict.

A corpus match cannot rescue a failing instrument test.

#### 2.4a Source audit (kept; results are appended in section 3, never here)

Transcribed from the rendered pages of `mathieu2007.pdf`.
- **Eq 2 (p. 2):** E_i = E_i° + χ_i Q_i + η_i Q_i².
- **Eq 6 (p. 4):** Q_k = Σ_{i<k} q_ik − Σ_{j>k} q_kj, with q_ij ≠ 0 only for
  i < j.
- **Eq 7 (p. 4):** E^p_ij = C_ij Θ(r_ij − λ_ij r^C_ij) ((r_ij − λ_ij r^C_ij) /
  (r_ij − r^W_ij))² q_ij².
- **Eq 8 (p. 4):** E = Σ_i E_i + Σ_{i<j} J_ij Q_i Q_j + Σ_{i…j} E^p_ij, where
  i…j runs over "only the N_p atom pairs such that r_ij < r^W_ij".
- **Eqs 9–11 (p. 4):** ∂E/∂q_ij = 0; ∂Q_k/∂q_ij = δ_kj − δ_ki; **Jq = B**.
- **Eq 12 (p. 4):** B_ij = χ_j − χ_i.
- **Eq 13 (p. 4):** J_ij,kl = 2η_i(δ_il − δ_ik) − 2η_j(δ_jl − δ_jk) +
  (J_il + J_jk − J_jl − J_ik) + K_ij × δ_ij,kl.
- **Eq 14 (p. 4):** K_ij = 2C_ij Θ(r_ij − λ_ij r^C_ij) ((r_ij − λ_ij r^C_ij) /
  (r_ij − r^W_ij))².
- **Sec. III (p. 5):** C_ij = C and λ_ij = λ for every pair.
- **Table I caption (p. 5):** C = 115 eV and λ = 0.816, with Bultinck et al.'s
  atomic parameters.
- **Table II caption (p. 6):** r^C_ij = r^C_i + r^C_j and r^W_ij = r^W_i +
  r^W_j. χ differences are relative to H, in eV; η is in eV.
  - Model B: χ − χ_H is C 4.25, H 0.00, N 7.80, O 13.72, F 14.00; η is
    C 9.00, H 17.95, N 9.39, O 14.34, F 19.77.
  - r^C: C 0.77, H 0.37, N 0.75, O 0.73, F 0.71 Å.
  - r^W: C 1.70, H 1.20, N 1.55, O 1.52, F 1.47 Å.
- **Table I (p. 5)**, R² to 2 dp (C, H, N, O, F, All) and Δq to 4 dp:

  | Row | C | H | N | O | F | All | Δq |
  |---|---|---|---|---|---|---|---|
  | EEM (EQ) | 0.96 | 0.81 | 0.95 | 0.66 | 0.36 | 0.97 | 0.0668 |
  | EEM (TS) | 0.96 | 0.86 | 0.93 | 0.86 | 0.36 | 0.96 | 0.0847 |
  | SQE (EQ) | 0.97 | 0.85 | 0.96 | 0.67 | 0.35 | 0.98 | 0.0650 |
  | SQE (TS) | 0.96 | 0.88 | 0.95 | 0.89 | 0.16 | 0.97 | 0.0952 |

- **The R² definition, verbatim (Sec. III.B, p. 5):** "a squared correlation
  coefficient R²q between the Qi and QiM data sets".
- **Prose values, a diagnostic and never an oracle (Sec. III.B, p. 5):** "fair
  atomic charges for EQ+TS, with Δq=0.0695 and a squared correlation
  coefficient R²q=0.97". This Δq equals Table I's EEM (NL) Δq.

**Eq 13 contradicts eq 8.** Write H for the Hessian of eq 8's first two terms
in atomic charges: H_aa = 2η_a (from eq 2), H_ab = J_ab for a ≠ b. By eq 10
and the chain rule:
- ∂E/∂q_ij = (χ_j − χ_i) + Σ_a (HQ)_a (δ_aj − δ_ai) + K_ij q_ij;
- ∂²E/∂q_ij∂q_kl = H_jl − H_jk − H_il + H_ik + K_ij δ_ij,kl.

Setting the gradient to zero gives **A q = χ_i − χ_j**, with that A. Expanding
H, the η part of A is 2η_j(δ_jl − δ_jk) − 2η_i(δ_il − δ_ik), and the Coulomb
part is J_jl − J_jk − J_il + J_ik. **Both are exactly the negatives of the
printed eq 13's**, while the printed K term keeps its + sign. Eq 12 is also the
negative of −∂E/∂q at q = 0. So the printed pair (eq 12, eq 13) equals
(−b, −A + 2K δ) and is not the stationarity condition of eq 8. Its diagonal,
−2η_i − 2η_j + 2J_ij + K_ij, is negative whenever K is small.

**Rule:** eq 8, the model's definition, governs. The literal eq 13 and eq 12
are kept as `literal_eq13_diagnostic` and are never on the solver path. The
rule is confirmed or overturned by instrument test 1 (finite differences of
eq 8), whose outcome is appended in section 3. Verstraelen 2011 eq 10
(`verstraelen2011`) writes the SQE energy with the kernel U^T J U + J′. That
corroborates the positive form; it is not evidence about Mathieu's print.

**Δq is not gated.** Check 2.2 measured eq 15 as printed at 0.004453 against
0.0668, and its square root at 6.6e-5 from it. Both forms are reported.

**Mulliken charges are a source limit:** 4 dp as deposited, and the underlying
B3LYP values are unknown. Per-atom errors are read with that in mind.

#### 2.4b The model as run

- **Energy:** eq 8 exactly. The stored parameter is η\*, the energy
  coefficient is η\*, and the Hessian diagonal is 2η\* (the shipped EEM's
  convention, eq 3 of Bultinck part I). The Coulomb sum runs over i < j.
- **J_ij = 1/R in atomic units.** Mathieu never writes the kernel and cites
  Bultinck; the shipped EEM uses 1/R and reproduced EEM (EQ) in 2.2.
- **χ and η** come from `ce.EEM_BULTINCK2002_PART1`. Only differences of χ
  enter (Verstraelen 2011, section II), and the relative values are asserted
  equal to Table II's.
- **Pairs:** i < j with r_ij < r^W_i + r^W_j, strictly (text above eq 8).
  - As r → r^W from below, K → +∞.
  - At r ≥ r^W the pair does not exist: eq 14 is never evaluated there.
- **Penalty:** eq 14 with Θ(0) = 0, because the text says only pairs with
  r_ij > λr^C are hampered.
- **Units, all inside the module:** coordinates in Å; R in bohr through
  `ce.EEM_BOHR_ANGSTROM`; A, b and K in Hartree per e², with χ, η and C
  divided by `ce.HARTREE_EV`; charges in e.
- **System:** M is N × N_p, and pair p = (i, j) has −1 in row i and +1 in
  row j. A = MᵀHM + diag(K) and b = −Mᵀχ.
  - Asymmetry ≤ 1e-14 is asserted, then A is symmetrised.
- **Solve:** `np.linalg.lstsq(A, b, rcond=1e-10)`. This is an implementation
  numerical policy, and instrument test 10 shows Q does not depend on it.
  - **The scientific output is Q = Mq.** When A has a null space, q is not
    unique, but Q is unique whenever H is positive definite on the neutral
    subspace of each pair-graph component.
- **Recorded per structure:** σ_max; σ_min of the retained singular values;
  condition = σ_max/σ_min(retained), never divided by a discarded value; the
  discarded count; the cycle dimension N_p − N + components; whether H is
  positive definite on each component's neutral subspace; ‖Aq − b‖∞ in
  Hartree/e and eV/e; the component count and each component's charge sum.
- **Valid** means residual ≤ 1e-9 Hartree/e, every component sum ≤ 1e-12 e,
  and H positive definite on the neutral subspaces.
  - **The expected invalid count is 0 in EQ and 0 in TS.**
  - An invalid structure is a recorded event with its reason, and is removed
    from the SQE and EEM populations alike.
  - The metrics then show the source, excluded and included populations.

#### 2.4c Metrics

- **R²** is `np.corrcoef(Q, Q^M)[0, 1]²`, which equals 1 − SSE/SST of a
  least-squares line with intercept. Instrument test 8 shows the two
  definitions agree.
  - Computed over atoms: each element over its own atoms, and "All" pooling
    every included atom of the set once.
  - Metric IDs are the fixed tuple (C, H, N, O, F, All), and "All" is not an
    element.
  - A subset with zero variance is undefined and fails its gate.
- **Population:** one builder, `population(fixture)`, serves EEM and SQE
  alike. Its rows are keyed (set, file, atom index in source order), and the
  keys are unique.
- **`mathieu_sqe_atoms.csv`**, one row per atom: set, file, atom index,
  element, Mulliken, EEM, SQE, and included with a reason. Every metric can be
  recomputed from it alone.
- **`mathieu_sqe_metrics.csv`**, per set and metric: n; printed SQE and its
  rounding interval [p − 0.005, p + 0.005); printed EEM; reconstructed SQE;
  recomputed EEM; |recon − printed SQE|; |recon − printed EEM|; and the
  discrimination class.
- **Non-gating per-atom diagnostics** (per element and All): mean signed
  error, MAE, RMS, max |error|, charge-sum error per structure, Δq as
  printed, and √Δq.
- **Small subgroups:** every element × set cell with n < 30 (TS F, n = 5, and
  TS N, n = 15) also reports the reference range, SSE, SST and the
  leave-one-out R² range. They still gate.

#### 2.4d Acceptance

- **Tolerance:** ±0.005, half a unit of Table I's second decimal.
- **EEM baseline first:** the shipped `ce.eem_charges`, run through
  `population()`, must return the six EEM (EQ) R² values pinned by 2.2
  (C 0.9619, H 0.8139, N 0.9535, O 0.6641, F 0.3574, All 0.9727, each to
  1e-4). If it does not, 2.4 stops.
- **Per set (EQ, TS), in order:**
  1. **Gate:** each of the six reconstructed R² lies in the printed SQE
     value's rounding interval.
  2. **Printed-value discrimination,** only where printed SQE and printed EEM
     differ by ≥ 0.01:
     - **STRICT** if |recon − SQE| < |recon − EEM| and recon lies outside
       the EEM value's rounding interval;
     - **AMBIGUOUS** otherwise, including a tie.
  3. **Model discrimination, reported and not gated:** reconstructed SQE minus
     recomputed EEM, on the same population.
- **Set verdict:**
  - **REPRODUCED:** all six gates pass, every applicable discrimination is
    STRICT, the invalid count is 0, and the manifest checks pass.
  - **AMBIGUOUS:** all six gates pass, but a discrimination is AMBIGUOUS.
  - **PARTIAL:** one to five gates pass. The failing metrics are listed; the
    count carries no scientific weight.
  - **NOT REPRODUCED:** no gate passes.
- **Model verdict:** REPRODUCED needs every instrument test passing, the
  baseline holding, and both EQ and TS REPRODUCED. It means **GO to a separate
  pre-registration and design stage for an SQE calculator**, not `src/` code.
  Anything less is HOLD, with strict-xfail stop records.

**Non-gating diagnostics:**
- **Rounding sensitivity, one parameter at a time** with every other value as
  published:
  - each relative χ (C, N, O, F) and each η (C, H, N, O, F) at ±0.005 eV;
  - λ at ±0.0005 and C at ±0.5 eV;
  - then the four λ × C corners.

  Each row gives parameter, baseline, perturbed value, set, metric and ΔR².
- **`literal_eq13_diagnostic`,** per set: the negative-eigenvalue count, the
  smallest and largest eigenvalues, the condition estimate, and the
  stationarity residual of its q under eq 8. It is not judged on whether its
  charges look plausible.
- **The prose EQ+TS values,** recomputed for the shipped EEM on the pooled
  population.

#### 2.4e Instrument tests, before any corpus metric

`energy_eq8` lives in the test file. It selects pairs, evaluates eq 7, builds
Q from eq 6 and sums eqs 2 and 8 with explicit loops, and calls none of the
module's `pairs`, `penalty`, `assemble` or `solve`.
1. **Finite differences at q = 0 and at a fixed nonzero q.** Central
   differences at h = 1e-3, 1e-4 and 1e-5 must converge. The acceptance step
   is h = 1e-4 (relative ≤ 1e-6). The gradient must equal Aq − b and the
   Hessian must equal A. The literal eq 13 matrix and B must differ from them.
2. **Two atoms, built through M** (column [−1, +1]ᵀ): q\* =
   (χ_A − χ_B)/(2η_A + 2η_B − 2J + K) with K > 0, and with K = 0 (which is
   `ce.eem_charges` for the pair), both to 1e-14.
3. **EEM limit through an explicit `penalty=None` branch** (K = 0, all pairs
   connected, eq 14 never evaluated): Q equals `ce.eem_charges` to 1e-10, and
   the energies agree.
4. **`test_k_zero_cycle_unique_atomic_charges_not_bond_charges`:** a K = 0
   triangle and z with Mz = 0 give Q(q + z) = Q(q) and E(q + z) = E(q), with
   one discarded singular value.
5. **Pair graph:** a four-atom geometry with exactly one pair beyond the
   cutoff. Its edges, components and each K are asserted.
6. **Cutoff and activation:**
   - K rises monotonically and stays finite at r^W − 1e-2, −1e-3, −1e-4 and
     −1e-5, and the solve is valid at each.
   - At r^W and r^W + 1e-6 the pair is absent and the component count changes.
   - At λr^C − 1e-9, λr^C and λr^C + 1e-9, K is 0, 0 and positive.
7. **Dissociation:** methanol from the EQ fixture, with its file and its C, O
   and H(O) indices recorded and their elements asserted. OH is translated
   rigidly along C→O in 1 Å steps until every inter-fragment distance exceeds
   its r^W sum by 1 Å; the charges are recorded at every step.
   - At the last step there are two components, each summing to ≤ 1e-12.
   - EEM's fragment sum there is > 0.01, reported as "EEM violates fragment
     neutrality at the separated geometry".
8. **R² definition:** `r_squared` equals 1 − SSE/SST with intercept and a
   hand-computed five-point value.
9. **χ shift:** adding c to every χ leaves Q, q and A unchanged.
10. **rcond policy:** on a well-conditioned case and on the cycle case, rcond
    1e-8, 1e-10, 1e-12 and 1e-14 give the same Q to ≤ 1e-12.
11. **Permutation:** permuting atoms and coordinates together gives the same Q
    per atom to ≤ 1e-12.
12. **Two molecules in one input:** each component sums to ≤ 1e-12.

**Mutations, each of which must turn a test red:**
- the literal eq 13 as the solver;
- Θ removed;
- η in place of 2η;
- `<=` at the cutoff;
- M's signs flipped.

A sixth mutation shows why independence is required: a planted `<=` cutoff
bug inside `pairs` must go uncaught by test 1 when `energy_eq8` is allowed to
call `pairs`, and be caught when it is not.

### 2.5 Mathieu Table I, the EEM TS row, against the shipped EEM

Pre-registered 2026-09-15, before the TS fixture is frozen. This is an
**external validation of shipped code, independent of 2.4**: neither verdict
feeds the other.
- **Population:** the EPAPS TS directory frozen as
  `tests/fixtures/charge_models/mathieu2007_ts.csv` in source atom order,
  with the expected counts 55 files and 1,085 atoms (C 327, H 592, N 15,
  O 146, F 5).
  - Manifests for EQ and TS record README.TXT's SHA-256 and, per source file,
    its SHA-256, atom and element counts, and its Mulliken-sum, coordinate and
    charge checksums.
  - The deposit's ZIP is not held and is recorded as such.
  - The EQ CSV must stay byte-identical.
- **Metrics and tolerance:** as 2.4c, ±0.005 against EEM (TS): C 0.96,
  H 0.86, N 0.93, O 0.86, F 0.36, All 0.96. Δq in both forms is reported and
  not gated, for 2.4a's reason.
- **Verdict:** REPRODUCED (all six gates pass), PARTIAL (the failing metrics
  are named), or NOT REPRODUCED. A miss is a strict-xfail stop record against
  the shipped EEM's external validation. It does not change 2.2 or 2.4.

### 2.6 Mathieu SQE: a named-cause test of 2.4's HOLD

Pre-registered 2026-09-15, after 2.4's results (section 3.5) and before any
number below exists. It asks one question: **is the model 2.4 built the model
Mathieu ran?** It fits nothing. χ and η are never refit (`verstraelen2011`).
The code is `mathieu_sqe_check.py` (extended); its outputs are
`mathieu_sqe_population.csv`, `mathieu_sqe_causes.csv`,
`mathieu_sqe_surface.csv`, `mathieu_sqe_powell.csv` and
`mathieu_sqe_stationarity.csv`.

#### 2.6a What pp. 6–8 add (rendered at 300 dpi, 2026-09-15)

Transcribed before any run, quoted where it matters.
- **The fit (Sec. III.C, p. 6).** "the parameters are varied until they
  minimize the scoring function [eq 15]"; "only local minimizations have been
  carried out using the Powell algorithm". Model B is "straightforwardly
  obtained using available values for χ_i and η_i and adding E^p_ij", and the
  fitted C and λ are Table II's.
- **Model B's objective at its optimum (p. 6):** introducing C and λ "yields
  only a slight improvement of the charges, with Δq decreasing from 0.0695 to
  0.0670". Both are on EQ+TS, the training set. In the form 2.5 measured
  (Table I's Δq is eq 15 under a square root), 0.0695 is EEM and **0.0670 is
  SQE model B at (115 eV, 0.816)**.
- **Model C (p. 7):** "a global optimization of all parameters yielded … R²_q
  = 0.98 and Δq = 0.0583". Table II model C, eV: χ − χ_H is C 5.44, H 0.00,
  N 10.48, O 22.37, F 29.80; η is C 8.93, H 18.86, N 10.06, O 20.55,
  F 45.74; λ is 0.695 and C is 8.03. Italics mark derived values.
- **Model D:** η C 27.08, H 13.39, N 18.97, O 16.40, F 14.62; λ 0.551;
  C 4.22.
  - Fitted to polarisabilities, which are not deposited. Its χ are not
    printed.
  - **Not usable.**
- **Model A:** Pearson's parameters, with no metric printed for them. **Not
  usable.**
- **Table III (p. 8)** lists the atoms whose SQE charge deviates from Mulliken
  by more than 0.2, with Q^M, the SQE Q_i and the deviation, each to 3 dp.
  - It is a **partial per-atom numerical oracle** (20 atoms), not a complete
    table and not categorical.
  - The paper's Sec. IV "focuses on model B", so Table III is read as model
    B.
- **Dipoles and polarisabilities (p. 8):** the B3LYP references are not
  deposited. Not usable.
- **No alternative Coulomb kernel or pair rule is named anywhere in the
  paper, so V3 = NONE.**

**Table III atoms, identified from deposited Mulliken charges only** (the
printed molecule name restricts the search, and |deposited Q^M − printed| ≤
5e-4). Frozen as `tests/fixtures/charge_models/mathieu2007_table3.csv`.
- 19 of the 20 rows identify one atom, or one symmetric pair whose deposited
  values round alike:
  - O2N-CF2-CF2-NO2 atoms 2 and 4;
  - difluorotetranitroethane atoms 2 and 4;
  - FCCF atoms 1 and 4, and atoms 2 and 3.

  Every atom of a pair is gated.
- **The last EQ row, printed "F3C-CN" at Q^M −0.421, matches no carbon.** It
  matches N6 (−0.4211), the only atom of that molecule within 5e-4. The row
  is identified by its value and recorded as a disagreement between the bold
  glyph and the printed number.
- The two "(NO2)2-CF-CF2-(NO2)" and "O2N-CF2-CF-(NO2)2" rows are one molecule
  (`trifluorotrinitroethane`), carbons 2 and 4.
- The TS rows cite references 52, 53 and 55. They identify
  `JPCA_2000_104_10526-ts1` (HCO+OH, O3 and H5), `JPCA2003-107-5798-TS17`
  (H3NO+HONO, N1 and O2) and `JPCA_2005_109_4829-TS1` (F17).

#### 2.6b Populations, frozen

- **Canonical order:** EQ then TS, file name in lexical order, source atom
  index. Every CSV row carries set, file, atom, element and `population_id`.
- **`SOURCE_POPULATION`:** all 249 deposited structures (EQ 194 and 3,064
  atoms; TS 55 and 1,085 atoms), from the manifests and never from a solver.
  Mathieu's own exclusions, if any, are unprinted.
- **`VALID_<arm>@<point>`:** structures passing 2.4b's validity predicate
  (residual ≤ 1e-9 Hartree/e **in the original, unscaled system**, component
  sums ≤ 1e-12 e, H positive definite on every neutral subspace) under that
  arm at that parameter point.
- **`COMMON_VALID`:** VALID_V0-unscaled@printed ∩ VALID_V0-scaled@printed.
  **Every cross-arm statement is made on it.**
- **Denominator rule:** a structure outside a population contributes no atom
  rows, and N_Z is recomputed. A failed structure never contributes zero
  error or NaN. The count of valid structures is a diagnostic, never an
  acceptance condition.
- **Fixed objective populations:** the stationarity and Powell objectives use
  the population fixed at the printed point, so they cannot jump as structures
  enter or leave.
  - An evaluation at which any structure of that population fails the
    predicate is flagged `population_violation`, never silently dropped.
  - A flagged point is never used to classify stationarity or a minimum.
- **Weighting, stated:** eq 15 averages atoms within each element, then
  elements. Molecules carry no weight of their own, so a large molecule
  counts through its many atoms. "Pooled EQ+TS" is not molecule-level
  weighting.

#### 2.6c Numerical arms

- **V0-unscaled:** exactly 2.4's solve (`lstsq`, rcond 1e-10). The historical
  reproduction baseline.
- **V0-scaled:** with D = diag(A), solve (D^−½AD^−½)y = D^−½b by the same
  `lstsq` and rcond, then q = D^−½y; validity is judged in the original
  system. The numerically stabilised baseline.
- Both are permanent records. For pentylamine, ts33 and any other structure
  whose validity differs between arms, the report gives status, charge
  difference, Δq difference and metric difference.
- A material difference between the arms opens a numerical investigation and
  is never read as evidence about Mathieu.
- **Every result row names its arm.**

#### 2.6d Oracles

- **G (Table I):** the 12 SQE gates, with 2.4c's definitions and 2.4d's
  intervals, per arm on that arm's VALID population.
- **T (Table III):** each identified atom's model charge within ±5e-4 of the
  printed Q_i (the 3 dp half-unit).
  - T passes if every identified atom passes, and the failing atoms are
    named.
  - An atom in a structure outside the arm's population is "not evaluable"
    and listed.
- **P_B (the p. 6 optimum value):** the pooled EQ+TS √Δq for model B at the
  printed point, against 0.0670.
  - **Known before running:** the shipped EEM's pooled √Δq on all 4,149 atoms
    is 0.069395 (section 3.5), against the printed 0.0695. Under half-up
    rounding [0.06945, 0.06955) that is outside by 5.5e-5, for a model that
    reproduces all six EQ correlations.
  - So P has three classes, fixed now:
    - **PASS:** within [p − 5e-5, p + 5e-5);
    - **NEAR:** within 1.1e-4 of p (twice the EEM analogue's miss);
    - **MISS:** otherwise.
  - The EEM analogue is recomputed in the same run and must reproduce
    0.069395 to 1e-6. Otherwise the run stops.
- **P_C (p. 7, diagnostic):** model C's parameters under each V0 arm give the
  pooled √Δq against 0.0583 (with P's classes) and the pooled R² All against
  0.98 (2 dp interval). **Diagnostic only**; it cannot change a verdict.
- **S (stationarity of the printed point), per V0 arm, on that arm's fixed
  population at the printed point.** The objective is pooled eq 15, as
  printed (no square root; its argmin equals the square root's, which is
  asserted as a property test).
  1. Δq at (115, 0.816): the core forensic datum, reported whatever else
     happens.
  2. **Step study:** central differences in physical units, ∂Δq/∂C per eV
     with h_C ∈ {1, 0.5, 0.25} eV, and ∂Δq/∂λ with h_λ ∈ {2e-3, 1e-3, 5e-4}.
     The middle step is used. If the three estimates of a component disagree
     by more than 1% relative (absolute floor 1e-12), the gradient is
     UNRELIABLE.
  3. The physical Hessian by central differences at the middle steps (4-point
     mixed term), with its eigenvalues. This is the forensic output.
  4. **Dimensionless coordinates for every gate:** c = C/115 eV and
     l = λ/0.816. g̃ and H̃ come from the physical ones by the chain rule.
     **Trusted:** H̃ positive definite and cond(H̃) ≤ 1e8.
  5. **δ from the p. 6 value:** p = 0.0670 printed to 4 dp, half-up, so
     δ = max((p + 5e-5)² − p², p² − (p − 5e-5)²).
  6. **g_tol = √(2δ·λ_min(H̃))**: the gradient at which H̃'s softest curvature
     would improve Δq by δ.
  - **Classes:**
    - **STATIONARY-AT-PRINTED:** trusted, ‖g̃‖₂ ≤ g_tol, and
      ½g̃ᵀH̃⁻¹g̃ < δ.
    - **NON-STATIONARY-AT-PRINTED:** trusted, and either test fails.
    - **UNRELIABLE:** the gradient or H̃ is untrusted.
  - **Surface:** C 60–200 eV in steps of 5 × λ 0.600–1.000 in steps of 0.024.
    Both axes contain the printed point exactly, which is its own CSV row.
    - Each grid local minimum (8-neighbour, unflagged) is refined on an 11 × 11
      subgrid spanning ±1 cell.
  - **Powell:** `scipy.optimize.minimize(method="Powell")` (SciPy, dev
    dependency group; the version is recorded in the output).
    - It runs in the scaled coordinates, with initial directions along the c
      and l axes.
    - Bounds are the box C ∈ [1, 400] eV and λ ∈ [0.3, 1.5], passed as
      `bounds`.
    - xtol 1e-8 and ftol 1e-12, maxfev 2000.
    - `success`, `message`, `nit` and `nfev` are recorded.
    - **Starts:** the printed point, every refined grid minimum, and
      (60, 0.6), (200, 0.6), (60, 1.0), (200, 1.0).
    - **Each row:** start C, start λ, end C, end λ, end Δq, iterations,
      status, basin id. End points closer than 1e-3 in both scaled
      coordinates share a basin.
  - **WITHIN-PREREGISTERED-NEIGHBOURHOOD:** an end point within C ±2 eV and
    λ ±0.01. A reporting convention.
  - **VERIFIED-NEARBY-MINIMUM:** such an end point whose own H̃ is trusted
    and positive definite with ‖g̃‖₂ ≤ g_tol.
  - **The S verdict:**
    - **STATIONARY:** stationary-at-printed and a verified nearby minimum;
    - **NON-STATIONARY:** non-stationary-at-printed and no verified nearby
      minimum;
    - **INCONCLUSIVE:** otherwise, including two or more verified basins
      within δ of each other anywhere on the surface.

#### 2.6e Variants, a closed list

- **V0:** 2.4's model, under both arms.
- **V1 (OpenChem reconstruction: bond-graph splits).**
  - Informed by Nistor's split-bond idea; not his rule, and never called it.
  - Pairs are r < 1.3 × (r^C_i + r^C_j) with Table II's r^C. The penalty is
    eq 14 on those pairs, the kernel as V0, the V0-scaled solve.
  - 1.3 is an engineering choice; 1.2 and 1.4 are reported as sensitivity.
  - **Valence check** on the graph: H 1, C 4, N 3, O 2, F 1. A structure
    failing it is V1-inapplicable, with its reason.
  - **EQ only:** TS structures contain partial bonds by construction, so V1 on
    TS is NOT APPLICABLE.
  - S and P are defined on EQ+TS, so they are NOT APPLICABLE to V1.
  - **Populations:** source EQ, V1-applicable, V1-inapplicable.
  - **V1 against V0 is reported on the V1-applicable population** with V0
    (scaled) recomputed there, and gates labelled as subpopulation gates. The
    V1-only figure is shown beside it.
- **V2 (Ohno–Klopman kernel), V0-scaled solve, V0 pair rule and penalty.**
  - Transcribed from `oda2003` **eq 17** (p. 162; eq 16 is the plain Ohno
    form): J_IJ = 1/√(R_IJ² + (1/(2J_II) + 1/(2J_JJ))²).
  - **Oda's convention (eqs 2–4):** E_I = E⁰ + q·χ⁰ + ½q²J_II, so J_II =
    ∂²E/∂q² is the full second derivative. Bultinck's and Mathieu's energy is
    χ\*Q + η\*Q², so **J_II = 2η\*** and the kernel here is J_IJ = 1/√(R² +
    (1/(4η\*_I) + 1/(4η\*_J))²).
  - The pair term is Oda's sum of halves, not a mean. Atomic units: R in
    bohr, η\* in Hartree.
  - Oda uses it for QEq's two-centre integrals. Here it is a diagnostic inside
    SQE.
  - **Instrument tests:**
    - R → ∞ gives 1/R;
    - R → 0 gives 4η\*_Iη\*_J/(η\*_I + η\*_J), which equals 2η\* for I = J;
    - η\* passed in eV must fail the R → 0 test.
  - S and P are evaluated for V2 exactly as for V0-scaled.
- **V3: NONE** (2.6a). No variant is added after any result exists.

#### 2.6f Verdicts

Per variant and arm, S, G, T and P are each reported, and **none rescues
another**. The rows are evaluated top to bottom, and the first match is the
class.

| Local class | Condition | Universal status |
|---|---|---|
| COMPATIBLE | S STATIONARY, all 12 G, T pass, P PASS or NEAR | REPRODUCED (claim: a reading consistent with Table I, III and p. 6) |
| G-compatible, S-incompatible | all G, S not STATIONARY | PARTIAL |
| S-stationary, G-incompatible | S STATIONARY, some G miss | PARTIAL |
| PARTIAL | anything else with at least one oracle passing | PARTIAL |
| INCOMPATIBLE | S NON-STATIONARY, no P PASS/NEAR, and T fails | INCOMPATIBLE |
| INCONCLUSIVE | S INCONCLUSIVE or UNRELIABLE, and nothing else passes | INCONCLUSIVE |
| V1 on TS, S or P | — | NOT APPLICABLE |

- Variants whose results agree within these oracles' own tolerances are
  reported as "no discrimination".
- Arms that disagree give INCONCLUSIVE for the model as a whole.
- Even a COMPATIBLE variant leaves SQE HOLD until its own GO pre-registration.

#### 2.6g Instrument tests, before any corpus run

1. V0-scaled equals V0-unscaled to 1e-12 on well-conditioned synthetic
   systems.
2. The prepared fast evaluator (pairs, MᵀHM and b cached; K rebuilt per
   (C, λ)) equals `solve` exactly on every synthetic case, and to 1e-12 on
   three corpus structures.
3. The eq 15 hand value on a 3-atom, 2-element toy.
4. argmin of Δq equals argmin of √Δq on a toy objective (a property, green
   by design).
5. δ and g_tol arithmetic.
6. Physical-to-scaled chain rule on an analytic quadratic.
7. The Powell wrapper (scaling, bounds, record fields) reaches the minimum of
   a quadratic in physical units with very different axis scales, and of
   both wells of a two-well function from starts in each basin, within 1e-6,
   and never leaves the box.
8. Basin labelling on the two-well function.
9. The V1 graph and valence check on synthetic ethanol and an over-bonded
   fragment.
10. Both V2 limits, and the eV mutation.

**Mutations (each must turn a test red):**
- scaling removed from the scaled arm;
- N_el wrong;
- the V1 factor not applied;
- V2's η left in eV;
- the fast evaluator using a stale K;
- a Powell start mislabelled as the printed one;
- the Powell wrapper reporting its end point in scaled rather than physical
  units;
- δ computed without the square root's rounding.

### 2.7 Nistor SQE: recover the geometry's atom correspondence, then test methods i, iii and iv

Pre-registered 2026-09-15, before any recovery or SQE charge exists. It
replaces the round 3 plan's "rebuild the missing hydrogen" design, because
three measurements made while writing it show that premise is wrong. Those
measurements use only coordinates and elements from
`nistor2006_si_molecules.csv`, no charge column, and are recorded here because
they motivate the design. The correction to check 2.1's record is appended to
section 3.1.

**What was measured (2026-09-15).**
1. **As printed, no molecule is chemically consistent.** 0 of 41 molecules
   give every atom its valence. That measurement used ad hoc radii (H 0.31,
   C 0.76, O 0.66, Si 1.11 Å, f = 1.25), not the registered rule below, which
   Step 2 applies.
2. **The real rows are self-consistent as a point set.** No two printed
   non-origin rows lie closer than 0.85 Å in any molecule.
3. **The origin row is not a hydrogen that lost its coordinates.**
   - It lies within 0.85 Å of a real row in 10 molecules (2, 3, 4, 12, 13,
     23, 31, 36, 37, 40): a fake point.
   - In the other 31 it sits at a chemically plausible distance.
   - Rotating the coordinate column down one row, so the origin belongs to
     atom 1, makes 6 molecules fully consistent, including SiH4, CH4 and
     CH3OH.
   - **So the coordinate column is misaligned against the element and charge
     columns** by a permutation that differs between molecules. That, not a
     lost hydrogen, is the defect. The raw PDF text shows the same rows, so
     the misalignment is in the archived page, not in `nistor_extract.py`.

**The model, from `nistor2006` pp. 2–5 and supplement pp. 3 and 8 (rendered).**
- **Energy:** V = Σ_i (½κ_iQ_i² + χ_iQ_i) + V_C, with Q_i = Σ_j q̄_ij over
  covalently bonded neighbours (eq 1), and V_C = Σ_{i<j} Q_iQ_jJ_ij(R_ij).
- **Kernel:** J_ij is the two-centre Coulomb integral of normalised ns Slater
  densities φ = A R^(n−1) e^(−ζR), A = √((2ζ)^(2n+1)/(4π(2n)!)), with n and ζ
  (Å⁻¹) of H 1/2.315, C 2/1.618, O 2/1.842 and Si 3/1.818. Energies are in eV.
  - The printed A values (H 1.987, C 1.084, O 1.500, Si 0.964) are a checksum
    on that transcription.
- **Method i** (eq 13): κ and χ per atom, QE rules.
- **Method ii** (eq 14): a fixed q̄ per bond type with no V_C. A pair
  "A–B v" puts +v on A and −v on B, checked by hand on CH3OH.
- **Method iii** (eq 16): method i plus a bond hardness κ^(s)_ij, with
  energy term ½κ^(s)_ij q̄_ij².
- **Method iv** (eq 17): method iii with χ_i = χ⁰_i + Σ_j Δχ_ij and
  κ_i = κ⁰_i + Σ_j Δκ_ij over bonded j, the Δ asymmetric.
- **The split-charge solve:** eq 9, ∂V/∂q̄_ij = 0 for i < j, with q̄_ji = −q̄_ij.
  The system can be singular on rings, and the atomic charges are the output
  (as in 2.4).

**Step 1: parameter set identification (topology only, no fit).**
- Method ii's charges depend on bonding alone. The supplement prints five sets:
  all-41 (p. 3), Si–O–H (p. 4), C–O–H (p. 5), ESP-fitted (p. 6),
  Mulliken-fitted (p. 7).
- The set used for the molecule tables is the one whose method ii q̄ values
  reproduce every printed method ii charge, given the recovered bonding, within
  n_bonds × 5e-5.
- A molecule matched by no set is BLOCKED on parameters. If more than one set
  matches, the all-41 set (the tables' own page) is used and the tie is
  recorded.

**Step 2: correspondence recovery, a constraint solve.**
- **Bonded rule:** d < f × (r_i + r_j) with Lange 15th ed. Table 4.7
  single-bond radii (`langes15`, already shipped in `tsei_radii.json`): H 0.30,
  C 0.772, O 0.66, Si 1.17 Å. f = 1.25 is an engineering choice; f = 1.15 and
  1.35 are reported as sensitivity.
- **Point sets tried:** S_all (all n rows, the origin included) and S_real (the
  n − 1 non-origin rows, one table atom left unplaced).
- **An assignment** maps table atoms to points one to one, and is valid when:
  - every placed atom's bonded-neighbour count equals its valence (H 1, C 4,
    O 2, Si 4, since every C and Si is tetracoordinate and every O
    bicoordinate, per the paper);
  - every bond joins two placed atoms under the rule;
  - every placed atom's method ii charge, recomputed from its neighbours'
    elements with the Step 1 set, matches the printed method ii value within
    5e-5 per bond. For S_real, the unplaced atom's missing bond is allowed to
    its parent only.
- **Symmetry classes:** table atoms with the same element and identical printed
  values in all five columns (ESP, i–iv) are interchangeable. Assignments
  differing only within a class are one solution.
- **Outcomes per molecule:**
  - **RECOVERED-UNIQUE:** exactly one solution on S_all, the origin row a real
    atom.
  - **RECOVERED-UNIQUE-ONE-UNPLACED:** no S_all solution and exactly one on
    S_real. The unplaced atom has no coordinates, so the molecule goes to
    INCONCLUSIVE for V_C methods; placing it would be a reconstruction, not
    done here.
  - **AMBIGUOUS:** more than one solution (count reported).
  - **UNRECOVERABLE:** none.
  - **BLOCKED:** parameters, or the solver's search limit of 10⁶ nodes.
- **What this is:** a recovery of which printed coordinate belongs to which
  printed atom, using only coordinates, elements and the topology-only method
  ii column. No coordinate is invented. **Method ii is used to recover, so it
  is never reported as an independent reproduction afterwards.**

**Step 3: methods i, iii and iv on RECOVERED-UNIQUE molecules.**
- **Kernel first, before any corpus run:** the ns Slater closed form in
  `charge_equilibration.py` (ζ converted to bohr⁻¹, result to eV) must equal
  an independent mpmath double integral of these normalised densities, for
  H–H, C–O and Si–Si at R = 0.5–6 Å, to 1e-9 eV.
  - It must also reproduce the supplement figure's R = 0 intercepts to plotting
    precision (H–H about 21, C–O about 9, Si–Si about 6.8 eV; a sanity check,
    not a gate).
  - If it fails, a separate kernel is written.
- **Oracle:** each atom's printed method charge, to 4 dp.
  - **Per atom:** reproduced if |Δ| ≤ 5e-5 (the half-unit), else failed.
  - **Per molecule × method:** REPRODUCED-ON-RECOVERED-CORRESPONDENCE when every
    atom is reproduced, else PARTIAL with the failing atoms and the largest |Δ|.
  - **Sigma = 100·Δ_n** (check 2.1's identified form) against the printed
    Sigma, reported.
- **Source inconsistencies already on record** are carried as expected
  departures, not failures: the method ii sum departures of molecules 5, 14
  and 18, and Table IV atom 15 method i. They do not touch methods i, iii and
  iv otherwise.
- **Program verdict:**
  - counts per class;
  - **GO-CANDIDATE** for a separate SQE pre-registration only if all three
    methods reproduce on at least 10 recovered molecules spanning the three
    families;
  - otherwise PARTIAL, INCONCLUSIVE or BLOCKED, with the reason.

**Universal status mapping:**
- REPRODUCED-ON-RECOVERED-CORRESPONDENCE → REPRODUCED (claim kind:
  implementation reproduction);
- PARTIAL → PARTIAL;
- AMBIGUOUS and ONE-UNPLACED → INCONCLUSIVE;
- UNRECOVERABLE → INCOMPATIBLE;
- BLOCKED → BLOCKED.

**Instrument tests, before any corpus run:**
- **Solver:** on a synthetic molecule with its rows permuted it recovers the
  permutation; it reports AMBIGUOUS on a constructed symmetric case where
  classes differ; it returns UNRECOVERABLE on scrambled coordinates.
- **Method ii recomputation:** reproduces CH3OH's printed column exactly.
- **Kernel checks** as above.
- **Split-charge solver:** equals a brute-force minimisation of V on a 3-atom
  toy for each method; method i equals an atomic QE solve with the same J on a
  connected molecule (eq 4's isomorphism).

**Mutations:**
- the pair sign convention flipped;
- ζ left in Å⁻¹;
- the S_real branch allowed to place the unplaced atom anywhere;
- symmetry classes ignoring the ESP column;
- Δ perturbations made symmetric;
- the two bond-hardness readings below exchanged.

**Amendment 2.7-A1 (2026-09-15, before any SQE charge or recovery number):
the bond-hardness factor is ambiguous in the source, so both readings run.**
The model above wrote the bond term as ½κ^(s)q̄². Reading the equations again
for the solver:
- **Eq 4** sums ½(κ^(s)_ij q̄_ij + …)q̄_ij over ORDERED pairs, so each bond
  contributes κ^(s)q̄². **Eq 10** differentiates to 2κ^(s)q̄, which agrees.
- **Eq 14's** stated solution q̄ = −χ̄/κ^(s) implies ½κ^(s)q̄² instead.

The paper contradicts itself by a factor of two in exactly the term methods iii
and iv add. So both run and both are reported, the way QEq's λ readings were:
- **R_eq10:** bond term κ^(s)q̄² per bond (eqs 4 and 10);
- **R_eq14:** bond term ½κ^(s)q̄² per bond (eq 14's solution).

Methods i and ii are unaffected: method i has no κ^(s), and method ii's q̄ is
printed directly. A method's class is assigned per reading. "Reproduced" under
one reading only is recorded with the reading named, and the reading is never
chosen by which one matches. Both are reported side by side.

The χ and atomic-κ terms are unambiguous, because eq 4 under the QE rules
equals eq 2's atomic form ½κ_iQ_i² + χ_iQ_i, and V_C = Σ_{i<j} Q_iQ_jJ_ij
runs over all atom pairs, bonded or not. Method iv's perturbations are read
per bonded neighbour: χ_i = χ⁰_i + Σ_j Δχ(Z_i–Z_j) using the ordered-pair row
("H-C" for an H bonded to C), and likewise κ.

**Amendment 2.7-A2 (2026-09-15): recovery narrowed to a one-row rotation.**
It is made AFTER a measurement on coordinates and elements only, with no
charge column and no SQE charge in existence, and disclosed as such.
- **Why the pre-registered general solve cannot deliver what it promised.**
  Its constraints are valence, the bonding rule and method ii charges, and
  method ii gives every hydrogen a value set only by its parent's element
  (H–C, H–O, H–Si).
  - So no topology-only constraint distinguishes a table hydrogen on one
    carbon from a table hydrogen on another carbon, or two hydrogens on the
    same carbon. The only columns that differ are the geometry-dependent ones
    (ESP, i, iii, iv), and choosing a correspondence by them would fit to the
    oracle.
  - A general solve would therefore return many solutions for every molecule
    with non-equivalent hydrogens, which is nearly all of them. That is a
    property of the constraints, argued here, not run.
- **The measurement.**
  - Every cyclic rotation of the coordinate column (and of its reversal) was
    tested per molecule with Step 2's registered bonding rule (Lange radii,
    f = 1.25).
  - 32 of 41 molecules have no consistent rotation.
  - **9 do, and all 9 are consistent at the same one: the column rotated down
    one row**, so the origin row belongs to table atom 1. They are molecules
    6 (SiH4), 26, 29, 32, 33, 34, 35, 38 and 41.
  - Five of them also have a second consistent rotation (SiH4, 29, 32, 35,
    41); these are the most symmetric molecules.
- **The amended Step 2.**
  - A molecule is RECOVERED-BY-ROTATION when the one-row rotation is
    consistent with the bonding rule at f = 1.25, AND with valence, AND every
    heavy atom's method ii charge recomputes to the printed value within 5e-5
    per bond.
  - Hydrogens are placed by the rotation itself, not chosen.
  - **Uniqueness:** every other consistent rotation must give the same
    structure. Their interatomic distance matrices, taken atom for atom in
    table order, must agree within 5e-3 Å (distances fix both the bonding and
    V_C, so equal matrices mean identical SQE charges per atom). A second
    rotation that differs is AMBIGUOUS.
  - Molecules with no consistent rotation are BLOCKED on correspondence. The
    general solve is not run, for the reason above.
  - f = 1.15 and 1.35 are reported as sensitivity on the rotation test only.
- **What stays unchanged:**
  - Step 1 (parameter identification), Step 3 (the oracle, tolerances,
    Sigma), both bond-hardness readings, the status mapping, and the
    mutations (plus: "rotation by two rows accepted as recovery").
  - **The GO bar stays at ten recovered molecules across three families.**
    With nine recoverable at most, Track 4 cannot reach GO. Its verdict is at
    best PARTIAL, and that is stated here, before any SQE number, rather than
    discovered afterwards.
- **This corrects check 2.1's record** ("every geometry is missing one
  hydrogen"). For these nine, nothing is missing: the column is displaced by
  one row. For the other 32, the scramble is not a rotation, and whether any
  atom is truly missing is not known.

**Amendment 2.7-A3 (2026-09-15): A2's uniqueness test restores Step 2's
symmetry classes.** It is made AFTER A2's recovery was run, with no SQE charge
in existence, and disclosed as such.
- **The measurement.** A2 as written gives 4 RECOVERED-BY-ROTATION (26, 33,
  34, 38), 5 AMBIGUOUS and 32 BLOCKED. Among the five:
  - molecules 29, 32 and 41: the second rotation moves heavy atoms, by up to
    5.50, 2.58 and 2.42 Å. These are genuinely ambiguous.
  - SiH4 (6) and CH4 (35): the second rotation (the reversal) moves only the
    four hydrogens, among the same four points. All four are identical in all
    five printed columns. The distance matrices differ by 0.0074 and 0.0152 Å,
    because the printed geometry is not exactly regular.
- **Why that is not ambiguity.** A2 required distance-matrix equality because
  equal matrices mean identical per-atom SQE charges. Here a stronger thing
  holds: each element carries the same set of points under both rotations, so
  the SQE solution on those points is the same. The two rotations differ only
  in which label a hydrogen gets, and every label in play prints the same
  value in every column. So every per-atom comparison is identical under both.
  A2 replaced Step 2 and dropped its symmetry-class rule; this restores it.
- **The amended uniqueness test.** A second consistent rotation is equivalent
  to the one-row rotation when, for every symmetry class (same element and
  identical printed values in ESP, i, ii, iii and iv, Step 2's definition), it
  places the class on the same set of printed points. Equivalent rotations are
  not ambiguity, and no tolerance is involved. Otherwise A2's distance-matrix
  test applies unchanged.
- **Effect:** 6 RECOVERED-BY-ROTATION (6, 26, 33, 34, 35, 38), 3 AMBIGUOUS, 32
  BLOCKED. The A2 counts are reported beside them. The GO bar is still
  unreachable.
- Mutation added: "symmetry classes ignoring the ESP column" now applies to
  this test.

### 2.8 Ionescu 2013: implementation reproduction of the published EEM models

Pre-registered 2026-09-15, before any EEM charge is computed from Table S1.
Claim kind: **IMPLEMENTATION REPRODUCTION** (the source's own model charges,
from its own parameters, structures and reference data), in the domain of
protein fragments only. It says nothing about small molecules.

Source: `ionescu2013` (doi 10.1021/ci400448n) and its supporting information.

**What was measured first (input side only; no EEM charge computed, no
comparison made).** These motivate the design and are recorded as such.
1. **Table S1 holds all 24 models**, read positionally by
   `ionescu_extract.py`: 180 rows, 12 E models with 6 atom types (H, C, N, O,
   S, Ca) and 12 EX models with 9 (H1, C1, C2, N1, N2, O1, O2, S1, Ca0), each
   with k and per-type A and B.
   - **Calcium is parameterised.** The round 3 plan left Ca conditional on
     this; it is decided here as INCLUDED, for every model.
2. **The QM/EEM CSV holds 12 scheme blocks.** Molecules per block: 41, except
   three blocks with 40 and one with 38. **The source population is therefore
   scheme-dependent**, and each scheme's own block defines it.
3. **Every fragment's total charge is an integer**, and the QM, E-EEM and
   EX-EEM columns all sum to the same one (measured on block 1: −9, −8, −4,
   −3, −2, −1, +1, −3, 0, +1, −3, −4, …). So the constraint is source-given
   and is never fitted.
4. **The PDB models and the CSV rows correspond atom for atom.** All 41
   fragments match in count and element, 0 mismatches, once the element is
   read as: a HETATM whose residue is `CA` is calcium (" CA " in an ATOM
   record is an alpha carbon), otherwise the atom name's first letter after
   any leading digit. Element totals then equal the paper's Table 1 exactly
   (H 19879, C 11912, N 3188, O 4954, S 148, Ca 61).
5. **One solve costs about 80 ms** for a fragment of ~1000 atoms; one pass
   over all 41 is 3.5 s.

**The model, transcribed (paper eqs 1–3).**
- X_i = A_i + B_i q_i + k Σ_{j≠i} q_j / r_ij, with A_i = X⁰_i + ΔX_i and
  B_i = 2(η⁰_i + Δη_i).
- Equalisation X_1 = X_2 = … = X̄ with Σ_i q_i = Q gives one linear system:
  rows B_i q_i + k Σ_{j≠i} q_j/r_ij − X̄ = −A_i, plus the charge row.
- **X̄ is an unknown of that system, not an input.** The paper's harmonic mean
  of Pauling electronegativities belongs to the *parametrisation* step
  (fitting A and B), which is not reproduced here.
- **Two distance readings, both run, neither chosen by agreement** (the
  units of k are not printed):
  - **R_angstrom:** r_ij in ångström, the PDB's own unit;
  - **R_bohr:** r_ij in bohr.

  A failure whose ratio is 1.889 would name the other reading, so both are
  reported side by side.

**Typing.**
- **E models need only the chemical element**, which measurement 4 fixes
  exactly. There is no typing inference, so no typing gate applies.
- **EX models need maximum bond multiplicity per atom**, so they need bond
  orders perceived from a PDB. That perception is not attempted in this
  round: the EX models are recorded **BLOCKED on typing**, not run, and no
  best-effort typing is ever compared as if it were the paper's.

**Population, per model.**
- `SOURCE_<scheme>`: the fragments present in that scheme's CSV block.
- `APPLICABLE`: those whose total charge is an integer within 1e-3 of its
  column sum and whose atoms all have a Table S1 type. Anything else is
  excluded and listed with its reason; a denominator never shrinks silently.

**Tolerance, computed and not judged.**
- `tau_linearized_i` = 5e-7 (the CSV's 6 dp half-unit) + Σ_p |∂q_i/∂p| · ½ ·
  10^(−d_p), over every Table S1 parameter p with d_p its printed decimals
  (A and B 6 dp, k 3 dp). It is a first-order estimate and is called that.
  - The sensitivities are exact, not finite differences: the system is
    solved once with one right-hand side per parameter.
- `envelope_i` = max |q_i(p′) − q_i(p)| + 5e-7 over samples p′ drawn in the
  full rounding box, plus every single-parameter ± corner.
- **The gate is τ_i = max(tau_linearized_i, 1.1 × envelope_i)**, and the
  ratio envelope/linear is reported with its maximum and median.
- **Amendment, cost-driven, registered now rather than discovered later.**
  The round 3 plan asked for 2000 samples on every fragment. At the measured
  3.5 s per pass that is about 2 h per model and 48 h for 24, which is not
  run. Instead:
  - the sample is 500 draws (seed 20260915) on a stratified subset: the
    smallest, the median-sized and the largest fragment;
  - every single-parameter ± corner is evaluated on those three;
  - for fragments outside the subset, τ_i uses the subset's measured maximum
    ratio envelope/linear as a scale on `tau_linearized_i`;
  - the subset, the ratio and the scale are printed in the result, so the
    approximation is visible wherever it is used.

**Amendment 2.8-A1 (2026-09-15): the sample count drops from 500 to 100,
on a measurement, before any model verdict exists.** The envelope on
fragment 1000023 (546 atoms, E-MPA/6-31G\*/gas, R_angstrom) is **identical at
25, 50, 100, 250 and 500 draws**: max envelope 2.346e-01 e, max ratio 25.0 in
every case. The maximum comes from the single-parameter ± corners, which are
always evaluated, and not from the random draws, so the draw count cannot
change a τ. 100 is kept (four times the count at which it had already
saturated) because that measurement is on one fragment. The seed is unchanged.

**What that envelope says about the gate, recorded with it:** τ is dominated
by **k's printed precision**. k is given to 3 decimals, so k = 0.006 ± 0.0005
is an 8% uncertainty, while A and B carry 6. A gate of this width is therefore
weak on its own, and the result must report the **distribution of |Δ|**
beside the pass count: an agreement far inside τ is the evidence that the
parameters are the source's, and an agreement merely inside τ is not.

**Oracle and classes.**
- Per atom: **reproduced** if |q_model − q_printed| ≤ τ_i, else **failed**.
- Per fragment × model: **REPRODUCED** when every applicable atom is
  reproduced, else **PARTIAL** with the failing count and the largest |Δ|.
- Per model: REPRODUCED when every applicable fragment is; else PARTIAL;
  INCONCLUSIVE if the applicable population is empty.
- Universal mapping: REPRODUCED → REPRODUCED, PARTIAL → PARTIAL, the EX
  models → BLOCKED, an excluded fragment population → PARTIAL-COVERAGE.

**Scheme agreement, reported beside it and never a gate.** R_avg, RMSD_avg
and D_avg per model against its own QM scheme's column, compared with Table
S2's printed values (3 dp; internal validation is the grey diagonal, e.g.
E-MPA/6-31G\*/gas against MPA/6-31G\*/gas is 0.975).
- **The paper contradicts itself on R_avg:** the prose calls it "the squared
  Pearson's correlation coefficient", and its eq 7 prints the unsquared
  form. So the definition is **identified, not assumed**, from a closed list
  fixed now: {Pearson r, r²} × {σ with ddof 0, ddof 1}, per molecule then
  averaged over molecules. Whichever reproduces Table S2's printed values is
  recorded as the source's convention, and all four are printed.
- Every row names the exact QM scheme ("MPA/6-31G\*/gas"), never "QM charge".

**Instrument tests, before the corpus run.**
- The system reproduces a hand-solved two-atom case.
- Total charge is conserved to 1e-9 on every solve.
- Exact sensitivities agree with central differences on one fragment to 1e-6.
- The PDB reader's element rule reproduces Table 1's element counts, and the
  CSV alignment check (measurement 4) is a test.
- A permuted atom order gives the same charges, per atom.

**Mutations:** k applied in bohr while distances are in ångström; the B sign
flipped; X̄ fixed to the harmonic mean instead of solved; the total charge
forced to zero; τ using only the linearised term; the Ca type dropped to
carbon's parameters.

**Verdict:** counts per class per model, plus the reading (R_angstrom or
R_bohr) that reproduces, if either. **GO-CANDIDATE** (a separate src
pre-registration for per-model keys such as
`eem_ionescu2013_e_mpa_631gs_gas`) only if a reading reproduces every
applicable fragment of at least one model; otherwise PARTIAL, INCONCLUSIVE or
BLOCKED with the reason.

### 2.9 EQeq (Wilmer 2012) on its own 12 MOFs, under a reconstructed parameter table

Pre-registered 2026-09-15, **before any EQeq charge is computed here**. Claim
kind: **IMPLEMENTATION REPRODUCTION under a named parameter substitution** —
the source's own charges, on the source's own structures, from its equations,
but with a parameter table we rebuild rather than the one it shipped.

Source: `wilmer2012` plus its supporting information; the substitute parameter
sources are `moore1970` (ionisation potentials) and `andersen1999` (electron
affinities). The electrostatics are transcribed in
`benchmarks/charges/periodic/FEASIBILITY.md` §2 and are not restated here.

**Measured first (input side only; no EQeq charge computed, nothing compared).**
1. **The corpus is held and identified.** 12 MOFs × 4 charge sets, each file
   carrying its cell and per-atom charges. All 12 atom counts equal the paper's
   Table 1 and every EQeq column sums to zero (FEASIBILITY §8).
2. **Charges print to 3 decimals** (e.g. `1.211`, `-0.968`), so the printed
   half-unit is **5e-4 e**.
3. **Both substitute tables extract.** Moore's Table I comes out in reading
   order as Z, element, then successive potentials in eV (H 13.598; C 11.260,
   24.383, 47.887, 64.492, …), integers being Z and decimals being potentials,
   so the parse is unambiguous. Andersen's **Table 3** (pp. 16–17) is
   "Summary of recommended atomic electron affinities" with EA in cm⁻¹ and eV.
4. **Moore's five printed stages are exactly enough** for the paper's charge
   centres: a centre at Q\* needs I(Q\*) and I(Q\*+1), and the deepest centre
   used is V(+4).

**The parameter table, and why it is a substitution.** EQeq's χ and J come from
successive ionisation energies about a chosen charge centre (SI eqs 57–58):
χ_Q\* = (I_{Q\*+1} + I_{Q\*})/2 and J_Q\* = I_{Q\*+1} − I_{Q\*}, with I_0 the
electron affinity. `ionizationData.dat` was not held when this was designed, so
the table is rebuilt from Moore and Andersen and **labelled a reconstruction in
every row of the result**. A per-atom miss therefore has two candidate causes —
the implementation and the table — and the design below is what separates them.

**The file arrived later (2026-09-16, in the correction's SI) and the
substitution was kept**, because it is now the stronger position: the
reconstruction was shown identical to the shipped table value for value, so the
table is no longer one of the two candidate causes rather than merely being
labelled as one.

**Settings, from the paper and its S3, not chosen here:** ε_R = 1.67 (so
K = 14.4/ε_R eV·Å), hydrogen's I_0 set to −2 eV rather than its measured
+0.754, no spherical cutoffs, and charge centres neutral except the metals at
their oxidation states (Mg +2, V +4, Co +2, Ni +2, Cu +2, Zn +2, Pd +2).

**Readings, all run, none chosen by agreement.**
- **The lattice sum:** direct summation over L = 2 (the paper's 5 × 5 × 5) and
  L = 3 (7 × 7 × 7). **Ewald is deliberately not implemented**: its 2π
  convention is unresolved (FEASIBILITY §2), and the paper states that at
  7 × 7 × 7 "charges from both Ewald and direct summation methods were
  identical", so the direct sum at L = 3 is the paper's own bridge between them.
- **The derivative factor c** on the pair terms: SI eq 62 prints K/2 while
  differentiating the ½ΣΣ energy of eq 12 gives K. Both **c = 1** and
  **c = ½** run, as A1's two bond-hardness readings did for Nistor.

**Oracle and classes.** The EQeq column of each structure file, to its printed
3 dp.
- Per atom: **reproduced** if |Δq| ≤ 5e-4.
- Per MOF × reading: **REPRODUCED** if every atom is, else **PARTIAL** with the
  failing count and the largest |Δ|.
- **The distribution is reported beside the count** (median, and the fraction
  within 5e-4, 5e-3, 5e-2), because a reconstructed table cannot be expected to
  land on the printed precision and the shape of the miss is the evidence.
- **Two independent diagnostics that do not depend on our table being theirs:**
  - the per-MOF mean |Q − Q_REPEAT| against the paper's **Table 2** (EQeq
    column, 0.11–0.24): computed from the REPEAT file beside each EQeq file;
  - charge conservation (Σq = 0) and the correlation against their EQeq column.

**Instrument tests, before the corpus run.**
- The extracted table reproduces printed values (H 13.598, C 11.260, Zn's
  first two, and Andersen's C 1.262 118 eV).
- A two-atom cell solved by hand.
- Σq = 0 to 1e-9 on every solve.
- The lattice sum converges: L = 1, 2, 3, 4 on one MOF, reported.
- The orbital-overlap term vanishes at long range and is finite at r → 0.

**Mutations:** ε_R dropped to 1; hydrogen left at its measured +0.754; every
charge centre forced to 0; the lattice sum reduced to the home cell; c
exchanged; the electron affinity's sign flipped.

**Verdict.** Counts per class per reading, with the distribution.
- **GO-CANDIDATE** for a src pre-registration of a periodic charge calculator
  only if some reading reproduces the printed charges of at least one MOF, or
  agrees at a level the parameter substitution can account for **and** matches
  Table 2's independent mean deviations.
- Otherwise PARTIAL or INCONCLUSIVE, naming which of the two causes the
  evidence can and cannot separate.

**Amendment 2.9-A1 (2026-09-15): three scan conventions, and what happens to an
element with no bound negative ion.** Found while building the table, before any
EQeq charge was computed.
1. **Moore prints oxygen's symbol as the digit "0".** A symbol-matching parse
   drops the row silently, and oxygen is in all 12 MOFs. The table is therefore
   keyed on the atomic number, with the symbol taken from Z and the printed
   token only checked against it.
2. **This typesetting renders a minus sign as "2"** — "cm21" is cm⁻¹, "Pm2" is
   Pm⁻. **Nitrogen's affinity prints as "20.07", meaning −0.07 eV**, and read
   literally it would make nitrogen bind an electron it does not bind. Nitrogen
   appears in 4 of the 12 MOFs.
3. **The parse validates itself.** Andersen prints every affinity twice, in
   cm⁻¹ and in eV, related by the conversion on its own page
   (1 eV = 8065.544 77 cm⁻¹). A row is accepted only when the two agree to
   1e-3 eV, and that check is what decides whether a leading "2" was a minus
   sign rather than a digit. Extracted values for the corpus: H 0.754204,
   C 1.262120, N −0.07, O 1.461110, V 0.525, Co 0.6633, Ni 1.157160,
   Cu 1.235780, Pd 0.562140 eV.
4. **Magnesium and zinc print "<0"** — no bound negative ion, so no number. In
   this corpus both are used only at a positive charge centre (+2), where the
   affinity is never read. **If a structure ever needs an affinity the source
   does not give, the check REFUSES for that structure** rather than
   substituting zero, and says which element.

### 2.10 QTPIE: the LAMMPS fingerprint, and the Table 2.2 exponent recomputation

Plan Track B (2026-09-16). **Read-only: nothing is installed or run from
LAMMPS.** Two parts, registered here before either result exists.

**Part 1: pinned retrieval.** The LAMMPS commit is chosen first, and the docs,
source and example `gfile` are read *from that commit*:
`lammps/lammps` develop `c8bd2ae5927ee236a8892dbd51c18a92cc9c33cf`
(2026-09-15). The newest commit touching the fix is `1ef4515` (2026-08-24).
SHA-256 as retrieved:
- `src/REAXFF/fix_qtpie_reaxff.cpp` (1,264 lines):
  `1877aa3ffb95b3417775f930def67aa5868ecdc0d5a37b985b0e3087f4354502`
- `src/REAXFF/fix_qtpie_reaxff.h`:
  `48230d9ca7686ff4b22a7265a2dd20ace19264c085a732fad83a17b731a7be51`
- `doc/src/fix_qtpie_reaxff.rst`:
  `ad5fdfc0db6b2a49a5c2d4ab8a5b4b206cc9ccce614d103092cf2348e371bc00`
- `examples/reaxff/water/gauss_exp.txt`:
  `b2c416b00d611d8a811a4b1b163bcc0e724eb776208697514f9385660ff1e2c1`
- For comparison only, `fix_qtpie_reaxff.cpp` at `stable_22Jul2025_update6`:
  `a1170527e471dbb8c17453e29e2dcde718f122d0e620df4ad0f069f996d55163`
  (it differs; the pinned develop commit is the one classified).

Each fingerprint row (plan B.2) is classified **same / different / not stated**
against a named source, from those files and the thesis, and the component and
model verdicts are derived from the rows, never asserted beside them.

**Part 2: the exponent recomputation, registered because of a discrepancy
found while reading.** Chen's thesis prints two versions of the same numbers:
- Table 2.2 (p 69): 16 Gaussian exponents to 4 decimals, H **0.5434**;
- Appendix A (p 201, `GaussianExponent`): the same 16 in the same element
  order to 15 digits, H **0.534337523756312**.

The other 15 round from the appendix to the table exactly. Hydrogen does not:
0.5343 against 0.5434, the pattern of a transposition. LAMMPS's example gfile
uses 0.5434. **Which one is Chen's fit is not assumed. It is recomputed from
§2.4's own definition:**

- **The fit (eqs 2.13 and 2.16):** for each element, α* minimises
  ∫₀^∞ (J_G(R; α) − J_S(R; ζ, n))² dR.
  - J_S is the Coulomb integral between two normalised ns Slater densities
    with Table 2.2's Slater exponent. Evaluated with the shipped
    `charge_equilibration.coulomb_pair_integrals`, in hartree and bohr.
  - J_G is taken from Appendix A's `sGTOCoulInt(a, b, R)`,
    erf(√(ab/(a+b)) R)/R with a = b = α, because the printed eq 2.14 does not
    survive text extraction.
  - n is Table I's principal quantum number (Chen's "From Ref. 20" Slater
    exponents are, value for value, the ζ column of Rappé–Goddard Table I as
    shipped in `QEQ_TABLE_I`).
- **The error column (eq 2.17):** MAE = max over R ≥ 0 of |J_G − J_S|,
  evaluated at the appendix exponent and at the table exponent.

**Reading gate, decided on the 15 non-hydrogen elements before hydrogen is
read.** The reading is VALIDATED only if all 15 of these hold:
(a) α* agrees with the appendix value to a relative 1e-4;
(b) α* rounds to Table 2.2's 4 decimals;
(c) the MAE at the appendix value rounds to the table's error column (5 decimals).
If any fail, the result is **READING-NOT-VALIDATED** and hydrogen is reported
without a verdict.

**Hydrogen verdict, only under a validated reading:**
- **TABLE-TRANSPOSITION:** α*_H is within a relative 1e-4 of the appendix value
  0.534337523756312, and not of 0.5434. The table's H exponent is then a
  misprint, and LAMMPS's example gfile inherits it.
- **APPENDIX-DIFFERS:** α*_H is within a relative 1e-4 of 0.5434 and not of
  the appendix value.
- **NEITHER:** otherwise, reported with α*_H.

Hydrogen's error column (0.01696) is about ten times every other element's. It
is reported beside both exponents' MAE and is **not** used to decide the
verdict, since which exponent it was computed at is exactly what is unknown.

**What it licenses.** It is a statement about a source table and one example
file. It does not change a shipped number (nothing ships QTPIE), and it does
not by itself make LAMMPS's model "not source-equivalent": the gfile is user
input, and the fix reads whatever exponent it is given.

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

**Correction (2026-09-15, check 2.7):** check 4's last sentence is wrong. The
coordinate column is displaced against the atom rows; nothing is known to be
missing. See 2.7's measurements and section 3.7.

### 3.2 Mathieu Table I, the EEM (EQ) row (2026-09-14)

**Fixture.** `mathieu2007_eq.csv` holds 194 molecules and 3,064 atoms. SHA-256
(LF): `c63f1dd1f5f0195917377118ce1abca9e3ae5dee84d79a69d6c1674f605c28f7`.

**Population.** All 194 molecules are in scope: every one is H/C/N/O/F, and
every Mulliken sum is 0 within 0.01. None is excluded, and the shipped EEM
refuses none. Atoms: C 965, H 1,812, N 92, O 133, F 62.

| Metric | Reconstructed with `ce.eem_charges` | Table I | Within the pre-registered bound? |
|---|---|---|---|
| R² C | 0.9619 | 0.96 | **yes** |
| R² H | 0.8139 | 0.81 | **yes** |
| R² N | 0.9535 | 0.95 | **yes** |
| R² O | 0.6641 | 0.66 | **yes** |
| R² F | 0.3574 | 0.36 | **yes** |
| R² All | 0.9727 | 0.97 | **yes** |
| Δq, eq 15 as printed | 0.004453 | 0.0668 | **no** (strict-xfail stop record) |

**Diagnostics.**
- **√Δq = 0.066734,** 6.6e-5 from the printed 0.0668, just outside the
  ±0.00005 rounding bound. So the table's number is almost certainly eq 15
  **with** a square root, which the printed equation lacks. That is inferred,
  and not adopted.
- **The all-atom RMS first guessed in step 3 is 0.043558,** nowhere near the
  table, which confirms the correction was needed.

**What it means.**
- The shipped EEM reproduces all six of Mathieu's R² values on 3,064 atoms of
  an independent 194-molecule set.
- The label stays **RELATED EEM IMPLEMENTATION**, as the frozen rule requires,
  because Mathieu's text never states the Coulomb kernel. But the
  reproduction is itself evidence that his EEM and the shipped one are the
  same model.
- **Mutation check:** η in place of 2η on the diagonal turns seven of these
  tests red.

### 3.3 Oda–Hirono pre-flight: BLOCKED before any ORCA run (2026-09-14)

The source-method identity half of the decision rule was settled first, from
the paper, and it decides the outcome by itself.
- **Atom labels: established.** Fig. 1 (rendered) draws α- and β-D-idose with
  every label on a chair:
  - C-1…C-6, ring O-18 (C1–O18–C5);
  - O-14/15/16/17/19 on C1/C2/C3/C4/C6;
  - H-7…H-13 on carbon, H-20…H-24 on the hydroxyls.

  Numbering follows Merz, J. Comput. Chem. 1992, 13, 749. The stereo agrees
  with PubChem's records: CID 7098664 α-D-idopyranose (2S,3S,4R,5R,6R) and
  CID 7018164 β (2R,3S,4R,5R,6R).
- **Charge scheme: not what 2.3 froze.** The "HF-ESP" charges are cited to
  ref 1, Singh & Kollman, J. Comput. Chem. 1984, 5, 129: Merz–Kollman point
  shells. Check 2.3 pre-registered CHELPG, a different fitting grid, so a
  CHELPG run cannot establish identity.
- **Verdict under the frozen rule:** Table 9 cannot be a per-atom oracle, and
  the conformer spread cannot change that. The pre-flight is **not run**, and
  would have cost hours of HF optimisations. Oda–Hirono stays **HOLD**.
- **What would unblock it:** a Singh–Kollman fit, meaning Merz–Kollman shells
  (1.4/1.6/1.8/2.0 × van der Waals radii) with the ESP evaluated from the HF
  density (for example ORCA's `orca_vpot`) and a constrained least-squares fit.
  That fit is a method of its own, and would need its own pre-registered check
  against a published Singh–Kollman example before it could judge Table 9.


### 3.4 Fixtures, the EEM baseline, and check 2.5: the shipped EEM on TS (2026-09-15)

**Fixtures.** `mathieu_eem_check.py --freeze` read both EPAPS directories. The
EQ CSV came out byte-identical to 2.2's. SHA-256 values (LF):
- `mathieu2007_eq.csv`:
  `c63f1dd1f5f0195917377118ce1abca9e3ae5dee84d79a69d6c1674f605c28f7`
- `mathieu2007_eq_manifest.csv`:
  `d932da7a8166cc57c20eda4fa8b38c86636eb835f978658abadee97892b1e0af`
- `mathieu2007_ts.csv` (55 files, 1,085 atoms):
  `c17f74d0d0e8e99c059ad1941356bb7361cb981afefff1f798a29e5dc603c40d`
- `mathieu2007_ts_manifest.csv`:
  `37f75e9c6f1ced540112bd60550a46444b0f3452478d94ce889f813251b887c7`

Each manifest lists:
- README.TXT with its SHA-256;
- the deposit's ZIP as NOT HELD;
- for every .xyz, its SHA-256, atom and element counts, and exact decimal
  sums of its Mulliken, coordinate and absolute-charge strings.

The tests check every CSV against its manifest. The population is exactly as
pre-registered: every element is supported, every (file, atom) key is unique,
and **nothing is excluded in either set**.

**EEM baseline (2.4d): holds.** Through `population()`, the shipped EEM on EQ
gives C 0.9619, H 0.8139, N 0.9535, O 0.6641, F 0.3574 and All 0.9727, 2.2's
values exactly.

**Check 2.5, EEM (TS): PARTIAL, fluorine the only miss.**

| Metric | n | Reconstructed R² | Table I | Interval | Gate |
|---|---|---|---|---|---|
| C | 327 | 0.9574 | 0.96 | [0.955, 0.965) | pass |
| H | 592 | 0.8597 | 0.86 | [0.855, 0.865) | pass |
| N | 15 | 0.9282 | 0.93 | [0.925, 0.935) | pass |
| O | 146 | 0.8639 | 0.86 | [0.855, 0.865) | pass |
| F | 5 | 0.3499 | 0.36 | [0.355, 0.365) | **miss by 0.0051** (strict-xfail stop record) |
| All | 1,085 | 0.9581 | 0.96 | [0.955, 0.965) | pass |

**Diagnostics, non-gating.**
- **Δq:** 0.007128 as printed and √Δq 0.084425, against 0.0847. That is
  2.8e-4 off, a larger gap than EQ's 6.6e-5.
- **Per-atom errors:** All MAE 0.0382, RMS 0.0549, max 0.2484.
- **TS fluorine is five atoms:**
  - reference charges −0.5012 to −0.1318;
  - SSE 0.05225 and SST 0.08038;
  - **leave-one-out R² from 0.2566 to 0.6145**.

  Removing any single atom moves the value across a range fifty times the gate
  width.
- **TS nitrogen (n = 15):** leave-one-out 0.9137–0.9495.

**What it means.**
- The shipped EEM reproduces five of Mathieu's six EEM (TS) values on 1,085
  transition-state atoms it was never fitted to.
- The one miss is a five-atom statistic, which one atom can move by ±0.2.
  It stays a recorded miss, not a pass.
- Check 2.5 does not feed 2.4.

### 3.5 Check 2.4: Mathieu SQE model B (2026-09-15)

The frozen order was followed: sources, pre-registration (commit b6704eb),
instrument, EEM baseline and 2.5 (section 3.4), then the corpus.
Outputs, all written by `mathieu_sqe_check.py`:
- `mathieu_sqe_atoms.csv`: 4,149 rows, one per deposited atom;
- `mathieu_sqe_metrics.csv`;
- `mathieu_sqe_structures.csv`;
- `mathieu_sqe_eq13.csv`;
- `mathieu_sqe_rounding.csv`.

**Instrument (2.4e): all 21 tests pass; every mutation is caught.**
- **Test 1 confirms 2.4a's derivation numerically.** The assembled A and b
  equal the finite-difference Hessian and gradient of the independent eq 8
  energy. **The literal eq 13 matrix equals −(that Hessian) + 2 diag(K)**,
  and eq 12's B equals the gradient itself rather than its negative. Eq 8
  governs, as pre-registered.
- **Mutations** (literal eq 13 as solver, Θ removed, η for 2η, `<=` at the
  cutoff, M's sign flipped): each turns a test red.
- **Independence:** a planted 0.5× cutoff in `pairs` is caught by test 1
  while `energy_eq8` keeps its own pair rule. When `energy_eq8` is made to
  call `pairs`, test 1 passes with the bug in place.
- **Two departures from 2.4e, recorded rather than hidden:**
  - **Dissociation uses nitramide.** The EQ set has no methanol, so test 7
    uses H2N–NO2 with NO2 moved along N–N. The NO2 fragment's charge:

    | Step | SQE | EEM | Pair-graph components |
    |---|---|---|---|
    | 0 Å | −0.1731 | −0.1851 | 1 |
    | 1 Å | −0.0100 | −0.2310 | 1 |
    | 2 Å | 0.0000 | −0.2264 | 2 |
    | 3 Å | 0.0000 | −0.2207 | 2 |

    SQE goes to zero continuously, through the penalty, before the graph
    splits. EEM violates fragment neutrality at the separated geometry.
  - **The step study cannot show convergence.** Eq 8 is exactly quadratic in
    q, so central differences carry no truncation error. The step study
    therefore shows agreement at every step, not convergence toward the
    analytic value.

**Corpus (2.4d): PARTIAL on EQ and on TS, so the model verdict is HOLD.**

| Set | Metric | n | SQE R² | Table I SQE | Interval | Gate | EEM R² (same atoms) | Table I EEM | Discrimination |
|---|---|---|---|---|---|---|---|---|---|
| EQ | C | 960 | 0.9676 | 0.97 | [0.965, 0.975) | pass | 0.9620 | 0.96 | STRICT |
| EQ | H | 1,799 | 0.8686 | 0.85 | [0.845, 0.855) | **miss** | 0.8118 | 0.81 | STRICT |
| EQ | N | 91 | 0.9621 | 0.96 | [0.955, 0.965) | pass | 0.9534 | 0.95 | STRICT |
| EQ | O | 133 | 0.6663 | 0.67 | [0.665, 0.675) | pass | 0.6641 | 0.66 | STRICT |
| EQ | F | 62 | 0.3359 | 0.35 | [0.345, 0.355) | **miss** | 0.3574 | 0.36 | STRICT |
| EQ | All | 3,045 | 0.9770 | 0.98 | [0.975, 0.985) | pass | 0.9727 | 0.97 | STRICT |
| TS | C | 317 | 0.9601 | 0.96 | [0.955, 0.965) | pass | 0.9565 | 0.96 | not applicable |
| TS | H | 575 | 0.8933 | 0.88 | [0.875, 0.885) | **miss** | 0.8616 | 0.86 | STRICT |
| TS | N | 15 | 0.9538 | 0.95 | [0.945, 0.955) | pass | 0.9282 | 0.93 | STRICT |
| TS | O | 143 | 0.8793 | 0.89 | [0.885, 0.895) | **miss** | 0.8617 | 0.86 | STRICT |
| TS | F | 5 | 0.3460 | 0.16 | [0.155, 0.165) | **miss** | 0.3499 | 0.36 | AMBIGUOUS |
| TS | All | 1,055 | 0.9708 | 0.97 | [0.965, 0.975) | pass | 0.9578 | 0.96 | STRICT |

- **Seven of twelve gates pass.** Every miss is a strict-xfail stop record.
- **The misses are not all in one direction.**
  - Hydrogen comes out more correlated than printed, on both sets: 0.8686
    against 0.85, and 0.8933 against 0.88.
  - EQ fluorine and TS oxygen come out less correlated than printed.
  - TS fluorine is nowhere near its printed 0.16; it sits beside the EEM
    value. On five atoms its leave-one-out R² runs from 0.003 to 0.786.
- **Discrimination is STRICT wherever it applies, except TS F.** The model
  moves every other metric from the EEM value toward Table I's SQE value,
  even where it overshoots.
- **Model discrimination** (SQE − EEM on the same atoms): EQ H +0.0568, EQ F
  −0.0214, TS H +0.0316, TS O +0.0176, TS N +0.0256.

**Two structures were invalid, against an expected 0.** That is a
strict-xfail stop record in its own right. Both fail the frozen residual
limit, and each is excluded from both arms:
- **EQ pentylamine (19 atoms).** One pair close to its van der Waals cutoff
  has a K that makes σ_max 6.0e9. The relative `rcond=1e-10` then cuts at 0.6
  Hartree and **discards three genuine modes**, leaving a residual of 2.5e-2
  Hartree/e. With rcond 1e-14 the residual falls to 2.5e-6, and a charge
  moves by 0.0174.
- **TS ts33 (30 atoms).** Residual 2.7e-9 Hartree/e with σ_max 5.3e7. This
  is roundoff, just over the limit; no mode is discarded.
- **Instrument test 10 did not cover this.** It passed on synthetic cases,
  but a relative cutoff is relative to the largest singular value, which here
  is a diverging penalty rather than chemistry.
- **The 1e-9 limit is at roundoff for this unscaled system, so which
  near-limit structures pass depends on the machine** (measured after the run,
  2026-09-15).
  - Many structures have condition numbers of 1e7–1e9 and residuals of
    1e-10 to 3e-9: ts29 4.4e-10, isopropylpropylamine 3.5e-10.
  - Forcing different OpenBLAS kernels on one machine gives ts33 a residual
    of 1.6e-9 (Prescott), 2.0e-9 (Sandybridge) and 2.7e-9 (Zen and the
    default).
  - #108's second CI run produced a different EQ population from this
    machine and from its first CI run.
  - In every case the gate pattern and both verdicts were the same, and
    pentylamine (2.5e-2) was always excluded.
  - The tests therefore pin the gates, the classes and pentylamine exactly,
    and the R² values to 1e-3.
  - Scaling the system, as below, removes the dependence. It is not adopted.
- **Post hoc diagnostic, not adopted:** a Jacobi-scaled solve (D^−½ A D^−½,
  condition numbers 4.3 and 10) gives residuals below 1e-11 for both. With
  both structures included that way, the EQ and TS gate outcomes are
  unchanged: EQ H 0.8704, TS O 0.8814. The two exclusions do not drive any
  miss.

**Diagnostics, non-gating.**
- **Δq:** EQ 0.004275 as printed and √Δq 0.065385, against 0.0650. TS
  0.010726 and √Δq 0.103568, against 0.0952.
- **Per-atom errors:** All MAE 0.0287 (EQ) and 0.0362 (TS); RMS 0.0447 and
  0.0528; max 0.3670 and 0.3782.
- **TS nitrogen (n = 15):** leave-one-out 0.9460–0.9755.
- **Rounding sensitivity:** 312 rows (26 variants × 2 sets × 6 metrics).
  - The largest |ΔR²| is 0.0021, from η_C + 0.005 on TS O. The λ × C corners
    reach 0.0017 on TS F.
  - No perturbation closes any miss: the smallest miss, TS O, needs +0.0057.
- **Literal eq 13, as a source record:**
  - EQ: 2,833 negative eigenvalues over 194 structures, minimum −2.16
    Hartree; its q leaves eq 8's gradient as large as 2.49.
  - TS: 1,004 negative eigenvalues, minimum −2.52, gradient up to 5.41.

  It is not a usable system on any structure.
- **Prose EQ+TS values (Sec. III.B), for the shipped EEM on all 4,149 atoms
  pooled:** R² 0.9687 against "0.97", and √Δq 0.069395 against "0.0695"
  (Δq as printed is 0.004816).
  - The prose figure is consistent with a pooled EQ+TS value under the square
    root.
  - It matching the NL row's 0.0695 looks like coincidence, not a copy.
  - Diagnostic only, as pre-registered.

**What it means.**
- **This is not a reproduction of Mathieu's SQE,** so SQE is not a GO. It
  stays HOLD, and there is no implementation stage.
- **What is established:**
  - eq 8 defines a well-posed model once eq 13's sign is fixed;
  - the model does what the paper claims qualitatively: neutral fragments on
    dissociation, and better correlations than EEM on most metrics;
  - Table II's printed precision cannot account for the gap.
- **What is not known:** why hydrogen and three other correlations differ.
  Candidates include:
  - a different Coulomb kernel (Mathieu never writes it);
  - a different pair rule or radii in his code;
  - a different solver treatment of near-cutoff pairs;
  - a Table I that does not correspond to the printed parameters.

  None has been tested, and none is adopted. `verstraelen2011`'s point that
  charge-only fits are ill-conditioned is a reason not to go looking for
  parameters that fit.
- **The solver policy failed on two real structures.** Any future SQE
  calculator needs a scaled or penalty-aware solve, with its own
  pre-registration.


### 3.6 Check 2.6: the named-cause study for SQE (2026-09-15)

Claim kind: SOURCE REPRODUCTION of Table I's aggregates, under each variant.
Run order in git: 2.6's pre-registration and instrument first, the driver fix
(46d44a2) after a crash that produced no numbers, then this run.

**Verdict per arm** (local / universal):

| Arm | Population | √Δq at printed vs 0.067 | S | G gates | Verdict |
|---|---|---|---|---|---|
| V0-unscaled | 247 / 249 | 0.068364 MISS | INCONCLUSIVE | EQ 4/6, TS 3/6 | PARTIAL / PARTIAL |
| V0-scaled | 249 / 249 | 0.068210 MISS | INCONCLUSIVE | EQ 4/6, TS 3/6 | PARTIAL / PARTIAL |
| V2-scaled (Ohno–Klopman) | 249 / 249 | 0.105699 MISS | INCONCLUSIVE | EQ 0/6, TS 0/6 | INCONCLUSIVE / INCONCLUSIVE |

**Oracle S, the point of the whole check.** Mathieu p. 6 says C and λ came from
a Powell minimisation of eq 15, so if our model were his, (115, 0.816) would be
stationary for our Δq.

- **At the printed point the scaled Hessian is INDEFINITE:** eigenvalues
  −7.37e-04 and +0.1999, condition infinite. The registered trust gate
  therefore fails and the class is **UNRELIABLE**, so neither "stationary" nor
  "not stationary" is claimed there. (Its scaled gradient is ‖g̃‖ = 7.28e-03,
  and Δq = 4.6527e-03.)
- **Powell from the printed point walks away and downhill**, to
  **C = 56.77 eV, λ = 0.81474**, where Δq = 4.4770e-03 — 3.8% below the
  printed point's. That end point is outside the pre-registered neighbourhood
  (±2 eV, ±0.01), so it is not "near" the printed point by the registered rule.
- **λ is what agrees.** The end point's λ differs from the printed 0.816 by
  0.16%, while C differs by 51%. Whatever separates our model from his is
  therefore in the C term rather than in λ — a narrowing, not a diagnosis.
- **The lowest point found is itself not certifiable:** at (56.77, 0.81474) the
  finite-difference gradient estimates disagree across the registered step
  study, so it too classes UNRELIABLE.
- **Five end points ARE verified minima** (positive definite, trusted, ‖g̃‖
  below g_tol), all at λ ≈ 1.40–1.45 with Δq = 4.81570e-03 and eigenvalues of
  order 1e-13 — a flat plateau, and **worse** than the printed point.
- Registered S verdict: **INCONCLUSIVE** for every arm.

**What the study rules OUT as the cause.**
- **Not the numerical arm.** Scaling changes the validity of exactly 2 of 249
  structures (pentylamine, one TS); on COMMON_VALID the pooled Δq differs by
  1.6e-05 and R²(All) by 6.4e-05.
- **Not the Coulomb kernel form.** V2's Ohno–Klopman kernel is much worse:
  √Δq 0.1057 and 0 of 12 gates.
- **Not model B's parameters alone.** The model C diagnostic misses as well:
  √Δq 0.0808 against the printed 0.0583, R²(All) 0.9688 against 0.98. A second
  printed model failing the same way points at something systematic in the
  implementation or in what the paper leaves unwritten, not at one parameter
  set.
- **V1 (the OpenChem bond-graph reconstruction) does not discriminate.** On its
  applicable EQ subpopulation (90 of 194 structures) **both** V1 and V0 score
  0 of 6 gates, so the comparison says nothing about splits: INCONCLUSIVE, and
  TS remains structurally undefined (NOT APPLICABLE).

**Oracle G, unchanged from 2.4** (V0-scaled): EQ C 0.9676/0.97 pass, H
0.8686/0.85 miss, N 0.9621/0.96 pass, O 0.6663/0.67 pass, F 0.3359/0.35 miss,
All 0.9770/0.98 pass; TS C 0.9601/0.96 pass, H 0.8933/0.88 miss, N 0.9538/0.95
pass, O 0.8793/0.89 miss, F 0.3460/0.16 miss, All 0.9708/0.97 pass.

**Oracle T (Table III's 24 atoms): 3 pass, 21 fail** at ±5e-4, on every arm.
The failures are dominated by fluorine and nitro compounds, which is where G's
fluorine correlation also misses.

**What is established, and what is not.** Δq at the printed point is a real
number on a stated population, and the printed point is not where our Δq is
minimised. Because the Hessian there is indefinite, the registered instrument
declines to certify *why*, and no parameter was refit to close the gap. The
cause is narrowed to the C term and to something shared by models B and C.

Result files (LF-normalised SHA-256, first 32 hex):
- `mathieu_sqe_population.csv` (1,439 rows): `b82038cd2341cab73ea0e5918a74b6dd`
- `mathieu_sqe_surface.csv` (5,351 rows): `f869bbb3aa1648a14a3ce65262cd5e3f`
- `mathieu_sqe_powell.csv` (47 rows): `b03133e8bf5a45f9c5d1ea5b7a27171f`
- `mathieu_sqe_stationarity.csv` (50 rows): `9713f62bed6407cac55685a60c285929`
- `mathieu_sqe_causes.csv` (203 rows): `75734d823bc9332dbc82fb9fb1962be6`
### 3.7 Check 2.7: Nistor SQE on recovered correspondence (2026-09-15)

Claim kind: IMPLEMENTATION REPRODUCTION, on geometry recovered by the one-row
rotation (amendments A2 and A3). Run order in git: A3 and the module 216aecf,
instrument tests 4a9faca, then this run.

**Instrument, before the run.**
- **Kernel:** equals an independent Fourier-space integral (the exact
  transform of an ns Slater density, numpy Gauss–Legendre) to 5.4e-13 eV
  worst case over H–H, C–O, Si–Si and H–Si at R = 0.5–6 Å, against the 1e-9 eV
  gate. mpmath is not installed, and this route shares nothing with the
  gamma-function closed form, so it replaces the registered mpmath integral.
  R = 0 intercepts: 20.83 (H–H), 8.99 (C–O) and 6.76 (Si–Si) eV, matching the
  figure.
- **Normalisation checksum:** H, O and Si reproduce the printed A. Carbon
  computes to 1.0847 against a printed 1.084; ζ = 1.6175, which also prints as
  1.618, gives 1.0839. The printed A is therefore inside ζ's rounding.
- **Parameter sets:** all five pages, 206 rows, re-parsed from a fresh text
  dump and compared in order, with 0 mismatches.
- **Tests:** `tests/test_nistor_sqe_instrument.py`, 19 tests.
  - The split-charge solve equals a brute-force minimisation of eq 4, written
    in loops with re-transcribed parameters, for i, iii and iv under both
    readings.
  - Method i equals an atomic QE solve.
- **Mutations: 6 of 6 red.** They cover the pair sign, ζ left in Å⁻¹,
  symmetry classes without ESP, symmetric Δ, the readings exchanged, and a
  two-row rotation accepted. The registered "S_real branch" mutation has
  nothing to test, since A2 removed that branch.

**Step 1 and Step 2.**
- **Parameter set:** the all-41 set's method ii reproduces every atom of all 6
  recovered molecules. No other set reproduces any.
- **Recovery:** 6 RECOVERED-BY-ROTATION, 3 AMBIGUOUS (29, 32, 41) and 32
  BLOCKED.
  - The recovered molecules are SiH4 (6, Si–O–H), (CH3)3SiC2H5 (26, Si–C–O–H),
    and HO–CH2–OH, CH3OH, CH4 and C(OH)2(CH3)2 (33, 34, 35, 38; all C–O–H).
  - Under A2 as written: 4, 5 and 32.
  - Sensitivity (f = 1.15 / 1.35): 4 / 7 recovered.

**Step 3: nothing reproduces.** Every molecule × method × reading is PARTIAL.

| Method | Atoms reproduced (\|Δ\| ≤ 5e-5) | Molecules reproduced | Max \|Δ\| range over molecules |
|---|---|---|---|
| i | 2 / 56 (both on SiH4) | 0 / 6 | 0.0006 (SiH4) to 0.185 (38) |
| iii R_eq10 | 0 / 56 | 0 / 6 | 0.0008 (SiH4) to 0.182 (38) |
| iii R_eq14 | 0 / 56 | 0 / 6 | 0.22 (SiH4) to 4.46 (38) |
| iv R_eq10 | 0 / 56 | 0 / 6 | 0.0013 (CH4) to 0.158 (38) |
| iv R_eq14 | 0 / 56 | 0 / 6 | 0.12 (SiH4) to 8.31 (26) |

- **Readings:** R_eq14's largest miss exceeds R_eq10's on every molecule and
  method, by a factor of 3.1 (38, iv) to 1,800 (CH4, iii). This is reported,
  not used to choose a reading.
- **Sigma** (model, then printed): CH4 i 3.16 / 3.41; CH3OH i 35.30 / 37.99;
  molecule 38 iii R_eq10 28.03 / 10.93. Every value is in
  `nistor_sqe_molecules.csv`.
- **A post-hoc diagnostic, not a class change:** coordinate rounding cannot
  explain the misses.
  - The fixture prints coordinates to 4 dp (1,477 of 2,067 have a nonzero
    last digit).
  - The linear envelope of each charge over ±5e-5 Å on every coordinate is at
    most 8e-6 e (SiH4), 3e-5 e (CH4) and 3e-4 e (the larger molecules).
  - Each molecule's largest miss is 68 to 2,900 times its largest envelope.
- **What it says:**
  - SiH4 and CH4 come within 2e-3 e under method i and iii R_eq10 (CH4 also
    iv R_eq10; SiH4 iv misses by 0.023), but not within the printed precision.
  - The four larger molecules miss by 0.02–0.18 e under method i and both
    R_eq10 readings. That includes method i, which has no bond-hardness term.
  - So a difference that method i already shows lies in the atomic model, the
    kernel convention or the recovered geometry. Which of these is not tested
    here, and nothing was refit.

**Program verdict: PARTIAL**, universal status PARTIAL. GO was unreachable
before the run (A2). No molecule is REPRODUCED-ON-RECOVERED-CORRESPONDENCE,
so no SQE src pre-registration follows from this check.

Result files (LF-normalised SHA-256):
- `nistor_recovery.csv`:
  `1679f036c3d451255853c2d3ab7d78958c6129ca55dda0dde8927659b16216f4`
- `nistor_sqe_molecules.csv`:
  `e085f61942b56c888ef8e3cc9c3a33771745eff7626b975cded59e45de1c607c`
- `nistor_sqe_atoms.csv`:
  `be80290213ed8119e91b64ae8125b7574de5a778b8bf91407e0aa926fd17f4d6`

### 3.8 Check 2.8: Ionescu 2013's E models reproduce (2026-09-15)

Claim kind: **IMPLEMENTATION REPRODUCTION**, in the domain of protein
fragments. Run order in git: pre-registration a7563cd, fixtures 7a69e33 and
b545044, implementation and mutations eb6563e, amendment 2.8-A1 735172b, then
this run.

**Verdict: REPRODUCED**, universal status REPRODUCED, for all 12 E models.

| Reading | Model × dataset rows reproduced | Verdicts |
|---|---|---|
| **R_angstrom** | **36 / 36** | REPRODUCED ×36 |
| R_bohr | 0 / 36 | PARTIAL ×36 |

- **Every applicable atom of every applicable fragment** is within τ under
  R_angstrom: 40,142 atoms on a full training set, 802 on insulin, 998 on
  ubiquitin, for each of the 12 models.
- **The distribution, which is the real evidence** (2.8-A1: τ is wide because
  k prints to 3 decimals, so the pass count alone proves little):
  - the two test proteins agree at the charge CSV's own printing precision —
    **median |Δ| 2.2e-07 to 2.6e-07**, against a 5e-7 half-unit;
  - the training sets agree less exactly but still far inside τ: median |Δ|
    5.3e-06 to 6.4e-05, **max |Δ| 0.0004** over all 36 rows.
  - **That difference between the test proteins and the training set is
    real, scheme-dependent (PCM rows are tighter than gas), and is not
    explained here.** Nothing was refit, and no mechanism is adopted.
- **R_bohr fails outright** — 34 of 998 atoms on ubiquitin, median |Δ| 0.1 —
  so the distance unit is ångström. It was not chosen; both readings ran.

**Populations, per scheme (the CSV's own blocks):** 41, 40 or 38 fragments,
with 0, 1 or 3 excluded as "absent from that scheme's block". No fragment was
excluded for any other reason: **calcium and sulfur are parameterised and were
included**, so there is no PARTIAL-COVERAGE here.

**The metric convention, identified and not assumed.** The paper's prose calls
R_avg the squared Pearson coefficient; its own eq 7 prints the unsquared form.
Computed both ways on all 36 rows, **R² matches Table S2's printed R_avg in
every row** (0 rows differ by more than 0.0015), as do RMSD_avg and D_avg.
Example (E-HiI/6-31G\*\*/PCM, training set): R² 0.9625 against 0.962, RMSD
0.1281 against 0.128, D 0.0949 against 0.094. So Table S2 prints the squared
coefficient, and the paper contradicts itself.

**Instrument:** 18 tests, all six registered mutations red. The calcium
mutation survived its first run because no test had a calcium atom in it; a
synthetic case was added rather than the mutation retired.

**EX models: BLOCKED on typing**, as registered. They need maximum bond
multiplicity per atom, so they need bond-order perception from a PDB; no
best-effort typing was compared.

**Program verdict: GO-CANDIDATE.** A reading reproduces every applicable
fragment of all 12 E models, which is the registered condition. A src
pre-registration would carry per-model keys (e.g.
`eem_ionescu2013_e_mpa_631gs_gas`), the protein-fragment domain limit, and
the fact that these parameters are fitted to QM charges of *protein
fragments* — not a small-molecule claim.

Result files (LF-normalised SHA-256):
- `ionescu_eem_models.csv` (72 rows):
  `daf4cee368f80087c2d127b6f4059b052962921cc9a00f1a97f9969b14b48347`
- `ionescu_eem_atoms.csv` (109,646 rows; the subset fragments):
  `2fe90adac0de67387c13cad1f71695ac12d80b5ba06105666f9324e1f1e937ce`
- `tests/fixtures/charges/ionescu2013/table_s1.csv`:
  `f6f687d8d4906b7052055700d83c835d4803c3fc42ebb0dc985a4064f14829f3`
- `tests/fixtures/charges/ionescu2013/table_s2.csv`:
  `4896075257d422abbd9fb251f8eb43e1e552822a7e67387779edac98f9b183da`

## 4. EEM beyond H/C/N/O/F: the source taxonomy (2026-09-15)

Each record carries the same fields: **kind**, what its charges are, whether
its **source population is recoverable** (exact / partial / independent
substitute only / unavailable), and **what evidence its oracle could give**
(implementation reproduction, scheme reproduction, or independent usability
only).

### 4.1 Ionescu et al. 2013 — the one exact route

- **Kind:** element extension (adds S and Ca) plus 24 published models.
- **Charges:** MPA, NPA and iterative Hirshfeld at HF/6-31G\* and 6-31G\*\*,
  in gas phase and PCM, on 41 protein fragments plus insulin and ubiquitin.
- **Population recoverable: exact.** The structures (PDB), the per-atom QM and
  EEM charges (CSV) and the parameters (Table S1) are all held.
- **Evidence:** implementation reproduction. Check 2.8 runs it; see 3.8.

### 4.2 Vařeková et al. 2007 — NCI DIS: independent substitute only

- **Kind:** element extension (S, F, Cl, Br, I, Fe, Zn) with the κ kernel.
- **Charges:** HF/STO-3G Mulliken, computed by the authors.
- **The sets, transcribed from its Table 1** (NCI DIS half only; the CSD half
  needs a licensed database and is unavailable):

  | Set | Molecules | Elements | Printed position |
  |---|---|---|---|
  | nbeg | 2000 | C, O, N, H, S | ID between 1 and 3162 |
  | nmid | 2000 | C, O, N, H, S | ID between 300 000 and 314 026 |
  | nend | 2000 | C, O, N, H, S | ID between 705 000 and 712 703 |
  | nall | 6000 | C, O, N, H, S | nbeg + nmid + nend |
  | nhal | 4000 | + Br, Cl, F, I | ID between 106 498 and 114 688 |

- **Population recoverable: independent substitute only**, for two measured
  reasons, neither of which is about availability:
  1. **The membership is not printed.** Each 2000-molecule set is drawn from a
     wider id range (nbeg: 2000 of 3162), and the paper does not say which
     ids. No list of members can be recovered from what is printed.
  2. **The geometry source is gone.** The paper's structures are NCI DIS 3D
     coordinates predicted by CHEM-X. The public NCI Open Database's 3D
     coordinates are generated by CORINA (release notes for the 1999, 2000,
     2003 and 2012 releases, read 2026-09-15). A CORINA structure for the same
     NSC number is a different geometry, so byte identity is not demonstrable
     even for a molecule that is certainly the right compound.
- **Availability, sampled 2026-09-15** (metadata only, nothing downloaded):
  8 ids evenly spaced across each printed range, queried against PubChem's
  `DTP.NCI` substance source: nbeg 8/8, nmid 4/8, nend 5/8, nhal 6/8 present
  (23 of 32). Presence there is an identity cross-reference, not the 2007
  geometry.
  - The CACTUS resolver returned HTTP 500 for two NSC probes the same day.
    That is a server fault and is recorded as evidence of nothing.
- **Evidence:** independent usability only. Its STO-3G Mulliken oracle would
  have to be recomputed by us, on structures we generate, and could never be
  called a reproduction of the paper.

### 4.3 The rest, recorded without new work

| Source | Kind | Charges | Population | Evidence available |
|---|---|---|---|---|
| `jiroušková2009` | element extension (S, Br, Cl, Zn) | B3LYP and HF/6-31G\* MK | **unavailable**, searched 2026-09-15 (below) | none |
| `bultinck2004` | same equations, AIM charges | B3LYP AIM, CHNOF | **partial**: the SI is a drawn list of molecule identities with no coordinates | identities only; AIM needs a tool not held |
| `ouyang2009`, `chaves2006`, `njo1998` | modified models / other elements | NPA, Mulliken, STO-3G+MK | not assessed; context only | context |
| `ionescu2012` | application (Bax/Bak profiles) | — | the fragment archive is not held | none |
| `verstraelen2009` | EEM and SQE on 500 molecules (H, C, N, O, F, S, Cl, Br) | its own | data not held | context for Tracks 1 and 5, never a gate |

**The Jiroušková 2009 search, run 2026-09-15, and its result: UNAVAILABLE.**
The round 3 plan required this before the record could say "unavailable".
- The paper's own data statement: 380 training, 116 validation and 111
  comparative molecules (16,841 atoms in the training set), "stored in SDF
  format". **It prints no molecule identities** -- no NSC numbers, no CSD
  refcodes, no names -- so even a recovered file could not be checked against
  a membership list, and no list can be rebuilt from the paper.
- The held SI is 3 pp of histograms.
- The page the paper cites for its software,
  `http://ncbr.chemi.muni.cz/~n19n/eem_abeem`, does not respond (connection
  failure on http and https).
- The Internet Archive holds **4 URLs** under that path, all captured in 2007
  and 2008, before this paper: the redirect itself, `email.htm`, `licence.htm`
  and `manual.htm`. None is data.

So the status is unavailable, on a search rather than on an assumption. It is
not reopened without a new source.



### 3.9 Check 2.9: EQeq REPRODUCED on all 12 MOFs (2026-09-15)

Claim kind: IMPLEMENTATION REPRODUCTION. **Verdict: REPRODUCED** — every atom
of all 12 MOFs, identical to the published charge at its printed precision.

| | |
|---|---|
| MOFs reproduced | **12 / 12** |
| Atoms identical at 3 dp | **3,452 / 3,452** |
| median \|Δq\| before rounding | 1.6e-04 to 3.5e-04 |
| max \|Δq\| before rounding | 0.0015 |
| mean \|q − q_REPEAT\| | equals the paper's Table 2 on all 12 |

**The oracle was confirmed first, independently of our model.** Matching atoms
by minimum-image position, the deposited files' own mean |EQeq − REPEAT|
reproduces every cell of the paper's Table 2 (MIL-47 0.112 against 0.11,
IRMOF-3 0.238 against 0.24, all twelve).
- **The four charge files of a MOF do not share an atom order**, and their
  coordinate lists are permutations. Index-by-index, MIL-47 reads 0.47 against
  a printed 0.11; position-matched (an exact bijection, worst residual 0.000 Å)
  it reads 0.112.

**The parameter substitution was never the cause.** The shipped
`ionizationdata.dat` holds the values this reconstruction produced — H 0.75420,
C 1.26212, N −0.07000, O 1.46111, Moore's potentials verbatim — so 2.9-A1's
three OCR conventions were read correctly, including the one where the scan
prints a minus sign as "2".

**What the first run found, and why it mattered.** Before the source code was
held, the check ran against the equations as printed and came out PARTIAL:
metals reproduced to 0.001–0.010 but bonded light atoms missed by up to 0.3,
and **SI eq 64 as printed made agreement worse than omitting the term
entirely** (IRMOF-1 max 0.216 against 0.030). Five readings of it were tried
and none reproduced. That is what the ambiguity was worth: the check refused to
adopt the best-agreeing variant, reported PARTIAL, and named the one formula it
could not read.

**Amendment 2.9-A2 (2026-09-15): the published source code settled it.** It
arrived in the SI of the paper's own *Correction* (doi 10.1021/jz301439a),
whose entire content is that these files "should have been included in the
original paper". Four things it fixes, none of which is derivable from the
article:
1. **The orbital term's first coefficient is 2a, not a**, with a = J_km/k —
   the article's eq 64 prints J_km/K. This alone moved IRMOF-1's max |Δq| from
   0.216 to 0.0012.
2. **The constants are k = 14.4 exactly and a "Coulomb scaling parameter"
   λ = 1.2**, so every pair term carries λk/2 = 8.64 eV·Å. Reading the article
   alone gives 14.399645/1.67 = 8.6226, which is 0.2% different.
3. **Direct summation is the default**, not Ewald, which retires the 2π
   question for these numbers.
4. **The published charges are post-processed**: rounded to 3 digits, and if
   the rounded set no longer sums to zero, the FIRST |Σq|×1000 atoms in file
   order are shifted by 0.001. Replicating that is what takes the agreement
   from "99% of atoms identical" to all of them; without it, 2 of 12 MOFs
   reproduce exactly and the rest sit at 79–99.4%.

**A discrepancy between the article's prose and its own code, recorded:** the
paper says two overlapped atoms of one element interact with an energy "equal
to the chemical hardness". With the code's lambda = 1.2 that limit is 1.2 J,
not J; the stated property holds only at lambda = 1.

**Settled by the run itself, and reported rather than tuned:**
- **the lattice sum is NOT fully converged, and the published charges are the
  paper's own L = 2 (5 x 5 x 5)**: MIL-47 moves by up to 5.4e-04 going to
  L = 3, which changes the third decimal of 10 of its 72 atoms, so only 86% of
  them still match at L = 3; IRMOF-1 moves by 8e-10 and none change. The paper
  calls that step negligible, and for MIL-47 it is visible at the precision the
  charges are printed to. (This corrects a "converged" reading taken before the
  source code was held, on the model that misread eq 64.);
- hydrogen's ad hoc I₀ = −2 eV is confirmed (IRMOF-1 median 0.008 against
  0.102 with the measured +0.754);
- the Ewald self term at η = 50 Å makes agreement worse, so it is not silently
  present in the published numbers;
- c = 1 beats c = ½ on every MOF, so eq 62's printed K/2 is not the derivative
  behind these charges;
- charge conservation holds to 4e-16 per cell.

**The shipped charge-centre file does NOT reproduce the published charges, and
the paper's prose does.** `chargecenters.dat` lists Mg 2, V 4, Co 2, Ni 2,
Cu 2, Zn 2 and **Zr 4 — with no palladium**, while the article's text names
"Pd: +2". Measured on Pd(2-pymo)₂: with Pd at +2 every atom matches; with Pd
at 0, which is what the file implies, **2.4% do** (its palladium reads +0.591
against a printed +0.780). So the charge centres are an input that the paper's
two artifacts state differently, and any calculator built on this must show
which centre each element was given rather than implying the structure
determines it.

**The 2011 prior report does not settle eq 64 either** (`wilmer2011`, Chem.
Eng. J. 171, 775, read 2026-09-15). It gives the two-centre Coulomb integral in
two *alternative* forms — a 1s Slater solution (its eq 6) and a Gaussian one
(eq 7) — and not the 2012 SI's eq 64; the code's own comment beside the term
says "other functional forms are OK too". So the published source is the
operative definition of this model, and that is now recorded rather than
inferred.

**Program verdict: GO-CANDIDATE.** A periodic charge calculator now has an
exact oracle and a fully resolved model. Shipping one is a separate src
pre-registration, and it must carry: the reconstruction's provenance (the
parameter table is ours, from Moore and Andersen, even though it agrees with
theirs value for value), the identity fields in
`benchmarks/charges/periodic/FEASIBILITY.md` §5, the disorder-resolution rule
that corpus never needed, and the charge-centre table, which is an input and
not a property of the structure.

Result files (LF-normalised SHA-256, first 32 hex):
- `eqeq_mofs.csv`: `1ee2d60c401b8854a9b8be2412050697`
- `eqeq_atoms.csv` (3,452 rows): `ee74343ee5e8bd46744ed62730e88718`

### 3.10 Check 2.10: the LAMMPS fingerprint, and Table 2.2 does not recompute (2026-09-16)

Run order in git: registration 3ac8fb6, then this. Nothing from LAMMPS was
installed or executed.

#### Part 2 first: READING-NOT-VALIDATED, and why no reading could pass

`qtpie_exponent_check.py` writes `qtpie_exponents.json`. **The reading gate
passed 0 of 15**, so hydrogen gets no verdict, as registered. Every fitted
exponent is far from both printed versions, and every recomputed error column
is 4 to 160 times the printed one (O: 0.0236 against 0.00167).

**A property of the instrument then explains the failure without a second
arm.** J_S(R; ζ, n) = ζ·f_n(ζR) and J_G(R; α) = √α·g(√α R), so the eq 2.13
minimiser must satisfy **α\*/ζ² = c_n, one constant per n**, under *any*
reading of these forms: printed eq 2.14 (erf √α R) or the appendix routine
(erf √(α/2) R), density exponent 2ζ or ζ. Measured, it holds to six digits
(n = 2: 0.206263 for Li, C, N, O and F alike). **Table 2.2 does not have this
property:** α/ζ² for n = 2 runs Li 0.957, C 0.282, N 0.268, O 0.236, F 0.273;
for n = 3, Na 0.504 down to Cl 0.136. So no reading of §2.4 as written, with
Table I's ζ and n, can produce Table 2.2. Whatever did (a finite R range in
fixed units, another ζ or n, a weighting) is not stated in §2.4. **No
alternative arm was run**, because the argument covers every reading the
rendered page suggested, and running them anyway would be fishing.

Read from the rendered page (p 67), because the registration relied on
extracted text:
- eq 2.14 prints J_G = erf(√α R)/R, which is **not** the appendix's
  `sGTOCoulInt` at a = b (erf(√(α/2) R)/R). The thesis text and its own code
  differ by a factor of two in the exponent convention.
- eq 2.15's integrand prints |r|ⁿ e^(−ζ|r|) per centre, while its prefactor
  (2ζ)^(4n+2)/((2n)!)² normalises r^(2n−2) e^(−2ζr) densities. The printed
  formula is not self-consistent either.

**Hydrogen stays unresolved.** The table prints 0.5434 and the appendix holds
0.534337523756312, while the other 15 agree. That is a fact about two
printings, not a finding about which is the fit. LAMMPS's example gfile uses
the table's value.

#### Part 1: the component fingerprint

Three sources: Chen's QTPIE **as published** (2007; thesis eq 2.9, "a scaled
overlap integral of the ns-type orbitals which are used to represent the
screened Coulomb interaction ... as was used in the QEq model"); **Chen's own
Gaussian implementation**, thesis Appendix A (`qtpie.f`, `DosGTOIntegrals`);
and **LAMMPS** at the pinned commit (source, docs, `gauss_exp.txt`) with Lalli
& Giusti 2025.

| component | Chen 2007 as published | Chen Appendix A (Gaussian) | LAMMPS `fix qtpie/reaxff` | LAMMPS vs Appendix A |
|---|---|---|---|---|
| effective electronegativity, zero field | Σⱼ(χᵢ−χⱼ)Sᵢⱼ / Σₘ Sᵢₘ | same (`OvNorm` = 1/row sum; diagonal S = 1) | same (`calc_chi_eff`; j = i included with S = 1) | **same** |
| external-field term β(φᵢ−φⱼ) | not in eq 2.9 | not in the listed routine | present; β = `scale`, default 1.0; the field must apply to all atoms | **different** (an extension; the comparison is at zero field) |
| overlap kernel | ns **Slater** overlap over QEq orbitals | normalised 1s **Gaussian**, (4ab/(a+b)²)^¾ exp(−ab/(a+b) R²), bohr | the same formula (`init_olap`, Lalli A1); R in Å, α converted by `ANGSTROM_TO_BOHRRADIUS_SQ` = 3.571064831 = 1/0.529177² | **same formula** |
| which exponent the overlap uses | Slater ζ | the **same** `Basis%zeta` its Gaussian Coulomb integral uses | the gfile's, one per atom **type** | same role; the values are user input |
| exponent values | — | `GaussianExponent`, 16 elements, H 0.534337523756312 | example gfile: O 0.2240, H 0.5434 (Table 2.2 to 4 dp) | **H differs** (0.5434 against 0.5343); O agrees to 4 dp |
| what the exponents were fitted for | — | §2.4: the **Coulomb** integral J, not S | — | fitted to J; Chen's code and LAMMPS both also apply them to S |
| electrostatic kernel | Slater Coulomb integrals (QEq) | Gaussian Coulomb, erf(√(ab/(a+b)) R)/R | shielded and tapered: Tap(r)·14.4 / (r³ + (γᵢγⱼ)^(−3/2))^(1/3) eV (`calculate_H`, Lalli eq 3) | **different** |
| parameters | QEq χ, J and radii, unmodified (§2.5) | read from a parameter file in eV | χ (eV), η = 2 × ReaxFF η (eV), γ (Å⁻¹), from ReaxFF or a file | **different** source |
| overlap cutoff | — | computed while R < √(ln((π/2α_min)³ / 10⁻¹⁸) / α_min) (threshold 10⁻⁹) | neglected beyond √(2·10·ln 10 / α_min), i.e. S < 10⁻¹⁰ (Lalli A2) | **different** rule |
| Coulomb cutoff | none | erf replaced by 1/R beyond 2√(−ln 10⁻⁹ / α_min) | seventh-order taper to `cuthi` (typically 10 Å), zero beyond | **different** |
| total-charge constraint | not read | not read | q = s − u·t with u = Σs/Σt, so **Σq = 0** over the local atoms; warns when the group's initial Σq exceeds 1e-5 | code and docs say **zero**; Lalli eq 2's q_net is not what runs (their runs used q_net = 0) |
| group vs molecule | one molecule | one molecule | χ̃ sums over **all** atoms inside the overlap cutoff, ghosts and atoms outside the fix group included; no molecule boundary | **not stated** by Chen for several molecules |
| solver | pseudoinverse in charge-transfer space | linear algebra in atom space | conjugate gradient to relative residual < `tolerance`, `maxiter` default 200 | **different** (numerics, not model) |
| naming | — | — | "the same as in `fix qeq/reaxff`", which Lalli call EEM-like; not the Rappé–Goddard QEq shipped here | recorded collision |
| boundaries | molecule | molecule | periodic, with several images of one atom mishandled (docs) | **different** |
| 2019 (Kritikos) → 2024 (Lalli) | — | — | both named as contributing authors; Lalli's Appendix A describes the implementation, **not what the rewrite changed** | **not stated** (the plan assumed Appendix A recorded it) |

#### Verdicts, derived from the rows

- **OVERLAP-KERNEL: EQUIVALENT** to Chen's Appendix A Gaussian implementation
  (same formula, same unit handling, same role for the exponents), and
  **DIFFERENT** from QTPIE as published in 2007 (Slater). The exponent values
  are user input, and the shipped example's hydrogen differs from Chen's code.
- **ELECTROSTATIC-KERNEL: DIFFERENT** from both of Chen's, Slater and
  Gaussian: LAMMPS uses ReaxFF's shielded, tapered Coulomb.
- **Model verdict: NOT-SOURCE-EQUIVALENT**, naming the electrostatic kernel,
  the parameters (ReaxFF's, which by the authors' own caveat are not fitted for
  QTPIE), the cutoffs and taper, and the zero-sum constraint. The conditional
  "same formalism, Chen Gaussian overlap" verdict needed the exponent test to
  pass, and it did not.
- **QTPIE's own record is unchanged: HOLD**, on a charge-level numeric oracle.
  LAMMPS implements Chen's attenuation of electronegativity on a different
  electrostatic model, so its charges cannot stand in for QTPIE's.

**Run inventory, recorded and not executed:** commit `c8bd2ae`; the REAXFF
package; `gauss_exp.txt` (type 1 O 0.2240, type 2 H 0.5434); χ, η, γ from
`qeq_ff.water` via `params reaxff`; `cutlo` 0.0, `cuthi` 10.0, `tolerance`
1e-6 as in the example; `maxiter` 200; β 1.0; `pair_style reaxff`. Installing
it is Alex's decision.

#### Thesis read (plan B.4)

- **CHARGE_ORACLE: NOT_FOUND** in what was read: §§2.3–2.5, the chapter 3
  reformulation around eq 3.22, and Appendix A's integral, basis and parameter
  routines, plus a search for "overlap" over all 245 pages. A caption scan of
  every table and figure was **not** done in this check, so this is not yet
  the permanent "full read" the plan defines.
- **PRINTED-NUMERICAL-IDENTITY:** Table 2.1 (QEq(-H) and QTPIE
  polarizabilities identical to four decimals), unchanged and not generalised.
- **SUPPORTING-NON-ORACLE-EVIDENCE:** Appendix A's source, which settled the
  overlap row; Table 2.2's exponents, now known not to recompute from §2.4.
