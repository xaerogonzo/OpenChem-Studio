# Sources: what is still open

Handoff for the next session working on provenance. `docs/SOURCES.md` is the
registry; this file is the list of what it cannot yet stand behind, in the
order worth doing.

**Delete this file when it empties.** It is a work list, not documentation,
and a stale work list is worse than none — the same argument
`tests/test_docs_are_current.py` exists to make.

## Do not read the counts below as current — derive them

Any number here rots. The registry is the source of truth and answers in a
second:

```bash
uv run --no-sync python -c "import tomllib,pathlib;s=tomllib.loads(pathlib.Path('docs/sources.toml').read_text(encoding='utf-8'))['source'];[print(f\"{e['key']:26} {e['kind']:14} {e['citation'][:70]}\") for e in s if e['verification']=='unverified']"
```

At the time of writing: **57 sources, 17 `citation_and_claim`, 23
`citation`, 17 `unverified`.**

(That line was wrong by two within the hour it was written, because three
entries were added while it sat there. Which is the point of the command
above it.)

## The method, so it does not have to be rediscovered

`pdftoppm` is not installed, so the `Read` tool cannot open a PDF. Use
pymupdf in a **throwaway venv**, never the project venv — the suite
environment must stay exactly what `uv sync` produces:

```bash
uv venv /path/to/scratch/pdfenv && uv pip install --python /path/to/scratch/pdfenv/Scripts/python.exe pymupdf
```

Then, and the encoding line is not optional — the first title containing
`∼` raises `UnicodeEncodeError` on the cp1252 console:

```bash
PYTHONIOENCODING=utf-8 /path/to/scratch/pdfenv/Scripts/python.exe -c "import pymupdf;d=pymupdf.open(r'FILE.pdf');print(len(d));print(d[0].get_text()[:1500])"
```

Four traps already paid for:

