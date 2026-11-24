# Open-shell molecules and hypervalent molecules: what was measured, what shipped, what is proposed

**Status: investigation done 2026-11-15; the small, verified pieces (section 5) are shipped, and OS2 and OS5 followed the same day (section 5, items 5 and 6); the rest are proposals (section 6).**
Companion to `docs/HYPERVALENT_COVERAGE_DESIGN.md`, which covers hypervalent structures RDKit accepts (WP1 to WP7) and the held ones of #597/#598.
The question put to this investigation: the owner saw triplet O2 "have the same difficulties" as hypervalent structures. **That was an observation, not a
measurement; it was measured per layer here.**

## 1. Which assumptions held

| Assumption | Verdict | Measured fact |
|---|---|---|
| "None of the calculators work well on hypervalent molecules." | **Partly.** True for the held ones (a refusal, by design), not for the RDKit-accepted ones. | Held (ClF3, BrF3, ClF5): 8 verified calculators run, the rest refuse with `HYPERVALENT_UNSUPPORTED` (#598, WP5). Accepted (SF6, PF5, XeF4, PIDA...): NaN from Gasteiger, chirality counts, Dreiding and polarizability defects, all fixed in WP1 to WP4. |
| "Triplet O2 has the same difficulties." | **Not the same.** The failure modes are opposite. | RDKit accepts every radical tried, the ordinary path runs, and **no calculator returned NaN, infinity or an exception on 12 open-shell species** (section 3.4). The defects are numbers computed as if the molecule were closed-shell, and a quantum run whose multiplicity is never derived. |
| "The editor mishandles an unpaired-electron drawing." | **Mostly not.** | The radical electrons survive the molfile, the model, the canonical SMILES and the undo path (section 3.1). What is lost is the *spin multiplicity* (a singlet and a triplet carbene read alike), and that is not stored anywhere. |
| "Multiplicity is chosen somewhere sensible." | **No.** It stayed at 1 whatever was selected. | Real ORCA: O2 at multiplicity 1 runs, finishes and is **39.7 kcal/mol above the triplet with no message** (section 3.3). |
| "The two gaps share a cause." | **Shared at one point only:** both are structures the valence model was not built for. Nothing else is shared. | Section 4. |

## 2. What is and is not known about a drawn radical

`Chem.MolFromMolBlock` keeps `M  RAD` lines as radical electrons; `ChemistryEngine.mol_from_molblock` is that call, so a drawn radical reaches the model unchanged
(measured: `[O][O]`, `[CH3]`, `[OH]`, `[N]=O`, `[O]`, `[H]`, `[CH2]`, TEMPO, `[O][O-]` all round-trip through a molblock with the same SMILES and the same radical-electron
list). The identity is `InChI=1S/O2/c1-2` for **both** `[O][O]` and `O=O`, the same key `MYMOFIZGZYHOMD-UHFFFAOYSA-N`: **the InChI does not tell triplet O2 from a
closed-shell O=O.**

* **Multiplicity is stored nowhere.** `MoleculeModel` has no spin field; `quantum_run_request.RunChoice.multiplicity` comes from the panel's spin box, which was set to 1 and
  never derived (the help text said so). RDKit reads a molfile's singlet (`M  RAD  1`) and triplet (`M  RAD  3`) both as two radical electrons and writes triplet back, so a
  drawn singlet carbene becomes a triplet one **in the molblock itself** (measured; `tests/test_open_shell.py::test_a_drawn_singlet_carbene_is_not_told_from_a_triplet_one`).
* A drawn lone atom with no `M  RAD` line is read with its implicit hydrogens (measured: an O atom with no radical flag is water, `H` count 2). Only the radical flag keeps
  `[O]` or `[H]` an atom.
* **Not measured:** what Ketcher itself writes for its radical atom property. Every molblock here was written by RDKit, which the application also parses. Driving the live
  editor is the check that would settle it (`benchmarks/visual`, `canvas_edit`).

## 3. Measurements, by layer

All runs 2026-11-15, RDKit 2025.09.6, ORCA 6.1.1 (`D:/ORCA/orca.exe`). Commands are in section 7.

### 3.1 Editor and model: see section 2.

### 3.2 3D generation (`RDKitConformerProvider`, ETKDG then force field)

It returns a conformer for every one of the 12 open-shell species (no failure), but the starting geometry is not a geometry of the molecule:

| Species | Bond from the pool's conformer | Reference |
|---|---|---|
| O2 drawn as `[O][O]` (single bond, two radicals) | 1.316 A | triplet O2 r_e 1.20752 A (Huber and Herzberg 1979, PDF p. 511; real ORCA below gives 1.2002 for B3LYP/def2-SVP) |
| O2 drawn as `O=O` | 1.151 A | same |
| NO | 1.424 A | NO r_e 1.15077 A (Huber and Herzberg 1979, PDF p. 489; ORCA below gives 1.1487) |
| O2-, superoxide | 1.316 A | |

Nothing wrong is *published* from this (an ORCA optimisation corrects it, `Oatom` and `H` need no geometry) but the 3D view and every geometry-based descriptor of a radical
rest on a force-field start. This is the open-shell counterpart of WP6 (the VSEPR table): a table of small open-shell molecules with their measured geometry would be the
equivalent, and is a proposal, not shipped.

### 3.3 Quantum runs: the multiplicity (real ORCA, B3LYP/def2-SVP `Opt`, input from the application's own `build_input`)

`benchmarks/open_shell/orca_spin_states.py` reproduces this table.

| Species | Multiplicity | Result |
|---|---|---|
| O2 | 3 | -150.144946 Eh, r = 1.2002 A (experiment about 1.21) |
| O2 | **1** | -150.081721 Eh, r = 1.2014 A: **+39.7 kcal/mol, finishes, no message** (a closed-shell RKS state; the a1Dg state is about 22 kcal/mol above the triplet, a figure from memory that no held source was read for, so this is not even that) |
| O2 | 5 | -149.951189 Eh, r = 1.9015 A (dissociating quintet: a legal input, a different molecule) |
| CH2 | 3 | -39.086062 Eh |
| CH2 | **1** | -39.019324 Eh: **+41.9 kcal/mol, no message** |
| CH3, NO | **1** | ORCA exit 55: `multiplicity (1) is odd and number of electrons (9\|15) is odd -> impossible`, **after** the job was queued |
| CH3, NO, OH | 2 | normal |

Only xtb checks the electron count itself (`xtb_engine.check_electrons`; xtb's own run of an impossible pair exits 0). **Psi4 was not run here**, so whether `psi4_engine` guards it is
unmeasured. The two silent cases are the dangerous ones: a singlet O2 is a fine-looking number.

### 3.4 The calculator registry on an open-shell panel (`benchmarks/open_shell/defect_scan.py`, 62 registry calculators)

Species: triplet O2 (`[O][O]`), O2 drawn `O=O`, methyl, hydroxyl, NO, O atom, superoxide, CH2, NH, TEMPO, benzyl, tert-butyl, and ethanol as the control. Numbers returned per
species: 43 to 49; refused 13 to 19 (the **control refuses 16**, mostly set-up refusals such as the pKa sidecars, ADMET and the NMR database). **Non-finite values: 0. Exceptions: 0.**
That is the opposite of the hypervalent scan, where the first thing found was a NaN.

What *is* wrong, found by comparing with an independent answer and not by looking for NaN:

| Calculator | Measured before | Independent answer | Shipped |
|---|---|---|---|
| `joback_properties` | ethyl radical `C[CH2]` gave groups `{-CH3, =CH2}` and allyl radical `C=C[CH2]` gave `{=CH2: 2, =CH-}`: a vinyl CH2 the structure does not contain | the groups are defined for closed-shell molecules and are matched on hydrogen and connection counts, not on a missing valence | refused, `OPEN_SHELL` |
| `hansen_solubility` | benzyl radical got ethylbenzene's `acch2-` group | same | refused, `OPEN_SHELL` |
| `huckel_analysis`, `huckel_pi_density` | benzyl radical: a 6-atom pi system, total 8.00 beta, gap 2.00, the radical carbon left out; NO: 2 electrons where it has 3 | benzyl 7 centres, 7 electrons, **8.72 beta** (textbook; recomputed by a second diagonalisation in the test); allyl 2 sqrt(2) | carbon radical centre included (benzyl 8.72, allyl 2.83); any other radical atom refused, `OPEN_SHELL` |

Measured and **not** shipped (no independent oracle held yet, listed in section 6): TEMPO's nitrogen is counted as a basic centre by `logd` (LogD 0.96 against LogP 2.38, a 1.42
unit drop for a centre that should not ionise at pH 7.4: a nitroxide nitrogen has no free lone pair, the oracle is a measured nitroxide pKa that is not held), as an H-bond
acceptor (`hbond_sites`) and as a donor in `steric_analysis`; the EEM and Gasteiger charges ignore spin by construction and are unvalidated on radicals; `elemental_analysis`,
`mass_spectrum` (`[M]+.` 15.022927 for methyl = 15.023475 less one electron mass: correct), `oxidation_states` (methyl C -3: correct), `oxygen_balance`, `topology_*` and
`lewis_sites` (already refuses a radical on a main-group atom, `LEWIS_MODEL_DOES_NOT_APPLY`) were checked and are right or already refuse.

## 4. Where the two gaps share infrastructure and where they do not

| | Hypervalent, RDKit refuses (ClF3) | Hypervalent, RDKit accepts (SF6, PIDA) | Open-shell |
|---|---|---|---|
| Does the structure reach a calculator? | only through `allow_hypervalent`, for the 8 verified | yes | yes, always |
| Typical failure | refusal (`HYPERVALENT_UNSUPPORTED`) | NaN, wrong count, meaningless energy | **a plausible number for another molecule** |
| What caught it | `calculation_input` gate, `UnsanitizableStructureError` | `finite_guard`, `stereo_elements`, Dreiding coordination | nothing, until this change |
| Is the finite guard relevant? | yes | yes | **no** (0 non-finite values measured) |
| Does a multiplicity matter? | no (closed-shell molecules) | no | **yes, and is never derived** |

Shared: the closed refusal-kind table (`domain/refusal_kinds.py`: `HYPERVALENT_UNSUPPORTED` and now `OPEN_SHELL` are both LIMITS, and a refusal with no kind is a fault), the
"fix it where it arises" principle of the hypervalent design (section 2 there), the per-calculator oracle discipline, and `Joback`'s existing refusals for charge and mixtures that
the new one sits beside. Not shared: `UnsanitizableStructureError` and the `allow_hypervalent` opt-in (RDKit parses a radical, there is nothing to opt into), the VSEPR geometry
tables, and the verified-calculator list (a radical is not held out of the registry; it runs everywhere and some answers are wrong). The honest statement is "both are limits of
a valence model that assumes closed shells and octets", which is a reason to keep the two designs side by side and a poor reason to build one mechanism.

## 5. Shipped with this change (each with a test shown to fail without it; `tests/test_open_shell.py`)

1. `chem/open_shell.py`: unpaired electrons, the high-spin default multiplicity (unpaired plus one), electron parity, the spin note. A DEFAULT, never a fact the structure stores.
2. **Quantum panel:** selecting a molecule sets the multiplicity from its drawing, as it already did the charge (`ChemistryEngine.default_multiplicity`). A closed-shell
   drawing still gives 1, so **O2 drawn as `O=O` stays at 1 and the ground state needs 3 by hand**; the help tooltip says so. (Mutation: with the line removed 1 test fails.)
3. **`prepare_run`:** an impossible charge/multiplicity pair is refused before anything is queued (ORCA's own verdict on CH3 and NO at multiplicity 1; xtb's guard was the model),
   and a multiplicity that does not match the drawn radicals is *noted*, not refused (O2 at multiplicity 1 is a legitimate input and a wrong default). The parity check sits after
   the Fukui refusals, whose wording is more specific for the same setting. Five existing tests used butane at multiplicity 2 as a stand-in for "open-shell"; two were changed to
   a possible state (triplet butane, an anion at doublet), three needed nothing.
4. **`OPEN_SHELL` refusal** (a LIMIT) for Joback and Hansen, and for Hueckel on anything but a carbon radical centre; Hueckel now includes the carbon radical centre as a pi centre.
   Controls (toluene, ethylbenzene, benzene) are unchanged.

5. **OS2, ground states drawn closed-shell.** `TRIPLET_GROUND_STATES` (O2, SO, S2) default to multiplicity 3 and `spin_note` says so at 1. Measured in real ORCA 6.1.1
   (B3LYP/def2-SVP, optimised, triplet minus singlet): O2 -39.7, SO -29.7, S2 -23.7 kcal/mol; N2 +147.5 is the control kept out. Se2 produced no output and is not listed.
   The X 3Sigma- assignment of each is in Huber and Herzberg 1979 (section 8). This supersedes the earlier statement that `O=O` stays at 1.
6. **OS5.** ORCA results gain `orca.s_squared` (the last `<S**2>`, with the ideal value and the excess in the provenance) for any unrestricted run; a restricted run
   gains nothing. `Psi4QuantumEngineProvider.build_input` refuses an impossible electron count like xtb's. **Psi4 is not installed here**, so only the arithmetic is tested, not Psi4's own behaviour.

7. **OS1, the multiplicity stays with the structure** (done without a new field or a file-format change). RDKit rewrites a singlet carbene's `M  RAD  1` as `3`, so
   `set_structure_from_molblock` now puts the drawing's singlet code back into the molblock it stores (`molblock_keeping_spin`); `spin_from_molblock` reads the multiplicity
   from that text (singlet 0, doublet 1, triplet 2 unpaired electrons per atom) and `ChemistryEngine.default_multiplicity` prefers it. Because the information is in the
   molblock, undo, redo and the project file carry it with no migration, and the canonical SMILES and InChI are unchanged. The run note compares against the drawing's own
   multiplicity, so a drawn singlet carbene run at 1 carries none. **Changed by item 12:** the stored multiplicity can now be set from the panel. Whether Ketcher itself writes singlet, doublet or triplet codes for its radical property is still unmeasured.

8. **H1, first calculator: `geometry_analysis` on held structures (ClF3, BrF3, ClF5).** The radii and the shadow (projection areas, enclosing-circle radii, sizes) are arithmetic on
   the atoms and the van der Waals table, so they are now allowed; `geometry_analysis` joins `HYPERVALENT_VERIFIED_CALCULATORS`. Held to an independent implementation
   (`tests/test_hypervalent_geometry.py`: centroid distances; a raster of the union of discs over 300 viewing directions; a Nelder-Mead enclosing circle; the extent
   along the sampled direction), which agreed with the application's exact search within 0.2% on areas and radii and 0.4% on sizes on ClF3 and BrF3 (prototype run before
   the test). No force field is computed for a held structure (the energy fact says why), and the options that need one (a conformer policy other than Never, relaxing for
   the energy or the projections) raise the `HYPERVALENT_UNSUPPORTED` limit; before this change they raised an uncaught `AtomValenceException`. Honest note: on default
   options the held structure already got no energies (MMFF and UFF have no parameters for it and Dreiding refuses since WP3), so the explicit guard is a statement and a
   clearer message, not a behaviour change there; reverting it does not fail a test, reverting the option refusal fails 4 and removing the list entry fails 1.
   **Part 2 (the dipole), 2026-11-24.** The registry `dipole_moment` is charges times positions and its Gasteiger charges are NaN on the centre atom, so it stays refused for a held structure. A quantum run needs no charge model: `parse_dipole` reads ORCA's last "Total Dipole Moment" block and the provider publishes `orca.dipole_moment` (Debye; the magnitude is #646's, the vector in the provenance is `parse_dipole`'s). Real ORCA 6.1.1, ClF3 from the VSEPR start, B3LYP/def2-SVP, `opt`: 0.984 D, the vector 179.87 degrees from the short Cl-F bond and 92.8 from each long one, i.e. on the C2 axis of the molecule printed in the same file (the oracle for the frame; the number itself is ORCA's, and is NOT compared with an experimental dipole, none being held). `tests/test_orca_dipole.py` (real-output fixture `clf3_opt_dipole_excerpt.out`; first block instead of last and no descriptor both fail it). Compound jobs get none. Method-dependent: a different functional or basis gives a different number, and the descriptor says nothing about that.

