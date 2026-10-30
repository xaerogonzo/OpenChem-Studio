# Two more EEM parameterisations (Jiroušková 2009 MK, NEEMP 2016 Ccd2016 NPA) — pre-registration

**Written 2026-10-30, before any src code and before any check below has run.** It follows
`ionescu_src_preregistration.md` (Ionescu 2013 E models, shipped) and the first EEM
(`bultinck2002a`, Open Babel's file is NOT that set). Nothing here is measured yet; §2 records
what was READ, §5 what will be MEASURED, and §6 what each outcome licenses.

## 0. Decisions taken (Alex, 2026-10-30)

1. **Two models, shipped separately, never mixed.** A parameter set is only meaningful with the
   κ and the charge scheme it was fitted with, so Cl and S from one paper cannot be added to
   another's C, H, N and O.
2. **Model J** = Jiroušková et al. 2009, **B3LYP/6-31G\* Merz-Kollman** column of its Table 2
   (`Jiroušková 2009.pdf`). Its HF/6-31G\* MK column is NOT shipped: the paper reports almost the
   same quality (mean molecular R 0.941 against 0.940) and a second set per paper is a second thing
   to explain.
3. **Model N** = NEEMP paper (Svobodová Vařeková's group, J. Cheminf. 2016), its **Ccd2016
   parameter set in `CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par`** (Additional file 6). The choice among the
   16 files is fixed here from the paper's own text, not from any score of ours: CCD_gen, not CCD_exp
   ("CCD_gen provided EEM parameter sets with better quality criteria"); DE-MIN with the RMSD
   criterion, which the paper recommends for large heterogeneous sets; NPA, because the paper says
   the MPA variant (and an older NPA set) show "slight correlation issues for S2 or C3" and the NPA
   one is not named. The LR and R² files and the DTP sets are not shipped.
4. **Boron is refused by both**: no held paper parameterises it.

## 1. The claim, and only this claim

> These are the charges that model J (or N) assigns to this structure.

Three things travel with every result, as for Ionescu:

1. **Different charge schemes.** J reproduces Merz-Kollman (electrostatic-potential) charges at
   B3LYP/6-31G\*; N reproduces NPA charges at B3LYP/6-311G. They are different quantities. Neither
   is the Mulliken charge of the shipped Bultinck model, and no result may be compared with another
   model's as if they measured the same thing.
2. **Applicability is not validation.** The code can evaluate any structure whose atom types are
   parameterised. What the papers validated is their own populations (J: 380 CSD organics; N: CCD
   ligands, which NEEMP generated with CORINA and did NOT optimise). Our conformers come from RDKit
   and ORCA, so the geometry is a stated difference (§5 C6).
3. **Atom types carry bond order.** A result also says which type each atom got.

## 2. What was read (the sources, not measurements of ours)

- **Equation** (J's eq 3; NEEMP `src/eem.c`, `fill_EEM_matrix_packed` and `calculate_charges`):
  unknowns `q_1..q_N, χ`; diagonal `B_i`; off-diagonal `κ / r_ij`; last column `-1`; last row `+1`;
  right-hand side `-A_i` and the total charge. This is the matrix `ionescu_system` already builds
  in `charge_equilibration.py`.
- **Units.** `r_ij` is `1 / sqrt(dx²+dy²+dz²)` of the SDF coordinates as read, with no conversion
  anywhere in NEEMP's source; SDF coordinates are in Å; Ionescu's eqs 3-4 (same group, same
  matrix) are shipped here with `r` in Å and an oracle; J states A and B are "in Pauling units".
  Three agreeing places, but **no paper states the distance unit in words**: §5 C5 tests it.
- **Atom type** (NEEMP `io.c`): element plus the highest bond order of any bond to the atom in the
  SDF bond block (1, 2 or 3; hydrogen is always 1). An aromatic bond type (4) makes the molecule
  invalid there, so the structure must be Kekulé. Net charge is the sum of formal charges.
- **Types present.** J: H1 C1 C2 N1 N2 O1 O2 F1 Cl1 Br1 S1 (Zn1 is parameterised but out of scope
  here: no metal is accepted). N (`CCD_gen_DE_RMSD`, κ = 0.5125): H1 C1 C2 C3 N1 N2 N3 O1 O2 F1 S1 S2
  Cl1 Br1 P2. **No iodine in N** (DTP_large has it, and is not shipped).
- **Non-convexity.** Every B read so far is positive in both sets, so the stationary point is a
  minimum; §5 C4 turns that into a test.
- Sources not read: N's per-type quality tables (images in the paper) and J's per-atom histograms.
  Nothing below depends on them.

## 3. Scope and refusals (each by name, with the type)

A structure is refused, not approximated, when: it has more than one component; an atom's
(element, highest bond order) is not a type of that model (named in the message); it has an
unpaired electron; two atoms are closer than `OVERLAP_ANGSTROM`; or the drawing cannot be
Kekulé-ised. A charged structure is accepted (net charge enters the system) but flagged: neither
paper validated ions beyond what its set contained. Model J therefore refuses sulfonyl, sulfinyl and
thiocarbonyl sulfur (S2), nitriles and alkynes (C3, N3) and phosphorus; model N refuses boron and
iodine and phosphorus other than P2.

## 4. Provenance to record at build time

- J: the 12-row table is read **twice**, once from the text layer and once from the page rendered at
  300 dpi (the Ionescu and Bultinck lesson: a text layer can disagree with the page), into
  `tests/fixtures/charges/jirouskova2009/table2.csv`, with a SHA-256 in the data file.
- N: the `.par` file is copied unchanged into `tests/fixtures/charges/neemp2016/`, and the data file
  records its SHA-256. This registration records the downloaded archive's as
  `d78fb0da580685bc0d950ae744103971886e6801462de2b0481d5a8584b648b9` and the chosen file's as
  `a0f20738dca189c7b89e4015e40a708b7353697afe1a9d5998ead23fd3b12e47`.
- Two sources.toml entries (`jiroukova2009`, `neemp2016`) with their verification, added when the
  code ships; the DOI guard is satisfied there, not here.

## 5. Checks, registered now and run in order

**C1 — transcription.** Every shipped A, B and κ equals its source. Exact; no tolerance.

**C2 — implementation oracle.** An independent solve of §2's system (a separate numpy script, not
the shipped function) on the 24-molecule census panel and on the hand-built molecules of the tests:
max |Δq| ≤ 1e-6 e. Different from the Ionescu bar (1e-4) because both sides are the same linear system
in double precision; a miss means a transcription or typing bug.

**C3 — typing is a function of the structure.** Charges are identical (max |Δq| ≤ 1e-8 e) under a
permutation of atom order and under every distinct Kekulé form of the aromatic molecules of the panel.
If a Kekulé form changes an atom's type the model is not a function of the structure and aromatic
rings are refused (reported with the molecule).

**C4 — convexity and charge conservation.** Every shipped B > 0 (a test on the data), and the
charges sum to the net charge to 1e-10.

**C5 — the distance unit.** ORCA CHELPG charges (B3LYP/6-31G\*, the stored or optimised conformer) for
12 small CHNOFS molecules (set fixed before the run: water, methanol, ethanol, acetic acid, acetamide,
dimethyl ether, methylamine, fluoromethane, chloromethane, methanethiol, dimethyl sulfide,
formamide) against model J solved with `r` in Å and with `r` in bohr. CHELPG is not
Merz-Kollman (both fit the ESP; they differ by a few hundredths of an e), so the test is relative:
**the unit whose mean absolute charge error over heavy atoms is smaller by a factor of at least 1.5 is
the unit.** If neither wins by that factor the unit stays Å (the three agreeing readings of §2) and
the result is reported as "not discriminated". N is not tested: NPA is not computable here.

**C6 — geometry source.** For model J and N, charges on the same 24 molecules from the RDKit
embedding, the MMFF-optimised and (where stored) ORCA-optimised conformer. Reported as the maximum and
mean |Δq| per atom type; **no threshold**, and the result is the stated sensitivity of the model to
geometry (N was fitted on unoptimised CORINA geometry).

**C7 — oxidised sulfur and P2 (the silent-error survey).** The Ionescu work found sulfur with an S-O
bond off by 1.75 e while every other check passed. For N (the only model with S2 and P2), on a panel
of 10 sulfones, sulfonamides, sulfoxides and thiocarbonyls and 4 phosphates, compare the sulfur or
phosphorus charge with ORCA CHELPG and Löwdin charges. **If |q_model − q_CHELPG| exceeds 0.5 e on 3 or more of the
molecules, S2 (respectively P2) is refused in N** and the numbers are published. 0.5 e is a stated
choice, one third of the error already seen, not a derived value.

**C8 — charge bound.** The largest |q| over the census panel and over every covered Blue Book
structure, per model. The shipped bound is that maximum rounded **up**, and is never smaller than the
largest charge on the paper's own population (unknown for N: then no bound is shipped and the
maximum is only reported).

**C9 — the models side by side.** On the molecules all of J, N, Ionescu E and Bultinck cover (CHNOF):
the per-atom spread between the four, reported, not judged. It is what a user will see if they run two.

## 6. What each outcome licenses

- **C1-C4 pass, C5 gives a unit:** the models may ship, labelled with their scheme, their types and
  C6's sensitivity, under the claim of §1.
- **C5 is not discriminated:** ships with Å and says so in the evidence.
- **C5 favours bohr:** stop; the equation is mis-transcribed or the papers use a different `r`, and
  nothing ships until the cause is found.
- **C3 fails for aromatic rings:** aromatic molecules are refused by that model.
- **C7 refuses S2 or P2 in N:** N ships without them, and its evidence says it was tested and why.
- **Any C2 miss:** stop and bring it back; it is a bug.
- **Not claimed, whatever passes:** that either model reproduces a QM charge for a molecule outside
  its paper's population; that J's and N's charges mean the same thing; that Cl or S are better
  described than by the shipped models, which have neither.

## 7. Where it plugs in (names only, no code yet)

`chem/charge_equilibration.py` (a typed system next to `ionescu_system`), `chem/geometry_charges.py`
(two method ids beside `EEM_IONESCU2013_*`), `chem/charge_evaluation.py` (labels and source keys),
`chem/data/` (one JSON per model, built by a tool as `eem_ionescu2013.json` is), the sources registry,
`docs/explainers/` for the prose, and a `docs/CALCULATOR_MATURITY.md` stage (EXPERIMENTAL until a
person decides otherwise, as every new charge model here).
