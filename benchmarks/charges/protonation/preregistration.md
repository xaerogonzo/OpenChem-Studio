# Geometry charges at a pH — pre-registration

Round 3, Track 3. Written 2026-09-15, **before any charge is computed on a
protonated conformer**. It follows Track 2's merge (master 9165d4f), whose
identity service and `evaluate_charges` producer this builds on.

**What is claimed:** none of this is a reproduction of any source. There is
**no oracle for the charges**, and the pre-registration says so up front. What
is tested is the *structure and state* path: which atom is which, which proton
moved, and that nothing but the new hydrogens moves in space.

## 1. Measured first, before any design (2026-09-15)

All five are measurements of the code as merged, not assumptions.

1. **`Microspecies` carries no atom map.** Its fields today are `mol`,
   `formal_charge` and `corrected_atoms`.
2. **But the correspondence already exists and is discarded.**
   `restore_heavy_atom_order` matches the two heavy-atom skeletons, scores the
   candidates by "fewest departures from the drawing", refuses when
   symmetry-equivalent atoms would receive different states, and then returns
   only the rebuilt molecule. `best[0]` — the map Track 3 needs — is a local
   variable. **So the map is surfaced, never invented.**
3. **The rebuild is index-aligned with the drawing.** Every drawn atom keeps
   its index, drawn explicit hydrogens included, and a proton change is
   expressed as a *formal charge and implicit H count* on the heavy atom.
4. **On an H-explicit conformer, deprotonation raises today.** Measured on
   embedded 3D molecules:
   - `CC(=O)O` at pH 7.4: `InvalidStructureError: Atom 4 is drawn with a
     hydrogen the protonated form removes`;
   - `NCC(=O)O` at 7.4: the same, on atom 5;
   - `CN` at 7.4: succeeds, returning **7 atoms from 7** with net +1, so the
     added proton is an implicit H count and **not an atom with coordinates**.

   `compute_geometry_charges` refuses implicit hydrogens
   (`REFUSE_IMPLICIT_HYDROGENS`), so a conformer always has explicit H. **Both
   halves of the gap are therefore structural, and both are this track's
   work**: choosing which drawn H is removed, and materialising an added one.
5. **The dominant states themselves** (on the flat drawing, pH 7.4):

   | Molecule | State | Net | Changed sites (index, ΔH, Δcharge) |
   |---|---|---|---|
   | `NCC(=O)O` | `[NH3+]CC(=O)[O-]` | 0 | N1 (+1, +1) and O5 (−1, −1) |
   | `CC(=O)O` | `CC(=O)[O-]` | −1 | O4 (−1, −1) |
   | `CN` | `C[NH3+]` | +1 | N2 (+1, +1) |
   | `c1ccccc1`, `CCO` | unchanged | 0 | none |

   Glycine is the case the per-site records exist for: two sites that cancel,
   so a total-only check would pass while saying nothing.

## 2. The provider is the sole authority for correspondence

`Microspecies` gains three fields, all computed where the correspondence is
already known and none re-derived by any consumer:

- **`source_heavy_map`:** source atom id → microspecies atom id, for every
  heavy atom. Application ids within the calculation snapshot; RDKit indices
  are diagnostics only.
- **`site_changes`:** a tuple of `(heavy atom id, removed source H id or
  None, ΔH, Δformal_charge)`. Every entry is one proton at one heavy atom;
  nothing else is representable.
- **`state_id`:** a stable digest of the selected state, for the result
  identity.

**Which source hydrogen is removed.** Dimorphite's output names no hydrogen,
so the rule is fixed here:
- when every explicit H on that heavy atom is equivalent under the frozen
  structural identity policy (graph and stereo) **and** removing any of them
  changes no per-atom result beyond printed precision, the lowest source atom
  id is used and **the choice is recorded** on the projection;
- otherwise the result is **`REFUSE_AMBIGUOUS_H_IDENTITY`**.
- An NH₃⁺ losing a proton is allowed by that rule; a prochiral CH₂ beside a
  stereocentre refuses.

**Skeleton equivalence** is Track 2's `IONISATION_STATE` policy: the provider's
map is *verified* (a bijection on heavy atoms, equal elements, equal
heavy–heavy bonds under aromaticity normalisation), never searched. A
difference beyond the changed sites refuses as `REFUSE_NOT_IONISATION_ONLY`.

