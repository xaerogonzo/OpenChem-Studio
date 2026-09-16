# A periodic charge calculator (EQeq) — src pre-registration

Written 2026-09-15, **before any src code exists**, after TRIAGE check 2.9
reproduced Wilmer 2012's published charges on all 12 of its MOFs: 3,452 of
3,452 atoms identical at the printed precision. That check is the oracle this
one ships against; nothing here re-argues the model.

**The claim this calculator makes, in one sentence:** *these are EQeq charges —
the charges Wilmer's method assigns to this periodic structure* — and never
"the charges of this material".

## 1. Measured before designing (2026-09-15)

1. **No calculator in this application applies to a crystal.** `applies_to`
   defaults to `frozenset({MOLECULE})` and is deliberate opt-in; **0 of the 60
   registered calculators** declare `CRYSTAL`. So this is the first, and the
   path from a crystal to a computed result has never carried anything.
2. **Crystals do have a result surface already:** `crystal_report.py` builds a
   `ReportResult` of `Fact`s, shown by `crystal_report_dialog`, and it already
   lists which calculators are *inapplicable* to a periodic solid by reading
   `applies_to`. A crystal calculator therefore changes that list the moment it
   is registered.
3. **The structure path exists:** `chem/cif.py` → `Crystal` → `expand()`, which
   gives every atom of one unit cell, wrapped and deduplicated, with occupancy.
4. **Shipped data lives in `src/openchem/chem/data/`** and is loaded relative to
   the module; the packaging spec lists files individually rather than shipping
   the directory wholesale, so a new data file must be added there too.
5. **`Crystal.expand()` has no disorder rule.** Measured on the six committed
   COD fixtures (FEASIBILITY §4): no atom is duplicated, but every pair closer
   than 0.7 Å is a disorder alternative with partial occupancy — two of them at
   0.000 Å. **Wilmer's 12 MOFs are fully ordered, so check 2.9 never met this.**

## 2. What ships, and what it refuses

**The model** is 2.9's, with the four things only the published source states
(2.9-A2): the orbital term's `2a`, k = 14.4 with λ = 1.2, direct summation, and
the rounding. **The solver is written from the equations, not ported** — the
published code is read and never vendored, and the repository stays
GPL-3.0-or-later.

**The parameter table ships as data**, `chem/data/eqeq_ionization.json`, built
by the committed extractor from Moore 1970 and Andersen 1999, carrying per
element: the electron affinity (or its absence), the successive ionisation
potentials, and the source of each. **It is our reconstruction**, and the
provenance says so even though 2.9 showed it agrees value-for-value with the
table the published code ships.

**Four refusals, each returning a reason rather than a number:**
- `REFUSE_NO_AFFINITY` — an element at a neutral charge centre whose sources
  give no bound affinity (magnesium and zinc print "<0"). Never substituted
  with zero.
- `REFUSE_ELEMENT_NOT_PARAMETERISED` — no entry at all, or a charge centre
  deeper than the potentials printed.
- `REFUSE_DISORDERED_STRUCTURE` — any site with occupancy < 1, or any two
  expanded atoms closer than 0.5 Å. **This is the honest form of §1.5:** the
  calculator does not choose a disorder alternative, and the corpus that
  validated it had none.
- `REFUSE_NO_CELL` — a structure without a unit cell is not what this method
  computes.

**The charge centres are an input, not a property of the structure — and the
paper's two artifacts disagree about them.** Its `chargecenters.dat` lists
Mg 2, V 4, Co 2, Ni 2, Cu 2, Zn 2 and **Zr 4, with no palladium**; its text
names "Pd: +2". Measured on Pd(2-pymo)₂ (3.9): with Pd at +2 every atom
reproduces, and with Pd at 0 — what the file implies — **2.4% do**.

So the shipped table is **the union**: the file's entries plus the text's
Pd 2, with each entry carrying which artifact it came from. It ships as data,
**the result names the centre used for every element**, and an element outside
the table takes 0 — which for a metal is a different model, so that case is
stated in the result rather than assumed harmless.

## 3. The result, and its identity

