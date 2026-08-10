# Biological assembly gate

The external check on `chem/structure_assembly.py`'s builder. Everything
else that tests it — 40 unit tests, hand-calculated rotations, refusal
cases — tests it against *this project's own reading* of the PDB and
mmCIF formats, and a misreading is invisible to that. RCSB generates its
assembly files from the mmCIF `_pdbx_struct_oper_list`; we build ours
from the PDB `REMARK 350 BIOMT` records. Two independent readings of the
same deposited annotation.

```bash
uv run --no-sync python benchmarks/assembly/fetch.py
uv run --no-sync python benchmarks/assembly/build.py --label shipped
uv run --no-sync python benchmarks/assembly/score.py benchmarks/assembly/predictions_shipped.json
```

Three scripts because only the first touches the network and only the
second is slow, following `benchmarks/naming` and
`benchmarks/conformers`. `score.py` refuses a predictions file built
against a different corpus version rather than mis-scoring it.

`--format mmcif` scores the other arm: the builder reads both deposited
forms, and RCSB's reference is mmCIF either way.

```bash
uv run --no-sync python benchmarks/assembly/build.py --label mmcif --format mmcif
uv run --no-sync python benchmarks/assembly/score.py benchmarks/assembly/predictions_mmcif.json
```

## Current result

Built from **PDB** (`REMARK 350`):

    case             atoms  chains   max dev  transform   serial     rmsd
    4DKL-a1          7,380       2    0.0000   0.000000 0.000000  0.00000
    4EA3-a1          5,130       2    0.0000   0.000220 0.000220  0.00000
    5I6X-a1          7,631       3    0.0000   0.000000 0.000000  0.00000
    2OMF-a1          8,481       3    0.0010   0.000524 0.000500  0.00012
    1A34-a1              refused; RCSB's own assembly has 208,440 atoms
    1A34-a6              not buildable from pdb

Built from **mmCIF** (`_pdbx_struct_oper_list`):

    4DKL-a1          7,380       2    0.0000   0.000000 0.000000  0.00000
    4EA3-a1          5,130       2    0.0000   0.000223 0.000223  0.00000
    5I6X-a1          7,631       3    0.0000   0.000000 0.000000  0.00000
    2OMF-a1          8,481       3    0.0000   0.000500 0.000500  0.00000
    1A34-a1              refused; RCSB's own assembly has 208,440 atoms
    1A34-a6         52,110      45    0.0000   0.000500 0.000500  0.00000

1A34 is the size guard: the builder refuses it at 208,440 atoms, and
RCSB's own file confirms that is the count to the atom, so the refusal
branch is checked against something external rather than against its own
arithmetic.

## 2OMF's 0.001 was a PREDICTION, and building from mmCIF removed it

115 of its 8,481 atoms differed from RCSB in the last written decimal.
The diagnosis was that the cause sits in the deposit rather than in
either builder — **the PDB states each matrix to six decimals where the
mmCIF carries ten**:

    PDB  REMARK 350 BIOMT   -0.866025      102.62401
    mmCIF _pdbx_struct_oper -0.8660254038  102.6240103485

At a 60 Å coordinate that is ~3×10⁻⁵ Å, which changes nothing unless an
atom sits within that distance of a rounding boundary. 115 of them did.

That made a falsifiable prediction: read the same ten-decimal matrix RCSB
reads and the difference should vanish entirely. It did — **0.0010 →
0.0000**, with the transform error settling at exactly 0.000500, which is
the half-unit of RCSB's own write rounding and cannot go lower. All four
buildable structures now agree with RCSB on every atom to the written
digit from mmCIF input.

## The tolerances are derived, not chosen

`SERIALISATION_TOLERANCE` is 5×10⁻⁴, half of the last written decimal:
rounding to three places *cannot* move a value further, so exceeding it
means the serializer is truncating or overflowing rather than rounding.
`TRANSFORM_TOLERANCE` is 6×10⁻⁴, covering RCSB's own write rounding
(≤5×10⁻⁴) plus the matrix-precision gap above (≤1.1×10⁻⁴ at 200 Å). A
wrongly transposed, mis-composed or mis-scoped operator misses by whole
ångströms, so neither bound is anywhere near the interesting range.

## Match on identity, validate on coordinates

