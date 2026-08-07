# DREIDING: the assessment, and what the implementation measured

> **Status: the force field is implemented and passes its gate.**
> `src/openchem/chem/dreiding/` reproduces the paper's own ethane
> rotational barrier — **2.8959 against the published 2.896** — which
> validates the additive bond radii, the angle term, the torsion barrier
> with its renormalisation, and the van der Waals term with its
> combination rules, all at once.
>
> Not yet done: the other seven barriers of Table XI (they need a general
> constrained optimiser, where ethane needed only its three symmetry
> parameters), and wiring the energy into the geometry report. Until that
> second step the app still reports MMFF94/UFF only.
>
> The rest of this document is the assessment written before the work,
> kept because its scoping held up and its warning about the PDF was
> exactly right. Findings from the implementation are at the end.

Every previous note in this repo said Dreiding energy was unavailable and
stopped there. That was never a finding — it was the absence of one. This
is the finding, from the primary source.

**Source**: Mayo, Olafson & Goddard, *DREIDING: A Generic Force Field for
Molecular Simulations*, J. Phys. Chem. **1990**, 94, 8897–8909. On disk at
`D:\Xaero Stuff\Documents\Sci Downloads\`, read with `pymupdf`.

**Conclusion: it is implementable and, unusually, it is validatable
against the paper itself.** It is not a tail-end task, and the reason is
transcription risk rather than algorithmic difficulty.

---

## Why the old answer ("RDKit has no Dreiding") was incomplete

RDKit having no Dreiding is true and irrelevant to whether we can have
one. Checked, so the option is closed rather than assumed:

| source | verdict |
| --- | --- |
| RDKit | MMFF94, MMFF94s, UFF. No Dreiding. |
| OpenBabel (installed here) | GAFF, Ghemical, MMFF94, MMFF94s, UFF. **No Dreiding.** |
| the paper | the complete functional form and every parameter |

So there is no library to call. There *is* a complete specification.

## The force field, from the paper

`E = E_val + E_nb`, six terms. None is exotic; all are the standard shapes.

    bond      E = 1/2 k (R - R0)^2          k  = 700 (kcal/mol)/A^2
              or Morse, D = 70 kcal/mol
    angle     E = 1/2 C (cos t - cos t0)^2  K  = 100 (kcal/mol)/rad^2
              linear case: E = K (1 + cos t)
    torsion   Table IV, by hybridisation of the two central atoms
    inversion for planar centres; K = 40 (kcal/mol)/rad^2
    vdW       Lennard-Jones 12-6 or exponential-6
    coulomb   optional charges; hydrogen bonds get their own 12-10 term

**The parameter tables are small and rule-generated, which is the point of
the paper.** Bond lengths are ADDITIVE — `R0(I,J) = R0(I) + R0(J) - 0.01`
— so Table I is one radius and one angle per atom type, about 37 types,
rather than a matrix of pairs. Force constants are near-universal
constants, not per-pair fits. That is what "generic" means here and it is
why the whole force field is a few hundred lines rather than a few
thousand.

## It validates against the paper, which is rare

Most force-field work has to be validated against experiment, where a
disagreement is ambiguous — bad implementation, or bad force field?
DREIDING's paper prints **its own calculated values**, so reproducing them
tests the implementation exactly, with no ambiguity left over.

Table XI, rotational barriers about single bonds (kcal/mol):

| molecule | experiment | DREIDING |
| --- | --- | --- |
| CH3–CH3 | 2.882 | **2.896** |
| CH3–CH2CH3 | 3.4 | **3.376** |
| CH3–CH2CH2CH3 | 3.4 | **3.410** |
| CH3CH2–CH2CH3 | 3.8 | **3.822** |
| CH3–CH(CH3)2 | 3.9 | **3.995** |
| CH3–C(CH3)3 | 4.7 | **5.071** |
| CH3–CH2F | 3.287 | **3.172** |
| CH3–CH2Cl | 3.68 | **3.487** |

Every one is a small molecule buildable from SMILES. **A barrier exercises
almost the whole force field** — torsion, vdW between the rotating groups,
bonds and angles all contribute — so eight barriers is a far stronger test
than eight single-point energies would be.

Tables XII and XIII add conformational and relative energies on the same
basis.

Table IX (structural errors over 76 molecules) is **not** usable: its rows
are Cambridge Structural Database refcodes (`AAXTHP` and the like), so it
needs reference structures we do not have.

## Why this is its own piece of work, not an afternoon

**The parameter tables come out of the PDF corrupted, and precisely in the
atom-type labels.** Measured:

    B_3  extracted as  "B?3"          C_3  extracted as  "C?3"
    kcal/mol           "keal/mol"     C_R  extracted as  "C.R"

Underscores, subscripts and periods are exactly the characters DREIDING's
atom-type notation is built from — `C_3`, `C_2`, `C_R`, `N_3`, `H_HB` — so
the corruption lands on the one field that must be exact. A silently
mistyped radius produces energies that are wrong by a plausible-looking
amount, which is the worst failure mode this project has and the one it
has already paid for: **a fixture labelled "verbatim from a real run" had
its energies typed from memory**, and loose tolerances hid it.

So the transcription needs checking digit by digit against the rendered
page, and the checking is the bulk of the work, not the physics.

## The plan, when it is picked up

1. **Transcribe Tables I–IV** into a data module, each value verified
   against the rendered page rather than the extracted text. A test
   asserts internal consistency — every atom type referenced by a torsion
   or inversion rule exists in Table I — the same guard shape that caught
   the Drago table refusing 14 of its own 24 acids.
2. **Implement the six terms** over an RDKit conformer, atom typing first,
   since everything else keys off it.
3. **Validate against Table XI before anything is wired to the UI.**
   Ethane must come out at 2.896, not "about 2.9". If it does not, the
   implementation is wrong and no amount of narrow unit tests says
   otherwise — the naming benchmark plays exactly this role for the
   nomenclature engine.
4. Only then add it to the geometry report, beside MMFF94 and UFF.

Step 3 is the gate. Shipping a "Dreiding energy" that does not reproduce
the paper's own numbers would be worse than the honest gap that exists
now, because it would look like parity.

## Where it stands today

`chem/geometry_analysis.py` reports MMFF94 and UFF, each carrying a
per-fact limitation naming this gap, so a reader meets the caveat attached
to the number rather than in a separate paragraph they may never see.

`benchmarks/` is where the Table XI set belongs when the work starts —
alongside the naming corpus, which is the model for "a benchmark that can
overturn a conclusion".

---

## What the implementation measured

### The gate: ethane, to four decimals

| geometry | barrier (kcal/mol) |
| --- | --- |
| rigid, at DREIDING's ideal geometry | 3.170 |
| **relaxed, both stationary points** | **2.8959** |
| paper, Table XI | 2.896 |
| experiment | 2.882 |

**The relaxation is not a detail.** Held rigid the answer is 9% high; the
eclipsed form pays for its torsion by lengthening C–C from 1.530 to 1.545 Å
and opening H–C–C from 109.47° to 110.46°, and that is the whole
difference between "close" and "the same force field". Ethane's D3d/D3h
symmetry means three parameters — C–C, C–H, the H–C–C angle — describe
each stationary point exactly, so the relaxation is complete rather than
restricted, which is what makes it comparable to the paper's number.

The barrier decomposes exactly as predicted: **2.000 from torsion**
(analytically, since nine dihedrals each contribute 2.0/9 at the eclipsed
maximum) and the balance from 1-4 hydrogen repulsion.

### Four things the paper hides in plain sight

Each would produce a plausible wrong answer rather than an error.

- **The torsion barrier is renormalised by the dihedral count.** V_JK is
  the *total* for the central bond, shared among every I–J–K–L across it:
  "the program uses a barrier of V_IJKL = 2/9 for each of the nine
  possibilities". Skip the division and ethane's barrier is 18, not 2.
- **The combination rules are mixed, and the paper develops the wrong one
  first.** It presents a geometric mean for both parameters, then says:
  *"for DREIDING we use (36a) with (36c) as defaults"* — geometric for
  the well depth, **arithmetic** for the radius. The geometric radius
  belongs to X6.
- **LJ 12-6 is the default, not exponential-6.** "We consider the LJ as
  the default and use DREIDING/X6 to denote cases where the
  exponential-6 form is used." Likewise harmonic bonds, not Morse — that
  is DREIDING/M.
- **1-4 pairs are included in full.** 1-2 and 1-3 are excluded as
  contained in the bond and angle terms, and there is no 1-4 scale
  factor of the kind AMBER applies. On ethane those 1-4 hydrogens are
  the entire non-torsional part of the barrier.

### A test that passed for the wrong reason

The torsion rules were written against `{type_j, type_k}` — a **set**,
which collapses to one element whenever both central atoms are the same
type. Every "are both of these sp3" test therefore answered 1, no rule
matched, and everything fell through to the Table IV fallback.

**Ethane still came out at 2.0, by luck**, so the gate passed while
hydrogen peroxide was silently getting a 3-fold 180° torsion instead of
its 2-fold 90° one — the parameter that makes HOOH sit near 90° at all.
It was caught by biphenyl, whose exocyclic rule (10 kcal/mol) has no
fallback that happens to agree.

The lesson is the general one: a symmetric test case cannot distinguish
"the rule fired" from "the fallback agreed with the rule". The
parametrised cases in `tests/test_dreiding.py` now cover an asymmetric
and a differing case for each rule.

### Gaps recorded rather than filled

- **Table IV has no row for `B_2`.** That is the paper's gap, not a
  transcription slip. It is listed in `TORSION_TABLE_OMISSIONS` so the
  completeness guard still fails on a *new* gap; the general rules cover
  trigonal boron by hybridisation.
- **No charges and no explicit hydrogen bonds.** Both are the paper's own
  default for the results it reports ("charges are not included"), which
  is what makes Table XI reproducible at all. Named in
  `UNSUPPORTED_TERMS` rather than silently absent.
- **`H__b` and `H___HB` are never assigned automatically.** Bridging and
  hydrogen-bonding hydrogens are modelling choices, not something
  connectivity determines.
