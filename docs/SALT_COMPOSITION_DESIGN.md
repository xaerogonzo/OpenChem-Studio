# Salt composition engine: design

**Status: architecture contract, 2026-11-10. Nothing is built.** This note is the
scientific and module-boundary contract. It is not an implementation plan: file
names below are the intended homes when code exists, not a commitment to write
them in this change. No calculator is registered, no UI is specified beyond
"later, beside the pKa view", and a charge-valid composition is never an
isolable salt.

This document was written on branch `cursor/salt-composition-design`, created
from fetched `origin/master` in an isolated worktree. It was not written on
`claude/nl005-close-validator`. Implementation, if it happens, is a later
session with its own plan after this file is reviewed.

## What is computed, and what is never claimed

The engine answers: **given ionic species with known identities and formal
charges, what is the smallest positive-integer composition whose charges
cancel**, and (when asked) **what happens if a proton is transferred between
two parent structures**.

It does **not** answer whether that composition crystallizes, is stable, is
pharmaceutically acceptable, or has been isolated. Those are different
questions. The four evidence claims below are recorded independently so a
charge-valid result cannot be read as an experimental salt.

The product is a **compositional** representation (structures, counts, formulas,
masses, evidence). It is not a 3D ion pair, not a unit cell, and not a CIF.

## Layers

Six units. The domain solver never learns whether a cation came from an amine,
a pyridine, an amidine, a metal, or a permanent charge, or whether an anion
came from a carboxylic acid, a sulfonic acid, a hydrohalide, or a polyprotic
inorganic acid.

1. **Domain stoichiometry** — pure integer arithmetic, no RDKit, no import of
   `lattice_energy`. Exact **binary** charge balance only (`balance_two`).
2. **Chemistry components** — graph-sensitive identity, formula, mass, formal
   charge. Mode B perception adapter.
3. **Ionization** — user-selected protonation/deprotonation is the v1 state of
   record. Optional pKa-ladder adapter with its own refusals. Proton transfer
   conserves elements.
4. **Assembly** — multiplicities on the composition, combined formula from
   **element counts**, conservation checks. Structures are primary; formula
   strings are presentation.
5. **Evidence** — four independent claims, not a score.
6. **UI** — deferred.

```
drawing / pair
    -> component identity
    -> ionization (user first; pKa ladder optional)
    -> balance_two
    -> element-count assembly
    -> independent evidence record
```

`chem/substance.py` feeds Mode B. It is not the engine.

## Existing code: reuse as input, not as authority

### `substance.py` — measured limits that the engine must not inherit

`_components()` groups fragments by `(formula, charge)`. That is **not**
molecular identity. Two constitutionally different ions can share an elemental
formula and a formal charge and must not collapse into one component. Formula
equivalence is not structural equivalence.

The `Component` dataclass (atom indices, formula, charge, count) remains a
useful *shape* for "a piece of the drawing". The engine's identity key is
**graph-sensitive**: the chemistry engine's isomeric canonical SMILES of that
fragment (stereo and isotopes included; the same canonicalization the rest of
the application already uses), with formal charge carried as a check that must
match the SMILES, not as a substitute for the graph. Sanitization failure is a
refusal, not a fallback to formula.

`_classify_ionic()` records `total charge` in its evidence but **does not
require it to be zero** before returning `IONIC_SALT`. Any disconnected drawing
with at least one charged fragment reaches that path, so a **neutral coformer
beside ions** can still be labelled an ionic salt. The engine must classify
independently:

| Situation | v1 engine |
|---|---|
| Charge-neutral two-ion salt, graph identities distinct | Mode B composition, reduced ratio computed |
| Unbalanced collection of ions | `charge_valid` false; do not call it a salt |
| Ionic pair plus disconnected neutral (coformer, solvent) | Ions go through `balance_two`; neutrals listed as **non-ionic extras**, not counterions |
| Hydrate / solvate as first-class formula-unit water | **Deferred.** v1 lists water/solvent as extras the same way; it does not emit `· 5 H2O` as a claimed crystal formula |
| Several distinct cations **and** several distinct anions | Keep `substance.py`'s **ambiguous** refusal; do not invent a pairing |
| Mixture of only neutrals | Not a salt (existing `MIXTURE` path) |
| One connected zwitterion | One molecule, not a cation/anion pair |

