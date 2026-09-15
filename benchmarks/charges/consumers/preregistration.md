# 3D charges where charges are consumed: pre-registration

Committed 2026-09-15 before any consumer number exists; git order is the
evidence. Plan: round 3, Track 2. The claim kinds are named per experiment:
SOURCE REPRODUCTION, IMPLEMENTATION REPRODUCTION or APPLICATION BENCHMARK.

## What was measured before designing

Each of these was read in the code, not assumed.
- **Every charge consumer recomputes Gasteiger on the conformer molecule, in
  conformer index space.**
  - `chem/dipole.py` (`dipole_vector`);
  - the ESP surface in `CalculatorInspectorDialog._on_surface_changed`;
  - `EspCompareWidget._render_point_charge`.

  All three hand the charges straight to a function on that same molecule
  (`electrostatic_potential_for_conformer` refuses a missing atom). So
  **none of them needs a drawing projection**; the identity question arises
  only where a per-atom value is shown against drawn atoms.
- **The result store never partitions by parameters.**
  - `SessionResultStore` records under (result_id, calculation_input,
    input_fingerprint).
  - `ResultIdentity.parameters_key` is serialised and read by nothing else
    in `src/`.
  - A calculator's result_id is fixed (for example
    `geometry_partial_charge`), so today an EEM result replaces a QEq one
    and the pH calculator's MMFF94 replaces its Gasteiger.
  - Consequences for this track:
    - adding `charge_model` changes only the recorded metadata of a default
      dipole, not whether an old result is found;
    - **the invariant that protects a reader is that every result names
      the charge model it used**, since the store will show the latest
      whichever model produced it.
  - Changing the store's partitioning is out of scope and recorded as a
    finding.
- **`input_fingerprint` is exact-text SHA-256, deliberately not
  canonicalised** (`chem/calculation_input.py`): the drawing molblock for
  DRAWING, and the conformer id plus its molblock for GEOMETRY. Its own
  docstring gives the reason, and it is kept. It already distinguishes
  stereo, isotopes, explicit H and coordinates, because they are in the
  text.
- **The Properties panel sends every parameter's default**
  (`PropertyPanel._on_run_selected`), so a new parameter always appears in
  a request.
- **Conformers survive some drawing edits.**
  `EditStructureCommand._invalidate_stale_conformers` keeps them when
  canonical SMILES is unchanged (coordinates moved, cleaned up, or an atom
  erased and redrawn) or only isotopes changed. So the drawing's atom order
  can change while a conformer stays, and a GEOMETRY result keyed by
  conformer index can then be shown against the wrong drawn atom. That makes
  the OPEN TODO reachable through first-party editing, not only through
  plugins. Measured in the driven check below before it is fixed.
- **No domain model records a conformer→drawing map.**
  `conformer_providers._skeleton_with_index_map` translates within one
  molecule only.

## Experiments

### E1. The index defect, measured then fixed

- **Driven, before any fix:** ethanol drawn as C–C–O, conformers generated,
  EEM 3D charges run and the Inspector's O value recorded. Then erase O,
  redraw O on the same carbon (canonical SMILES unchanged), and record
  whether conformers survive, the drawn atom order, the Inspector's O value,
  and whether the result reads fresh.
- **Prediction, recorded before the run:** conformers survive, the O moves
  to the last drawing index, the result stays READY, and the Inspector shows
  some atom's charge on the wrong drawn atom.
  - If the prediction fails, that is recorded, and the fix is still made
    for the plugin and foreign-file routes.
- **Fix:** conformers record `drawing_atom_ids` against the drawing
  fingerprint they were built from.
  - First-party routes tag atoms with an RDKit property before generation,
    which survives `AddHs` and embedding; the ORCA copy inherits it.
  - A projection is trusted only when the current drawing fingerprint
    equals the recorded one. Otherwise the `CONFORMER_OF_DRAWING` policy
    applies: graph isomorphisms including isotope and stereo; one
    isomorphism is the map; several are resolved only by value-observational
    uniqueness for that dataset, or refused `REFUSE_AMBIGUOUS_IDENTITY`.
  - The claim is IMPLEMENTATION REPRODUCTION of "each drawn atom shows the
    charge computed for it".

### E2. Dipoles (claim: APPLICATION BENCHMARK)

- **A, historical:** BLOCKED. `gasteiger1985` Table I (rendered at 320 dpi)
  prints 15 molecules' experimental and PEPE dipoles and no geometries. Its
  0.164 D mean absolute error is quoted, never compared.
- **B:** the same 15 molecules on OpenChem conformers, frozen before any
  dipole is computed:
  - SMILES as in `tests/fixtures/charges/gasteiger1985_dipoles.csv`;
  - `RDKitConformerProvider(random_seed=20260915)` with the app's default
    search and MMFF94 optimisation;
  - the conformer `canonical_conformer` would pick, with explicit hydrogens;
  - molblocks written to `tests/fixtures/charges/gasteiger1985_conformers.csv`,
    SHA-256 recorded here after freezing: `dfc34dfabd1bf9126850aa5bb7a0b9e42eee0678885d3a555089f5a5c4e6e4e1`
    (frozen 2026-09-15 with `search_conformers` and default `GenerationOptions`,
    committed before any dipole was computed on it).
