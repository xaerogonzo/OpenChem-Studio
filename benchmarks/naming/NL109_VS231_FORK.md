# NL-109 / VS231 — fork notes (cumulene axis)

**Suite entry.** CIP Validation Suite `VS231` (`compounds.smi`):

- SMILES: `CC=[C@]=C1CC[C@H](CC1)CC`
- Labels (2D file): `2p 4p 7s` (atom numbers = SMILES order)
- Labels (3D SDF): `1p 6s 8p` (different numbering; same stereochemistry)
- Rules: Blue Book P-93.5.1.4.2.2; stereo units `TH` + `TH3`; sequence rules `1a,5`

**Measured 2026-11-10 (application, pre-fork).**

| Check | Result |
|---|---|
| Engine name | `1-ethyl-4-(prop-1-en-1-ylidene)cyclohexane` (no `p`, no ring `s`) |
| RDKit non-legacy perception on suite SMILES | No `_CIPCode`; cumulene `[@]` does not survive parsing |
| RDKit after `EmbedMolecule` + `AssignCIPLabels` | Still no labels (TH3 not implemented in rdCIPLabeler here) |
| OPSIN read-back of flat name | Parses connectivity; does not pin stereoisomers |

**Fork direction (not started in application vendor).**

1. **Perception** — Detect cumulene / allene axes (≥3 cumulated double bonds or suite `TH3`). Do not rely on SMILES `@` alone; accept 3D SDF/MOL or embedded coordinates when present, or a dedicated axis-parity reader.
2. **`StereoCenter.type == "axial"`** — Already in `types.py`; `perception/stereo.py` and `_collect_stereo_descriptors` in `engine.py` only handle `tetrahedral` and `double_bond` today. Extend collector to admit `p`/`P`/`M` for `axial` (precedent: `_STEREO_LOCANT_PREFERENCE` already lists `M`/`P`).
3. **Placement** — VS231 stereo sits on the **ylidene substituent** (`prop-1-en-1-ylidene`), not the cyclohexyl parent; descriptor collection must follow substituent-tree assembly, not only parent `_collect_stereo_descriptors`.
4. **Validation** — OPSIN may not read `p`; keep `_validate_stereo_via_opsin` gate; strict `xfail` in `tests/test_namer_nl109_vs231_cumulene_axis.py` until read-back pins.

**Regression target.** When implemented: name carries at least one locant–`p` pair (regex `\d+p`, not the substring `prop`), and (if OPSIN allows) read-back to input InChIKey.