A crystal result carries the fields FEASIBILITY §5 lists, and the molecular
result store's identity is not reused:
- cell vectors and periodicity;
- fractional coordinates in the expanded order, and the wrapping tolerance;
- occupancy handling (here: refused unless every site is full);
- the summation: direct, with **L = 2**, which is the paper's setting and, per
  2.9, the setting the published charges correspond to (L = 3 changes 10 of
  MIL-47's 72 rounded charges);
- λ, k, hydrogen's I₀, the charge-centre table's checksum and the parameter
  table's checksum;
- the claim kind (IMPLEMENTATION REPRODUCTION of `wilmer2012`) and the
  reconstruction note.

**Two numbers are reported beside the charges, because they are what a reader
needs to judge them:** Σq (zero by construction) and the count of atoms whose
value was moved by the published rounding rule.

## 4. Gates — what must hold before it is offered

1. **The oracle, in the src code path:** on Wilmer's 12 MOFs read through
   `chem/cif.py`-equivalent input, every atom reproduces the published charge
   at 3 dp, exactly as 2.9 established through the benchmark path. **A
   difference between the two paths is a defect in this one**, not a new
   scientific question.
   - The structures are ACS accompanying files and are not committed, so the
     corpus test skips when they are absent. The **shipped** regression uses
     the `NaCl.cif` the same SI ships: 8 atoms, P1, a = 5.63 Å. It carries **no
     published charges**, so it is a REGRESSION PIN plus two hand checks, not
     an oracle: by symmetry every Na must take one value and every Cl its
     negative, and Σq must vanish.
2. **Conservation:** |Σq| < 1e-9 on every structure.
3. **Determinism:** the same structure gives byte-identical charges across runs
   and across atom orderings that differ only by the expansion's own order.
4. **Every refusal reaches the user with its reason**, tested through the
   registry, and no refusal path returns a charge.
5. **The crystal report's inapplicable list shrinks by exactly this
   calculator**, which is the measurable consequence of §1.2.

## 4-A1. Amendment, 2026-09-15, after gate 1 ran: the sum is not invariant to translating ONE atom

Gate 1 was run on all twelve. **Ten reproduce every atom exactly; Ni-MOF74 and Zn-MOF74 do not**,
by up to 0.159 e and 0.008 e. The pre-registration says a difference between the paths is a defect
in this one, so the cause was measured rather than argued:

- **The two implementations are identical on identical atoms.** Feeding check 2.9's benchmark solver
  the coordinates the src path actually used — the expanded, wrapped ones — returns *byte-identical*
  charges to `compute_periodic_charges` on all twelve, Ni-MOF74 and Zn-MOF74 included. **The
  difference is the input, not the code.**
- **It is the deposited representatives.** `Crystal.expand()` wraps every atom into the cell, and the
  deposited files place atoms up to 26 Å outside it: 106 of Ni-MOF74's 162 atoms and 108 of
  Zn-MOF74's move, against 0 for the ten that reproduce.
- **A direct sum truncated at L cells is invariant to translating the WHOLE structure and not to
  translating one atom.** Measured on the shipped NaCl positions: a rigid shift by (1, 2, 0) cells
  changes no pair term by more than 0, and moving a single sodium by one cell edge changes a pair
  term by **3.23 eV**. Co-MOF74 is the control in the corpus — all 162 of its atoms move under
  wrapping, uniformly, and every charge still reproduces exactly.
- **It does not converge away.** At L = 8 the Ni-MOF74 wrapped-against-deposited difference is still
  0.155 e. The lattice sum of a 1/r kernel is conditionally convergent, so the answer depends on the
  region summed, and moving one atom by a cell moves that region for every pair it belongs to.

**Gate 1 is therefore narrowed, and the narrowing is a statement about the source, not a weakening
of the test:**

> On the ten structures whose deposited coordinates lie inside their unit cell, every atom of the
> src path reproduces the published charge at 3 dp. On Ni-MOF74 and Zn-MOF74 the published charges
> depend on unwrapped representatives that **a CIF cannot carry**, and the src path reproduces them
> only when handed those coordinates. Both halves are tested.

**This is a property of EQeq, and it is reported rather than hidden.** The src path wraps, so its
answer is well defined and reproducible for any input representative — which the published
convention is not. The result carries `wrapped_sites`, the number of input sites the expansion moved
into the cell, because that count is exactly the condition under which the two diverge, and is
otherwise invisible to a reader.

## 4-A2. Amendment, 2026-09-15: it ships as a crystal-report section, not a registry entry

§1.1 measured that no calculator declares `CRYSTAL` and concluded "a crystal calculator therefore
changes that list the moment it is registered". **Measured since, before writing the registration:
the registry cannot carry one.** `CalculationRequest` has `calculator_id`, `molecule_uuid` and
parameters, and `RegistryExecution` hands a `Chem.Mol` to a function — there is no route from a
crystal to a registered calculator, and
`test_a_calculation_cannot_even_be_ADDRESSED_to_a_crystal` keeps it that way *on purpose*, naming
itself as the place that would have to change first.

So this follows the precedent the same file already sets for crystal-side science: **the powder
pattern is not a registered calculator either**, it is a section of `build_crystal_report`. The
charges ship the same way, per element with the spread beside the mean, plus the balance row.

Consequences, each tested:
- **Gate 5 is replaced.** The inapplicable list is *unchanged*, because nothing molecular changed,
  and a test asserts no `EQeq` entry appears in `CALCULATOR_DEFINITIONS`.
- **A new reporting cap, `CHARGE_MAX_ATOMS = 500`.** `build_crystal_report` runs synchronously on
  the UI thread at import and on every selection, and the solve is O(N²) over 125 cells — 0.46 s at
  276 atoms, 3.46 s at 624. The cap stops the *work*, not just the printing, and the module itself
  has no cap.
- **Measured over the six committed CIF fixtures: one computes, one is over the cap, and four refuse
  for partial occupancy.** §1.5 said disorder would be the binding constraint on real files rather
  than anything about the model, and that is what the numbers say.

## 4-A3. Amendment, 2026-09-16: §3's identity fields are for a STORED result, and nothing stores this

§3 asked the result to carry cell vectors, fractional coordinates, checksums of
both tables, the claim kind and the rest, so that "the molecular result store's
identity is not reused". **Measured: it is not reused, because this result never
enters a store.** `build_crystal_report` recomputes on every selection and
returns a `ReportResult` with `molecule_uuid=""`; there is no retained record
for an identity to key, and nothing to go stale against.

So the fields ship where they can be acted on rather than as a payload nobody
reads: **the settings that change the answer and are in neither the article nor
the structure** — direct summation at 5×5×5, k = 14.4, λ = 1.2, hydrogen's I₀ of
−2 eV, the charge centre used per element, and the table's reconstruction note —
are printed as the result's own evidence, and a test asserts each is there. The
checksums are dropped: a hash with nothing to compare against is ceremony, and
`tests/test_sources_are_current.py` already guards the shipped tables' provenance
in the place that catches an edit.

**If a crystal result is ever persisted, §3 comes back in full**, and the first
thing it will need is what 4-A2 says does not exist yet: a request that can name
a crystal.

## 5. Tests and mutations

**Tests:** the four refusals; NaCl by hand; the parameter table's checksums;
the charge-centre table's effect (Zn at +2 against Zn at 0 must differ, and the
result must say which was used); conservation; determinism; the report's
inapplicable list; and a driven live check that opens a CIF and shows the
charges on screen.

**Mutations, each of which must turn a test red:**
- the orbital term read as the article prints it (`a` for `2a`);
- λ dropped to 1;
- L reduced to 1;
- the rounding rule skipped;
- a metal's charge centre forced to 0;
- an element with no affinity given 0 instead of refusing;
- a disordered structure accepted by taking the majority occupant;
- the published-code constants swapped for the article's (8.6226 for 8.64).

## 6. What this calculator will NOT claim

- **Not a DFT charge.** 2.9 records EQeq's own mean |q − q_REPEAT| of 0.11–0.24
  e against REPEAT charges, and the result carries that number so the reader
  sees the model's distance from an ESP-derived answer.
- **Not transferable to molecules.** The molecular EEM and QEq calculators
  already ship under their own scopes; this one is periodic and is offered only
  for crystals.
- **Not a statement about disorder, partial occupancy, or charged cells.**
  Each is refused, not approximated.
