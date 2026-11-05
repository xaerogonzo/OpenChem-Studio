# NL-011 triage — seed 8901 (re-measured 2026-11-04)

Worktree `D:\_scratch\OpenChem-Studio-naming-r94` at `origin/master` (`16b8b5ea`).

Generator: `tools/nl011_seed8901_measure.py` (round-88 spiro `join`, extended by one joint; 225 polycyclic curated rings + 14 bridged partners; seed `8901`; 30 tries → 20 chains, 10 rejected).

Artifact: `benchmarks/naming/artifacts_nl011_seed8901.json`

Oracle: connectivity InChIKey (first 14 chars). OPSIN 2.9.0 via py2opsin, unique temp file per call.

## Summary (after bucket A fix, 2026-11-04)

| Outcome | Count | Notes |
|--------|------:|-------|
| **ok** (read-back) | **19** | Was 3 before VB locant fallback on multicomponent components |
| **wrong** read-back | **1** | #13: `1-methyldispiro[...]` vs flat without methyl (substituent prefix) |
| **unparsable** flat name, OPSIN empty | **0** among former nested three; **14** others unchanged (bucket B) |
| **nested** `spiro[spiro[...]]` | **0** | #10, #16, #17 now flat `dispiro[...]` |

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

OPSIN returns empty for the emitted string (validator limitation unless a spelling variant parses).

Common shapes in the flat string:

- Middle or end partner is **`bicyclo[2.1.1]hexane`** (many chains).
- Retained / fusion names inside brackets: e.g. `5H-2,3-benzodiazepine`, `3,4,5,6-tetrahydroimidazo[4,5-d][1]benzazepine`, `octahydropyridazino[1,2-a][1,2]diazepine`, `5H-dibenzo[a,d][7]annulene`, `hexahydrofuro[2,3-b]furan`.
- Von-Baeyer tricyclo partners with **`0^{3,6}`** or **`4-azatricyclo[4.3.1.1^{3,8}]`**.

**#13 extra:** N-methyl on a bridged partner → engine prefixes `1-methyl` on the whole dispiro name while the composer omits it; probe whether flat name should carry substituent locants on the correct component.

**Next step:** for each row, run `D:\_scratch\r60\r80\op.py`-style candidate names (retained spelling variants, prime/locant permutations) and classify **fixable spelling** vs **OPSIN gap** before filing OPEN rows.

## Command

```powershell
$env:JAVA_HOME = "D:\Random Programs\OpenChemStudio_Data\jre\jdk-21.0.12+8-jre"
cd D:\_scratch\OpenChem-Studio-naming-r94
uv run --no-sync python tools/nl011_seed8901_measure.py --json benchmarks/naming/artifacts_nl011_seed8901.json
```
