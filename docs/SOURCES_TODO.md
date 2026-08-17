# Sources: what is still open

Handoff for the next session working on provenance. `docs/SOURCES.md` is the
registry; this file is the list of what it cannot yet stand behind.

**Delete this file when it empties.** It is a work list, not documentation,
and a stale work list is worse than none.

## Derive the numbers, don't read them

```bash
uv run --no-sync python -c "import tomllib,pathlib;s=tomllib.loads(pathlib.Path('docs/sources.toml').read_text(encoding='utf-8'))['source'];[print(f\"{e['key']:26} {e['kind']:14} {e['citation'][:70]}\") for e in s if e['verification']=='unverified']"
```

At the time of writing: **58 sources, 20 `citation_and_claim`, 31
`citation`, 7 `unverified`** — of which three are terminal, so **four real
gaps remain.**

## What the verification pass closed

The first draft of this file had a Tier 1 of one entry, `vogel_drago1996`,
described as *"the weakest link in the project"*. It is closed, and closing
it **found a defect in shipped data**: every one of the 53 shipped Drago E/C
parameters was checked against Table 1 of the paper, 52 matched exactly, and
methylamine's `C_B` was shipped as 3.13 where the table prints 3.12. Fixed in
`tools/build_lewis_parameters.py`; it does not move the validation MAE.

Also closed: `allred1961`, `aqsoldb`, `gutmann_frontiers2022`, `ich_m9`,
`tdc_admet`, `autodock_vina`, `pkasolver`, `adoptium_temurin`,
`dimorphite_dl`, `crc_handbook`.

**`crc_handbook` closed by dissolving the question.** "Which edition" was
the wrong one: with the 97th in hand, **no number in this project came from
any edition**. The lattice targets are [source:kaya2022]'s; the CRC column
in `lattice_energy.py` is [source:jenkins1999]'s own ref 40, taken from
Jenkins' table; the electronegativities are [source:allred1961]'s. It is
`reference_only` now.

**And it falsified a claim in shipped data.** `electronegativity.json` said
the Allred set is "reproduced in the CRC Handbook". Against table 9-103 of
the 97th: **72 of 85 agree, 13 do not** — because that table gives values
"for the most common oxidation state", a different quantity. No shipped
value is wrong; the word "reproduced" was, and has been corrected.

**`kaya2022` was added, and it was missing for an instructive reason.** It
supplies every experimental lattice energy the Kapustinskii route is scored
against — 35 of 36 salts located, all 35 matching — and was cited in two
places while absent from the registry. The author-year sweep at the foot of
this file **could not have caught it**: "Kaya" was not in its alternation,
so that check only finds authors somebody already thought of.

## The four that remain

### `drago1992` — needs the paper

*Inorg. Chem.* 1992, 32, 2473. Paywalled (ACS). A supplementary source for
the shipped E/C compilation. **Lower stakes than it was**: the primary source
is now verified and the whole table checked against it, so this is
completeness rather than risk.

### `yalkowsky_banerjee1992` — needs the book

Nothing beyond the author-year string exists anywhere in the repository, and
it backs external test set A1. Believed to be a book. Its provenance matters
because the A1 finding — *"74% inside ESOL's own training set"* — is a claim
about what that compilation contains.

### `nmrshiftdb2` — three routes tried, all dead

Its SourceForge page says only that *"the data is published under an open
content license"* **without naming which**, and gives no citation. The web
front end serves a Jetspeed login form rather than an about page, and the
help path 404s. So the licence is known to be open and otherwise
unidentified, and no canonical paper reference has been obtained from a
primary source. A citation is easy to supply from memory here and
deliberately has not been.

### `orca` — licence verified, citation not

faccts.de confirms *"free for academic use, while commercial licenses are
available through FACCTs"*, which is what the `license` field claims. The
site gives no canonical publication and points at the manual instead. The
paper anyone reporting ORCA results should cite is still unestablished.

## Terminal — leave them

`miller_polarizability`, `hlb`, `tsei`. Their `reason` **is** that no usable
source exists: unpublished parameters, no published formula, several
incompatible definitions. `unverified` is the correct final state. Do not
"fix" these.

## Method

`pdftoppm` is not installed, so `Read` cannot open a PDF. Use pymupdf in a
**throwaway venv**, never the project venv:

```bash
uv venv /scratch/pdfenv && uv pip install --python /scratch/pdfenv/Scripts/python.exe pymupdf
```

The encoding line is not optional — a title containing `∼` raises
`UnicodeEncodeError` on the cp1252 console:

```bash
PYTHONIOENCODING=utf-8 /scratch/pdfenv/Scripts/python.exe -c "import pymupdf;d=pymupdf.open(r'FILE.pdf');print(d[0].get_text()[:1500])"
```

Six traps already paid for:

- **A scan has no text layer.** `vogel1996.pdf` is 7 pages of images and
  extracts as empty — which reads as a broken file rather than a scan.
  Render at 500+ dpi and read the image; that is how `shannon1976` and the
  Drago table were both read.
