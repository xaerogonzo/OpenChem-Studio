# Engine pose-ranking test

From `PREREGISTRATION_ENGINE.md`, frozen 2026-11-04. Primary comparison is each
candidate against `vina`. `smina-default` is beside it (search-code control).

Deciding receptors: 46 (G4 dropped 4PE5; training overlap none).
Rows: 690 / 690.

## Control (`smina-default` vs `vina`)

compared 46, gained 0, lost 0, unchanged 46, net +0, p=1.
Neutral at two-sided 0.05: **yes**.

## Candidates (primary vs `vina`)

| Arm | vs vina | vs smina-default |
|---|---|---|
| `smina-ad4` | HARMFUL (compared 46, gained 3, lost 15, unchanged 28, net -12, p=0.003769) | HARMFUL (compared 46, gained 3, lost 15, unchanged 28, net -12, p=0.003769) |
| `smina-dkoes_fast` | HARMFUL (compared 17, gained 0, lost 8, unchanged 9, net -8, p=0.003906) | HARMFUL (compared 17, gained 0, lost 8, unchanged 9, net -8, p=0.003906) |
| `smina-vinardo` | NULL (compared 20, gained 0, lost 1, unchanged 19, net -1, p=0.5) | NULL (compared 20, gained 0, lost 1, unchanged 19, net -1, p=0.5) |

Overall (gates plus primary): **HARMFUL**.
