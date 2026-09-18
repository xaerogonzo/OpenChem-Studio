"""Severity-A regression suite for the vendored IUPAC engine.

SEVERITY A MEANS THE ENGINE NAMED THE WRONG MOLECULE. Not a debatable
choice between two valid names -- a name that denotes something else.
The benzyl cation came out as `methylbenzene`, which is toluene; the
phthaloyl dication as `1,2-bis(oxomethyl)benzene`, which is
phthalaldehyde. Both were emitted with complete confidence and nothing in
the output to suggest a problem.

That is why this file lives in the DEFAULT test suite rather than in
tests/vendor/, which is excluded from the normal run because it takes
seven minutes. A wrong-molecule regression must surface on every run, not
only when somebody remembers to invoke the vendored suite. Everything
here is a single `name_smiles` call, so the whole file costs a second or
two.

Each expected name below was verified through the engine's own
correctness criterion -- parse it back with OPSIN and confirm it yields
the input structure, checked on canonical SMILES AND full InChIKey. That
verification needs a JRE, so it lives in the vendored suite; what is
pinned here is the resulting string, which needs nothing but RDKit.

`former` records what the engine used to emit. It is not decoration: when
one of these regresses, the failure message shows the wrong answer it
regressed to, which is usually enough to identify the cause without
bisecting.

OPEN defects are marked xfail(strict=True). If one starts passing the
test FAILS, which is the intended alarm -- it means somebody fixed it and
this file needs updating rather than silently drifting out of date.
"""

from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer import name_smiles

