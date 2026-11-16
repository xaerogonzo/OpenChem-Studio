# CIP Validation Suite (local oracle)

The [CIP Validation Suite](https://github.com/CIPValidationSuite/ValidationSuite) (Hanson *et al.*, *J. Chem. Inf. Model.* **2018**, 58, 1755; [DOI 10.1021/acs.jcim.8b00324](https://doi.org/10.1021/acs.jcim.8b00324)) is the programme's second stereo oracle beside the Blue Book. OpenChem does not vendor it; the files live on disk next to other maintainer corpora.

## Local path (this machine)

| Item | Value |
|------|--------|
| Root | `E:\My Area\Documents\OpenChem Studio literature\CIPValidationSuite\` |
| SMILES + labels | `compounds.smi` (288 rows, measured on upstream commit below) |
| 2D / 3D | `compounds_2d.sdf`, `compounds_3d.sdf` |
| Upstream | https://github.com/CIPValidationSuite/ValidationSuite |
| Pinned commit | `6b9f9db46dadc6749da8234b05164e1e0fb413b9` (master, cloned 2026-11-15) |
| Size | ~1.6 MB total |

Override with environment variable `OPENCHEM_CIP_SUITE` pointing at the directory or at `compounds.smi` directly.

## Probe

```text
uv run --no-sync python tools/naming_cip_suite_probe.py list
uv run --no-sync python tools/naming_cip_suite_probe.py pinned
uv run --no-sync python tools/naming_cip_suite_probe.py bridgehead-candidates
```

`pinned` re-checks the four suite rows already wired in the naming tests (VS207, VS214, VS279, VS231). `bridgehead-candidates` lists **P-93.5.2** bridgehead / norbornane–tropane rows (rule column and pinned ids — SMILES never spell `bicyclo[…]`) and prints whether any `bicyclo[3.3.1]` row exists (**NL-002**).

### P-93.5.2 bridgehead rows (measured 2026-11-15 on pinned commit)

| Suite id | Labels | Rule | Scaffold (informal) |
|----------|--------|------|---------------------|
| VS111 | 2S 3S 5R 6S | P-93.5.2.2.1 | halo norbornane |
| VS159 | 2R 3R 5S 6S | P-93.5.2.2.1 | methyl norbornane |
| VS235 | 3S 5r 7R 12S | P-93.5.2.2.1 | N-tropane ester (NL-001 family) |
| VS238 | 2s 3S 7R | *(empty)* | 8-methylbicyclo[3.2.1]octane analogue |
| VS241 | 2s 4S 6R | P-93.5.2.2.1 | tropane-3-ol |

No row carries `bicyclo[3.3.1]` in SMILES or labels — **NL-002** (`9-chlorobicyclo[3.3.1]nonan-1-ol`) still has no suite oracle.

## Programme use

- **NL-107 / NL-109** — terminal-ring numbering and legacy-perception stereo (round 92; VS231 in NL-109).
- **NL-001** — extend descriptor checks to VS111, VS159, VS235, VS241 (same book section as closed limit).
- **NL-002** — closed 2026-11-15 with partial oracle (`tests/test_namer_nl002_ws1_partial_oracle.py`): five P-93.5.2 rows above; still no `bicyclo[3.3.1]` row on the representative molecule.