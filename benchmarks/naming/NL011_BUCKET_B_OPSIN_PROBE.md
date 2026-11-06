# NL-011 bucket B — OPSIN probes (seed 8901)

Measured 2026-11-05 on worktree `D:\_scratch\OpenChem-Studio-naming-r94` (post bucket A, `c870fdcd`).

**Population:** the fourteen chains whose **baseline** flat `dispiro[...]` was OPSIN-unparsable at measure `fa3a0115` (indices 2, 3, 4, 5, 6, 7, 9, 12, 13, 14, 15, 18, 19, 20). Baseline strings are pinned in `benchmarks/naming/artifacts_nl011_bucket_b_baseline_flats.json`.

**Oracle:** connectivity InChIKey (first 14 chars), same as the matrix.

**Method:** `tools/nl011_bucket_b_opsin_probe.py` — op.py-style read-back (`py2opsin` + key match). For each chain it tries, in order:

1. Baseline flat (fa3a0115), today's composer flat, today's emitted name.
2. Locant sweeps on spiro citation digits (1–9).
3. Small spelling set (bridge superscript `0^{3,6}` vs `0(3,6)`, `decahydronaphthalene` vs `decalin`, retained `5H-` variants, whole-name `1-methyldispiro` prefix).

Cap: 120 candidates per chain (enough to cover the sweeps without nested cross-products). Full rows: `benchmarks/naming/artifacts_nl011_bucket_b_probe.json`.

## Summary

| Classification | Count | Meaning |
|----------------|------:|---------|
| **resolved_emitted** | **13** | Today's emitted name reads back on the oracle. Baseline flat was unparsable; failure was **wrong spiro locants** (bucket A), not an OPSIN-only spelling gap. |
| **parses_wrong_only** | **1** | **#13** — OPSIN parses many variants but **none** match the oracle in the probe window; emitted `1-methyldispiro[...]` reads back as a **different** connectivity key. |

**OPSIN gap (empty SMILES on all tried strings):** **0** of 14 at today's emitted spelling.

**Baseline flat unparsable:** **14** of 14 (`baseline_ok: false` on every row).

## Per-chain (compact)

| # | Baseline flat OPSIN | Emitted today | Probe class | Note |
|---|---------------------|---------------|-------------|------|
| 2 | empty | ok | resolved_emitted | Locants `nonane-1,` → `nonane-2,` |
| 3 | empty | ok | resolved_emitted | `bicyclo211` citation `4',1'` → `2',5'` |
| 4 | empty | ok | resolved_emitted | Quinuclidine / norbornane locants re-pinned |
| 5 | empty | ok | resolved_emitted | `hexane-1,` → `hexane-2,` |
| 6 | empty | ok | resolved_emitted | `hexane-1''` → `hexane-2''` |
| 7 | empty | ok | resolved_emitted | Double `bicyclo211` locants |
| 9 | empty | ok | resolved_emitted | `pentane-1',1''` → `pentane-2',7''` |
| 12 | empty | ok | resolved_emitted | `hexane-1',5'` → `hexane-5',2'` |
| 13 | empty | **wrong key** | parses_wrong_only | N-methyl on tropane; see below |
| 14 | empty | ok | resolved_emitted | All three partner locants moved |
| 15 | empty | ok | resolved_emitted | Heptane / nonane citations |
| 18 | empty | ok | resolved_emitted | Decalin arm + tricyclo tail locants |
| 19 | empty | ok | resolved_emitted | `hexane-1,` → `hexane-2,` |
| 20 | empty | ok | resolved_emitted | `pentane-1,8'` → `pentane-2,3'` |

Several rows also have **alternate locant spellings** that OPSIN accepts (listed under `fixable_hits` in the JSON). The engine already emits one valid hit on 13 chains; those alternates are ambiguity noise, not blockers for the matrix.

## Chain #13 (remaining NL-011 failure)

| Field | Value |
|-------|--------|
| Key | `RLWFDXNXMRUBBS` |
| Emitted | `1-methyldispiro[bicyclo[2.1.1]hexane-5,10'-4-azatricyclo[4.3.1.1^{3,8}]undecane-7',3''-8-azabicyclo[3.2.1]octane]` |
| Composer flat (no prefix) | `dispiro[bicyclo[2.1.1]hexane-5,10'-…]` — OPSIN parses but key `SBMVPSBBUUQVCV` (wrong molecule) |
| Emitted read-back key | `NWCFKYNBWOBWCB` (wrong) |

Ad-hoc methyl-on-component probes (`8-methyl-8-azabicyclo…`, `N-methyl-4-azatricyclo…`, `-octane-8-methyl` inside dispiro) were **unparsable** in OPSIN 2.9.0. This row is **engine substituent placement** on the multicomponent chain (round 94 bucket C / separate defect), not fixable by locant sweep alone.

## Commands

```powershell
$env:JAVA_HOME = "D:\Random Programs\OpenChemStudio_Data\jre\jdk-21.0.12+8-jre"
cd D:\_scratch\OpenChem-Studio-naming-r94
uv run --no-sync python tools/nl011_bucket_b_opsin_probe.py --json benchmarks/naming/artifacts_nl011_bucket_b_probe.json
```

## Conclusion for bucket B

The fourteen baseline flats were **validator-unfriendly locant choices** on von-Baeyer / dispiro citations. After bucket A, **13/14** read back on the emitted name. **No OPEN OPSIN defect** is justified for those thirteen from this probe. **#13** stays an **engine** item (methyl on the tropane-bearing component, not whole-name `1-methyldispiro`).
