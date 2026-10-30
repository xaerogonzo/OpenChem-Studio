# Naming limitations: programme and inventory

This is the **operational** list of what the naming engine (`src/openchem/vendor/iupac_namer/`) is known to get wrong or cannot yet
verify, and what to do about each item. It tells a naming round what to work on and what evidence it needs. It is **not** a history:
the round-by-round narratives stay in `src/openchem/vendor/KNOWN_LIMITATIONS.md` and `src/openchem/vendor/CHANGELOG.md`, and this
file links to them instead of copying them.

`KNOWN_LIMITATIONS.md` is written in the standalone naming fork (`xaerogonzo/open-iupac-namer`) and never copied by
`tools/fork_port.py`. This file is the application's own index of it. Nothing in `KNOWN_LIMITATIONS.md` was changed for this
inventory.

## Dashboard

**Baseline this inventory was prepared against (checked 2026-10-27).**

| | |
|---|---|
| Application commit | `4c0696b1` (naming round 89, PR #477) |
| Fork commit read | `58058f0` (`main`, merge of fork PR #89) |
| Fork `KNOWN_LIMITATIONS.md` | 979 lines, blob `35af4e46da8110e5414aa72fe5bf6a3aa23e2d67` |
| Application `KNOWN_LIMITATIONS.md` | 1279 lines, blob `251dd2c85416143d7458241a9c1fc576f55205b9` |
| Relationship of the two files | The ten "What round N left open" bullets for rounds 80 to 89 are **byte-identical** in both. The files differ elsewhere: the application copy carries about 300 more lines of older prose and a different title line. They are two documents that share the recent bullets, not one document in two places. |
| Fork changes not yet landed here | None known: fork PR #89 is the latest and is vendored as application PR #477. |

**Counts** (from the audit run for this PR). Canonical rows: 96, of which 4 are retired cluster redirects, plus the 13 `OPEN`
regression rows, each mapped to exactly one canonical row (`NL-030` to `NL-042`). By class: W 1, M 8, I 8, B 44, V 5, S 12, U 10, N 4,
C 4 (the redirects). By priority: P0 1, P1 15, P2 22, P3 58 (the P0 and the W are `NL-070`, closed). By status: open 57, carried 27, blocked 3, closed 9 (`NL-003` and `NL-004` closed in round 91, `NL-107` in round 92).

**Plainly: one row was a *confirmed* wrong molecule, now fixed, and eight more may be.** `NL-070`: a diazo compound drawn
`C=[N+]=[N-]` was named as an iminoazanium that OPSIN reads back as a different formula. It was found by re-measuring the benchmark
section, not by a population run, and fixed in naming round 90 (#488). Eight rows (class M) record a name that OPSIN reads back as a different
molecule, never adjudicated as an engine fault or a validator fault. Six rows (class I) are cases where the validator cannot say
whether the name pins the intended stereoisomer. None of these groups has been shown harmless.

**Highest-priority next action.** WS1 first pass is done: the Blue Book `r`/`s` examples agree with the engine on the bridged constructions (`NL-001`), `NL-002` has no book oracle (blocked), and the 23 ylidene molecules are triaged (`NL-005`). `NL-107` was fixed in round 92 (D-389) and `NL-109` narrowed to the cumulene axis. Next: WS2 coverage matrix, and `NL-108`. `NL-003` and `NL-004` were fixed in round 91 (D-388, descriptors dropped by atom, fewest first). `NL-070`, the one confirmed wrong molecule, is closed.

**Workstreams.** WS0 confirmed defects: *empty* (`NL-070` closed in round 90). WS1 stereo audit: *active*, first pass done 2026-10-29 (`NL-003` and `NL-004` are needless flattening, `NL-001`, `NL-002` and the `NL-005` spiro case are validator limits with identity unresolved; `NL-003` and `NL-004` fixed in round 91). WS2 coverage probes: *active*, not started. WS3 source lookups: *active*,
not started. WS4 missing constructions: *deferred* (they round-trip today as von Baeyer names). WS5 older non-preferred names:
*deferred*. WS6 historical clusters: split on 2026-10-27; the rows they left `carried` remain.

**Blocked.** On a source the Blue Book PDF here does not print: `NL-017`, `NL-019` (status `blocked`). Waiting on an oracle that does
not exist yet for the failure class, status still `open`: `NL-002` (a substituted bridgehead has no example in the Blue Book or in the CIP Validation Suite; `NL-001` now has two oracles that agree and stays open as a validator limit; `NL-004` has an oracle now, OPSIN's own CIP reading, and is a measured needless flattening); permanently a validator limit: `NL-020`.

**Last completed round.** Round 89, `4c0696b1`, merged 2026-10-27.

**Last reviewed.** 2026-10-27, by reading `KNOWN_LIMITATIONS.md` (all sections, with the older "Open after round 3 to 14" sections only
to cluster level, see *Triage coverage*) and the 13 strict-xfail rows of `OPEN` in `tests/test_namer_known_defects.py`.

**Known coverage gaps in this inventory.** The 79 table rows of the older sections (rounds 3 to 14) and the benchmark section were
re-measured on 2026-10-27 by turning each row's names into structures with OPSIN, naming those structures with the current engine
and reading the result back (and, for 33 explicit SMILES in the same text and the 15 `adjudication.toml` rows still open, directly).
Every structure read back except the diazo drawing. That tells you the names are right about the molecule, not that they are the
preferred ones. Rows with no structure in their text (`NL-077`, `NL-081`, `NL-090`, `NL-095` to `NL-099`, `NL-104`) and the rows
`NL-051` to `NL-064` from rounds 20 to 49 were not re-measured; `NL-052` is cut short in the source. A coverage gap is not a clean bill.

## Chronology

The dates printed in `KNOWN_LIMITATIONS.md` do not agree with the repository. Order is not in doubt (85, 86, 87, 88, 89 are
consecutive on the merge ancestry); the calendar dates are.

| Round | Merge date on `master` (git author date) | Date in `KNOWN_LIMITATIONS.md` | Fork sync date in `VENDORING.md` | Application PR / commit |
|---|---|---|---|---|
| 80 | 2026-10-23 | 2026-10-22 | 2026-10-23 | #434 / `7b1394c0` |
| 81 | 2026-10-23 | 2026-10-23 | 2026-10-23 | #436 / `627e2ed4` |
| 82 | 2026-10-23 | 2026-10-23 | 2026-10-23 | #442 / `cf58133c` |
| 83 | 2026-10-24 | 2026-10-24 | 2026-10-24 | #456 / `38048ab6` |
| 84 | 2026-10-25 | 2026-10-25 | 2026-10-25 | #467 / `f4162db9` |
| 85 | 2026-10-26 | 2026-10-26 | 2026-10-26 | #471 / `62ba5b05` |
| 86 | 2026-10-26 | 2026-10-27 | 2026-10-27 | #473 / `09fa0166` |
| 87 | 2026-10-26 | 2026-10-28 | 2026-10-28 | #474 / `00d68437` |
| 88 | 2026-10-26 | 2026-10-28 | 2026-10-28 | #475 / `1e00da60` |
| 89 | 2026-10-27 | 2026-10-26 | 2026-10-27 | #477 / `4c0696b1` |

Round 89's printed date (10-26) is *before* round 87 and 88's printed dates (10-28), which is impossible. The git column is used
for every "round" date in the tables below. The two `VENDORING.md` sync dates that look late (rounds 87 and 88, 10-28) match the
file's own dates, so the discrepancy sits in the written dates, not in the history; it was not corrected in the fork's file.

## Classes, priority, status

| Code | Class | Meaning |
|---|---|---|
| W | confirmed wrong molecule | an independent identity check establishes the name denotes something else |
| M | unadjudicated read-back mismatch | OPSIN reads the name back as a different molecule; nobody has decided whether the engine or the validator is at fault |
| I | unresolved identity | the name may denote several stereoisomers, or its descriptor cannot be checked; no oracle yet |
| B | correct structure, non-preferred name | identity is established; the preferred construction differs |
| V | validator limitation | the available parser cannot establish correctness for this feature |
| S | source-unverified preference | readable, but the applicable Blue Book rule has not been checked |
| U | untested shape | no adequate probe has been run |
| N | not currently actionable | kept with evidence and a reason not to pursue it now |
| C | cluster (retired) | the four cluster rows `NL-100` to `NL-103` stood for older table rows; they are split and kept only as redirects |

| Priority | Rubric |
|---|---|
| P0 | credible risk of a wrong molecule or lost identity, with enough evidence to justify investigating now |
| P1 | likely structural or stereochemical correctness issue that needs adjudication |
| P2 | preferred name, source check, or broader coverage |
| P3 | low-impact missing construction, or deliberately deferred |

Confidence (H / M / L) is how sure the *report* is, and is independent of priority: a low-confidence report of a severe error can
outrank a certain style difference.

Status values: `open`, `blocked`, `inactive` (two adequately covered rounds without a new defect; **not** proven correct), `closed`
(with evidence), `carried` (listed in an older section, not re-measured since).

## Inventory

Closure criterion, next action and evidence for each row are in the table that follows this one; this table has the identity and the
decision fields.

| ID | Aliases | Item | Class | Conf | Pri | WS | Status |
|---|---|---|---|---|---|---|---|
| NL-001 | R89a | Isomers of a bridged parent that differ only in a pseudoasymmetric `r`/`s` centre share one name (2,6-dimethylnorbornane bridgeheads; positions 3 and 7 of 3,7-dimethylbicyclo[3.3.1]nonan-3-ol). OPSIN reads no `r`/`s`. **Measured 2026-10-29: validator limit on the two constructions tried.** 2,6-dimethylnorbornane: 4 isomers, 2 pin, 2 do not and no descriptor subset pins them; 3,7-dimethylbicyclo[3.3.1]nonan-3-ol: 8 isomers, 0 pin, 0 of 16 subsets pin. Identity of the dropped `r`/`s` descriptors is unresolved: no independent oracle (RDKit against RDKit is not one; Blue Book examples not yet located). Pre-validation names were identical across 25 random atom orderings for the cases tested. **Oracle found 2026-10-30:** the Blue Book's P-93.5.2.2.1 worked examples (book PDF pp. 937-938) with the geometry classified from an RDKit embedding, independent of any CIP code: 8-syn-methylbicyclo[3.2.1]octane is `8s` and anti is `8r`; the 3-exo-ol and 3-endo (tropane ester) are `3s` and `3r`; the engine's pre-validation descriptors agree in all three (and for the N-methyl acetate). So the descriptors are right on the bridged constructions tried; the two NL-001 molecules are other constructions on the same code path, so this is agreement by analogy. Residual risk: stays a validator limit. **Second oracle 2026-10-30:** the CIP Validation Suite (Hanson et al., J. Chem. Inf. Model. 2018, 58, 1755; `CIPValidationSuite/ValidationSuite`, 300 structures with author-agreed labels, licence not stated, nothing copied here) lists the same bridged cases with labels: VS238 `8s`, VS241 `3s`, VS235 `3r`; the engine's descriptors agree (a count comparison, then by locant). | I | H | P1 | WS1 | open |
| NL-002 | R89b | OPSIN cannot anchor R/S at a substituted bridgehead (`bicyclo[3.3.1]nonan-1-ol`, 9-chloro-1-ol) and fails its own CIP assignment on some 3,7 patterns, so those isomers share a flat name. The engine's descriptors there are checked only by RDKit's labeller. **Measured 2026-10-29: validator limit.** 9-chlorobicyclo[3.3.1]nonan-1-ol, 4 of 4 isomers named flat; OPSIN parses only 2 of the 8 descriptor subsets and none pins. Descriptor correctness unresolved. **Searched the Blue Book 2026-10-30: no worked example has a substituted bridgehead stereocentre, so no oracle exists in the book; blocked on an independent source.** | I | M | P1 | WS1 | blocked |
| NL-003 | R89c | The bridgehead fallback takes the ring atoms of the whole molecule; it equals the parent's bridgeheads only while the parent is the whole molecule. **Measured 2026-10-29 (WS1 audit): a potential engine defect, not a validator limit.** For `3-(bicyclo[2.2.1]heptan-2-yl)bicyclo[2.2.2]octan-2-ol` all 10 sampled isomers are named flat, and for every one an OPSIN-readable name that pins the isomer exists (e.g. `(2R,3R)-3-[(1R,2R,4S)-bicyclo[2.2.1]heptan-2-yl]bicyclo[2.2.2]octan-2-ol`). The same skeleton with a cyclohexyl substituent pins all 4 of 4 isomers, so the loss comes from the validator's tree-wide strip by locant number, which removes a bridged component's locants wherever they sit. **Fixed in naming round 91 (D-388):** when the by-locant strip parses but no longer pins, descriptors are dropped by atom, fewest first, and the first name OPSIN reads to exactly the input is kept; 10 of 10 sampled isomers now pin. | I | H | P1 | WS1 | closed |
| NL-004 | R89d | 2,4-difluoroadamantane: four embeddable isomers got three names, two of which pin their isomer (the cage has more `r`/`s` centres than any other parent). **Measured 2026-10-29: needless flattening in 2 of 4.** The two isomers named flat each have an OPSIN-readable subset of the engine's own descriptors that pins them, e.g. `(1R,2R,4R,5S)-2,4-difluoroadamantane`; OPSIN independently reproduced the engine's R labels at C2 and C4 for the traced isomer. The unconditional strip to `bridged_or_spiro` discards descriptors a smaller search would keep. **Fixed in naming round 91 (D-388):** the same atom-wise subset search; all 4 of 4 isomers now pin, e.g. `(1R,2R,4R,5S)-2,4-difluoroadamantane`. | I | H | P1 | WS1 | closed |
| NL-005 | R88d | The stereo layer was not triaged on ylidene-plus-stereo molecules (23 of 60 differ from the input) or on spiro names with an adamantane or bicyclo[2.2.2]octane parent, which name several embeddable isomers alike (`6'-methylspiro[tricyclo[3.3.1.1^{3,7}]decane-2,1'-cyclohexane]` for all 4; the non-spiro `4-methylbicyclo[2.2.2]octan-2-ol` for both enantiomers). Ring-forced versus free centres were not separated; the post-assembly OPSIN check drops descriptors it cannot read. **Measured 2026-10-29: the adamantane spiro case is a validator limit** (4 of 4 isomers named flat, no readable subset pins; one subset first looked like it pinned and was a raw-count artefact of deduplicating by InChIKey). The `4-methylbicyclo[2.2.2]octan-2-ol` collision did not reproduce. **Ylidene triage 2026-10-30 (the 23):** in every row the pre-validation name carries a full descriptor set and the final name drops the bridged-centre and `r`/`s` descriptors (the validator limit). Of the 23, 18 inputs are not among the isomers RDKit can embed (`tryEmbedding`; 8 have none at all, mostly strained spiro-bicyclo[1.1.1]pentane cages); the other ten were not separated from a second cause found on 2026-10-30: RDKit's stereoisomer enumeration does not enumerate ring pseudoasymmetry, so an input whose InChIKey carries it can never be among the enumerated keys), so the pin test cannot judge them: class *unjudgeable by this oracle*, not a defect. 4 pass (rows 7 and 13 pin to one isomer containing the input; 1 and 6 denote 4 and 2 isomers containing it, correct but underspecified). 1 is `NL-108`. Adamantane spiro: the Blue Book has no such example, so it stays a validator limit with residual risk. | I | M | P1 | WS1 | open |
| NL-006 | R89e | Round 89's population was 39 molecules, one seed, one substituent set (C, O, Cl, N, F). | U | H | P2 | WS2 | open |
| NL-007 | R42, R44, R45 | A quaternary N+ stereocentre has no descriptor: OPSIN reads one only for an acyclic N+, never the N+ of a bridged parent (ipratropium); the validator strips it. A descriptor at a primed spiro locant that parses as the wrong isomer would not be caught (none found in 79). | V | H | P2 | WS1 | carried |
| NL-008 | R43 | E/Z is lost for a methyl-branched alkenyl substituent (`N-(2-methylbut-2-en-1-yl)acetamide` names both stereoisomers; the descriptor is collected and never reaches the substituent tree). | I | M | P1 | WS1 | carried |
| NL-009 | R24, R45 | Four complex natural products lost stereo in the app in round 24 (atropine, scopolamine: tropane parents; galantamine; ibogaine). A fusion name cites its side-chain centre and not its ring-fusion ones (`bis([1,3]dioxolo)pyran`), a real stereo loss OPSIN cannot parse with descriptors. Not diagnosed; round 89 may have changed the tropane case. | I | M | P1 | WS1 | carried |
| NL-010 | R88b | The heteroatoms probed as the spiro atom were Si, N+ and P+ only (not B-, As, Sb+, or S/Se at a higher valence). | U | H | P2 | WS2 | open |
| NL-011 | R88c | A system of three or more polycyclic components joined at spiro atoms was not generated. | U | H | P2 | WS2 | open |
| NL-012 | R84c, R85a, R88e | Spiro partners not re-measured: an adamantane or tricyclic bridged partner with a substituent (round 88 did not reproduce it on its own molecules, not round 85's); a tetrahydropteridinone spiro-joined to an imidazoquinazolinone (unreadable); a pteridinone spiro-joined to a benzodiazepinone (`...-2',4-dione`, unreadable); a spiro of two methano-benzazocines (reads back as another molecule). | M | M | P1 | WS2 | open |
| NL-013 | R81a, R83a | A purinone joined to a purine with no ring N-H (`1H-purin-1-yl`, `3H-purin-3-yl`) is named with the oxo on C8 and the substituent on C2: another molecule (3 of 6,500 pairs; the odd tautomers are the generator's). Round 83 fixed only the `6-oxo-9H-purin-N-yl` half and did not re-measure this. | M | M | P1 | WS2 | open |
| NL-014 | R82c | The tetrahydropteridinone pair (one ring with a hydroxyl on a nitrogen) reads back as another molecule (1 of 3,100 assemblies). | M | M | P1 | WS2 | open |
| NL-015 | R83b | A quinoid ring with two oxo carbons and no N-H keeps the curated indicated hydrogen; no population drew one. | U | L | P2 | WS2 | open |
| NL-016 | R86a, R87b, R87c | Curated-ring checks have blind spots: the adjacency test cannot see two swapped atoms that both touch one labelled atom; a ring nitrogen with no hydrogen cannot be probed by a substituent; the pair probe samples 120 pairs, so a larger entry was not exhaustive. | U | M | P2 | WS2 | open |
| NL-017 | R87a | Corrin's numbering and the camptothecin and indolizinocarbazole systems' are not printed in the Blue Book PDF available here, so they are checked only against OPSIN. | S | H | P2 | WS3 | blocked |
| NL-018 | R86b | The 17 numbering conventions in the test are the book's retained orders and were not each re-read against the book. | S | M | P2 | WS3 | open |
| NL-019 | R80a | The other curated ring labels round 78 listed as unconfirmable still stand; only the pyrrolo[3,4-b]pyridine one was settled. | S | M | P2 | WS3 | blocked |
| NL-020 | R82a | Two heptalenes joined by a bond (`5,1'-biheptalene`) are unreadable by OPSIN in every spelling tried, so the name cannot be verified. | V | H | P3 | WS3 | open |
| NL-021 | R88a | A silicon spiro atom is cited in both partners (`spiro[silolane-1,2'-2-silabicyclo[2.2.1]heptane]`); OPSIN reads it but the book's form for a heteroatom shared by two named components was not looked up; the same for `<loc>-azonia` / `<loc>-phosphonia` before a polycyclic first partner. | S | H | P2 | WS3 | open |
| NL-022 | R81b, R82b | Ring-assembly spelling: `bi1H-indole` (OPSIN reads it; the book spells `1H,1'H-...-biindole`); a component with three or more rings is enclosed (`bi(anthracene)`) while a two-ring one is not (`1,1'-binaphthalene`), which is OPSIN's need, not a source-backed spelling. | S | H | P2 | WS3 | open |
| NL-023 | R80b | A ring cation is named as the parent whenever present, so an ester of a cationic alcohol is an acyloxy prefix (`2-(acetyloxy)chromenylium`), not the ester name OPSIN would also read. | S | M | P3 | WS3 | open |
| NL-024 | R80c | The substituent forms of the two ring ketones are in hydro-prefix style, while the quinazolinedione form (`2,4-dioxo-1H,3H-quinazolin-6-yl`) keeps the older added-hydrogen style that OPSIN also reads. | S | M | P3 | WS3 | open |
| NL-025 | R84d | The ketone of a spiro ring is cited with an added hydrogen only when the parent has exactly one aromatic ring N-H (`-4(1H)-one`). | B | M | P3 | WS5 | open |
| NL-026 | R81c | The seven nucleobases are excluded from the heteroatom short-circuit, so an adenine joined through an exocyclic atom is named by its purine parent and not `adenin-yl`. | B | H | P3 | WS5 | open |
| NL-030 | D-086b | A fusion name needing a second-order attached component (`cyclopenta[4,5]pyrrolo[2,3-c]pyridine`); today a von Baeyer name or none. Book p. 239. | B | H | P3 | WS4 | open |
| NL-031 | D-086c | A fusion name with an interior heteroatom (`6H-quinolizino[3,4,5,6-ija]quinoline`, P-25.3.3.2); today a von Baeyer name. Book p. 223. | B | H | P3 | WS4 | open |
| NL-032 | D-088b | `ethyl hydrazinecarboxylate` for `CCOC(=O)NN`; today `(ethoxycarbonyl)hydrazine`. The anion of hydrazinecarboxylic acid is not nameable, so no ester plan is offered. | B | H | P3 | WS5 | open |
| NL-033 | D-088d | `4-(2-methylhydrazine-1-carbonyl)benzoic acid`; today `4-[(2-methylhydrazinyl)(oxo)methyl]benzoic acid` (the acid is now the parent; the prefix spelling is not). Book p. 668. | B | H | P3 | WS5 | open |
| NL-034 | D-088f | `N,N'-oxybis(N-methylmethanamine)`; today `{[(dimethylamino)oxy](methyl)amino}methane`. No marker reads this unit's attachment N. Book p. 108. | B | H | P3 | WS5 | open |
| NL-035 | D-088h | `4,4'-[(2-methylpropane-1,3-diyl)bis(oxy)]diphenol`; a substituted linker is outside the built multiplicative class (P-15.3.1.2.1.2). | B | H | P3 | WS5 | open |
| NL-036 | D-088i | `(benzene-1,3,5-triyl)tris(silane)`; a ring as the central group is not built. Book p. 107. | B | H | P3 | WS5 | open |
| NL-037 | D-088j | `4,4',4''-(ethane-1,1,2-triyl)tribenzoic acid`; an unsymmetrical central group (P-15.3.3.1) is not built. Book p. 110. | B | H | P3 | WS5 | open |
| NL-038 | D-089s | `1,1,3,3-tetramethyldisiloxane-1,3-diol`: a silanol on a silicon parent (P-68.2.5) reaches a suffix only through a pre-plan route. | B | M | P3 | WS5 | open |
| NL-039 | D-089u | `N-silylsilanamine` (book p. 145, "not disilazane"); the organometallic chain route still builds `disilaazane`. | B | H | P3 | WS5 | open |
| NL-040 | D-090b | `1-methyltrisiloxane`; today `2,4-dioxa-1,3,5-trisilahexane`. The skeletal-replacement count predates N5; `-SiH2-O-SiH2-` is one heterounit (p. 440). | B | M | P3 | WS5 | open |
| NL-041 | D-089v | `ethyl N,N-dimethylphosphoramidocyanidate`; functional replacement by -CN (P-67.1.2.4, p. 704) is not built; the old `tabun` name is gated. | B | M | P3 | WS5 | open |
| NL-042 | D-130 | `dicyclohexylmethanediimine` (P-62.3.1.4, p. 528); the wrong molecule this row was admitted for is fixed, the PIN is not. | B | H | P3 | WS5 | open |
| NL-050 | Observed | `[C-]1C=CC=C1` names as `cyclopenta-2,4-dien-1-ide`, dropping the unpaired electron (the radical anion). No name OPSIN parses back to the radical anion was found, so no target is stated. | V | H | P3 | WS3 | open |
| NL-051 | R49a-f | Ions of round 49: (a) the anion-mode plan of an N-acyl isothiourea thiolate claims the carbonyl oxygen twice (the default mode rejects it and the name is right; the strict mode raises); (b) an N-sulfonyl iminium is refused; (c) anions of an N-N bond are refused or visibly wrong (`CC(=O)[N-]N` is a `NAMING ERROR`); (d) a carboxylate beside two neutral acids on an amidinium is refused; (e) a sulfonamide anion bearing N-methoxycarbonyl is `N-[methoxy(oxo)methyl]methanesulfonamidate`, not `methoxycarbonyl`; (f) the census's seven non-exact rows. | B | M | P2 | WS5 | carried |
| NL-052 | R46-R48 | Charge residue of rounds 46 to 48: the thiolate of a thioamide or isothiourea is named with `sulfanide` inside; a quaternary ring N+ (N-methylpyridinium type) has no protonated hydro form; 11 protonated and 2 quaternary cations are refused by the charge guard (amidoximes, imidates, ...). **The three bullets are cut off at a line break in the source; the rest of each list was not read.** | B | L | P2 | WS5 | carried |
| NL-053 | R41-R45 | Refusals and charge handling: an amidinium zwitterion with a second acid, and a quaternary carbon carrying both acids, are refused; a phenolate beside a real OH is refused; an anion beside a senior group is a prefix (`4-oxidobenzene-1-carbonitrile`, not `4-cyanophenolate`, P-73); a protonated hydrazone `C=[NH+]NC(=O)R` is named as the neutral hydrazide (charge dropped). | M | M | P1 | WS5 | carried |
| NL-054 | R34, R41 | A ring cation with an exocyclic double bond on a ring carbon (`C=C1CCC[NH+]=C1`) is `5-methylideneazinan-1-ium`, **a different molecule**. N-substituted 1-pyrrolinium and 1-imidazolinium (`C[N+]1=CCCC1`) get the Hantzsch-Widman `azol`/`diazol` spelling where the neutral ring takes the retained one. | M | M | P1 | WS5 | carried |
| NL-055 | R35-R40, R37 | Curated ring cations: about 13 curated entries list no locant for a ring heteroatom, so their cations fall to the next plan; a tricyclic bridgehead iminium is declined; 28 fused azetidinium cases; the two resonance forms of a bicyclic amidinium get two different, both exact, names; a second-order fusion is built for one level only. | B | M | P2 | WS5 | carried |
| NL-056 | R13, R14, R41-44 | Rings with no table entry are wrong in the ring-locant sweep: the four helicenes (orientation rule P-25.3.3.1.1 not implemented), octahydropyridazino[1,2-a][1,2]diazepine (28 of 34 cases), corrin (10 of 33), two indolo[4,3-fg]quinolines, a furo-naphtho-dioxole; all-carbon table-less fused rings (nonacene, heptacene, the phenes). The sweep skips heteroatom sites (651), and a heteroatom-attachment sweep was never built. | M | M | P1 | WS2 | carried |
| NL-057 | R40-R45 | Names OPSIN cannot check: `N1,N2` on `oxamide`, `oxobis[...]phosphanyl`, CIP on a bis-adamantane, `bis([1,3]dioxolo)...pyran`, and a camptothecin-type ring cation. The app verifies four of them through a respelling; the census and benchmark scans still cannot parse them. | V | H | P3 | WS3 | carried |
| NL-058 | R41-R45 | `bluebook_frozen` has two names that differ from the round-40 seal, attributed to a late round-40 edit and not investigated, since a frozen row may not be read. | N | L | P3 | WS3 | carried |
| NL-059 | R25, R26 | Esters are written in the accepted acyloxy form, not the PIN, for different anions on one polyol; for a polyol whose organyl group is not one parent (multiplicative, ring assembly); and for esters of a polyol and a polyacid (P-65.6.3.3.4.1). | B | H | P3 | WS5 | carried |
| NL-060 | R25 | "Senior acid" is ring-before-chain, then skeletal atoms, then substituents, not the full P-41/P-44.1 order; with more than four tied esters or a retained acid other than formate, acetate, benzoate, the choice falls to a canonical atom rank. | B | M | P3 | WS5 | carried |
| NL-061 | R24 | Charged morphinans fall back to a von Baeyer name; only morphinan is eligible for `didehydro`/`epoxy` modification (not ergoline, ibogamine, the Amaryllidaceae scaffolds). | B | H | P3 | WS5 | carried |
| NL-062 | R21-R23 | Two or more nitramide groups (ethylenedinitramine) keep the amine name `N1,N2-dinitroethane-1,2-diamine`; the derived `ethane-1,2-diylbis(nitramide)` was not implemented. | B | H | P3 | WS5 | carried |
| NL-063 | R20 | An azine, a triazane or a ring nitrogen on the second nitrogen of an `=N-N` group keeps the imino form; the book's `hydrazin-1-yl` locant (p. 717) versus `hydrazinyl` (p. 71) is unresolved. | S | M | P3 | WS3 | carried |
| NL-064 | R26 (stereo cache) | Prefixes that tie on their letters alone are cited in atom order (P-14.5.4). **Probably closed** by the P-45.2.3 / P-45.5 work of rounds 26 and 27; not re-measured. | B | L | P3 | WS5 | carried |
| NL-065 | R6 | Cyanamide as a prefix (`3-(cyanoamino)propanoic acid`): the Blue Book prints no name for it, so none is targeted. | N | H | P3 | WS3 | closed |
| NL-066 | R3, Bench | 274 retained-name registry entries have no audited status (round 3); the benchmark section counts it differently: 74 of 292 `retained_pins` carry no cited rule, two were wrong, 72 unexamined. The two counts were taken at different times and not reconciled; `tools/retained_name_audit.py` reports the backlog. | S | M | P2 | WS3 | carried |
| NL-070 | Diazo | **Confirmed wrong molecule.** A diazo compound drawn `C=[N+]=[N-]` is named as an iminoazanium: diazomethane `imino(methylidene)azanium`, which OPSIN reads as `N=[N+]=C` (CH3N2+, not CH2N2). Five of five further diazo shapes measured the same way (diazoethane, diazoacetone, phenyldiazomethane, methyl 2-diazopropanoate, 2-diazopropane). The other Lewis form `[CH2-][N+]#N` is right (`methanidyldiazonium`, D-019); an organic azide is right. Found by re-measuring the benchmark section; D-019 fixed only the one drawing. **Fixed in naming round 90 (D-387, #488):** the diazo group now subsumes the imine it overlaps; 147 to 150 of 150 diazo molecules read back on each of five seeds (before: 26 and 27 of 150), the five unseen failures stereo only. | W | H | P0 | WS0 | closed |
| NL-071 | Diazo | `C=[N+]=C` (a 2-azaallenium) is refused with `No name found that keeps the positive charge`; a refusal, not a wrong name. | B | H | P3 | WS5 | open |
| NL-072 | R8 row 805 | N-alkoxy thioamide, N,N-dialkoxy amide and O-alkylhydroxylamine keep prefix forms (`N-methoxy-N-methyl-1-thioxoethan-1-amine`, `1-(dimethoxyamino)-1-oxoethane`, `(aminooxy)methane`); all read back. | B | H | P3 | WS5 | open |
| NL-073 | R8 row 806 | A polynitrate ester is named `1,2,3-tris(nitrooxy)propane`, not `propane-1,2,3-triyl trinitrate`; reads back. | B | H | P3 | WS5 | open |
| NL-074 | R8 row 807 | Carbonic acid halides and anhydrides: `methoxymethanoyl chloride` (not `methyl carbonochloridate`); di-tert-butyl dicarbonate is `2-methyl-2-({[(2-methylpropan-2-yl)oxy](oxo)methoxy}(oxo)methoxy)propane`. Both read back. | B | H | P3 | WS5 | open |
| NL-075 | R8 row 816 | Benzil is `1,2-diphenylethane-1,2-dione`; the book omits the locants of a symmetrical ethane (`diphenylethanedione`, p. 559). | B | H | P3 | WS5 | open |
| NL-076 | R8 row 819 | A diacyl peroxide is `1-(acetylperoxy)-1-oxoethane` (not `diacetyl peroxide`); a xanthate ester is `O-ethyl (methylsulfanyl)methanethioate` (not `O-ethyl S-methyl carbonodithioate`). Both read back. | B | H | P3 | WS5 | open |
| NL-077 | R8 row 818 | Peroxide, sulfur, phosphorus and boron pseudoketones: only a ring peroxide was re-measured (`1,2-dioxolan-3-one`, a "one" name); the acyclic and S, P, B shapes were not probed. | U | L | P3 | WS2 | carried |
| NL-078 | R7 row 866 | Deprotonated phosphonic and phosphoric acids stay oxido-on-phosphane names (`hydroxy(oxido)(oxo)(phenyl)phosphane`, `hydroxy(oxido)(oxo)(phenoxy)phosphane`), a declared unsupported class; the book's 'hydrogen' method (`hydrogen phenylphosphonate`, p. 808) is not built. Reads back. | B | H | P3 | WS5 | open |
| NL-079 | R7 row 867 | Chiral amino-acid anions are `(2S)-2-aminopropanoate`, `(2S)-pyrrolidine-2-carboxylate`, not `alaninate`/`prolinate` (P-103.2.4.2); a stereo policy for the retained names is not decided. Reads back. | B | H | P3 | WS5 | open |
| NL-080 | R7 row 870 | A betaine's cationic prefix is `(trimethylazaniumyl)acetate`; the pages read do not say whether the book also allows it versus `(N,N-dimethylmethanaminiumyl)acetate`. | S | M | P3 | WS3 | open |
| NL-081 | R7 row 872 | Compound acyl names on `azanide` (`chloroacetylazanide` versus `(chloroacetyl)azanide`): the enclosure test looks for locant characters. **Not re-measured**: the row gives no structure. | B | L | P3 | WS5 | carried |
| NL-082 | R5 row 933 | Skeletal replacement with a principal group: `(2-{2-[2-(carboxymethoxy)ethoxy]ethoxy}ethoxy)acetic acid`, not `3,6,9,12-tetraoxatetradecane-1,14-dioic acid` (p. 437). Reads back. | B | H | P3 | WS5 | open |
| NL-083 | R5 row 935, adjudication | Carbon with two double-bonded suffix groups: carbon disulfide `dithioxomethane` (PIN `methanedithione`) and dimethylcarbodiimide `bis(methylimino)methane` (PIN `dimethylmethanediimine`); `adjudication.toml` records both as ENGINE_WRONG with `fix_status` OPEN. Same mechanism as `NL-042`. | B | H | P3 | WS5 | open |
| NL-084 | R5 row 946 | a(ba)n chains of chalcogen terminals (`{[(methylsulfanyl)oxy]sulfanyl}methane`) and cyclic siloxanes (the cyclic trimer is `2,2,4,4,6,6-hexamethyl-1,3,5,2,4,6-trioxatrisilinane`) are not built; a carbon-bearing S-O-S as a sulfenic anhydride was not checked against the book. Both read back. | B | M | P3 | WS5 | open |
| NL-085 | R5 row 944 | `hypoboric acid` is emitted where the book prints `hypodiboric acid` (p. 720): OPSIN cannot parse the book's form. | V | H | P3 | WS3 | open |
| NL-086 | R5 row 976 | Phosphoryl prefix: `[diethyl(oxo)phosphanyl]acetic acid` instead of `(diethylphosphoryl)acetic acid` (p. 357). Reads back. | B | H | P3 | WS5 | open |
| NL-087 | R5 rows 973, 977 | `tert-butyl` in a PIN is written `2-methylpropan-2-yl` (`dimethyl(2-methylpropan-2-yl)silanol`); classified in round 8 and left, since it moves the alphanumerical order. | B | H | P3 | WS5 | open |
| NL-088 | Bench | Purine's four tautomers are all named `9H-purine` on purpose (the xanthine and caffeine family is numbered off it), which loses which tautomer was supplied. Deliberate; recorded so it is not mistaken for a defect. | N | H | P3 | WS3 | open |
| NL-089 | Bench | Metformin is `1,1-dimethylbiguanide`: `biguanide` is a retained name that carries no tautomer information, and OPSIN picks one depiction. Not fixable by naming. | N | H | P3 | WS3 | open |
| NL-090 | R8 row 814 | Curated hydro or bridged ring entries with letter labels on atoms in three rings (`12a`/`12b`, `6a`, `13a`, in three entries) are not covered by `tests/test_known_deviations.py`, which scans only the fully aromatic entries. **Not re-measured.** | U | L | P2 | WS2 | carried |
| NL-091 | R5 rows 873, 922 | The ring table keeps the CAS interior locants for pyrene and phenalene (`10b`, `10c`) where the book numbers them `3a1`, `5a1` (P-25.3.3.3.1, p. 224). Deliberate: the round-trip oracle reads the CAS locants. | B | H | P3 | WS5 | open |
| NL-092 | R5 rows 919-921 | Refused fusion constructions: a 7- or 8-membered ring fused on three or more sides (4 of the book's 8 such systems number as OPSIN numbers them, 4 do not); rings of more than eight members; helicenes (their own orientation rule). A von Baeyer name or none. | B | H | P3 | WS4 | open |
| NL-093 | R5 rows 918, 923 | Multiparent systems (`benzo[1,2-b:4,5-c']difuran`) are refused to a von Baeyer name or none; the hydro forms of a traditionally numbered retained parent (anthracene, phenanthrene) fall to von Baeyer (`tricyclo[8.4.0.0^{4,9}]tetradeca-1(14),2,10,12-tetraene` for a hexahydrophenanthrene). | B | H | P3 | WS4 | open |
| NL-094 | R5 row 925 | The P-44.1.2 senior-atom tier between two rings is compared ring against ring, which the book says it is not; agrees with P-44.2.1 wherever one ring has N or one is a carbocycle. | B | M | P3 | WS5 | open |
| NL-095 | R5 row 972 | 32 ring-table entries number only some positions; a substituent elsewhere had an empty locant. Guarded (the plan is refused), not repaired. | U | M | P2 | WS2 | carried |
| NL-096 | R5 row 924 | OPSIN's ring vocabulary (`rings_from_opsin.json`, 705 names; `fusion_components.json`, 821) is read as ring parent names, unaudited. | S | M | P2 | WS3 | carried |
| NL-097 | R5 rows 915, 916 | The ownership audit does not see a prefix whose name denotes an atom it does not claim (`carbamimidoyl` on a chain), nor the insides of functional-class, multiplicative, ring-assembly and additive nodes (66 of 267 tuning molecules had no substitutive level). | U | M | P2 | WS2 | carried |
| NL-098 | R14 | Bridged methano-benzocyclooctenes: the skeleton is named as the wrong ring system (2 rows, the same shape twice, not measured further). **Not re-measured.** | M | L | P1 | WS2 | carried |
| NL-099 | R14 | Six single-row structural misnames: an N-hydroxy-N-alkyl amide in an ester losing its N-substituent (D-162, closed in round 38), an acylamidine, an oxime ether of a thioamidine, a purine hydro-prefix, an N versus N' hydrazide locant, a steroid oxime ether. **Not re-measured except D-162.** | M | L | P1 | WS2 | carried |
| NL-104 | R14 | Other round-14 residue, not re-measured: tricyclic and amidinium ring cations (4; the neutral copy is verified for bicyclic systems only), neutral fused or spiro polycycles with "no valid plan" (4 shapes), sulfonamide N- anions (4: two are OPSIN reading an anion as the neutral sulfonamide, one drops the charge inside a `sulfamoyl` prefix, one is a refusal), seven unparsable shapes, one double-bond stereo omitted. | B | L | P2 | WS5 | carried |
| NL-105 | adjudication | Six rows of `benchmarks/naming/adjudication.toml` with `fix_status` OPEN or PARTLY_FIXED and a verdict that the engine's name is not the PIN: a phosphocholine whose cation is the principal characteristic group (platelet-activating factor, `2-({[2-(acetyloxy)-3-(hexadecyloxy)propoxy](hydroxy)(oxo)phosphanyl}oxy)-N,N,N-trimethylethanaminium`); an alkanesulfonyl prefix (`propan-2-ylsulfonyl` for `propane-2-sulfonyl`); a nitrone (`methyl(oxido)(propan-2-ylidene)azanium` for `N-methylpropan-2-imine N-oxide`, the book's own example); dimethyl diselenide (`1,2-dimethyldiselane`, PIN `(methyldiselanyl)methane`); Boc-glycine (`({[(2-methylpropan-2-yl)oxy](oxo)methyl}amino)acetic acid`, PIN `[(tert-butoxycarbonyl)amino]acetic acid`); the round 7 thiourea, whose structure now reads back and whose PIN differs. All six re-measured and read back. | B | H | P3 | WS5 | open |
| NL-106 | adjudication | Five rows of `adjudication.toml` with verdict UNDECIDED and `fix_status` OPEN: trans-decalin (`trans-decalin` versus `decahydronaphthalene`: decalin is not in the book); diazepam (hydro prefixes versus added hydrogen, P-58.2); an indolocarbazole-type fusion (every ring has five or more members, P-52.2.4.1); a veratrum-type alkaloid and a dinucleotide (two von Baeyer names with different main-ring divisions). The sources here do not resolve them; UNDECIDED is a legal outcome. All five re-measured and read back. | S | H | P3 | WS3 | open |
| NL-107 | WS1 oracle | Tetraspiro example (Blue Book P-93.5.3 ex. 5, p. 942): OPSIN reads the book's name and the engine's to the same structure, but the engine writes `1,6,9,12-tetraoxa` where the book writes `1,5,8,11-tetraoxa`, and its descriptors (`3R,4s,7S,10r`) are the book's `3R,4r,7S,10s` mirrored at the pseudoasymmetric centres. Correct structure, non-preferred numbering. **Atom level, 2026-10-30 (CIP suite VS256):** the four spiro carbons sit on a cyclobutane; walked round it the suite's labels read `s R r S`, the engine's `R s S r` (the same cycle read the other way) and the book's `R r S s` (the same cycle read forward), so the descriptors are right and only the numbering direction and the oxygen locants differ. The same structure drawn from the suite's SMILES gave `1,5,9,12-tetraoxa` and from its 2D file `1,6,9,12-tetraoxa`, so the heteroatom locants are not stable (cause undetermined: atom order or stereo). **Fixed in round 92 (D-389):** the terminal rings of a polyspiro system are numbered in both directions, the tied numberings are offered to the stereodescriptor tie-break, and a chirality centre precedes a pseudoasymmetric one when every rank ties. 16 of 16 atom orders of the suite's structure now give `(3R,4r,7S,10s)-1,5,8,11-tetraoxatetraspiro[2.0.2^4.0.2^7.0.2^10.0^3]dodecane`, the book's own name. | B | M | P3 | WS5 | closed |
| NL-108 | WS1 ylidene | Two ylidene-on-bridged-ring rows: the final name `(6'Z)-6'-ethylidenespiro[bicyclo[4.1.0]heptane-3,5'-bicyclo[2.1.1]hexane]` has a stereo descriptor OPSIN cannot attach ("Could not find bond"), and `5'-ethylidenespiro[...thieno[3,2-c]pyridine-4,2'-bicyclo[1.1.1]pentane]` omits the E/Z of an input that has one. Not shown wrong; unresolved. | I | L | P2 | WS1 | open |
| NL-109 | WS1 CIP suite | The engine's stereo layer states fewer or different descriptors than the CIP Validation Suite's labels for four entries, and `_validate_stereo_via_opsin` is never called for them, so these are omissions of the engine's own naming, not validator strips: VS207 omits the central ring's two `r` (suite `s2 r4`, name `r2 s2`); VS214 and VS231 carry no stereo at all (suite `E E s s` and `p p s`; the name denotes the flat structure); VS279 omits the carbinol `R` and writes `r`/`s` on all four ring atoms where the suite has `R r S s S`. OPSIN cannot read the first and last, and for the other two the name does not pin the input. Not shown to be a wrong molecule; no independent reading beyond the suite. **Round 92 (D-389) fixed the cause for three of the four:** RDKit's legacy stereo perception cleaned the chiral tag off a ring atom whose two branches differ only by another centre's configuration, and ignored a double bond between two rings, at parse time. `name_smiles` now runs under the non-legacy perception, and VS207, VS214 and VS279 carry the suite's labels (`tests/test_namer_round92_...`). **Still open: the cumulene axis of VS231** (suite `2p 4p`), which RDKit's mol has no tag for. | I | M | P2 | WS1 | open |
| NL-100 | Cluster | Was the cluster of round 3 to 8 candidate-generation rows. **Split on 2026-10-27** into `NL-072` to `NL-087` and the closed table below. | C | H | P3 | WS6 | closed |
| NL-101 | Cluster | Was the cluster of the round 5 backlog. **Split** into `NL-092` to `NL-097`, `NL-030`, `NL-031` and the closed table below. | C | H | P3 | WS6 | closed |
| NL-102 | Cluster | Was the cluster of rounds 8 to 14 residue. **Split** into `NL-098`, `NL-099`, `NL-104` and the closed table below. | C | H | P3 | WS6 | closed |
| NL-103 | Cluster | Was the cluster of the benchmark and Severity B/C sections. **Split** into `NL-070`, `NL-071`, `NL-088`, `NL-089` and `NL-066`; every other entry in those sections is closed or explanatory. | C | H | P3 | WS6 | closed |

## Next action and closure criterion

An item is `closed` only when its closure criterion holds, with the evidence recorded.

| ID | Next action | Closure criterion |
|---|---|---|
| NL-001 | Find an oracle for pseudoasymmetric `r`/`s` (Blue Book worked examples with a bridged parent; a second CIP implementation only if it supports pseudoasymmetry), then compare with the engine's descriptors | Correct descriptor shown, or defect filed with a regression row; otherwise recorded as validator limitation with residual risk |
| NL-002 | One representative (9-chlorobicyclo[3.3.1]nonan-1-ol): write the evidence chain for it | Same as `NL-001` |
| NL-003 | Generate a bridged parent as a substituent of a larger molecule, name every embeddable isomer, read back | Distinct, readable names for all isomers, or a defect row |
| NL-004 | Decide whether three names for four isomers is a contract failure; check the two that pin their isomer | A written contract decision plus a test, or a defect row |
| NL-005 | Separate ring-forced from free centres on the 23 differing molecules | Each of the 23 classed (validator, engine, or by design) |
| NL-006 | Write the coverage matrix (WS2), include non-C/O/Cl/N/F substituents and a second seed | Matrix met on two seeds |
| NL-007 | None until a validator exists | Stays validator limitation |
| NL-008 | Re-measure the one example on the current engine | Reproduces (defect row) or does not (record input, seed) |
| NL-009 | Re-measure atropine, scopolamine, galantamine, ibogaine | Each classed |
| NL-010 | Probe B-, As, Sb+, S/Se at a spiro atom | Coverage matrix met, or a defect row |
| NL-011 | Generate three-component spiro chains | Same |
| NL-012 | Re-measure the four named molecules on the current engine | Each classed engine, validator, or not reproduced |
| NL-013 | Re-measure the `1H-purin-1-yl` / `3H-purin-3-yl` pairs; adjudicate which tautomer the generator drew | Classed, or fixed with a regression row |
| NL-014 | Re-measure the tetrahydropteridinone pair | Same |
| NL-015 | Draw a quinoid ring with two oxo carbons and no N-H | Probe run |
| NL-016 | Add the missing checks for the entries already known, then probe the rest | Each entry covered |
| NL-017 | Wait for a source; record it | Source read, or kept `blocked` |
| NL-018 | Re-read each of the 17 against the book | Each confirmed |
| NL-019 | As `NL-017` | As `NL-017` |
| NL-020 | None | Stays validator limitation |
| NL-021 | Read the rule on a heteroatom shared by two named components; read the `azonia`/`phosphonia` rule | Passage, page, rule and applicability written down, or marked source-unverified |
| NL-022 | Read the ring-assembly spelling rules | Same |
| NL-023, NL-024 | Read the rules; decide | Same |
| NL-025 to NL-026 | Probe the stated shape | Classed |
| NL-030 to NL-042 | Batch round (WS5 or WS4); each row keeps its `OPEN` xfail until its target is produced | The `xfail(strict=True)` row flips and the row moves to the closed table in the test file |
| NL-050 | None until an oracle exists | Stays validator limitation |
| NL-051 to NL-056, NL-059 to NL-064 | Re-measure on the current engine, then split or close (they carry no structures in the text, so the first step is to find the SMILES in the vendor changelog or `tests/test_namer_known_defects.py`) | Each sub-item classed |
| NL-057 | None | Stays validator limitation |
| NL-058 | Ask whether the two rows can be examined without reading a frozen row | Explained, or recorded `N` |
| NL-065 | None | Closed (no target exists) |
| NL-066 | Run `tools/retained_name_audit.py` | Backlog count recorded |
| NL-003, NL-004 | None (fixed in round 91, D-388) | Met: every sampled isomer's name reads back to exactly that isomer (pinned in `tests/test_namer_round91_stereo_is_dropped_by_atom_not_by_locant_number.py`); the validator-limit cases `NL-001`, `NL-002` and the spiro case are unchanged |
| NL-107 | None (fixed in round 92, D-389) | Met: 16 of 16 atom orders of the suite's structure give the book's name, pinned in `tests/test_namer_round92_ring_stereo_and_terminal_ring_orientation.py` and the `D-389` row of the known-defects table |
| NL-070 | None (fixed in round 90, #488) | Met: all six shapes read back on InChIKey; `[CH2-][N+]#N` and an organic azide unchanged (pinned in `tests/test_namer_round90_a_diazo_carbon_is_not_an_imine.py`) |
| NL-071 | None until a name exists that OPSIN reads and the book supports | Stays a refusal, or a verified name |
| NL-072 to NL-076, NL-078, NL-079, NL-082 to NL-084, NL-086, NL-087, NL-091 to NL-094, NL-105 | Batch round (WS5, WS4): each keeps a converse row; the `adjudication.toml` rows with `fix_status` OPEN move when produced | The emitted name equals the adjudicated target and reads back |
| NL-077, NL-081, NL-090, NL-095, NL-097 | Probe the shape (WS2 coverage matrix) or re-measure | Classed, or a defect row |
| NL-080, NL-096 | Source lookup (WS3) | Passage, page, rule written down, or source-unverified |
| NL-085, NL-088, NL-089 | None | Stay as recorded |
| NL-098, NL-099 | Re-measure from `benchmarks/naming/` round-14 artifacts and the named shapes | Each classed engine, validator or not reproduced |
| NL-104 | Re-measure, then split | Each sub-item classed |
| NL-105 | Include in the WS5 batch round; each is an `OPEN` row in `adjudication.toml` | The emitted name equals the adjudicated target; `fix_status` moves to FIXED |
| NL-106 | Source lookup (WS3) or a recorded decision that the book allows both | Verdict changes from UNDECIDED, or the row is kept as such with the reason |
| NL-107 | Decide the numbering rule that puts the heteroatoms at 1,5,8,11 (P-31.1.4 lowest locants for the spiro heteroatoms) and add a regression row | Engine gives the book's locants or the book's rule is shown not to apply |
| NL-108 | Check by hand whether the E/Z descriptor is valid on a one-atom bridge and whether the omitted one is a real stereo element | Correct, or defect filed with a regression row |
| NL-109 | Emit the allene axis of VS231 (find whether RDKit carries one; the suite lists `p`). The other three are done. Take the four entries from `compounds.smi`, state which stereo unit the engine does not emit (ring pseudoasymmetry, cumulene axis, ylidene E/Z, a stereocentre next to pseudoasymmetric rings), then decide per unit whether the contract requires it | Each unit emitted with a regression row, or recorded as correct but underspecified |
| NL-100 to NL-103 | None (split on 2026-10-27) | Closed |

## Triage coverage

Every `##` or `###` section of the application's `KNOWN_LIMITATIONS.md`, and where its open items went.

| Lines | Section | Disposition |
|---|---|---|
| 1-37 | Preamble, "The failure shape worth understanding first" | explanatory, no items |
| 38-134 | Open defects (severity A) | "None" and worked examples of closed defects; no open items |
| 135-144 | Observed, no verified target | `NL-050` |
| 145-214 | Benchmark: the standing 4 of 124 (tautomers, genuine wrong structures) | `NL-070`, `NL-071` (found on re-measure), `NL-088`, `NL-089`; the 1,2,3-triazole (D-026), diazomethane's other drawing (D-019) and purine entries are closed or deliberate |
| 215-256 | Severity B / unaudited data / Severity C | `NL-066`; every other entry closed (oxalyl dichloride D-065f, isobutane D-036c, malonamide, malonaldehyde) or explanatory |
| 257-339 | Refusal guard (resolved); substituent locants (closed round 4); indicated hydrogen (closed round 4) | closed in the source |
| 340-345 | Not limitations | explanatory |
| 346-351 | Round 16's open items (closed in round 17) | closed in the source |
| 352-367 | Open after D-191 and D-192 | D-193 closed in round 28; isotopic label work closed in round 29; no open item recorded |
| 368-378 | Open after P-14.4 (j) | closed by rounds 26 and 27 per the source; `NL-064` |
| 379-386 | Open after round 26 | `NL-059` |
| 387-393 | Open after the stereo cache fix | `NL-064`; the CIP-checked name (not read by read-back) is by design |
| 394-401 | Open after round 25 | `NL-059`, `NL-060`, `NL-001` (tropine and pseudotropine) |
| 402-409 | Open after round 24 | `NL-009`, `NL-061` |
| 410-421 | Open after round 23 | `NL-062` (D-179 fixed) |
| 422-451 | Open after rounds 22 and 21 | `NL-062`; D-171 and D-173 fixed |
| 452-470 | Open after round 20 | `NL-063` |
| 471-482 | Open after round 15 | D-163 fixed; instruments only |
| 483-574 | Open after round 13 | `NL-056` (ring-locant sweep); D-145 to D-150 fixed |
| 575-663 | Open after round 12 | D-144 fixed; the fused-cation signal was "not admitted", see `NL-055` |
| 664-714 | Open after round 11 | D-143, D-091v fixed; frequency tables, no open item |
| 715-747 | Open after round 10 | D-139 to D-142 fixed; frequency tables |
| 748-789 | Open after round 9 | D-130 `NL-042`; D-131 to D-138 fixed |
| 790-848 | Open after round 8 | `NL-072` to `NL-084`, `NL-090`; other rows closed (see *Closed by re-measurement*) |
| 849-890 | Open after round 7 | `NL-078` to `NL-081`; the rest closed or fixed in round 8 (see *Closed by re-measurement*) |
| 891-904 | Round 6, open after cyanic acid | `NL-065` |
| 905-947 | Open after round 5 | `NL-030` to `NL-042`, `NL-082`, `NL-085`, `NL-086`, `NL-092` to `NL-097`; other rows closed |
| 948-1019 | Open after round 4 | round 3 residue closed (see *Closed by re-measurement*) |
| 1020-1054 | Open after round 3, and the architecture notes | closed (chloroquine, warfarin, caffeine, xylene, DMSO, trimethylamine N-oxide re-measured); `NL-066` |
| 1055-1120 | Open after round 14 | `NL-056`, `NL-098`, `NL-099`, `NL-104` |
| 1121-1165 | Open after P-45.2.3, and the per-round bullets for rounds 27 to 89 | rounds 80 to 89 `NL-001` to `NL-026`; rounds 34 to 49 `NL-051` to `NL-057`; the other bullets are closed items |

The four cluster rows are split (see *Closed by re-measurement* for the entries that turned out to be closed). Two areas stay
incomplete and are named so that a later round can pick them up: `NL-052` (the round 46 to 48 lists are cut off in the source at a
line break), and rows `NL-051` to `NL-064`, which carry no structures in the text and were not re-measured. Nine rows of the split
(`NL-081`, `NL-090`, `NL-095`, `NL-097`, `NL-098`, `NL-099`, `NL-104`, `NL-077`, `NL-096`) say "not re-measured" for the same reason.

## Closed by re-measurement (2026-10-27)

Rows of the older sections whose target the engine now produces, each read back to its input on InChIKey. The engine's name today
is in the last column. These are closed in the sense of "the stated defect is gone"; none was checked against the book again.

| Source line | Shape | Engine name today |
|---|---|---|
| 810 | acyl prefix of a ring-nitrogen amide on a benzoic acid | `4-(piperidine-1-carbonyl)benzoic acid` |
| 811 | second prefix on a one-carbon ketone parent | `(morpholin-4-yl)(phenyl)methanone` |
| 817, 940 | substituted carbamimidoyl | `4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid` |
| 868, 869 | protonated imidazole, benzimidazole | `1H-imidazol-3-ium`, `1H-benzimidazol-3-ium` |
| 871 | serinate as drawn | `2-azaniumyl-3-oxidopropanoate` |
| 874 | citrate trianion | `2-hydroxypropane-1,2,3-tricarboxylate` |
| 875 | biguanidium cation | `[(dimethylamino)(imino)methyl]guanidinium` |
| 926, 938 | N'-acyl hydrazide; two acyl groups on one N | `N'-benzoylbenzohydrazide`, `N-acetylbenzamide` |
| 928 | C=O between two N= | `bis(phenyldiazenyl)methanone` |
| 930, 936 | disilane as a parent; full substitution | `methyldisilane`, `hexamethyldisiloxane` |
| 932 | triethanolamine | `2,2',2''-nitrilotri(ethan-1-ol)` |
| 934 | hydrazide on a systematic acid | `pentanehydrazide` |
| 939 | condensed ureas | `2-imidodicarbonic diamide` |
| 961-970 | multiplicative bis-guanidine, hydrazinecarboxamide, N-methylsulfamic acid, oxamide, silicic acid, N-carbamoylbenzamide, chain amidine, silanol with an alcohol, hydroxamic acid, tetrahydropyridine | `N'',N'''''-(tetradecane-1,14-diyl)diguanidine`, `hydrazinecarboxamide`, `N-methylsulfamic acid`, `oxamide`, `silicic acid`, `N-carbamoylbenzamide`, `5-amino-5-iminopentanoic acid`, `(2-hydroxyethyl)di(methyl)silanol`, `N-hydroxycyclohexanecarboxamide`, `1,2,3,6-tetrahydropyridine-4-carboxylic acid` |
| 974 | hydrazide beside a second acid (was an `OwnershipError`) | `4-hydrazinyl-4-oxobutanoic acid` |
| 1029-1034 | chloroquine, warfarin, caffeine, p-xylene, DMSO, trimethylamine N-oxide | `N4-(7-chloroquinolin-4-yl)-N1,N1-diethylpentane-1,4-diamine`, `4-hydroxy-3-(3-oxo-1-phenylbutyl)-2H-1-benzopyran-2-one`, `1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione`, `1,4-xylene`, `(methanesulfinyl)methane`, `N,N-dimethylmethanamine N-oxide` |


## Workstreams

Priority order. The detail of method is in the programme's plan; the short form:

0. **WS0, confirmed defects:** one round each, before the rest. Currently none open (`NL-070` closed in round 90).

1. **WS1, validator-limited stereo: an evidence-only audit first.** For one representative per mechanism, write the chain: the
   intended atom-level stereo; the descriptors the engine assigns *before* OPSIN validation; what OPSIN can parse or distinguish;
   the emitted name including any descriptor the validation path removed; the set of structures that name could denote; the
   independent evidence. Decide: **validator limitation** (descriptor correct, OPSIN cannot verify), **potential engine defect**
   (a correct descriptor stripped, or a distinction the contract requires lost), **unresolved identity** (no suitable oracle) or
   **correct but underspecified** (a contract decision). Order: `NL-003`, `NL-002`, `NL-001`, then the spiro cases `NL-005`.
   `_name_pins_structure` stays strict. An RDKit labeller is not independent ground truth against another RDKit labeller.
2. **WS2, coverage probes.** A coverage matrix is written before anything is generated (structural feature, stereo class, prior
   coverage, planned variants, oracle, pass and fail criteria). Unusual-spiro-atom probes stay separate from probes that challenge
   stereo assignment. Reuse `tools/naming_variants.py` (frozen structures refused; use `--orderings` where atom order matters) and
   `tools/naming_ion_populations.py`. Record the seed, and use a different seed to test generalisation.
3. **WS3, source lookups before code.** Record the exact passage, page, rule and applicability. If the book does not settle it,
   mark source-unverified.
4. **WS4, missing constructions** (`NL-030`, `NL-031`): lowest priority.
5. **WS5, older non-preferred names**: one batch round, each row with a converse or non-regression case.
6. **WS6, historical clusters:** done for the four clusters on 2026-10-27; what remains is re-measuring the rows they left `carried`.

**Exit rules.** A workstream is *inactive*, not proven correct, after two consecutive rounds that met the coverage matrix, covered
the right strata, and used a validator able to detect that failure class. Two more OPSIN-only rounds cannot clear an `r`/`s`
question; an empty sample cannot clear a feature never generated; a new defect reopens the workstream. Every round closes or
re-measures at least one row here; a measured non-reproduction counts if it records the exact input, seed, expected and observed
behaviour, and why the row stays open or closes.

**Regression surveillance.** The fast known-defects suite holds the expected emitted names. The OPSIN-backed suite shows that fixed
names round-trip. The frozen benchmarks (`benchmarks/naming/`) are measurement only and are never tuned against. Diagnostic
populations and `tools/naming_census_scan.py` discover and give before-and-after on unfrozen structures. Every engine-changing round
reports counts by defect class, not only the remaining `NAMING ERROR` rows, and re-runs the severity-A and stereo rows whenever it
touches parent selection, stereo, fusion or validation code.

**Evidence record.** For each investigated row, a saved artifact with: the canonical and related defect IDs; the exact input with
stereo annotations; the engine revision and the RDKit and OPSIN versions; the exact command and seed; the population generator and
its configuration; the output and read-back; the independent or source evidence (for a book rule: the passage, page, worked example
and why it applies); before and after results; the final disposition and remaining uncertainty.

## Dates per row

Five dates matter and none overwrites another: first identified, last relevant engine change, last direct reproduction, last
independent validation or source lookup, and the date this row was last reviewed. For this first version every row was last reviewed
on 2026-10-27. The other four are filled from the round that produced the row (first identified and last reproduction) and from the
merge date in the *Chronology* table; **last engine change** is "none since" for every open row unless a round says otherwise, and
**last independent validation** is "none" for every row. A later review replaces these rather than inferring them from when a
paragraph was edited.

| Round of origin | Merge date (git) | Rows first identified there |
|---|---|---|
| 80 | 2026-10-23 | `NL-019`, `NL-023`, `NL-024` |
| 81 | 2026-10-23 | `NL-013`, `NL-022`, `NL-026` |
| 82 | 2026-10-23 | `NL-014`, `NL-020`, `NL-022` |
| 83 | 2026-10-24 | `NL-015` |
| 84 | 2026-10-25 | `NL-012`, `NL-025` |
| 85 | 2026-10-26 | `NL-012` |
| 86 | 2026-10-26 | `NL-016`, `NL-018` |
| 87 | 2026-10-26 | `NL-016`, `NL-017` |
| 88 | 2026-10-26 | `NL-005`, `NL-010`, `NL-011`, `NL-021` |
| 89 | 2026-10-27 | `NL-001` to `NL-004`, `NL-006` |
| 3 to 79 | various (see `KNOWN_LIMITATIONS.md`) | `NL-007` to `NL-009`, `NL-030` to `NL-066`, `NL-070` to `NL-106` |