# (defect id, SMILES, correct name, name formerly emitted, what went wrong)
FIXED: list[tuple[str, str, str, str, str]] = [
    # --- D-001: ring polyacylium named as its neutral aldehyde ----------
    # _diacid_name_to_polyacylium had no rule for a "-carboxylic acid"
    # parent, returned None, and None routes to the plan-search
    # neutralizer instead of failing.
    ("D-001a", "O=[C+]c1ccccc1[C+]=O", "benzene-1,2-dicarbonylium",
     "1,2-bis(oxomethyl)benzene", "charge dropped; phthalaldehyde"),
    ("D-001b", "O=[C+]c1cccc([C+]=O)c1", "benzene-1,3-dicarbonylium",
     "1,3-bis(oxomethyl)benzene", "charge dropped"),
    ("D-001c", "O=[C+]c1ccc([C+]=O)cc1", "benzene-1,4-dicarbonylium",
     "1,4-bis(oxomethyl)benzene", "charge dropped"),
    ("D-001d", "O=[C+]C1CCCCC1[C+]=O", "cyclohexane-1,2-dicarbonylium",
     "1,2-bis(oxomethyl)cyclohexane", "charge dropped"),
    ("D-001e", "O=[C+]c1ccc2ccccc2c1[C+]=O", "naphthalene-1,2-dicarbonylium",
     "1,2-bis(oxomethyl)naphthalene", "charge dropped"),
    ("D-001f", "O=[C+]c1ccncc1[C+]=O", "pyridine-3,4-dicarbonylium",
     "3,4-bis(oxomethyl)pyridine", "charge dropped"),
    ("D-001g", "O=[C+]c1cc([C+]=O)cc([C+]=O)c1", "benzene-1,3,5-tricarbonylium",
     "1,3,5-tris(oxomethyl)benzene", "charge dropped (trication)"),

    # --- D-005: -ylium / -ide locant hardcoded to 1 ---------------------
    # _render_simple_carbon assumed the charged carbon is always at
    # position 1. True for the four terminal-charge audit compounds it was
    # written against, false for everything else -- and because no test
    # exercised a non-terminal charge, the OPSIN round-trip never caught
    # it. Now the engine is asked to name the skeleton as a SUBSTITUENT
    # anchored at the charged atom, so its own parent selection and
    # numbering decide.
    ("D-005a", "C[CH+]C", "propan-2-ylium",
     "propan-1-ylium", "charge moved to C1; isopropyl vs n-propyl cation"),
    ("D-005b", "C[C-](C)C", "2-methylpropan-2-ide",
     "isobutan-1-ide", "charge moved to a methyl carbon"),
    ("D-005c", "C[C+](C)C", "2-methylpropan-2-ylium",
     "isobutan-1-ylium", "charge moved to a methyl carbon"),
    ("D-005d", "[CH2+]C1CCCCC1", "cyclohexylmethan-1-ylium",
     "methylcyclohexan-1-ylium", "charge moved onto the ring"),
    ("D-005e", "[CH2-]C1CCCCC1", "cyclohexylmethan-1-ide",
     "methylcyclohexan-1-ide", "charge moved onto the ring"),
    ("D-005f", "[CH2+]CC(C)C", "3-methylbutan-1-ylium",
     "2-methylbutan-1-ylium", "branch locant numbered from the wrong end"),
    ("D-005g", "CC[CH+]CC", "pentan-3-ylium",
     "pentan-1-ylium", "charge moved to C1"),
    ("D-005h", "[CH+]1CCCC(C)C1", "3-methylcyclohexan-1-ylium",
     "methylcyclohexan-1-ylium", "substituent locant dropped"),
    ("D-005i", "CC(C)[CH+]C(C)C", "2,4-dimethylpentan-3-ylium",
     "2,4-dimethylpentan-1-ylium", "charge moved to C1"),

    # --- D-002 family: charge next to unsaturation or aromaticity ------
    # _classify_simple_carbon_charge required every atom non-aromatic and
    # every bond single, so it claimed nothing here -- and an unclaimed
    # charge is not left alone, it falls through to the plan-search
    # neutralizer. The restriction bought nothing: the renderer drives the
    # engine in substituent mode, which names these skeletons perfectly
    # well (phenylmethan-1-yl, prop-2-en-1-yl, ethen-1-yl).
    ("D-002", "[CH2+]c1ccccc1", "phenylmethan-1-ylium",
     "methylbenzene", "charge dropped; toluene"),
    ("D-011", "[CH2-]c1ccccc1", "phenylmethan-1-ide",
     "methylbenzene", "charge dropped; toluene"),
    ("D-009", "[CH2+]C=C", "prop-2-en-1-ylium",
     "prop-1-ene", "charge dropped; propene"),
    ("D-012", "[CH2-]C=C", "prop-2-en-1-ide", "prop-1-ene", "charge dropped"),
    ("D-010", "[CH+]=C", "ethen-1-ylium", "ethene", "charge dropped"),
    ("D-014", "[CH+](c1ccccc1)c1ccccc1", "diphenylmethan-1-ylium",
     "(phenylmethyl)benzene", "charge dropped; diphenylmethane"),
    ("D-017", "[CH2+]C#C", "prop-2-yn-1-ylium",
     "prop-1-yne", "charge dropped; propyne"),

    # --- D-003: aromatic ring carbanion -------------------------------
    # No classifier claimed these, so the plan search neutralized them --
    # the phenyl anion lost its charge AND its aromaticity. An aromatic
    # ring carbanion needs the RING parent's numbering, which is exactly
    # why _classify_simple_carbon_charge refuses an aromatic charged atom.
    ("D-003", "c1ccc[c-]c1", "benzen-1-ide",
     "cyclohexane", "charge AND aromaticity dropped"),
    ("D-003b", "[c-]1cccc2ccccc12", "naphthalen-1-ide",
     "(unclaimed)", "generalises to fused rings"),
    ("D-003c", "[c-]1ccc2ccccc2c1", "naphthalen-2-ide",
     "(unclaimed)", "locant comes from the engine's own numbering"),
    ("D-003d", "[c-]1cccnc1", "pyridin-3-ide",
     "(unclaimed)", "generalises to heteroaromatic rings"),
    ("D-003e", "[c-]1ccccn1", "pyridin-2-ide", "(unclaimed)", "as above"),

    # --- D-004: guanidinium -------------------------------------------
    # _classify_amidinium requires the third substituent on the central
    # carbon to be a CARBON, so guanidinium -- whose third substituent is
    # another amino nitrogen -- fell through to the neutralizer.
    ("D-004", "[NH2+]=C(N)N", "guanidinium",
     "iminomethane-1,1-diamine", "charge dropped"),

    # --- D-016: azide -------------------------------------------------
    # No classifier claimed the N3 chain, so the plan search produced
    # "diiminoazanium" -- which denotes N=[N+]=N, a CATION. The same one
    # name came out for the anion (q=-1) AND its conjugate acid (q=0),
    # so one confident answer covered three different species and matched
    # none of them. Azide belongs with the other retained pseudohalides
    # (cyanide, thiocyanate, cyanate, isocyanate, isothiocyanate) in the
    # curated inorganic table, and simply was not there.
    ("D-016", "[N-]=[N+]=[N-]", "azide",
     "diiminoazanium", "named a cation for an anion"),
    ("D-016b", "N=[N+]=[N-]", "hydrogen azide",
     "diiminoazanium", "same wrong name as its conjugate base"),
    ("D-016c", "[Na+].[N-]=[N+]=[N-]", "sodium azide",
     "sodium diiminoazanium", "salt path inherited the wrong ion name"),

    # --- non-regression: the rest of the pseudohalide block ------------
    ("D-016x", "[C-]#N", "cyanide", "cyanide", "unchanged"),
    ("D-016y", "N#C[S-]", "thiocyanate", "thiocyanate", "unchanged"),
    ("D-016z", "[N-]=C=S", "isothiocyanate", "isothiocyanate", "unchanged"),
    # Organic azides never went through the ion table -- the azido
    # substituent prefix is a separate path and was always correct.
    ("D-016w", "CCN=[N+]=[N-]", "azidoethane", "azidoethane", "unchanged"),

    # --- D-022: pre-composed retained ring in substituent position -----
    # "5-pyrazolone" encodes C4's saturation only by convention, so
    # attaching there ("...-5-pyrazolon-4-yl") removed the hydrogen that
    # made C4 sp3 and OPSIN re-read the ring as its aromatic tautomer -- a
    # different species. Any senior characteristic group that pushes the
    # ring into substituent position hit it: amide, acid, nitrile.
    #
    # The retained lookup cannot see the substituent case: it receives the
    # carved fragment, which is byte-identical to the standalone molecule,
    # and is not told the output form. 5-pyrazolone is semi-systematic
    # rather than a PIN, so it is now declined outright and the systematic
    # path -- which states the saturation explicitly -- is correct in both
    # positions.
    ("D-022", "CC1=NN(c2ccccc2)C(=O)C1CCNC(C)=O",
     "N-[2-(3-methyl-5-oxo-1-phenyl-4,5-dihydro-1H-pyrazol-4-yl)ethyl]acetamide",
     "N-[2-(3-methyl-1-phenyl-5-pyrazolon-4-yl)ethyl]acetamide",
     "ring re-read as its aromatic tautomer"),
    ("D-022b", "CC1=NN(c2ccccc2)C(=O)C1CCC(=O)O",
     "3-(3-methyl-5-oxo-1-phenyl-4,5-dihydro-1H-pyrazol-4-yl)propanoic acid",
     "3-(3-methyl-1-phenyl-5-pyrazolon-4-yl)propanoic acid", "as above"),
    ("D-022c", "CC1=NN(c2ccccc2)C(=O)C1CC#N",
     "2-(3-methyl-5-oxo-1-phenyl-4,5-dihydro-1H-pyrazol-4-yl)ethanenitrile",
     "2-(3-methyl-1-phenyl-5-pyrazolon-4-yl)ethanenitrile", "as above"),

    # --- D-013 / D-018: the all-carbon classifier gate ------------------
    # _classify_simple_carbon_charge required EVERY atom to be carbon, far
    # stronger than the reason for the gate: heteroatom motifs (acylium,
    # iminium, amidinium) all have the heteroatom bonded directly to the
    # charged atom, so checking the charged atom's own NEIGHBOURS is
    # enough. The stronger form left any charge on a hetero-containing
    # skeleton unclaimed, and unclaimed means neutralized.
    ("D-018", "[CH2+]c1ccncc1", "(pyridin-4-yl)methan-1-ylium",
     "4-methylpyridine", "charge dropped"),
    ("D-018b", "[CH2-]c1ccncc1", "(pyridin-4-yl)methan-1-ide",
     "4-methylpyridine", "charge dropped"),
    ("D-018c", "[CH2+]c1ccco1", "(furan-2-yl)methan-1-ylium",
     "2-methylfuran", "charge dropped"),
    ("D-018d", "[CH2+]COC", "2-methoxyethan-1-ylium",
     "1-methoxyethane", "charge dropped"),
    # Charge-separated groups elsewhere (nitro, azido) carry no net charge
    # and are ordinary prefixes, but detect()'s coverage gate needs them
    # claimed or it refuses the molecule.
    ("D-018e", "[CH2+]c1ccc([N+](=O)[O-])cc1", "(4-nitrophenyl)methan-1-ylium",
     "4-methyl-1-nitrobenzene", "charge dropped"),
    ("D-018f", "[CH2+]CN=[N+]=[N-]", "2-azidoethan-1-ylium",
     "1-azidoethane", "charge dropped"),
    # Formylium is the R=H acylium. _classify_acylium cannot reach it --
    # it demands no hydrogen on the [C+] and a single-bonded R, and
    # formylium has one H and no R -- so the single species is curated.
    ("D-013", "[CH+]=O", "formylium", "oxomethane", "charge dropped"),

    # --- D-015: azolide charge relocated from N to C --------------------
    # Worse than dropping the charge: the plan search MOVED it, naming
    # pyrrolide "1H-pyrrol-2-ide" with the charge on a ring carbon. The
    # ring-anion classifier now covers nitrogen as well as carbon. The
    # trap was the neutralization probe: an aromatic ring N needs its
    # hydrogen stated EXPLICITLY or the ring will not kekulize, which
    # presented as "not an aromatic ring anion" and skipped the family.
    ("D-015", "[n-]1cccc1", "1H-pyrrol-1-ide",
     "1H-pyrrol-2-ide", "charge relocated from N to C"),
    ("D-015b", "[n-]1ccnc1", "1H-imidazol-1-ide",
     "1,3-diazol-3-ide", "Hantzsch-Widman stem instead of the retained PIN"),
    ("D-015c", "c1nnn[n-]1", "1H-tetrazol-1-ide",
     "1,2,3,4-tetraazol-1-ide", "as above"),
    ("D-015d", "[n-]1cccn1", "1H-pyrazol-1-ide",
     "1,2-diazol-2-ide", "as above"),
    # NOT a defect fix, recorded so the change is not mistaken for one:
    # the fused azolide was ALREADY correct as "1H-indol-1-ide". Routing it
    # through the ring-anion classifier changed it to "indol-1-ide", which
    # round-trips just as well. One right name replaced another.
    ("D-015e", "[n-]1ccc2ccccc21", "indol-1-ide",
     "1H-indol-1-ide", "was already correct; wording changed"),

    # --- D-019: diazoalkane ylide ---------------------------------------
    # Net-neutral but carrying both a carbanion and a diazonium.
    # _classify_diazonium claimed only the two nitrogens, leaving the
    # carbanion uncovered, so the coverage gate refused the molecule.
    # Named as the carbanion's own "-ide" name + "yldiazonium", which
    # delegates parent selection and locants to the renderer that already
    # gets them right.
    ("D-019", "[CH2-][N+]#N", "methanidyldiazonium",
     "(azanylidyne)(methyl)azanium", "gained an H; emitted the cation"),
    ("D-019b", "C[CH-][N+]#N", "ethan-1-id-1-yldiazonium",
     "<raised: partial_claim>", "generalises to diazoalkanes"),
    # The diazonium sits on the SAME carbon as the charge, so its locant
    # must be stated: "propan-2-idyl" lets OPSIN default the attachment to
    # C1, giving the 1-diazonio-2-ide -- a different molecule.
    ("D-019c", "C[C-](C)[N+]#N", "propan-2-id-2-yldiazonium",
     "<raised: partial_claim>", "attachment locant must be cited"),
    ("D-019d", "[CH-](c1ccccc1)[N+]#N", "phenylmethan-1-id-1-yldiazonium",
     "<raised: partial_claim>", "as above"),

    # --- D-020: N-substituted guanidinium -------------------------------
    ("D-020", "CNC(N)=[NH2+]", "methylguanidinium",
     "N-(aminoiminomethyl)methanamine", "charge dropped"),
    ("D-020b", "CCNC(N)=[NH2+]", "ethylguanidinium",
     "N-(aminoiminomethyl)ethanamine", "one N-substituent as a prefix"),
    ("D-020c", "c1ccccc1NC(N)=[NH2+]", "phenylguanidinium",
     "N-(aminoiminomethyl)benzen-1-amine", "as above"),

    # --- D-026: indicated hydrogen discarded ----------------------------
    # The 2H entry in the ring table was labelled "1H-1,2,3-triazole" -- the
    # wrong tautomer -- and the 1H form had no entry at all, so BOTH inputs
    # came back as the 1H structure and the indicated hydrogen the caller
    # supplied was thrown away. Same class as silently flattening
    # stereochemistry: information the input carried, discarded without a
    # word. The 1,2,4-triazole and tetrazole entries beside it already
    # distinguished their tautomers correctly.
    ("D-026", "c1cn[nH]n1", "2H-1,2,3-triazole",
     "1H-1,2,3-triazole", "named the other tautomer"),
    ("D-026b", "c1c[nH]nn1", "1H-1,2,3-triazole",
     "1,2,3-triazole", "had no entry; fell through to the generic name"),

    # --- non-regression: tautomer pairs that were already right ---------
    ("D-026x", "c1nc[nH]n1", "1H-1,2,4-triazole", "1H-1,2,4-triazole",
     "unchanged"),
    ("D-026y", "c1nnc[nH]1", "4H-1,2,4-triazole", "4H-1,2,4-triazole",
     "unchanged"),
    ("D-026z", "c1nnn[nH]1", "1H-tetrazole", "1H-tetrazole", "unchanged"),
    ("D-026w", "c1nn[nH]n1", "2H-tetrazole", "2H-tetrazole", "unchanged"),
    # SUPERSEDED BY D-036o. This row belonged to the indicated-hydrogen work
    # (D-026) and used caffeine only as a non-regression witness that the
    # xanthine tautomers were not disturbed. The witness still holds -- the
    # structure is named correctly -- but `caffeine` is not a PIN, so the
    # string moved. Its citation in the registry was `P-31.1.3`, which is
    # about indicated hydrogen and says nothing about retaining the name:
    # the row and the bad citation came from the same neighbourhood.
    ("D-026v", "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
     "1,3,7-trimethyl-2,6-dioxo-1H-purine", "caffeine",
     "tautomer handling unchanged; the retained name was never a PIN"),
    # Purine deliberately normalises all four tautomers to 9H-purine, the
    # IUPAC preferred parent, with atom_locants built so N9 gets locant 9
    # whatever the canonical SMILES does. Documented in data_loader.py and
    # left alone -- it underpins the whole xanthine family.
    ("D-026u", "c1ncc2nc[nH]c2n1", "9H-purine", "9H-purine", "unchanged"),

    # --- D-024: ring N-oxide in substituent position --------------------
    # Additive nomenclature produces a two-word name ("pyridine 1-oxide"),
    # and a substituent must end in "-yl" for its parent to attach to --
    # there is nothing to attach to the end of the word "oxide". Emitting
    # it anyway gave "(pyridin-4-yl)methan-1-ylium 1-oxide", unparsable.
    # The additive path now steps aside in substituent output form, and the
    # substitutive path already knew how: "1-(oxido)pyridin-1-ium-4-yl".
    # Standalone output is untouched, so "pyridine 1-oxide" and
    # "pyridine-4-carboxylate 1-oxide" keep the additive form correct for them.
    ("D-024", "[CH2+]c1cc[n+]([O-])cc1",
     "[1-(oxido)pyridin-1-ium-4-yl]methan-1-ylium",
     "(pyridin-4-yl)methan-1-ylium 1-oxide", "unparsable; oxide wrapped a cation"),
    ("D-024b", "[CH2-]c1cc[n+]([O-])cc1",
     "[1-(oxido)pyridin-1-ium-4-yl]methan-1-ide",
     "(unclaimed)", "same shape, anion"),

    # --- non-regression: additive names that MUST keep the two-word form
    ("D-024x", "[O-][n+]1ccccc1", "pyridine 1-oxide", "pyridine 1-oxide",
     "unchanged"),
    ("D-024y", "[O-]C(=O)c1cc[n+]([O-])cc1", "pyridine-4-carboxylate 1-oxide",
     "pyridine-4-carboxylate 1-oxide", "unchanged"),
    # SUPERSEDED BY D-036e. This row pinned the additive form as unchanged,
    # and the additive PATH is indeed untouched -- what changed underneath it
    # is the parent: `trimethylamine` is a traditional name, not a PIN, and
    # the book prints all three forms on one line saying so. The additive
    # `... oxide` construction this row exists to guard is still in use, now
    # on the systematic parent.
    ("D-024z", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine oxide",
     "trimethylamine oxide", "additive path unchanged; the PARENT is now the PIN"),
    ("D-024w", "CS(C)=O", "dimethyl sulfoxide", "dimethyl sulfoxide",
     "unchanged"),

    # --- D-025: more than one N-substituent on guanidinium --------------
    # Guanidine numbers the charged (imino) nitrogen 2 and the two amino
    # nitrogens 1 and 3. Lowest locants go to the more heavily substituted
    # amino nitrogen, which is what makes the trimethyl case 1,1,3- rather
    # than 1,3,3-.
    ("D-025", "CNC(NC)=[NH2+]", "1,3-dimethylguanidinium",
     "1-imino-N,N'-dimethylmethane-1,1-diamine", "charge dropped"),
    ("D-025b", "CN(C)C(N)=[NH2+]", "1,1-dimethylguanidinium",
     "N-(aminoiminomethyl)-N-methylmethanamine",
     "both substituents on one nitrogen"),
    ("D-025c", "CNC(=[NH2+])N(C)C", "1,1,3-trimethylguanidinium",
     "N-[(imino)(methylamino)methyl]-N-methylmethanamine",
     "lowest locants to the more substituted nitrogen"),
    ("D-025d", "CNC(N)=[NH+]C", "1,2-dimethylguanidinium",
     "N-{amino[amino(methyl)azaniumylidene]methyl}methanamine",
     "the charged nitrogen is locant 2"),
    ("D-025e", "CCNC(=[NH2+])NC", "1-ethyl-3-methylguanidinium",
     "N-ethyl-1-imino-N'-methylmethane-1,1-diamine",
     "different prefixes, alphabetical order"),

    # --- non-regression: motifs the relaxed gate must NOT steal ---------
    ("D-013x", "[C+](C)=O", "acetylium", "acetylium", "unchanged"),
    ("D-013y", "CC(=[NH2+])N", "acetamidinium", "acetamidinium", "unchanged"),
    ("D-013z", "CC[N+]#N", "ethane-1-diazonium", "ethane-1-diazonium",
     "unchanged"),
    ("D-015x", "c1cc[nH]c1", "1H-pyrrole", "1H-pyrrole", "unchanged"),
    ("D-015y", "[O-][n+]1ccccc1", "pyridine 1-oxide", "pyridine 1-oxide",
     "unchanged"),
    ("D-020x", "[NH2+]=C(N)N", "guanidinium", "guanidinium", "unchanged"),

    # --- D-023: pyrazole stem lost in the partially-saturated path -----
    # Severity B, not A -- the molecule was right, the ring stem was not.
    # With no curated entry for the partially-saturated 1,2-diazole ring,
    # naming fell through to Hantzsch-Widman, which spells it
    # "1,2-diazole". "pyrazole" is the retained PIN (P-25.2.1). Only
    # pyrazole was affected: imidazole and pyrrole already had curated
    # partially-saturated entries, and oxazole/thiazole get away without
    # one because their HW names ("1,3-oxazole", "1,3-thiazole") ARE the
    # preferred forms. Pyrazole is the sole 5-ring here whose HW name
    # differs from its PIN.
    ("D-023", "C1C=NNC1", "4,5-dihydro-1H-pyrazole",
     "4,5-dihydro-1H-1,2-diazole", "HW stem instead of the retained PIN"),
    ("D-023b", "C1NNC=C1", "2,3-dihydro-1H-pyrazole",
     "2,3-dihydro-1H-1,2-diazole", "as above"),
    ("D-023c", "CC1=NN(c2ccccc2)C(=O)C1",
     "3-methyl-1-phenyl-4,5-dihydro-1H-pyrazol-5-one",
     "3-methyl-1-phenyl-4,5-dihydro-1H-1,2-diazol-5-one",
     "edaravone core; stem propagates through the whole pyrazolone family"),
    ("D-023d", "C1C=NN(c2ccccc2)C1", "(4,5-dihydro-1H-pyrazol-1-yl)benzene",
     "(4,5-dihydro-1H-1,2-diazol-1-yl)benzene", "substituent form too"),

    # --- non-regression: sibling 5-rings the new curated entries sit
    # beside, which must keep the names they already had.
    ("D-023x", "c1cc[nH]n1", "1H-pyrazole", "1H-pyrazole", "unchanged"),
    ("D-023y", "C1CNNC1", "pyrazolidine", "pyrazolidine", "unchanged"),
    ("D-023z", "C1CN=CN1", "4,5-dihydro-1H-imidazole",
     "4,5-dihydro-1H-imidazole", "unchanged"),
    ("D-023w", "C1CC=CN1", "2,3-dihydro-1H-pyrrole",
     "2,3-dihydro-1H-pyrrole", "unchanged"),
    ("D-023v", "C1COC=N1", "4,5-dihydro-1,3-oxazole",
     "4,5-dihydro-1,3-oxazole", "unchanged"),

    # --- non-regression: the other PIN-ineligible retained stems, which
    # share the gate that was extended to reach the pyrazolone.
    ("D-022x", "C1Cc2ccccc2C1", "2,3-dihydro-1H-indene",
     "2,3-dihydro-1H-indene", "unchanged"),
    ("D-022y", "C1CCc2ccccc2C1", "1,2,3,4-tetrahydronaphthalene",
     "1,2,3,4-tetrahydronaphthalene", "unchanged"),
    # Pre-composed retained stems that are still PIN-eligible and must keep
    # their retained names, including in substituent position.
    # The free-valence locant here MOVED with D-029, and the new one is
    # right: sulfolene's S is locant 1 either way round and both directions
    # give "en-3", so the choice falls to the free valence, which P-31.1.4
    # ranks (d) above the ene ending (e). Both names round-trip to this
    # structure on canonical SMILES and InChIKey (checked before editing a
    # pinned row), so this is a preferred-name change, not a wrong molecule.
    ("D-022z", "O=S1(=O)CC=CC1CCN", "2-(sulfol-3-en-2-yl)ethanamine",
     "2-(sulfol-3-en-5-yl)ethanamine", "free valence took the higher locant"),
    ("D-022w", "O=c1[nH][nH]c(=O)[nH]1", "urazol", "urazol", "unchanged"),
    # 4-pyrazolone changed as a consequence of the D-023 curated entries,
    # and the change is kept rather than worked around. Adding a curated
    # ring entry for the 2,3-dihydro-1H-pyrazole skeleton gives it priority
    # over the pre-composed "4-pyrazolone" stem, so this ring now takes the
    # systematic form -- which is exactly the treatment 5-pyrazolone was
    # given for being semi-systematic rather than a PIN. Both pyrazolone
    # stems now behave the same way. Verified to round-trip on both gates.
    ("D-022v", "O=C1C=NNC1", "4,5-dihydro-1H-pyrazol-4-one",
     "4-pyrazolone", "semi-systematic stem replaced by the systematic form"),

    # --- non-regression: delocalised aromatic anions the ring-carbanion
    # classifier must NOT steal. Cyclopentadienide keeps its hydrogen and
    # is a delocalised pi anion with a retained name; benzenide is a sigma
    # carbanion with the hydrogen removed. Gating on "no H on the charged
    # carbon" is what separates them -- written as [cH-]1cccc1 the
    # cyclopentadienide is closed-shell, so a radical test does not.
    ("D-003x", "[cH-]1cccc1", "cyclopentadienide", "cyclopentadienide",
     "unchanged"),
    # Ferrocene reaches the ring-carbanion classifier one fragment at a
    # time, so a substituted cyclopentadienide arrives on its own. Two
    # cheaper gates were tried and both let it through: "no radical" (it
    # is closed-shell) and "no hydrogen on the charged carbon" (a chlorine
    # occupies that position rather than a proton having left it). With
    # the refusal guard in place, over-claiming here raised instead of
    # mis-naming -- louder, but still a regression.
    ("D-003y", "c1cc[cH-]c1.[Fe+2].c1cc[cH-]c1", "ferrocene", "ferrocene",
     "unchanged"),

    # --- non-regression: retained ring cations the relaxed gate must NOT
    # steal. These carry retained -ylium PINs owned by the retained-ring
    # lookup; claiming them in the simple-carbon classifier would quietly
    # replace a correct retained name with the systematic one
    # ("phenylium" -> "benzene-1-ylium"). A Kekule-written ring cation is
    # not flagged aromatic by RDKit, so the guard is ring saturation, not
    # the aromatic flag.
    ("D-002x", "[C+]1=CC=CC=C1", "phenylium", "phenylium", "unchanged"),
    ("D-002y", "[O+]1=CC=CC=C1", "pyrylium", "pyrylium", "unchanged"),
    ("D-002z", "[C+](C)=O", "acetylium", "acetylium", "unchanged"),

    # --- non-regression: shapes the locant fix must NOT disturb ---------
    ("D-005j", "[CH2+]C", "ethan-1-ylium", "ethan-1-ylium", "unchanged"),
    ("D-005k", "[CH2+]CCCC", "pentan-1-ylium", "pentan-1-ylium", "unchanged"),
    ("D-005l", "[CH+]1CCCCC1", "cyclohexan-1-ylium", "cyclohexan-1-ylium",
     "unchanged"),
    ("D-005m", "[CH3+]", "methylium", "methylium", "unchanged"),
    ("D-005n", "[CH3-]", "methanide", "methanide", "unchanged"),

    # --- D-027: a descriptor inside a substituent recomputed on the fragment --
    # Carving replaces the cut side with H, which reorders CIP priorities at
    # any centre or double bond whose ranking depended on that side. The
    # first carve already inherited the parent's descriptors; a NESTED carve
    # started from the first fragment and recomputed, and E/Z never
    # inherited at all. Every E/Z measured inside a substituent was inverted.
    # MPMI's R centre (named (5S)) is pinned with its locant in D-028.
    ("D-027a", "C/C=C(/C)c1ccc(cc1)C(=O)O", "4-[(2Z)-but-2-en-2-yl]benzoic acid",
     "4-[(2E)-but-2-en-2-yl]benzoic acid", "E/Z inverted on the attachment carbon"),
    ("D-027b", "C/C=C(\\C)c1ccc(cc1)C(=O)O", "4-[(2E)-but-2-en-2-yl]benzoic acid",
     "4-[(2Z)-but-2-en-2-yl]benzoic acid", "E/Z inverted, other isomer"),
    ("D-027c", "OC(=O)c1ccc(cc1)/C(C)=C/Cc1ccccc1",
     "4-[(2E)-4-phenylbut-2-en-2-yl]benzoic acid",
     "4-[(2Z)-4-phenylbut-2-en-2-yl]benzoic acid", "E/Z inverted, nested phenyl"),
    # non-regression: descriptors that were already right must stay right
    ("D-027x", "OC(=O)c1ccc(cc1)/C=C/C", "4-[(1E)-prop-1-en-1-yl]benzoic acid",
     "4-[(1E)-prop-1-en-1-yl]benzoic acid", "unchanged"),
    ("D-027y", "OC(=O)c1ccc(cc1)[C@H](C)CC", "4-[(2R)-butan-2-yl]benzoic acid",
     "4-[(2R)-butan-2-yl]benzoic acid", "unchanged"),
    ("D-027z", "N[C@@H](C)C(=O)N[C@@H](Cc1ccccc1)C(=O)O",
     "(2S)-2-[(2S)-2-aminopropanoylamino]-3-phenylpropanoic acid",
     "(2S)-2-[(2S)-2-aminopropanoylamino]-3-phenylpropanoic acid", "unchanged"),

    # --- D-028: prefixes cited out of alphanumerical order ---------------
    # SEVERITY B, not A: the right molecule, cited in the wrong order, so it
    # round-trips and the naming benchmark scores it "equivalent". The sort
    # key kept nested brackets (which sort before every letter) and filed
    # "dimethylamino" under m. See `assembly.derive_sort_name`.
    ("D-028a", "CC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1",
     "N-phenyl-N-[1-(2-phenylethyl)piperidin-4-yl]acetamide",
     "N-[1-(2-phenylethyl)piperidin-4-yl]-N-phenylacetamide", "compound prefix cited first"),
    ("D-028b", "CCCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1",
     "N-phenyl-N-[1-(2-phenylethyl)piperidin-4-yl]butanamide",
     "N-[1-(2-phenylethyl)piperidin-4-yl]-N-phenylbutanamide", "compound prefix cited first"),
    ("D-028c", "CN(C)c1ccc(C(=O)O)c(CC)c1", "4-(dimethylamino)-2-ethylbenzoic acid",
     "2-ethyl-4-(dimethylamino)benzoic acid", "dimethylamino filed under m"),

    # --- D-029: a heterocyclyl free valence numbered by plan order ---------
    # SEVERITY B. P-31.1.4.2.4 ranks free valences with suffixes, ahead of
    # every prefix; the engine scored the free valence nowhere, so on a ring
    # whose heteroatom numbering has two equal directions the tie decided.
    # The carved fragment 1-methylpyrrolidine has C2 == C5 by symmetry, so
    # which of them was the attachment depended on the input's atom order.
    # Fixed by `engine._lowest_free_valence_numberings`.
    # The three tryptamines also pin D-027 (their R centre was named S) and
    # D-028 (methoxy was cited after the compound prefix).
    ("D-029a", "CN1CCC[C@@H]1Cc1c[nH]c2ccccc12",
     "3-{[(2R)-1-methylpyrrolidin-2-yl]methyl}-1H-indole",
     "3-{[(5S)-1-methylpyrrolidin-5-yl]methyl}-1H-indole", "MPMI: locant 5, and S for R"),
    ("D-029b", "CN1CCC[C@@H]1Cc1c[nH]c2cccc(O)c12",
     "3-{[(2R)-1-methylpyrrolidin-2-yl]methyl}-1H-indol-4-ol",
     "3-{[(5S)-1-methylpyrrolidin-5-yl]methyl}-1H-indol-4-ol", "4-HO-MPMI: locant 5, and S for R"),
    ("D-029c", "CN1CCC[C@@H]1Cc1c[nH]c2ccc(OC)cc12",
     "5-methoxy-3-{[(2R)-1-methylpyrrolidin-2-yl]methyl}-1H-indole",
     "3-{[(2S)-1-methylpyrrolidin-2-yl]methyl}-5-methoxy-1H-indole", "5-MeO-MPMI: S for R, order"),
    ("D-029d", "CN1CCCC1CO", "(1-methylpyrrolidin-2-yl)methanol",
     "(1-methylpyrrolidin-5-yl)methanol", "tie broken by atom order"),
    ("D-029e", "OC(=O)c1ccc(cc1)C1CCC(C)N1C", "4-(1,5-dimethylpyrrolidin-2-yl)benzoic acid",
     "4-(1,2-dimethylpyrrolidin-5-yl)benzoic acid", "prefix locants ranked above the free valence"),
    ("D-029f", "C[C@@H]1CCCN1C", "(2R)-1,2-dimethylpyrrolidine",
     "(2R)-1,2-dimethylpyrrolidine", "unchanged: a PARENT ring, no free valence"),
    # Across ring kinds. v and y were meant as non-regression rows and turned
    # out to be the same defect -- checked against the pre-fix engine rather
    # than assumed "unchanged". u is the one where the PARENT's numbering
    # changes (the chloro) while the substituent's must not.
    ("D-029u", "Clc1cc(ccc1C(=O)O)C1CCCN1C", "2-chloro-4-(1-methylpyrrolidin-2-yl)benzoic acid",
     "2-chloro-4-(1-methylpyrrolidin-2-yl)benzoic acid", "unchanged"),
    ("D-029v", "OC(=O)c1ccc(cc1)C1CC(C)CCN1", "4-(4-methylpiperidin-2-yl)benzoic acid",
     "4-(4-methylpiperidin-6-yl)benzoic acid", "piperidine: free valence 6, found while writing this table"),
    ("D-029w", "OC(=O)c1ccc(cc1)N1CCOCC1", "4-(morpholin-4-yl)benzoic acid",
     "4-(morpholin-4-yl)benzoic acid", "unchanged: O outranks the attached N"),
    ("D-029x", "OC(=O)c1ccc(cc1)C1CCCCC1C", "4-(2-methylcyclohexyl)benzoic acid",
     "4-(2-methylcyclohexyl)benzoic acid", "unchanged: carbocycle"),
    ("D-029y", "OC(=O)c1ccc(cc1)c1ccc(C)o1", "4-(5-methylfuran-2-yl)benzoic acid",
     "4-(2-methylfuran-5-yl)benzoic acid", "furan: free valence 5, found while writing this table"),
    ("D-029z", "OC(=O)c1ccc(cc1)c1ccncc1", "4-(pyridin-4-yl)benzoic acid",
     "4-(pyridin-4-yl)benzoic acid", "unchanged: aromatic N ring"),

    # --- D-030: a BRIDGED free valence numbered by plan order -------------
    # The third ring class to show the same rule, and the first to produce a
    # WRONG MOLECULE from it. D-029 fixed monocyclic heterocycles by
    # FILTERING the numberings; bridged rings kept a separate branch that
    # only SORTED them, so the lowest free-valence locant merely landed last
    # and won on "later-generated wins a tie". Any competing ring prefix
    # outscores that, and P-31.1.4.2.4 ranks the free valence AHEAD of
    # detachable prefixes.
    #
    # Bare adamantyl was always right, which is why nothing caught this: the
    # defect needs a second ring substituent to exist. Found by the held-out
    # corpus (cid 36000), not by the 187-row regression corpus, which scores
    # 187/187 both before and after the fix.
    #
    # In adamantane numbering locant 2 is adjacent to 1 and 3 but NOT to 5,
    # so "2-substituted...-5-yl" is not a non-preferred name for the input --
    # it denotes a constitutional isomer. Three of these four rows changed
    # InChIKey, which is what makes them severity A.
    ("D-030a", "CNC(C)CC12CC3CC(CC(C3)C1C1CCCCC1)C2",
     "1-(2-cyclohexyladamantan-1-yl)-N-methylpropan-2-amine",
     "1-(2-cyclohexyladamantan-5-yl)-N-methylpropan-2-amine",
     "HQMBUZVFGUDZCC emitted for RNYOSRZCHQLRMT; held-out cid 36000"),
    ("D-030b", "CNC(C)CC12CC3CC(CC(C3)C1C)C2",
     "N-methyl-1-(2-methyladamantan-1-yl)propan-2-amine",
     "N-methyl-1-(2-methyladamantan-5-yl)propan-2-amine",
     "WDPWWLGUBBHNPQ emitted for UXKZZZWEQVOJDT"),
    ("D-030c", "OCC12CC3CC(CC(C3)C1C)C2", "(2-methyladamantan-1-yl)methanol",
     "(2-methyladamantan-5-yl)methanol",
     "IFNZKCYIMQCMBL emitted for QIYMDQBSEMTZPK; a different parent context"),
    # Severity B, kept here because it is the SAME cause: the two
    # bicyclo[2.2.1]heptane bridgeheads are equivalent in this molecule, so
    # both names denote it (NYBSCAFHRVFOLB either way) and only
    # P-31.1.4.2.4 chooses. It is the control that says the fix is about the
    # rule and not about adamantane.
    # THE BRACES WERE PINNED AS EMITTED HERE, AND THE MECHANISM WORKED.
    # This row deliberately held the wrong enclosing mark with a note that
    # fixing the nesting rule would make it fail -- and it did, in the same
    # branch, which is how D-034 got found rather than forgotten. The
    # von Baeyer bracket is exempt from the nesting order (P-16.5.4.1.2), so
    # the prefix takes parentheses.
    ("D-030d", "CNC(C)CC12CCC(C)(CC1)C2",
     "N-methyl-1-(4-methylbicyclo[2.2.1]heptan-1-yl)propan-2-amine",
     "N-methyl-1-{1-methylbicyclo[2.2.1]heptan-4-yl}propan-2-amine",
     "same molecule, non-preferred locant: free valence after the prefix"),
    # Non-regression: bare bridged substituents, which were ALREADY correct
    # and are what the removed branch was written for. If the filter ever
    # drops the locant-1 numbering these go first.
    ("D-030e", "OCC12CC3CC(C1)CC(C3)C2", "(adamantan-1-yl)methanol",
     "(adamantan-1-yl)methanol", "unchanged: no competing prefix"),
    ("D-030f", "CNC(C)CC12CC3CC(C1)CC(C3)C2",
     "1-(adamantan-1-yl)-N-methylpropan-2-amine",
     "1-(adamantan-1-yl)-N-methylpropan-2-amine", "unchanged"),
    # Non-regression for the ELISION half. Correcting the locant to 1
    # exposed a second latent defect: the "-yl" suffix elided locant 1 on a
    # ring stem, which has no alkan->alk contraction to absorb it, giving
    # "adamantan-yl". A ring under method ALKYL ignores that flag entirely,
    # so these two prove the narrowed predicate did not reach them.
    ("D-030g", "OCC1CCCCC1", "cyclohexylmethanol", "cyclohexylmethanol",
     "unchanged: ALKYL method, contracted ring stem"),
    ("D-030h", "OCc1ccccc1", "phenylmethanol", "phenylmethanol",
     "unchanged: ALKYL method"),

    # --- D-031: a FUSED free valence, when locant 1 is not on offer --------
    # The last of the three ring classes, and the one my own plan predicted
    # wrongly. The prediction was that a ring numbered from the curated table
    # exposes a single canonical map, leaving nothing to choose between.
    # Measured: naphthalene offers FOUR numberings, putting the attachment at
    # 2, 3, 7 or 6 -- the correct one exists and is offered first.
    #
    # The branch filtered for "attachment at locant 1" and, finding none,
    # fell back to yielding EVERY numbering. Falling back to every numbering
    # is falling back to no rule: the prefix band then chose, and it prefers
    # the numbering that gives methoxy the lower locant, which P-31.1.4.2.4
    # puts after the free valence. Locant 1 is simply not reachable on a
    # fused ring, so the fallback now applies the same rule to what IS
    # reachable -- the lowest free-valence locant among the candidates.
    #
    # Severity B: both names denote naproxen, which is why the round-trip
    # benchmark scored the old one as a success for months.
    ("D-031a", "COc1ccc2cc([C@@H](C)C(=O)O)ccc2c1",
     "(2R)-2-(6-methoxynaphthalen-2-yl)propanoic acid",
     "(2R)-2-(2-methoxynaphthalen-6-yl)propanoic acid",
     "free valence took 6 so methoxy could take 2"),
    ("D-031b", "COc1ccc2cc([C@H](C)C(=O)O)ccc2c1",
     "(2S)-2-(6-methoxynaphthalen-2-yl)propanoic acid",
     "(2S)-2-(2-methoxynaphthalen-6-yl)propanoic acid",
     "the other enantiomer, same locant defect"),
    ("D-031c", "COc1ccc2cc(ccc2c1)C(C)C(=O)OC",
     "methyl 2-(6-methoxynaphthalen-2-yl)propanoate",
     "methyl 2-(2-methoxynaphthalen-6-yl)propanoate",
     "the PARENT changes (acid -> ester) and the substituent must not"),
    # Generalisation across ring systems, each verified on both gates. The
    # locant differs per skeleton -- 2 for naphthalene and anthracene, 3 for
    # phenanthrene -- which is the point: the rule is "lowest reachable", not
    # a constant.
    ("D-031d", "OC(=O)c1ccc(cc1)c1cc2ccccc2c(C)c1",
     "4-(4-methylnaphthalen-2-yl)benzoic acid",
     "4-(4-methylnaphthalen-2-yl)benzoic acid",
     "naphthalene with a distal methyl"),
    ("D-031e", "OC(=O)c1ccc(cc1)c1ccc2cc3ccccc3cc2c1",
     "4-(anthracen-2-yl)benzoic acid", "4-(anthracen-2-yl)benzoic acid",
     "anthracene: unchanged, no competing prefix"),
    ("D-031f", "OC(=O)c1ccc(cc1)c1ccc2ccc3ccccc3c2c1",
     "4-(phenanthren-3-yl)benzoic acid", "4-(phenanthren-3-yl)benzoic acid",
     "phenanthrene: lowest reachable is 3, not 2"),
    ("D-031g", "OC(=O)c1ccc(cc1)c1ccc2ccccc2n1",
     "4-(quinolin-2-yl)benzoic acid", "4-(quinolin-2-yl)benzoic acid",
     "fused heterocycle: N holds locant 1, so 2 is lowest reachable"),
    # Non-regression for the branch that still WANTS locant 1 and can get it.
    # If the fallback ever swallows the locant-1 case these go first.
    ("D-031h", "OC(=O)c1ccc(cc1)c1ccccc1C",
     "4-(2-methylphenyl)benzoic acid", "4-(2-methylphenyl)benzoic acid",
     "unchanged: monocyclic, attachment reachable at 1"),
    ("D-031i", "OC(=O)c1ccc(cc1)c1ccccc1", "4-phenylbenzoic acid",
     "4-phenylbenzoic acid", "unchanged: unsubstituted phenyl, no locant"),
    ("D-031j", "OC(=O)C(C)c1ccc2ccccc2c1",
     "2-(naphthalen-2-yl)propanoic acid",
     "2-(naphthalen-2-yl)propanoic acid",
     "unchanged: naphthalene with no competing prefix was already right"),

    # --- D-032: the senior parent was never PROPOSED ----------------------
    # Not a ranking defect. The seniority logic was correct all along and
    # scored the silicon parent at 5000 against benzene's 561 -- but the
    # plan search had already spent its whole 20-plan budget on benzene's
    # NUMBERING variants, so no silicon plan existed to rank. Measured: 20
    # of 20 top-level plans were benzene numberings or methyls, and 67 of
    # 189 corpus molecules were hitting that cap.
    #
    # The budget is two budgets now (see `_PlanBudget`): a work bound, and a
    # per-hypothesis bound so one parent cannot consume what another needs.
    # The winner trace moves from `monocyclic/len=6` to
    # `heteroatom_center/elem=Si`, which is the shape of the evidence: a
    # candidate appeared, and P-44.1.2 preferred it unchanged.
    ("D-032a", "C[Si](C)(C)c1ccccc1", "trimethyl(phenyl)silane",
     "(trimethylsilan-yl)benzene", "Si parent starved out by benzene numberings"),
    ("D-032b", "c1ccccc1P(c1ccccc1)c1ccccc1", "triphenylphosphane",
     "(diphenylphosphan-yl)benzene", "same, phosphorus"),
    ("D-032c", "c1ccc(cc1)[I+]c1ccccc1", "diphenyliodanium",
     "(phenyliodaniumyl)benzene", "same, iodine cation"),
    ("D-032d", "O=P(c1ccccc1)(c1ccccc1)c1ccccc1", "oxotri(phenyl)phosphane",
     "[oxodi(phenyl)phosphan-yl]benzene",
     "right parent now; the tri(phenyl) enclosing marks are a separate defect"),
    # Generalisation past the corpus rows, both verified on canonical SMILES
    # and full InChIKey.
    ("D-032e", "CC[Si](CC)(CC)c1ccccc1", "triethyl(phenyl)silane",
     "(triethylsilan-yl)benzene", "not specific to methyl"),
    ("D-032f", "c1ccccc1[As](c1ccccc1)c1ccccc1", "triphenylarsane",
     "triphenylarsane", "unchanged: arsenic was already reached"),

    # --- D-033: a mononuclear parent must NOT cite locant 1 ---------------
    # The counterpart to D-030, from the same paragraph. P-29.2 method (2):
    # the free-valence locants "are as low as is consistent with any
    # established numbering of the parent hydride and, EXCEPT FOR MONONUCLEAR
    # PARENT HYDRIDES or the suffix 'ylidyne', the locant '1' must be cited"
    # (BlueBookV2.pdf p. 301).
    #
    # So the same rule requires `adamantan-1-yl` to carry its locant (D-030)
    # and forbids `azanium-1-yl` from carrying one. Both were wrong, in
    # opposite directions, and the D-030 fix made the second visible.
    #
    # A mononuclear parent also has nothing to contract -- the engine stores
    # `alkyl_stem == stem` for these, measured as 'silan' and 'azanium' -- so
    # the chain test the contraction used could never match.
    ("D-033a", "C[N+](C)(C)CC(=O)[O-]", "2-(trimethylazaniumyl)acetate",
     "2-(trimethylazanium-1-yl)acetate",
     "mononuclear N cited a locant the rule forbids; = PubChem now"),
    # Method (1) is restricted BY NAME to four elements: "recommended
    # primarily for saturated acyclic and monocyclic hydrocarbon substituent
    # groups and for the mononuclear hydrides of silicon, germanium, tin,
    # and lead". It replaces the "ane" ending, so silane gives `silyl` --
    # the universal TMS prefix -- where the engine had `silan-1-yl`.
    ("D-033b", "NC[Si](C)(C)C", "(trimethylsilyl)methanamine",
     "(trimethylsilan-1-yl)methanamine", "method (1) contraction for Si"),
    ("D-033c", "OCC[Si](C)(C)C", "2-(trimethylsilyl)ethanol",
     "2-(trimethylsilan-1-yl)ethanol", "same, on a longer chain"),
    ("D-033d", "OC(=O)C[Si](C)(C)C", "(trimethylsilyl)acetic acid",
     "(trimethylsilan-1-yl)acetic acid", "same, retained-name parent"),
    ("D-033e", "Nc1ccc(cc1)[Si](C)(C)C", "4-(trimethylsilyl)benzen-1-amine",
     "4-(trimethylsilan-1-yl)benzen-1-amine", "same, on a ring parent"),
    # Phosphorus is deliberately absent from method (1)'s element list, so
    # `phosphanyl` keeps its "an": the mononuclear exception drops the
    # LOCANT, not the ending. This row is what stops the contraction being
    # applied to every mononuclear heteroatom.
    ("D-033f", "CNC(=O)CSP(=O)(OC)OC",
     "2-{[di(methoxy)(oxo)phosphanyl]sulfanyl}-N-methylacetamide",
     "2-{[di(methoxy)(oxo)phosphanyl]sulfanyl}-N-methylacetamide",
     "unchanged: P takes method (2), so phosphanyl not phosphyl"),
    # Non-regression for the other side of the same rule: a POLYCYCLIC parent
    # must keep its locant. If the mononuclear exception ever widens, these
    # go first.
    ("D-033g", "OCC12CC3CC(C1)CC(C3)C2", "(adamantan-1-yl)methanol",
     "(adamantan-1-yl)methanol", "unchanged: not mononuclear, locant required"),
    ("D-033h", "OCC1CCCCC1", "cyclohexylmethanol", "cyclohexylmethanol",
     "unchanged: monocyclic hydrocarbon, method (1)"),
    ("D-033i", "CO", "methanol", "methanol", "unchanged: mononuclear carbon parent"),

    # --- D-035: the isotope hyphen depends on what FOLLOWS ----------------
    # P-82.2.1 (BlueBookV2.pdf p. 852): "Immediately after the parentheses
    # there is neither space nor hyphen, except that when the name, or a part
    # of a name, includes a preceding locant, a hyphen is inserted." The
    # book's own PIN for the plain case is `1,2-di[(13C)methyl]benzene`.
    #
    # The engine keyed the hyphen off whether the ISOTOPE LABEL carried a
    # locant, which is a different question, so a locanted label always got
    # one even when the parent name had no preceding locant.
    ("D-035a", "[2H]CO", "(1-2H)methanol", "(1-2H)-methanol",
     "no preceding locant on `methanol`, so no hyphen"),
    ("D-035b", "[13CH4]", "(1-13C)methane", "(1-13C)-methane", "same, carbon-13"),
    ("D-035c", "CC([2H])O", "(1-2H)ethanol", "(1-2H)-ethanol",
     "same, and the parent locant is internal rather than preceding"),
    # THE EXCEPTION, which is why this is not simply "delete the hyphen": an
    # indicated-hydrogen marker IS a preceding locant, so the hyphen stays.
    ("D-035d", "[13cH]1cc2ccccc2[nH]1", "(2-13C)-1H-indole", "(2-13C)-1H-indole",
     "unchanged: `1H-` is a preceding locant, so the hyphen is required"),
    # Non-regression for labels with no locant at all, which never had one.
    ("D-035e", "[2H]O[2H]", "(2H2)water", "(2H2)water", "unchanged"),
    ("D-035f", "[15NH3]", "(15N)ammonia", "(15N)ammonia", "unchanged"),

    # --- D-036: a retained name is not automatically a preferred name -----
    # `retained_pins` asserted PIN status for 292 names while citing a rule
    # for 31, because 161 of them were harvested from OPSIN's name-to-
    # structure dictionary -- where presence means a name can be READ, not
    # that IUPAC prefers it. Entries now carry `pin_status` with the evidence
    # beside it; see benchmarks/naming/adjudication.toml for the quotations.
    #
    # Only entries a benchmark name DEPENDS ON were audited: 22 of 292,
    # established by instrumenting which names a retained plan wins. The
    # other 274 stay UNKNOWN and keep working exactly as before, because
    # the answer to "asserted without evidence" is not "denied without
    # evidence". tools/retained_name_audit.py reports that backlog.
    ("D-036a", "CCCC=O", "butanal", "butyraldehyde",
     "P-66.6.1; the book writes `3-oxobutanal (PIN) (not 3-oxobutyraldehyde)`"),
    ("D-036b", "ClC(Cl)Cl", "trichloromethane", "chloroform",
     "P-61.3.4 verbatim: chloroform is `acceptable in general nomenclature`"),
    ("D-036c", "CC(C)C", "2-methylpropane", "isobutane",
     "P-61.2.1 verbatim: isobutane is `no longer recommended`"),
    ("D-036d", "CCN(CC)CC", "N,N-diethylethanamine", "triethylamine",
     "not retained anywhere; amines are substitutive (P-66.4.1)"),
    ("D-036e", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine oxide",
     "trimethylamine oxide",
     "the book gives all three forms and labels trimethylamine traditional"),
    ("D-036f", "CC1(C)C2CCC1(C)C(=O)C2",
     "1,7,7-trimethylbicyclo[2.2.1]heptan-2-one", "camphor",
     "not retained as a ketone PIN"),
    ("D-036g", "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
     "2-[4-(2-methylpropyl)phenyl]propanoic acid", "ibuprofen",
     "an INN, absent from the book; harvested from OPSIN"),
    # RETAINED NAMES THAT ARE GENUINELY PREFERRED. These are the reason the
    # audit could not be a sweep: `toluene` is a PIN in as many words
    # (P-22.1.3), and demoting every retained name would have broken it.
    ("D-036h", "Cc1ccccc1", "toluene", "toluene",
     "unchanged: P-22.1.3 says toluene is a PIN"),
    ("D-036i", "Oc1ccccc1", "phenol", "phenol", "unchanged: retained PIN"),
    ("D-036j", "CC(=O)O", "acetic acid", "acetic acid", "unchanged: retained PIN"),
    ("D-036k", "NC(N)=O", "urea", "urea", "unchanged: retained PIN"),
    ("D-036l", "Nc1ccccc1", "aniline", "aniline", "unchanged: retained PIN"),
    ("D-036m", "O=Cc1ccccc1", "benzaldehyde", "benzaldehyde",
     "unchanged: retained PIN"),
    ("D-036n", "CC#N", "acetonitrile", "acetonitrile", "unchanged: retained PIN"),
    # Dropping caffeine's retained name exposed a DIFFERENT defect, pinned
    # as emitted: the ring ketones come out as `oxo` prefixes where the
    # principal characteristic group should take the `-dione` suffix. That is
    # PCG assignment, the same layer as warfarin. When it is fixed this row
    # FAILS, which is the intended way to find it.
    ("D-036o", "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
     "1,3,7-trimethyl-2,6-dioxo-1H-purine", "caffeine",
     "systematic now, but oxo-prefix instead of the dione suffix"),

    # --- D-037: two curated ring names that were not the preferred ones ---
    # Both verbatim, and both single-entry data changes:
    #   p. 150 (Table 2.2) and p. 449:  "1,2-oxazole (PIN)  isoxazole"
    #   p. 208:                         "1-benzofuran (PIN)  benzofuran"
    # p. 211 adds that isoxazole, isothiazole, thiazole and oxazole,
    # "although permitted in general nomenclature, are not retained" as
    # fusion parent components, and p. 376 uses
    # `(1-benzofuran-2-yl)phosphane (PIN)`.
    #
    # Both were inconsistent with their own neighbours rather than with a
    # rule nobody had applied: the plain-oxazole entry already said
    # `1,3-oxazole`, and `1-benzothiophene` and `1,3-benzothiazole` sit
    # either side of benzofuran in the same table carrying their locants.
    ("D-037a", "c1cnoc1", "1,2-oxazole", "isoxazole", "Table 2.2 / P-52.2.3"),
    # The sulfur twin, from the same table line. Fixing only the oxygen one
    # would leave the same inconsistency it was fixing.
    ("D-037g", "c1cnsc1", "1,2-thiazole", "isothiazole",
     "Table 2.2: `isothiazole  1,2-thiazole (PIN)`"),
    ("D-037b", "c1ccc2occc2c1", "1-benzofuran", "benzofuran",
     "p. 208; the `1-` is what distinguishes it from 2-benzofuran"),
    ("D-037c", "Cc1cc(NS(=O)(=O)c2ccc(N)cc2)no1",
     "4-amino-N-(5-methyl-1,2-oxazol-3-yl)benzene-1-sulfonamide",
     "4-amino-N-(5-methylisoxazol-3-yl)benzene-1-sulfonamide",
     "sulfamethoxazole, through the substituent form"),
    # The other half of p. 208, which came along for free.
    ("D-037d", "c1ccc2cocc2c1", "2-benzofuran", "isobenzofuran",
     "p. 208: `2-benzofuran (PIN)  isobenzofuran  benzo[c]furan`"),
    # Non-regression: the entries that were already right.
    ("D-037e", "c1cocn1", "1,3-oxazole", "1,3-oxazole", "unchanged"),
    ("D-037f", "c1ccc2sccc2c1", "1-benzothiophene", "1-benzothiophene",
     "unchanged: already carried its locant"),
]

