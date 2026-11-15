# Blue Book V3 (corrected PDF, local)

IUPAC publishes corrected HTML and PDF at [iupac.qmul.ac.uk/BlueBook/](https://iupac.qmul.ac.uk/BlueBook/). **Version 3** (merged PDF, 6 Dec 2023) is at [BlueBookV3.pdf](https://iupac.qmul.ac.uk/BlueBook/PDF/BlueBookV3.pdf).

## Local copy

| | |
|---|---|
| Path | `D:\Xaero Stuff\Documents\Sci Downloads\BlueBookV3.pdf` |
| Pages | 1149 |
| SHA-256 | `10790680e7edd0582eac0a4d96e4a5fcca9796b4d4189cfef2a67cf6ba4cf0e1` (measured 2026-11-15) |

## Relation to the repo pin

Adjudication and `bluebook_protocol.toml` still record **`BlueBookV2.pdf`** and its SHA-256. New WS3 source lookups (e.g. **NL-023**) may cite **V3 page numbers**; changing the harvest or adjudication pin to V3 is a separate, explicit migration (re-hand-check samples, update `docs/sources.toml`).

Read V3 with the same pymupdf workflow as V2 (`docs/NAMING_ROUNDS.md`, round 87 notes).

## WS1 sweep — NL-002 bridgehead oracle (2026-11-15)

Searched local **V3** PDF (SHA above) for substituted bridgeheads and `bicyclo[3.3.1]` stereochemistry. Paired with the CIP suite table in [CIP_VALIDATION_SUITE.md](CIP_VALIDATION_SUITE.md).

| Section | V3 pages | Finding |
|---------|----------|---------|
| P-93.5.2.1 | 929 | `(1S,3R,5R,7R)-3-amino-5-bromoadamantan-1-ol` — full **R/S** on **tricyclo[3.3.1.1^{3,7}]** with **1-bridgehead alcohol** and **5-bromo** on a non-bridgehead corner; closest chemistry to “bridgehead OH + remote halogen”, not plain `bicyclo[3.3.1]nonane`. |
| P-93.5.2.2.1 | 930–931 | `endo`/`exo`/`syn`/`anti` for substituents on **non-bridgehead** atoms in bicyclo[*x.y.z*]alkanes, including **bicyclo[3.3.1]nonane**; tropane 3-ol examples with `r`/`s` (aligns with **NL-001**; V2 cited pp. 937–938). |
| P-93.5.2.2.2 | 931 | `rel-(1R,10R)-1-methylbicyclo[8.3.1]tetradecane` — **cis**/**trans** only when a ligand sits **on a bridgehead** (methyl on C1/C10), not the NL-002 skeleton. |

Text search: no `9-chloro` example; no worked **9-chlorobicyclo[3.3.1]nonan-1-ol** PIN. **NL-002** closed 2026-11-15 with a **partial oracle** (`tests/test_namer_nl002_ws1_partial_oracle.py`): suite + RDKit on pre-validation + cage alcohol analogue; no exact PIN on this skeleton.