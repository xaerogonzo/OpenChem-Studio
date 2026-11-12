# Salt composition engine: design

**Status: slices 1–5 are in the library and on Tools > Salt Composition
(`balance_two`, Mode B, Mode A, ionization and catalog, Mode C enumerate, the
window). Charge-valid is never an isolable salt.**
This note is the scientific and module-boundary contract. It is not an
implementation plan: file names below are the intended homes when code exists,
not a commitment to write them in this change. No calculator is registered. The
UI is Tools > Salt Composition, beside the pKa view as evidence, and a
charge-valid composition is never an isolable salt.

This document lives on branch `cursor/salt-composition-design`, created from
fetched `origin/master` in an isolated worktree. It was not written on
`claude/nl005-close-validator`. Implementation, if it happens, is a later
session with its own plan after this file is accepted.

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
3. **Ionization** — a **fully specified** user-selected ionic structure is
   the v1 state of record (not a bare net charge). Optional pKa-ladder adapter
   with its own refusals. Proton transfer conserves elements, **weighted by
   formula-unit multiplicities**.
4. **Assembly** — multiplicities on the composition, combined formula from
   **element counts**, multiplicity-weighted conservation of the complete
   formula unit. Structures are primary; formula strings are presentation.
5. **Evidence** — four independent claims, not a score.
6. **UI** — Tools > Salt Composition (`ui/dialogs/salt_composition_dialog.py`),
   companion to the pKa view: Analyze / two neutrals / two ions / enumerate.
   Never presented as a crystal.

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
**graph-sensitive**, not a universal chemical-species equivalence:

- Use a consistent sanitized, canonicalized representation: the chemistry
  engine's isomeric canonical SMILES of the fragment (the same
  canonicalization the rest of the application already uses).
- Strip atom-map annotations from the identity key.
- Preserve defined stereochemistry.
- Preserve isotope information.
- Keep formal charge as an **independent** consistency check that must match
  the SMILES; it is not a substitute for the graph. `[Na+].[O-]` is not
  sulfate: identity and charge stay independent.
- Do not collapse different constitutional structures because formula and
  charge match.
- Do not silently normalize tautomers or resonance forms into one identity.
  If tautomer or resonance equivalence is ever wanted, it is a separate,
  validated operation, not an implicit part of canonicalization.

Sanitization failure is a refusal, not a fallback to formula. v1 identity is
the molecular graph as written after that sanitization, not "the same
species" in a chemical-equivalence sense.

`_classify_ionic()` records `total charge` in its evidence but **does not
require it to be zero** before returning `IONIC_SALT`. Any disconnected drawing
with at least one charged fragment reaches that path, so a **neutral disconnected fragment
beside ions** can still be labelled an ionic salt. The engine must classify
independently. `SubstanceKind.IONIC_SALT` is not proof of a valid neutral
salt, and the existing classifier does not necessarily resolve the cases
below.

