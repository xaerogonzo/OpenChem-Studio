# Docking engine candidates: can a second native Windows engine pick the right pose more often?

Pilot run 2026-11-02; deciding test frozen and run 2026-11-04
(`PREREGISTRATION_ENGINE.md`, `artifacts_engine/RESULT.md`). This is the owner's
"option 3" after the pose-choice sentence (PR 508), the redocking survey (PR 502,
`benchmarks/docking/PREP_BOX_RESULT.md`) and the two PLECscore tests (`RESULT_PLEC.md`,
inconclusive; `RESULT_PLEC2.md`, harmful). Nothing is added to `src/` and nothing ships:
this is a measurement and a recommendation. The spike that preceded it is `ROADMAP.md`,
"Ranking affinities" (smina, finished 2026-09-12 and stopped at its findings); its findings
are reused here, not repeated.

## The short answer

1. **Engines that only change the search cannot change which pose ranks first.** QuickVina 2,
   QuickVina-W and Vina-GPU search faster under Vina's own scoring function. The headroom is 9
   receptors whose correct pose Vina finds and ranks lower, which is a scoring question. So the
   speed-ups are not candidates for this problem, and neither has a native Windows binary that
   was obtainable and runnable here anyway (table).
2. **smina is the one Vina-family engine that ran natively with other scoring functions.** It
   ran here from a clean folder of 27 files (7.4 MB, 2.8 MB zipped) with a bare `PATH`. Its
   default function matched Vina on the 17-receptor pilot and again on all 46 deciding
   receptors (control is neutral). That harness is sound.
3. **The frozen deciding test is closed: overall HARMFUL.** 5 arms × 3 seeds × 46 receptors
   (G4 drop 4PE5; training overlap empty) = 690 docks. Primary vs Vina:
   `smina-vinardo` NULL (0 gained, 1 lost among 20 comparable), `smina-dkoes_fast` HARMFUL
   (0/8 among 17), `smina-ad4` HARMFUL (3/15 among 46). Vinardo and dkoes_fast majority calls
   were incomplete on the rest (`setup: ligand could not be built` on some seeds); incomplete
   calls are excluded, not counted as losses.
4. **Do not build an engine seam.** Obtaining smina is still a nine-package conda closure, and
   that no longer matters for pose ranking. The product answer stays PR 508's sentence. Learned
   scorers are a **new program**: slice 1 is the gnina obtain-and-start spike
   (`docs/GNINA_SPIKE.md`), not an Amendment of this test.

## The candidates

