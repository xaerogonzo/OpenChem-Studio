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