- **A PDF's first page is not necessarily its paper.** `Drago & Wayland EC
  1965.pdf` opens on the tail of the preceding article. Search the whole
  text, not page one.
- **A reference list is a verification instrument.** Llinàs 2020's supplied
  confirmed citations for two other entries, named the paper `avdeef2020`
  had been confused with, and revealed a source the sweep had missed.
- **A filename is not an identification.** `kaya2022.pdf` matched a DOI's
  year and is a different paper entirely.
- **Local package metadata beats any PDF for software.**
  `importlib.metadata` gave five licences and corrected one.

## Where each kind of fact goes

Everything is edited in **`docs/sources.toml`** — never in `docs/SOURCES.md`,
which is generated and will be overwritten. After any edit:

```bash
uv run --no-sync python tools/build_sources_doc.py
uv run --no-sync python -m pytest -q tests/test_sources_are_current.py tests/test_docs_are_current.py
```

| what you learned | field to set |
| --- | --- |
| the reference is right | `verification = "citation"` + `verified_date` |
| the **number we use** is right | `verification = "citation_and_claim"` + `verified_date` |
| a DOI | `identifier_type = "doi"`, `identifier = "10...."` |
| a title you actually read | fold into `citation` |
| a licence read from the artifact | `license` |
| a resolved version | `version` + `package_manifest` |
| you now hold the PDF | `local = "filename.pdf"` (never checked by any guard) |

A `verified_date` on an `unverified` row fails the schema guard, and so does
the reverse — the pair is enforced.

## Tier 1 — the one that carries real weight

### `vogel_drago1996` — the weakest link in the project

**Needed:** Vogel & Drago, *J. Chem. Educ.* **1996**, 73, 701.

`src/openchem/chem/data/lewis_parameters.json` says its shipped E/C numbers
came *"via the Wikipedia ECW model compilation"*. So the chain is
Wikipedia → this repo → the registry, and **no step of it has touched the
paper.** The entire Drago adduct feature — 24 acids, 33 bases — rests on a
compilation nobody here has checked against a source.

What currently stands in for that check is
`test_the_shipped_table_reproduces_the_measured_enthalpies`, which
reproduces eight measured donor–iodine enthalpies to 0.27 kcal/mol across a
1.4–12.0 range. That is real evidence and it is validation-by-outcome, not
provenance: a systematically shifted table that still fits eight points
would pass it.

**On obtaining it:** confirm the iodine reference values are `E = 0.5,
C = 2.0` (the modern scale). If they are, raise to `citation_and_claim` and
say so in the note — that single fact is what
`test_lewis_parameters_match_the_declared_parameter_scale` ultimately
encodes, and it is currently derived from [source:drago1965] stating the
*other* scale rather than from this one stating ours.

**`drago1992`** (*Inorg. Chem.* 1992, 32, 2473) is the supplementary source
on the same line of the same JSON file, and is worth the same trip.

## Tier 2 — cited in the repo, thinly sourced

### `yalkowsky_banerjee1992`

**Needed:** the full citation. Believed to be a book, not an article.

Nothing beyond the author-year string exists anywhere in this repository,
and it backs external test set A1 — cited in `docs/VALIDATION.md`,
`benchmarks/solubility/README.md` and CLAUDE.md. Its provenance matters more
than most, because the A1 finding is *"74% inside ESOL's own training set"*,
which is a claim about what that compilation contains.

### `allred1961`

**Needed:** the title, and confirmation of the page range.
*J. Inorg. Nucl. Chem.* 17 (1961) 215-221.

Backs every electronegativity in `chem/data/electronegativity.json`. The
numbers are a standard reproduced table, so the risk is low and the
attribution should still be right.

### `gutmann_frontiers2022`

**Needed:** [10.3389/fchem.2022.861379](https://doi.org/10.3389/fchem.2022.861379)
— authors and title.

Open access, so this is a download rather than a hunt. It is
`assessed_not_shipped`, and the recorded quotes in CLAUDE.md (*"no
correlation could be found"*) came from a web fetch that cannot be
reproduced here. **Do not restore an author list from the key name** — the
previous one was invented that way.

### `crc_handbook` — a decision, not a lookup

**Which edition?** Nothing in the repo records it, and values do move
between editions. It is used for two unrelated things: the Allred-revised
Pauling electronegativities, and the lattice-energy column that
[source:jenkins1999] was validated against. Those may well have come from
different editions.

## Tier 3 — verifiable from the web in minutes

Each needs its canonical citation or licence confirmed from the project's
own site, then `verification = "citation"`:

`aqsoldb` (title/volume/pages — the repo carries only *"Sorkun, Khetan & Er,
Scientific Data 2019"*), `nmrshiftdb2`, `tdc_admet`, `ich_m9` (the full
guideline title, from ICH itself), `adoptium_temurin`, `autodock_vina`,
`orca`, `pkasolver`.

For the four software ones, prefer whatever the shipped artifact or its
package metadata states over the website.

## Tier 4 — unverifiable by construction, leave them

`miller_polarizability`, `hlb`, `tsei`. Their `reason` **is** that no usable
source exists — unpublished parameters, no published formula, and several
incompatible definitions respectively. `unverified` is the correct terminal
state. Do not "fix" these.

## Structural gaps, not citation gaps

### The Ketcher bundle is not attributed

`src/openchem/resources/ketcher/dist/` carries third-party code beyond
Ketcher — EPAM's Miew 0.11.1 is proven by its surviving banner, three.js by
its constants — against a build tree of **430 packages** (340 MIT, 46 ISC,
15 Apache-2.0, 11 "Apache-2.0 AND MIT", 6 BSD-3-Clause, 5 BlueOak-1.0.0, 1
CC-BY-4.0, 2 undeclared).

Their notices are **not recoverable from the artifact**: the build strips
comments even with minification off, so exactly two licence banners survive
in 35 MB. An accurate list has to be generated at build time from
`tools/ketcher-host/package-lock.json` — a `npm run build` step emitting a
`THIRD-PARTY-NOTICES.txt` beside the dist, which the licence guard could
then require. Adding Ketcher's own Apache-2.0 was necessary and is not
sufficient.

`threedmol` has the same shape and is better behaved: its bundled licence
text says outright *"3Dmol.js incorporates code from GLmol, Three.js, and
jQuery"*.

### `test_docs_are_current._repo_files` walks `.venv/`

It enumerates with `rglob("*")` over the whole tree, so a cited path
resolves if **anything in site-packages** happens to match it. That is why
`docs/ROADMAP.md` can cite a bare `setup.py` — which does not exist in this
repository — and pass on any machine with numpy installed.

`tests/test_sources_are_current.py::test_every_used_by_path_is_tracked_in_git`
avoids this by asking git instead, and is the pattern to copy. Fixing the
docs guard is a separate, small change: either exclude `.venv`/`.git` from
the walk, or take the file list from `git ls-files`.

### `local` is never checked, by design

It names a file in an archive outside the repository, so no run can resolve
it. Recording that limit is deliberate — a check that cannot run is worse
than a stated gap — but it does mean a wrong `local` survives silently.
One already did: `kaya2022.pdf`.

## Uncited PDFs sitting in the archive

Present locally and cited nowhere in the repo, so **not** registry entries —
listed only so nobody re-derives whether they matter:
`glasser2000.pdf`, `glasser2012.pdf`, `jenkins2002.pdf`. All three are in
the lattice-energy family, where `glasser1995` and `jenkins1999` are already
registered and verified.

## The completeness caveat is load-bearing

`SOURCES.md` says its initial completeness rests on the reconstruction
sweep, not on anything a test proves. That caveat has already been paid out
once: `glasser1995`, `hopfinger2009` and `yalkowsky_banerjee1992` were all
cited in the repository and absent from the registry, and the DOI sweep
could not see them because none carries a DOI.

**The check that found them** — worth re-running after any batch of source
work, since it is the only thing covering the non-DOI half:

```bash
rg -o -N --no-filename -g '!docs/sources.toml' -g '!docs/SOURCES.md' -g '!**/vendor/**' -g '!**/resources/**' -e '(Glasser|Jenkins|Sorkun|Avdeef|Llin[aà]s|Abraham|Acree|Bradley|Delaney|Platts|Pearson|Parr|Drago|Shannon|Allred|Mayo|Hopfinger|Yalkowsky|Banerjee)[ ,]{0,2}(?:et al\.?)?[ ,]{0,3}(19|20)\d\d' . | sort -u
```

Every author-year it prints should resolve to a registry key. Extend the
alternation when a new name enters the codebase.
