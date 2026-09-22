# B1: the 23 `wrong_structure` rows on the Blue Book tuning half, triaged

Source: `benchmarks/naming/stages/r9-b1.json`, population `bluebook_tuning` (1129 rows).
`wrong_structure` here means OPSIN, applied to the **engine's own generated name**, does not
round-trip to the row's original structure -- this is oracle-independent of whether the book's
printed PIN is itself trustworthy (that question is B1's separate oracle-validity pipeline).

Every row below whose bucket note says "VERIFIED" was checked by actually parsing the engine's
name through OPSIN and comparing canonical SMILES / InChI against the original, not by reading the
names. Buckets are read-through categorisation for rows not individually verified; the pattern
(no anion/cation suffix anywhere in the name) is the same signal in every case, so the confidence
is high, but only the VERIFIED rows are asserted as confirmed.

This is a triage input for the end-of-B admissions ledger, not the ledger itself: nothing here is
committed to a fix slot. Counts are of `wrong_structure` rows only (23), not of B1 as a whole.

## Bucket A -- charge lost entirely (11 rows, dominant pattern: 48% of all wrong-structure rows)

The engine's name carries no anion/cation marker at all where the original structure has one (or,
for a symmetric di-charged species, drops one of two). VERIFIED: bb-153b7bd9e351, bb-50fa57d2a776,
bb-db0d904b9c97 (parsed through OPSIN and diffed against the original canonical SMILES).

| label | original (charge) | engine's name implies |
|---|---|---|
| bb-3914bf067e98 | `[C-]#[C-]` ethynediide (dianion) | `ethyne` (neutral) |
| bb-4ec6c6c83b27 | 1-phosphabicyclo[2.2.2]octan-1-uide (anion) | ...octane (neutral) |
| bb-70f2eee3ae7e | cyclobut-3-ene-1,2-bis(ylium) (dication) | `cyclobutane` (neutral, saturated) |
| bb-972f4e41e5a4 | butaniminide (anion) | 1-iminobutane (neutral) |
| bb-8bf128472635 | pent-1-yn-1-id-5-oate (dianion) | drops the alkynide charge (monoanion) |
| bb-d093313f0a6d | butanebis(nitrilium) (dication) | drops one of the two charges |
| bb-2249cf014e11 | anthracen-4a(2H)-ylium (cation); von Baeyer fallback keeps the ring unsaturation (`-hexaene`) but has no charge marker at all | (cation lost) |
| bb-74bda923e0b2 | dication (ring C+ and O+) | keeps the O+ (`oxidanium`), drops the ring C+ |
| **bb-153b7bd9e351** VERIFIED | `[C-]#[N+]...` isocyanide carbanion | OPSIN(engine name) = `C#[N+]...` -- the terminal C- became neutral CH |
| **bb-50fa57d2a776** VERIFIED | disodium bis-sulfinate salt (2x O-, 2x Na+) | OPSIN(engine name) gives neutral S=O and neutral Na (not Na+) throughout |
| **bb-db0d904b9c97** VERIFIED | bis(propan-2-ylium) dication | OPSIN(engine name) = `1,3-di(propan-2-yl)benzene`, fully neutral |

This is the headline B1 finding so far: charge state is the single most common way the engine
names the wrong molecule, and it recurs across unrelated functional-group families (carbanions,
carbocations, sulfinate salts, nitrilium, phosphide). Whether these route through one shared
charge-perception gap or several independent ones is exactly what the D-row trace needs to answer
before this becomes an admissions-ledger item; a single item with 11-row reach would be an unusually
strong F candidate under "a wrong molecule outranks frequency."

## Bucket B -- von Baeyer polycyclic fallback drops ring unsaturation entirely (3 rows)

Where the retained fusion name isn't available, the engine's numeric fallback names a fully
aromatic fused ring system with a saturated `-ane` parent suffix -- not merely a non-preferred
name, a structurally wrong one (missing every ring double bond). VERIFIED: bb-cd2b32859c12.