## 3. The parameter, and what it changes

- **`protonation`:** `as_drawn` (default, the existing key unchanged) or
  `at_ph`, with a `ph` parameter.
- **Result identity** carries: the mode, pH, `state_id`, `site_changes`, the
  source fingerprint, the conformer and coordinate hash, the Dimorphite,
  pkasolver and RDKit versions, the H-placement settings, and
  **`protonation_selection_policy_version`** — bumped whenever the selection
  or tie-breaking rule changes, guarded by a test that hashes the decision
  table.
- **The scientific state is separate from the request.** The evaluation also
  carries `effective_structure_fingerprint`, the structure the charges were
  actually computed on. When `at_ph` selects no change, that fingerprint
  equals `as_drawn`'s and the charges are identical, while the request still
  differs in mode and pH — so the store keeps both and neither is a duplicate.

## 4. The coordinate-transfer sequence, and its gate

`protonate_at_ph` rebuilds from SMILES, which carries no coordinates, so every
step is explicit:

1. select the microspecies (the provider);
2. verify `source_heavy_map` and the H identities;
3. build the target with explicit H for every retained source H;
4. **copy** coordinates for every mapped heavy atom and every retained H;
5. **assert bit identity before any minimisation** (`== 0.0`, not a tolerance);
6. add only the newly required H;
7. place and minimise **only those** hydrogens;
8. assert bit identity again for every copied atom.

**H placement, pinned:** `AddHs(addCoords=True)`, then MMFF94 (not 94s) with
every heavy atom and every retained H as a fixed point via
`MMFFGetMoleculeForceField`, 2000 iterations, RDKit's default gradient
tolerance recorded. All intramolecular terms including H–H.
`REFUSE_H_PLACEMENT` with a reason if MMFF cannot type the species or does not
converge. **No fallback force field, and no silent skip.**

## 5. Cases, each pinned

- acetic acid at 7.4 (one removal); methylamine (one addition); **glycine**
  (one of each, net 0);
- an atom-mapped imidazole (maps stripped at the library boundary, restored
  through the map);
- the succinate automorphism tie;
- **no ionisable centre** (benzene, ethanol): no state change, **no H
  placement call at all** (spied), no coordinate change, a charge vector
  numerically identical to `as_drawn`'s, and a **distinct request identity**;
- already dominant as drawn: idempotent.

**Vařeková 2013's phenol and carboxylic-acid SDF pairs are a structure set,
not an oracle** — not for Dimorphite's choice of state, not for which state is
right at a pH, and not for charges. On each neutral SDF: does `at_ph` reach
the dissociated topology at the same site, are heavy coordinates preserved
(our gate), and how far did the deposited dissociated heavy atoms move from
their neutral ones (a measurement of *their* protocol, not ours). Molecules
Dimorphite leaves neutral are reported, never failed. Every MOESM xls is read
first and its fields recorded before anything is compared.

## 6. Mutations

Each must turn the tests red:
- rebuild from SMILES and embed, with no coordinate transfer (must fail at
  step 5);
- pick the lowest-id H at a non-equivalent site (must fail the prochiral case);
- flip the ΔH sign convention;
- change the dominant-state rule without bumping the policy version;
- substructure-search the mapping instead of verifying the provider's (must
  fail the succinate tie);
- re-embed the heavy atoms;
- drop the per-site records, keeping only the total (must fail glycine);
- skip H placement silently;
- fall back to another force field.

## Implementation notes (appended; the sections above are unchanged)

- **2026-09-17: section 3's `effective_structure_fingerprint` was not written by
  the shipped calculator until this date.** It now is, beside the structure
  itself (`PerAtomDataset.structure_molblock`), after the pH result was found
  drawn on the stored conformer: for an acid, every value after the removed
  hydrogen sat on the next atom.
- **2026-09-17: two departures from section 3, recorded rather than silent.**
  The mode is the `ph_dependent` option of `geometry_partial_charge` rather
  than a separate calculator; and the store keeps one result per dataset id
  and input (the latest run), as it does for every calculator, rather than
  both the as-drawn and the pH result.
