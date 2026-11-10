# NL-011 triage — seed 8901 (re-measured 2026-11-05)

Worktree `D:\_scratch\OpenChem-Studio-naming-r94` on `claude/naming-r94-nl011-13-methyl` (includes app #552 on master).

Generator: `tools/nl011_seed8901_measure.py` (round-88 spiro `join`, extended by one joint; 225 polycyclic curated rings + 14 bridged partners; seed `8901`; 30 tries → 20 chains, 10 rejected).

Artifact: `benchmarks/naming/artifacts_nl011_seed8901.json`

Oracle: connectivity InChIKey (first 14 chars). OPSIN 2.9.0 via py2opsin, unique temp file per call.

## Summary (after bucket A + bucket C narrow, 2026-11-06)

| Outcome | Count | Notes |
|--------|------:|-------|
| **ok** (OPSIN read-back) | **19** | Bucket A VB locants; bucket C narrow restored #6/#7/#14 |
| **unparsable** flat name | **1** | **#13** only — engine cites `8-methyl-8-azabicyclo[...]` inside `dispiro[...]`; OPSIN 2.9.0 empty (validator; strict xfail in tests) |
| **wrong** read-back | **0** | |
| **nested** `spiro[spiro[...]]` | **0** | |

Prior baseline (pre-fix): 3 ok, 14 unparsable flat, 3 nested — see git history for `artifacts_nl011_seed8901.json`.

## Three nested names (fixed round 94 bucket A)

Root cause: `_spiro_locants_for_component` → `_component_fallback_locants` returned `None` for bridged von-Baeyer partners (`bicyclo[2.1.1]hexane`, `bicyclo[2.2.2]octane`, …) with empty `numbering_options`. Fix: `_vb_spiro_locants_for_submol` (same VB pin as D-381/D-382).

| # | SMILES | Flat name (pinned in `tests/test_namer_round94_nl011_multicomponent_vb_locants.py`) |
|---|--------|------|
| 10 | `C1C2CC1C1(C2)CC2CC1C1(C2)C2CC1C2` | `dispiro[bicyclo[2.1.1]hexane-2,6'-bicyclo[2.2.1]heptane-2',2''-bicyclo[1.1.1]pentane]` |
| 16 | `C1CC2CCC1CC21C2CC3CC(C2)C2(CC4CC2C4)C1C3` | `dispiro[bicyclo[2.1.1]hexane-2,4'-adamantane-2',2''-bicyclo[2.2.2]octane]` |
| 17 | `C1CC2C3(CC1CC21C2CC4CC(C2)C41)C1CNC2CC(C1)CC3C2` | `dispiro[tricyclo[3.2.1.0^{3,6}]octane-7,2'-bicyclo[2.2.2]octane-6',7''-4-azatricyclo[4.3.1.1^{3,8}]undecane]` |

## Three read-backs (unchanged pins; more chains now ok)

| # | Key (conn) | Defect | SMILES (canonical) |
|---|------------|--------|---------------------|
| 1 | `BELKMPVYYYQUKB` | D-390 | `C1C2CC3CC1CC(C2)C31CCC2OC1CC21CN2CCC1CC2` |
| 8 | `OZYQERXLZFIDFK` | D-393 | `C1CCC2CC3(CCC2C1)C1CC2CC3OC3(CC4CCN3CC4)C(C2)C1` |
| 11 | `KBVHVYJVELUXHJ` | D-394 | `C1NC2CC3CC1CC(C21C2CC4CC(C2)CC1C4)C31C2CC3CC1C3C2` |

## Fourteen OPSIN-unparsable flat names (round 94 target B)

**Update after bucket B probes (2026-11-05):** see `benchmarks/naming/NL011_BUCKET_B_OPSIN_PROBE.md` and `artifacts_nl011_bucket_b_probe.json`. Of the fourteen baseline (`fa3a0115`) flat strings, **13** are fixed for OPSIN by **bucket A locants** (today's emitted name reads back). **None** of those thirteen are bare OPSIN spelling gaps. **#13** remains: wrong read-back (methyl prefix / wrong component), not empty parser output.

Historical note — common shapes in the **baseline** flat strings (before locant fix):

- Middle or end partner is **`bicyclo[2.1.1]hexane`** (many chains).
- Retained / fusion names inside brackets: e.g. `5H-2,3-benzodiazepine`, `3,4,5,6-tetrahydroimidazo[4,5-d][1]benzazepine`, `octahydropyridazino[1,2-a][1,2]diazepine`, `5H-dibenzo[a,d][7]annulene`, `hexahydrofuro[2,3-b]furan`.
- Von-Baeyer tricyclo partners with **`0^{3,6}`** or **`4-azatricyclo[4.3.1.1^{3,8}]`**.

**#13 extra:** N-methyl on a bridged partner → engine prefixes `1-methyl` on the whole dispiro name while the composer omits it; bucket B probes found **no** connectivity-correct OPSIN spelling in the locant/methyl variant set (see probe doc).

**Probe command:**

```powershell
uv run --no-sync python tools/nl011_bucket_b_opsin_probe.py --json benchmarks/naming/artifacts_nl011_bucket_b_probe.json
```

## Command

```powershell
$env:JAVA_HOME = "D:\Random Programs\OpenChemStudio_Data\jre\jdk-21.0.12+8-jre"
cd D:\_scratch\OpenChem-Studio-naming-r94
uv run --no-sync python tools/nl011_seed8901_measure.py --json benchmarks/naming/artifacts_nl011_seed8901.json
```