| label | printed (retained fusion name) | engine's fallback |
|---|---|---|
| bb-7ec8e8c1b941 | anthra[2,1,9-def:6,5,10-d'e'f']diisoquinoline | 7,18-diazaheptacyclo[...]hexacos**ane** |
| **bb-cd2b32859c12** VERIFIED | cyclopenta[ij]pentaleno[2,1,6-cde]azulene | pentacyclo[...]hexadec**ane** (OPSIN of this parses to a fully saturated ring system) |
| bb-e3c2f25abaa0 | phenanthro[1,10-bc:9,8-b'c'f]difuran-2,10-dione | ...octadec**ane**-11,18-dione |

Same subsystem (`ring_naming/vb_decompose.py`) that needed the per-row timeout fix (`dfbc7c69`) --
almost certainly covered by "fusion is explicitly out of scope this round," but recorded here
because it's a severe defect (fully wrong molecule, not a style choice) and belongs in "Open after
naming round 9," not forgotten.

## Bucket C -- an imine/oxime C=N rendered with the wrong bond order or position (3 rows)

| label | printed | engine (wrong) |
|---|---|---|
| bb-02e67d7545ab | `azanylylidenemethanylylidene` (=N-CH=) | `azanediylmethylene` (-NH-CH2-, saturated) |
| bb-6596d793fbc9 | `oxamoylimino` (=N-) | `acetamido` (-NH-C(=O)-, an amide) |
| **bb-a53d359b46f8** VERIFIED | O-C(=NH)- (carbamimidate ester) | OPSIN(engine name) gives O-N=CH- (an oxime-like swap of which atom carries the double bond) |

The verified row matches the shape of seed item **F7** (substituted carbamimidoyl, D-091v) closely
enough that it's likely the same underlying gap, not a new one.

## Bucket D -- wrong ring parent: an entire fused ring dropped (1 row, VERIFIED, high priority)

**bb-3e0b412fafed**: `O=C(O)Cc1cc2ccccc2cc1CC(=O)O` (a naphthalene-2,3-diyl diacetic acid) named
`2,2'-(1,2-phenylene)diacetic acid`. OPSIN of the engine's own name parses to
`O=C(O)Cc1ccccc1CC(=O)O` -- a **plain benzene ring**, four carbons short of the original fused
bicyclic naphthalene. This is not an obscure polycyclic-fusion case like Bucket B: naphthalene is
one of the most basic retained ring names in the nomenclature, so this looks like a genuine
parent-selection defect on an ordinary, high-frequency scaffold, not something "fusion is out of
scope" should be read to cover. Worth weighing heavily once B3's census gives a frequency number
for 2,3-disubstituted naphthalenes.

## Bucket E -- an atom or a double bond silently dropped in an S/P functional group (2 rows, both VERIFIED)

| label | defect |
|---|---|
| bb-9f8eab45027d | `CN=S(=O)(Br)NC` named `[(methylaminosulfinyl)amino]methane`; OPSIN of the engine's name gives `CNS(=O)NC` -- **the bromine atom is gone**, and the S=N imine bond became S-N single bond. Two things wrong in one row. |
| bb-9952c721a5d5 | `CN(N)P(=O)(N(C)N)N(C)N` (a P(V) phosphine oxide) named `1,1',1''-phosphanetriyltris(1-methylhydrazine)`; OPSIN of the engine's name gives a **trivalent P(III)** with no P=O at all. |

## Bucket F -- locant ambiguity across two symmetric-but-distinguishable substituent groups (1 row, VERIFIED)

**bb-ee1e7cac0062**: `CCN=C(N)C1(C(=N)N(C)C)CCCCC1`, a cyclohexane-1,1-dicarboximidamide with an
ethyl group on one carboxamidine's imino N and a dimethyl pair on the *other* carboxamidine's amino
N. The engine's name `N'-ethyl-N,N-dimethylcyclohexane-1,1-dicarboximidamide` puts **both**
substituents on the same carboxamidine group (verified: OPSIN of that name gives
`CCN=C(N(C)C)C1(C(=N)N)CCCCC1`, leaving the other carboxamidine fully unsubstituted) -- the N/N'
locant convention can't disambiguate which of two ring-symmetric-but-substituent-distinguished
groups a primed locant belongs to. Same family as Bucket C's F7 match.

## Bucket G -- missing fusion locants let OPSIN pick the wrong isomer (1 row, VERIFIED)

**bb-ea3dc696fc19**: `dibenzo[a,e][8]annulene` (printed, locants given) vs the engine's
`dibenzo[8]annulene` (no locants). OPSIN parses the unlocanted name to a **different** relative
ring-fusion arrangement (a biaryl-bonded isomer) than the original. The name isn't ambiguous to a
human who already knows the answer; it's ambiguous to a parser, and OPSIN's default guess is wrong.
Possibly covered by the same "fusion is out of scope" exclusion as Bucket B; flagged rather than
scoped in.

## Bucket H -- explicitly out of scope (1 row)

**bb-b857087b13c6**: a tetrasilacyclooctenyne. Silicon rows are explicitly excluded from round 9's
fixes per the plan. No further action this round.

## Summary

| bucket | rows | severity | likely in scope for round 9 |
|---|---:|---|---|
| A -- charge lost | 11 | high, systemic | yes -- strongest candidate seen so far |
| B -- fused-aromatic fallback loses unsaturation | 3 | high | no (fusion excluded) |
| C -- imine/oxime bond-order confusion | 3 | medium-high | yes, likely = F7 |
| D -- wrong ring parent (naphthalene) | 1 | high | yes -- ordinary scaffold, not fusion-exotic |
| E -- dropped atom/bond in S or P group | 2 | high | undecided -- narrow, needs a layer trace |
| F -- symmetric-substituent locant ambiguity | 1 | medium | yes, likely = F7 |
| G -- missing disambiguating fusion locants | 1 | medium | undecided, fusion-adjacent |
| H -- silicon | 1 | n/a | no (excluded) |

23 total. This is one input to the end-of-B admissions ledger, alongside B2 and B3 and the existing
seed list; nothing here fills a slot yet.