`formula_unit` reports **drawn** multiplicities (`2 × Cl−` if the drawing has
two chlorides). The solver must not treat those as already reduced. A result
reports **drawn counts** and the **reduced integer ratio** as two facts.

`perceive()` already refuses `[Na+].[Cl-].[K+].[Br-]` as ambiguous. The engine
keeps that refusal. It does **not** treat `SubstanceKind.IONIC_SALT` as proof
of a valid neutral salt.

### `lattice_energy.py` — sibling, not a dependency

Two pathways already exist, and both **consume** a composition; they do not
define one.

- `kapustinskii()` — monatomic binary salts; a local GCD produces ion counts
  for the Kapustinskii formula. Refuses polyatomic ions because they need
  thermochemical radii, a different measurement.
- `volume_based_lattice_energy()` / `ionic_strength_term()` — any ion types,
  given a formula-unit volume (imported crystal). `2I = sum(n_k z_k^2)`.

The domain solver **must not import** this module to reuse GCD. Duplicate the
two-ion GCD in `domain/` (a few integer lines). Do not introduce a shared
chemistry-layer utility solely to DRY that. Lattice energy remains a later
consumer of an established composition, on a crystal or on a classified
binary salt, not a step of composition.

### `formulation.py` — do not extend

Energetic **mass-fraction** recipes with a required condensed-phase ΔfH. Wrong
question.

### `components.py` (ChEMBL parent) — opposite job

Strips counter-ions so compound properties run on the organic piece. The salt
engine must not select a parent and discard the ion.

### Naming salt multipliers — different job

Names a drawn salt. Does not compose one. The salt-multiplier naming test
named in an earlier research note is not in this tree.

## Modes

**A. Generate.** The user supplies a parent and either (i) an already ionic
counter-species or (ii) a parent acid/base. Those are different workflows:
supplying `Na+` or `SO4^2-` is not supplying NaOH or sulfuric acid. From two
neutrals, the ionization layer models proton transfer and then `balance_two`
runs on the resulting ions.

**B. Analyze.** Already-charged disconnected fragments. Graph identity,
independent net-charge check, coformers as extras, zwitterion as one
component, ambiguous pairings refused. `balance_two` only when exactly one
cation species and one anion species remain after extras are set aside.

**C. Enumerate (v1).** Cartesian product of **candidate ionization states of
one selected two-component pair**. Deduplicate identical species+compositions.
Hard cap: **50** unique compositions; if more would be produced, return those
50 in a stated order (user-specified states first, then ladder order) and a
count of omitted. This is **not** general multicomponent salt search.

## Why `balance_many` is deferred

For two opposite-sign charges `z+` and `z-`, the reduced positive integers

`n_C = |z-| / gcd(|z+|, |z-|)`  
`n_A = |z+| / gcd(|z+|, |z-|)`

are unique. `sum n_i z_i = 0` for more than two species admits many positive
integer solutions unless bounds and an optimization criterion are stated.
Neutrality does not prove a unique pairing (`NaCl + KBr` versus `NaBr + KCl`).
A later `balance_many` must define those constraints and **report
non-uniqueness**. v1 does not silently extend the two-ion closed form.

Zero charge, same-sign charges, and non-positive multiplicities are refusals
of `balance_two`, not compositions.

## Ionization versus pKa

Three objects, never interchangeable:

1. A predicted ionization **site**
2. A particular molecular **microspecies**
3. A complete ionic **salt composition**

A site does not prove a dominant solution species. A microspecies does not
prove an isolated salt.

**v1 state of record:** the user specifies how many protons to add or remove
(or picks a charge). Protonation and deprotonation must update **both** the
hydrogen count and the formal charge.

**Already-charged input:** pKa compatibility is **not assessed**. The
protonation state is in the drawing.

