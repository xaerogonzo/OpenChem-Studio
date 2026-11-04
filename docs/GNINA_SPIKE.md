# gnina obtain-and-start spike (slice 1)

Written 2026-11-04. This is **not** a preregistration and **not** a pose-ranking
result. It answers only: can gnina be started on this machine with a visible CUDA
device? Catalog receptors are not scored. Nothing is added to `src/`. A dated Frozen
preregistration is a later slice, and it may not be written if this spike fails.

The closed Vina-family test is `PREREGISTRATION_ENGINE.md` / `artifacts_engine/RESULT.md`
(overall HARMFUL). Learned scorers are a new program (`docs/DOCKING_ENGINE_CANDIDATES.md`).

Owner decisions that bound this slice: obtain-and-start before picking the scientific
question; **gnina first** (not DiffDock); **WSL2 + CUDA is in bounds** (native Windows
is a bonus); a PASS does not by itself justify an External Tools tab.

## This machine (2026-11-04, before any gnina download)

| Fact | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 4060, 8188 MiB |
| Windows driver | 595.95 (`nvidia-smi` on Windows) |
| WSL | Ubuntu, WSL2, **Stopped** |
| Intended scratch (outside Git) | `D:/_scratch/gnina/` |

CUDA inside WSL is **not** yet measured. `nvidia-smi` in the distro after `wsl -d Ubuntu`
is the first live check, before a 2 GB download.

## What counts as PASS / FAIL

**PASS** (all of these):

1. A gnina binary from the obtain order below exists under `D:/_scratch/gnina/` (or the
   WSL path that mounts it).
2. `gnina --version` (or the flag the binary actually prints) exits 0. Record stdout.
3. A CUDA device is visible to that process (gnina's own GPU log, or `nvidia-smi` in the
   same WSL session). `--no_gpu` is a **diagnostic**, not a PASS.

**FAIL** (stop; do not then install DiffDock as a consolation):

- No Linux binary, or the download is corrupt (size/hash mismatch).
- WSL has no NVIDIA device.
- gnina starts only with `--no_gpu`.
- Only a source build would make it run. This slice does not compile gnina.

A **non-catalog smoke** is allowed after `--version` so we know the GPU CNN path loads:
gnina's own example files from its repository or release notes, or a two-atom toy written
in scratch. **Forbidden:** any PDB id in the docking catalog, any file under
`benchmarks/docking/artifacts_prep_box/`, any pose from the engine or PLEC tests.

## Obtain order (stop at the first PASS)

Sizes and names below were read from GitHub on 2026-11-04. They are not a download.

1. **Official Linux static binary** (recommended). Latest release **v1.3.3**
   (published 2026-06-29): one asset
   [`gnina.cuda12.8.static`](https://github.com/gnina/gnina/releases/download/v1.3.3/gnina.cuda12.8.static)
   **2,056,131,000 bytes** (~1.91 GiB). Hash is recorded **after** the download
   (`Get-FileHash` / `sha256sum`), never guessed. gnina's README says the pre-built
   binary is the intended WSL path. RTX 4060 wants the CUDA 12.8 build, not an older
   default binary.
2. **Docker Hub `gnina/gnina:v1.3.3`** only if (1) starts but cannot see CUDA, and the
   NVIDIA Container Toolkit is already usable. The image is ~22 GB compressed. Record
   that cost if we even pull it.
3. **conda-forge / a WSL env** only if (1) and (2) cannot produce a `--version`.
4. **Source build: out of scope** for this slice.

Do not commit the binary. Do not put it on a PATH the application reads.

## What this slice records

A short **Outcome** section at the end of **this file** (dated), plus optional
`D:/_scratch/gnina/SPIKE_LOG.txt` (gitignored by being outside the repo):

- obtain path used (1 / 2 / 3)
- tag, asset name, byte size, sha256
- `gnina --version` text
- whether WSL `nvidia-smi` listed the 4060
- whether gnina logged a GPU
- wall time to first `--version`
- smoke used (name of **non-catalog** files only) or "version only"

No RMSD. No catalog id. No gained/lost.

## After this slice

- **PASS:** draft a Frozen preregistration in a later slice. That draft picks the
  scientific question (CNN rescore of the existing Vina nine vs gnina as a dock), the
  training-overlap rule (CrossDocked2020 is in the 1.3 paper; it is not PDBbind 2020
  general PL), and the Windows/WSL story. No deciding receptor is scored before that
  Frozen line.
- **FAIL:** the program stops. DiffDock-class is a **new** spike if the owner reopens
  it, not an automatic fallback.

## Status

Not run. No binary on disk from this slice.
