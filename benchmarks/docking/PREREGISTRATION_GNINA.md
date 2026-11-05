# Preregistration: does gnina CNN rescoring put the right Vina pose first?

Written 2026-11-04, **Frozen 2026-11-04** by the commit that adds this file together with
`run_gnina_test.py` `list` / `dock` / `rescore` / `report` / `gates`. Slice 1
(`docs/GNINA_SPIKE.md`) PASSed: gnina v1.3.3 starts in WSL2 with the RTX 4060. **No catalog
receptor has been CNN-rescored.** Nothing here may change after the first deciding receptor
is rescored. A change is a dated Amendment at the end. Nothing is added to `src/`.

This is not an Amendment of `PREREGISTRATION_ENGINE.md` or of PLEC2. Those closed Vina-family
functions and PLECscore. This test asks a different question with a learned pose score.

## The question

If the **same nine poses** Vina 1.2.7 already returned (prep-and-box survey `app` arm, seed
**20261029**, exhaustiveness **25**, box from the crystal ligand) are **re-ordered by gnina's
CNNscore**, does the pose within 2.0 A of the crystal ligand land on top more often than in
Vina's order?

That is a **rescore**, not a new search. gnina as its own dock (`--cnn_scoring` refinement/all)
is **not an arm**. A later Amendment could add it; this freeze does not.

CNNscore (default `--pose_sort_order`) is the ranking number: it is a pose probability, not
an analogue affinity. **CNNaffinity is reported beside the verdict and never used to order
poses.** ROADMAP route 2 (within-assay ranking) is a different ability and is not this test.

## How gnina is invoked

WSL2 Ubuntu, `HOME=/home/main`, GPU device 0, no `--no_gpu`:

```
gnina -r receptor.pdb -l poses.sdf --score_only --cnn_scoring rescore --device 0
```

Binary: `D:/_scratch/gnina/gnina.cuda12.8.static` (v1.3.3, `6fe1ce2`, 2,056,131,000 bytes,
sha256 `3340c1f4…72172`). `LD_LIBRARY_PATH` includes the user CUDA 12.8 / cuDNN 9 env on D:
and `/usr/lib/wsl/lib`. The GitHub asset is not self-contained (slice 1). The default
built-in CNN ensemble is used (`--cnn` not set). `--cnn_scoring rescore` is gnina's default
(`=1` in `--help`); it is named here so a later default cannot move the test.

Ties in CNNscore keep Vina's order (`gnina_core.rerank` is a stable sort).

## Populations

- **Deciding:** the 47 measurable catalog receptors minus CrossDocked2020 overlap (below).
  That is **29** receptors (`gnina_core.deciding_ids`). 4PE5 stays: Vina produced poses; the
  smina G4 drop does not apply.
- **Reported apart, never counted:** catalog PDB codes that appear in CrossDocked2020's
  `crossdocked_set_ids.txt` (gnina/models). Intersection measured 2026-11-04 from the file
  sha256 `254d543af569d942c9f8cb395e45a1db620ad950d47af2c83240054185ed03b0` (25,752 unique
  PDB codes). Hits: `2RH1`, `2V5Z`, `2VT4`, `3EML`, `3PBL`, `3RZE`, `3SN6`, `3UON`, `4DJH`,
  `4EA3`, `4EY7`, `4IAR`, `4IB4`, `5C1M`, `5CXV`, `5HK1`, `5HK2`, `5KIR`. That index is **not**
  PDBbind 2020 general PL. Residual same-protein leakage beyond these 18 is a stated limit.
- **Seen subset, reported apart:** the 17-receptor engine/PLEC pilot list, among the 29.

`run_gnina_test.py list` prints these counts and starts nothing.

## Rules (`gnina_core.py`)

A pose is correct at assignment RMSD **<= 2.0 A** (survey cutoff, restated).

Per deciding receptor: **gained** = Vina's top pose wrong, CNNscore's top pose correct;
**lost** = the reverse.

Verdict, in this order:

- **INCONCLUSIVE** if more than 5 deciding receptors cannot be rescored, or if the CNN
  produced no ranking signal: the median over deciding receptors of the highest CNNscore
  among the nine poses is below **0.01** (all-zero / failed CNN; not fitted on a catalog
  receptor), or a receptor's nine CNNscores are tied to 1e-12.
- **PASS** if gained − lost >= 3 and the one-sided exact sign test on gained and lost is
  <= 0.05 (five gained and none lost is the smallest PASS).
- **HARMFUL** by the mirror rule.
- **NULL** otherwise.

Reported beside, never counted: the 18 overlap receptors, CNNaffinity tables, wall time,
whether gnina logged the 4060, Vina-order agreement with the survey, the headroom receptors
that remain in the 29.

## Gates, all passed BEFORE any gained/lost is read

`run_gnina_test.py gates` (no catalog CNN):

1. **Version.** `gnina --version` contains `gnina v1.3.3` and `6fe1ce2`.
2. **GPU.** `nvidia-smi -L` in the same WSL session names the RTX 4060. Deciding rescores
   do not pass `--no_gpu`.
3. **Harness.** Vina `dock` (save molblocks + receptor PDB, same path as PLEC) must reproduce
   the survey's top-pose class on each receptor it writes; a mismatch is reported, not hidden.

A format failure on a receptor (gnina will not score the SDF) makes that receptor unscored.

## What was looked at before this was frozen

Slice 1: `--version` and `--help` only. `ldd` missing-lib list. CrossDocked index
intersection (PDB codes, not CNN scores). **No catalog pose, crystal, or receptor was sent
to gnina.**

## Expectation and what each outcome means

The expectation is a **null**. CNNscore was trained to pick poses on CrossDocked2020, which
is not this GPCR-heavy catalog, and 18 catalog entries are already held out. A PASS would
justify a larger test and still would **not** ship an External Tools tab (WSL + 6.4 GiB +
`wsl.exe`, slice 1). A NULL or HARMFUL closes **CNN rescore of these Vina poses** as a
product path and leaves PR 508's pose-choice sentence in place. It does not speak to gnina
as a dock, to DiffDock-class generators, or to analogue affinity ranking.

## Limits stated now

- Redocking into the crystal ligand's box, one seed, one ligand conformer: optimistic, as
  the survey said.
- Assignment RMSD is a lower bound.
- Protonation is whatever Vina's molblock carried (pH 7.4 PDBQT path), then RDKit write to
  SDF; that is not CrossDocked's protonation.
- Same-protein leakage beyond the 18 PDB-code hits remains.
- WSL2 + CUDA is the only obtain path that PASSed; a Windows user does not get a one-file
  download.
- CNNscore is not a binding-affinity calculator.

## How it is run

```
uv run --no-sync python benchmarks/docking/run_gnina_test.py list
uv run --no-sync python benchmarks/docking/run_gnina_test.py gates
uv run --no-sync python benchmarks/docking/run_gnina_test.py dock
uv run --no-sync python benchmarks/docking/run_gnina_test.py rescore
uv run --no-sync python benchmarks/docking/run_gnina_test.py report
```

`list` and `gates` start no catalog CNN. `dock` is Vina only. `rescore` is the first
catalog CNN and must not run before this freeze.

## Amendments

(none)
