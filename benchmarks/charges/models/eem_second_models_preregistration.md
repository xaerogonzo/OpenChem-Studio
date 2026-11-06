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

## 8. Amendment 1 (2026-10-30, same day, before any check ran): what the refusals do

Decided after asking what could be done about each refusal in §3. Nothing below changes a parameter,
a check or a threshold.

1. **A refusal names the other model when that model would accept the structure.** J's refusal of
   S2, C3, N3 and P2 says "model N has parameters for this type"; N's refusal of Zn says nothing. The
   message states the type and the other model's name and scheme, and never substitutes its charges.
2. **N stays on `CCD_gen_DE_RMSD_B3LYP_6311G_NPA`.** `DTP_large` has I1 and P1 as well and the same
   other types (κ 0.5548), but the paper prefers CCD_gen on quality and its quality tables were not
   readable (images), so the citable choice stays. Iodine and P(III) are refused by N, by name.
3. **Boron stays refused by both**, with a message saying no published parameters exist. A fit of our
   own (Jiroušková's procedure, about 50 boron compounds, reference charges from ORCA) is recorded in
   `docs/ROADMAP.md` as a research item, not part of this work: its reference scheme would be CHELPG,
   not the Merz-Kollman charges J was fitted to, and it would be an unpublished model.
4. **Zinc stays refused by J** (52 atoms in the paper; a metal's bonds do not fit the highest-bond-order
   typing). Salts and mixtures are handled by choosing a component with the existing component picker;
   neither model solves more than one component. Ions are accepted and flagged; unpaired electrons are
   refused.

## 5-R. C1 — RESULT (2026-10-30, run after commit 5c24ca40)

**PASS.** Model J's Table 2 was read twice: the PDF's text layer (`jirouskova_extract.py`, 12 rows) and the page
rendered at 300 dpi and typed by hand (`table2.csv`). Over 12 atom types x 2 columns x 5 printed numbers (A, its
interval, B, its interval, s) = 120 numbers, plus both κ (0.302, 0.227) and both R_avg_mol (0.941, 0.940),
**there are 0 differences**. The second reading was NOT blind (the text-layer numbers had been printed first), so
this rules out a transcription slip and not a misreading shared by both; the rendered page is the arbiter and
was read at 300 dpi. Model N's file is the machine's own: its SHA-256 and the archive's are held, its 15 atom
types are read as a table, and `.gitattributes` marks it `-text` so a Windows checkout cannot change its bytes
(the repository already does this for Geidl 2015's file `geidl2015/B3LYP_6-311G_NPA.par`, which is the
Cheminf2015 set the NEEMP paper compares against in C9).

The test (`tests/test_jirouskova_eem_table.py`, 11 tests) was mutated four ways and killed all four: one typed
digit, one text-layer digit, one digit of the NEEMP file, and a negative B.

What C1 does NOT show: that the numbers are right in the paper (a printed error would pass), nor anything about
the units; C5 is that.

## 5-R. C2, C3 and C4 — RESULT (2026-10-30, run after commit 5568396f)

Code: `src/openchem/chem/typed_eem.py` and `data/eem_second_models.json` (built by `tools/build_eem_second_models.py`);
independent solve: `eem_second_models_oracle.py`; tests: `tests/test_eem_second_models.py` (23 tests). Panel: the
census panel's single-component molecules plus a hand-built list, 77 molecules, every type of both models met at least
once (a test fails otherwise, so the pass cannot be vacuous).

**C2 — PASS.** Model J accepts 63 of the 77 molecules and Model N 72; the shipped solver and the independent one accept
**the same molecules** and agree to **1.4e-13 e** (J) and **1.9e-13 e** (N), against the registered 1e-6. Also checked in
closed form: hydrogen chloride from the two-atom system's own algebra, which pins r in angstrom (bohr would move the charge
by more than 0.005 e).

**C3 — PASS for the question registered, with one FINDING it did not foresee.**
- Atom order: charges identical to 1e-8 e under random renumbering of the first 40 molecules, both models.
- Kekulé form of an aromatic ring: all 16 aromatic molecules (benzene to quinoline and a pyridone), every form RDKit
  enumerates, **no atom's type changes and the charges agree to 1e-8 e**. Aromatic rings are NOT refused.
