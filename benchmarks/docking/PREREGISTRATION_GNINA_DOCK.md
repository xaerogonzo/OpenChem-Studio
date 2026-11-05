# Preregistration: does gnina's default dock beat Vina's top pose?

Written 2026-11-05, **Frozen 2026-11-05** by the commit that adds this file together
with `run_gnina_dock_test.py`. This is **not** an Amendment of
`PREREGISTRATION_GNINA.md`. That test asked whether CNNscore re-ranking of
**Vina's nine poses** helped; it ran NULL (`RESULT_GNINA.md`). This test asks
whether **gnina's own search** puts a pose within 2.0 A first more often than
Vina already did.

Slice 1 (`docs/GNINA_SPIKE.md`) PASSed. **No catalog receptor has been sent to
gnina as a dock.** `list` and `gates` start no catalog search. `vina_dock` is
Vina only. `search` is the first catalog gnina dock and must not run before this
freeze. Nothing is added to `src/`.

## The question

On the 29 deciding catalog receptors (same hold-out as the CNN-rescore test),
if gnina **docks** (no `--score_only`) into the **same crystal-ligand box** Vina
used, with seed **20261029**, exhaustiveness **25**, and nine poses, is the top
pose within 2.0 A of the crystal ligand more often than Vina's top pose on that
receptor?

`--help` on gnina v1.3.3 (measured 2026-11-05, no catalog input) says
`--cnn_scoring arg (=1)` is **rescore (default)**, then refinement, metrorescore,
metrorefine. This freeze pins the default: `--cnn_scoring rescore`. That is
still a **search** (gnina generates poses, then CNN-rescored them). It is not
`--cnn_scoring all` or refinement; those would be a later Amendment.

CNNaffinity is stored beside the verdict and never used to decide gained/lost.

## How gnina is invoked

WSL2 Ubuntu, `HOME=/home/main`, GPU device 0, no `--no_gpu`, no `--score_only`:

```
gnina -r receptor.pdb -l ligand.sdf
  --center_x CX --center_y CY --center_z CZ
  --size_x SX --size_y SY --size_z SZ
  --exhaustiveness 25 --num_modes 9 --seed 20261029
  --cnn_scoring rescore --device 0
  -o gnina_poses.sdf
```

Binary, libraries, and version pin: the same as `PREREGISTRATION_GNINA.md`
(`gnina.cuda12.8.static`, v1.3.3 `6fe1ce2`). The ligand file is the same
SMILES-embed start Vina gets, not the crystal coordinates. The box is
`box_from_ligand` (crystal ligand), matching the survey / PLEC Vina path.

## Populations

Same as `gnina_core.TRAINING_OVERLAP` / `deciding_ids`: 47 measurable, 18
CrossDocked2020 hold-outs reported apart, **29 deciding**. 4PE5 stays.

## Rules (`gnina_dock_core.py`)

A pose is correct at assignment RMSD **<= 2.0 A** (survey cutoff).

Per deciding receptor: **before** = Vina pose 1; **after** = gnina pose 1
(file order after gnina's own sort). **gained** / **lost** as in the CNN-rescore
test. Verdict grammar identical (`MIN_NET` 3, α=0.05, max 5 unscored). There is
no CNNscore sanity gate: a failed search is unscored.

## Gates, all passed BEFORE any catalog gnina search

`run_gnina_dock_test.py gates` (no catalog search):

1. **Version.** `gnina --version` contains `gnina v1.3.3` and `6fe1ce2`.
2. **GPU.** `nvidia-smi -L` names the RTX 4060.
3. **Default.** `gnina --help` still lists `--cnn_scoring` default as rescore.
4. **Harness.** `vina_dock` must reproduce the survey / committed CNN-rescore
   top-pose class on each receptor it writes; a mismatch is reported, not hidden.

## Expectation and what each outcome means

The expectation is a **null**. Default `--cnn_scoring rescore` is a Vina-family
search plus the CNN that already failed to reorder Vina's poses on this catalog.
A PASS would justify a larger test and still would **not** ship an External
Tools tab. A NULL or HARMFUL closes **gnina default dock on this catalog** as a
product path. It does not speak to `--cnn_scoring all`, to DiffDock-class
generators, or to analogue affinity ranking.

## Limits stated now

The CNN-rescore freeze's limits still apply (optimistic crystal box, assignment
RMSD, protonation, residual same-protein leakage, WSL-only obtain path).

## How it is run

```
uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py list
uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py gates
uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py vina_dock
uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py search
uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py report
```

`search` is the first catalog gnina dock and must not run before this freeze.

## Amendments

(none)