### `pka_species_ladder.py` — optional adapter, limited reuse

The ladder is sequential macroscopic dissociation from a fully protonated
state, in a shared predicted-pKa order. It produces a series of structures,
not every microscopic state. It refuses the whole ladder when a site cannot
be mapped, sanitized, or given an acid/base direction, and when the parent
already has **explicit hydrogen atoms** (`explicit_hydrogens`). It carries
`LADDER_NOTE` (interacting sites, similar pKa values).

It is **not** a universal catalog of ionic structures. An adapter may expose
ladder species as *candidate states* for Mode C on structures the ladder
accepts. Every such result must propagate `LADDER_NOTE` and any refusal. Do
not broaden the ladder's scientific claim. Do not feed the integer solver a
pKa value.

### `pka_compatible` is evidence, not proof

Keep pKa out of `balance_two`.

For `B + HA ⇌ BH+ + A−`, a screening comparison under **comparable**
conditions is `ΔpKa = pKa(BH+) − pKa(HA)`, with `log10(K) ≈ ΔpKa`. That
favours proton transfer **in solution**. It does not establish a crystal.

For a polyprotic acid, use the **dissociation step that matches the proposed
ion**. Hydrogen sulfate is not "sulfuric acid is diprotic, so the salt is
2:1". A triprotic parent is not automatically assigned its third pKa when
the proposed anion is still protonated.

Record, when used: pKa value, measured vs predicted, solvent/medium,
temperature, ionic strength, uncertainty, and step identity. Do not compare
values from incompatible conditions as exact thermodynamic constants.

The claim name is **`pka_compatible`** (equivalently `acid_base_plausible` in
prose). Never unqualified `acid_base_supported`. The report states the
evidence, or that pKa was not assessed.

## Proton transfer and elemental conservation (Mode A from neutrals)

`B + HA → BH+ + A−` (and the acid-side analogue: `HA + B → A− + BH+`):

- The ionization layer actually changes hydrogen count and charge on each
  structure. Charge balancing never creates or destroys atoms.
- Combined elemental composition of the **neutral parents** equals combined
  composition of the **ions**, including hydrogen.
- Explicit and implicit hydrogens are not double-counted.
- Isotopic hydrogens are preserved where the representation supports them.
- Combined formula is summed from component element counts, never by
  concatenating formula strings.

An already supplied ion (`Na+`, `SO4^2-`) skips this transfer and is used as
the ionic component. Mixing the two workflows in one step is a refusal.

The conservation test compares original neutrals with resulting ions. That is
stronger than testing a formula string.

## Evidence (independent dimensions, not a scale)

| Claim | Means | v1 |
|---|---|---|
| `charge_valid` | `sum n_i z_i = 0` at the proposed multiplicities | Required for a successful composition |
| `structurally_consistent` | Structures, charges, formulas, valences, and identities internally consistent | Required for a successful composition |
| `pka_compatible` | pKa evidence for the stated proton-transfer step under stated conditions | Optional; **absent / not assessed** for already-charged input |
| `experimentally_established` | An identifiable reference for **this** composition | Unset in v1 |

A result can be charge-valid and structurally consistent with no pKa and no
reference. An experimental salt can be referenced while the predicted pKa
model is uncertain. Charge validity does not mean crystallizable, stable,
pharmaceutical, or isolated.

## Data model

Multiplicity lives on the **composition**, not on the component.

An ionic component is more than `(id, formula, charge, mass)`:

- stable identity (isomeric canonical SMILES of the fragment, as above)
- molecular structure (canonical representation; **primary**)
- molecular formula (presentation)
- formal charge
- molecular mass
- isotope information (in the structure)
- provenance (drawing fragment, user state, registry row, ladder species)
- ionization-state identifier, if applicable
- parent-structure identifier, if generated from a parent
- proton-transfer transform, if generated
- source of the ionic-state definition (registry citation, user, ladder)

### Ionic-species registry