- **Finding: the type of a charge-separated group depends on how it is drawn.** `[N+](=O)[O-]` and `C(=O)[O-]` are the same
  molecule with the double bond on either oxygen, and the model types the double-bonded oxygen O2 and the other O1, so the
  two chemically equivalent oxygens get different charges depending on which one the drawing chose. On the panel this is
  **12 of 77 molecules, every one a nitro group or a carboxylate**, and no molecule without such a group varies (a test pins
  both halves). It is a property of the published models read as their solver reads them (the type is whatever the SDF
  bond block says), not a bug in the code, and it is the adapter's choice of bond list, not the solver's, that decides what
  the application does. **Not decided here; it needs a decision before the models are wired to a calculator.** The options:
  (a) refuse any molecule whose types vary over its resonance forms (loses nitro and carboxylate, the energetic-materials
  panel included); (b) give the equivalent atoms one type by a stated rule and say the charges are symmetrised, a choice
  neither paper made; (c) average the charges over all resonance forms; (d) accept the drawing as it comes and flag the
  molecule. Neither paper says how its own training set's nitro and carboxylate groups were drawn.

**C4 — PASS.** Every shipped B is positive in both models (so the stationary point is a minimum), and for every accepted
molecule, ions included, the charges sum to the net charge to 1e-10.

Mutation check: ten one-line breaks (off-diagonal kappa doubled, right-hand side sign, A for B on the diagonal, distance
in bohr, net charge ignored, triple bonds capped at 2, zinc allowed, the other-model name dropped, the overlap check removed,
the builder reading the HF column) were each caught by at least one test.

Not done: nothing here is reachable from a calculator or the interface, and checks C5 to C9 have not run.

## 5-L. Literature read on the nitro / carboxylate finding (2026-10-30)

Read, not decided. Nothing below changes a check or a threshold.

**Held in the library, read:**
- **Halgren 1996, MMFF94 part I** (`halgren1996_I.pdf`): its atom-type table gives the carboxylate oxygen ONE type with a
  fractional formal charge (-1/2 on each oxygen) and the nitro-group oxygen one type, so a resonance-equivalent pair is typed
  alike by design. This is the precedent for typing the pair symmetrically (option b); it is a force-field convention, not an
  EEM one.
- **Geidl 2015** (`geidl2015.pdf`): defines the type as "element type and maximal bond order", notes that an aromatic atom X is
  therefore X2, and says nothing about nitro, carboxylate or resonance. It also states that EEM parameters fitted to
  **MK and CHELPG charges are "very low quality"** on its drug-like test set (657 approved drugs), "in agreement with
  published data", while MPA, NPA and AIM are very high. **That bears on Model J, which is MK-fitted**, and is unresolved:
  Jiroušková reports a mean molecular R of 0.94 against its own MK reference. Read before J is wired to anything.
- **Jiroušková 2009**: its own discussion says some nitrogens labelled order 1 "are in fact conjugated", the one place the
  papers admit the typing is crude.
- **Bultinck 2004 and Ouyang 2009**: both note aromatic and conjugated atoms are not well described by one spherical
  parameter per atom; Ouyang separates only benzene carbons from other sp2 carbon.

**Software:** ChargeFW2's documentation (the group's own EEM code behind the Atomic Charge Calculator) labels its types
`C hbo 1`, `N hbo 2` (highest bond order), accepts SDF V2000/V3000, PDB, Mol2 and mmCIF, and says nothing about perceiving or
standardising bond orders. NEEMP's solver reads the SDF bond block as given. So in the group's own tools the type is whatever
the input drew.

**A crude look at the published numbers** (Geidl 2015's per-atom file for DrugBank molecules, held in `geidl2015_si/`;
identification by charge only, with no connectivity, so accidental pairs are included and this is an indication, not a
measurement): oxygens typed O1 and O2 whose REFERENCE charges agree within 0.01 e differ in their EEM charges by a median
of about 0.05 e and up to about 0.2 e, in the Cheminf NPA set (118 pairs), Bultinck NPA (93) and Jiroušková's own DFT set
(113). The effect is in the authors' own published figures, not introduced here.

