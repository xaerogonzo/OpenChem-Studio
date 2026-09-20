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
    # Expected moved in round 4: P-14.3.4 (a), naming round 4 (D-039).
    ("D-005e", "[CH2-]C1CCCCC1", "cyclohexylmethanide",
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
    # Expected moved in round 4: P-14.3.4 (a), naming round 4 (D-039).
    ("D-011", "[CH2-]c1ccccc1", "phenylmethanide",
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
    # Expected moved in round 4: P-14.3.4 (a), naming round 4 (D-039).
    ("D-018b", "[CH2-]c1ccncc1", "(pyridin-4-yl)methanide",
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
    # Expected moved in round 4: the anion keeps its parent's indicated H, as the book's '1H-inden-1-ido' (p. 787); naming round 4 (D-040).
    ("D-015e", "[n-]1ccc2ccccc21", "1H-indol-1-ide",
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
    # Expected moved in round 4: P-14.3.4 (a), as the unsubstituted methanidyldiazonium; OPSIN round-trips it.
    ("D-019d", "[CH-](c1ccccc1)[N+]#N", "phenylmethanidyldiazonium",
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
    # Expected moved in round 4: the ring C=O takes the suffix, and P-58.2
    # places the hydrogens -- one indicated H, at N1 (P-58.2.3.1.3), the
    # rest hydro (D-045).
    ("D-026v", "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
     "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione", "caffeine",
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
    # Expected moved in round 4 (A9): "oxido" is a simple prefix and takes no
    # enclosing marks of its own (P-16.5.1); both forms round-trip.
    ("D-024", "[CH2+]c1cc[n+]([O-])cc1",
     "(1-oxidopyridin-1-ium-4-yl)methan-1-ylium",
     "(pyridin-4-yl)methan-1-ylium 1-oxide", "unparsable; oxide wrapped a cation"),
    # Expected moved in round 4: P-14.3.4 (a), naming round 4 (D-039).
    ("D-024b", "[CH2-]c1cc[n+]([O-])cc1",
     "(1-oxidopyridin-1-ium-4-yl)methanide",
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
    # Expected moved in round 4 (A10): the N locant is cited (D-065h).
    ("D-024z", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine N-oxide",
     "trimethylamine oxide", "additive path unchanged; the PARENT is now the PIN"),
    # Expected moved in round 4 (A10): the substitutive PIN (D-065a).
    ("D-024w", "CS(C)=O", "(methanesulfinyl)methane", "dimethyl sulfoxide",
     "the class name is the book's second form, p. 912"),

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
    # Expected moved in round 4: P-14.3.4 (b), naming round 4 (D-039).
    ("D-013z", "CC[N+]#N", "ethanediazonium", "ethane-1-diazonium",
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
    # Expected moved in round 4: P-58.2.3.1.1 (pdf p. 481) -- as many
    # indicated H as groups, so it sits on the group carbon, and the hydro
    # locants "are those of the saturated positions" (D-045).
    ("D-023c", "CC1=NN(c2ccccc2)C(=O)C1",
     "3-methyl-1-phenyl-1,4-dihydro-5H-pyrazol-5-one",
     "3-methyl-1-phenyl-4,5-dihydro-1H-1,2-diazol-5-one",
     "edaravone core; stem propagates through the whole pyrazolone family"),
    # Moved in round 5 (N4): 1-phenylpyrazoline is no longer named on the
    # benzene -- P-44.2.1 (a), a heterocycle is senior to a carbocycle, now
    # holds through the P-44.1.2 senior-atom tier -- so the substituent form
    # this row guards is taken from an acid, which keeps benzene the parent.
    ("D-023d", "OC(=O)c1ccc(N2CCC=N2)cc1", "4-(4,5-dihydro-1H-pyrazol-1-yl)benzoic acid",
     "4-(4,5-dihydro-1H-1,2-diazol-1-yl)benzoic acid", "substituent form too"),
    ("D-023e", "C1C=NN(c2ccccc2)C1", "1-phenyl-4,5-dihydro-1H-pyrazole",
     "(4,5-dihydro-1H-pyrazol-1-yl)benzene",
     "P-44.2.1 (a): the heterocycle is the parent (round 5, N4)"),

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
    # Expected moved in round 4: a two-atom chain with a prefix keeps locant 1 (D-042).
    ("D-022z", "O=S1(=O)CC=CC1CCN", "2-(sulfol-3-en-2-yl)ethan-1-amine",
     "2-(sulfol-3-en-5-yl)ethanamine", "free valence took the higher locant"),
    # Expected moved in round 4: urazol is not in the book; the saturated
    # Hantzsch-Widman name is the PIN, as imidazolidine-2,4-dione (p. 566).
    ("D-022w", "O=c1[nH][nH]c(=O)[nH]1", "1,2,4-triazolidine-3,5-dione", "urazol",
     "a retained name the book does not have"),
    # 4-pyrazolone changed as a consequence of the D-023 curated entries,
    # and the change is kept rather than worked around. Adding a curated
    # ring entry for the 2,3-dihydro-1H-pyrazole skeleton gives it priority
    # over the pre-composed "4-pyrazolone" stem, so this ring now takes the
    # systematic form -- which is exactly the treatment 5-pyrazolone was
    # given for being semi-systematic rather than a PIN. Both pyrazolone
    # stems now behave the same way. Verified to round-trip on both gates.
    # Expected moved in round 4: as D-023c (D-045).
    ("D-022v", "O=C1C=NNC1", "1,5-dihydro-4H-pyrazol-4-one",
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
    # Expected moved in round 4 (A9): the amido prefix, P-66.1.1.4.3 method (1)
    # (pdf p. 652); both descriptors unchanged, which is what this row guards.
    ("D-027z", "N[C@@H](C)C(=O)N[C@@H](Cc1ccccc1)C(=O)O",
     "(2S)-2-[(2S)-2-aminopropanamido]-3-phenylpropanoic acid",
     "(2S)-2-[(2S)-2-aminopropanoylamino]-3-phenylpropanoic acid", "descriptors unchanged"),

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
    # Round 4 (A6): the book names P=O substitutively as a heterone, "triphenyl-
    # λ5-phosphanone (PIN) ... (not oxotriphenyl-λ5-phosphane)" (p. 769),
    # so the parent this row fixed stays and the -one suffix replaces "oxo".
    ("D-032d", "O=P(c1ccccc1)(c1ccccc1)c1ccccc1", "triphenyl-lambda5-phosphanone",
     "[oxodi(phenyl)phosphan-yl]benzene",
     "right parent now, and the heterone the book prefers (round 4, A6)"),
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
    # Expected moved in round 4: an acetate takes no C2 locant, as the book's
    # "(N,N-dimethylmethanaminiumyl)acetate (PIN)" (pdf p. 837).
    ("D-033a", "C[N+](C)(C)CC(=O)[O-]", "(trimethylazaniumyl)acetate",
     "2-(trimethylazanium-1-yl)acetate",
     "mononuclear N cited a locant the rule forbids; = PubChem now"),
    # Method (1) is restricted BY NAME to four elements: "recommended
    # primarily for saturated acyclic and monocyclic hydrocarbon substituent
    # groups and for the mononuclear hydrides of silicon, germanium, tin,
    # and lead". It replaces the "ane" ending, so silane gives `silyl` --
    # the universal TMS prefix -- where the engine had `silan-1-yl`.
    ("D-033b", "NC[Si](C)(C)C", "(trimethylsilyl)methanamine",
     "(trimethylsilan-1-yl)methanamine", "method (1) contraction for Si"),
    # Expected moved in round 4: as D-042.
    ("D-033c", "OCC[Si](C)(C)C", "2-(trimethylsilyl)ethan-1-ol",
     "2-(trimethylsilan-1-yl)ethanol", "same, on a longer chain"),
    ("D-033d", "OC(=O)C[Si](C)(C)C", "(trimethylsilyl)acetic acid",
     "(trimethylsilan-1-yl)acetic acid", "same, retained-name parent"),
    # Expected moved in round 4: aniline takes full substitution (D-043).
    ("D-033e", "Nc1ccc(cc1)[Si](C)(C)C", "4-(trimethylsilyl)aniline",
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
    ("D-036e", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine N-oxide",
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
    # Expected moved in round 4, the way this row asked to be found: the
    # dione suffix, with P-58.2's hydrogens (D-045).
    ("D-036o", "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
     "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione", "caffeine",
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
    # --- D-038: the alphanumerical criterion keyed every carbon prefix "z" ---
    # P-14.4 (g): "lowest locants for the substituent cited first as a prefix
    # in the name"; P-14.5.1 prints 1-ethyl-4-methylcyclohexane (PIN). The
    # tie-break was a x0.0001 term of the ranking float, keyed on the FG type,
    # and every carbon substituent fell back to "z" -- so ethyl, methyl and
    # methoxy tied and plan order decided. Fixed by applying P-14.4 (g) on the
    # EXECUTED names of plans that tie on every other tier (stage 5b).
    ("D-038a", "CCc1ccc(C)cc1", "1-ethyl-4-methylbenzene", "4-ethyl-1-methylbenzene",
     "P-14.4 (g) on an arene"),
    ("D-038b", "CC1CCCC(CC)C1", "1-ethyl-3-methylcyclohexane", "3-ethyl-1-methylcyclohexane",
     "the same on a saturated ring; P-14.5.1's own example is its 1,4 isomer"),
    ("D-038c", "CCC1CCC(C)CC1", "1-ethyl-4-methylcyclohexane", "4-ethyl-1-methylcyclohexane",
     "P-14.5.1's own printed example, which the engine had wrong"),
    ("D-038d", "COc1ccc(C)cc1", "1-methoxy-4-methylbenzene", "4-methoxy-1-methylbenzene",
     "anisole takes no substitution in a PIN, so this is numbering only"),
    ("D-038e", "CC(C)c1ccc(CC)cc1", "1-ethyl-4-(propan-2-yl)benzene",
     "1-ethyl-4-(propan-2-yl)benzene",
     "non-regression: a compound prefix against a simple one, right before and after"),
    # Non-regression: halogens were keyed by their FG type and were already
    # right; the chain case never went through the ring tie-break.
    ("D-038f", "Clc1ccc(Br)cc1", "1-bromo-4-chlorobenzene", "1-bromo-4-chlorobenzene",
     "unchanged"),
    ("D-038g", "CCC(C)CC(CC)CC", "3-ethyl-5-methylheptane", "3-ethyl-5-methylheptane",
     "unchanged; P-15.1.7.1.5's own example"),
    ("D-038h", "Fc1cc(Cl)cc(Br)c1", "1-bromo-3-chloro-5-fluorobenzene",
     "1-bromo-3-chloro-5-fluorobenzene", "unchanged: three prefixes, symmetric set"),
    # --- D-039: locant 1 cited where P-14.3.4 omits it -----------------------
    # "'1' is omitted: (a) in substituted mononuclear parent hydrides; ...
    # (b) in monosubstituted homogeneous chains consisting of only two
    # identical atoms; ... (c) in monosubstituted homogeneous monocyclic
    # rings". The charged-species renderers never applied it: the diazonium
    # one hard-coded locant 1, the -ide one kept the uncontracted form.
    ("D-039a", "N#[N+]c1ccccc1", "benzenediazonium", "benzene-1-diazonium", "(c)"),
    ("D-039b", "C[N+]#N", "methanediazonium", "methane-1-diazonium",
     "(a); the book's own example, 'methanediazonium (PIN)'"),
    ("D-039c", "CC[N+]#N", "ethanediazonium", "ethane-1-diazonium", "(b)"),
    ("D-039d", "N#[N+]C1CCCCC1", "cyclohexanediazonium", "cyclohexane-1-diazonium", "(c)"),
    ("D-039e", "[CH2-]c1ccccc1", "phenylmethanide", "phenylmethan-1-ide",
     "(a); 'methanide (PIN)'"),
    ("D-039f", "[CH-](c1ccccc1)c1ccccc1", "diphenylmethanide", "diphenylmethan-1-ide",
     "(a); the book prints diphenylmethanediide for the dianion"),
    # Converses: where the locant is required, it stays.
    ("D-039g", "CCC[N+]#N", "propane-1-diazonium", "propane-1-diazonium",
     "converse: a three-atom chain keeps its locant"),
    ("D-039h", "[CH2-]CC", "propan-1-ide", "propan-1-ide", "converse"),
    # NOT adjudicated: the cation. Pinned as emitted so any change to it is a
    # decision, not a side effect of the anion fix (which is scoped to -ide).
    ("D-039i", "[CH2+]c1ccccc1", "phenylmethan-1-ylium", "phenylmethan-1-ylium",
     "unadjudicated; pinned deliberately"),
    # --- D-040: an N-H on a symmetry axis, and an indicated H dropped ------
    # One family, one fix each, measured on the whole matrix. An [nH] in the
    # curated ring's query pins the TAUTOMER, not the orientation, and the
    # match was uniquified -- which collapses mirror orientations over the
    # same atom set, so 9H-carbazole kept one numbering and read 1 as 8.
    # N-methylcarbazole had no [nH] in its query and was always right. The
    # substituent branch dropped the ring's "1H-" (indol-2-yl), where the
    # tautomer branch beside it already carried it.
    ("D-040a", "Oc1cccc2c1[nH]c1ccccc12", "9H-carbazol-1-ol", "9H-carbazol-8-ol", ""),
    ("D-040b", "Oc1ccc2c(c1)[nH]c1ccccc12", "9H-carbazol-2-ol", "9H-carbazol-7-ol", ""),
    ("D-040c", "Oc1ccc2[nH]c3ccccc3c2c1", "9H-carbazol-3-ol", "9H-carbazol-6-ol", ""),
    ("D-040d", "Oc1cccc2[nH]c3ccccc3c12", "9H-carbazol-4-ol", "9H-carbazol-5-ol", ""),
    ("D-040e", "CC(C)=CCCC(C)=CCc1c(O)c(C)cc2c1[nH]c1ccccc12",
     "1-(3,7-dimethylocta-2,6-dien-1-yl)-3-methyl-9H-carbazol-2-ol",
     "8-(3,7-dimethylocta-2,6-dien-1-yl)-6-methyl-9H-carbazol-7-ol",
     "held-out cid4000; now its adjudicated target exactly"),
    ("D-040f", "OC(=O)c1ccc(cc1)c1cc2ccccc2[nH]1", "4-(1H-indol-2-yl)benzoic acid",
     "4-(indol-2-yl)benzoic acid", "naming round 2's open item"),
    ("D-040g", "OC(=O)c1ccc(cc1)-c1n[nH]c2ccccc12", "4-(1H-indazol-3-yl)benzoic acid",
     "4-(indazol-3-yl)benzoic acid", "generalisation, found by the matrix"),
    # Non-regression: N-substituted forms, a substituent on the other ring,
    # and the tautomer-sensitive rings that the un-uniquify must not un-pin.
    ("D-040h", "Oc1cccc2c1n(C)c1ccccc12", "9-methyl-9H-carbazol-1-ol",
     "9-methyl-9H-carbazol-1-ol", "unchanged"),
    ("D-040i", "OC(=O)c1ccc(cc1)c1cc2ccccc2n1C", "4-(1-methyl-1H-indol-2-yl)benzoic acid",
     "4-(1-methyl-1H-indol-2-yl)benzoic acid", "unchanged"),
    ("D-040j", "OC(=O)c1ccc(cc1)-c1ccc2[nH]c3ccccc3c2c1", "4-(9H-carbazol-3-yl)benzoic acid",
     "4-(9H-carbazol-3-yl)benzoic acid", "unchanged"),
    ("D-040k", "Clc1ccc2[nH]cnc2c1", "5-chloro-1H-benzimidazole",
     "5-chloro-1H-benzimidazole", "unchanged: the tautomer stays pinned"),
    ("D-040l", "Clc1ccc2nc[nH]c2c1", "6-chloro-1H-benzimidazole",
     "6-chloro-1H-benzimidazole", "unchanged: and its other tautomer stays distinct"),
    ("D-040m", "OC(=O)c1ccc(cc1)-c1c[nH]cn1", "4-(1H-imidazol-4-yl)benzoic acid",
     "4-(1H-imidazol-4-yl)benzoic acid", "unchanged"),
    # --- D-041: fusion names versus von Baeyer, by P-52.2.4.1 ---------------
    # "Fusion nomenclature gives preferred IUPAC names only to compounds
    # having at least two rings of at least five or more members ... When
    # fusion names are not allowed, unsaturated von Baeyer ring system names
    # are preferred". The naming-method ranks were a x0.01 nudge in the
    # ranking float; read as a lexicographic tier they put von Baeyer (1.2)
    # ahead of fused `systematic` (0.9) and unlisted `benzo_fused_bridged`
    # (0.5). Found by the vendored suite, not the benchmark.
    ("D-041a", "c1ccc2cc3c(cc2c1)SCS3", "2H-naphtho[2,3-d][1,3]dithiole",
     "4,6-dithiatricyclo[7.4.0.0^{3,7}]trideca-1(13),2,7,9,11-pentaene",
     "fusion allowed, so the fusion name. The target was '[1,3]dithiolo[4,5-b]"
     "naphthalene' until round 5 (N3), copied from an older engine output: "
     "P-25.3.2.4 (a) makes the heterocycle the parent, as in the book's own "
     "'2H-furo[2,3-d][1,3]dioxole (PIN)' (p. 218)"),
    ("D-041b", "OC1=CC=C2C(=C1)C1CCCCCC2C1",
     "5,6,7,8,9,10,11-heptahydro-5,11-methanobenzocyclononen-2-ol",
     "tricyclo[6.5.1.0^{2,7}]tetradeca-2,4,6-trien-4-ol",
     "a bridged fused name is a fusion name (P-25.4)"),
    ("D-041c", "C1=CC=C2CC2=C1", "bicyclo[4.1.0]hepta-1,3,5-triene",
     "bicyclo[4.1.0]hepta-1,3,5-triene",
     "the converse, and the book's own PIN: a three-membered partner forbids fusion"),
    ("D-041d", "CC12CCC3C(CCC4CCCCC34C)C1CCC2(C)O",
     "10,13,17-trimethylhexadecahydro-1H-cyclopenta[a]phenanthren-17-ol",
     "1,5,6-trimethyltetracyclo[11.4.0.0^{2,10}.0^{5,9}]heptadecan-6-ol",
     "the steroid class (cid19000's shape); the exact hydro form is stage A7's"),
    # --- D-042: locant 1 omitted on a two-atom chain that has a prefix ------
    # P-14.3.4 (b) omits it only for a MONOSUBSTITUTED two-atom chain, and
    # p. 70 says it outright: "the omission of the locant '1' in
    # 2-chloroethanol, while permissible in general usage, is not allowed in
    # preferred IUPAC names, thus the name 2-chloroethan-1-ol is the PIN".
    ("D-042a", "ClCCO", "2-chloroethan-1-ol", "2-chloroethanol", "p. 70, verbatim"),
    ("D-042b", "NCCO", "2-aminoethan-1-ol", "2-aminoethanol",
     "p. 553: '2-aminoethan-1-ol (PIN) (not ethanolamine)'"),
    ("D-042c", "NCCc1ccccc1", "2-phenylethan-1-amine", "2-phenylethanamine",
     "as p. 518's '2-chloroethan-1-amine (PIN)'"),
    ("D-042d", "OCCc1ccccc1", "2-phenylethan-1-ol", "2-phenylethanol", ""),
    ("D-042e", "NCC(O)c1ccccc1", "2-amino-1-phenylethan-1-ol", "2-amino-1-phenylethanol",
     "held-out cid1000; PubChem drops the locant too"),
    # Converses: (a) a mononuclear parent omits it whatever the substitution;
    # (b) a monosubstituted chain omits it; N-substituents are not on the chain.
    ("D-042f", "CCO", "ethanol", "ethanol", "converse: monosubstituted"),
    ("D-042g", "ClCO", "chloromethanol", "chloromethanol", "converse: mononuclear"),
    ("D-042h", "CCN(CC)CC", "N,N-diethylethanamine", "N,N-diethylethanamine",
     "converse: N-substituents are on the nitrogen, the chain is monosubstituted"),
    # --- D-043: retained PINs the book lets you substitute -----------------
    # phenol (P-34.1.1.3, "substitution allowed"), aniline (P-34.1.1.5, "full
    # substitution"; p. 516 prints N-methylaniline and 4-chloroaniline),
    # benzaldehyde and acetaldehyde (P-66.6.1, "substitution allowed"). The
    # assembler already did this for benzoic acid; these were never added.
    ("D-043a", "Cc1ccc(O)cc1", "4-methylphenol", "4-methylbenzen-1-ol", ""),
    ("D-043b", "Oc1ccc(Cl)cc1Br", "2-bromo-4-chlorophenol", "2-bromo-4-chlorobenzen-1-ol", ""),
    ("D-043c", "Cc1ccc(N)cc1", "4-methylaniline", "4-methylbenzen-1-amine", ""),
    ("D-043d", "CNc1ccccc1", "N-methylaniline", "N-methylbenzen-1-amine", "p. 516, verbatim"),
    ("D-043e", "COc1ccccc1N", "2-methoxyaniline", "2-methoxybenzen-1-amine", "held-out cid7000"),
    ("D-043f", "Cc1ccc(C=O)cc1", "4-methylbenzaldehyde", "4-methylbenzene-1-carbaldehyde", ""),
    ("D-043g", "COc1cc(C=O)c(Cl)cc1O", "2-chloro-4-hydroxy-5-methoxybenzaldehyde",
     "2-chloro-4-hydroxy-5-methoxybenzene-1-carbaldehyde", "held-out cid29000"),
    ("D-043h", "O=CCc1ccccc1", "phenylacetaldehyde", "2-phenylethanal",
     "as p. 695's 'phenoxyacetaldehyde (PIN)'; the vendored guard that pinned "
     "2-phenylethanal claimed the book had no such PIN"),
    ("D-043i", "OCC=O", "hydroxyacetaldehyde", "2-hydroxyethanal", ""),
    # Negatives: anisole takes NO substitution in a PIN (P-34.1.1.4), toluene
    # is "not freely substitutable" (P-22.1.3), and two suffix groups keep
    # the systematic diamine.
    ("D-043j", "COc1ccc(C)cc1", "1-methoxy-4-methylbenzene", "1-methoxy-4-methylbenzene",
     "negative: anisole"),
    ("D-043k", "Cc1ccc(Cl)cc1", "1-chloro-4-methylbenzene", "1-chloro-4-methylbenzene",
     "negative: toluene"),
    ("D-043l", "Nc1ccccc1N", "benzene-1,2-diamine", "benzene-1,2-diamine",
     "negative: two suffix groups"),
    # --- D-044: registry names the book does not prefer, and ones it does --
    # Each demotion's systematic replacement was named and verified BEFORE
    # the registry changed; uracil and theophylline wait for stage A5, since
    # their systematic path still writes ring ketones as oxo prefixes.
    ("D-044a", "Oc1ccccc1O", "benzene-1,2-diol", "pyrocatechol", "p. 533"),
    ("D-044b", "Oc1cccc(O)c1", "benzene-1,3-diol", "resorcinol", "p. 533"),
    ("D-044c", "Oc1ccc(O)cc1", "benzene-1,4-diol", "hydroquinone", "p. 533"),
    ("D-044d", "Cc1ccc(C(C)C)cc1", "1-methyl-4-(propan-2-yl)benzene", "p-cymene",
     "P-22.1.3: 'The names cumene and cymene are not retained.'"),
    ("D-044e", "O=C1CCC(=O)N1", "pyrrolidine-2,5-dione", "succinimide",
     "P-66.2.1 -- KNOWN_LIMITATIONS called succinimide a genuine PIN"),
    ("D-044f", "O=C1CC(=O)NC(=O)N1", "1,3-diazinane-2,4,6-trione", "barbituric acid", "p. 566"),
    ("D-044g", "c1ccc2c(c1)CC2", "bicyclo[4.2.0]octa-1,3,5-triene", "benzocyclobutene",
     "P-52.2.4.1: a four-membered partner forbids a fusion PIN"),
    ("D-044h", "NCCc1c[nH]c2ccccc12", "2-(1H-indol-3-yl)ethan-1-amine", "tryptamine",
     "absent from the book; and D-042's locant, and D-040's 1H"),
    ("D-044i", "Cc1ccc(C)cc1", "1,4-xylene", "1,4-dimethylbenzene",
     "P-22.1.3: 'xylene (1,2-, 1,3-, and 1,4-isomers, PINs)'; the entry was ADDED"),
    ("D-044j", "Cc1ccccc1C", "1,2-xylene", "1,2-dimethylbenzene", "as D-044i"),
    ("D-044k", "Cc1cccc(C)c1", "1,3-xylene", "1,3-dimethylbenzene", "as D-044i"),
    # --- D-045: where a ring C=O suffix puts the ring's hydrogens (P-58.2) --
    # Each parent-naming route guessed at indicated / added / hydro on its
    # own; one procedure (ring_naming/indicated_hydrogen_p58) now decides,
    # and added hydrogen is a numbering criterion (P-31.1.4.2.4 (d)).
    ("D-045a", "Cn1ccccc1=O", "1-methylpyridin-2(1H)-one", "1-methylpyridin-2-one",
     "P-58.2.2 added hydrogen, lost when N1 carries a substituent"),
    ("D-045b", "O=C1C=CC(=O)N1", "1H-pyrrole-2,5-dione",
     "2,5-dihydro-1H-pyrrole-2,5-dione", "P-66.2.1 (pdf p. 666)"),
    ("D-045c", "O=C1Nc2ccccc2C1=O", "1H-indole-2,3-dione",
     "2,3-dihydro-1H-indole-2,3-dione", "P-58.2.3.1.3 (1): the one indicated H at N1"),
    ("D-045d", "O=C1Cc2ccccc2N1", "1,3-dihydro-2H-indol-2-one",
     "2,3-dihydro-1H-indol-2-one", "P-58.2.3.1.1: the indicated H on the group carbon"),
    ("D-045e", "O=C1CNc2ccccc12", "1,2-dihydro-3H-indol-3-one",
     "1,3-dihydro-2H-indol-3(2H)-one",
     "p. 566, '(not 1H-indol-3(2H)-one; see P-58.2)'; the former did not round-trip"),
    ("D-045f", "O=C1CC(=O)N=CN1", "pyrimidine-4,6(1H,5H)-dione",
     "3,5-dihydropyrimidine-4,6-dione",
     "p. 478; and the numbering direction is set by the added-H tier"),
    ("D-045g", "O=C1CCCc2ccccc21", "3,4-dihydronaphthalen-1(2H)-one",
     "3,4-dihydronaphthalen-1(2H)-one", "converse: added hydrogen still required"),
    ("D-045h", "O=C1CCCCN1", "piperidin-2-one", "piperidin-2-one",
     "negative: no ring double bond left, so the saturated name (p. 556)"),
    ("D-045i", "CCC1(c2ccccc2)C(=O)NC(=O)NC1=O",
     "5-ethyl-5-phenyl-1,3-diazinane-2,4,6-trione",
     "5-ethyl-5-phenyl-1,3-diazinane-2,4,6-trione",
     "negative: '1,3-diazinane-2,4,6-trione (PIN)' over the (1H,3H,5H) form, p. 566"),
    ("D-045j", "O=C1C=CC(=O)C=C1", "cyclohexa-2,5-diene-1,4-dione",
     "cyclohexa-2,5-diene-1,4-dione",
     "negative: not a mancude parent name, so nothing to rewrite (p. 558)"),
    # --- D-046: the chromene family's PINs are benzopyrans -----------------
    # "Systematic 'benzo' names, for example 2H-1-benzopyran, are preferred
    # IUPAC names for chromene, isochromene..." (pdf p. 45).
    ("D-046a", "O=c1ccc2ccccc2o1", "2H-1-benzopyran-2-one", "coumarin", "p. 45"),
    ("D-046b", "O=c1ccoc2ccccc12", "4H-1-benzopyran-4-one", "chromone", "p. 45"),
    ("D-046c", "O=c1occc2ccccc12", "1H-2-benzopyran-1-one", "isocoumarin", "p. 45"),
    ("D-046d", "C1=Cc2ccccc2OC1", "2H-1-benzopyran", "2H-chromene", "p. 45"),
    ("D-046e", "C1=COc2ccccc2C1", "4H-1-benzopyran", "4H-chromene", "p. 45"),
    ("D-046f", "CC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O",
     "4-hydroxy-3-(3-oxo-1-phenylbutyl)-2H-1-benzopyran-2-one",
     "4-hydroxy-3-(3-oxo-1-phenylbutyl)coumarin", "warfarin, substituted"),
    ("D-046g", "O=c1cc(-c2ccccc2)oc2ccccc12", "2-phenyl-4H-1-benzopyran-4-one",
     "2-phenylchromone", "flavone, substituted"),
    ("D-046h", "c1ccc2c(c1)CCCO2", "3,4-dihydro-2H-1-benzopyran",
     "3,4-dihydro-2H-1-benzopyran", "control: chroman's alias, already in place"),
    # --- D-047: a curated "-N-yl" form left its placeholder in the name ----
    # Every such substituent reached "...-N-2-yl", which OPSIN rejects.
    ("D-047a", "OC(=O)c1ccc(cc1)-c1cn2ccccc2n1",
     "4-(imidazo[1,2-a]pyridin-2-yl)benzoic acid",
     "4-(imidazo[1,2-a]pyridin-N-2-yl)benzoic acid", "a plain substituent_form"),
    ("D-047b", "OC(=O)c1ccc(cc1)-c1ccc2OCCCc2c1",
     "4-(3,4-dihydro-2H-1-benzopyran-6-yl)benzoic acid",
     "4-(3,4-dihydro-2H-1-benzopyran-N-6-yl)benzoic acid", "a pin_substituent_form"),
    ("D-047c", "OC(=O)c1ccc(cc1)C1CCc2ccccc21",
     "4-(2,3-dihydro-1H-inden-1-yl)benzoic acid",
     "4-(2,3-dihydro-1H-inden-N-1-yl)benzoic acid", "as D-047b"),
    ("D-047d", "OC(=O)c1ccc(cc1)C1CCCc2ccccc21",
     "4-(1,2,3,4-tetrahydronaphthalen-1-yl)benzoic acid",
     "4-(1,2,3,4-tetrahydronaphthalen-N-1-yl)benzoic acid", "as D-047b"),
    ("D-047e", "OC(=O)c1ccc(cc1)-c1cc2ccccc2oc1=O",
     "4-(2-oxo-2H-1-benzopyran-3-yl)benzoic acid",
     "4-(coumarin-3-yl)benzoic acid", "D-046's alias, as a substituent"),
    ("D-047f", "OC(=O)c1ccc(cc1)-c1ccc2ccccc2c1", "4-(naphthalen-2-yl)benzoic acid",
     "4-(naphthalen-2-yl)benzoic acid", "control: a form with no placeholder"),
    # --- D-048: base names the book never uses (searched: 0 hits each) -----
    # Held back from D-044 until their systematic names were right (D-045).
    ("D-048a", "O=c1cc[nH]c(=O)[nH]1", "pyrimidine-2,4(1H,3H)-dione", "uracil", "absent"),
    ("D-048b", "Cc1c[nH]c(=O)[nH]c1=O", "5-methylpyrimidine-2,4(1H,3H)-dione",
     "thymine", "absent"),
    ("D-048c", "Nc1cc[nH]c(=O)n1", "4-aminopyrimidin-2(1H)-one", "cytosine", "absent"),
    ("D-048d", "Cn1c(=O)c2[nH]cnc2n(C)c1=O",
     "1,3-dimethyl-3,7-dihydro-1H-purine-2,6-dione", "theophylline",
     "absent; its P-31.1.3 citation is about indicated hydrogen"),
    ("D-048e", "Cn1cnc2c1c(=O)[nH]c(=O)n2C",
     "3,7-dimethyl-3,7-dihydro-1H-purine-2,6-dione", "theobromine", "as D-048d"),
    # --- D-049: precomposed ring-ketone parents with hand-written hydrogens -
    # The ring table stores some parents WITH their C=O ("...-2-one"), which
    # the engine emits as written. 15 of 42 disagreed with P-58.2; three
    # described a different tautomer from their own key. Guarded wholesale by
    # test_every_precomposed_ring_ketone_name_places_its_hydrogens_by_p58.
    ("D-049a", "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
     "7-chloro-1-methyl-5-phenyl-1,3-dihydro-2H-1,4-benzodiazepin-2-one",
     "7-chloro-1-methyl-5-phenyl-2,3-dihydro-1H-1,4-benzodiazepin-2-one",
     "diazepam; P-58.2.3.1.1, as D-045d"),
    ("D-049b", "OC1N=C(c2ccccc2Cl)c2cc(Cl)ccc2NC1=O",
     "7-chloro-5-(2-chlorophenyl)-3-hydroxy-1,3-dihydro-2H-1,4-benzodiazepin-2-one",
     "7-chloro-5-(2-chlorophenyl)-3-hydroxy-2,3-dihydro-1H-1,4-benzodiazepin-2-one",
     "lorazepam, the same entry"),
    ("D-049c", "O=C1CCCc2ccccc2N1", "1,3,4,5-tetrahydro-2H-1-benzazepin-2-one",
     "2,3,4,5-tetrahydro-1H-1-benzazepin-2-one", "as D-049a"),
    ("D-049d", "O=c1nc[nH]n2cncc12", "imidazo[5,1-f][1,2,4]triazin-4(1H)-one",
     "imidazo[5,1-f][1,2,4]triazin-4(3H)-one",
     "the recorded name was the OTHER tautomer's; its own key has N1-H"),
    ("D-049e", "O=c1ccnc2ccccn12", "4H-pyrido[1,2-a]pyrimidin-4-one",
     "4H-pyrido[1,2-a]pyrimidin-4-one",
     "control: a bridgehead N takes no hydrogen, and the entry was right"),
    ("D-045k", "O=C1OCc2cnccc21", "furo[3,4-c]pyridin-1(3H)-one",
     "1,3-dihydrofuro[3,4-c]pyridin-1-one",
     "a parent with no indicated H takes ADDED hydrogen (P-58.2.2, p. 478)"),
    ("D-045l", "O=C1CC=CO1", "furan-2(3H)-one", "2,3-dihydrofuran-2-one", "as D-045k"),
    # --- D-050: isoindoline is not a PIN, so phthalimide was mis-parented ---
    # Table 3.1 (pdf p. 334): "2H-isoindoline / 2,3-dihydro-1H-isoindole (PIN)".
    ("D-050a", "O=C1N(c3ccccc3)C(=O)c2ccccc12", "2-phenyl-1H-isoindole-1,3(2H)-dione",
     "2-phenylisoindoline-1,3-dione", "the book's own example, p. 666"),
    ("D-050b", "O=C1NC(=O)c2ccccc12", "1H-isoindole-1,3(2H)-dione",
     "isoindoline-1,3-dione", "phthalimide"),
    ("D-050c", "c1ccc2c(c1)CNC2", "2,3-dihydro-1H-isoindole", "isoindoline", "Table 3.1"),
    # The book contradicts itself here. Its retained-prefix list (p. 344)
    # prints "2,3-dihydro-1H-isoindol-2-yl (preferred prefix) (also 1-, 4- and
    # 5-isomers)", one mechanical line for every isomer; P-58.2.3.1.1 and the
    # worked analysis on p. 499 give the free valence the indicated hydrogen
    # -- "Parent hydride with free valence: 2H-isoindol-2-yl" -- as in "1,3,4,5-
    # tetrahydro-2H-2-benzazepin-2-yl" (p. 481). The rule wins (A7).
    ("D-050d", "OC(=O)c1ccc(cc1)N1Cc2ccccc2C1",
     "4-(1,3-dihydro-2H-isoindol-2-yl)benzoic acid",
     "4-(isoindolin-2-yl)benzoic acid", "the alias as a substituent (D-047's path)"),
    # --- D-051: an N-substituted imine is still an imine (P-68.3.1.1.1) ----
    # The class matched only [NX2H1], so an oxime or an N-alkyl imine lost its
    # principal group and became a substituted alkane.
    ("D-051a", "CCC=NO", "N-hydroxypropan-1-imine", "1-(hydroxyimino)propane",
     "the book's own example, p. 98"),
    ("D-051b", "CC(C)=NC", "N-methylpropan-2-imine", "2-(methylimino)propane",
     "p. 842, 'N-methylpropan-2-imine N-oxide (PIN)'"),
    # Round 4 (A6): p. 934's "(1seqCis,4R)-N-hydroxy-4-methylcyclohexan-1-imine
    # (PIN)" needs its 1 for the 4-methyl. With only the N-hydroxy, the ring is
    # monosubstituted and P-14.3.4.2(c) omits the 1, as in "N-hydroxy-
    # cyclohexanecarboxamide (PIN)" (p. 587).
    ("D-051c", "ON=C1CCCCC1", "N-hydroxycyclohexanimine",
     "(hydroxyimino)cyclohexane", "P-14.3.4.2(c); an N-prefix is not a ring substituent"),
    ("D-051d", "CC(C)=NOC", "N-(methyloxy)propan-2-imine", "2-(methyloxyimino)propane",
     "an O-alkyl oxime; 'methyloxy' itself is A9's"),
    ("D-051e", "OC(=O)CCC(C)=NO", "4-(hydroxyimino)pentanoic acid",
     "4-(hydroxyimino)pentanoic acid",
     "converse: not the principal group, so the compound prefix stays"),
    ("D-051f", "CN=Cc1ccccc1O", "2-[(methylimino)methyl]phenol",
     "2-[(methylimino)methyl]phenol", "converse: a phenol outranks an imine"),
    ("D-051g", "CC(C)=NN", "(propan-2-ylidene)hydrazine",
     "1-(propan-2-ylidene)hydrazine", "negative: N-N is a hydrazone, not this class; "
     "round 5 (N4) dropped the '1', P-14.3.4 (b), as 'propylidenehydrazine (PIN)'"),
    ("D-051h", "CC(=N)N", "ethanimidamide", "ethanimidamide",
     "negative: C(=N)N is an amidine (p. 468)"),
    # --- D-052: hydrazides and formamides on their retained acid stems -----
    # P-66.3.1 (pdf p. 668): "formohydrazide (PIN)", "acetohydrazide (PIN)",
    # "benzohydrazide (PIN)"; P-66.1.1.1.2.2 (p. 646): formamide, N-substituted.
    ("D-052a", "CC(=O)NN", "acetohydrazide", "ethanohydrazide", "p. 668"),
    ("D-052b", "NNC(=O)c1ccccc1", "benzohydrazide", "benzenecarbohydrazide", "p. 668"),
    ("D-052c", "NNC(=O)c1ccc(Cl)cc1", "4-chlorobenzohydrazide",
     "4-chlorobenzenecarbohydrazide", "substituted, as p. 671's N'-benzoyl form"),
    ("D-052d", "CN(N)C(C)=O", "N-methylacetohydrazide", "1-acetyl-1-methylhydrazine",
     "p. 671, 'N-methylacetohydrazide (PIN)': the class needed an N-H"),
    ("D-052e", "NNC=O", "formohydrazide", "methanohydrazide", "p. 668"),
    ("D-052f", "O=CNc1ccccc1", "N-phenylformamide", "N-phenylmethanamide", "p. 649"),
    # Round 4 (A6) gave the hydrazide its N' locants, so this former control is
    # now named by P-66.3 ("N'-benzoylbenzohydrazide (PIN)", p. 671).
    ("D-052g", "CNNC(C)=O", "N'-methylacetohydrazide", "1-acetyl-2-methylhydrazine",
     "hydrazide N' locants (round 4, A6); was the control for their absence"),
    ("D-052h", "ClC(N)=O", "aminomethanoyl chloride", "aminomethanoyl chloride",
     "negative: a substituent on the formyl CARBON is not formamide "
     "('not 1-chloroformamide', p. 646)"),
    # --- D-053: a sulfonate anion is named on its acid, as a carboxylate is -
    # "benzenesulfonate (PIN)" (pdf p. 807). The anion route re-protonates
    # and names with the ANION suffix, but only accepted a CARBON neighbour.
    ("D-053a", "CS(=O)(=O)[O-]", "methanesulfonate", "(oxidosulfonyl)methane", "p. 807"),
    ("D-053b", "[O-]S(=O)(=O)c1ccccc1", "benzenesulfonate", "(oxidosulfonyl)benzene",
     "the book's own example"),
    ("D-053c", "[Na+].CS(=O)(=O)[O-]", "sodium methanesulfonate",
     "sodium (oxidosulfonyl)methane", "in a salt"),
    ("D-053d", "[O-]S(=O)(=O)CCS(=O)(=O)[O-]", "ethane-1,2-disulfonate",
     "1,2-bis(oxidosulfonyl)ethane", "two sites"),
    ("D-053e", "Cc1ccc(cc1)S(=O)(=O)O", "4-methylbenzene-1-sulfonic acid",
     "hydro-p-toluenesulfonate",
     "a registry entry from OPSIN named the ACID as a hydrogen salt; demoted"),
    ("D-053f", "Cc1ccc(cc1)S(=O)(=O)[O-]", "4-methylbenzene-1-sulfonate",
     "1-methyl-4-(oxidosulfonyl)benzene", "as p. 620's 4-ethylbenzene-1-sulfonate"),
    ("D-053g", "COS(=O)(=O)[O-]", "(sulfonatooxy)methane", "(sulfonatooxy)methane",
     "negative: O-sulfonate (a sulfate half-ester) is not a C-sulfonate"),
    # --- D-054: a sulfonic ester is named by functional class -------------
    # "methyl 4-ethylbenzene-1-sulfonate (PIN)" (pdf p. 620). Only the
    # carboxylic ester had a decomposition, so the ester O became a prefix.
    ("D-054a", "COS(=O)(=O)c1ccc(CC)cc1", "methyl 4-ethylbenzene-1-sulfonate",
     "1-ethyl-4-(methyloxysulfonyl)benzene", "the book's own example"),
    ("D-054b", "COS(=O)(=O)C", "methyl methanesulfonate", "(methyloxysulfonyl)methane",
     "an alkanesulfonate"),
    ("D-054c", "CS(=O)(=O)Oc1ccccc1", "phenyl methanesulfonate",
     "(methylsulfonyloxy)benzene", "an aryl ester"),
    ("D-054d", "COC(=O)c1ccc(cc1)S(=O)(=O)OC", "methyl 4-(methyloxysulfonyl)benzoate",
     "methyl 4-(methyloxysulfonyl)benzoate",
     "converse: a carboxylic ester outranks a sulfonic one, as its acid does"),
    ("D-054e", "COS(=O)(=O)OC", "dimethyl sulfate", "dimethyl sulfate",
     "negative: a sulfate diester is not a C-sulfonate"),
    # --- D-055: an ammonium cation is named by the aminium suffix ----------
    # The book's PINs use "-aminium" on a carbon parent; the azanium and
    # "tetramethylammonium" spellings are its NON-preferred alternatives
    # (pdf pp. 530, 816-849). Cations (class 6) outrank acids (Table 4.1).
    ("D-055a", "[Cl-].C[NH3+]", "methanaminium chloride", "methylazanium chloride",
     "p. 530, the book's own example"),
    ("D-055b", "CC[NH2+]C", "N-methylethanaminium", "ethyl(methyl)azanium",
     "p. 530, 'N-methylethanaminium bromide (PIN)'"),
    ("D-055c", "[I-].C[N+](C)(C)C", "N,N,N-trimethylmethanaminium iodide",
     "tetramethylammonium iodide", "p. 530"),
    ("D-055d", "C[N+](C)(C)c1ccccc1", "N,N,N-trimethylanilinium",
     "trimethyl(phenyl)ammonium", "p. 819"),
    ("D-055e", "[NH3+]c1ccccc1", "anilinium", "phenylazanium", "p. 848"),
    ("D-055f", "CCOC(=O)CC[N+](C)(C)C", "3-ethoxy-N,N,N-trimethyl-3-oxopropan-1-aminium",
     "ethyl 3-(trimethylazaniumyl)propanoate",
     "p. 621: a cation outranks the ester, so the ester becomes a prefix"),
    ("D-055g", "[NH3+]CC([NH3+])C", "propane-1,2-bis(aminium)",
     "[1-(azaniumyl)propan-2-yl]azanium", "p. 833: multiplied as bis(aminium)"),
    ("D-055h", "C[N+](C)(C)CC(=O)[O-]", "(trimethylazaniumyl)acetate",
     "2-(trimethylazaniumyl)acetate",
     "converse: a zwitterion (class 5) keeps the cation as a prefix; taken as "
     "the principal group it lost the anion, '1-carboxy-...methanaminium'"),
    ("D-055i", "[NH4+]", "azanium", "azanium", "negative: no carbon to carry a suffix"),
    # --- D-056: an alcohol and a phenol are one class, "-ol" (P-63.1) -----
    # Detected as two types, they became two principal-group options, and
    # the parent could take only one of them as its suffix.
    # The indicated hydrogen is 6H, not the 17H this row first pinned: C17 is
    # a CH of 1H-cyclopenta[a]phenanthrene, so the -ol needs no accommodating
    # (P-58.2.3.1 only places indicated hydrogen where a group needs it, cf.
    # "2,3-dihydro-1H-inden-2-yl", p. 343) and the lowest-locant rule for
    # indicated hydrogen applies (P-31.1.4.2.4 (c)).
    ("D-056a", "CC12CCC3c4ccc(O)cc4CCC3C1CCC2O",
     "13-methyl-7,8,9,11,12,13,14,15,16,17-decahydro-6H-cyclopenta[a]phenanthrene-3,17-diol",
     "17-hydroxy-13-methyl-6,7,8,9,11,12,13,14,15,16-decahydro-17H-cyclopenta[a]phenanthren-3-ol",
     "estradiol, flat: the round-4 plan's 'same-class suffix' item"),
    ("D-056b", "OC1CCc2cc(O)ccc21", "2,3-dihydro-1H-indene-1,5-diol",
     "5-hydroxy-2,3-dihydro-1H-inden-1-ol", "the smallest case"),
    ("D-056c", "OC1CCCc2cc(O)ccc21", "1,2,3,4-tetrahydronaphthalene-1,6-diol",
     "6-hydroxy-1,2,3,4-tetrahydronaphthalen-1-ol", "as D-056b"),
    ("D-056d", "OCc1ccc(O)cc1", "4-(hydroxymethyl)phenol", "4-(hydroxymethyl)phenol",
     "converse: one -ol per parent either way, and the ring is senior"),
    # --- D-057: the most principal groups on the parent, FIRST (P-44.1.1) --
    # The count was a band inside a blended float that scored a ring's exo
    # group 2.0 and a chain's 1.0, so one amine on a ring tied two on a
    # chain; it is its own tier now, and the amine types are one option.
    # "N1-(4-aminophenyl)-N4-phenylbenzene-1,4-diamine (PIN)" (pdf p. 524)
    # takes its parent the same way.
    ("D-057a", "CCN(CC)CCCC(C)Nc1ccnc2cc(Cl)ccc12",
     "N4-(7-chloroquinolin-4-yl)-N1,N1-diethylpentane-1,4-diamine",
     "7-chloro-N-[5-(diethylamino)pentan-2-yl]quinolin-4-amine",
     "chloroquine: the round-3 multi-PCG item"),
    ("D-057b", "CN(C)CCNc1ccccc1", "N1,N1-dimethyl-N2-phenylethane-1,2-diamine",
     "N-[2-(dimethylamino)ethyl]aniline", "the smallest case"),
    ("D-057c", "Nc1ccc(CCN)cc1", "4-(2-aminoethyl)aniline", "4-(2-aminoethyl)aniline",
     "converse: one amine each, so rings over chains decides"),
    ("D-057d", "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
     "7-chloro-1-methyl-5-phenyl-1,3-dihydro-2H-1,4-benzodiazepin-2-one",
     "7-chloro-1-methyl-5-phenyl-1,3-dihydro-2H-1,4-benzodiazepin-2-one",
     "control: a C=O a precomposed parent already spells still counts, or a "
     "von Baeyer name carrying it as a suffix wins"),
    # --- D-058: a diazonium is a suffix on its carbon parent (p. 823) -----
    # A whole-molecule renderer named the parent WITHOUT the group and
    # appended "-1-diazonium": a retained name and a lost position for any
    # substituted parent, and the book's own 3-substituted example on C1.
    ("D-058a", "CC(=O)C([N+]#N)C(C)=O", "2,4-dioxopentane-3-diazonium",
     "pentane-2,4-dione-1-diazonium",
     "the book's own PIN; the former put the group on C1 -- another molecule"),
    ("D-058b", "N#[N+]c1ccc(C)cc1", "4-methylbenzene-1-diazonium",
     "toluene-1-diazonium", "did not parse back"),
    ("D-058c", "COc1ccc([N+]#N)cc1", "4-methoxybenzene-1-diazonium",
     "anisole-1-diazonium", "as D-058b"),
    ("D-058d", "N#[N+]c1ccc(cc1)[N+]#N", "benzene-1,4-bis(diazonium)",
     "(azanylidyne){4-[(azanylidyne)azaniumyl]phenyl}azanium",
     "p. 823, '(not didiazonium)' (p. 128)"),
    ("D-058e", "N#[N+]c1ccccc1", "benzenediazonium", "benzenediazonium",
     "control: a bare parent keeps the whole-molecule route"),
    # --- D-059: enclosing marks and alkoxy spellings (A9) ------------------
    # Every prefix not on an allowlist was enclosed as though compound, and
    # every acyclic "...yl" was contracted to "...oxy". P-16.5.1 encloses a
    # SUBSTITUTED substituent or one qualified by locants; P-63.2.2.2 (pdf
    # p. 541) contracts only methoxy, ethoxy, propoxy, butoxy and phenoxy,
    # the last "fully substitutable".
    ("D-059a", "C=Cc1ccccc1", "ethenylbenzene", "(ethenyl)benzene", "a simple prefix"),
    ("D-059b", "OC(=O)COc1ccccc1", "phenoxyacetic acid", "(phenoxy)acetic acid",
     "as D-059a"),
    ("D-059c", "CCCCOCCOCCCO", "3-(2-butoxyethoxy)propan-1-ol",
     "3-[2-(butoxy)ethoxy]propan-1-ol", "the heldout cid16000 tail"),
    ("D-059d", "CCCCCCCOc1ccccc1N", "2-(heptyloxy)aniline", "2-(heptoxy)aniline",
     "no 'heptoxy': not one of the retained contractions"),
    ("D-059e", "CC(=O)Oc1ccccc1C(=O)O", "2-(acetyloxy)benzoic acid",
     "2-(acetoxy)benzoic acid", "aspirin; adjudicated as P-65.6-acetyloxy"),
    ("D-059f", "CC(C)Oc1ccccc1", "[(propan-2-yl)oxy]benzene", "(propan-2-oxy)benzene",
     "'(propan-2-yl)oxy (preferred prefix)', p. 541, and P-16.5.1.3's locant rule"),
    ("D-059g", "OC(=O)COc1cc(Cl)c(Cl)cc1Cl", "(2,4,5-trichlorophenoxy)acetic acid",
     "(2,4,5-trichlorophenyloxy)acetic acid", "phenoxy, substituted"),
    ("D-059h", "FC(F)(F)c1ccccc1", "(trifluoromethyl)benzene", "(trifluoromethyl)benzene",
     "converse: a substituted substituent keeps its marks"),
    ("D-059i", "OCc1ccc(O)cc1", "4-(hydroxymethyl)phenol", "4-(hydroxymethyl)phenol",
     "converse: as D-059h"),
    # --- D-060: an amino prefix's N-substituents, as the book writes them ---
    # Alphabetical; the first enclosed only if compound, every later one
    # enclosed (pdf pp. 521-665). Two builders pre-wrapped every name and let
    # the merge wrap the wrapped ones again.
    ("D-060a", "CCN(CCO)CCc1ccccc1", "2-[ethyl(2-phenylethyl)amino]ethan-1-ol",
     "2-{[(ethyl)][(2-phenylethyl)]amino}ethan-1-ol", "doubled marks"),
    ("D-060b", "CN(c1ccccc1)c1cccc(O)c1", "3-[methyl(phenyl)amino]phenol",
     "3-(methylphenylamino)phenol", "the book's own example, p. 521"),
    ("D-060c", "CN(Cc1nc2ccccc2cn1)CCO", "2-{methyl[(quinazolin-2-yl)methyl]amino}ethan-1-ol",
     "2-{[(methyl)][(quinazolin-2-yl)methyl]amino}ethan-1-ol",
     "FDA-0033's grouping still unambiguous: the later substituent is enclosed"),
    ("D-060d", "CC(C)N(C(C)C)CCO", "2-[di(propan-2-yl)amino]ethan-1-ol",
     "2-[bis(propan-2-yl)amino]ethan-1-ol",
     "a locant-qualified SIMPLE prefix takes di (P-16.5.1.3; 'di(butan-2-yl)amino', p. 554)"),
    ("D-060e", "CC(C)CN(CC(C)C)CCO", "2-[bis(2-methylpropyl)amino]ethan-1-ol",
     "2-[bis(2-methylpropyl)amino]ethan-1-ol",
     "converse: a substituted one keeps bis ('bis(2-methylpropyl)', p. 811)"),
    # --- D-061: italic locants are lower than numerals (P-14.3.5, p. 74) ---
    # Locant.__lt__ put numerals first and cited P-14.4 for it; every mixed
    # set came out "4,N". Each target below is the book's own printed PIN.
    ("D-061a", "CNC(=O)C(C)C", "N,2-dimethylpropanamide", "2,N-dimethylpropanamide",
     "p. 415"),
    ("D-061b", "CN(C(=O)c1ccc(C)cc1)c1cccc(C)c1",
     "N,4-dimethyl-N-(3-methylphenyl)benzamide",
     "4,N-dimethyl-N-(3-methylphenyl)benzamide", "p. 650"),
    ("D-061c", "CC(C)(N)CC(C)NC", "N4,2-dimethylpentane-2,4-diamine",
     "2,N4-dimethylpentane-2,4-diamine", "p. 522, a superscripted N"),
    ("D-061d", "Clc1ccc(cc1)C=Nc1ccc(Cl)cc1", "N,1-bis(4-chlorophenyl)methanimine",
     "1,N-bis(4-chlorophenyl)methanimine", "p. 526"),
    ("D-061e", "CNc1ccc(C)cc1", "N,4-dimethylaniline", "4,N-dimethylaniline",
     "as D-061b"),
    # --- D-062: R-CO-NH- is an amido prefix (P-66.1.1.4.3, pdf p. 652) -----
    # "changing the final letter 'e' in the complete name of the amide to
    # 'o' ... Method (1) generates preferred IUPAC names"; the engine used
    # method (2), acylamino, everywhere. An N-substituted one is cited as
    # acyl(R)amino in the book's enclosing style.
    ("D-062a", "O=CNc1ccc(C(=O)O)cc1", "4-formamidobenzoic acid",
     "4-(formylamino)benzoic acid", "the book's own PIN"),
    ("D-062b", "O=C(Nc1ccc(cc1)S(=O)(=O)O)c1ccccc1", "4-benzamidobenzene-1-sulfonic acid",
     "4-(benzoylamino)benzene-1-sulfonic acid", "the book's own PIN"),
    ("D-062c", "O=C(NCC(=O)O)C1CCCCC1", "(cyclohexanecarboxamido)acetic acid",
     "(cyclohexanecarbonylamino)acetic acid", "carboxamido, enclosed: a stem plus a group"),
    ("D-062d", "CCC(=O)N(C)c1ccccc1S(=O)(=O)O",
     "2-[methyl(propanoyl)amino]benzene-1-sulfonic acid",
     "2-{[(methyl)][(propanoyl)]amino}benzene-1-sulfonic acid", "the book's own example, p. 653"),
    ("D-062e", "CC(=O)N(C)c1ccc(C(=O)O)cc1", "4-[acetyl(methyl)amino]benzoic acid",
     "4-(acetylmethylamino)benzoic acid", "as D-062d"),
    # --- D-063: an acetate takes no C2 locant, as acetic acid does ---------
    # The omission ran for the acid only; the anion and an ester's acid stem
    # are whole names too (adjudicated: glycine zwitterion, heldout cid16000).
    ("D-063a", "[NH3+]CC(=O)[O-]", "azaniumylacetate", "2-azaniumylacetate",
     "adjudicated; PubChem's '2-' is the one lost verbatim match"),
    ("D-063b", "CCCCOCCOCCCOC(=O)COc1cc(Cl)c(Cl)cc1Cl",
     "3-(2-butoxyethoxy)propyl (2,4,5-trichlorophenoxy)acetate",
     "3-(2-butoxyethoxy)propyl 2-(2,4,5-trichlorophenoxy)acetate", "adjudicated"),
    ("D-063c", "COC(=O)CCl", "methyl chloroacetate", "methyl 2-chloroacetate", "an ester"),
    ("D-063d", "C[C@H](N)C(=O)O", "(2S)-2-aminopropanoic acid", "(2S)-2-aminopropanoic acid",
     "converse: a stereodescriptor citing C2 keeps its locant"),
    # P-16.5.1.3.2 (pdf p. 131): with the locants gone, the second and
    # further prefixes are each enclosed. Each target is the book's own PIN.
    ("D-063e", "OC(=O)C(Br)([N+](=O)[O-])c1ccccc1", "bromo(nitro)(phenyl)acetic acid",
     "bromonitrophenylacetic acid", "p. 131; the former ran the names together"),
    ("D-063f", "OC(=O)C(Cl)Br", "bromo(chloro)acetic acid", "bromochloroacetic acid",
     "p. 131"),
    ("D-063g", "O=CC(O)C1CC1", "cyclopropyl(hydroxy)acetaldehyde",
     "cyclopropylhydroxyacetaldehyde", "p. 889"),
    # --- D-064: preferred prefixes the engine spelled longhand, and the
    #     carbamate's N locant ------------------------------------------------
    ("D-064a", "c1ccncc1Cc1ccccc1", "3-benzylpyridine", "3-(phenylmethyl)pyridine",
     "'2-benzylpyridine (PIN)' (pdf p. 313)"),
    ("D-064b", "Brc1ccc(Cc2ccccn2)cc1", "2-[(4-bromophenyl)methyl]pyridine",
     "2-[(4-bromophenyl)methyl]pyridine",
     "converse: benzyl is 'not to be substituted' (P-29.6.1), the book's own PIN"),
    ("D-064c", "OC(=O)c1ccccc1Nc1ccc(Cl)cc1", "2-(4-chloroanilino)benzoic acid",
     "2-[(4-chlorophenyl)amino]benzoic acid", "anilino: 'full substitution' (p. 352)"),
    ("D-064d", "CNC(=O)c1ccccc1C(=O)O", "2-(methylcarbamoyl)benzoic acid",
     "2-[(methylamino)(oxo)methyl]benzoic acid", "carbamoyl: 'full substitution' (p. 352)"),
    ("D-064e", "CC(O)COC(=O)NCCN", "2-hydroxypropyl (2-aminoethyl)carbamate",
     "2-hydroxypropyl N-(2-aminoethyl)carbamate", "the book's own PIN, p. 601"),
    ("D-064f", "CCOC(=O)Nc1ccccc1", "ethyl phenylcarbamate", "ethyl N-phenylcarbamate",
     "carbamic acid has one substitutable atom (P-16.5.1.3.2)"),
    ("D-064g", "CN(C)C(=O)OCC", "ethyl dimethylcarbamate", "ethyl N,N-dimethylcarbamate",
     "as D-064f"),
    # --- D-065: round 3's carry-overs (A10), each the book's printed PIN ---
    ("D-065a", "CS(C)=O", "(methanesulfinyl)methane", "dimethyl sulfoxide",
     "p. 912; the class name is the book's SECOND form"),
    ("D-065b", "CS(C)(=O)=O", "(methanesulfonyl)methane", "dimethyl sulfone", "as D-065a"),
    ("D-065c", "CS(=O)(=O)c1ccccc1", "(methanesulfonyl)benzene", "methyl phenyl sulfone",
     "and 'benzenesulfonyl (preferred prefix) phenylsulfonyl', p. 611"),
    ("D-065d", "CCOOC", "(methylperoxy)ethane", "ethyl methyl peroxide", "P-63.3.1, p. 546"),
    ("D-065e", "CSSC", "(methyldisulfanyl)methane", "1,2-dimethyldisulfane",
     "p. 546: 'Names formed by substituting the parent hydrides ... disulfane ... are "
     "not recommended'"),
    ("D-065f", "ClC(=O)C(=O)Cl", "oxalyl dichloride", "ethane-1,2-dioyl chloride",
     "P-65.5.1, p. 615"),
    ("D-065g", "ClC(=O)CC(=O)Cl", "propanedioyl dichloride", "propane-1,3-dioyl chloride",
     "p. 615: no locants, and the class word multiplied"),
    ("D-065h", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine N-oxide",
     "N,N-dimethylmethanamine oxide", "the N locant, as p. 842's 'N-oxide'"),
    ("D-065i", "CC[Se](C)=O", "ethyl methyl selenoxide", "ethyl methyl selenoxide",
     "control, NOT a target: Se keeps the class name until a substitutive plan exists"),
    ("D-065j", "COc1ccc2[nH]c(nc2c1)S(=O)Cc1ncc(C)c(OC)c1C",
     "5-methoxy-2-[(4-methoxy-3,5-dimethylpyridin-2-yl)methanesulfinyl]-1H-benzimidazole",
     "(5-methoxy-1H-benzimidazol-2-yl) ((4-methoxy-3,5-dimethylpyridin-2-yl)methyl) sulfoxide",
     "omeprazole: substitutive, and a substituted methanesulfinyl (P-65.3.2.3)"),
    ("D-065k", "O=S(=O)(Cc1ccccc1)c1ccccc1C(=O)O", "2-(phenylmethanesulfonyl)benzoic acid",
     "(2-carboxyphenyl) (phenylmethyl) sulfone",
     "the former put the acid inside a sulfone class name"),
    # --- D-066: a saturated heteromonocycle takes its saturated name (A8) ---
    # P-31.1.4.2.4 (pdf p. 336): saturated retained / Hantzsch-Widman names
    # "are preferred to those expressed by 'hydro' prefixes"; Table 2.3 gives
    # "1,3-thiazolidine (PIN)". The tetrahydro name ranked as "retained".
    ("D-066a", "C1CSCN1", "1,3-thiazolidine", "2,3,4,5-tetrahydro-1,3-thiazole", "Table 2.3"),
    ("D-066b", "C1COCN1", "1,3-oxazolidine", "2,3,4,5-tetrahydro-1,3-oxazole", "Table 2.3"),
    ("D-066c", "O=C1CSC(=O)N1", "1,3-thiazolidine-2,4-dione",
     "2,3,4,5-tetrahydro-1,3-thiazole-2,4-dione", "adjudicated; exo C=O does not count"),
    ("D-066d", "O=C(O)c1ccc(NCN2C(=O)C(=Cc3ccc(O)cc3)SC2=S)cc1",
     "4-[({5-[(4-hydroxyphenyl)methylidene]-4-oxo-2-sulfanylidene-1,3-thiazolidin-3-yl}"
     "methyl)amino]benzoic acid",
     "4-[({5-[(4-hydroxyphenyl)methylidene]-4-oxo-2-(sulfanylidene)-1,3-thiazol-3-yl}"
     "methyl)amino]benzoic acid",
     "cid56000: a MANCUDE retained name on a ring with no ring double bond; its "
     "adjudicated (sulfanylidene) enclosing came off in N8"),
    ("D-066e", "O=C1CCCN1", "pyrrolidin-2-one", "pyrrolidin-2-one",
     "converse: Table 2.3's own saturated retained names keep their rank"),
    ("D-066f", "C1=CCNC1", "2,5-dihydro-1H-pyrrole", "2,5-dihydro-1H-pyrrole",
     "converse: a ring double bond keeps the hydro name"),
    # --- D-067: a saturated FUSED parent's hydrogens, by P-58.2 (A7) --------
    # A single-bonded suffix needs indicated or added hydrogen only on an atom
    # with none in the mancude parent: "1,4-dihydro-3aH-indene-3a-carboxylic
    # acid" and "naphthalen-4a(2H)-amine" (pp. 481, 526), but "1,2,3,4-tetra-
    # hydronaphthalen-1-amine (PIN)" (p. 526). Complete hydrogenation drops
    # the hydro locants (P-14.3.4.5, "decahydronaphthalene (PIN)", p. 73).
    ("D-067a", "OC12CCCC1CCCC2", "octahydro-3aH-inden-3a-ol", "octahydro-4H-inden-3a-ol",
     "a fusion carbon carries the -ol"),
    ("D-067b", "OC12CCCCC1CCCC2", "octahydronaphthalen-4a(2H)-ol",
     "decahydronaphthalen-4a-ol", "p. 535, 'naphthalen-4a(2H)-ol (PIN)', fully hydrogenated"),
    ("D-067c", "CC1(O)C2CCCCC2CC2CCCCC21", "9-methyltetradecahydroanthracen-9-ol",
     "9-methyl-1,2,3,4,4a,5,6,7,8,8a,9,9a,10,10a-tetradecahydroanthracen-9-ol",
     "P-14.3.4.5; 'tetradecahydroanthracene (PIN)', p. 336"),
    # Every position is hydro, added or the group, so no hydro locants:
    # "hexahydro-1H-isoindole-1,3(2H)-dione (PIN)", p. 666 (D-071i).
    ("D-067d", "O=C1CCCC2CCCCC12C", "8a-methyloctahydronaphthalen-1(2H)-one",
     "8a-methyldecahydronaphthalen-1-one", "the saturated form of p. 479's naphthalen-1(2H)-one"),
    ("D-067e", "C1CCC2CCCC2C1", "octahydro-1H-indene", "octahydro-4H-indene",
     "a table name; indicated hydrogen at the lowest locant"),
    ("D-067f", "CC1(O)CCC2C3CCC4CCCCC4(C)C3CCC12C",
     "10,13,17-trimethylhexadecahydro-1H-cyclopenta[a]phenanthren-17-ol",
     "10,13,17-trimethylhexadecahydro-1H-cyclopenta[a]phenanthren-17-ol",
     "converse: C17 is a CH of the 1H parent, so the -ol takes no indicated H"),
    ("D-067g", "NC1Cc2ccccc2C1", "2,3-dihydro-1H-inden-2-amine", "2,3-dihydro-1H-inden-2-amine",
     "converse: 'indan-2-yl ... 2,3-dihydro-1H-inden-2-yl (preferred prefix)', p. 343"),
    ("D-067h", "OC1CCOc2ccccc21", "3,4-dihydro-2H-1-benzopyran-4-ol",
     "3,4-dihydro-2H-1-benzopyran-4-ol", "converse: a CH of 2H-1-benzopyran"),
    # --- D-068: a free valence is accommodated like a suffix (A7) -----------
    # "pyridin-1(2H)-yl (preferred prefix)", "1,3-thiazol-3(2H)-yl (PIN)"
    # (pp. 479, 797). The retained route wrote the table's hydro text.
    ("D-068a", "OC(=O)CN1CCc2ccccc2C1", "(3,4-dihydroisoquinolin-2(1H)-yl)acetic acid",
     "(1,2,3,4-tetrahydroisoquinolin-2-yl)acetic acid",
     "cf. '1-(3,4-dihydroquinolin-1(2H)-yl)ethan-1-one (PIN)', p. 567"),
    ("D-068b", "OC(=O)CN1CSC=C1", "(1,3-thiazol-3(2H)-yl)acetic acid",
     "(2,3-dihydro-1,3-thiazol-3-yl)acetic acid", "the book's own prefix"),
    ("D-068c", "OC(=O)CC1Cc2ccccc2C1", "(2,3-dihydro-1H-inden-2-yl)acetic acid",
     "(2,3-dihydro-1H-inden-2-yl)acetic acid", "converse: a CH free valence, p. 343"),
    ("D-068d", "OC(=O)CC1CCOc2ccccc21", "(3,4-dihydro-2H-1-benzopyran-4-yl)acetic acid",
     "(3,4-dihydro-2H-1-benzopyran-4-yl)acetic acid", "converse, as D-067h"),
    # --- D-069: anthrone had no anthracene parent (A7) ----------------------
    # The single-hydro route required the saturated atom to sit next to the
    # C=O; in anthrone it is para. The book prints anthrone nowhere; the form
    # is P-58.2.2's, as in "anthracen-9(10H)-yl-10-ylidene" (p. 479).
    ("D-069a", "O=C1c2ccccc2Cc2ccccc21", "anthracen-9(10H)-one",
     "tricyclo[8.4.0.0^{3,8}]tetradeca-1(14),3,5,7,10,12-hexaen-2-one", "anthrone"),
    ("D-069b", "O=C1c2ccccc2C(C)c2ccccc21", "10-methylanthracen-9(10H)-one",
     "9-methyltricyclo[8.4.0.0^{3,8}]tetradeca-1(14),3,5,7,10,12-hexaen-2-one",
     "the suffix, not the hydrogen, takes the low locant"),
    ("D-069c", "O=C1CCCc2ccccc21", "3,4-dihydronaphthalen-1(2H)-one",
     "3,4-dihydronaphthalen-1(2H)-one", "converse: the adjacent case is unchanged"),
    # --- D-070: a ring "carbo-" suffix keeps its locant 1 (A7) --------------
    # The vendored set of "C1 by definition" suffixes held -carboxylic acid,
    # -carboxamide and -carbonitrile, which are added-carbon RING forms:
    # "piperidine-1-carboxamide (PIN)", "piperidine-1-carbonitrile (PIN)",
    # "pyrrolidine-1-carboxylic acid (PIN)" (pp. 645, 687, 580).
    ("D-070a", "OC(=O)c1cccc2ccccc12", "naphthalene-1-carboxylic acid",
     "naphthalenecarboxylic acid", "p. 564"),
    ("D-070b", "NC(=O)N1CCCCC1", "piperidine-1-carboxamide", "piperidinecarboxamide", "p. 645"),
    ("D-070c", "N#CN1CCCCC1", "piperidine-1-carbonitrile", "piperidinecarbonitrile", "p. 687"),
    ("D-070d", "OC(=O)N1CCCc2ccccc21", "3,4-dihydroquinoline-1(2H)-carboxylic acid",
     "1,2,3,4-tetrahydroquinolinecarboxylic acid",
     "'quinoline-1(2H)-carboxylic acid (PIN)', p. 479; the former did not parse back"),
    ("D-070e", "OC(=O)C1=CC=CCC1", "cyclohexa-1,3-diene-1-carboxylic acid",
     "cyclohexa-1,3-dienecarboxylic acid", "a multiplied '-dien' hid the ring's unsaturation"),
    ("D-070f", "OC(=O)C1CCCCC1", "cyclohexanecarboxylic acid", "cyclohexanecarboxylic acid",
     "converse: P-14.3.4.2(c) still omits it on a homogeneous monocycle"),
    ("D-070g", "OC(=O)c1cnccn1", "pyrazinecarboxylic acid", "pyrazinecarboxylic acid",
     "converse: P-14.3.4.4, unique by symmetry"),
    # --- D-071: a saturated HETEROfused ring kept no fusion name (A7) -------
    # P-31.2.3.3.2 names a hydrogenated mancude ring system by hydro prefixes
    # (p. 335). The hydro route re-aromatized the ring to find its parent; the
    # first mode that sanitized won even when it was the wrong tautomer (a
    # 1,4-dihydroquinoxaline), an azole N never got its H back, and an odd
    # saturated count had nowhere to put the parent's own indicated hydrogen.
    ("D-071a", "OC1CCC2C(C1)NC1CCCCC12", "dodecahydro-1H-carbazol-2-ol",
     "2-azatricyclo[7.4.0.0^{3,8}]tridecan-12-ol", "and 2, not 7: both orientations offered"),
    ("D-071b", "C1CCC2C(C1)NC1CCCCC12", "dodecahydro-1H-carbazole",
     "2-azatricyclo[7.4.0.0^{3,8}]tridecane", "perhydrocarbazole"),
    ("D-071c", "OC1CCC2NNCC2C1", "octahydro-1H-indazol-5-ol",
     "7,8-diazabicyclo[4.3.0]nonan-3-ol", "the NH put back on one N"),
    ("D-071d", "OC1CCC2NCCNC2C1", "decahydroquinoxalin-6-ol",
     "2,5-diazabicyclo[4.4.0]decan-8-ol", "the wrong tautomer sanitized first"),
    ("D-071e", "C1CCC2NCCNC2C1", "decahydroquinoxaline", "2,5-diazabicyclo[4.4.0]decane",
     "P-14.3.4.5, no hydro locants"),
    ("D-071f", "C1CCC2C(C1)OC1CCCCC12", "dodecahydrodibenzofuran",
     "1,2,3,4,4a,5a,6,7,8,9,9a,9b-dodecahydrodibenzofuran", "P-14.3.4.5"),
    ("D-071g", "OC1CCC2CNCCC2C1", "decahydroisoquinolin-6-ol", "3-azabicyclo[4.4.0]decan-8-ol",
     "the table entry numbered 1-4 only"),
    ("D-071h", "CC1CCC2CNCCC2C1", "6-methyldecahydroisoquinoline", "methyldecahydroisoquinoline",
     "the former did not parse back"),
    ("D-071i", "O=C1NC(=O)C2CCCCC12", "hexahydro-1H-isoindole-1,3(2H)-dione",
     "octahydro-1H-isoindole-1,3-dione", "the book's PIN, p. 666"),
    ("D-071j", "O=C1CCC2CCCC2C1", "octahydro-5H-inden-5-one", "octahydro-4H-inden-5-one",
     "P-58.2.3.1.1; cf. 'tetrahydro-4H-pyran-4-one', p. 481"),
    ("D-071k", "OC1CCC2NCCC2C1", "octahydro-1H-indol-5-ol", "octahydro-1H-indol-5-ol",
     "converse: a table entry already covered it"),
    # --- D-072: eleven ring-table locant maps were stored inverted (A7) -----
    # locant -> atom instead of atom -> locant ("4: 0", "5: 1"), so one ring
    # atom had no locant and the rest were misplaced; for the dihydrofuran and
    # dihydropyrrole that named a DIFFERENT molecule. All eleven re-checked by
    # OPSIN chloro probing of every locant.
    ("D-072a", "FC1=COCC1", "4-fluoro-2,3-dihydrofuran", "3-fluoro-2,3-dihydrofuran",
     "a different molecule"),
    ("D-072b", "OC(=O)C1=COCC1", "2,3-dihydrofuran-4-carboxylic acid",
     "2,3-dihydrofuran-3-carboxylic acid", "a different molecule"),
    ("D-072c", "FC1=CNCC1", "4-fluoro-2,3-dihydro-1H-pyrrole", "3-fluoro-2,3-dihydro-1H-pyrrole",
     "a different molecule"),
    ("D-072d", "FC1=CCOCC1", "4-fluoro-3,6-dihydro-2H-pyran", "4-fluoro-3,6-dihydro-2H-pyran",
     "converse: right by another route before, and still"),
    ("D-072e", "CC1=CCOC1", "3-methyl-2,5-dihydrofuran", "3-methyl-2,5-dihydrofuran",
     "converse, as D-072d"),
    # --- D-073: a prefix with no locant is refused, not emitted (A7) --------
    # A ring-table entry that numbers only some positions gave a substituent
    # elsewhere an empty locant, and the name went out as "fluoro-...": 32
    # entries were measured with such a gap. The substitutive builder now
    # refuses the plan and another parent is chosen.
    ("D-073a", "Fc1ccc2ssc2c1", "5-fluoro-1,2-benzodithiete", "fluoro-1,2-benzodithiete",
     "the former did not parse back"),
    ("D-073b", "Cc1ccncc1", "4-methylpyridine", "4-methylpyridine",
     "converse: a complete entry is untouched"),
    # --- D-074: a ring acid's locant carried into its cation (A7) -----------
    # The amidylium/amidinium renderers stripped "carboxylic acid" and
    # appended "-1-", so any other position printed "naphthalene-2-1-
    # amidylium", which does not parse; with D-070 the 1-isomer would have
    # broken the same way.
    ("D-074a", "c1ccc2cc(C(=O)[NH+])ccc2c1", "naphthalen-2-amidylium",
     "naphthalene-2-1-amidylium", "the former did not parse back"),
    ("D-074b", "NC(=[NH2+])c1ccc2ccccc2c1", "naphthalen-2-amidinium",
     "naphthalene-2-1-amidinium", "as D-074a"),
    ("D-074c", "C1(=CC=CC2=CC=CC=C12)C(=O)[NH+]", "naphthalen-1-amidylium",
     "naphthalen-1-amidylium", "converse: position 1 unchanged"),
    # --- D-075: hydrazide nitrogens take N and N' (A6) --------------------
    # P-66.3: the acyl-side N is N and the terminal one N' ('N'-benzoylbenzo-
    # hydrazide (PIN)', p. 671). The pattern needed a bare N'H2, so any N'
    # substituent broke the suffix, and N primes came from atom order.
    ("D-075a", "CNNC(=O)c1ccccc1", "N'-methylbenzohydrazide",
     "[(2-methylhydrazinyl)(oxo)methyl]benzene", "the terminal N is N' (p. 671)"),
    ("D-075b", "CC(=O)NNc1ccccc1", "N'-phenylacetohydrazide",
     "(2-acetylhydrazinyl)benzene", "as D-075a"),
    ("D-075c", "CN(C)NC(=O)c1ccccc1", "N',N'-dimethylbenzohydrazide",
     "[(2,2-dimethylhydrazinyl)(oxo)methyl]benzene", "two on N'"),
    ("D-075d", "CN(N)C(=O)c1ccccc1", "N-methylbenzohydrazide",
     "N-methylbenzohydrazide", "converse: the acyl-side N stays unprimed"),
    ("D-075e", "NNC(=O)N1CCCCC1", "piperidine-1-carbohydrazide",
     "1-[(hydrazinyl)(oxo)methyl]piperidine", "p. 667, 'piperidine-1-carbohydrazide (PIN)'"),
    ("D-075f", "O=C(NNC(=O)c1ccccc1)c1ccccc1", "1,2-dibenzoylhydrazine",
     "[(2-benzoylhydrazinyl)(oxo)methyl]benzene", "control, NOT a target: an acylated N' is kept out of the hydrazide pattern; letting it in named '1,2-dibenzoylhydrazine-1,2-dicarbohydrazide', a different molecule. Round 5 (N4): the hydrazine parent now outranks benzene (P-44.1.2) -- the right molecule, and still not the PIN, which is 'N'-benzoylbenzohydrazide (PIN) (not 1,2-dibenzoylhydrazine)' (p. 670); see OPEN D-088a"),
    # --- D-076: amidine nitrogens take N and N' by role (A6) ---------------
    # P-66.4.1.4.1 (p. 678): 'the locant N refers to the amino group and N'
    # refers to the imino group'. The pattern needed =NH and NH2.
    ("D-076a", "CNC(C)=N", "N-methylethanimidamide",
     "1-imino-N-methylethan-1-amine", "the amino N is N (p. 678)"),
    ("D-076b", "CN=C(C)N", "N'-methylethanimidamide",
     "1-(methylimino)ethan-1-amine", "the imino N is N' (p. 678)"),
    ("D-076c", "CCN=C(NC)c1ccccc1", "N'-ethyl-N-methylbenzenecarboximidamide",
     "1-(ethylimino)-N-methyl-1-phenylmethanamine", "p. 678, verbatim"),
    ("D-076d", "CN=C(N(c1ccccc1)c1ccccc1)c1ccccc1", "N'-methyl-N,N-diphenylbenzenecarboximidamide",
     "N-[(methylimino)phenylmethyl]-N-phenylaniline", "p. 678, verbatim"),
    ("D-076e", "NC(=N)c1ccccc1", "benzenecarboximidamide",
     "benzenecarboximidamide", "converse: unsubstituted"),
    ("D-076f", "CCCCCC(N)=N", "hexanimidamide",
     "hexan-1-imidamide", "p. 674, verbatim; amidines follow the amide rules"),
    ("D-076g", "NC(=N)CCC(N)=N", "butanediimidamide",
     "butane-1,4-diimidamide", "two terminal amidines take 'diimidamide' (p. 674)"),
    ("D-076h", "CN=C(N)CCC(N)=NC", "N'1,N'4-dimethylbutanediimidamide",
     "1,4-bis(methylimino)butane-1,4-diamine", "the prime before the numeral, as D-082a"),
    # --- D-077: an N-prefix does not block P-14.3.4.2(c) (A6) --------------
    # 'N-hydroxycyclohexanecarboxamide (PIN)' (p. 587): a prefix on the
    # suffix's nitrogen is not a ring substituent, so the 1 is omitted.
    ("D-077a", "CNC(=O)C1CCCCC1", "N-methylcyclohexanecarboxamide",
     "N-methylcyclohexane-1-carboxamide", "an N-prefix leaves the ring monosubstituted (p. 587)"),
    ("D-077b", "CNS(=O)(=O)c1ccccc1", "N-methylbenzenesulfonamide",
     "N-methylbenzene-1-sulfonamide", "as D-077a (p. 661)"),
    ("D-077c", "CNC(=O)C1CCCCC1C", "N,2-dimethylcyclohexane-1-carboxamide",
     "N,2-dimethylcyclohexane-1-carboxamide", "converse: a ring prefix keeps the 1"),
    # --- D-078: guanidine and urea as N-core parents (A6) -----------------
    # Substituted guanidines had no parent at all. The urea route also
    # claimed molecules whose acid outranks urea, primed by atom order, and
    # the acylamino builder spelled 'carbamyl' and dropped enclosing marks.
    ("D-078a", "CNC(N)=N", "N-methylguanidine",
     "guanidinomethane", "guanidine as parent (p. 676)"),
    ("D-078b", "CN(C)C(N)=N", "N,N-dimethylguanidine",
     "(dimethylamino)methanimidamide", "as D-078a"),
    ("D-078c", "c1ccccc1N=C(N(C)C)N(C)C", "N,N,N',N'-tetramethyl-N''-phenylguanidine",
     "N,N,N',N'-tetramethyl-1-(phenylimino)methane-1,1-diamine", "p. 676, verbatim: the imino N is N''"),
    ("D-078d", "CNC(=O)N(C)C", "N,N,N'-trimethylurea",
     "N,N',N'-trimethylurea", "lowest locants for all prefixes decide which N is unprimed"),
    ("D-078e", "NC(=O)NCC(=O)O", "(carbamoylamino)acetic acid",
     "N-(carboxymethyl)urea", "the acid outranks urea; 'carbamoyl', not 'carbamyl' (p. 660)"),
    ("D-078f", "OC(=O)c1c(NC(=O)NC)ccc2ccccc12", "2-[(methylcarbamoyl)amino]naphthalene-1-carboxylic acid",
     "N-(1-carboxynaphthalen-2-yl)-N'-methylurea", "p. 660, verbatim"),
    ("D-078g", "NC(=N)NCCCC(=O)O", "4-(carbamimidoylamino)butanoic acid",
     "4-guanidinobutanoic acid", "'carbamimidoylamino (preferred prefix)', p. 676"),
    ("D-078h", "NC(=N)NC(C)=O", "N-carbamimidoylacetamide",
     "N-carbamimidoylacetamide", "converse: p. 676, an amide outranks guanidine"),
    ("D-078i", "CN(C)C(=O)Nc1ccccc1", "N,N-dimethyl-N'-phenylurea",
     "N,N-dimethyl-N'-phenylurea", "converse: unchanged"),
    ("D-078j", "NC(N)=NCCCCCCCCCCCCCCN=C(N)N", "N'',N'''''-(tetradecane-1,14-diyl)diguanidine",
     "1,14-bis[(diaminomethylidene)amino]tetradecane", "cid45000's shape: a guanidine carbon is not an amidine ('amino...methanimidamide' was the widened pattern's name). Round 5 (N4) reaches the multiplicative form (P-51.3.1): imino N is N'' (p. 675), the second unit's nitrogens follow the first's three (P-15.3.2.2.1). Derived, not printed"),
    ("D-078k", "NC(=O)NC(=O)c1ccccc1", "N-carbamoylbenzamide",
     "N-benzoylurea", "p. 660, verbatim; 'amides from carboxylic acids ... are senior to "
     "urea' (P-66.1.6.1.1.5). Round 5 (N6): a urea carbonyl is no longer a carboxamide, "
     "so the benzoyl amide is perceived and the urea route steps aside for it"),
    # --- D-079: condensed guanidines are imidodicarbonimidic diamides (A6) --
    # 'biguanide ... no longer recommended' (p. 677); the page's figure
    # numbers N1 1 N'1 2 3 N'3 N3. The former of D-079b named a DIFFERENT
    # molecule (the ethyl on an amino N).
    ("D-079a", "CN(C)C(=N)NC(N)=N", "N1,N1-dimethylimidodicarbonimidic diamide",
     "1,1-dimethylbiguanide", "metformin; 'biguanide' is no longer recommended (p. 677)"),
    ("D-079b", "NC(=N)NC(=NCC)N(c1ccccc1)c1ccccc1", "N'1-ethyl-N1,N1-diphenylimidodicarbonimidic diamide",
     "1-ethyl-1,1-diphenylbiguanide", "p. 677, verbatim"),
    ("D-079c", "NC(=N)NC(N)=N", "imidodicarbonimidic diamide",
     "guanidinomethanimidamide", "the bare parent (p. 677)"),
    # --- D-080: carbamic acid substituted on N (A6) -----------------------
    ("D-080a", "c1ccccc1NC(=O)O", "phenylcarbamic acid",
     "anilinomethanoic acid", "p. 120"),
    ("D-080b", "CN(C)C(=O)O", "dimethylcarbamic acid",
     "(dimethylamino)methanoic acid", "p. 601"),
    ("D-080c", "NC(=O)NC(=O)O", "carbamoylcarbamic acid",
     "N-carboxyurea", "p. 661"),
    # --- D-081: single heteroatom-centre parents (A6) ---------------------
    # Silanols, boron and pnictogen oxoacids, phosphanones and diazenes take
    # prefixes on the centre with no locant (P-63.1.4, P-67.1.1.2, P-68.1.4,
    # P-68.3.1.3, P-74.2.1.4). Each steps aside for a senior group elsewhere.
    ("D-081a", "C[Si](C)(C)O", "trimethylsilanol",
     "(hydroxy)tri(methyl)silane", "p. 537"),
    ("D-081b", "CB(O)O", "methylboronic acid",
     "methaneboronic acid", "p. 737, 'not methylboranediol'"),
    ("D-081c", "OB(O)c1ccc(cc1)C(=O)O", "4-boronobenzoic acid",
     "4-boronobenzoic acid", "converse: the carboxylic acid outranks it"),
    ("D-081d", "O=Pc1ccccc1", "phenylphosphanone",
     "oxo(phenyl)phosphane", "p. 769, 'not oxo(phenyl)phosphane'"),
    ("D-081e", "CP(C)(C)=O", "trimethyl-lambda5-phosphanone",
     "trimethylphosphane oxide", "p. 769 and p. 839: method (3) is the PIN"),
    ("D-081f", "CN=NC", "dimethyldiazene",
     "1,2-dimethyldiazene", "p. 761"),
    ("D-081g", "c1ccc(cc1)N=Nc1ccccc1", "diphenyldiazene",
     "(phenyldiazenyl)benzene", "p. 761"),
    ("D-081h", "Clc1cccc(c1)N=Nc1ccc(Cl)cc1", "(3-chlorophenyl)(4-chlorophenyl)diazene",
     "1-chloro-3-(4-chlorophenyldiazenyl)benzene", "p. 761, verbatim"),
    ("D-081i", "Oc1ccc(cc1)N=Nc1ccccc1", "4-(phenyldiazenyl)phenol",
     "4-(phenyldiazenyl)phenol", "converse: a suffix group outranks diazene"),
    ("D-081j", "CCP(=O)(O)O", "ethylphosphonic acid",
     "ethanephosphonic acid", "p. 700, 'not ethanephosphonic acid'"),
    ("D-081k", "CCP(=O)(O)CC", "diethylphosphinic acid",
     "diethyl(hydroxy)(oxo)phosphane", "p. 700"),
    ("D-081l", "O[As](c1ccccc1)c1ccccc1", "diphenylarsinous acid",
     "(hydroxy)di(phenyl)arsane", "p. 700"),
    ("D-081m", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine N-oxide",
     "N,N-dimethylmethanamine N-oxide", "converse: N-oxides stay additive"),
    # --- D-082: a primed N locant with a numeral is N'1, not N1' (A6) -------
    ("D-082a", "O=C(NNCc1ccccc1)C(=O)NNCc1ccccc1", "N'1,N'2-dibenzyloxalohydrazide",
     "({2-[(2-benzylhydrazinyl)(oxo)acetyl]hydrazinyl}methyl)benzene", "'N'1', not 'N1'': OPSIN reads N1' as another position, and the heldout cid55000 name came back a different molecule; the retained stem 'oxalohydrazide (PIN)' (p. 667) since round 5 N5 (D-089c)"),
    ("D-082b", "CNC(=O)CC(=O)NC", "N1,N3-dimethylpropanediamide",
     "N1,N3-dimethylpropanediamide", "converse: no prime, unchanged"),
    # --- D-083: general fusion nomenclature, P-25.3 (round 5, N3) ----------
    # Targets are the book's own PINs, verbatim, with the page; "former" is
    # what the engine emitted at a2eff41, measured, not guessed. 13 of the
    # book's 125 ortho- and peri-fused examples were exact before; 78 after.
    ("D-083a", "c1cc2ccsc2o1", "thieno[2,3-b]furan",
     "furo[2,3-b]thiophene", "P-25.3.2.4 (a): O is senior to S, so furan is the parent (p. 222)"),
    ("D-083b", "c1cc2cc[se]c2[se]1", "selenopheno[2,3-b]selenophene",
     "selenolo[2,3-b]selenofuran", "retained names and 'e' -> 'o' prefixes (p. 210)"),
    ("D-083c", "C1=Nc2ccccc2CO1", "4H-3,1-benzoxazine",
     "[1,3]oxazino[4,5-b]benzene", "a benzo name, P-25.2.2.4 (p. 207)"),
    ("D-083d", "C1=Cc2ccccc2C=CO1", "3-benzoxepine",
     "4-oxabicyclo[5.4.0]undeca-1(11),2,5,7,9-pentaene", "p. 207"),
    ("D-083e", "c1cc2ccc3ncccc3cc-2c1", "azuleno[6,5-b]pyridine",
     "[NAMING ERROR: No valid naming plan found for c1cc2ccc3ncccc3cc-2c1]",
     "a heterocycle is senior to a larger carbocycle (p. 217)"),
    ("D-083f", "c1ccc2c(c1)[nH]c1cc3nccnc3cc12", "6H-pyrazino[2,3-b]carbazole",
     "[NAMING ERROR: No valid naming plan found for c1ccc2c(c1)[nH]c1cc3nccnc3cc12]",
     "P-25.3.2.4 (b): more rings (p. 217)"),
    ("D-083g", "c1cn2ccsc2n1", "imidazo[2,1-b][1,3]thiazole",
     "[NAMING ERROR: No valid naming plan found for c1cn2ccsc2n1]",
     "a fusion N belongs to both components; [1,3]thiazole, never thiazole (p. 220)"),
    ("D-083h", "c1cc2nc3ccoc3cc2o1", "difuro[3,2-b:2',3'-e]pyridine",
     "[NAMING ERROR: No valid naming plan found for c1cc2nc3ccoc3cc2o1]",
     "identical attached components, primed (p. 225)"),
    ("D-083i", "c1cc2ccc3ccnc4ccc(c1)c2c34", "naphtho[2,1,8-def]quinoline",
     "4-azatetracyclo[10.2.2.0^{5,14}.0^{8,13}]hexadecane",
     "peri fusion: only the attached component's nonfused atoms are cited (p. 239)"),
    ("D-083j", "c1ccc2c(c1)COc1ccccc1-2", "6H-dibenzo[b,d]pyran",
     "3-oxatricyclo[8.4.0.0^{4,9}]tetradeca-1(14),4,6,8,10,12-hexaene",
     "two benzenes on one heterocycle are dibenzo, not a benzo name (p. 234)"),
    ("D-083k", "C1=CC=CC2=C(C=C1)C=CC2", "1H-cyclopenta[8]annulene",
     "bicyclo[6.3.0]undeca-1(8),2,4,6,9-pentaene",
     "two monocyclic hydrocarbons: no descriptor; lowest indicated hydrogen (p. 238)"),
    ("D-083l", "c1poc2c1OCO2", "5H-[1,3]dioxolo[4,5-d][1,2]oxaphosphole",
     "2,6,8-trioxa-3-phosphabicyclo[3.3.0]octa-1(5),3-diene",
     "greater variety of heteroatoms; P now joins the P-58 planner (p. 218)"),
    ("D-083m", "c1ccc2c(c1)ccc1ccccc12", "phenanthrene",
     "phenanthrene", "converse: a retained system stays with the ring table"),
    ("D-083n", "C1CC2CCC1C2", "bicyclo[2.2.1]heptane",
     "bicyclo[2.2.1]heptane", "converse: bridged, so von Baeyer is right"),
    # --- D-084: ring-table names repaired on the way (round 5, N3) ---------
    # OPSIN's arylGroups stems were read as whole ring names: "quinolizin",
    # "arsindol". A stem regains its 'e' when OPSIN's fusion prefixes show the
    # parent has one ("quinolizino"); and the table's hydrogen-free name loses
    # to the constructor's planned one.
    ("D-084a", "C1=CCN2C=CC=CC2=C1", "4H-quinolizine",
     "quinolizin", "'the PIN is 4H-quinolizine' (p. 203)"),
    ("D-084b", "c1ccc2cc3cc4ccccc4cc3cc2c1", "tetracene",
     "naphthacene", "'tetracene (PIN) (formerly naphthacene)' (p. 199)"),
    ("D-084c", "C1=Cc2ccccc2[AsH]1", "1H-arsindole",
     "arsindol", "Table 2.8's As analogue of indole"),
    ("D-084d", "N=C1c2ccccc2-c2ccccc12", "9H-fluoren-9-imine",
     "fluoren-9-imine", "the P-58.2 planner reaches the table's ring once its hydrogens are "
     "planned: the indicated H goes on the group carbon (P-58.2.3.1.1, as "
     "'1,2-dihydro-3H-indol-3-one (PIN)'); heldout_v2 h2cid20500, where PubChem "
     "writes the same wrong form"),
    ("D-084e", "Clc1ccc2cccc3c2c1NC=N3", "9-chloro-1H-perimidine",
     "4-chloro-3H-perimidine", "P-14.4 (b) ranks indicated hydrogen before the "
     "substituent (pdf p. 74), and 'the PIN is 1H-perimidine' (p. 201); the "
     "preference key had no indicated-hydrogen tier, so the table's 3H numbering "
     "won on the chlorine's locant. Found by the vendored suite"),
    ("D-084f", "O=C(O)C1=CC=CCO1", "2H-pyran-6-carboxylic acid",
     "2H-pyran-6-carboxylic acid", "the book's own P-14.4 (b) example (pdf p. 74): "
     "the indicated hydrogen keeps 2 although the suffix could have had it. A "
     "converse -- the new tier must not trade it for 6H-pyran-2-carboxylic acid"),
    # --- D-085: the round's corpus population (round 5, N3) --------------
    # Each round-trips through OPSIN; the numbering choice between mirror
    # numberings is the substitutive machinery's once they travel together.
    ("D-085a", "CCN(CC)C(=O)c1c2c(nc3ccccc13)CCCCC2",
     "N,N-diethyl-7,8,9,10-tetrahydro-6H-cyclohepta[b]quinoline-11-carboxamide",
     "N,N-diethyl-2-azatricyclo[8.5.0.0^{3,8}]pentadeca-1,3,5,7,9-pentaene-9-carboxamide",
     "heldout_v2 h2cid23500; PubChem prints the same name"),
    ("D-085b", "CN1CCN([C@H]2c3cc(Cl)ccc3Sc3ccccc3[C@H]2O)CC1",
     "(10R,11S)-2-chloro-11-(4-methylpiperazin-1-yl)-10,11-dihydrodibenzo[b,f]thiepin-10-ol",
     "(9R,10S)-13-chloro-10-(4-methylpiperazin-1-yl)-2-thiatricyclo[9.4.0.0^{3,8}]pentadeca-1(15),3,5,7,11,13-hexaen-9-ol",
     "heldout_v2 h2cid55500; the suffix takes the lower of the mirror numberings"),
    ("D-085c", "COc1ccc2c(c1)c1c3c(c4c5ccccc5n(C)c4c1n2CC(O)CN(C)C)C(=O)NC3=O",
     "13-[3-(dimethylamino)-2-hydroxypropyl]-3-methoxy-12-methyl-12,13-dihydro-5H-indolo[2,3-a]pyrrolo[3,4-c]carbazole-5,7(6H)-dione",
     "2-[3-(dimethylamino)-2-hydroxypropyl]-21-methoxy-5-methyl-2,5,15-triazahexacyclo[17.4.0.0^{3,18}.0^{4,12}.0^{6,11}.0^{13,17}]tricosa-1(23),3,6,8,10,12,17,19,21-nonaene-14,16-dione",
     "heldout_v2 h2cid3500; prefixes {3,12,13} before {9,12,13}"),
    ("D-085d", "CC1C(=O)N=C2Nc3cccc(Cl)c3CN21",
     "6-chloro-3-methyl-5,10-dihydroimidazo[2,1-b]quinazolin-2(3H)-one",
     "4-chloro-13-methyl-1,9,11-triazatricyclo[8.3.0.0^{3,8}]trideca-3,5,7,10-tetraen-12-one",
     "heldout_v1 cid5000"),
    # --- D-087: candidate generation (round 5, N4) ------------------------
    # P-44.1.2 (pdf p. 375): the senior ATOM chooses between a ring and a
    # chain, N > P > ... > Si > ... > C, before ring over chain. The engine
    # had no such tier; a flat ring bonus beat hydrazine.
    ("D-087a", "NNc1ccccc1", "phenylhydrazine", "(hydrazinyl)benzene",
     "'phenylhydrazine (PIN)' (p. 755); '1' omitted, P-14.3.4 (b)"),
    ("D-087b", "NNC(N)=O", "hydrazinecarboxamide", "1-(hydrazinyl)methanamide",
     "'hydrazinecarboxamide (PIN)' (p. 757)"),
    ("D-087c", "NNC(=O)Nc1ccccc1", "N-phenylhydrazinecarboxamide",
     "1-(hydrazinyl)-N-phenylmethanamide", "'N-phenylhydrazinecarboxamide (PIN)' (p. 757)"),
    ("D-087d", "CNC(=O)N(C)N", "N,1-dimethylhydrazine-1-carboxamide",
     "N-methyl-1-(1-methylhydrazinyl)methanamide",
     "'N,1-dimethylhydrazine-1-carboxamide (PIN)' (p. 757)"),
    ("D-087e", "CCCC(CC)=NNC(=O)N(c1ccccc1)c1ccccc1",
     "2-(hexan-3-ylidene)-N,N-diphenylhydrazine-1-carboxamide",
     "1-[2-(hexan-3-ylidene)hydrazinyl]-N,N-diphenylmethanamide",
     "the book's semicarbazone (p. 758)"),
    ("D-087f", "NNC(=O)O", "hydrazinecarboxylic acid", "aminocarbamic acid",
     "'hydrazinecarboxylic acid (PIN) (not carbazic acid)' (p. 756): the carbamic "
     "acid route declines on an N-N"),
    ("D-087g", "NC(=S)NN", "hydrazinecarbothioamide", "hydrazinecarbothioamide",
     "'hydrazinecarbothioamide (PIN)' (p. 758); converse, held"),
    ("D-087h", "NNC(=O)NN", "hydrazinecarbohydrazide", "1-[(hydrazinyl)(oxo)methyl]hydrazine",
     "'hydrazinecarbohydrazide (PIN) ... carbonic dihydrazide' (p. 671): the hydrazide "
     "pattern admits a carbonyl whose other neighbour is a hydrazine N"),
    ("D-087i", "O=C(NN)c1ccccc1S(=O)(=O)O", "2-(hydrazinecarbonyl)benzene-1-sulfonic acid",
     "2-[(hydrazinyl)(oxo)methyl]benzene-1-sulfonic acid",
     "'hydrazinecarbonyl (preferred prefix)' (p. 668); the book's example, p. 669"),
    ("D-087j", "CN(C)N", "1,1-dimethylhydrazine", "1,1-dimethylhydrazine",
     "converse: two substituents keep their locants (p. 755)"),
    ("D-087k", "NNC(=O)c1ccccc1", "benzohydrazide", "benzohydrazide",
     "converse: hydrazine present never means hydrazine parent -- the hydrazide is "
     "the principal group (p. 667)"),
    ("D-087l", "C[Si](C)(C)c1ccccn1", "2-(trimethylsilyl)pyridine",
     "trimethyl(pyridin-2-yl)silane", "N is senior to Si (P-44.1.2)"),
    ("D-087m", "NS(=O)(=O)O", "sulfamic acid", "amidosulfuric acid",
     "'H2N-SO2-OH sulfamic acid' (p. 703); the other is the inorganic form"),
    ("D-087n", "CNS(=O)(=O)O", "N-methylsulfamic acid", "[(hydroxysulfonyl)amino]methane",
     "derived: P-67.1.2.4.1 substitutes a nonacidic H 'with a letter locant ... N', "
     "as 'N,N-dimethylphosphoramidic acid (PIN)' (p. 703)"),
    ("D-087o", "O=S(=O)(O)N1CCCCC1", "piperidine-1-sulfonic acid",
     "piperidine-1-sulfonic acid", "converse: a ring N is the ring parent's suffix site"),
    ("D-087p", "c1ccc(Oc2ccccc2)cc1", "1,1'-oxydibenzene", "phenoxybenzene",
     "multiplicative, P-51.3.1 (tests/test_namer_multiplicative.py has the book's set)"),
    ("D-087q", "OP(O)(=O)CP(O)(O)=O", "methylenebis(phosphonic acid)",
     "methane-1,1-diphosphonic acid", "as '[azanediylbis(methylene)]bis(phosphonic acid) "
     "(PIN)' (p. 105); a phosphonic acid is a functional parent (P-67.1.2)"),
    ("D-087r", "CC(=O)NNCNNC(C)=O", "N',N'''-methylenediacetohydrazide",
     "N'-[(2-acetylhydrazinyl)methyl]acetohydrazide", "p. 106, verbatim"),
    ("D-087s", "CCOC(=O)NN", "(ethoxycarbonyl)hydrazine", "ethyl aminocarbamate",
     "control, NOT the PIN (that is ethyl hydrazinecarboxylate, OPEN D-088b): a "
     "carbazate is never split as a carbamate, 'not carbazic acid' (p. 756)"),
    # --- Round 5 (N5): the OPSIN registry gate, retained parents, a(ba)n
    # chains. The gate refuses a RECORD, never a spelling: the converses at
    # the end are names the engine builds itself, one of them at a SMILES
    # where the registry holds an OPSIN-sourced entry under another name. ----
    ("D-088e", "[SiH3][SiH2]C", "methyldisilane", "methyl(silyl)silane",
     "derived, P-44.3: same senior atom, so the longer chain is the parent; the "
     "silane centre's +50 in parent_selection had outranked it"),
    ("D-088g", "OCCN(CCO)CCO", "2,2',2''-nitrilotri(ethan-1-ol)", "triethanolamine",
     "p. 106: 'triethanolamine' was an OPSIN-sourced registry entry, now gated"),
    ("D-089a", "O=c1[nH]cc(F)c(=O)[nH]1", "5-fluoropyrimidine-2,4(1H,3H)-dione",
     "fluorouracil", "an INN copied from OPSIN's dictionary into the registry; the "
     "gate requires NORMATIVE_RULE evidence and it has none"),
    ("D-089b", "Nc1ncnc2[nH]cnc12", "9H-purin-6-amine", "adenine",
     "the registry's audited RETAINED_NOT_PIN now binds the curated ring table's "
     "record of the SAME name; that table was consulted first and never audited"),
    ("D-089c", "NNC(=O)C(=O)NN", "oxalohydrazide", "ethanedihydrazide",
     "'oxalohydrazide (PIN)' (P-66.3.1, p. 667)"),
    ("D-089d", "NC(=O)C(N)=O", "oxamide", "ethanediamide",
     "'oxamide (PIN)', substitution on N allowed (P-66.1.1.1.2.1, p. 644)"),
    ("D-089e", "N#CCNC(=O)C(=O)NCC#N", "N1,N2-bis(cyanomethyl)oxamide",
     "N1,N2-bis(cyanomethyl)ethanediamide", "p. 653, verbatim; OPSIN cannot parse "
     "the book's N1,N2-oxamide form, an oracle gap, not a namer defect"),
    ("D-089f", "O[Si](O)(O)O", "silicic acid", "tetrahydroxysilane",
     "'silicic acid (preselected name) (not orthosilicic acid)' (p. 698)"),
    ("D-089g", "CCO[Si](OCC)(OCC)OCC", "tetraethyl silicate", "tetraethoxysilane",
     "derived: esters are named from silicic acid (P-68.2.4, p. 748), as 'O-ethyl "
     "S,S,S-trimethyl trithiosilicate (PIN)' (p. 710)"),
    ("D-089h", "O[Si](O)(O)O[Si](O)(O)O", "disilicic acid",
     "tri(hydroxy)(trihydroxysilanyloxy)silane",
     "'disilicic acid (preselected name)' (p. 720)"),
    ("D-089i", "Cl[SiH2]O[SiH3]", "chlorodisiloxane", "chloro(silyloxy)silane",
     "p. 71, verbatim: an a(ba)n chain (P-21.2.3.1) is a substitutable parent"),
    ("D-089j", "[SiH3]O[SiH2]C(=O)O", "disiloxanecarboxylic acid",
     "(silyloxy)silanecarboxylic acid", "p. 579, verbatim"),
    ("D-089k", "CPPC", "1,2-dimethyldiphosphane", "methyl(methylphosphanyl)phosphane",
     "derived, P-44.3, as D-088e"),
    ("D-089l", "C[Si](C)(C)O[Si](C)(C)O[Si](C)(C)C", "octamethyltrisiloxane",
     "{[dimethyl(trimethylsilyloxy)silyl]oxy}tri(methyl)silane",
     "derived: trisiloxane (P-21.2.3.1, p. 145); P-14.3.4.5 omits the locants "
     "since N8 (D-089q)"),
    ("D-089m", "CC(=O)CCN1CCCCCC1", "4-(azepan-1-yl)butan-2-one",
     "4-(azepan-1-yl)butan-2-one", "converse: the registry holds OPSIN's "
     "'hexamethyleneimine' at azepane's SMILES; the engine's own 'azepane' is untouched"),
    ("D-089n", "NCC(=O)O", "glycine", "glycine",
     "converse: an unaudited entry without OPSIN provenance stays usable -- the gate "
     "is not 'denied without evidence'"),
    ("D-089o", "C[Si](C)(C)O", "trimethylsilanol", "trimethylsilanol",
     "converse: one Si keeps the silane centre"),
    ("D-089p", "OB(O)O", "boric acid", "boric acid",
     "converse: B joined the a(ba)n chains; a lone boron acid is still an acid"),
    ("D-089w", "Cl[SiH2]O[Si](C)(C)C", "3-chloro-1,1,1-trimethyldisiloxane",
     "(chlorosilanyloxy)tri(methyl)silane", "derived: a chain is numbered from "
     "either end, and {1,1,1,3} is lower than {1,3,3,3} (P-31.1.4)"),
    ("D-089x", "CBOB", "methyldiboroxane", "(boryloxy)(methyl)borane",
     "derived from 'tetramethyldiboroxane (PIN)' (p. 731); OPSIN parses boroxanes, "
     "which the old reason for excluding boron said it could not"),
    ("D-089z", "C[Si](O[Si](C)(C)C)(O[Si](C)(C)C)O[Si](C)(C)C",
     "1,1,1,3,5,5,5-heptamethyl-3-(trimethylsilyloxy)trisiloxane",
     "[(1,1,1,3,5,5,5-heptamethyltrisiloxanyl)oxy]tri(methyl)silane",
     "derived, P-44.3: a branched siloxane offers each end-to-end chain and the "
     "longest is the parent; the prefix's enclosure is N8's"),
    ("D-090a", "[SiH](O[SiH3])(O[SiH3])O[SiH3]", "3-(silyloxy)trisiloxane",
     "tris(silyloxy)silane", "derived: trisiloxane has two kinds of Si-H, so the "
     "locant stays (P-14.3.4.3); the two-atom-chain omission must not reach it"),
    ("D-090c", "O=c1[nH]cnc2[nH]cnc12", "1,9-dihydro-6H-purin-6-one", "hypoxanthine",
     "registry RETAINED_NOT_PIN (absent from the book); ring naming's curated "
     "table emitted it as a PARENT name until the gate bound that table too"),
    ("D-090d", "Nc1nc2[nH]cnc2c(=O)[nH]1", "2-amino-1,9-dihydro-6H-purin-6-one", "guanine",
     "as D-090c; with only the curated table gated it briefly became "
     "'2-aminohypoxanthine' from OPSIN's ring vocabulary -- that table is gated by "
     "the registry's demotions too"),
    ("D-090e", "O=c1[nH]c(=O)c2[nH]cnc2[nH]1", "3,7-dihydro-1H-purine-2,6-dione", "xanthine",
     "the systematic name KNOWN_LIMITATIONS gives; gating 'xanthine' first left NO "
     "name, because the oxo-on-mancude derivation waited for a ring mol it never uses"),
    ("D-090f", "O=c1[nH]c(=O)c2nc[nH]c2[nH]1", "3,9-dihydro-1H-purine-2,6-dione", "xanthine",
     "the curated table files xanthine under two tautomer keys and the registry "
     "one, so its demotion is read by NAME; 'xanthine' also parsed back as the 7H "
     "tautomer, which this name does not"),
    # --- Round 5 (N8): serialization. ------------------------------------
    ("D-089q", "C[Si](C)(C)O[Si](C)(C)C", "hexamethyldisiloxane",
     "1,1,1,3,3,3-hexamethyldisiloxane", "P-14.3.4.5 (pdf p. 72): 'all locants are "
     "omitted ... in which all substitutable positions are completely substituted "
     "... in the same way', as the book's own 'tetrafluorourea (PIN)' (pdf p. 73)"),
    ("D-089r", "ClC(Cl)(Cl)C(Cl)(Cl)Cl", "hexachloroethane",
     "1,1,1,2,2,2-hexachloroethane", "as D-089q"),
    ("D-092h", "CB(C)OB(C)C", "tetramethyldiboroxane", "1,1,3,3-tetramethyldiboroxane",
     "'tetramethyldiboroxane (PIN)' (p. 731)"),
    ("D-092i", "ClC1=C(Cl)C(Cl)=C(Cl)C(Cl)=C1Cl", "hexachlorobenzene",
     "1,2,3,4,5,6-hexachlorobenzene", "a ring parent under the same rule"),
    ("D-092j", "FC(F)(F)C(Cl)(Cl)Cl", "1,1,1-trichloro-2,2,2-trifluoroethane",
     "1,1,1-trichloro-2,2,2-trifluoroethane", "converse: TWO substituent kinds are not "
     "'in the same way', so the locants stay"),
    ("D-092k", "ClC(Cl)(Cl)C(Cl)Cl", "1,1,1,2,2-pentachloroethane",
     "1,1,1,2,2-pentachloroethane", "converse: one position is still free"),
    ("D-092l", "O=C1CSC(=S)N1", "2-sulfanylidene-1,3-thiazolidin-4-one",
     "2-(sulfanylidene)-1,3-thiazolidin-4-one", "a one-stem ylidene prefix is simple, so "
     "P-16.5.1.3 leaves it bare: '3-sulfanylidene-2-benzothiophen-1-one (PIN)' (pdf p. 642)"),
    ("D-092m", "C=C1CCCO1", "2-methylideneoxolane", "2-methylidenoxolane",
     "elision belongs at a stem/suffix junction, not between a prefix and its parent: "
     "'2-sulfanylideneoxolane-3-carbonitrile (PIN)' (pdf p. 631). Unenclosing the "
     "prefix let this junction reach the elision rule for the first time"),
    ("D-092o", "CCCCC(=O)NN", "pentanehydrazide", "pentanohydrazide",
     "verbatim (pdf p. 43): \"the suffix '-hydrazide' rather than '-ohydrazide' ... "
     "pentanehydrazide ..., not pentanohydrazide\""),
    ("D-092p", "CC(=O)NN", "acetohydrazide", "acetohydrazide",
     "converse: a RETAINED acid stem keeps the connecting 'o' (PIN, p. 667)"),
    ("D-092q", "NNC(=O)c1ccncc1", "pyridine-4-carbohydrazide", "pyridine-4-carbohydrazide",
     "converse: in '-carbohydrazide' the 'o' belongs to 'carbo'"),
    ("D-092r", "CCC=CC(=O)NN", "pent-2-enehydrazide", "pent-2-enohydrazide", "as D-092o"),
    ("D-092s", "CCOC(=O)c1c(C)c2c(OCC(O)CNCCc3ccc(OC)c(OC)c3)cccc2n1C",
     "ethyl 4-(3-{[2-(3,4-dimethoxyphenyl)ethyl]amino}-2-hydroxypropoxy)-1,3-dimethyl-"
     "1H-indole-2-carboxylate",
     "ethyl 4-[(3-{[2-(3,4-dimethoxyphenyl)ethyl]amino}-2-hydroxypropyl)oxy]-1,3-dimethyl-"
     "1H-indole-2-carboxylate", "h2cid53500, adjudicated: methoxy..butoxy are 'fully "
     "substitutable' (P-63.2.2.2), and the ring test asked about the whole fragment "
     "rather than the ATTACHMENT atom"),
    ("D-092t", "c1ccc(OC2CCCCC2)cc1", "phenoxycyclohexane", "phenoxycyclohexane",
     "converse: an attachment ON a ring keeps the 'yloxy' form where it applies"),
    ("D-092u", "O=C1SC(=Cc2ccccc2)C(=O)N1", "5-(phenylmethylidene)-1,3-thiazolidine-2,4-dione",
     "5-(phenylmethylidene)-1,3-thiazolidine-2,4-dione", "converse to D-092l: "
     "'phenylmethylidene' is TWO stems, a compound prefix, so it keeps its "
     "enclosing marks"),
    ("D-092v", "C1CCCCC1OCC(=O)O", "(cyclohexyloxy)acetic acid", "(cyclohexyloxy)acetic acid",
     "converse to D-092s: the ATTACHMENT atom is a ring atom, so no contraction "
     "(P-63.2.2.2 retains only methoxy..butoxy and phenoxy)"),
    ("D-092w", "Cc1nnnn1C", "1,5-dimethyl-1H-tetrazole", "1,5-dimethyl-1H-tetrazole",
     "converse to D-089q: an aromatic ring N carries no hydrogen to begin with, so "
     "'no free position' is NOT 'every substitutable position substituted'. 2,5- is "
     "another compound, so these locants stay (measured on the vendored suite)"),
    ("D-092x", "CN(C)N(C)C", "1,1,2,2-tetramethylhydrazine", "1,1,2,2-tetramethylhydrazine",
     "converse: the book prints no locant-free form for a fully substituted "
     "hydrazine, so P-14.3.4.5 is not applied to it"),
    ("D-092y", "C1CCC1OCC(=O)O", "(cyclobutyloxy)acetic acid", "(cyclobutyloxy)acetic acid",
     "converse to D-092s, and the one that BITES: 'cyclobutyl' ends in 'butyl', so "
     "only the attachment-atom ring test stops it contracting to 'cyclobutoxy'"),
    # --- Round 5 (N9): exposed by the registry audit's demotions. ---------
    ("D-093a", "C(O)O", "methanediol", "methane-1,1-diol",
     "P-14.3.4.6 (pdf p. 73): 'all locants are omitted for parent compounds when "
     "all substitutable hydrogen atoms have the same locant', and a mononuclear "
     "parent has one position -- 'dimethylsilanediol (PIN)' (p. 748). A retained "
     "registry entry supplied this name until the N9 audit demoted it as absent "
     "from the book, which is how the systematic route's locants surfaced"),
    ("D-093b", "C(S)S", "methanedithiol", "methane-1,1-dithiol", "as D-093a"),
    ("D-093c", "OC(O)c1ccccc1", "phenylmethanediol", "phenylmethane-1,1-diol",
     "as D-093a: a substituent does not create a second position on methane"),
    ("D-093d", "CC(O)O", "ethane-1,1-diol", "ethane-1,1-diol",
     "converse: two carbons, so 1,1 and 1,2 are different compounds"),
    ("D-093e", "OCCO", "ethane-1,2-diol", "ethane-1,2-diol", "converse, as D-093d"),
    # --- Naming round 6: amides and esters of cyanic and thiocyanic acid. ---
    # Found by the functional-groups v3 cross-check. The generic path read the
    # cyano group as a nitrile of methane and named the ester's carbon parent.
    ("D-094a", "NC#N", "cyanamide", "aminomethanenitrile",
     "P-66.1.6.2 (pdf p. 663), verbatim: 'cyanamide' is retained for NC-NH2 and is the PIN"),
    ("D-094b", "CC(C)NC#N", "(propan-2-yl)cyanamide", "[(propan-2-yl)amino]methanenitrile",
     "p. 663, verbatim '(propan-2-yl)cyanamide (PIN)'"),
    ("D-094c", "CCN(CC)C#N", "diethylcyanamide", "(diethylamino)methanenitrile",
     "p. 663, verbatim 'diethylcyanamide (PIN)'"),
    ("D-094d", "CN(C)C#N", "dimethylcyanamide", "(dimethylamino)methanenitrile",
     "derived from D-094c: 'substitution is allowed on the -NH2 group'"),
    ("D-094e", "CCN(C)C#N", "ethyl(methyl)cyanamide", "[ethyl(methyl)amino]methanenitrile",
     "derived: two different substituents cited alphabetically, no locants (one position)"),
    ("D-094f", "OCCNC#N", "(2-hydroxyethyl)cyanamide", "[(2-hydroxyethyl)amino]methanenitrile",
     "derived: the amide class is senior to the alcohol (P-41)"),
    ("D-094g", "CC(C)SC#N", "propan-2-yl thiocyanate", "[(propan-2-yl)sulfanyl]methanenitrile",
     "P-65.6.3.3.7.2.1 (p. 629), verbatim '(CH3)2CH-S-CN propan-2-yl thiocyanate (PIN)'"),
    ("D-094h", "CSC#N", "methyl thiocyanate", "(methylsulfanyl)methanenitrile",
     "derived from D-094g; also the Gold Book's own example (thiocyanates, p. 1537)"),
    ("D-094i", "c1ccccc1OC#N", "phenyl cyanate", "phenoxymethanenitrile",
     "derived: P-65.2.2 (p. 604) makes cyanic acid an acid that 'generat[es] ... esters'; "
     "the Gold Book prints 'PhOCN phenyl cyanate' (p. 363)"),
    ("D-094j", "COC#N", "methyl cyanate", "methoxymethanenitrile", "as D-094i"),
    ("D-094k", "N#CSCCC(=O)O", "3-(thiocyanato)propanoic acid", "3-(cyanosulfanyl)propanoic acid",
     "P-65.2.2 (p. 604), verbatim '3-(thiocyanato)propanoic acid (PIN)': the prefix "
     "derived from thiocyanic acid, ENCLOSED as the book prints it"),
    ("D-094l", "CCSC(=O)CCSC#N", "S-ethyl 3-(thiocyanato)propanethioate",
     "2-[(ethylsulfanyl)(oxo)methyl]ethyl thiocyanate",
     "p. 629, verbatim: the thioester outranks the thiocyanate ester, so this is the "
     "converse that keeps the new ester route from stealing a molecule with a senior group"),
    ("D-094m", "N#CN1CCCCC1", "piperidine-1-carbonitrile", "piperidine-1-carbonitrile",
     "control: a ring N is the ring parent's -carbonitrile, not a cyanamide"),
    ("D-094n", "N#CNC(C)=O", "N-cyanoacetamide", "N-cyanoacetamide",
     "control: an amide elsewhere is the parent"),
    ("D-094o", "N#CN=C(N)N", "N''-cyanoguanidine", "N''-cyanoguanidine",
     "control: an N-cyanoimine is not an amide of cyanic acid; the guanidine is the parent"),
    ("D-094p", "S=C=NCCC(=O)O", "3-isothiocyanatopropanoic acid", "3-isothiocyanatopropanoic acid",
     "converse to D-094k, and the one that BITES: 'isothiocyanato' CONTAINS the word "
     "'thiocyanato', which the book encloses, and is printed bare (pdf p. 615)"),
    ("D-094q", "O=C=NCCC(=O)O", "3-isocyanatopropanoic acid", "3-isocyanatopropanoic acid",
     "control: an isocyanate is N-bound and is not touched by the cyanate routes"),
    ("D-092z", "CC1(C)c2c(C)c(C)c(C)c(C)c2C(C)=C1C", "octamethyl-1H-indene",
     "octamethyl-1H-indene", "P-14.3.4.5 on a carbocyclic parent that carries "
     "indicated hydrogen in its NAME: every substitutable position is a methyl"),
    # --- Round 5 (N6): principal-group seniority and assignment. ----------
    ("D-089t", "[SiH](O)(O)O", "silanetriol", "trihydroxysilane",
     "derived from 'dimethylsilanediol (PIN)' (p. 748): a bare silanol had no "
     "retained-name entry for the single-centre route to fall to (N6)"),
    ("D-091a", "NC(=O)NS(=O)(=O)c1ccccc1", "N-carbamoylbenzenesulfonamide",
     "N-(benzenesulfonyl)urea", "p. 660, verbatim"),
    ("D-091b", "NC(=O)NC(=O)Cc1ccccc1", "N-carbamoyl-2-phenylacetamide",
     "N-(phenylacetyl)urea", "p. 660, verbatim"),
    ("D-091c", "NC(=O)NCCNC(C)=O", "N-[2-(carbamoylamino)ethyl]acetamide",
     "N-(2-acetamidoethyl)urea", "p. 660, verbatim: the urea route let any amide stand "
     "as its substituent (limit 1100, amides are 1100)"),
    ("D-091d", "NC(=O)NCCCNC=O", "N-[3-(carbamoylamino)propyl]formamide",
     "N-(3-formamidopropyl)urea", "p. 660, verbatim '[not N-(3-formamidopropyl)urea]'"),
    ("D-091e", "NC(=O)NC(=O)NC(N)=O", "N-(carbamoylcarbamoyl)urea",
     "N-(carbamoylcarbamoyl)urea", "control, NOT the PIN (2,4-diimidotricarbonic diamide, "
     "OPEN D-091t): the new urea group and an amide both claimed the shared N until the "
     "amide was made to subsume it"),
    ("D-091f", "NC(=N)CCC(=O)O", "4-amino-4-iminobutanoic acid",
     "4-carbamimidoylbutanoic acid", "a WRONG MOLECULE before: 'carbamimidoyl' carries its "
     "carbon and the chain named it too. P-66.4.1.3.2 (p. 676): a chain-terminal amidine "
     "is 'amino' + 'imino'"),
    ("D-091g", "CN(C)C(=NCC)CCC(=O)OC", "methyl 4-(dimethylamino)-4-(ethylimino)butanoate",
     "methyl 4-carbamimidoylbutanoate", "p. 676, verbatim; each nitrogen takes the "
     "substituents hanging off it, which the demoted amidine held in its own atom set"),
    ("D-091h", "NC(=N)c1ccc(C(=O)O)cc1", "4-carbamimidoylbenzoic acid",
     "4-carbamimidoylbenzoic acid", "converse, p. 676 verbatim: off the chain, the carbon "
     "is the prefix's"),
    ("D-091i", "C[Si](C)(O)CCO", "(2-hydroxyethyl)di(methyl)silanol",
     "2-[(hydroxy)di(methyl)silyl]ethan-1-ol", "derived: P-44.1.1 counts one -OH each, "
     "then P-44.1.2 prefers Si; 'di(methyl)' is N8's enclosure defect"),
    ("D-091j", "OC(=O)C[Si](C)(C)O", "[hydroxydi(methyl)silyl]acetic acid",
     "[(hydroxy)di(methyl)silyl]acetic acid", "converse: an acid's O-H is not an alcohol "
     "to count, so the acid stays principal"),
    ("D-091k", "OCC(O)C[Si](C)(C)O", "3-[hydroxydi(methyl)silyl]propane-1,2-diol",
     "3-[(hydroxy)di(methyl)silyl]propane-1,2-diol", "converse: two alcohols beat one "
     "silanol on P-44.1.1's count"),
    ("D-091l", "CN[Si](O)(O)O", "(methylamino)silanetriol",
     "tri(hydroxy)(methylamino)silane", "p. 748, verbatim"),
    ("D-091m", "C[Si](C)(O)O", "dimethylsilanediol", "dimethylsilanediol",
     "control, p. 748 verbatim"),
    ("D-091n", "ONC(=O)C1CCCCC1", "N-hydroxycyclohexanecarboxamide",
     "cyclohexanecarbohydroxamic acid", "p. 587, verbatim '(not cyclohexanecarbohydroxamic "
     "acid)'; the OH's O is the N-hydroxy prefix's, not the suffix's (ownership)"),
    ("D-091o", "ONC(C)=O", "N-hydroxyacetamide", "ethanehydroxamic acid", "p. 586, verbatim"),
    ("D-091p", "CN(O)C(C)=O", "N-hydroxy-N-methylacetamide",
     "1-[hydroxy(methyl)amino]-1-oxoethane", "derived, as D-091o: the pattern required N-H"),
    ("D-091q", "OC1=CC=CCC1", "cyclohexa-1,3-dien-1-ol", "1-hydroxycyclohexa-1,3-diene",
     "an enol is an alcohol: the -ol suffix (adjudicated round-4 leftover)"),
    ("D-091r", "OC1=CCCc2ccccc21", "3,4-dihydronaphthalen-1-ol",
     "1-hydroxy-3,4-dihydronaphthalene", "p. 535, verbatim"),
    ("D-091s", "C[Si](C)(OC)O", "methoxydi(methyl)silanol",
     "(hydroxy)(methoxy)di(methyl)silane", "derived; the silanol route wrote "
     "'methyloxy' until bare alkoxy names were contracted (P-63.2.2.2)"),
    ("D-091w", "O=c1cccc2ccccn12", "4H-quinolizin-4-one", "[NAMING ERROR]",
     "derived from '4H-quinolizine (PIN)' (p. 203). OPEN when N1 re-probed it; found "
     "fixed when N6 re-probed the adjudication's open rows, by an earlier round-5 "
     "stage's ring-name work (not bisected)"),
    # --- Round 5 (N7): numbering. P-14.4 (pdf pp. 74-75) ranks (c) suffixes
    # and free valences, (d) added hydrogen, then (e)(i) 'hydro/dehydro
    # prefixes ... and ene and yne endings', all before detachable prefixes.
    # A hydro-named parent's orientations carried no hydro locants to the
    # preference key, so they tied and the first enumerated won.
    ("D-092a", "OC(=O)C1=CCNCC1", "1,2,3,6-tetrahydropyridine-4-carboxylic acid",
     "1,2,5,6-tetrahydropyridine-4-carboxylic acid", "derived, P-14.4 (e)(i): the "
     "acid is at 4 either way, so the hydro set decides"),
    ("D-092b", "CN1CCC(=CC1)c1ccccc1", "1-methyl-4-phenyl-1,2,3,6-tetrahydropyridine",
     "1-methyl-4-phenyl-1,2,5,6-tetrahydropyridine", "derived, as D-092a: hydro "
     "prefixes before the detachable ones (MPTP)"),
    ("D-092c", "OC(=O)CN1CC=CC=C1", "(pyridin-1(2H)-yl)acetic acid",
     "(1,6-dihydropyridin-1-yl)acetic acid", "'pyridin-1(2H)-yl (preferred prefix)' "
     "(p. 479). Round 4 put this on the free valence missing from the key; the "
     "candidate was generated all along and lost a tie"),
    ("D-092d", "OC(=O)CN1CC=CC(Cl)=C1", "(5-chloropyridin-1(2H)-yl)acetic acid",
     "(3-chloro-1,6-dihydropyridin-1-yl)acetic acid", "derived: P-14.4 (d), the "
     "added hydrogen's 2H before the chlorine's 3"),
    ("D-092e", "OC1=CCCNC1", "1,2,5,6-tetrahydropyridin-3-ol",
     "1,2,5,6-tetrahydropyridin-3-ol", "converse: P-14.4 (c), the suffix's 3 before "
     "the hydro set"),
    ("D-092f", "C1=CCNCC1", "1,2,3,6-tetrahydropyridine", "1,2,3,6-tetrahydropyridine",
     "control"),
    ("D-092g", "OC(=O)CN1C=CC=C(Cl)C1", "(3-chloropyridin-1(2H)-yl)acetic acid",
     "(3-chloropyridin-1(2H)-yl)acetic acid", "control: 2H and the 3-chloro agree"),
    ("D-089y", "CP(=O)(O)OP(C)(=O)O",
     "hydroxy{[hydroxy(methyl)(oxo)phosphanyl]oxy}(methyl)(oxo)phosphane",
     "(hydroxy){[(hydroxy)(methyl)(oxo)phosphanyl]oxy}(methyl)(oxo)phosphane",
     "converse, NOT a PIN: a P(V) is not a standard-valence a-term atom, so no "
     "'dioxodiphosphoxane' -- measured on a nucleotide diphosphate before the guard"),
]

# Targets the book prints that OPSIN cannot parse, so the OPSIN half of this
# table (tests/vendor/iupac_namer/test_known_defects.py) cannot check them by
# parsing. It asserts the parse still FAILS instead: the day OPSIN reads one,
# that test goes red and the entry has to come out. The app shows such a name
# marked unverified (`RoundTrip.PARSER_FAILED`); it withheld it until round 5.
OPSIN_CANNOT_PARSE: dict[str, str] = {
    "D-089e": "OPSIN reads no numbered N locant on oxamide; the book prints "
              "'N1,N2-bis(cyanomethyl)oxamide (PIN)' (p. 653)",
}

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
OPEN: list[tuple[str, str, str, str, str]] = [
    # Round 5 (N3): NOT wrong molecules -- ring systems whose fusion PIN needs
    # a construction general fusion does not build yet. The book's PIN is the
    # target; the second column is today's output (a von Baeyer name, or none
    # where that construction fails too).
    ("D-086a", "c1cc2cc3cocc3cc2o1", "benzo[1,2-b:4,5-c']difuran",
     "[NAMING ERROR: No valid naming plan found for c1cc2cc3cocc3cc2o1]",
     "a multiparent name (P-25.3.4.1.3, p. 234)"),
    ("D-086b", "C1=CC2=c3ccncc3=NC2=C1", "cyclopenta[4,5]pyrrolo[2,3-c]pyridine",
     "2,5-diazatricyclo[7.3.0.0^{3,8}]dodeca-1(12),2,4,6,8,10-hexaene",
     "a second-order attached component (p. 239)"),
    ("D-086c", "C1=CC2=CC=C3C=CCC4=C3N2C(=C1)C=C4", "6H-quinolizino[3,4,5,6-ija]quinoline",
     "13-azatetracyclo[10.2.2.0^{5,14}.0^{8,13}]hexadeca-1(15),2,5(14),6,8,10,12(16)-heptaene",
     "an interior heteroatom, P-25.3.3.2 (p. 223)"),
    # Round 5 (N4): NOT wrong molecules either -- each round-trips today; the
    # book prints the target (or it is derived, as marked).
    ("D-088a", "O=C(NNC(=O)c1ccccc1)c1ccccc1", "N'-benzoylbenzohydrazide",
     "1,2-dibenzoylhydrazine", "'N'-benzoylbenzohydrazide (PIN) (not "
     "1,2-dibenzoylhydrazine)' (p. 670). Admitting an acylated N' to the hydrazide "
     "pattern reaches it, but turned 4-(2-benzoylhydrazinyl)-4-oxobutanoic acid into "
     "a butanedioyl name: the demoted, prefix form is not built"),
    ("D-088b", "CCOC(=O)NN", "ethyl hydrazinecarboxylate", "(ethoxycarbonyl)hydrazine",
     "the ester of hydrazinecarboxylic acid; its anion is not nameable yet "
     "('oxidooxomethylhydrazine'), so no ester plan is offered"),
    ("D-088c", "O=C(N=Nc1ccccc1)N=Nc1ccccc1", "bis(phenyldiazenyl)methanone",
     "1-[(oxo)(phenyldiazenyl)methyl]-2-phenyldiazene",
     "p. 110: a C=O between two N= is not perceived as a ketone"),
    ("D-088d", "O=C(NNC)c1ccc(C(=O)O)cc1", "4-(2-methylhydrazine-1-carbonyl)benzoic acid",
     "4-carboxy-N'-methylbenzohydrazide",
     "derived from 'hydrazinecarbonyl (preferred prefix)' (p. 668): the acid is the "
     "principal group, but a substituted hydrazide has no prefix form (before N4 too)"),
    ("D-088f", "CN(C)ON(C)C", "N,N'-oxybis(N-methylmethanamine)",
     "{[(dimethylamino)oxy](methyl)amino}methane", "p. 108: no marker reads this "
     "unit's attachment N -- methyl and ethyl take over the parent, chloro and bromo "
     "are named '[chloro(methyl)amino]methane'"),
    ("D-088h", "Oc1ccc(OCC(C)COc2ccc(O)cc2)cc1",
     "4,4'-[(2-methylpropane-1,3-diyl)bis(oxy)]diphenol",
     "4-{[3-(4-hydroxyphenoxy)-2-methylpropyl]oxy}phenol",
     "p. 105: a substituted linker (P-15.3.1.2.1.2) is outside the built class"),
    ("D-088i", "[SiH3]c1cc([SiH3])cc([SiH3])c1", "(benzene-1,3,5-triyl)tris(silane)",
     "[3,5-bis(silyl)phenyl]silane", "p. 107: a ring as the central group is not built"),
    ("D-088j", "OC(=O)c1ccc(CC(c2ccc(C(O)=O)cc2)c2ccc(C(O)=O)cc2)cc1",
     "4,4',4''-(ethane-1,1,2-triyl)tribenzoic acid",
     "4-[1,2-bis(4-carboxyphenyl)ethyl]benzoic acid",
     "p. 110: an unsymmetrical central group (P-15.3.3.1) is not built"),
    # Round 5 (N5): each round-trips today.
    # Round 5 (N6), still open:
    ("D-091t", "NC(=O)NC(=O)NC(N)=O", "2,4-diimidotricarbonic diamide",
     "N-(carbamoylcarbamoyl)urea", "p. 662: condensed ureas are imidopolycarbonic diamides; "
     "not built"),
    ("D-091u", "CC(=O)NC(=O)c1ccccc1", "N-acetylbenzamide", "N-benzoylacetamide",
     "p. 654, verbatim: of two acyls on one N only one amide is perceived, so the "
     "senior one (ring before chain) is never offered as the parent"),
    ("D-091v", "CCN=C(N(C)C)c1ccc(C(=O)O)cc1",
     "4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid",
     "4-[(dimethylamino)(ethylimino)methyl]benzoic acid", "p. 676, verbatim; today's "
     "name is the book's second (general) form -- before N6 it was a wrong molecule, "
     "'4-(carbamimidoylmethyl)benzoic acid'"),
    ("D-089s", "C[Si](C)(O)O[Si](C)(C)O", "1,1,3,3-tetramethyldisiloxane-1,3-diol",
     "1,3-dihydroxy-1,1,3,3-tetramethyldisiloxane", "derived: -ol on a silicon parent "
     "(P-68.2.5); silanols reach a suffix only by a pre-plan route (N6)"),
    ("D-089u", "[SiH3]N[SiH3]", "N-silylsilanamine", "disilaazane",
     "p. 145, verbatim '(not disilazane)': with N the a(ba)n rule gives way to amine "
     "names; the organometallic chain route still builds it"),
    ("D-090b", "C[SiH2]O[SiH2]O[SiH3]", "1-methyltrisiloxane", "2,4-dioxa-1,3,5-trisilahexane",
     "derived: '-SiH2-O-SiH2-, disiloxane-1,3-diyl' is ONE heterounit (p. 440), so "
     "P-51.4.1's four are not reached; the skeletal-replacement count predates N5"),
    ("D-089v", "CCOP(=O)(C#N)N(C)C", "ethyl N,N-dimethylphosphoramidocyanidate",
     "(dimethylamino)(ethoxy)(oxo)phosphanecarbonitrile", "derived from functional "
     "replacement (P-67.1.2.4, 'methylphosphonocyanatidic acid (PIN)', p. 704); was "
     "'tabun', which the book never prints (gated, N5)"),
]

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