"Ran" means a binary was started on this machine (Windows 11, RTX 4060). Binaries live in
`D:\_scratch\dockeng\`, outside the repository; nothing was committed or installed.

| Candidate | Version | Licence (checked where) | Windows binary, source, size | Ran here? | Scoring function | Fits the app? |
|---|---|---|---|---|---|---|
| **AutoDock Vina** (baseline) | 1.2.7, released 2025-02-26 | Apache-2.0 (GitHub) | `vina_1.2.7_win.exe`, 1,233,920 bytes, GitHub release asset | Yes (the application's own) | Vina; also Vinardo and `ad4` (the latter needs AutoGrid maps) | Already in External Tools |
| **smina** | 2020.12.10, built 2025-07-15, "Based on AutoDock Vina 1.1.2" | Apache-2.0 for the Vina-derived code and a GPL-2.0 file (`LICENSE.GNU`) in the source mirror; conda-forge lists Apache-2.0. The binary links Open Babel 3.2.1, which conda-forge lists as GPL-2.0-only | conda-forge `win-64/smina-2020.12.10-he0c23c2_2.conda`, 389,686 bytes (sha256 `dac05f31268b054c...7d46`); `smina.exe` 1,180,160 bytes (sha256 `486a5908fdafd477...13af`). Runtime closure: 27 files, 7.4 MB, from 9 conda packages (smina, openbabel, libboost, zstd, liblzma, libzlib, bzip2, ucrt, vc14_runtime) | **Yes**: from the conda env, and from the 27-file folder with `PATH=C:\Windows\System32` | `default` (= Vina's, agrees to 0.004 kcal/mol in the spike), `vinardo`, `dkoes_fast`, `dkoes_scoring`, `ad4_scoring`, custom | Runs as a child process like Vina. Needs a packaging decision (below) |
| **QuickVina 2.1 / QuickVina-W** | repo `QVina/qvina`, last commit 2022-11-07; no releases | Apache-2.0 (GitHub) | **None.** `bin/` holds Linux ELF files only (`qvina2.1` is 4,277,120 bytes, sha256 `bc1f9088...b43d`, first bytes `7F 45 4C 46`). No compiler (`cl`, `g++`, `gcc`) is on this machine's `PATH`, so no Windows build was attempted | No | Vina's own; its README reports 0.967 Pearson correlation with Vina's first-mode energy | Not a candidate for pose choice (search only); not obtainable for Windows |
| **Vina-GPU 2.1** (QuickVina2-GPU, QuickVina-W-GPU variants) | repo `DeltaGroupNJUPT/Vina-GPU-2.1`, last push 2024-10-01; no releases | Apache-2.0 (GitHub) | The repository itself commits `AutoDock-Vina-GPU-2.1/Vina-GPU+.exe`: 651,776 bytes, x86-64 PE, linker time 2022-09-22 (older than the repo's 2.1 label), sha256 `5e47ced0...cf6be`, imports `OpenCL.dll` and the MSVC runtime only, plus precompiled kernels (`Kernel1_Opt.bin`, `Kernel2_Opt.bin`). Needs a GPU with an OpenCL driver (CUDA only if one builds for it) | **No.** I inspected the PE imports and stopped there: running an unsigned, unreleased binary taken from a repository was refused by the session's permission layer and I did not work around it | Vina's own | Not a candidate for pose choice (search only); needs a GPU most users lack |
| **AutoDock4 (4.2.6)** | 4.2.6 | GPL (Scripps download page: "distributed freely under the GNU GPL") | One installer, `autodocksuite-4.2.6.i86Windows.exe` (per the download page; size not stated) | No: it is an installer, and installers are not run in this task | AD4 force field (a different family); needs `autogrid4` maps, so not a drop-in | smina `ad4_scoring` was the stand-in and was HARMFUL on the frozen test |
| **AutoDock-GPU** | repo `ccsb-scripps/AutoDock-GPU`, active 2026-08 | GPL-2.0 plus LGPL files (GitHub) | None. The README's tested-platform table lists Linux and macOS; it is OpenCL or CUDA | No | AD4 on GPU | No |
| **Uni-Dock** | repo `dptech-corp/Uni-Dock`, active 2026-07 | Apache-2.0 (GitHub) | None found; the repository's README does not mention Windows, and the code is C++ and CUDA | No | Vina, Vinardo, AD4 (per its description) | No (CUDA) |
| **gnina** | v1.3.3 (`6fe1ce2`) | Apache-2.0 (GitHub) | GitHub `gnina.cuda12.8.static`, 2,056,131,000 bytes (sha256 `3340c1f4…72172`); not self-contained (CUDA 12.8 + cuDNN 9). Slice 1 PASS in WSL2 | **CNN rescore NULL** (`RESULT_GNINA.md`); **default dock NULL** (`RESULT_GNINA_DOCK.md`, 2026-11-05) | CNN / gnina | Not a Vina-family function; not a one-file Windows PE |
| **LeDock, PLANTS, DOCK 6, rDock** | | Closed or academic-licence programs (LeDock has a Windows release per Wikipedia and the vendor's announcement; DOCK 6 is free for academic use and charged for industry per UCSF's page); redistribution terms not read; rDock's platform support not verified | Not looked for further | No | Their own | Not pursued: a bundled or app-downloaded closed binary needs a licence the project does not have, and none was checked |

What the table does not claim: no engine other than smina and Vina was started, so "does not
run on Windows" is claimed for none of them. Each "not a candidate" line says why in terms of
what the program is for or what could not be obtained.

### Licence compatibility with GPL-3.0-or-later

Not legal advice; this is how the project already treats Vina, ORCA and xtb.

- **Running it as a separate program** (a child process with an argument array) creates no
  licence obligation for the application, whatever the engine's licence. All the candidates
  above that run are used this way.
- **Download on demand** (the Vina model, `docking/vina_executable_path`) leaves the project
  redistributing nothing, so it is the cleanest option for smina too.
- **Bundling** smina in the installer would redistribute Apache-2.0 code (compatible with
  GPL-3.0), Boost (BSL-1.0), zlib, bzip2, zstd, liblzma and the MSVC runtime, and **Open Babel's
  DLL, which conda-forge lists as GPL-2.0-only**. A separate executable shipped beside the
  application is an aggregate, not a combined work, and the project already optionally uses Open
  Babel, but the source-offer obligations would be new and should be read by the owner before
  anything is bundled.

### How the app could obtain smina (will not be built for pose ranking)

The frozen test closed the pose-ranking reason to ship smina. The three obtain paths below
are left as the spike recorded them; none of them should be started for this question.

Vina is one file on a GitHub release. smina is not.

1. **Locate-only tab** (the xtb pattern): the user supplies `smina.exe`. For a Windows user the
   only path to it is conda, which is exactly the extra setup the owner wanted to avoid.
2. **The app downloads the nine conda packages** from conda-forge by name and hash and unpacks
   the `.conda` archives (zip files holding zstd tarballs). Nothing is hosted by the project,
   but the manifest of nine pinned hashes, the archive handling and a repair story are new code.
3. **The project hosts one 2.8 MB zip** of the 27-file folder built from those packages. Simple
   for the user, but it makes the project the redistributor (see above) and a maintainer of a
   binary.

## The pilot: 17 receptors, one seed, as a measurement

`benchmarks/docking/engine_pilot.py`. It reuses the survey's own `run_one`, so the receptor
preparation (Open Babel, waters stripped, cofactors kept, pH 7.4), the box from the crystal
ligand, the embedded ligand, seed 20261029, exhaustiveness 25 and nine poses are the code that
produced `PREP_BOX_RESULT.md`. Every arm is the shipped `VinaDockingProvider` with only the
engine swapped (smina through the spike's `_smina.SminaEngine`; the scoring function is fixed
inside the arm because the provider refuses any function but `vina` and `vinardo`, the seam
the spike recorded). Distances are the survey's assignment RMSD (a lower bound) against its
2.0 A cutoff. Rows: `benchmarks/docking/artifacts_engine_pilot/results.jsonl`.

**The receptors were chosen by a rule, not by hand**: every measurable receptor whose top pose
the survey did not call correct (12: 4DKL, 8EF5, 5HK2, 7M93, 7E2Y, 4IAR, 6A93, 6BQG, 6KUX,
6J8G, 8ZYO, 3EML) plus every seventh top-correct receptor in catalogue order (5C1M, 4IB4, 3PBL,
3RZE, 5I6X). Five of 17 therefore start correct, against 35 of 47 in the whole catalogue: the
pilot is deliberately loaded with headroom and says nothing about the rate over the catalogue.

| Arm | Top pose within 2 A | Best of nine within 2 A | Gained / lost vs Vina | Median top score | Median seconds | Poses returned (of 153 = 17 x 9) |
|---|---|---|---|---|---|---|
| Vina 1.2.7 | 5 | 14 | | -10.09 | 23 | 129 |
| smina `default` | 5 | 14 | 0 / 0 | -10.05 | 30 | 133 |
| smina `vinardo` | 7 | 15 | 2 / 0 (6A93, 6BQG) | -9.36 | 14 | 130 |
| smina `dkoes_fast` | 2 | 8 | 0 / 3 | -7.97 | 16 | 153 |
| smina `ad4_scoring` | 7 | 11 | 3 / 1 (gained 5HK2, 6BQG, 6KUX; lost 5I6X) | -57.93 | 21 | 70 |

(Wall time was taken with two runs sharing the machine, so it is a rough order, not a speed
comparison. Scores from different functions are not comparable and are not compared.)

**Gates that were passed before reading any count** (this is the lesson of the PLECscore test:
a comparison means nothing unless the inputs reproduce something known):

- The Vina arm reproduced the recorded survey top-pose distance on **17 of 17** receptors, so
  the harness, the ligands, the boxes and the distance still reproduce the committed result.
- smina's `default` reproduced Vina's call on **17 of 17** (0 gained, 0 lost) with a median top
  score of -10.05 against -10.09. That is the control: it is the same function, so the harness
  attributes a difference to the function and not to the engine's plumbing.

**What the numbers say, and do not:**

- `vinardo` and `ad4_scoring` gained receptors whose correct pose Vina ranked lower. 6BQG went
  from a top pose 5.23 A away to 0.89 A (`vinardo`) and 1.47 A (`ad4_scoring`); 6A93 from 4.20
  to 1.41 under `vinardo`.
  `dkoes_fast` did worse than Vina on three receptors that Vina had right and found the right
  pocket less often (4 wrong-pocket calls against 1).
- **None of it is a verdict.** One seed, 17 receptors, 12 of them chosen because Vina missed. A
  receptor that Vina missed will change class under almost any change of seed or function, so
  a few "gained" are what chance alone gives on a loaded sample. With 2 gained and 0 lost the
  one-sided sign-test p is 0.25 for `vinardo`; with 3 and 1, 0.31 for `ad4_scoring`. The full
  test uses three seeds per arm for exactly this reason.
- **The `ad4_scoring` arm's inputs are suspect.** Its top scores run from about -31 to -82, not
  a kcal/mol scale, and it returned 70 poses for 17 receptors (about 4 per receptor, not 9), so
  its "best of nine" and its gains cannot be read like the others. Open Babel's PDBQT may not
  carry the atom types and charges that function expects. This is the same warning as the
  PLECscore test (a confident number from a function fed inputs it does not read) and it is why
  the frozen test has an input gate for it (G5) that later PASSed on the catalog.
- smina's own `--version` states it is based on AutoDock Vina 1.1.2, while the app's Vina is
  1.2.7. Identical calls on 17 of 17 receptors do not mean identical poses on every
  receptor, only that the pilot found no receptor where the two differ.

## Recommendation

1. **Do not add an engine to the application.** The frozen test is overall HARMFUL
   (`artifacts_engine/RESULT.md`). A seam (injected rescorer, engine-qualified rescore id,
   per-engine function vocabularies) and a smina packaging path would be engineering for a
   route that is closed.
2. **The Vina-family scoring-function route is closed.** `smina-default` matched Vina on 46
   of 46. Vinardo is NULL. `dkoes_fast` and `ad4_scoring` are HARMFUL. QuickVina and Vina-GPU
   remain search-only.
3. **The product answer stays PR 508's sentence** (pose 1 is the best-scoring pose, not a
   verified one), plus showing more than the top pose, which needs no new engine.
4. **Learned CNN rescore of these Vina poses is closed NULL**, and **gnina
   default dock is closed NULL.** Slice 1 PASS 2026-11-04. CNN rescore
   `RESULT_GNINA.md` (gained 3 lost 2). Default dock run 2026-11-05:
   `RESULT_GNINA_DOCK.md` (29 deciding, Vina 20/29 vs gnina 21/29, gained 4
   lost 3, p = 0.5).    Not an External Tools tab. `--cnn_scoring all` and
   DiffDock-class were not arms. **CNNaffinity ranking power** is a
   separate freeze (`PREREGISTRATION_CNN_AFFINITY.md`); no catalog
   CNNaffinity yet.
5. **QuickVina and Vina-GPU are worth revisiting only for speed**, never for pose choice, and
   only if a Windows binary with provenance appears.

## Reproducing

```bash
# smina from conda-forge into scratch (outside the repository)
conda create -y -p D:/_scratch/dockeng/smina-env -c conda-forge --override-channels smina=2020.12.10
set OPENCHEM_SMINA=D:\_scratch\dockeng\smina-env\Library\bin\smina.exe
uv run --no-sync python benchmarks/docking/engine_pilot.py --list
uv run --no-sync python benchmarks/docking/engine_pilot.py --arms vina smina-default smina-vinardo smina-dkoes_fast smina-ad4 --out bench-out/engine_pilot
uv run --no-sync python benchmarks/docking/engine_pilot.py --report --out bench-out/engine_pilot
```

Vina's path is read from the application's Settings (`_config.vina_executable`). Real Vina
1.2.7 was used. The 27-file closure was found by walking the PE import tables of `smina.exe`
and its DLLs (a throwaway script in scratch, not committed).

## Limits

- Redocking into the box drawn around the crystal ligand, one ligand conformer per receptor: a
  well-aimed search, optimistic, and silent on a user who boxes by guesswork (as the survey said).
- The distance is an assignment RMSD, a lower bound (`prep_box_core.py`).
- The licence column was read from GitHub's licence field, the conda-forge package metadata, the
  smina source mirror's licence files and the Scripps download page; no licence text was read in
  full, and the closed-source rows were not looked into beyond the one search.
- Vina-GPU's executable was inspected, not run; `QuickVina` was not built. Neither would change
  pose ranking, but "does not run" is not claimed for either.