**Not found:** any paper saying how EEM should type a resonance-equivalent pair. Searches turned up none, and the ChargeFW2
documentation's Python tutorial was not read.

### 5-L.2. What Geidl 2015's "MK is very low quality" rests on (read 2026-10-30)

Geidl cites two held papers for it; both were read.

- **Bultinck et al. 2002, part II** (`bultinck2002_II.pdf`; B3LYP/6-31G* geometries, H C N O F, EEM calibrated per charge scheme).
  Its abstract: EEM-derived Mulliken and NPA charges "are in good agreement with the ab initio values", while "electrostatic
  potential derived, and Hirshfeld charges show no good agreement". Its Table 3 gives the average absolute deviation of the EEM
  charge from the DFT charge over all atoms: Mulliken 0.03, NPA 0.05, Hirshfeld 0.02, **CHELPG 0.08 and MK 0.08 e**; for
  nitrogen MK is 0.20 e against 0.06 e for Mulliken, and the relative deviation on hydrogen is 76% (MK) and 93% (CHELPG).
  Its explanation: ESP-fitted charges are statistically under-determined and give "quite a lot of negatively charged hydrogen
  atoms" that are not chemical, and since the calibration cannot tell which are meaningful "we expect problematic behavior".
  It concludes "the ESP derived charges do not yield useful EEM parameters." This is Bultinck's OWN MK set, not Jiroušková's.
- **Svobodová Vařeková et al. 2013** (`varekova2013.pdf`): in its pKa study "MK and CHELPG provide weak QM models", and the
  EEM models "confirm previous observations that the EEM approach is not able to faithfully mimic MK charges", citing the
  Bultinck paper above. But its Table 2 also shows MK-based EEM sets (Jir2008 dft, Bult2002 mk) giving pKa models of R2 about
  0.86 to 0.91, comparable to the others: so MK-based EEM is a poor copy of MK charges and not necessarily a poor descriptor.

