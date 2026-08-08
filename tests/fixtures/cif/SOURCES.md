# CIF fixtures, and where they came from

All six are real depositions from the **Crystallography Open Database**
(<https://www.crystallography.net/cod/>), kept here because a reader that
has only ever parsed a file this project wrote is not a reader that has
been tested.

Each file states its own `_cell_volume` and `_exptl_crystal_density_diffrn`,
computed by the depositor's software from the depositor's structure. That
is why these are worth more than any fixture we could author: reproducing
those two numbers exercises parsing, symmetry expansion, wrapping,
deduplication, composition and cell volume **against a value this project
did not produce**.

| COD | what it exercises |
| --- | --- |
| 1504676 | triclinic; `;` text fields; quoted values with commas |
| 7717378 | triclinic, 120 sites, uranium |
| 1511792 | **disorder groups**; atom labels containing apostrophes (`N2'`, `H6'1`) |
| 1569411 | **partial occupancy on a special position**; modern `_space_group_*` tags |
| 1004002 | 238 sites, tungsten, two-site disorder |
| 1502211 | C-centred orthorhombic, 8 operations, 1488 atoms, heavy solvent disorder |

## Licences

**Public domain**, by COD's own statement ("All data on this site have
been placed in the public domain by the contributors"):
1504676, 7717378, 1511792, 1004002, 1502211.

**1569411 is different and requires attribution.** Its COD header states
that the original data were provided by IUCr Journals and that the file
"may be used within the scientific community so long as proper
attribution is given to the journal article from which the data were
obtained". That article is:

> Bravetti, F., Tapmeyer, L., Skorodumov, K., Alig, E., Habermehl, S.,
> Hühn, R., Bordignon, S., Gallo, A., Nervi, C., Chierotti, M. R. &
> Schmidt, M. U. (2023). *Leucopterin, the white pigment in butterfly
> wings: structural analysis by PDF fit, FIDEL fit, Rietveld refinement,
> solid-state NMR and DFT-D.* **IUCrJ 10**, 448–463.
> <https://doi.org/10.1107/S2052252523004281>

The other five carry publication references in their own headers.
