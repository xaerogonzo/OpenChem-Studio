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

**Counts** (from the audit run for this PR). Canonical rows: 60, plus the 13 `OPEN` regression rows, each mapped to exactly one of them
(`NL-030` to `NL-042`). By class: W 0, M 6, I 6, B 23, V 4, S 9, U 6, N 2, C 4 (cluster rows of unremeasured historical entries). By
priority: P0 0, P1 13, P2 19, P3 28. By status: open 35, carried 22, blocked 2, closed 1.

**Plainly: no row is a *confirmed* wrong molecule, and that does not mean none exists.** Six rows (class M) record a name that OPSIN
reads back as a different molecule, found by a population run and never adjudicated as an engine fault or a validator fault. Six rows
(class I) are cases where the validator cannot say whether the name pins the intended stereoisomer. Neither group has been shown
harmless.

**Highest-priority next action.** `NL-003`, whether a bridged parent inside a larger molecule gets the right stereo descriptors. It
is cheap (a pure scope question, no new oracle), it decides how much of workstream 1 is real, and round 89's fallback was never run on
it.

**Workstreams.** WS1 stereo audit: *active*, not started. WS2 coverage probes: *active*, not started. WS3 source lookups: *active*,
not started. WS4 missing constructions: *deferred* (they round-trip today as von Baeyer names). WS5 older non-preferred names:
*deferred*. WS6 historical clusters: *active* (re-measure, then split or close).

**Blocked.** On a source the Blue Book PDF here does not print: `NL-017`, `NL-019` (status `blocked`). Waiting on an oracle that does
not exist yet for the failure class, status still `open`: `NL-001`, `NL-002`, `NL-004`; permanently a validator limit: `NL-020`.

**Last completed round.** Round 89, `4c0696b1`, merged 2026-10-27.

**Last reviewed.** 2026-10-27, by reading `KNOWN_LIMITATIONS.md` (all sections, with the older "Open after round 3 to 14" sections only
to cluster level, see *Triage coverage*) and the 13 strict-xfail rows of `OPEN` in `tests/test_namer_known_defects.py`.

