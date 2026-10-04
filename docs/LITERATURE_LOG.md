# Literature log: what was looked at, and what came of it

`docs/sources.toml` (rendered as `docs/SOURCES.md`) is the **guarded provenance registry**: an entry
there must back something a tracked file uses, and is checked. This log is the other half, and it exists
so that a later session does not repeat a search: **every paper that was opened for a question, including
the ones that turned out not to answer it**, with what it was read for, how deeply, and what was found.

It is hand-edited and checked by nothing, on purpose: a negative result ("this paper is not an energy
source") is exactly what a guard on `used_by` cannot hold. Where a paper IS in the registry its `key`
is given and the registry entry is authoritative for the citation. Identity details below are the ones
printed in the file itself (DOIs are deliberately not repeated here: the DOI guard requires every DOI in a tracked document to be in the registry, and this log is for papers that are not); where a file prints less (a scan, an author manuscript) this says so rather
than filling the gap. Files are in Alex's `Sci Downloads`.

**Read depth** is stated per entry: *full* (read through for the claim), *tables* (the relevant tables
read), *identity + abstract* (first pages only: do not treat the verdict as more than that), *scan*
(no text layer).

## Tautomer energetics (Phase O and Phase R)

| file | what it is | read for | depth | outcome | registry key |
|---|---|---|---|---|---|
| `trygubenko2002.pdf` | Cytosine, 5 gas-phase structures, CCSD(T) to the basis-set limit (PCCP 4, 4192) | the cytosine row | tables | the criteria-v1/v2 cytosine reference | `trygubenko2002` |
| `belova2014.pdf`, `belova2014_si.pdf` | Acetylacetone enol/diketo (J. Org. Chem. 79) | the acetylacetone row | tables + SI energies | SI energies used, not Table 1: Table 1 and the SI disagree on two B3LYP labels | `belova2014` |
| `fogarasi2010.pdf` | Converged tautomerization energies, small systems (J. Mol. Struct. 978) | acetaldimine/vinylamine and two optional rows | tables | used | `fogarasi2010` |
| `goller2022.pdf`, `Göller2022_si/` | Tautomer benchmark, DLPNO-CCSD(T)/def2-QZVPP (J. Comput.-Aided Mol. Des.) | 2-pyridone row; held-out indazole and hypoxanthine | full + Table 1 positional extraction | Table 1 fails its own checksum for adenine and 1,2,3-triazole; the SI names fix structure identity but carries no absolute CCSD(T) energies | `goller2022` |
| `balabin2009.pdf` | Triazoles, focal-point CCSD(T)/CBS (J. Chem. Phys. 131, 154307) | held-out triazole rows | Table III full | used; its 3.98 equals Goller's implied gas value, which identifies Goller's printed 4.36 as the typo | `balabin2009` |
| `hanus2004.pdf` | Adenine tautomers, RI-MP2/TZVPP | adenine as a held-out system | tables | RI-MP2, not coupled cluster, so it fails the selection rule: adenine excluded | `hanus2004` |
| `Catalán1996.pdf` | Importance of aromaticity on the relative stabilities of indazole annular tautomers, ab initio (J. Chem. Soc., Perkin Trans. 2, 1996) | indazole corroboration | tables | MP2 3.6 kcal/mol, sign and rough size only | `catalan1996` |
| `Brovarets2013.pdf` | Hypoxanthine, 21 tautomers, MP2 | hypoxanthine ordering | tables | ordering only, no number transcribed | `brovarets2013` |
| `ganyecz2019.pdf` | Thermochemistry of uracil, thymine, cytosine, adenine (J. Phys. Chem. A 123, 4057) | adenine and cytosine tautomers | full | adenine only as the canonical form, so it does NOT rescue adenine; cytosine only for tautomers | `ganyecz2019` |
| `Barone2023.pdf`, `Barone2023_si.pdf` | Cytosine tautomers, CCSD(T)-F12 composite (J. Chem. Theory Comput. 19, 4970) | cytosine corroboration | abstract + Table 4 located | relative electronic energies in cm-1; a second look at the existing cytosine system, nothing transcribed | `barone2023` |
| `Perry2025.pdf`, `Perry2025_si/` | Tautomerism in crystal structure prediction, DLPNO-CCSD(T1) benchmark (author manuscript) | which functionals to screen | full for the functional-ranking passage | wB97M-V and revDSD-PBEP86-D4 best, routine GGA/hybrids poor; M06-2X not mentioned; large drug-like systems | `perry2025` |
| `moreno1990.pdf` | 2-pyridone/2-hydroxypyridine, CISD/DZP | the pyridone row | full | too uncertain (its own cited literature spans about 5 kcal/mol): corroboration | none (no DOI printed) |
| `rendell1993.pdf` | 2-pyridone, distributed CCSD(T) | the pyridone row | full | small bases, SCF geometries, best estimate adds zero-point: not an electronic energy | `rendell1993` |
| `Hejazi 2016.pdf` | 2-hydroxypyridine/2-pyridone, CCSD | the pyridone row | full | zero-point-inclusive totals: not the declared quantity | `hejazi2016` |
| `fogarasi2008.pdf` | Cytosine dynamics; cites CCSD(T) ranges | cytosine uncertainty | read | secondary citation, places 3a about 1 kcal/mol from Trygubenko | none |
| `delchev2001.pdf` | Acetylacetone, HF/BLYP | acetylacetone | read | its 0.008725 a.u. includes zero-point corrections | none |
| `rzepiela2020.pdf` | Uracil, six tautomers, B3LYP-D3 | uracil cross-check | read | second-lowest more than 10 kcal/mol up: lopsided, not a reference | none |
| `wieder2021.pdf` | Solution and vacuum free-energy ratios, ML potential | tautomer populations | read | a different quantity (free energy): not eligible | none |

## Held-out candidates and gap-fillers that did NOT become references (second and third rounds)

| file | what it is | read for | depth | outcome |
|---|---|---|---|---|
| `Begtrup1988.pdf` | 15 pages, no text layer, so its title was not read | a possible indazole/azole value | **scan, no text layer** | skimmed as images in an earlier session; not used. Anything transcribed from it would need an image read |
| `cox1990.pdf` | 1,2,3- and 1,2,4-triazole tautomerism, gas phase and aqueous (J. Phys. Chem. 94, 5499) | triazole gas-phase energies | abstract confirmed this session; earlier reading not recorded | MP2/6-31G**//3-21G **with zero-point effects**: not the electronic quantity; corroboration of which tautomer is lower |
| `davarski1998.pdf` | Quantum-chemical study of 1,2,3- and 1,2,4-triazoles (Chem. Heterocycl. Compd. 34, no. 5) | triazole energies | abstract confirmed this session; earlier reading not recorded | semiempirical and MP2: not coupled cluster; agrees on 2H-1,2,3 and 1H-1,2,4 being more stable |
| `anandan2004.pdf` | Five tautomeric forms of indazole, MP2/B3LYP/B3PW91 6-311G(2d,2p) (J. Mol. Struct. THEOCHEM) | indazole | abstract confirmed this session; earlier reading not recorded | not coupled cluster: fails the selection rule |
| `Kim2007.pdf` | Adenine 9H to 7H and 9H to 3H tautomerization facilitated by water (J. Phys. Chem. A) | adenine tautomer energies | identity + abstract | a microsolvation barrier study, not a gas-phase electronic-energy reference |
| `Claramunt2024.pdf`, `Claramunt2024_si.pdf` | Addition of azoles to acetone-d6, NMR and computation | triazole corroboration | read in an earlier session; the quoted figures are from that reading | cites 26.1 kJ/mol CCSD(T)/cc-pCVTZ for 4H-1,2,4-triazole (matching Balabin's 6.25 kcal/mol) and 15.9 kJ/mol for 1,2,3-triazole **including ZPVE**: corroboration only |
| `Rybczyński2023.pdf`, `Rybczyński2023_si/` | Tautomeric equilibrium in 1-benzamidoisoquinoline derivatives, Molecules 28, 1101 | whether DLPNO-CCSD(T) reorders DFT | skimmed in an earlier session | DMSO solution, wB97X-D/def2-TZVP; only the methodological point. Not a reference |
| `alkorta2022.pdf` | NH-indazoles with formaldehyde in HCl, NMR and crystallography (J. Org. Chem. 87, 5866) | an indazole energy | **identity + abstract only** | a reaction-mechanism study, not a tautomer-energy source: nothing used |
| `kim2008.pdf` | Densities of solid energetic molecules from surface electrostatic potentials (J. Comput. Chem.) | (it was suggested as a "Kim" tautomer paper) | identity | **not a tautomer paper at all**; unrelated to this work |

## How to use this

Before searching for a reference for a tautomer system, look here. A paper listed as "not an energy
source" or "fails the selection rule" fails it **for the reason given**, which may not be the reason the
next question cares about. Add a row when a paper is opened, even if it is dropped in the same minute.