- **Oracle:** the experimental column (2 dp). **Metric:** mean absolute error
  over the molecules each model covers, with n.
  - EEM refuses chlorobenzene (Cl), so its n is 14, reported as
    PARTIAL-COVERAGE.
  - QEq may refuse bound-active or non-converging cases, each listed.
- **0.794 D is a regression reference, not an oracle.** It is this project's
  own PEOE measurement on unfrozen conformers (VALIDATION.md). The frozen
  set's Gasteiger MAE is reported beside it with the difference; nothing
  stops on it.
- **Product rule, separate from the benchmark:** the choice is offered
  whatever the MAE. Each dipole result states its model and the benchmark's
  MAE and coverage for that model. The MAE never chooses the default, which
  stays Gasteiger.

### E3. The external EEM benchmark (claim: APPLICATION BENCHMARK)

`ionescu2013` SI: `training_set.pdb` (41 MODELs) and the insulin and
ubiquitin PDBs, against the CSV's **"MPA/6-31G\*/gas"** QM charges.
- The shipped Bultinck EEM runs on each fragment's deposited coordinates,
  with every atom explicit as deposited.
- Fragments containing S or Ca are refused: PARTIAL-COVERAGE with counts.
- **Report per element and pooled:** R² (squared Pearson), RMSD, and n.
- **Populations:** source, applicable, excluded-S, excluded-Ca.
- **No gate.** A protein-fragment domain at a different QM level from
  Bultinck's fit. No claim about small molecules follows either way.
- **Fragment charge:** the net of the deposited QM charges per MODEL,
  rounded to an integer. A MODEL whose deposited sum is more than 0.01 from
  an integer is excluded and listed.

### E4. The ESP surface

No oracle. The existing vertex-colour correlation test is re-run per model as
an application and rendering regression. It is never charge validation.

## Architecture under test

- **`ChargeEvaluation`**, canonical in calculation space:
  - charges by the evaluated structure's atom index;
  - `method_key` and `parameters_key`;
  - the parameter-set record (source key, version, source-file SHA-256,
    normalised payload SHA-256);
  - the method's declared input requirement (Gasteiger DRAWING; EEM and QEq
    GEOMETRY);
  - the input fingerprint from `resolve_calculation_input`;
  - identity policy and mapping version;
  - claim kind, provenance, refusal code and reason.
- **`DrawingProjection`** is separate: calculation atom → drawing atom, with
  the policy used and any value-uniqueness record.
- **Consumers:** the dipole, the ESP surface and the ESP comparison take
  `charge_model` (stable keys `gasteiger`, `eem_bultinck2002_part1`,
  `qeq_rg1991_lambda_half_h_experimental`).
  - They need the stored 3D conformer for their own physics.
  - There is no fallback of any kind; a refusal is shown with its reason.

## Tests and mutations, before implementation is called done