**Known coverage gaps in this inventory.** The older sections for rounds 3 to 14 and the benchmark section hold 79 table rows that
read as open, many of which carry an inline "BUILT" or "FIXED" note and some of which were never re-measured. They are grouped into
the four cluster rows `NL-100` to `NL-103` instead of being asserted one by one. Splitting a cluster into canonical rows requires
re-measuring it first, which is itself the work of a round.

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
| C | cluster of unremeasured historical rows | stands for several older table rows whose present state is unknown; to be re-measured, then split |

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
| NL-001 | R89a | Isomers of a bridged parent that differ only in a pseudoasymmetric `r`/`s` centre share one name (2,6-dimethylnorbornane bridgeheads; positions 3 and 7 of 3,7-dimethylbicyclo[3.3.1]nonan-3-ol). OPSIN reads no `r`/`s`. | I | H | P1 | WS1 | open |
| NL-002 | R89b | OPSIN cannot anchor R/S at a substituted bridgehead (`bicyclo[3.3.1]nonan-1-ol`, 9-chloro-1-ol) and fails its own CIP assignment on some 3,7 patterns, so those isomers share a flat name. The engine's descriptors there are checked only by RDKit's labeller. | I | M | P1 | WS1 | open |
| NL-003 | R89c | The bridgehead fallback takes the ring atoms of the whole molecule; it equals the parent's bridgeheads only while the parent is the whole molecule. A bridged parent inside a larger molecule was **not tested**. | U | L | P1 | WS1 | open |
| NL-004 | R89d | 2,4-difluoroadamantane: four embeddable isomers got three names, two of which pin their isomer (the cage has more `r`/`s` centres than any other parent). | I | H | P1 | WS1 | open |
| NL-005 | R88d | The stereo layer was not triaged on ylidene-plus-stereo molecules (23 of 60 differ from the input) or on spiro names with an adamantane or bicyclo[2.2.2]octane parent, which name several embeddable isomers alike (`6'-methylspiro[tricyclo[3.3.1.1^{3,7}]decane-2,1'-cyclohexane]` for all 4; the non-spiro `4-methylbicyclo[2.2.2]octan-2-ol` for both enantiomers). Ring-forced versus free centres were not separated; the post-assembly OPSIN check drops descriptors it cannot read. | I | M | P1 | WS1 | open |
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
| NL-066 | R3 | 274 retained-name registry entries have no audited status; `tools/retained_name_audit.py` reports the backlog. | S | M | P2 | WS3 | carried |
| NL-100 | R3-R8 | Cluster, rounds 3 to 8 candidate-generation rows (lines 803 to 977 and 1029 to 1034 of `KNOWN_LIMITATIONS.md`): polynitrate esters, carbonic acid halides and anhydrides, N-alkoxy amides, benzil locants, peroxide/sulfur/phosphorus pseudoketones, diacyl peroxide and xanthate esters, deprotonated phosphonic and phosphoric acids, chiral amino-acid anions, protonated imidazole and benzimidazole, a betaine's cationic prefix, zwitterion with an anion of another class, `tert-butyl` in a PIN, phosphoryl prefixes, hypodiboric acid, chloroquine/warfarin/caffeine/p-xylene/DMSO/trimethylamine N-oxide (round 3 targets). **Many rows are marked BUILT or FIXED in line.** | C | L | P2 | WS6 | carried |
| NL-101 | R5 | Cluster, round 5 backlog (lines 905 to 946): second-order attached components, multiparent systems, interior heteroatoms, 7/8-membered rings fused on three or more sides, rings above eight members, hydro forms of a traditionally numbered retained parent, the P-44.1.2 senior-atom tier between two rings, ring-table entries that number only some positions (32, guarded), a(ba)n chains of chalcogen terminals. Overlaps `NL-030`, `NL-031`. | C | L | P2 | WS6 | carried |
| NL-102 | R8-R14 | Cluster, rounds 8 to 14 residue: the round-14 single-row misnames (an N-hydroxy-N-alkyl amide in an ester, an acylamidine, an oxime ether of a thioamidine, a purine hydro-prefix, an N vs N' hydrazide locant, a steroid oxime ether), bridged methano-benzocyclooctenes named as the wrong ring system, the neutral fused/spiro polycycles with "no valid plan", sulfonamide N- anions, and the unparsable shapes. Some are closed in later rounds (D-162 in round 38). | C | L | P2 | WS6 | carried |
| NL-103 | Bench | Cluster, the benchmark section (lines 145 to 250) and the older "Severity B / C / unaudited data" sections: the standing 4 of 124 (tautomers, genuine wrong structures), Severity B and C entries. **Not read item by item for this inventory.** | C | L | P2 | WS6 | carried |

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
| NL-051 to NL-056, NL-059 to NL-064 | Re-measure on the current engine, then split or close | Each sub-item classed |
| NL-057 | None | Stays validator limitation |
| NL-058 | Ask whether the two rows can be examined without reading a frozen row | Explained, or recorded `N` |
| NL-065 | None | Closed (no target exists) |
| NL-066 | Run `tools/retained_name_audit.py` | Backlog count recorded |
| NL-100 to NL-103 | Re-measure every row against the current engine (`benchmarks/naming/adjudication.toml` holds targets) | Cluster split into canonical rows, each classed, or closed |

## Triage coverage

Every `##` or `###` section of the application's `KNOWN_LIMITATIONS.md`, and where its open items went.

| Lines | Section | Disposition |
|---|---|---|
| 1-37 | Preamble, "The failure shape worth understanding first" | explanatory, no items |
| 38-134 | Open defects (severity A) | "None" and worked examples of closed defects; no open items |
| 135-144 | Observed, no verified target | `NL-050` |
| 145-214 | Benchmark: the standing 4 of 124 (tautomers, genuine wrong structures) | **cluster `NL-103`, not read item by item** |
| 215-256 | Severity B / unaudited data / Severity C | `NL-066`, **cluster `NL-103`** |
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
| 575-663 | Open after round 12 | D-144 fixed; the fused-cation signal was "not admitted", see `NL-055`, `NL-102` |
| 664-714 | Open after round 11 | D-143, D-091v fixed; frequency tables, no open item |
| 715-747 | Open after round 10 | D-139 to D-142 fixed; frequency tables |
| 748-789 | Open after round 9 | D-130 `NL-042`; D-131 to D-138 fixed |
| 790-848 | Open after round 8 | **cluster `NL-100`** |
| 849-890 | Open after round 7 | **cluster `NL-100`** |
| 891-904 | Round 6, open after cyanic acid | `NL-065` |
| 905-947 | Open after round 5 | **cluster `NL-101`**, rows `NL-030`, `NL-031`, `NL-032` to `NL-042` |
| 948-1019 | Open after round 4 | **cluster `NL-100`** (round 3 residue) |
| 1020-1054 | Open after round 3, and the architecture notes | **cluster `NL-100`**; the 274-entry registry audit `NL-066` |
| 1055-1120 | Open after round 14 | `NL-056`, `NL-102` |
| 1121-1165 | Open after P-45.2.3, and the per-round bullets for rounds 27 to 89 | rounds 80 to 89 `NL-001` to `NL-026`; rounds 34 to 49 `NL-051` to `NL-057`; the other bullets are closed items |

The three unfinished triage areas are `NL-052` (the round 46 to 48 lists are cut off in the source at a line break), `NL-103` (the
benchmark and Severity B/C sections) and the four cluster rows. Each is named so that a later round can pick it up.

## Workstreams

Priority order. The detail of method is in the programme's plan; the short form:

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
6. **WS6, historical clusters:** re-measure, then split into canonical rows or close.

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
| 3 to 79 | various (see `KNOWN_LIMITATIONS.md`) | `NL-007` to `NL-009`, `NL-030` to `NL-066`, `NL-100` to `NL-103` |
