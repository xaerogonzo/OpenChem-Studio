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

- **PASS:** Frozen preregistration is `benchmarks/docking/PREREGISTRATION_GNINA.md`
  (CNN rescore NULL; default dock NULL — `RESULT_GNINA.md`, `RESULT_GNINA_DOCK.md`). No
  deciding receptor is CNN-rescored before that freeze.
- **FAIL:** the program stops. DiffDock-class is a **new** spike if the owner reopens
  it, not an automatic fallback.

## How another user would install it (External Tools)

Not like Vina. Vina is one PE (`vina_1.2.7_win.exe`) that the Windows app starts with an argument array. gnina v1.3.3 on this machine is a **Linux** ELF that still needs **CUDA 12.8 runtime + cuDNN 9** (`ldd` listed seven missing `.so` files before those libs were added). There is no official Windows gnina binary.

A user who wanted this as an External Tool would need, today:

1. WSL2 with a working NVIDIA GPU (`nvidia-smi` inside the distro).
2. The v1.3.3 `gnina.cuda12.8.static` file (~1.91 GiB) on a **fast** disk (D: here; an external USB disk is likely too slow for a 2 GiB map).
3. Matching CUDA/cuDNN libraries (~3 GiB in a user-level micromamba env here). The word "static" on the GitHub asset is false for cudnn/cudart; those are not bundled.
4. A wrapper that sets `LD_LIBRARY_PATH` and is invoked through `wsl.exe`, not `CreateProcess` on a `.exe`.

That is closer to "bring your own Linux CUDA stack" than to Settings > External tools > Download. Docker Hub `gnina/gnina:v1.3.3` is **~22 GB compressed** and was **not** pulled. A PASS here is not a packaging decision.

gnina's papers are about **docking power** (right pose). They are not a measurement of analogue **affinity ranking** (ROADMAP route 2 already NULL for Vinardo). This spike measures neither; it only starts the process.

## Status

**PASS** (obtain-and-start). Run 2026-11-04. No catalog receptor. Nothing in `src/`.

## Outcome (2026-11-04)

- **Obtain path:** (1) official binary, plus user-level CUDA/cuDNN libs on D: (not Docker, not a source build, no `sudo`).
- **WSL GPU before download:** `nvidia-smi` in Ubuntu listed `NVIDIA GeForce RTX 4060`, driver 595.95, 8188 MiB. Same GPU as Windows.
- **Asset:** v1.3.3 `gnina.cuda12.8.static`, 2,056,131,000 bytes, sha256 `3340c1f49cd3c7c84d8699182a1c6af13c7fa2a22448d1204640446106f72172`, path `D:/_scratch/gnina/gnina.cuda12.8.static` (`/mnt/d/_scratch/gnina/...`). Download ~36 s (~54 MB/s).
- **First start:** failed `libcudnn.so.9` (also missing `libcudart.so.12`, `libcusparse.so.12`, `libcufft.so.11`, `libcublas.so.12`, `libcublasLt.so.12`, `libcusolver.so.11`). The binary is not self-contained.
- **Libs:** micromamba 2.10.0 (extracted on Windows; WSL has no `bzip2`) created `/mnt/d/_scratch/gnina/cuda-env` from `nvidia`/`conda-forge`: cuda-cudart 12.8.90, cudnn/libcudnn 9.14.0.64, libcublas 12.8.5.5, plus cufft/cusparse/cusolver. ~2 GB download, ~3.1 GiB on disk. WSL `sudo` needs a password, so no system CUDA toolkit.
- **`LD_LIBRARY_PATH`:** `/mnt/d/_scratch/gnina/cuda-env/lib:/usr/lib/wsl/lib` (`ldd`: none missing).
- **`gnina --version`:** `gnina v1.3.3 master:6fe1ce2   Built Jun 30 2026.` exit 0, ~7.3 s real (cold map of a 2 GiB ELF off NTFS).
- **GPU in the same session:** `GPU 0: NVIDIA GeForce RTX 4060`. `--no_gpu` was not used. CNN weights were not loaded (no dock).
- **Smoke:** version only.
- **Disk:** ~6.4 GiB under `D:/_scratch/gnina/` (2.0 GiB binary + 3.1 GiB cuda-env + 1.5 GiB micromamba package cache). Not 22 GiB.
- **WSL `HOME`:** Windows `HOME` leaks in as `C:Userspmpd`; commands used `HOME=/home/main` (uid `main`).

Wrapper used (not in Git): `LD_LIBRARY_PATH=/mnt/d/_scratch/gnina/cuda-env/lib:/usr/lib/wsl/lib` then the ELF.