Chains are paired by **composition**, never by serialized id. RCSB calls
5I6X's generated chains `B-2` and `C-2` where we call them `B` and `C`;
failing on that would be a false negative about naming. Within a paired
chain, atoms match on `(residue name, number, insertion code, atom name,
altloc)` and coordinates then *check* the pairing — so two atoms that
happen to occupy the same place cannot be matched to each other.

## The gate has been shown to fail

A benchmark that has never failed is not evidence. `build.py --mutate`
corrupts the operators on purpose, patching `operator_transforms` rather
than editing the module — this project has twice been misled by a
mutation that never landed and by a restored file running from stale
bytecode.

| mutation | 4DKL | 4EA3 | 5I6X | 2OMF | 1A34-a6 |
| --- | --- | --- | --- | --- | --- |
| `transpose` | pass | pass | pass | **FAIL, 118.5 Å** | — |
| `swap-translation` | **FAIL, 70.9 Å** | **FAIL, 14.9 Å** | **FAIL, 129.2 Å** | **FAIL, 161.9 Å** | — |
| `union-product` | — | — | — | — | **FAIL, 81.7 Å** |
| `reverse-composition` | — | — | — | — | pass — see below |

**That top row is the whole reason 2OMF is in the corpus, and it is now
measured rather than argued.** Every matrix in the bundled receptor
catalogue is axis-aligned, so transposing one is a no-op — a transposed
implementation passes all 49 of them, and passes three of the four
structures here. 2OMF's 3-fold is dense and asymmetric and is the only
thing in reach that can tell the difference.

1A34 passes under both mutations, correctly: it tests the size guard,
which a corrupted matrix does not change. Do not read that as the
mutation escaping.

## The product expression, and the one thing it cannot check

**1A34 assembly 6 is `(X0)(1-10,21-25)`** — two groups, the second
carrying a range *and* a comma list, expanding to 15 placements over 8
chains. It is scored as a **subset** of assembly 1, because RCSB
pre-generates only assembly 1 for this entry and `1-10,21-25` are 15 of
that assembly's 60 operators. All 52,110 of our atoms appear among their
208,440, exactly.

`REMARK 350` has no expression syntax at all, so this case is mmCIF-only
and the PDB arm reports it as not applicable rather than skipping it
silently.

**It does not catch a reversed composition, and that is measured rather
than assumed.** `--mutate reverse-composition` passes it: 1A34 defines
`X0` as the exact identity, and composing the identity with anything is
order-independent. `--mutate union-product` — reading `(A)(B)` as *A and
B* instead of *A after B* — **is** caught, at 81.7 Å, because it changes
the placement count from 15 to 16.

Nothing better is reachable. Every product expression whose outer group
is non-identity — 1M4X assembly 7 `(P)(61-88)`, 1AL0 assembly 6, 1NOV
assembly 6 — lives in an assembly RCSB does not pre-generate, and the one
product that *is* in a served assembly, 1M4X assembly 1 `(1-60)(61-88)`,
is 16,284,240 atoms. So composition **order** has no external witness and
stays unit-tested. `tests/test_assembly_gate.py` derives that conclusion
from the deposit's own X0 matrix rather than trusting the corpus flag, so
claiming the coverage without adding a better entry fails.

## What this gate does NOT cover

- **Composition order**, for the reason set out just above.
- **A site at an interface.** None of the curated 49 receptors has one,
  which is exactly why the catalogue could not be the gate. Building
  changes zero docking outcomes on the catalogue; 4DKL is the control for
  that (its pocket is inside the monomer, so a built assembly must *not*
  move its pose). `spikes/assembly_docking/` covers both directions
  against a live Vina.
- **Chain naming.** Deliberately: chains are paired by composition, so
  the gate is blind to what they are called. Our generated copies follow
  RCSB's `A-2` convention, but a chain placed only under a non-identity
  operator keeps its bare deposited name where RCSB would suffix it —
  `keep_chains` addresses chains by name, and the same receptor must
  exclude the same chains whichever format it was imported from.

## Files

`corpus.json` states each structure and why it is there. `sources.json`
records the sha256, size and fetch date of every downloaded file — RCSB
regenerates assemblies when a deposit is revised, and `fetch.py --recheck`
reports changed bytes rather than silently absorbing them. The structures
themselves are not committed: 15 files and 81 MB, of which 1A34's
208,440-atom assembly is 24 MB on its own — larger than the entire `.git`
— and all of it re-fetchable from a stable public URL.
