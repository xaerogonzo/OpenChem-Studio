# NL-109 / VS231 — cumulene axis

**Suite entry.** CIP Validation Suite `VS231` (`compounds.smi`):

- SMILES: `CC=[C@]=C1CC[C@H](CC1)CC`
- Labels (2D file): `2p 4p 7s` (atom numbers = SMILES order)
- Labels (3D SDF): `1p 6s 8p` (different numbering; same stereochemistry)
- Rules: Blue Book P-93.5.1.4.2.2; stereo units `TH` + `TH3`; sequence rules `1a,5`

**Measured 2026-11-10 (application, after helix + paired tetra).**

| Check | Result |
|---|---|
| Engine name | `(1s)-1-ethyl-4-[(1p)-prop-1-en-1-ylidene]cyclohexane` |
| Opposite allene `=[C@@]=` | `(1r)-1-ethyl-4-[(1m)-prop-1-en-1-ylidene]cyclohexane` |
| Opposite ring `[C@@H]` | `(1r)-1-ethyl-4-[(1p)-prop-1-en-1-ylidene]cyclohexane` |
| RDKit non-legacy perception on suite SMILES | No `_CIPCode`; cumulene `[@]` does not survive parsing |
| RDKit after `AssignCIPLabels` | Still no labels (TH3 not implemented in rdCIPLabeler here) |
| Ring centre (suite `7s`) | `FindMolChiralCenters` → `(6, "?")`; engine letter `s` from pairing the SMILES `@` with the helix |

**What shipped.** `perception/cumulene.py` restores a helical letter from the SMILES winding onto an even-cumulene centre (`_CumuleneHelix`, `_CIPCode`). `CHI_TETRAHEDRAL_*` on an allene makes `AssignCIPLabels` raise, so no chiral tag is set. A second SMILES `@`/`@@` that RDKit leaves unassigned is paired with that one helix (`_CumulenePairedTetra`): `p` with `@` is `s` (the suite's labelled point); flipping either bit flips the letter. `StereoAnalysis` emits `axial` and the paired tetrahedral. The axis is cited on the carved ylidene (attachment locant 1); the ring letter is `(1s)` on the ethyl carbon.

**Limitation.** Helical sense and the paired `r`/`s` are that mapping, not a full CIP ranking of the extended tetrahedron.