9. **OS4, nitroxide nitrogen (done for the three calculators measured).** `BASIC_AMINE_SMARTS` (the one definition `logd`, the hERG checklist and the substructure list share) excludes an N bonded
   to a neutral one-connection oxygen (`N[OX1;+0]`), the H-bond acceptor pattern excludes it too, and `steric.find_donor` skips it. Oracle: the measured pKa of the protonated radical, -5.5 to -6.2 in
   sulfuric acid, protonation on oxygen (section 8). Measured effect: TEMPO's LogD at pH 7.4 is now its Crippen LogP (2.38) instead of 0.96; 4-amino-TEMPO keeps its one basic centre (the amine);
   TEMPOH (N-OH) and 2,2,6,6-tetramethylpiperidine are unchanged; a nitroso N=O is still a ligand donor. A nitroxide is now refused by the steric calculator as having no donor (its donor is the oxygen,
   which that calculator does not list). The nitroxide OXYGEN is not added as an H-bond acceptor: no source was read for it. `tests/test_nitroxide_basicity.py`, 3 mutations each fail 1 to 5 tests.
   Not done: the charge models and `solubility` on radicals, which have no oracle.

10. **OS3, measured geometries for small open-shell molecules.** `chem/open_shell_geometry.py` builds (not searches) eight species: O2, NO, OH, SO, S2 and Se2 at the Huber and Herzberg r_e, triplet CH2 from
   Jensen and Bunker 1988 (1.0753 A, 133.931 degrees) and singlet CH2 from Petek et al. 1989 (1.107 A, 102.4 degrees), chosen by the drawing's own multiplicity (OS1: the engine carries it on the Mol as
   `SPIN_PROP`, since RDKit cannot), and CH3 (planar, 1.079 A) and NH2 (103.4 degrees, 1.024 A) labelled 'as listed by CCCBDB'. One deterministic conformer, no energy, `ConformerModel.method`
   `open_shell_table`, its note names the source; hooked into `search_conformers` beside the VSEPR templates. Anything else (charged, substituted, an atom, closed-shell water) takes the ordinary path.
   Measured effect: O2 1.316 and 1.151 A become 1.20752, NO 1.424 becomes 1.15077. Plausibility against real ORCA B3LYP/def2-SVP optima (2026-11-15): within 0.02 A for O2, NO, OH, CH3 and triplet CH2.
   `tests/test_open_shell_geometry.py`; four mutations fail 13, 1, 2 and 1 tests (the hook fails 13).

