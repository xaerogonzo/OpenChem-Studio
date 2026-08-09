# Biological assembly gate

The external check on `chem/structure_assembly.py`'s builder. Everything
else that tests it — 30 unit tests, hand-calculated rotations, refusal
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

## Current result

    structure      atoms  chains   max dev  transform   serial     rmsd
    4DKL           7,380       2    0.0000   0.000000 0.000000  0.00000
    4EA3           5,130       2    0.0000   0.000220 0.000220  0.00000
    5I6X           7,631       3    0.0000   0.000000 0.000000  0.00000
    2OMF           8,481       3    0.0010   0.000524 0.000500  0.00012
    1A34               refused; RCSB's own assembly has 208,440 atoms

Three of the four buildable structures agree with RCSB **to the written
digit** — every atom, exactly. 1A34 is the size guard: the builder
refuses it at 208,440 atoms, and RCSB's own file confirms that is the
count to the atom, so the refusal branch is checked against something
external rather than against its own arithmetic.

## What 2OMF's 0.001 is, and why it is not a defect

115 of its 8,481 atoms differ from RCSB in the last written decimal. The
cause is in the deposit, not in either builder: **the PDB states each
matrix to six decimals where the mmCIF carries ten.**

    PDB  REMARK 350 BIOMT   -0.866025      102.62401
    mmCIF _pdbx_struct_oper -0.8660254038  102.6240103485

At a 60 Å coordinate that is ~3×10⁻⁵ Å, which changes nothing unless an
atom sits within that distance of a rounding boundary. 115 of them do.
Building from the mmCIF instead would remove it — which is one concrete
argument for that work, and the only place this gate can currently see
the difference between the two formats at all.

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

| mutation | 4DKL | 4EA3 | 5I6X | 2OMF |
| --- | --- | --- | --- | --- |
| `transpose` | pass | pass | pass | **FAIL, 118.5 Å** |
| `swap-translation` | **FAIL, 70.9 Å** | **FAIL, 14.9 Å** | **FAIL, 129.2 Å** | **FAIL, 161.9 Å** |

**That top row is the whole reason 2OMF is in the corpus, and it is now
measured rather than argued.** Every matrix in the bundled receptor
catalogue is axis-aligned, so transposing one is a no-op — a transposed
implementation passes all 49 of them, and passes three of the four
structures here. 2OMF's 3-fold is dense and asymmetric and is the only
thing in reach that can tell the difference.

1A34 passes under both mutations, correctly: it tests the size guard,
which a corrupted matrix does not change. Do not read that as the
mutation escaping.

## What this gate does NOT cover

- **mmCIF input.** The builder reads PDB only, so the gate compares a
  PDB-derived build against an mmCIF-derived reference. That asymmetry is
  what surfaces the 2OMF precision finding, and it means nothing here
  exercises our mmCIF reading of `_pdbx_struct_oper_list`.
- **Product expressions.** `(X0)(1-60)` is an mmCIF construct;
  `REMARK 350` enumerates every operator explicitly and has no expression
  syntax at all. So from PDB input `expand_expression` never sees a
  product, and right-to-left composition stays unit-tested until mmCIF
  building lands.
- **A site at an interface.** None of the curated 49 receptors has one,
  which is exactly why the catalogue could not be the gate. Building
  changes zero docking outcomes on the catalogue; 4DKL is the control for
  that (its pocket is inside the monomer, so a built assembly must *not*
  move its pose).

## Files

`corpus.json` states each structure and why it is there. `sources.json`
records the sha256, size and fetch date of every downloaded file — RCSB
regenerates assemblies when a deposit is revised, and `fetch.py --recheck`
reports changed bytes rather than silently absorbing them. The structures
themselves are not committed: 10 files and 40 MB, of which 1A34's
208,440-atom assembly is 24 MB on its own — larger than the entire `.git`
— and all of it re-fetchable from a stable public URL.
