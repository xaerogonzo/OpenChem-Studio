# Open-shell molecules and hypervalent molecules: what was measured, what shipped, what is proposed

**Status: investigation done 2026-11-15; the small, verified pieces (section 5) are shipped; the rest are proposals (section 6).**
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
| O2 drawn as `[O][O]` (single bond, two radicals) | 1.316 A | triplet O2 r_e about 1.21 A (NIST CCCBDB value not re-fetched; real ORCA below gives 1.2002 for B3LYP/def2-SVP) |
| O2 drawn as `O=O` | 1.151 A | same |
| NO | 1.424 A | NO r_e about 1.15 A (ORCA below gives 1.1487) |
| O2-, superoxide | 1.316 A | |

Nothing wrong is *published* from this (an ORCA optimisation corrects it, `Oatom` and `H` need no geometry) but the 3D view and every geometry-based descriptor of a radical
rest on a force-field start. This is the open-shell counterpart of WP6 (the VSEPR table): a table of small open-shell molecules with their measured geometry would be the
equivalent, and is a proposal, not shipped.

### 3.3 Quantum runs: the multiplicity (real ORCA, B3LYP/def2-SVP `Opt`, input from the application's own `build_input`)

`benchmarks/open_shell/orca_spin_states.py` reproduces this table.

| Species | Multiplicity | Result |
|---|---|---|
| O2 | 3 | -150.144946 Eh, r = 1.2002 A (experiment about 1.21) |
| O2 | **1** | -150.081721 Eh, r = 1.2014 A: **+39.7 kcal/mol, finishes, no message** (a closed-shell RKS state; the a1Dg state is about 22 kcal/mol above the triplet, from memory, so this is not even that) |
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

Mutation checks run: each of 7 edits (Joback, Hansen, both Hueckel rules, the parity refusal, the spin note, the engine default) fails 1 to 5 tests when reverted.

## 6. Proposed work packages, by value and risk (not started; each needs the owner's go-ahead)

| # | Package | Why | What it takes | Risk |
|---|---|---|---|---|
| OS1 | **Store the multiplicity** with the structure (a `spin_multiplicity` field, project format bump, `None` = derive) and read `M  RAD 1/2/3` from the molblock text ourselves because RDKit conflates 1 and 3 | a drawn singlet carbene is rewritten as triplet today; the default would stop being a guess | a field on `MoleculeModel`, codec and project-file migration, an editor control, tests | medium (file format) |
| OS2 | **Known-ground-state table**: O2, CH2, NH, SO, S2... drawn closed-shell (`O=O`) default to their measured ground-state multiplicity, with the source for each | `O=O` is the most likely way someone draws oxygen, and gets multiplicity 1 | a small cited table like `vsepr_geometry`'s, tests against the ORCA runs above | low |
| OS3 | **Open-shell 3D starts**: small-molecule geometry table for diatomic and triatomic radicals (O2, NO, OH, CH3, CH2, NH2...), each with a source | section 3.2: 1.316 A and 1.151 A for O2 | same shape as WP6; sources needed (below) | low |
| OS4 | **Calculator audit for radicals with oracles:** `logd`/ionisable sites, `hbond_sites`, `steric_analysis`, charge models, `solubility`: decide gate or refuse per calculator | section 3.4, TEMPO | a nitroxide pKa (not held), a decision per calculator; if more than about four calculators are gated, one registry-level `CLOSED_SHELL_ONLY` set beside `HYPERVALENT_VERIFIED_CALCULATORS` is cleaner than per-calculator code | low to medium |
| OS5 | **Psi4 parity check** (measure first) and a spin-contamination figure (`<S**2>`) in every unrestricted result, as bond dissociation already flags | an unrestricted run's quality is invisible | parse ORCA/Psi4 `<S**2>`, one fact | low |
| OS6 | Hueckel for heteroatom radicals (nitroxide, NO) with real alpha/beta parameters | currently refused | parameter set, oracle | medium, little value |
| H1 | **Hypervalent, calculator by calculator** (the owner's long-term goal): split `geometry_analysis` so the size and shape descriptors (pure coordinates) run on held structures and only the Dreiding energy refuses; then `dipole_moment` from a quantum run, where the ORCA geometry check of #600 is the oracle | the descriptors that need no valence model are the cheap ones | one calculator at a time, each with its own oracle test as in #598 | low |
| H2 | **Parameters for Cl(III), Br(III), P(V), Xe in a charge model** | the Gasteiger NaN is guarded, not solved | a published parameter set per element (a literature question) | high |

Order: **OS2 and OS5 first** (cheap, and OS2 removes the last way O2 gets the wrong spin by default), then OS1 (it makes the default a stored choice, and carries the file-format
risk), then OS3, OS4 with the nitroxide pKa in hand, H1 in parallel since it is independent, OS6 and H2 last.

## 7. Commands and what was not done

```
uv run --no-sync python benchmarks/open_shell/defect_scan.py --matrix            # section 3.4 (needs no ORCA)
uv run --no-sync python benchmarks/open_shell/orca_spin_states.py D:/ORCA/orca.exe <folder>   # section 3.3
uv run --no-sync python -m pytest tests/test_open_shell.py
```

Not done, said plainly: Ketcher was not driven (section 2); Psi4 and xtb were not run on a radical here (xtb's guard is read from its source and its fixtures); no calculator outside
the panel's 62 was checked; no literature was fetched. The O2 and NO bond lengths quoted for comparison are from memory of NIST CCCBDB and the spectroscopic literature, not
re-read for this change, and no DOI is attached to them for that reason.

## 8. Literature wanted (the owner fetches papers; the short list is also in `WANTED_NOW.md`)

* A measured pKa of a protonated nitroxide (TEMPO conjugate acid), to settle OS4's `logd` question.
* A reference for the equilibrium geometries of small open-shell molecules (NO, OH, CH3, CH2 triplet, O2) for OS3 (Huber and Herzberg, *Constants of Diatomic Molecules*; Jacox for
  radicals), or NIST CCCBDB entries as a bulk source.