11. **Ketcher measured (2026-11-24; `tests/test_ketcher_radical_roundtrip.py`).** The question left open in section 2: what the real editor writes. Ketcher keeps radical codes 1, 2 and 3
   through `setMolecule`/`getMolfile` for a molfile and for its KET `radical` property, so a singlet carbene drawn in the editor reaches the application as a singlet (the OS1 chain holds for
   Ketcher's own output). Its SMILES reader maps `[CH2]` to the singlet code (RDKit's default is triplet) and `[CH3]`, `[OH]`, `[N]=O`, the nitroxide to 2; the application never hands Ketcher a
   SMILES, so that is recorded only. **One real loss found and fixed:** RDKit writes no `M  RAD` line for a bond-less O or H (the radical rides in the atom line's valence field), so a singlet
   code on a lone atom vanished from the stored molblock and the default fell back to the triplet; `molblock_keeping_spin` now inserts the singlet code where RDKit wrote none. Not measured: the
   editor's own atom dialog (the Radical dropdown) driven through the page; the KET `radical` property is what that dropdown sets, per the file format, but the dialog itself was not clicked.

12. **A multiplicity a person can set (2026-11-24; `tests/test_set_multiplicity.py`).** `MoleculeModel.multiplicity` (saved only when set) holds the choice and `SetMultiplicityCommand` makes it undoable (an identity-kind change: no structure, conformer or descriptor moves). The Quantum panel's Multiplicity box writes it when the person edits the box and clears it when the value equals what the drawing implies (`ChemistryEngine.drawn_multiplicity`); selecting a molecule shows the stored value. `ChemistryEngine.stated_spin` applies the stored value only when the structure's electrons allow it (`multiplicity_problem`; ORCA exits 55 otherwise), so a later edit that changes the electron count drops a stale choice instead of failing a queued job, and it is the value `default_multiplicity`, the run note and the open-shell geometry table read (singlet or triplet CH2 follows the choice: 102.4 against 133.9 degrees). A value the electrons cannot have stays in the box, is not stored, and Run refuses it with the reason. Not done: a control outside the Quantum panel, and the Fukui and other panel buttons are unchanged (they read the box).

Mutation checks run: each of 7 edits (Joback, Hansen, both Hueckel rules, the parity refusal, the spin note, the engine default) fails 1 to 5 tests when reverted.

## 6. Proposed work packages, by value and risk (not started; each needs the owner's go-ahead)

| # | Package | Why | What it takes | Risk |
|---|---|---|---|---|
| OS1 | **DONE (stored in the molblock; no editor control yet).** Store the multiplicity with the structure (a `spin_multiplicity` field, project format bump, `None` = derive) and read `M  RAD 1/2/3` from the molblock text ourselves because RDKit conflates 1 and 3 | a drawn singlet carbene is rewritten as triplet today; the default would stop being a guess | a field on `MoleculeModel`, codec and project-file migration, an editor control, tests | medium (file format) |
| OS2 | **DONE (O2, SO, S2; cited to Huber and Herzberg 1979).** Known-ground-state table: O2, CH2, NH, SO, S2... drawn closed-shell (`O=O`) default to their measured ground-state multiplicity, with the source for each | `O=O` is the most likely way someone draws oxygen, and gets multiplicity 1 | a small cited table like `vsepr_geometry`'s, tests against the ORCA runs above | low |
| OS3 | **DONE (eight species, section 5 item 10).** Open-shell 3D starts: small-molecule geometry table for diatomic and triatomic radicals (O2, NO, OH, CH3, CH2, NH2...), each with a source | section 3.2: 1.316 A and 1.151 A for O2 | same shape as WP6; the sources are in section 8 | low |
| OS4 | **DONE for `logd`, `hbond_sites` and `steric_analysis` (section 5, item 9); charge models and `solubility` remain.** Calculator audit for radicals with oracles: `logd`/ionisable sites, `hbond_sites`, `steric_analysis`, charge models, `solubility`: decide gate or refuse per calculator | section 3.4, TEMPO | a nitroxide pKa (not held), a decision per calculator; if more than about four calculators are gated, one registry-level `CLOSED_SHELL_ONLY` set beside `HYPERVALENT_VERIFIED_CALCULATORS` is cleaner than per-calculator code | low to medium |
| OS5 | **DONE** (Psi4 only by arithmetic). Psi4 parity check and a spin-contamination figure (`<S**2>`) in every unrestricted result, as bond dissociation already flags | an unrestricted run's quality is invisible | parse ORCA/Psi4 `<S**2>`, one fact | low |
| OS6 | Hueckel for heteroatom radicals (nitroxide, NO) with real alpha/beta parameters | currently refused | parameter set, oracle | medium, little value |
| H1 | **DONE for `geometry_analysis` (radii and shadow) and for the dipole, which comes from the quantum run (`orca.dipole_moment`), not the registry calculator.** Hypervalent, calculator by calculator (the owner's long-term goal): split `geometry_analysis` so the size and shape descriptors (pure coordinates) run on held structures and only the Dreiding energy refuses; then `dipole_moment` from a quantum run, where the ORCA geometry check of #600 is the oracle | the descriptors that need no valence model are the cheap ones | one calculator at a time, each with its own oracle test as in #598 | low |
| H2 | **Parameters for Cl(III), Br(III), P(V), Xe in a charge model** | the Gasteiger NaN is guarded, not solved | a published parameter set per element (a literature question) | high |

Order: OS2 and OS5 are done; next OS1 (it makes the default a stored choice, and carries the file-format
risk), then OS3, OS4 with the nitroxide pKa in hand, H1 in parallel since it is independent, OS6 and H2 last.

## 7. Commands and what was not done

```
uv run --no-sync python benchmarks/open_shell/defect_scan.py --matrix            # section 3.4 (needs no ORCA)
uv run --no-sync python benchmarks/open_shell/orca_spin_states.py D:/ORCA/orca.exe <folder>   # section 3.3
uv run --no-sync python -m pytest tests/test_open_shell.py
```

Not done, said plainly: Ketcher was not driven (section 2); Psi4 and xtb were not run on a radical here (xtb's guard is read from its source and its fixtures); no calculator outside
the panel's 62 was checked. (The literature the first version of this section asked for has been obtained and read: section 8.)

## 8. Literature obtained and read (2026-11-15), and what it settles

Each number below was read in the held file (`docs/sources.toml` has an entry per paper with what was and was not read); an ordinary chatbot summary of these papers was checked
against them and agreed, with the corrections noted.

* **Nitroxide basicity (OS4's oracle).** The measured pKa of protonated TEMPO is **-5.5 +/- 1** (Malatesta and Ingold 1973) and **-5.8 +/- 0.3** (Sen and Golubev 2009), of 4-hydroxy-TEMPO
  **-6.2**, all in concentrated sulfuric acid (Konopko and Litwinienko 2022, Table 2, footnote 'Both values determined in H2SO4'), with protonation on **oxygen** (Voinov et al. 2024). These are
  not aqueous values, but they settle the question `logd` raised: at pH 7.4 a nitroxide is protonated to a fraction of about 10^-13, so counting its nitrogen as a basic centre (LogD 0.96
  against LogP 2.38 for TEMPO, a 1.42 unit drop) is wrong. **OS4 is now unblocked for `logd`, `hbond_sites` (the nitroxide N as acceptor) and `steric_analysis` (as donor).** No value was found
  for 4-oxo-TEMPO or di-tert-butyl nitroxide, and the -6.2 credited to Sen is not in the main text of his paper (his SI document was not opened).
* **Small open-shell geometries (OS3's table).** Huber and Herzberg 1979, ground-state r_e (A): NO 1.15077 (p. 489), O2 1.20752 (p. 511), OH 0.96966 (p. 521), S2 1.8892 (p. 577), Se2 2.1660
  (p. 595, X1 component), SO 1.481087 (p. 635); the three triplets O2, S2 and SO are X 3Sigma-, which backs OS2's table. Methylene: triplet r(CH) 1.07530 (11) A and HCH 133.931 degrees (derived
  from the printed rho_e 46.0692 (21)) with T0 = 3147 cm-1 (8.998 kcal/mol), Te = 3223 cm-1 (Jensen and Bunker 1988); singlet r_e 1.107 A, theta_e 102.4 degrees (Petek et al. 1989, abstract;
  no uncertainty is printed there); Leopold et al. 1984 revised the photoelectron splitting from at least 19.5 to about 9 kcal/mol. **Corrections to the chatbot summary:** the +/-0.0003 A and
  +/-0.06 degrees it gave for triplet CH2 are not in the paper (the fit gives 0.00011 A and 0.002 degrees on rho_e); the diatomic r_e values it credited to NIST are in Huber and Herzberg itself.
  **CH3 and NH2** (read in the saved NIST CCCBDB pages, which credit Herzberg 1966): CH3 D3h, C-H 1.079 A, HCH 120 degrees (rotational constants from Yamada et al. 1981, whose ground-state
  B = 9.57789 and C = 4.74202 cm-1 were found in the paper, and whose analysis supports a planar radical); NH2 C2v, N-H 1.024 A, HNH 103.4 degrees. These are NIST's transcriptions: Herzberg's own
  pages were not opened and the bond-length convention (r0, rs, re) is not stated, so OS3 should label them 'experimental geometry, as listed by CCCBDB' and not r_e.
* **Hueckel.** Benzyl 7 alpha + 8.721 beta (Ramachandran et al. 2008, Table 4.10, PDF p. 97), which is the application's 8.72; allyl 2 sqrt(2) beta is arithmetic.
* **Spin contamination (the `orca.s_squared` threshold).** Jensen 1990: even a small contamination can change vibrational frequencies markedly (his <S**2> of 0.785 and 0.787 are called small in
  the text); the 10% rule of thumb quoted second-hand comes from the online page of D. Young, which was NOT downloaded and is not registered. No threshold is shipped; `orca.s_squared` reports the
  value and the excess and leaves the judgement to the reader.