- **A PDF's first page is not necessarily its paper.** `Drago & Wayland EC
  1965.pdf` opens on the tail of the preceding article.
- **A reference list is a verification instrument.** Llinàs 2020's supplied
  confirmed citations for two entries and revealed one the sweep had missed.
- **A filename is not an identification — and "not that paper" is not "not
  a source".** `kaya2022.pdf` matched a DOI's year, was assumed to be
  [source:gutmann_frontiers2022], and is not. It was then written off as
  unrelated, and is in fact cited twice in this repository as the source of
  every experimental lattice energy. Both halves of that were wrong in the
  same direction: deciding what a file is without opening it.
- **Local package metadata beats any PDF for software.**
  `importlib.metadata` gave five licences and corrected one.
- **A guess that turns out right was still a guess.** `allred1961`'s title
  was invented, removed as unverifiable, and the source later confirmed it.
  The identical move on `avdeef2020` named a different paper. Removal was
  right both times.

## Where each answer goes

Edit **`docs/sources.toml`** — never `docs/SOURCES.md`, which is generated.

| what you learned | field |
| --- | --- |
| the reference is right | `verification = "citation"` + `verified_date` |
| the **number we use** is right | `verification = "citation_and_claim"` + `verified_date` |
| a DOI | `identifier_type = "doi"`, `identifier` |
| a title you actually read | fold into `citation` |
| you now hold the PDF | `local = "filename.pdf"` (never checked) |

```bash
uv run --no-sync python tools/build_sources_doc.py
uv run --no-sync python -m pytest -q tests/test_sources_are_current.py tests/test_docs_are_current.py
```

A `verified_date` on an `unverified` row fails the schema guard, and so does
the reverse.

**And if a data file is generated, put the keys in the GENERATOR.** Hand-added
metadata in `lewis_parameters.json` was silently dropped by the next run of
`tools/build_lewis_parameters.py`. That file now carries a `_generated_by`
marker, which it previously lacked — which is why the hand edit looked safe.

## Structural gaps, not citation gaps

### The Ketcher bundle is not attributed

`src/openchem/resources/ketcher/dist/` carries third-party code beyond
Ketcher — EPAM's Miew 0.11.1 by its surviving banner, three.js by its
constants — against a build tree of **430 packages** (340 MIT, 46 ISC, 15
Apache-2.0, 11 "Apache-2.0 AND MIT", 6 BSD-3-Clause, 5 BlueOak-1.0.0, 1
CC-BY-4.0, 2 undeclared).

Their notices are **not recoverable from the artifact**: the build strips
comments even with minification off, so exactly two banners survive in 35 MB.
An accurate list has to be generated at build time from
`tools/ketcher-host/package-lock.json` — a step emitting a
`THIRD-PARTY-NOTICES.txt` beside the dist, which the licence guard could then
require.

`threedmol` has the same shape and is better behaved: its bundled licence
says outright *"3Dmol.js incorporates code from GLmol, Three.js, and
jQuery"*.

### `test_docs_are_current._repo_files` walks `.venv/`

It enumerates with `rglob("*")` over the whole tree, so a cited path resolves
if **anything in site-packages** matches it. That is why `docs/ROADMAP.md` can
cite a bare `setup.py` — which this repository does not have — and pass.

`test_every_used_by_path_is_tracked_in_git` avoids this by asking git, and is
the pattern to copy. Fixing the docs guard is a small separate change: exclude
`.venv`/`.git` from the walk, or take the list from `git ls-files`.

## Uncited PDFs in the archive

Present locally, cited nowhere, so **not** registry entries — listed only so
nobody re-derives whether they matter: `glasser2000.pdf`, `glasser2012.pdf`,
`jenkins2002.pdf` (lattice-energy family, where `glasser1995` and
`jenkins1999` are registered), and `tantardini2021.pdf` — "Thermochemical
electronegativities of the elements", Tantardini & Oganov, which is adjacent
to `electronegativity.json`'s subject and might be worth a look on its own
merits.

## The completeness check

`SOURCES.md` says its completeness rests on the reconstruction sweep, not on
anything a test proves. That has already paid out once: `glasser1995`,
`hopfinger2009` and `yalkowsky_banerjee1992` were cited in the repository and
absent from the registry, and the DOI sweep could not see them because none
carries a DOI.

Re-run this after any batch of source work — it is the only thing covering
the non-DOI half:

```bash
rg -o -N --no-filename -g '!docs/sources.toml' -g '!docs/SOURCES.md' -g '!**/vendor/**' -g '!**/resources/**' -e '(Glasser|Jenkins|Sorkun|Avdeef|Llin[aà]s|Abraham|Acree|Bradley|Delaney|Platts|Pearson|Parr|Drago|Shannon|Allred|Mayo|Hopfinger|Yalkowsky|Banerjee)[ ,]{0,2}(?:et al\.?)?[ ,]{0,3}(19|20)\d\d' . | sort -u
```

Every author-year it prints should resolve to a registry key. Extend the
alternation when a new name enters the codebase.