# Measured, reproduced, not yet fixed. Every one of these currently names
# the WRONG MOLECULE. The common shape is a charged carbon next to
# unsaturation or aromaticity, which no classifier claims, so the charge
# is dropped and the neutral skeleton is named.
# Empty, and that is the point of keeping it: a defect found later is added
# here as xfail(strict=True) so that fixing it FAILS the suite and forces
# this table and KNOWN_LIMITATIONS.md to be updated together.
#
# NB "benzylium" would be the obvious target for a benzyl cation and is
# WRONG: OPSIN reads it as O=[C+]c1ccccc1, the BENZOYL cation. Every target
# added here must be checked by parsing it back
# (tests/vendor/iupac_namer/test_known_defects.py), precisely to catch that
# class of mistake before it becomes someone's goal.
OPEN: list[tuple[str, str, str, str, str]] = []

# Observed but NOT tracked here, because this table requires a verified
# target name and these have none:
#
#   [C-]1C=CC=C1  ->  "cyclopenta-2,4-dien-1-ide"
#       The cyclopentadienyl RADICAL anion (no H, one unpaired electron),
#       which is a different species from cyclopentadienide -- different
#       InChIKey -- and the radical is dropped. "cyclopentadienide" was
#       tried as the target and rejected by the OPSIN check in
#       tests/vendor/iupac_namer/test_known_defects.py: it denotes the
#       closed-shell anion. No name for the radical anion was found that
#       OPSIN parses back to it, so stating one would be guessing.


@pytest.mark.parametrize(
    "defect,smiles,expected,former,note",
    FIXED,
    ids=[row[0] for row in FIXED],
)
def test_fixed_defect_stays_fixed(defect, smiles, expected, former, note):
    got = name_smiles(smiles)
    assert got == expected, (
        f"{defect} regressed ({note}).\n"
        f"  input:    {smiles}\n"
        f"  expected: {expected}\n"
        f"  got:      {got}\n"
        f"  (the original defect emitted {former!r})"
    )


@pytest.mark.parametrize(
    "defect,smiles,expected,former,note",
    OPEN,
    ids=[row[0] for row in OPEN],
)
@pytest.mark.xfail(strict=True, reason="known open defect, measured not guessed")
def test_open_defect_still_open(defect, smiles, expected, former, note):
    """Fails when the defect is fixed -- that is the point.

    A strict xfail turning green means the engine improved and this file
    is now lying about it. Move the row from OPEN to FIXED.
    """
    assert name_smiles(smiles) == expected