**What this means for Model J:** the claim is about how closely EEM reproduces MK charges (a mean absolute deviation of
0.08 e for Bultinck's set, 0.20 e on nitrogen), a different metric from Jiroušková's mean per-molecule correlation of 0.94, so
the two do not contradict each other and neither tests the other. Model J's own deviation from Merz-Kollman charges has not
been measured by anyone I found. It is what check C5 can start to measure, if a Merz-Kollman reference is computed (ORCA gives
CHELPG, which Bultinck found behaves like MK).

### 5-L.3. A second search (ChatGPT's list), checked against the documents themselves (2026-10-30)

Every claim below was checked in the file named, not taken from the search's summary.

**A published EEM that handles this.** Gilson, Gilson and Potter 2003 (`gilson2003.pdf`, J. Chem. Inf. Comput. Sci. 43,
1982) and the patent application behind it (`Patents/`, paragraphs 0046, 0055 and 0056): their quotes are accurate. The
method is fitted to ab initio electrostatic potentials, finds alternate resonance forms by a donor/acceptor algorithm,
keeps only the lowest-energy forms ("both forms of a carboxylate, but only the form of an amide that has no formal
charges"), and **averages the electronegativities and hardnesses over those forms**, so the two carboxylate oxygens end up
with equal parameters; it also says charges could instead be computed per form and then averaged. It states that only
resonance changes that move formal charge need explicit handling, "because the second type [ring Kekule changes] does not
affect atom typing", which is what C3 measured here. It says many charging algorithms special-case carboxylate. It does NOT
mention nitro groups (searched). This is the precedent for averaging the PARAMETERS of the equivalent atoms.

**How the training structures drew nitro.** wwPDB's ligand procedures (`web page downloads/wwPDB_ Processing Procedures
and Policies.htm`): "Nitro groups (R-NO2) are represented in a charge separated state (R-[N+](=O)[O-])", so the CCD
sets (NEEMP's Ccd2016, Model N) were trained on charge-separated nitro. The NCI DTP page (checked 2026-10-30) says its
old SMILES had nitro groups "lacking formal charges", edited by N(=O)O -> [N+](=O)[O-], which means the original NCI
structures drew nitro PENTAVALENT (N(=O)=O, both oxygens O2) and the page does not say what the current SD file uses; so
the DTP-trained sets (Geidl 2015's Cheminf sets; Jiroušková's set was trained on CSD structures instead) may have typed both
nitro oxygens alike. CORINA's manual (`Manuals/`) documents `-o gold` (GOLD bond-type conventions for groups with more than
one canonical form, guanidinium given) and `-o fcharges`; it does not say what nitro or carboxylate output it writes, and
nothing shows the Geidl pipeline used `-o gold`. Jiroušková's CSD structures: nothing stated.

**What RDKit does here (run 2026-10-30).** It normalises pentavalent `CN(=O)=O` to `C[N+](=O)[O-]`, and which oxygen then
carries the double bond follows the atom order of the INPUT: `CN(=O)=O` and `C[N+](=O)[O-]` give the double bond to
different oxygens of the same molecule. Likewise `CC(=O)[O-]` and `CC([O-])=O`. So in this application the same
structure written two ways gets mirror-image oxygen types and charges.

**Quality by atom type.** NEEMP (`Raček2016.pdf`): the Figure 4 caption's C3 and S2 problems are for the CHEMINF2015
sets (mpa and npa); the text names Ccd2016_mpa and Cheminf2015_npa for slight C3 or S2 issues; Ccd2016_npa, Model N, is not
named. Svobodová Vařeková 2013: "most of the outliers contain one or more nitro groups. This may be related to reported
lower accuracy of EEM for these groups", citing Bultinck 2002 part I, which says nitrogen outliers "are mainly associated
with nitro compounds" while that calibration does give them the right (positive) sign. No paper gives per-oxygen errors
for nitro or carboxylate.

**Independent test of Model J (Geidl 2015, Table 6, R2 of EEM against QM charges on its test set of approved drugs, with
the share of molecules each set covers).** Jir2008_mk (Model J's set) **0.7022** at about 71% to 80% coverage; Jir2008_hf
0.6872; Bult2002_mk 0.7844; Bult2002_che 0.7803; Bult2002_npa 0.8131; against Bult2002_mpa 0.9658 and Ouy2009 0.9655, at
about 48% to 55% coverage. Different molecules and a different statistic from Jiroušková's own mean per-molecule
correlation (0.94), so not a contradiction, but it is the only independent number for Model J and it is the lowest in the
table. Geidl's own sets exceed R2 0.93 on the same kind of test set (its abstract).

**E versus EX** (`ionescu2012.pdf`): "chemical elements only (denoted 'E')" against elements and maximum bond order
("EX", for example O1); the PLoS paper, not the 2013 one, is where the terms are defined in the text read.

**Not found by that search:** a general resonance-averaging rule in conventional EEM, QEq, SQE, PEOE or ACKS2; an atom-by-atom
error table for nitro or carboxylate oxygens; Ouyang 2009's full text (the library holds it).

**The DOI-named copy of Jiroušková 2009** added to the library (`10.1002@jcc.21142.pdf`) is byte-identical to the file
the registry already names (`Jiroušková 2009.pdf`), SHA-256 09716d51...cdac.

## 9. Amendment 2 (2026-10-30): Model J is paused; Model N goes on

Decided (Alex, 2026-10-30) after the second literature search (5-L.3).

1. **Model J stays in the repository and is not wired to anything.** Its fixtures, data, solver support and tests (C1 to C4)
   stay and keep passing. It will not be offered by a calculator, a setting or the interface until a comparison with
   Merz-Kollman charges exists. Why: the only independent test found (Geidl 2015, Table 6) gives its set the lowest R2 of
   the sets listed (0.7022, against 0.9658 for Bultinck's MPA set and 0.9655 for Ouyang's), at a different statistic and on
   different molecules from the paper's own 0.94, so it is neither confirmed nor refuted; and Model N covers every type
   Model J has except zinc, so J adds the Merz-Kollman scheme and nothing else.
2. **What would unpause it:** a measured mean absolute deviation of Model J's EEM charges from Merz-Kollman charges on a stated
   panel (check C5 starts this, but needs a Merz-Kollman reference that ORCA does not write), or a published one.
3. **Model N is the model that continues,** with its own checks (C5 to C9 apply to it; the Merz-Kollman comparison of C5 does
   not, since N is fitted to NPA charges, which cannot be computed here).
4. **Nitro and carboxylate, direction not yet decided (a proposal is `eem_resonance_typing_design.md`):** a setting (a settings page, not a hard refusal) that chooses how a
   resonance-equivalent pair is typed, with a warning when it is off. The options are those of 5-R, plus the one the
   literature adds: Gilson et al. 2003 average the PARAMETERS of the equivalent atoms over the low-energy resonance forms, which
   for this model means giving both oxygens the mean of the O1 and O2 parameters. Which is the default, and whether the
   unaveraged drawing stays available, is open.

## 10. Status of C5 to C9 (2026-10-30): DEFERRED, nothing scored

Alex asked on 2026-10-30 to stop running ORCA while his own long job is using the machine, so **C5 to C9 have not run.** What was done and learned first:

- **Two throwaway ORCA 6.1.1 jobs on water** (B3LYP/6-311G with the NPA keyword, 38 s; B3LYP/6-31G* with CHELPG, 7 s; one core, below-normal priority), their scratch removed.
  - **ORCA cannot give NPA charges here:** its output says `Environment variable NBOEXE for nbo6.exe or nbo5.exe not set! Skipping NBO-Analysis`. So Model N's own charge scheme (NPA) cannot be computed with what is installed, which confirms the statement made at registration. A free NPA program that reads ORCA's output (JANPA, from memory, not checked) would change that; it would be a download and is not assumed.
  - **CHELPG works** (`! B3LYP 6-31G* CHELPG` writes a `CHELPG Charges` block beside the Mulliken and Loewdin ones), so C5 and C7 can be run against CHELPG and Loewdin charges.
- **A confound to carry into C5 and C7 when they run:** Model N was fitted to NPA charges and Model J to Merz-Kollman ones; CHELPG is close to Merz-Kollman and is NOT NPA. So a large difference between N's sulfur or phosphorus charge and CHELPG can be the scheme and not an error, and C7's 0.5 e criterion as registered cannot tell the two apart. It is reported as registered; a refusal of S2 or P2 on that evidence alone would be a decision to take with this stated, not an automatic result.
- **The panels, registered now before any run:**
  - C5 (12 molecules, as in section 5): water, methanol, ethanol, acetic acid, acetamide, dimethyl ether, methylamine, fluoromethane, chloromethane, methanethiol, dimethyl sulfide, formamide; geometry = the MMFF conformer the EEM models are given (single points, no optimisation); the unit rule is as in section 5.
  - C7, sulfur (10): dimethyl sulfone, dimethyl sulfoxide, methanesulfonamide, benzenesulfonamide, methanesulfonic acid, methyl methanesulfonate, sulfolane, thiourea, thioacetamide, dimethyl sulfate; phosphorus (4): trimethyl phosphate, dimethyl methylphosphonate, phosphoric acid, trimethylphosphine oxide.
- **C6, C8 and C9 need no ORCA** (they are RDKit and the solvers only) and are the part that can run without disturbing the machine; C6 has no stored ORCA-optimised geometries to use, so it compares the raw embedding with the MMFF-optimised one.

## 11. C6, C8 and C9 — RESULT (2026-10-30, run after commit 0dbf8a7e; C5 and C7 still deferred)

Runner `eem_second_models_c6_c8_c9.py` (one core, below-normal priority, 100 s), result `eem_second_models_results/c6_c8_c9.json`, held by
`tests/test_eem_second_models_c6_c8_c9.py`. Resonance option `averaged` throughout. The census panel has 24 single-component molecules; the Blue Book 1,108.

**C6, geometry source: reported, no threshold.** Raw ETKDG embedding against the same molecule MMFF-optimised (no ORCA-optimised geometry is stored, so there is no third).
- Model N, 23 molecules, 642 atoms: mean |dq| **0.017 e**, largest **0.098 e**. Model J, 22 molecules, 632 atoms: mean 0.012 e, largest 0.089 e.
- By atom type (N): the nitro nitrogens move most (N2: mean 0.056 e, largest 0.095 e), then O1 and O2 (mean 0.025 e, largest 0.077 and 0.098), C1 (0.021 e), H (0.011 e),
  N1 (0.018 e); the single Cl, F and S2 atoms move 0.0005 to 0.016 e. The molecules that move most are the energetic ones and a large peptide-like one. So the model is
  sensitive to the geometry source by about 0.02 e on average and up to 0.1 e, which is the stated sensitivity and not a defect: N was fitted on unoptimised CORINA structures.

**C8, charge bound: Model N ships no bound, only the maximum.** The paper's own population is unknown, so by the registered rule nothing is shipped and the maximum is
reported. Model N covers 919 of the Blue Book and census molecules whose elements it knows (33 refused for a type, 10 for an unpaired electron); Model J covers 737 (215 refused
for a type: S2, C3, N3, P).
- Model N: 22,168 atoms, **largest |q| 2.654 e** (the sulfonyl sulfur of `O=C=NS(=O)(=O)F`), 99th percentile 0.89 e, 99.9th percentile 2.10 e.
- **The tail is exactly the types C7 is about.** Of the 129 atoms above 1.0 e, 56 are S2 and 43 are P2; of the 78 above 1.5 e, **all are S2 (47) or P2 (31)**, and all 43
  above 2.0 e are S2 (27) or P2 (16). The rest of the model tops out below 1.5 e. NPA does give large positive charges to oxidised sulfur and phosphorus, so a value near 2 e is
  not by itself an error; but it is the population where the Ionescu work found a model silently off by 1.75 e, and C7 has not run.
- Model J: 18,684 atoms, largest 1.050 e (a peroxy carbonate carbon), nothing above 1.5 e.

**C9, the models side by side (not judged).** 572 CHNO molecules (15,158 atoms) that all four models accept, on one MMFF geometry each. The four use different charge schemes
(J Merz-Kollman, N NPA, Bultinck and Ionescu E Mulliken), so a spread is partly a difference of definition and not an error.
- Mean spread (largest charge minus smallest, per atom): C 0.118 e, H 0.083 e, **N 0.294 e**, O 0.207 e; the largest for a single atom is 0.98 e (a nitrogen).
- Mean charge by element (J / N / Bultinck / Ionescu E): C -0.050 / -0.125 / -0.070 / -0.096; H +0.150 / +0.215 / +0.158 / +0.226; N -0.451 / -0.428 / -0.411 / **-0.678**;
  O -0.523 / -0.582 / -0.493 / **-0.684**. Ionescu's E model, fitted to protein fragments, puts markedly more negative charge on N and O than the other three.
- Mean absolute difference between pairs: J-Bultinck 0.024 e (closest), N-Ionescu 0.049, N-Bultinck 0.061, J-N 0.074, Bultinck-Ionescu 0.086, J-Ionescu 0.095 e.

**Still not run:** C5 (the distance unit against reference charges) and C7 (the oxidised sulfur and phosphorus survey), which need ORCA and wait for Alex's job to finish. C8's
result is the reason C7 matters most: it is the one population where Model N's largest charges live.

## 12. C5 and C7 — RESULT (2026-10-31, ORCA 6.1.1, B3LYP/6-31G*, run by `eem_second_models_c5_c7.py`; result `eem_second_models_results/c5_c7.json`, judge held by `tests/test_eem_second_models_c5_c7.py`)

References are CHELPG, Loewdin and Mulliken charges on the MMFF conformer. **NPA could not be computed here (no NBO program), so every comparison for Model N is across schemes**: a difference over 0.5 e cannot tell a scheme difference from an error.

**C5, distance unit (12 small molecules, 31 heavy atoms).** Model J: angstrom, mean error 0.141 against 0.241 for bohr, ratio 1.71, discriminated. Model N: 0.226 against 0.248, ratio 1.10, **not discriminated** (the rule stays angstrom, as the authors' code reads it). Model J is paused; N's unit rests on the code, not on this check.

**C7, oxidised sulfur and phosphorus (10 S2 molecules, 4 P2 molecules).** By the registered rule (refuse a type if the model differs from the reference by more than 0.5 e on 3 or more molecules) **the rule says refuse both**: S2 differs from CHELPG on 9 of 10 and from Loewdin on 7 of 10; P2 on 4 of 4 for both. Mean charge on S2: model 1.53 e, CHELPG 0.65, Loewdin 0.91, Mulliken 0.85; on P2: model 2.19 e, CHELPG 1.07, Loewdin 0.98, Mulliken 1.08. The largest are 2.39 e (S2) and 2.40 e (P2).

**What was shipped, and the decision left open.** Because the references are not NPA (NPA is known to give larger charges on hypervalent atoms than CHELPG), the rule's verdict is not applied as a refusal. The method is wired with a **warning** on any S2 or P2 atom above 1.5 e, saying the model ran about 1 e higher against other schemes. Whether to refuse these types instead is the owner's call; the single change is to add them to `OUT_OF_SCOPE_TYPES` in `chem/typed_eem.py`. An NPA reference (an NBO install) would settle it.

## 13. Amendment 3 (2026-11-05): the Model J measurement that Amendment 2 asked for, registered before it runs

Alex asked on 2026-11-05 to unpause Model J. Amendment 2 (2) names the condition: a measured deviation of J's EEM charges from Merz-Kollman charges on a stated panel. ORCA writes CHELPG and not Merz-Kollman; Bultinck found CHELPG behaves like MK and C5 already used it as the nearest reference, so **CHELPG is the reference and the result says so**. Fixed here, before any job runs:

- **Panel (J1):** 36 neutral closed-shell molecules not in C5's panel, drawn from the elements J types (H, C, N, O, F, Cl, Br, S): alkanes, alkenes, alkynes, aromatics and heteroaromatics, carbonyls, acids, esters, amides, nitrile, nitro, amines, halides, thiols, and four drug-sized molecules. The list is in `eem_model_j_panel.py`. MMFF conformer, B3LYP/6-31G*, CHELPG, as C5.
- **Statistic:** mean absolute difference over heavy atoms between J's charges and CHELPG, over the molecules J accepts; refused molecules are counted and listed, never dropped silently.
- **Yardstick:** the shipped default (Bultinck 2002 Part 1) against the same CHELPG charges, on the molecules both accept. J is judged against it because an absolute number means little without it.
- **Unpause rule:** J is offered as a sixth method if (a) its mean absolute difference is at most 0.15 e, (b) it is at most 1.25 times the yardstick's on the common molecules, and (c) no accepted molecule has a heavy atom off by more than 0.5 e. Otherwise it stays paused and the number is reported. It is offered with its scheme named (Merz-Kollman, compared here only against CHELPG) and its scope note.

## 14. Amendment 4 (2026-11-05): a boron feasibility probe, registered before it runs

Alex asked on 2026-11-05 to look at boron. Section 3 left a fit of our own as an unscheduled research item. This is only a probe of whether it is worth doing; **nothing it finds ships**, because Model J is paused (section 13) and Model N's NPA charges cannot be computed here. Fixed first:

- **What is fitted:** one boron type (A and B, two numbers) added to Model J's table with Model J's other types unchanged, to ORCA's CHELPG charges (B3LYP/6-31G*, MMFF conformer, as C5) of the 16 boron compounds in `eem_boron_probe.py`. A compound that needs a type Model J lacks is reported and left out.
- **Score:** leave-one-molecule-out, so no compound is predicted by a fit that saw it.
- **Feasible if all of:** the leave-one-out mean absolute error over heavy atoms is at most 0.20 e (Model J's own on its elements is 0.134, `model_j_panel.json`); the worst leave-one-out error on a boron atom is at most 0.5 e; the standard deviation of each fitted number over the leave-one-out fits is at most 10 % of its value.
- **If feasible:** a model with one fitted boron type is described, not wired, and the reference scheme (CHELPG, not Merz-Kollman) is stated. If not: boron stays refused and the reason is recorded here.

