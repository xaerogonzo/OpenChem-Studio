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
    ("D-026v", "Cn1cnc2c1c(=O)n(C)c(=O)n2C", "caffeine", "caffeine",
     "unchanged"),
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
    ("D-024z", "C[N+](C)(C)[O-]", "trimethylamine oxide",
     "trimethylamine oxide", "unchanged"),
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
    ("D-022z", "O=S1(=O)CC=CC1CCN", "2-(sulfol-3-en-5-yl)ethanamine",
     "2-(sulfol-3-en-5-yl)ethanamine", "unchanged"),
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
