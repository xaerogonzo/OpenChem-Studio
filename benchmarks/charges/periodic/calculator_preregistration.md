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