- **Identity:**
  - hydrogens before heavy atoms;
  - shuffled indices;
  - atom maps changed or removed;
  - isopropanol (graph search alone must refuse; the recorded map must
    place each methyl's distinct charge);
  - two isomorphisms with different values, which must refuse;
  - planar benzene carbons with equal values, which must succeed;
  - 2-butanol R against S, which must not cross;
  - CD₃ against CH₃;
  - the end-to-end fixture: drawing → generation → ORCA-style geometry copy
    (process boundary mocked) → save → reopen → EEM → projection, on atom
    ids.
- **Consumers:**
  - symmetric molecule gives about 0 under every model;
  - refusal propagation (EEM element; QEq `REFUSE_BOUND_ACTIVE` on
    propane-1,3-diide; QEq `REFUSE_NOT_CONVERGED` on LiH; no conformer);
  - every result names its model;
  - a different model gives a different `parameters_key`, and the same
    request gives the same;
  - a changed conformer gives a different fingerprint;
  - an edit that clears conformers makes the result STALE;
  - no-fallback in computation (spied) and in persistence (a refused EEM
    request stores an INAPPLICABLE result with no charge array);
  - provenance completeness for every persisted result these tracks create;
  - **Gasteiger's behaviour unchanged, against a project fixture saved on
    master:** identical charge vector, atom association, freshness and
    displayed model; no conformer dependency added to Gasteiger's own
    evaluation.
    - The recorded `parameters_key` for a default dipole gains
      `charge_model` and is not asserted byte-identical, because nothing
      reads it (measured above).
    - The plan's byte-identical-key item is amended openly for that reason.
- **Mutations:**
  - persist Gasteiger's array under the refused EEM key;
  - key charges by drawing index;
  - drop stereo from the identity policy;
  - fall back to Gasteiger on refusal;
  - fall back to drawing coordinates;
  - store the English label;
  - omit the model from the result text;
  - trust a recorded map after the drawing fingerprint changed;
  - naive first isomorphism.

## Live check

`OPENCHEM_DRIVE`:
- E1's erase-and-redraw sequence, before and after the fix, with
  `inspector_report`;
- the dipole under each model, then `result_report`, then a shot;
- ESP shots per model, cropped to 3×;
- EEM on chlorobenzene shows its refusal;
- QEq on the bound-active dianion shows its refusal;
- `save_project`, a relaunch, and `report`.

## Results (2026-09-15)

Appended after the runs. Nothing above this heading was changed by them, apart
from the E2 fixture hash, which was recorded before any dipole existed.

### E1: measured, then fixed

- **Driven before the fix** (`restructure` on ethanol, erase-and-redraw shaped):
  - SMILES unchanged, conformer kept, the result READY;
  - the Atom Inspector showed the oxygen with **−0.4258 e, carbon C1's EEM 3D
    charge** (the oxygen's own is −0.5818), while the drawing-based Gasteiger
    row beside it was correct.
  - **The prediction held in every part.**
- **Driven after the fix:**
  - ethanol uses the unique graph correspondence, and every atom shows its
    own value;
  - reordered isopropanol, whose methyls differ, shows "not shown" with
    `REFUSE_AMBIGUOUS_IDENTITY`.
- **Tests:**
  - `tests/test_atom_identity.py` covers the recorded map, the stale map with
    elements aligned, graph uniqueness, ambiguity, printed-precision
    uniqueness, isotopes both ways, stereo and unwedged drawings, a gone
    conformer, and round-tripping;
  - `tests/test_atom_inspector_panel.py` covers the real panel after a
    reorder;
  - a project saved by master's code opens with its results fresh and
    projected.

### E2: dipoles (application benchmark)

- **A:** BLOCKED as pre-registered (no geometries printed).
- **B** (`dipole_benchmark.csv`):

  | Model | MAE | n |
  |---|---|---|
  | Gasteiger | 0.794 D | 15 |
  | EEM | 1.786 D | 14 (chlorobenzene refused) |
  | QEq | 1.689 D | 15 |

  - Gasteiger equals the earlier unfrozen reference, 0.794 D.
  - Both 3D models overestimate polar molecules.
  - Each dipole result quotes its model's figure; a test ties the quotes to
    the CSV.

### E3: Ionescu 2013 (application benchmark)

- **Populations:** 43 source structures, 1 applicable, 35 excluded for S,
  7 for Ca, 0 for order or charge.
- **Ubiquitin** against MPA/6-31G\*/gas: R² 0.95 pooled; C 0.97, H 0.74,
  N 0.36, O 0.03; RMSD 0.12 e pooled.
- **PARTIAL-COVERAGE.** Its main finding is that coverage, not agreement,
  limits the shipped EEM on protein data.

### E4: ESP

- Covered by widget tests (the comparison pane) and the dialog's own-charges
  path.
- **Not driven:** the comparison pane appears only after a completed ORCA
  job, and no ORCA run was made for this track.

### Live check

- **Driven:**
  - salicylic acid's dipole under Gasteiger, EEM and QEq (2.30, 5.95 and
    4.90 D), each named and quoting its benchmark;
  - EEM on chlorobenzene INAPPLICABLE with `REFUSE_ELEMENT_NOT_PARAMETERISED`
    ("Not applicable" in the magnified Properties shot);
  - a save.
- **Not driven:** QEq's bound-active dianion, which is covered by
  `tests/test_charge_consumers.py` through the calculator, and a relaunch
  after the save, which is covered by the master-project fixture test.

### Mutations

- **11 of 11 turn the tests red.**
- **The first run left four green:**
  - key-by-drawing-index;
  - a stale recorded map;
  - stereo dropped;
  - isotopes dropped.
- Each exposed a test that did not test its claim, and each was fixed:
  - a panel-level test;
  - a 1-propanol stale map whose elements still align;
  - both stereo checks removed together;
  - the isotope case in the unlabelled-drawing direction.

### Departures from this pre-registration, stated

1. **Stereo in identity:** CIP labels are compared only where the DRAWING
   states a configuration. Comparing them everywhere refused ordinary
   unwedged drawings, since a 3D conformer always has a hand. Found by the
   mutation run.
2. **Value-observational uniqueness** is judged at the consumer's printed
   precision (`atom_report.per_atom_display`), as written above. The first
   implementation used 1e-9 and was corrected to match this document.
3. **Placement is at display time,** not in `resolve_calculation_input` as
   the old Known TODO proposed, for the reason E1 measured.
4. **Gasteiger's recorded `parameters_key`** gains `charge_model` and is not
   byte-identical, as stated above. Its charge vector, dipole, facts
   (bar the benchmark sentence), freshness and association are identical,
   and are tested against a project master saved.
5. **The ORCA optimised geometry does not inherit a recorded map.** E1 said
   it would. It was not built: an ORCA-optimised conformer records no map,
   so its values are placed by the graph policy, and refused where
   symmetry-equivalent atoms differ. Tracked as an open edge, not claimed.
6. **E4's per-model re-run of the vertex-colour correlation test was not
   done.** The ESP views are covered by widget tests (the model choice, the
   caption, a refusal leaving the pane empty) and by the dialog's
   own-charges path, not by a per-model rendering correlation.