| Situation | v1 engine |
|---|---|
| Exactly one distinct cation species and one distinct anion species, `drawn_total_charge = 0` | Eligible for Mode B as a charge-neutral input; report drawn counts and the theoretical ratio as **separate** facts |
| Same two species, `drawn_total_charge ≠ 0` | Not a charge-neutral composition. May report `balance_two`'s theoretical ratio as a **diagnostic**. Must **not** present the drawing as that salt |
| More than two distinct ionic species (two cations + one anion; one cation + two anions; or any larger set) | **Unsupported multicomponent.** Distinct refusal from ambiguous pairing. Do not call `balance_two`. Do not infer a pairing |
| Several distinct cations **and** several distinct anions | Ambiguous pairing: refuse rather than infer (keep `substance.py`'s refusal). Do not invent NaCl+KBr versus NaBr+KCl |
| Multiple copies of the **same** ionic species | One component identity; preserve the drawn count (`2 × Cl−` is one species, count 2) |
| Ionic pair plus disconnected **neutral** fragment | Ions follow the two-species rules above. Neutrals are **unclassified extras**, not automatically a coformer, hydrate, or solvate |
| First-class hydrate / solvate formula unit | **Deferred.** v1 does not emit `· 5 H2O` as a claimed crystal formula |
| Mixture of only neutrals | Not a salt (existing `MIXTURE` path) |
| One connected zwitterion | One molecule, not a cation/anion pair |

`formula_unit` in `substance.py` reports **drawn** multiplicities. The solver
must not treat those as already reduced.

### Mode B invariant: no automatic stoichiometric correction

Evaluate the input on its **actual drawn** multiplicities:

    drawn_total_charge = sum(component.count * component.charge)

Only `drawn_total_charge = 0` may be reported as a charge-neutral
composition of that drawing. `balance_two()` returns the unique reduced
theoretical ratio for the two charges. That ratio **must never silently
correct** an unbalanced drawing.

Example: `[Ca+2].[Cl-]` has drawn total charge +1. The theoretical Ca²⁺/Cl⁻
ratio is 1:2. The engine may say so as a diagnostic. It must not report the
drawing as calcium chloride. `[Ca+2].[Cl-].[Cl-]` is the balanced drawn
input.

Three facts stay distinct in every Mode B result:

1. **Drawn counts** (component identity unchanged).
2. **Reduced theoretical ratio** from `balance_two`.
3. **Input charge validity** (`drawn_total_charge == 0` or not).

`perceive()` already refuses `[Na+].[Cl-].[K+].[Br-]` as ambiguous. The
engine keeps that refusal **and** refuses every other >2 distinct ionic
species as unsupported multicomponent, even when `substance.py` would still
call it an ionic salt (for example two distinct cations and one anion).

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

**A. Generate.** Two different workflows; mixing them in one step without
explicit proton accounting is a refusal.

1. **Two molecular neutrals** (organic or molecular parent + molecular parent
   acid/base). The ionization layer models proton transfer of the form
   `B + HA → BH+ + A−`, then `balance_two` runs on the resulting ions.
   Supplying acetic acid or sulfuric acid as a **molecular** parent is this
   path. **Metal hydroxides are not.** NaOH is ordinarily `Na+` and `OH−`;
   `HA + NaOH → NaA + H2O` is a different reaction class (spectator cation,
   hydroxide as proton acceptor, water as a product). v1 **does not** model
   that neutralization. Do not treat NaOH as a two-neutral parent. Use
   workflow 2 if the user supplies `Na+` (already ionic, no invented
   protons) or defer the hydroxide path until a later contract defines the
   spectator, the water byproduct, and formula-unit conservation for it.
2. **Already ionic counter-species.** Supplying `Na+` or `SO4^2-` is not
   supplying the parent acid/base. The ion is used as given. The engine must
   **not** invent the hydrogens or charge needed to protonate a remaining
   neutral. A neutral organic base plus sulfate dianion does not, by itself,
   provide the protons for `BH+` or `BH2^2+`. Require one of: the organic
   parent already in its selected protonated state; a user-specified
   protonation transform with explicit proton-source accounting; or a
   modelled proton donor (neutral parent acid or other accounted source).
   Distinguish **supplied** ionic components from species **generated** by
   proton transfer.

**B. Analyze.** Already-charged disconnected fragments. Graph identity.
`drawn_total_charge` on the drawn counts. Neutral fragments are unclassified
extras. Zwitterion is one molecule. `balance_two` only when extras are set
aside and **exactly one** distinct cation species and **exactly one**
distinct anion species remain. More than two distinct ionic species:
unsupported or ambiguous, as in the table above. No silent correction of
drawn counts.

**C. Enumerate (v1).** Cartesian product of **candidate ionization states of
one selected two-component pair**. Deduplicate identical species+compositions.
Hard cap: **50** unique compositions. Order is **deterministic** for identical
inputs: user-specified fully specified states first, then ladder species in
the ladder's own index order, then by identity key. Record three integers:
**generated** (unique compositions before truncation), **returned** (at most
50), **omitted** (`generated - returned`). If more than 50 would be produced,
return those 50 in that order and those counts. Repeated runs of the same
input must produce the same ordered list and the same three counts. This is
**not** general multicomponent salt search.

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

**User-selected ionization must identify a structure.** A net charge alone
does **not**: several site arrangements can share a charge.

| User input | v1 |
|---|---|
| Fully specified ionic structure (drawing, molblock, or registry ion) | Accepted as the proposed state |
| Specific ionization-site selection that yields one structure | Accepted |
| Number of protons added or removed, when that maps to **exactly one** structure | Accepted |
| Desired net charge only | **Not enough.** Must not protonate whichever site is encountered first |
| Several valid structures at the same charge (alternative microspecies) | Present the candidates, or refuse to pick one automatically |

Protonation and deprotonation, when applied, must update **both** the
hydrogen count and the formal charge on the chosen structure.

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

The same rule applies to a **polybasic** molecule. Sequential conjugate-acid
pKa values are different steps. Assessing `BH2^2+` with the first
protonation pKa of B is the same class of error as assessing `SO4^2-` with
the first pKa of sulfuric acid. `pka_compatible` must name the
protonation/dissociation step that corresponds to the **proposed
microspecies**, not reuse the first step for every subsequent one.

Record, when used: pKa value, measured vs predicted, solvent/medium,
temperature, ionic strength, uncertainty, and step identity. Do not compare
values from incompatible conditions as exact thermodynamic constants.

The claim name is **`pka_compatible`** (equivalently `acid_base_plausible` in
prose). Never unqualified `acid_base_supported`. The report states the
evidence, or that pKa was not assessed.

## Proton transfer and elemental conservation (Mode A from neutrals)

One reaction, written once:

    B + HA → BH+ + A−

The same accounting applies whichever parent is described as the acid or the
base. Do not treat a swapped writing as a second mechanism.

Conservation is **multiplicity-weighted over the complete formula unit**, not
a 1:1 pairing of two parent molecules. For a generated composition:

    sum over neutrals (n_parent * elemental_counts(parent))
        = sum over ions (n_ion * elemental_counts(ion))

Example:

    B + 2 HA → BH2^2+ + 2 A−

Compare one B and two HA against one BH2²⁺ and two A⁻. A 1:1 check of B
against BH2²⁺ would fail for the wrong reason (missing two hydrogens that
came from two HA).

Charge balancing and proton-transfer accounting stay separate:

- The ionization layer produces valid structures and named transformations
  (which protons moved, from where). It must not invent atoms.
- `balance_two` only assigns integer multiplicities from charges.
- The assembly layer verifies **formula-unit** conservation: total element
  counts, total hydrogen (explicit and implicit, not double-counted),
  isotopes where the representation supports them, and total charge before
  versus after the modelled transfer (the ions' `sum n_i z_i` is 0; the
  neutrals' net charge is 0).

Combined formula is summed from component element counts, never by
concatenating formula strings.

An already supplied ion skips this transfer and is used as given (Mode A
workflow 2). Combining a remaining **neutral** with that ion still requires
explicit proton-source accounting; the generator must not treat "neutral
parent + counterion" as a complete acid-base reaction.

## Evidence (independent dimensions, not a scale)

| Claim | Means | v1 |
|---|---|---|
| `charge_valid` | For Mode B: `drawn_total_charge = 0`. For a generated composition: `sum n_i z_i = 0` at the **assigned** multiplicities. Theoretical `balance_two` output does not make an unbalanced drawing valid | Required to report a charge-neutral composition |
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

- stable identity (graph key as in the identity policy above; no atom maps)
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
reduce when drawn counts share a factor. Property: every successful
`balance_two` has total charge 0 and is the smallest positive integers.
**Identities and drawn multiplicities are unchanged** when the theoretical
ratio is calculated (the ratio is a separate fact).

**Mode B correction forbidden.** `[Ca+2].[Cl-]` unbalanced (drawn +1);
`[Ca+2].[Cl-].[Cl-]` balanced; `[Na+].[SO4-2]` unbalanced; `[Na+].[Na+].[SO4-2]`
balanced; `[Na+].[O-]` is not sulfate (identity ≠ formula guess).

**Structure.** Same formula and charge, **different constitution** (must not
collapse); stereo; isotopes; explicit hydrogen; atom maps stripped from
identity; no tautomer/resonance merge; permanent charge (quaternary
ammonium, no protonation required); unsanitizable structures refuse;
implicit-H formulas still distinguish graphs.

**Ionization selection.** Net charge only is refused or listed as candidates;
two microspecies at the same charge are not auto-picked; site-specific
selection is accepted. Net-charge listing tries N, O, P and S sites only, so
a carbon deprotonation of acetic acid is not treated as a competing microspecies.

**Acid-base / Mode A.** Monoprotic; diprotic first vs second deprotonation
(hydrogen sulfate vs sulfate); triprotic with partial deprotonation; one
basic site; several basic sites (do not assume max protonation); polybasic
second protonation assessed with the **matching** conjugate-acid pKa, not the
first; `B + 2 HA → BH2^2+ + 2 A−` multiplicity-weighted conservation;
user-selected **structure** with pKa unused; pKa missing or incomparable;
**neutral base + supplied sulfate** without a proton source is refused, not
auto-protonated; **NaOH + HA** is out of v1 (not two-neutral proton transfer).

**Classification.** Balanced binary; net-charge-nonzero drawing not reported
as the theoretical salt; **unclassified** neutral extra (not labelled
coformer/hydrate unless evidence says so); zwitterion vs disconnected ions;
two cations + one anion unsupported; one cation + two anions unsupported;
several distinct cations and anions ambiguous; repeated identical components
(drawn vs reduced); ethanol + benzene not a salt.

**Conservation and output.** Multiplicity-weighted elemental and hydrogen
conservation on proton transfer; combined formula vs independent element
arithmetic; mass vs independent RDKit component-mass sum; original identities
and drawn counts preserved beside the theoretical ratio; extras not mixed
into hydrate fields. Mode C: identical inputs → identical order and the same
generated / returned / omitted counts.

Handbook checks: **one printed formula unit at a time**, not a bulk table.

## Intended modules (when code exists)

These paths are not in the tree yet. They are named here so an
implementation plan does not have to invent them; this document's
citations stay on files that already exist.

- domain salt_stoichiometry — `balance_two` only; no RDKit; no
  lattice-energy import.
- chem salt_components — graph identity; Mode B around `perceive`
  fragments, **not** `_components()`'s `(formula, charge)` key.
- chem salt_ionization — fully specified user states; optional ladder
  adapter; proton-source accounting when a counter-species is already ionic.
- chem data ionic_species (JSON) — general ions, cited.
- chem salt_assembly — element counts; multiplicity-weighted formula-unit
  conservation; evidence record.

UI: Tools > Salt Composition, companion to the pKa view, never presented as a crystal.

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
- Metal-hydroxide neutralization (`HA + NaOH → NaA + H2O`): spectator cation,
  hydroxide as acceptor, water as product. Not the two-neutral `B + HA`
  workflow. v1 does not invent that reaction class.

Preserve `substance.py`'s distinction: an ionic **association** is not a
covalent bond, carries no length, and must never grow a fake edge.

## Order of work after this note is accepted

1. Review this file. Amend it here if a contract statement is wrong.
2. Separate implementation plan (tests first for `balance_two`). Not
   authorized by this revision.
3. Mode B on real drawings: graph identity, `drawn_total_charge`, no silent
   correction, >2 ionic species refused.
4. Fully specified user ionization, proton-source rules, small cited registry.
5. Mode C state pairs with deterministic truncation; pKa as annotation only.
6. UI.

No `src/` in the change that lands or revises this document.
