# NL-109 / VS231 — cumulene axis

**Suite entry.** CIP Validation Suite `VS231` (`compounds.smi`):

- SMILES: `CC=[C@]=C1CC[C@H](CC1)CC`
- Labels (2D file): `2p 4p 7s` (atom numbers = SMILES order)
- Labels (3D SDF): `1p 6s 8p` (different numbering; same stereochemistry)
- Rules: Blue Book P-93.5.1.4.2.2; stereo units `TH` + `TH3`; sequence rules `1a,5`

**Measured 2026-11-10 (application, after cumulene stamp).**

| Check | Result |
|---|---|
| Engine name | `1-ethyl-4-[(1p)-prop-1-en-1-ylidene]cyclohexane` |
| Opposite winding `=[C@@]=` | `1-ethyl-4-[(1m)-prop-1-en-1-ylidene]cyclohexane` |
| RDKit non-legacy perception on suite SMILES | No `_CIPCode`; cumulene `[@]` does not survive parsing |
| RDKit after `AssignCIPLabels` | Still no labels (TH3 not implemented in rdCIPLabeler here) |
| Ring centre (suite `7s`) | `FindMolChiralCenters` → `(6, "?")`; not cited |

**What shipped.** `perception/cumulene.py` restores a helical letter from the SMILES winding onto an even-cumulene centre as atom properties (`_CumuleneHelix`, `_CIPCode`). `CHI_TETRAHEDRAL_*` on an allene makes `AssignCIPLabels` raise, so no chiral tag is set. `StereoAnalysis` emits `type="axial"`; `_collect_stereo_descriptors` admits `p`/`P`/`m`/`M`; assembly stereo groups include those letters. The axis is cited on the carved ylidene (attachment locant 1), not as two end-atom labels.

**Still open.** Cyclohexyl `s`. Helical sense is the SMILES `@`/`@@` mapping, not a full CIP ranking of the extended tetrahedron.