A general catalog of **ions**, not a pharmaceutical counterion whitelist:
anions from parent acids, cations from parent bases, permanently charged
ions, monatomic and polyatomic inorganics, organic ions. Each row
distinguishes the neutral parent, the actual ionic structure, charge, and
ionization relationship. Curated rows need source metadata in
`docs/sources.toml`. Presence in the registry does **not** mean
pharmaceutical acceptability or safety. `HSO4−` and `SO4^2−` are different
rows.

v1 catalog is small and cited (hydrohalides, sulfate / hydrogen sulfate,
phosphate ladder, acetate, nitrate, plus a few organic ions as examples).
Unusual species still pass through the same machinery if the user supplies
the structure and charge.

## Test matrix (v1)

**Mathematics.** Opposite-sign two-ion GCD for +1/−1, +1/−2, +2/−1, +2/−2,
+3/−2; reject charge 0, same-sign, negative multiplicities; large |z|;
reduce when drawn counts share a factor; component identity unchanged by
balancing. Property: every successful `balance_two` has total charge 0 and
is the smallest positive integers.

**Structure.** Same formula and charge, **different constitution** (must not
collapse); stereo; isotopes; explicit hydrogen; permanent charge (quaternary
ammonium, no protonation required); unsanitizable structures refuse;
implicit-H formulas still distinguish graphs.

**Acid-base.** Monoprotic; diprotic first vs second deprotonation (hydrogen
sulfate vs sulfate); triprotic with partial deprotonation; one basic site;
several basic sites (do not assume max protonation); user-selected state
with pKa unused; pKa missing or incomparable (`pka_compatible` not assessed
or refused, composition may still be charge-valid).

**Classification.** Balanced binary; net-charge-nonzero; salt plus coformer;
zwitterion vs disconnected ions; several distinct cations and anions
(ambiguous refusal); repeated identical components (drawn vs reduced);
ethanol + benzene not a salt.

**Conservation and output.** Elemental and hydrogen conservation on proton
transfer; combined formula vs independent element arithmetic; mass vs
independent RDKit component-mass sum; original identities and formulas
preserved; multiplicities not mixed with hydrate/solvate extras.

Handbook checks: **one printed formula unit at a time**, not a bulk table.

## Intended modules (when code exists)

These paths are not in the tree yet. They are named here so an
implementation plan does not have to invent them; this document's
citations stay on files that already exist.

- domain salt_stoichiometry — `balance_two` only; no RDKit; no
  lattice-energy import.
- chem salt_components — graph identity; Mode B around `perceive`
  fragments, **not** `_components()`'s `(formula, charge)` key.
- chem salt_ionization — user deltas; optional ladder adapter;
  conservation.
- chem data ionic_species (JSON) — general ions, cited.
- chem salt_assembly — element counts; evidence record.

UI later, companion to the pKa view, never presented as a crystal.

## Explicitly out of scope (unchanged)

- CIF import and COD search. Roadmap already decided (2026-09-16): search by
  formula or name plus fetch-by-ID **together**, through `net.py`, disk cache,
  no network tests. That is finding a **measured** deposit. It is not this
  engine. Crystal structure prediction from a drawing remains refused
  (`docs/SCIENTIFIC_LIMITATIONS.md`).
- Ion-pair 3D geometry and conformer packing. Disconnected ionic fragments
  are not a meaningful pose; the application already embeds a salt on top of
  itself (documented for sodium acetate). The engine must not interpret
  composition as coordinates.
- Crystal lattice reconstruction.
- Hydrates and solvates as first-class composition features.
- Pharmaceutical safety or acceptability.
- `balance_many()` / general multicomponent integer balancing.

Preserve `substance.py`'s distinction: an ionic **association** is not a
covalent bond, carries no length, and must never grow a fake edge.

## Order of work after this note is accepted

1. Review this file. Amend it here if a contract statement is wrong.
2. Separate implementation plan (tests first for `balance_two`).
3. Mode B on real drawings with graph identity and independent charge checks.
4. User-selected ionization and a small cited registry.
5. Mode C state pairs; pKa as annotation only.
6. UI.

No `src/` in the change that lands this document.
