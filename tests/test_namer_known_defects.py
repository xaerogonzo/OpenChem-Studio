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
    # (pdf p. 652). Expected moved AGAIN in round 9 (item "peptide-acyl-
    # naming", D-135): Ala-Phe is a plain dipeptide between two of the 20
    # proteinogenic amino acids, so P-103.2.5/P-103.3.2's retained "-yl"
    # acyl form now fires and supersedes the systematic substitutive form
    # entirely -- round 4's fix picked the best available STYLE within
    # substitutive naming, before the retained convention existed in this
    # engine at all; "alanylphenylalanine" outranks it, not merely differs
    # from it (P-103.2.5 is prescriptive, not a style preference).
    ("D-027z", "N[C@@H](C)C(=O)N[C@@H](Cc1ccccc1)C(=O)O",
     "alanylphenylalanine",
     "(2S)-2-[(2S)-2-aminopropanoylamino]-3-phenylpropanoic acid",
     "superseded by the peptide-acyl retained form, round 9"),

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
    ("D-051d", "CC(C)=NOC", "N-methoxypropan-2-imine", "2-(methyloxyimino)propane",
     "an O-alkyl oxime. Round 8 (D-124): the 'methyloxy' spelling this row first pinned, A9's, is the contracted 'methoxy' (P-63.2.2.2)"),
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
    ("D-054d", "COC(=O)c1ccc(cc1)S(=O)(=O)OC", "methyl 4-(methoxysulfonyl)benzoate",
     "methyl 4-(methyloxysulfonyl)benzoate",
     "converse: a carboxylic ester outranks a sulfonic one, as its acid does. Round 8 (D-124): 'methoxysulfonyl', where this row first pinned 'methyloxysulfonyl'"),
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
    ("D-075f", "O=C(NNC(=O)c1ccccc1)c1ccccc1", "N'-benzoylbenzohydrazide",
     "1,2-dibenzoylhydrazine",
     "p. 670 verbatim, and the CONTROL of round 5 REVERSED in round 8: 'letting an acylated N' into the hydrazide pattern named 1,2-dibenzoylhydrazine-1,2-dicarbohydrazide, a different "
     "molecule' was true of the pattern alone. It needs two more things, and they are D-117: the hydrazide is a prefix only when it attaches through its carbonyl carbon, and a lone "
     "locanted 'hydrazinyl' is printed bare. Same molecule as D-088a."),
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
    # --- Naming round 7 (R3): an acid anion beside another group, and the ownership hole. ---
    # The panel (benchmarks/naming/charged_panel.toml, frozen) is the source of every target and of every
    # `former`; each row is a panel row. A carboxylate or sulfonate beside a neutral OH/NH2/SH, another acid,
    # or a nitro group had NO owning route (classifier deferred to plan search, plan search excluded it as
    # 'handled by the classifier'), so the charge fell to an 'oxido' prefix on the wrong parent.
    ("D-095a", "CC(O)C(=O)[O-]", "2-hydroxypropanoate", "1-oxido-1-oxopropan-2-ol",
     "panel A1-lactate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 2-hydroxypropanoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095b", "OCC(=O)[O-]", "hydroxyacetate", "2-oxido-2-oxoethan-1-ol",
     "panel A1-glycolate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on hydroxyacetic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095c", "OC(c1ccccc1)C(=O)[O-]", "hydroxy(phenyl)acetate", "2-oxido-2-oxo-1-phenylethan-1-ol",
     "panel A1-mandelate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on hydroxy(phenyl)acetic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095d", "Oc1ccccc1C(=O)[O-]", "2-hydroxybenzoate", "2-oxidooxomethylphenol",
     "panel A1-salicylate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 2-hydroxybenzoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095e", "Oc1cccc(c1)C(=O)[O-]", "3-hydroxybenzoate", "3-oxidooxomethylphenol",
     "panel A1-3-hydroxybenzoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 3-hydroxybenzoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095f", "Oc1ccc(cc1)C(=O)[O-]", "4-hydroxybenzoate", "4-oxidooxomethylphenol",
     "panel A1-4-hydroxybenzoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 4-hydroxybenzoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095g", "CC(O)CC(=O)[O-]", "3-hydroxybutanoate", "4-oxido-4-oxobutan-2-ol",
     "panel A1-3-hydroxybutanoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 3-hydroxybutanoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095h", "OCCCC(=O)[O-]", "4-hydroxybutanoate", "4-oxido-4-oxobutan-1-ol",
     "panel A1-4-hydroxybutanoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 4-hydroxybutanoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095i", "OCC(O)C(O)C(O)C(O)C(=O)[O-]", "2,3,4,5,6-pentahydroxyhexanoate", "6-oxido-6-oxohexane-1,2,3,4,5-pentol",
     "panel A1-gluconate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 2,3,4,5,6-pentahydroxyhexanoic acid (PIN, stereodescriptors omitted); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095j", "Nc1ccc(cc1)C(=O)[O-]", "4-aminobenzoate", "4-oxidooxomethylaniline",
     "panel A2-4-aminobenzoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 4-aminobenzoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095k", "Nc1ccccc1C(=O)[O-]", "2-aminobenzoate", "2-oxidooxomethylaniline",
     "panel A2-anthranilate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 2-aminobenzoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095l", "NCCC(=O)[O-]", "3-aminopropanoate", "3-oxido-3-oxopropan-1-amine",
     "panel A2-3-aminopropanoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 3-aminopropanoic acid (PIN); P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095m", "SCCC(=O)[O-]", "3-sulfanylpropanoate", "3-oxido-3-oxopropane-1-thiol",
     "panel A3-3-sulfanylpropanoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 3-sulfanylpropanoic acid (PIN)"),
    ("D-095n", "SCC(=O)[O-]", "sulfanylacetate", "2-oxido-2-oxoethane-1-thiol",
     "panel A3-sulfanylacetate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on sulfanylacetic acid (PIN)"),
    ("D-095o", "[O-]C(=O)c1ccc(cc1)[N+](=O)[O-]", "4-nitrobenzoate", "1-nitro-4-oxidooxomethylbenzene",
     "panel A0-4-nitrobenzoate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 4-nitrobenzoic acid (PIN)"),
    ("D-095p", "OC(=O)CCCCC(=O)[O-]", "5-carboxypentanoate", "6-oxido-6-oxohexanoic acid",
     "panel A4-5-carboxypentanoate (PRINTED): P-72.2.2.2.1.2 (pdf p. 808): '5-carboxypentanoate (PIN)'"),
    ("D-095q", "OC(=O)CCC(=O)[O-]", "3-carboxypropanoate", "4-oxido-4-oxobutanoic acid",
     "panel A4-3-carboxypropanoate (PRINTED): P-65.6.2 (pdf p. 619): 'ammonium 3-carboxypropanoate (PIN)'"),
    ("D-095r", "OC(=O)CC(O)C(=O)[O-]", "3-carboxy-2-hydroxypropanoate", "3-hydroxy-4-oxido-4-oxobutanoic acid",
     "panel A4-3-carboxy-2-hydroxypropanoate (DERIVED): P-72.2.2.2.1.2 (pdf p. 808): a neutral acid group on an anion is a 'carboxy' prefix, an ester an 'alkoxy...oxo' prefix, a hydroxy group 'hydroxy' on the mono-anion of 2-hydroxybutanedioic acid"),
    ("D-095s", "OC(=O)c1ccccc1C(=O)[O-]", "2-carboxybenzoate", "2-oxidooxomethylbenzoic acid",
     "panel A4-2-carboxybenzoate (DERIVED): P-72.2.2.2.1.2 (pdf p. 808): a neutral acid group on an anion is a 'carboxy' prefix, an ester an 'alkoxy...oxo' prefix, a hydroxy group 'hydroxy'"),
    ("D-095t", "CCOC(=O)CC(O)(CC(O)=O)C([O-])=O", "2-(carboxymethyl)-4-ethoxy-2-hydroxy-4-oxobutanoate", "5-ethoxy-3-hydroxy-3-oxidooxomethyl-5-oxopentanoic acid",
     "panel A5-citrate-diester-anion (PRINTED): P-72.2.2.2.1.2 (pdf p. 808): '2-(carboxymethyl)-4-ethoxy-2-hydroxy-4-oxobutanoate (PIN)'"),
    ("D-095u", "[O-]C(=O)CC(O)C([O-])=O", "2-hydroxybutanedioate", "1,4-dioxido-1,4-dioxobutan-2-ol",
     "panel A6-2-hydroxybutanedioate-dianion (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on 2-hydroxybutanedioic acid (PIN)"),
    ("D-095v", "Oc1ccccc1S(=O)(=O)[O-]", "2-hydroxybenzene-1-sulfonate", "2-(oxidosulfonyl)phenol",
     "panel B1-2-hydroxybenzenesulfonate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on the sulfonic acid's PIN; P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095w", "Nc1ccc(cc1)S(=O)(=O)[O-]", "4-aminobenzene-1-sulfonate", "4-(oxidosulfonyl)aniline",
     "panel B1-sulfanilate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on the sulfonic acid's PIN; P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095x", "NCCS(=O)(=O)[O-]", "2-aminoethane-1-sulfonate", "2-(oxidosulfonyl)ethan-1-amine",
     "panel B1-taurinate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on the sulfonic acid's PIN; P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095y", "OCCS(=O)(=O)[O-]", "2-hydroxyethane-1-sulfonate", "2-(oxidosulfonyl)ethan-1-ol",
     "panel B1-isethionate (DERIVED): P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate' on the sulfonic acid's PIN; P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7)"),
    ("D-095z", "[O-]C(=O)c1ccc(cc1)S(O)(=O)=O", "4-sulfobenzoate", "4-oxidooxomethylbenzene-1-sulfonic acid",
     "panel B4-4-sulfobenzoate (DERIVED): P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7); the deprotonated group takes the ending, the neutral acid becomes a prefix"),
    ("D-095aa", "OC(=O)c1ccc(cc1)S(=O)(=O)[O-]", "4-carboxybenzene-1-sulfonate", "4-(oxidosulfonyl)benzoic acid",
     "panel B4-4-carboxybenzenesulfonate (DERIVED): P-41 Table 4.1 (pdf p. 360): anions (class 4) rank above zwitterions (5), cations (6) and acids (7); here the SULFONATE is the anion although the carboxylic acid is the senior neutral acid"),
    ("D-095ab", "[Na+].Oc1ccccc1C(=O)[O-]", "sodium 2-hydroxybenzoate", "sodium 2-oxidooxomethylphenol",
     "panel G0-sodium-salicylate (DERIVED): P-65.6.2 (pdf pp. 618-619): the cation's name, a space, the anion's name (method 1); P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate'"),
    ("D-095ac", "[Na+].CC(O)C(=O)[O-]", "sodium 2-hydroxypropanoate", "sodium 1-oxido-1-oxopropan-2-ol",
     "panel G0-sodium-lactate (DERIVED): P-65.6.2 (pdf pp. 618-619): the cation's name, a space, the anion's name (method 1); P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate'"),
    ("D-095ad", "[K+].OC(=O)CCC(=O)[O-]", "potassium 3-carboxypropanoate", "potassium 4-oxido-4-oxobutanoic acid",
     "panel G0-potassium-3-carboxypropanoate (DERIVED): P-65.6.2 (pdf p. 619): the printed 'ammonium 3-carboxypropanoate (PIN)' pattern"),
    ("D-095ae", "[Na+].Nc1ccc(cc1)S(=O)(=O)[O-]", "sodium 4-aminobenzene-1-sulfonate", "sodium 4-(oxidosulfonyl)aniline",
     "panel G0-sodium-4-aminobenzene-sulfonate (DERIVED): P-65.6.2 (pdf pp. 618-619): the cation's name, a space, the anion's name (method 1)"),
    ("D-095af", "C[N+](C)(C)CCO.Oc1ccccc1C(=O)[O-]", "2-hydroxy-N,N,N-trimethylethan-1-aminium 2-hydroxybenzoate", "2-hydroxy-N,N,N-trimethylethan-1-aminium 2-oxidooxomethylphenol",
     "panel G1-choline-salicylate (DERIVED): P-65.6.2 (pdf pp. 618-619): the cation's name, a space, the anion's name (method 1); cations are cited before anions; P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate'"),
    ("D-095ag", "C[N+](C)(C)CCO.CC(O)C(=O)[O-]", "2-hydroxy-N,N,N-trimethylethan-1-aminium 2-hydroxypropanoate", "2-hydroxy-N,N,N-trimethylethan-1-aminium 1-oxido-1-oxopropan-2-ol",
     "panel G1-choline-lactate (DERIVED): P-65.6.2 (pdf pp. 618-619): the cation's name, a space, the anion's name (method 1); cations are cited before anions; P-72.2.2.2.1.1 (pdf p. 807): the 'ic acid' ending of the acid's PIN becomes 'ate'"),
    ("D-095ah", "CC(=O)[O-]", "acetate", "acetate",
     "control, the pure carboxylate: the classifier still owns it (panel A0-acetate)"),
    ("D-095ai", "[O-]C(=O)c1ccccc1", "benzoate", "benzoate",
     "control, a pure aromatic carboxylate (panel A0-benzoate)"),
    ("D-095aj", "ClCC(=O)[O-]", "chloroacetate", "chloroacetate",
     "control, a substituent with no O/N/S-H: never deferred, must not be re-routed (panel A0-chloroacetate)"),
    ("D-095ak", "COc1ccc(cc1)C(=O)[O-]", "4-methoxybenzoate", "4-methoxybenzoate",
     "control, an ether O has no H: the same secondary-group family as OH, and unchanged (panel A0-4-methoxybenzoate)"),
    ("D-095al", "Cc1ccc(cc1)S(=O)(=O)[O-]", "4-methylbenzene-1-sulfonate", "4-methylbenzene-1-sulfonate",
     "control, a pure sulfonate with an alkyl group (panel B0-tosylate)"),
    ("D-095am", "CS(=O)(=O)[O-]", "methanesulfonate", "methanesulfonate",
     "control, a pure aliphatic sulfonate (panel B0-mesylate)"),
    ("D-095an", "OCC[O-]", "2-hydroxyethan-1-olate", "2-hydroxyethan-1-olate",
     "control, the OLATE cascade: an alkoxide beside a neutral OH is owned by the carved route, which this round must not disturb (panel C1-2-hydroxyethan-1-olate)"),
    ("D-095ao", "[S-]c1ccccc1S", "2-sulfanylbenzene-1-thiolate", "2-sulfanylbenzene-1-thiolate",
     "control, as above, a thiolate beside a neutral SH (panel C2-2-sulfanylbenzene-1-thiolate)"),
    ("D-095ap", "[NH3+]CC([O-])=O", "azaniumylacetate", "azaniumylacetate",
     "control, a carboxylate beside a CATION is a zwitterion, owned by the FG route; the acid-anion decision function must return None for it and leave it alone (panel E0-glycine-zwitterion)"),
    ("D-095aq", "[Na+].CC(=O)[O-]", "sodium acetate", "sodium acetate",
     "control, the salt path with a pure carboxylate (panel G0-sodium-acetate)"),
    ("D-095ar", "[Na+].[O-]S(=O)(=O)c1ccccc1", "sodium benzenesulfonate", "sodium benzenesulfonate",
     "control, the salt path with a pure sulfonate (panel G0-sodium-benzenesulfonate)"),
    ("D-095as", "NC(=O)CCC(=O)[O-]", "4-amino-4-oxobutanoate", "4-oxido-4-oxobutanamide",
     "panel A5-3-carbamoylpropanoate (DERIVED, erratum 2): P-72.2.2.2.1.1 on '4-amino-4-oxobutanoic "
     "acid (PIN)', pdf p. 593, where '3-carbamoylpropanoic acid' is printed as a NON-PIN alternative"),
    # --- Naming round 7 (R4a): the charge ledger. A route that OWNS a site can still get the charge wrong. ---
    ("D-096a", "[NH3+]C(CCC(O)=O)C([O-])=O", "2-azaniumyl-4-carboxybutanoate", "2-azaniumylpentanedioate",
     "a WRONG MOLECULE before: one deprotonated carboxylate and one NEUTRAL COOH were both rendered as anion "
     "suffixes (the name is the dianion). DERIVED, not printed: P-72.2.2.2.1.2 (pdf p. 808) makes a neutral acid "
     "on an anion a 'carboxy' prefix (printed '5-carboxypentanoate'), and P-74 (pdf p. 1048) puts the cation "
     "on the anionic parent as 'azaniumyl' (printed 'azaniumylacetate'); prefixes in ALPHABETICAL order, so "
     "azaniumyl precedes carboxy (the first draft of this row had them the other way round, an error of "
     "the row and not of the engine). Panel E2-glutamate-monoanion"),
    ("D-096b", "[NH3+]C(CCC([O-])=O)C([O-])=O", "2-azaniumylpentanedioate",
     "(1,5-dioxido-1,5-dioxopentan-2-yl)azanium",
     "a NET-NEGATIVE zwitterion (glutamate as drawn at pH 7: two carboxylates, one ammonium) had NO owning "
     "route: FG perception detects a charged carboxylic acid only when the net charge is zero, and the "
     "classifier declines any genuine cation, so the charge fell to 'oxido' prefixes on an azanium parent. "
     "DERIVED: both carboxyl groups are deprotonated ('dioate'), the cation is the 'azaniumyl' prefix "
     "(P-74, printed 'azaniumylacetate', pdf p. 1048). Found after the panel was frozen: logged R7-UNPLANNED"),
    ("D-096c", "[NH3+]CC([O-])=O", "azaniumylacetate", "azaniumylacetate",
     "converse: net charge zero, the FG route owns it (glycine zwitterion, printed pdf p. 1048)"),
    ("D-096d", "[NH3+]CCC([O-])=O", "3-azaniumylpropanoate", "3-azaniumylpropanoate",
     "converse: a longer chain, same route, same shape as D-096c"),
    ("D-096e", "[NH3+]C(CC(=O)[O-])C([O-])=O", "2-azaniumylbutanedioate",
     "(1,4-dioxido-1,4-dioxobutan-2-yl)azanium",
     "aspartate as drawn at pH 7, the same net-negative hole as D-096b, DERIVED the same way"),
    # --- Naming round 7 (R4b): the retained anion names the book prints (alkoxides, glycinate). ---
    # A retained NAME for a whole charged molecule belongs in the curated table detect() asks first, keyed by the
    # canonical SMILES; the chiral amino acids are NOT here because 'alaninate' asserts no configuration in the book
    # while OPSIN reads it as L, so they need a stereo policy first.
    ("D-097a", "C[O-]", "methoxide", "methanolate",
     "pdf p. 808, verbatim: 'methoxide (PIN)'"),
    ("D-097b", "CC[O-]", "ethoxide", "ethanolate",
     "pdf p. 808: 'methoxide, ethoxide, propoxide, butoxide, tert-butoxide, phenoxide ... are retained as preferred IUPAC names'"),
    ("D-097c", "CC(C)(C)[O-]", "tert-butoxide", "2-methylpropan-2-olate",
     "pdf p. 808, as D-097b; 'tert-Butoxide cannot be substituted'"),
    ("D-097d", "[O-]c1ccccc1", "phenoxide", "phenolate",
     "pdf p. 808, as D-097b: the book retains 'phenoxide' and does not print 'benzenolate' or 'phenolate'"),
    ("D-097e", "CCC[O-]", "propoxide", "propan-1-olate",
     "pdf p. 808, as D-097b (propoxide, not the isopropoxide the book rejects)"),
    ("D-097f", "CCCC[O-]", "butoxide", "butan-1-olate",
     "pdf p. 808, as D-097b"),
    ("D-097g", "NCC(=O)[O-]", "glycinate", "aminoacetate",
     "P-103.2.4.2 (pdf p. 1047), verbatim: 'H2N-CH2-COO- glycinate'. Glycine is achiral, so the retained name asserts no configuration"),
    ("D-097h", "[Na+].[O-]c1ccccc1", "sodium phenoxide", "sodium phenolate",
     "the salt of D-097d: the anion fragment reaches the same retained name"),
    ("D-097i", "[K+].CC(C)(C)[O-]", "potassium tert-butoxide", "potassium 2-methylpropan-2-olate",
     "the salt of D-097c"),
    ("D-097j", "[Na+].NCC(=O)[O-]", "sodium glycinate", "sodium aminoacetate",
     "the salt of D-097g"),
    ("D-097k", "CC(C)[O-]", "propan-2-olate", "propan-2-olate",
     "control, verbatim pdf p. 808: 'propan-2-olate (PIN)', and the book says isopropoxide is NOT retained as a PIN"),
    ("D-097l", "OCC[O-]", "2-hydroxyethan-1-olate", "2-hydroxyethan-1-olate",
     "control: an alkoxide beside a neutral OH is the carved-route cascade, a different SMILES from any retained entry"),
    ("D-097m", "NC(=O)[O-]", "carbamate", "carbamate",
     "control: the curated table's other whole-molecule anion, unchanged"),
    ("D-097n", "NCC(=O)O", "glycine", "glycine",
     "control: the neutral parent of D-097g keeps its retained name"),
    # --- Naming round 7 (R4c): identical organic anions in a salt take a multiplying prefix. ---
    # The salt path repeated the name ('calcium acetate acetate'). The collapse was deliberately narrow: 'disulfate' and
    # 'diphosphate' are different ions, and OPSIN misreads 'diphenylacetylide'. The book prints 'calcium diacetate (PIN)',
    # so identical ORGANIC '-ate' anions (no spaces, not an inorganic oxoanion) are multiplied: 'di' for a plain stem,
    # 'bis(...)' for a substituted one.
    ("D-098a", "[Ca+2].CC(=O)[O-].CC(=O)[O-]", "calcium diacetate", "calcium acetate acetate",
     "P-65.6.2 (pdf p. 618), verbatim: 'calcium diacetate (PIN)'"),
    ("D-098b", "[Al+3].CC(=O)[O-].CC(=O)[O-].CC(=O)[O-]", "aluminium triacetate", "aluminium acetate acetate acetate",
     "derived from the printed 'germanium tetraacetate (PIN)' (pdf p. 619)"),
    ("D-098c", "[Mg+2].[O-]C(=O)c1ccccc1.[O-]C(=O)c1ccccc1", "magnesium dibenzoate", "magnesium benzoate benzoate",
     "derived: as D-098a with an unsubstituted retained stem"),
    ("D-098d", "[Ca+2].OCC(O)C(O)C(O)C(O)C(=O)[O-].OCC(O)C(O)C(O)C(O)C(=O)[O-]", "calcium bis(2,3,4,5,6-pentahydroxyhexanoate)", "calcium 2,3,4,5,6-pentahydroxyhexanoate 2,3,4,5,6-pentahydroxyhexanoate",
     "derived: a SUBSTITUTED anion takes bis/tris, as the printed 'antimony tris(3-carboxypropanoate)' (pdf p. 619)"),
    ("D-098e", "[Ca+2].CC(O)C(=O)[O-].CC(O)C(=O)[O-]", "calcium bis(2-hydroxypropanoate)", "calcium 2-hydroxypropanoate 2-hydroxypropanoate",
     "as D-098d"),
    ("D-098f", "[Na+].CC(=O)[O-]", "sodium acetate", "sodium acetate",
     "control: ONE anion is not multiplied"),
    ("D-098g", "[Ca+2].[Cl-].[Cl-]", "calcium dichloride", "calcium dichloride",
     "control: the simple '-ide' path that already multiplied is untouched"),
    ("D-098h", "[Na+].[Na+].[O-]C(=O)CCC([O-])=O", "disodium butanedioate", "disodium butanedioate",
     "control: two cations and ONE dianion: the cation collapse is separate and unchanged"),
    ("D-098i", "[Na+].[Na+].[O-]S(=O)(=O)[O-]", "disodium sulfate", "disodium sulfate",
     "control: an INORGANIC oxoanion is never multiplied into a 'di'-prefixed anion ('disulfate' is a different ion)"),
    # --- Naming round 7 (R4d): an amide anion is an acyl group on the parent anion 'azanide', not '-amide'. ---
    # The renderer's docstring recorded why it emitted '{acyl}amide': the '-amidide' promotion was not OPSIN-parseable.
    # The book's method (2) uses the preselected anionic parent instead, and OPSIN reads every '{acyl}azanide' form.
    ("D-099a", "CC(=O)[NH-]", "acetylazanide", "acetylamide",
     "pdf p. 810, verbatim: 'acetylazanide (PIN)'; P-72.2.2.2 (pdf p. 807): amides are not named by the '-aminide' method, and 'the use of parents azanide and azanediide eliminates all possible ambiguity'"),
    ("D-099b", "O=C([NH-])c1ccccc1", "benzoylazanide", "benzoylamide",
     "derived from D-099a: the acyl group on the parent anion 'azanide'"),
    ("D-099c", "O=C[NH-]", "formylazanide", "formylamide",
     "derived from D-099a"),
    ("D-099d", "CCC(=O)[NH-]", "propanoylazanide", "propanoylamide",
     "derived from D-099a"),
    ("D-099g", "Cc1ccc(cc1)C(=O)[NH-]", "(4-methylbenzoyl)azanide", "4-methylbenzoylamide",
     "derived from D-099a: a COMPOUND acyl name (one carrying a locant) is enclosed, as any compound prefix is"),
    ("D-099e", "C[NH-]", "methanaminide", "methanaminide",
     "control, verbatim pdf p. 805: an AMINE anion takes '-aminide'; only AMIDE anions take the azanide parent"),
    ("D-099f", "CC(N)=O", "acetamide", "acetamide",
     "control: the neutral amide is unaffected"),
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
    ("D-091e", "NC(=O)NC(=O)NC(N)=O", "2,4-diimidotricarbonic diamide",
     "N-(carbamoylcarbamoyl)urea", "was a control for the NON-PIN name while D-091t was open (the new urea group and an "
     "amide both claimed the shared N until the amide was made to subsume it); naming round 8 built the printed PIN "
     "(p. 663), so the control now pins the PIN and the ownership point stands: one route owns the shared nitrogen"),
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
    # ---- naming round 8, W1: three or more C-anchored suffix groups on one chain (P-65.1.2.2.1). The fixes are in OPEN
    # below until the engine offers the skeleton chain; these are the CONVERSES, which pass today and must not move
    # (each differs from a fix by a REASON, not by another molecule of the same shape).
    ("D-100r", "OC(=O)CCC(O)=O", "butanedioic acid", "(unchanged)",
     "converse: TWO terminal acid groups are one dioic chain (P-65.1.2.1); the new rule needs MORE than two"),
    ("D-100s", "OC(=O)CCCC(O)=O", "pentanedioic acid", "(unchanged)", "converse: two groups, longer chain"),
    ("D-100t", "OC(=O)C(O)C(O)C(O)=O", "2,3-dihydroxybutanedioic acid", "(unchanged)",
     "converse, p. 578 verbatim: two groups with substituents"),
    ("D-100u", "OC(=O)c1ccc(C(O)=O)c(C(O)=O)c1", "benzene-1,2,4-tricarboxylic acid", "(unchanged)",
     "converse, p. 95 verbatim: a RING already counts its exocyclic acids"),
    ("D-100v", "OC(=O)C1CC(C(O)=O)CC(C1)C(O)=O", "cyclohexane-1,3,5-tricarboxylic acid", "(unchanged)",
     "converse: the saturated ring analogue, a ring parent throughout"),
    ("D-100w", "OC(=O)CCC(C(O)=O)c1ccc(cc1)C(O)=O", "2-(4-carboxyphenyl)pentanedioic acid", "(unchanged)",
     "converse, an EARLIER rule: three acids, but only two on the chain; the third is on a ring, so no one chain "
     "carries all three and the skeleton candidate must not exist"),
    ("D-100x", "OC(=O)CCC(O)(CCC(O)=O)CCC(O)=O", "4-(2-carboxyethyl)-4-hydroxyheptanedioic acid", "(unchanged)",
     "converse: three acids on THREE arms of a branched skeleton; no single path reaches all three attachment carbons"),
    ("D-100y", "N#CCC(C#N)(CC#N)CCC(O)=O", "4,5-dicyano-4-(cyanomethyl)pentanoic acid", "(unchanged)",
     "converse, an EARLIER rule (P-41): three nitriles beside a carboxylic acid; the acid is the senior class, so a "
     "tricarbonitrile parent must LOSE however many suffix groups it would carry"),
    ("D-100z", "N#CCC(CC#N)C(N)=O", "3-cyano-2-(cyanomethyl)propanamide", "(unchanged)",
     "converse, an EARLIER rule: two nitriles and one amide; the amide is senior, so the count of nitriles never "
     "decides"),
    # (moved from OPEN when the exo-skeleton candidate landed: each was red before, with the names in the 'former' column)
    # ---- naming round 8, W1 (P-65.1.2.2.1, pdf p. 579: an unbranched chain linked to MORE THAN TWO carboxy groups names
    # ALL of them 'carboxylic acid', and P-44.1.1, p. 374: the parent with the maximum number of principal groups).
    # Traced: the skeleton chain that excludes every acid carbon is never a CANDIDATE, so the pcg_count tier never sees
    # a parent with three suffix groups. Each row is red before and green after the candidate is offered.
    ("D-100a", "OC(=O)CC(O)(CC(O)=O)C(O)=O", "2-hydroxypropane-1,2,3-tricarboxylic acid",
     "3-carboxy-3-hydroxypentanedioic acid", "p. 578 verbatim, the PIN of citric acid"),
    ("D-100b", "OC(=O)CCC(C(O)=O)CCC(O)=O", "pentane-1,3,5-tricarboxylic acid",
     "4-carboxyheptanedioic acid", "p. 579 verbatim: three groups, two of them on chain ends a longer diacid could absorb"),
    ("D-100c", "OC(=O)C(C(O)=O)C(C(O)=O)C(O)=O", "ethane-1,1,2,2-tetracarboxylic acid",
     "2,3-dicarboxybutanedioic acid", "p. 579 verbatim: four groups on a two-carbon parent"),
    ("D-100d", "OC(=O)CC(CC(O)=O)C(O)=O", "propane-1,2,3-tricarboxylic acid",
     "3-carboxypentanedioic acid", "derived from p. 579 (its anion is printed in a salt name on p. 619)"),
    ("D-100e", "OC(=O)C(C(O)=O)C(O)=O", "methanetricarboxylic acid",
     "carboxypropanedioic acid", "derived from p. 579: the one-carbon parent of the same rule"),
    ("D-100f", "OC(C(O)=O)C(C(O)=O)C(=O)C(O)=O", "1-hydroxy-3-oxopropane-1,2,3-tricarboxylic acid",
     "3-carboxy-2-hydroxy-4-oxopentanedioic acid", "p. 582 verbatim: three groups AND two prefixes, so the parent and "
     "its numbering are separate failures"),
    ("D-100g", "NC(=O)CC(CC(N)=O)C(N)=O", "propane-1,2,3-tricarboxamide",
     "3-carbamoylpentanediamide", "p. 645 verbatim: the same count rule for amides"),
    ("D-100h", "CCCC(C#N)(C#N)C#N", "butane-1,1,1-tricarbonitrile",
     "2,2-dicyanopentanenitrile", "p. 686 verbatim: the same count rule for nitriles"),
    ("D-100i", "O=CCC(C=O)CCC=O", "butane-1,2,4-tricarbaldehyde",
     "3-formylhexanedial", "p. 691 verbatim: the same count rule for aldehydes, where a longer dial chain exists"),
    ("D-100j", "COC(=O)C(C(=O)OC)CC(C)C(=O)OC", "trimethyl butane-1,1,3-tricarboxylate",
     "methyl 5-methoxy-4-(methoxycarbonyl)-2-methyl-5-oxopentanoate", "p. 623 verbatim: the same rule through the "
     "functional-class ester, which reads the parent acid's name"),
    ("D-100k", "OC(=O)CC(C)(CC(O)=O)C(O)=O", "2-methylpropane-1,2,3-tricarboxylic acid",
     "3-carboxy-3-methylpentanedioic acid", "derived: a substituent on the unbranched skeleton does not stop it being "
     "an unbranched chain linked to three carboxy groups (P-65.1.2.2.1)"),
    ("D-100l", "N#CCC(CC#N)C#N", "propane-1,2,3-tricarbonitrile",
     "3-cyanopentane-1,5-dinitrile", "derived from p. 686: the tricarbonitrile of a three-carbon skeleton"),
    # ---- naming round 8, W1: the site-level charge ledger of the classifier route. On that route every acid group IS a
    # deprotonated site, so a NEUTRAL `carboxy` prefix in the name is a wrong charge; the book writes such a site as the
    # anionic prefix `carboxylato` (pdf p. 619: `2-(carboxylatomethyl)benzoate`). Former names measured on master.
    ("D-100m", "[O-]C(=O)CCC(C([O-])=O)c1ccc(cc1)C([O-])=O", "2-(4-carboxylatophenyl)pentanedioate",
     "2-(4-carboxyphenyl)pentanedioate", "derived (p. 619): three sites, two on the chain and one on a ring, so no "
     "chain candidate can carry all three; the name had two charges for three sites"),
    ("D-100n", "[O-]C(=O)Cc1ccccc1C([O-])=O", "2-(carboxylatomethyl)benzoate",
     "2-(carboxymethyl)benzoate", "p. 619 verbatim as an anion part: the dianion had the SAME name as its mono-anion "
     "(D-100ab), one charge for two"),
    ("D-100o", "[O-]C(=O)CCC(O)(CCC([O-])=O)CCC([O-])=O", "4-(2-carboxylatoethyl)-4-hydroxyheptanedioate",
     "4-(2-carboxyethyl)-4-hydroxyheptanedioate", "derived (p. 619): three acids on THREE arms, where no exo-skeleton "
     "chain exists (D-100x); the ledger, not the candidate, is what balances it"),
    ("D-100p", "[Na+].[Na+].[Na+].[O-]C(=O)CCC(C([O-])=O)c1ccc(cc1)C([O-])=O",
     "trisodium 2-(4-carboxylatophenyl)pentanedioate", "trisodium 2-(4-carboxyphenyl)pentanedioate",
     "derived: the same trianion as a salt, so the ledger is exercised through the salt path too"),
    ("D-100q", "[O-]C(=O)CC(O)(CC([O-])=O)C([O-])=O", "2-hydroxypropane-1,2,3-tricarboxylate",
     "3-carboxy-3-hydroxypentanedioate", "derived (p. 578 + P-65.1.2.2.1): citrate's trianion, the round-7 finding; "
     "fixed by the exo-skeleton candidate, not by the ledger"),
    ("D-100aa", "[O-]C(=O)c1ccc(cc1)C([O-])=O", "benzene-1,4-dicarboxylate", "(unchanged)",
     "converse: two sites, both suffix positions of a ring parent; the ledger has nothing to convert"),
    ("D-100ab", "OC(=O)Cc1ccccc1C([O-])=O", "2-(carboxymethyl)benzoate", "(unchanged)",
     "converse, p. 619 verbatim: a mono-anion beside a NEUTRAL acid keeps `carboxy`; the carved route owns it, and "
     "the name that used to serve the dianion too is now only the mono-anion's"),
    ("D-100ac", "CC(=O)[O-]", "acetate", "(unchanged)",
     "converse: a retained parent has no suffix groups to count and no carboxy word to convert"),
    # ---- naming round 8, W5 (P-16.5.1.3.1, pdf p. 130): for a one-carbon parent the second and further simple prefixes are
    # each enclosed. CONVERSES first: they pass today and must not move.
    ("D-101x", "ClC(Cl)c1ccccc1", "(dichloromethyl)benzene", "(unchanged)",
     "converse: ONE prefix, multiplied, so there is no second prefix to enclose (the multiplier stays outside marks)"),
    ("D-101y", "OC(=O)C(Br)Cl", "bromo(chloro)acetic acid", "(unchanged)",
     "converse, p. 131 verbatim: a NAMED parent already encloses its second prefix"),
    ("D-101z", "N=C(S)Nc1ccccc1", "anilinomethanimidothioic acid", "(unchanged)",
     "converse: an isothiourea whose parent DOES survive as a suffix has no demoted prefix to write"),
    ("D-101w", "CCSC(=N)N(C)C", "1-(ethylsulfanyl)-N,N-dimethylmethanimidamide", "(unchanged)",
     "converse: p. 663's S-alkyl isothiourea, round-tripping today"),
    ("D-101v", "CC(Cl)c1ccccc1", "(1-chloroethyl)benzene", "(unchanged)",
     "converse: a TWO-carbon substituent group is not a mononuclear parent, and one prefix carries a locant"),
    # (moved from OPEN when the enclosure rule landed; each was red before, with the names in the 'former' column)
    # ---- naming round 8, W5: the one wrong structure of heldout_v4's final evaluation was an isothiourea whose demoted
    # prefix was written 'aminosulfanylmethylidene', which OPSIN reads as amino-SULFANYL (S-NH2): another molecule. The book
    # prints the prefix as '[amino(sulfanyl)methylidene]amino' (p. 663) by P-16.5.1.3.1 (p. 130). Measured layer: SERIALIZATION.
    ("D-101a", "CCN=C(N)S", "{[amino(sulfanyl)methylidene]amino}ethane",
     "[(aminosulfanylmethylidene)amino]ethane", "p. 663: the prefix H2N-C(SH)=N- is printed '[amino(sulfanyl)methylidene]amino'; "
     "the unenclosed form was a WRONG MOLECULE"),
    ("D-101b", "CN=C(S)NC", "{[(methylamino)(sulfanyl)methylidene]amino}methane",
     "[((methylamino)sulfanylmethylidene)amino]methane", "derived (p. 130): a compound first prefix keeps its own marks, "
     "the second is enclosed; the old name was a wrong molecule"),
    ("D-101d", "FC(Cl)c1ccccc1", "[chloro(fluoro)methyl]benzene",
     "(chlorofluoromethyl)benzene", "derived (p. 130, and the printed 'amino(sulfanylidene)methyl' of p. 663): the same rule on a "
     "substituent group; structurally right before, non-preferred"),
    ("D-101c", "CCOc1ccnc(CCN=C(S)Nc2ccc(Cl)cn2)c1F",
     "2-[2-({[(5-chloropyridin-2-yl)amino](sulfanyl)methylidene}amino)ethyl]-4-ethoxy-3-fluoropyridine",
     "2-{2-[([(5-chloropyridin-2-yl)amino]sulfanylmethylidene)amino]ethyl}-4-ethoxy-3-fluoropyridine",
     "THE heldout_v4 row (h4cid4750), red at r8-base as wrong_structure: the enclosure rule (p. 130) applied to the "
     "prefix, and the ylidene-amino wrapper now asks _choose_brackets so the marks nest ( [ { ( [ as P-16.5.4 says; the "
     "name round-trips MATCH. Not the PIN (that is a carbamimidothioic acid, p. 663): the parent construction is open"),
    ("D-101u", "FC(Cl)Br", "bromochlorofluoromethane", "(unchanged)",
     "converse, RECORDED OPEN and not a PIN: a three-prefix PARENT hydride. The rule text (p. 130) says the second and "
     "further prefixes are enclosed, and the book's own example on p. 873 prints 'bromo(chloro)fluoromethane' with the "
     "third bare; the book contradicts itself, so W5 is scoped to the SUBSTITUENT groups p. 663 prints and this stays put"),
    # ---- naming round 8, W2 (cation charge count): a NEUTRAL amine beside a ring cation is a PREFIX ('amino'), never the
    # '-aminium' suffix, which names a CHARGED nitrogen. CONVERSES first: they pass today and must not move.
    ("D-102v", "[NH3+]c1cccc[nH+]1", "pyridin-1-ium-2-aminium", "(unchanged)",
     "converse: the TRUE dication (ring N-H+ AND NH3+) keeps the aminium suffix; the guard is about a NEUTRAL amine N, not "
     "about amines"),
    ("D-102w", "[NH3+]c1ccccc1", "anilinium", "(unchanged)", "converse: the cation IS the amine, so aminium is right"),
    ("D-102x", "[NH3+]c1ccc(N)cc1", "4-aminoanilinium", "(unchanged)",
     "converse: a charged amine with a NEUTRAL amine beside it; the neutral one is the prefix, as it must be"),
    ("D-102y", "Cc1cccc[nH+]1", "2-methylpyridin-1-ium", "(unchanged)", "converse: a hydrocarbon prefix on a ring cation"),
    ("D-102z", "NCc1cccc[nH+]1", "2-(aminomethyl)pyridin-1-ium", "(unchanged)",
     "converse: an amine on a CARBON substituent was already a prefix"),
    # (moved from OPEN when the neutral-amine guard landed; each was red before, with the names in the 'former' column)
    # ---- naming round 8, W2: every protonated or alkylated aminopyridine was a WRONG MOLECULE. Cations outrank amines
    # (P-41, Table 4.1, pdf p. 360), so the ring cation is the parent and a NEUTRAL amino group is a prefix (P-73.1.1.2, pdf
    # p. 818: 1-methylpyridin-1-ium, with the printed 4-carboxy-1-methylpyridin-1-ium as the same construction on p. 580).
    # OPSIN reads 'pyridin-1-ium-2-aminium' as [NH+]1=C(C=CC=C1)[NH3+], a dication. Measured on master.
    ("D-102a", "Nc1cccc[nH+]1", "2-aminopyridin-1-ium", "pyridin-1-ium-2-aminium",
     "derived (p. 818 + P-41): the monocation of 2-aminopyridine; the old name was a dication"),
    ("D-102b", "Nc1ccc[nH+]c1", "3-aminopyridin-1-ium", "pyridin-1-ium-3-aminium", "derived: the 3-isomer"),
    ("D-102c", "Nc1cc[nH+]cc1", "4-aminopyridin-1-ium", "pyridin-1-ium-4-aminium", "derived: the 4-isomer"),
    ("D-102d", "CN(C)c1cc[nH+]cc1", "4-(dimethylamino)pyridin-1-ium", "N,N-dimethylpyridin-1-ium-4-aminium",
     "derived: protonated DMAP, a very common molecule; a compound prefix on the cation"),
    ("D-102e", "Nc1ccc[n+](C)c1", "3-amino-1-methylpyridin-1-ium", "1-methylpyridin-1-ium-3-aminium",
     "derived: an N-alkylated cation with a neutral amine, so the charge is not a protonation at all"),
    # ---- naming round 8, W2: the guanidinium renderer never enclosed a COMPOUND prefix. Converses first.
    ("D-103y", "CNC(N)=[NH2+]", "methylguanidinium", "(unchanged)", "converse: a simple prefix stays bare"),
    ("D-103z", "CN(C)C(N)=[NH2+]", "1,1-dimethylguanidinium", "(unchanged)",
     "converse: p. 819 prints N,N-dimethylguanidinium; the numeric form the renderer uses is the same compound"),
    # (moved from OPEN when the guanidinium enclosure fix landed; each was red before, with the names in the 'former' column)
    # ---- naming round 8, W2: metforminium was a WRONG MOLECULE. OPSIN reads '(dimethylamino)(imino)methylguanidinium' as
    # CN(C)N(C(=[NH2+])N)C=N, with an N-N bond: the compound prefix was neither enclosed nor located. P-16.5.1.3 (pdf p. 130)
    # encloses a compound prefix; a multiplied compound prefix takes 'bis' (the multiplier stays outside the marks).
    ("D-103a", "CN(C)C(=N)NC(N)=[NH2+]", "[(dimethylamino)(imino)methyl]guanidinium",
     "(dimethylamino)(imino)methylguanidinium", "derived: metformin's cation; the old name denoted another molecule"),
    ("D-103b", "ClCCNC(=[NH2+])NCCCl", "1,3-bis(2-chloroethyl)guanidinium",
     "1,3-di2-chloroethylguanidinium", "derived: a multiplied compound prefix; the old name did not parse at all"),
    ("D-103c", "CNC(=N)NC(N)=[NH2+]", "[(imino)(methylamino)methyl]guanidinium",
     "(imino)(methylamino)methylguanidinium", "derived: N-methylbiguanidium, the same defect"),
    ("D-103d", "NC(=[NH2+])NCCCl", "(2-chloroethyl)guanidinium",
     "2-chloroethylguanidinium", "derived (P-16.5.1.3: a prefix that carries a locant is enclosed): structurally right "
     "before, non-preferred"),
    # ---- naming round 8, W2 part 2: condensed ureas and guanidines (P-66.1.6.1.4 pdf p. 663, P-66.4.1.2 pdf p. 677). Converses
    # first: they pass today and must not move.
    ("D-104x", "NC(N)=O", "urea", "(unchanged)", "converse: n = 1 is urea itself, a retained name, not a condensed chain"),
    ("D-104y", "NC(=N)NC(N)=N", "imidodicarbonimidic diamide", "(unchanged)",
     "converse, p. 677 verbatim: n = 2 guanidine has its own constructor since round 4 and this constructor must not touch it"),
    ("D-104z", "CN(C)C(=N)NC(N)=N", "N1,N1-dimethylimidodicarbonimidic diamide", "(unchanged)",
     "converse: metformin, the regression-corpus row, already the book's form (the round's plan assumed it would change)"),
    ("D-104w", "CC(=O)NC(N)=O", "N-carbamoylacetamide", "(unchanged)",
     "converse: an acetylurea has ONE urea carbon; a chain needs at least two urea/guanidine carbons"),
    # (moved from OPEN when the condensed-diamide constructor landed; each was red before, with the names in the 'former' column)
    # The Blue Book prints these with the imido locants for ureas ('2-imidodicarbonic diamide') and without for guanidines.
    ("D-104a", "NC(=O)NC(N)=O", "2-imidodicarbonic diamide", "N-carbamoylurea",
     "p. 663 verbatim (biuret is 'no longer recommended as a preferred IUPAC name')"),
    ("D-104b", "NC(=O)NC(=O)NC(N)=O", "2,4-diimidotricarbonic diamide", "N-(carbamoylcarbamoyl)urea",
     "p. 663 verbatim (triuret)"),
    ("D-104c", "NC(=N)NC(=N)NC(N)=N", "diimidotricarbonimidic diamide", "N1-carbamimidoylimidodicarbonimidic diamide",
     "p. 677 verbatim (triguanide); structurally right before, and not the PIN"),
    ("D-104d", "NC(=O)NC(=O)NC(=O)NC(N)=O", "2,4,6-triimidotetracarbonic diamide", "N-[(carbamoylcarbamoyl)carbamoyl]urea",
     "derived (p. 663: 'n = 2, 3, or 4'): the next member of the printed series"),
    ("D-104e", "CNC(=O)NC(N)=O", "N1-methyl-2-imidodicarbonic diamide", "N-carbamoyl-N'-methylurea",
     "derived (p. 663: 'locants ... are used to indicate the positions of substituents'); OPSIN reads it back to the row"),
    ("D-104f", "CNC(=O)NC(=O)NC", "N1,N3-dimethyl-2-imidodicarbonic diamide", "N-methyl-N'-(methylcarbamoyl)urea",
     "derived: one substituent on each end, so the locant set is decided by lowest locants, not by atom order"),
    ("D-104g", "CN(C(N)=O)C(N)=O", "2-methyl-2-imidodicarbonic diamide", "N-carbamoyl-N-methylurea",
     "derived: a substituent on the BRIDGING nitrogen takes the numeric locant 2, as the figure on p. 663 shows"),
    ("D-104v", "NC(=O)NC(=O)NCC(O)=O", "[(carbamoylcarbamoyl)amino]acetic acid", "(unchanged)",
     "converse, an EARLIER rule: a carboxylic acid on a chain nitrogen is senior to the amide, so it is the parent and the "
     "condensed urea is a prefix; the constructor must return None"),
    ("D-104u", "NC(=O)NC(=O)NC", "N1-methyl-2-imidodicarbonic diamide", "N-carbamoyl-N'-methylurea",
     "derived: D-104e written from the OTHER end, so the chain is walked from the other side and the numbering direction, "
     "not the atom order, must put the substituent on N1"),
    ("D-104t", "CN=C(N)NC(=N)NC(N)=N", "N'1-methyldiimidotricarbonimidic diamide", "N1-carbamimidoyl-N'3-methylimidodicarbonimidic diamide",
     "derived (p. 677: the imino nitrogen of an END carbon is N'1, primed): a substituent there is not on the amino nitrogen"),
    ("D-104r", "NC(=N)NC(=NC)NC(N)=N", "N3-methyldiimidotricarbonimidic diamide", "N1-carbamimidoyl-N3-methylimidodicarbonimidic diamide",
     "derived (p. 677: an INTERIOR carbon's imino nitrogen is N3, unprimed): the same atom kind as D-104t at a different position"),
    # D-104s pinned "n = 5 ureas are not built, the book prints none". RETIRED in the limitations sweep: D-113c builds it, marked DERIVED (the skeletal-replacement
    # form of the printed n = 5 guanidine, p. 677, with oxo and diamide; OPSIN reads it back), which is the convention for a target the book does not print.
    ("D-091t", "NC(=O)NC(=O)NC(N)=O", "2,4-diimidotricarbonic diamide",
     "N-(carbamoylcarbamoyl)urea", "pdf p. 663 (recorded here as p. 662, the zero-based index): condensed ureas are "
     "imidopolycarbonic diamides. FIXED in naming round 8 (W2): _name_condensed_carbonic_diamide_functional_parent"),
    # ---- naming round 8, W3: a protonated ring nitrogen beside a second ring nitrogen (P-73.1.1.2, pdf p. 818). Converses first:
    # they pass today and must not move. Each differs from the defect by a REASON, not by a spelling.
    ("D-105x", "C[n+]1ccn(C)c1", "1,3-dimethyl-1H-imidazol-3-ium", "(unchanged)",
     "converse: BOTH nitrogens substituted; the direct build finds two targets, fails to sanitise, and the string path neutralises it"),
    ("D-105y", "c1cc[nH+]cc1", "pyridin-1-ium", "(unchanged)",
     "converse: ONE ring nitrogen; no indicated-H target exists, the direct build steps aside and the string path neutralises it"),
    ("D-105z", "c1ccc2[nH+]cccc2c1", "quinolin-1-ium", "(unchanged)",
     "converse: a fused ring with ONE ring nitrogen, the same route as pyridinium"),
    ("D-105w", "c1c[nH]cn1", "1H-imidazole", "(unchanged)",
     "converse: the NEUTRAL parent, which goes through the same direct build with no charged atom in it"),
    ("D-105v", "C[n+]1ccsc1", "3-methyl-1,3-thiazol-3-ium", "(unchanged)",
     "converse: a chalcogen ring with one substituted nitrogen; the direct build finds a target, cannot sanitise [nH] beside S, and steps aside"),
    ("D-105a", "c1c[nH]c[nH+]1", "1H-imidazol-3-ium", "1,3-diazol-1-ium",
     "p. 818 verbatim '1H-imidazol-3-ium (PIN)'; the carved ring kept its charge, so the retained 'imidazole' key never matched"),
    ("D-105b", "Cn1cc[nH+]c1", "1-methyl-1H-imidazol-3-ium", "1-methyl-1,3-diazol-3-ium",
     "derived (P-73.1.1.2 on the printed 1H-imidazol-3-ium): the protonated nitrogen is the -ium, the methylated one carries the 1H"),
    ("D-105c", "c1ccc2[nH]c[nH+]c2c1", "1H-benzimidazol-3-ium", "[NAMING ERROR: No valid naming plan found for c1ccc2[nH+]c[nH]c2c1]",
     "derived (P-73.1.1.2 on the retained benzimidazole); an embedded refusal string, not a name, before"),
    ("D-105d", "Cn1c[nH+]c2ccccc21", "1-methyl-1H-benzimidazol-3-ium",
     "{[NAMING ERROR: No valid naming plan found for c1ccc2[nH+]c[nH]c2c1]}methane",
     "derived: the same ring failure, here as a refusal inside a substituent name; a methyl benzimidazolium was named 'methane'"),
    ("D-105e", "c1c[nH+][nH]c1", "1H-pyrazol-2-ium", "1,2-diazol-2-ium",
     "derived (P-73.1.1.2 on the retained pyrazole); the same hole as imidazolium"),
    ("D-105f", "c1ccc2[nH][nH+]cc2c1", "1H-indazol-2-ium", "[NAMING ERROR: No valid naming plan found for c1ccc2[nH][nH+]cc2c1]",
     "derived: the fused analogue of pyrazolium, an embedded refusal before"),
    ("D-105g", "c1c[nH]c[nH+]1.[Cl-]", "1H-imidazol-3-ium chloride", "1,3-diazol-1-ium chloride",
     "the salt of D-105a; the cation is named apart from the anion, so it must follow"),
    # ---- naming round 8, W3: the indicated hydrogen and the -ium are on DIFFERENT nitrogens. Converses: the neutral N-alkyl azoles
    # the changed branch of _retag_indicated_h was written for, and the cations that already had a neutral substituted nitrogen.
    ("D-106x", "Cn1c[n+](C)c2ccccc12", "1,3-dimethyl-1H-benzimidazol-3-ium", "(unchanged)",
     "converse: the -ium is at 3 and the neutral N-methyl at 1 already carries the indicated hydrogen"),
    ("D-106y", "Cn1nn[n+](C)c1", "1,4-dimethyl-1H-tetrazol-4-ium", "(unchanged)",
     "converse: a tetrazolium whose curated indicated hydrogen already sits on the NEUTRAL substituted nitrogen"),
    ("D-106z", "Cn1cnc2cncnc12", "9-methyl-9H-purine", "(unchanged)",
     "converse: the NEUTRAL 9-alkylpurine, the case the 'keep the curated prefix when the atom is substituted' branch exists for"),
    ("D-106w", "Cn1nc2ccccc2n1", "2-methyl-2H-benzotriazole", "(unchanged)",
     "converse: a neutral N-methyl benzotriazole with the indicated hydrogen on the middle nitrogen, which is where the cation's moves to"),
    ("D-106a", "C[n+]1cnn(C)c1", "1,4-dimethyl-1H-1,2,4-triazol-4-ium", "1,4-dimethyl-4H-1,2,4-triazol-4-ium",
     "derived (P-31.1.4.2.4 with the printed 1H-imidazol-3-ium, p. 818): the -ium atom cannot also be the indicated-hydrogen atom; "
     "OPSIN read the old name as one hydrogen too many"),
    ("D-106b", "C[n+]1cn(C)cn1", "1,4-dimethyl-4H-1,2,4-triazol-1-ium", "1,4-dimethyl-1H-1,2,4-triazol-1-ium",
     "derived: the same collision at locant 1, the other way round; the indicated hydrogen moves to the neutral N-methyl at 4"),
    ("D-106c", "Cn1nc2ccccc2[n+]1C", "1,2-dimethyl-2H-benzotriazol-1-ium", "1,2-dimethyl-1H-benzotriazol-1-ium",
     "derived: the same collision on a fused ring; the indicated hydrogen goes to the neutral N-methyl on the middle nitrogen"),
    ("D-106d", "Cn1[n+](C)c2ccccc2c1", "1,2-dimethyl-2H-indazol-1-ium", "1,2-dimethyl-1H-indazol-1-ium",
     "derived: the same collision on indazole"),
    # ---- naming round 8, W3: a ring cation outranks every uncharged suffix group (P-41, Table 4.1, pdf p. 360). Converses first:
    # each keeps a suffix or a form for a REASON of its own, so a guard that demoted too much would move one of them.
    ("D-107x", "C[n+]1ccc(cc1)C(O)=O.[Cl-]", "4-carboxy-1-methylpyridin-1-ium chloride", "(unchanged)",
     "converse, pdf p. 580 verbatim '4-carboxy-1-methylpyridin-1-ium chloride (PIN)': the salt route already wrote the acid as a prefix"),
    ("D-107y", "[O-]C(=O)c1cccc[n+]1C", "1-methylpyridin-1-ium-2-carboxylate", "(unchanged)",
     "converse: the zwitterion is dispatched as an ANION, where the carboxylate outranks the cation and stays the suffix"),
    ("D-107z", "NC(=[NH2+])c1ccccc1", "benzamidinium", "(unchanged)",
     "converse: the cationic centre is INSIDE the group, so it is the cation itself and not a junior group beside one"),
    ("D-107w", "C[N+](C)(C)CCO", "2-hydroxy-N,N,N-trimethylethan-1-aminium", "(unchanged)",
     "converse: an ACYCLIC ammonium takes the azanium parent-hydride route, which already wrote the alcohol as a prefix"),
    ("D-107v", "C[n+]1ccccc1C=NO", "2-[(hydroxyimino)methyl]-1-methylpyridin-1-ium", "(unchanged)",
     "converse: an oxime on a ring cation, already a prefix (pralidoxime)"),
    ("D-107a", "C[n+]1ccc(cc1)C(N)=O", "4-carbamoyl-1-methylpyridin-1-ium", "1-methylpyridin-1-ium-4-carboxamide",
     "derived: Table 4.1 (p. 360) puts cations above amides, as the printed 4-carboxy-1-methylpyridin-1-ium (p. 580) shows for the acid"),
    ("D-107b", "C[n+]1ccc(cc1)O", "4-hydroxy-1-methylpyridin-1-ium", "1-methylpyridin-1-ium-4-ol",
     "derived: cations above alcohols (Table 4.1)"),
    ("D-107c", "C[n+]1ccc(cc1)C#N", "4-cyano-1-methylpyridin-1-ium", "1-methylpyridin-1-ium-4-carbonitrile",
     "derived: cations above nitriles (Table 4.1)"),
    ("D-107d", "C[n+]1ccc(cc1)C=O", "4-formyl-1-methylpyridin-1-ium", "1-methylpyridin-1-ium-4-carbaldehyde",
     "derived: cations above aldehydes (Table 4.1)"),
    ("D-107e", "C[n+]1ccc(cc1)C(O)=O", "4-carboxy-1-methylpyridin-1-ium", "1-methylpyridin-1-ium-4-carboxylic acid",
     "pdf p. 580 verbatim (as the chloride): the ISOLATED cation was the one that kept the acid as a suffix, the salt did not"),
    ("D-107f", "C[n+]1ccc(cc1)S(O)(=O)=O", "1-methyl-4-sulfopyridin-1-ium", "1-methylpyridin-1-ium-4-sulfonic acid",
     "derived: cations above acids (Table 4.1); the chloride was already '1-methyl-4-sulfopyridin-1-ium chloride'"),
    ("D-107g", "NC(=O)c1ccc[nH+]c1", "3-carbamoylpyridin-1-ium", "pyridin-1-ium-3-carboxamide",
     "derived: protonated nicotinamide, the same rule with the charge from protonation and not alkylation"),
    ("D-107h", "C[n+]1ccc(cc1)C(N)=O.[Cl-]", "4-carbamoyl-1-methylpyridin-1-ium chloride", "1-methylpyridin-1-ium-4-carboxamide chloride",
     "derived: the salt of D-107a; the cation is named apart from its anion, so it must follow"),
    ("D-107i", "Cn1cc[n+](C)c1C(N)=O", "2-carbamoyl-1,3-dimethyl-1H-imidazol-3-ium", "1,3-dimethyl-1H-imidazol-3-ium-2-carboxamide",
     "derived: the same rule on a five-membered ring cation"),
    # Added AFTER the fix, to close two mutation survivors: they were green when written, and the mutants that turn them red are the proof.
    ("D-107j", "OC(=O)c1cc[o+]cc1", "4-carboxypyrylium", "pyrylium-4-carboxylic acid",
     "derived: the guard is not nitrogen-only; an oxygen ring cation outranks an acid too (Table 4.1)"),
    ("D-107k", "OC1CC[S+](C)CC1", "4-hydroxy-1-methylthian-1-ium", "1-methylthian-1-ium-4-ol",
     "derived: a SATURATED ring sulfonium, the same rule with a chalcogen cation"),
    ("D-107u", "C[n+]1ccc(cc1)C[NH3+]", "(1-methylpyridin-1-ium-4-yl)methanaminium", "(unchanged)",
     "converse: a DICATION whose second cationic centre is the group itself keeps its aminium suffix; only an UNCHARGED group is demoted"),
    # ---- naming round 8, W3: an anion outranks a cation (Table 4.1, pdf p. 360), so a net-POSITIVE species that also holds a carboxylate is
    # named as the anion. Converses first: each already carries its carboxylate, or has none to carry.
    ("D-108x", "[NH3+]CCCCC(N)C(=O)[O-]", "2-amino-6-azaniumylhexanoate", "(unchanged)",
     "converse: lysine with ONE ammonium is net zero, already dispatched as an anion"),
    ("D-108y", "[NH3+]CC(O)=O", "carboxymethanaminium", "(unchanged)",
     "converse: a net-positive amino acid with NO anionic site has nothing to promote"),
    ("D-108z", "C[n+]1ccc(cc1)CC(=O)[O-]", "(1-methylpyridin-1-ium-4-yl)acetate", "(unchanged)",
     "converse: a net-zero ring-cation zwitterion, already an anion with the ring -ium independent of the form"),
    ("D-108w", "[NH3+]CC(=O)[O-]", "azaniumylacetate", "(unchanged)",
     "converse: glycine zwitterion, the neutral-net case this rule extends"),
    ("D-108a", "[NH3+]CCCCC([NH3+])C(=O)[O-]", "2,6-bis(azaniumyl)hexanoate", "(5-azaniumyl-1-carboxypentyl)azanium",
     "derived (Table 4.1: anions above cations; P-72.2 with the printed azaniumylacetate form): the carboxylate was written as a NEUTRAL carboxy, "
     "a different molecule (lysine at physiological pH)"),
    ("D-108b", "[NH3+]C(Cc1c[nH]c[nH+]1)C(=O)[O-]", "2-azaniumyl-3-(1H-imidazol-3-ium-4-yl)propanoate",
     "[1-carboxy-2-(1H-imidazol-3-ium-4-yl)ethyl]azanium",
     "derived: histidine with the ring protonated, the same loss of the carboxylate's charge with a ring cation beside it"),
    ("D-108c", "[NH3+]CC([NH3+])C(=O)[O-]", "2,3-bis(azaniumyl)propanoate", "2,3-diazaniumylpropanoate",
     "derived: the multiplier alone. Round trip failed under OPSIN with 'diazaniumyl' (two skeletal-replacement aza prefixes or a diazane), "
     "so the form the oracle reads is the one shipped; the book prints no multiplied azaniumyl"),
    # ---- naming round 8, W3: the SALT route, for a net-positive component holding a carboxylate. Red at 742a54f, measured by naming an archived
    # copy of that tree (not by a strict xfail: these were added together with the fix). Same rule as D-108, one dispatch deeper.
    ("D-109a", "[NH3+]CCCCC([NH3+])C(=O)[O-].[Cl-]", "2,6-bis(azaniumyl)hexanoate chloride", "(5-azaniumyl-1-carboxypentyl)azanium chloride",
     "a balanced lysine salt (+2, -1, -1): the component was named as a CATION, its carboxylate a neutral 'carboxy', so the name had one charge too many"),
    ("D-109b", "[NH3+]C(Cc1c[nH]c[nH+]1)C(=O)[O-].[Cl-]", "2-azaniumyl-3-(1H-imidazol-3-ium-4-yl)propanoate chloride",
     "[1-carboxy-2-(1,3-diazol-3-ium-4-yl)ethyl]azanium chloride", "histidinium chloride: the same loss, and the ring name was the unretained one as well"),
    ("D-109x", "[NH3+]CCCCC(N)C(=O)O.[Cl-]", "5-amino-5-carboxypentan-1-aminium chloride", "(unchanged)",
     "converse: the ordinary lysine hydrochloride has NO deprotonated site, so the fragment stays a cation"),
    ("D-109y", "[NH3+]CC(=O)O.[Cl-]", "carboxymethanaminium chloride", "(unchanged)",
     "converse: glycinium chloride, likewise"),
    ("D-109u", "[NH3+]CCc1ccc(cc1)[N+](=O)[O-].[Cl-]", "[2-(4-nitrophenyl)ethyl]azanium chloride", "(unchanged)",
     "converse: a net-positive cation whose negative atom is a NITRO group's, not an acid site; only an anion suffix earns the ANION form"),
    ("D-109v", "C[N+](C)(C)CC(=O)[O-].O", "(trimethylazaniumyl)acetate water", "(unchanged)",
     "converse: a NET-ZERO zwitterion beside another component keeps the ANION form the net-zero branch gives it"),
    ("D-091u", "CC(=O)NC(=O)c1ccccc1", "N-acetylbenzamide", "N-benzoylacetamide",
     "p. 654, verbatim: of two acyls on one N only one amide is perceived, so the "
     "senior one (ring before chain) is never offered as the parent"),
    # ---- naming round 8, W4(a): which of two acyl groups on one nitrogen is the parent (P-66.1.4.2, pdf p. 654). Converses first: each keeps the
    # name it had, and the two that a first attempt broke (offering BOTH amide matches to plan search) are here so it cannot be tried again unseen.
    ("D-110x", "CC(=O)NC(C)=O", "N-acetylacetamide", "(unchanged)", "converse: the symmetric imide, no ring on either side"),
    ("D-110y", "CCC(=O)NC(C)=O", "N-acetylpropanamide", "(unchanged)",
     "converse: two chains: the ring test does not apply and the existing tie-break decides"),
    ("D-110z", "CC(=O)N(C(C)=O)C(C)=O", "N,N-diacetylacetamide", "(unchanged)",
     "converse: a triacylamine. Offering every amide match gave an atom-ownership error for it"),
    ("D-110w", "CC(=O)NC(=O)c1ccc(cc1)C(O)=O", "4-(acetylcarbamoyl)benzoic acid", "(unchanged)",
     "converse: the ACID is the parent (Table 4.1); offering both amide matches wrote the imide unit twice, '4,4-bis(acetylcarbamoyl)benzoic acid'"),
    ("D-110v", "O=C(NC(=O)c1ccccc1)c1ccccc1", "N-benzoylbenzamide", "(unchanged)", "converse: a ring on BOTH sides, so neither is preferred by it"),
    ("D-110u", "CC(=O)N(C)C(C)=O", "N-acetyl-N-methylacetamide", "(unchanged)", "converse: the tertiary imide with no ring"),
    ("D-110t", "O=C1CCC(=O)N1", "pyrrolidine-2,5-dione", "(unchanged)", "converse: a ring imide has no second acyclic amide to choose"),
    ("D-110a", "CC(=O)NC(=O)C1CCCCC1", "N-acetylcyclohexanecarboxamide", "N-(cyclohexanecarbonyl)acetamide",
     "derived (ring before chain, P-44.1.2.2, as the printed N-acetylbenzamide): the saturated ring is a ring too"),
    ("D-110b", "CC(=O)N(C)C(=O)c1ccccc1", "N-acetyl-N-methylbenzamide", "N-benzoyl-N-methylacetamide",
     "derived: the tertiary imide, the same choice of representative"),
    ("D-110r", "c1ccccc1C(=O)NC(C)=O", "N-acetylbenzamide", "(unchanged)",
     "the SAME molecule written ring-first: the ring match is now the one already kept, and a chain match must not replace it"),
    ("D-110q", "O=C(NC(C)=O)C1CCCCC1", "N-acetylcyclohexanecarboxamide", "(unchanged)",
     "the saturated ring written first, the same guard"),
    # ---- naming round 8, limitations sweep: a tetrazolium whose two substituted nitrogens are ADJACENT. The retained '1H-tetrazole' came back with no
    # numbering, the strategy rotated the ring freely, and the winner put '5' on a nitrogen ('1,5-dimethyl-1H-tetrazol-5-ium': locant 5 is the carbon; OPSIN cannot
    # read it). Red at 742a54f and at d66b7ad, measured from archived trees. The carve now leaves a bare [n+] out of the indicated-H targets when a NEUTRAL
    # substituted nitrogen exists, so the 2H-tautomer key is the one matched.
    ("D-111a", "Cn1nnc[n+]1C", "1,2-dimethyl-2H-tetrazol-1-ium", "1,5-dimethyl-1H-tetrazol-5-ium",
     "derived (the -ium and the indicated hydrogen on different nitrogens, as the printed 1H-imidazol-3-ium, p. 818); OPSIN reads it back to the input"),
    ("D-111b", "Cn1nnc(C)[n+]1C", "1,2,5-trimethyl-2H-tetrazol-1-ium", "1,4,5-trimethyl-1H-tetrazol-5-ium",
     "the same ring with a carbon substituent; the old name put a 4 and a 5 on nitrogens"),
    ("D-111c", "CCn1nnc[n+]1C", "2-ethyl-1-methyl-2H-tetrazol-1-ium", "1-ethyl-5-methyl-1H-tetrazol-5-ium",
     "two different N-alkyls: which of them is at the -ium is decided by lowest locants, not by atom order"),
    ("D-111x", "Cn1ncn[n+]1C", "2,3-dimethyl-2H-tetrazol-3-ium", "(unchanged)",
     "converse: the other adjacent-nitrogen tetrazolium, whose carve already reached the 2H key"),
    ("D-111y", "C[n+]1ccccc1", "1-methylpyridin-1-ium", "(unchanged)",
     "converse: ONE ring nitrogen, so the bare [n+] IS the only slot for the indicated hydrogen and stays a target"),
    ("D-111z", "Cn1cc[n+](C)c1", "1,3-dimethyl-1H-imidazol-3-ium", "(unchanged)",
     "converse: the imidazolium, where a neutral N-methyl and a [n+](C) were both targets before and the result must not move"),
    # ---- naming round 8, limitations sweep: an N-oxide beside ANOTHER cationic centre. '<parent> N-oxide' names a NEUTRAL parent with an oxide on one nitrogen; with a second
    # positive centre it did not say which nitrogen carried the oxide and OPSIN could not read it (five inputs), and once it named a pyridinium's pyridine N-oxide as another
    # molecule (D-112e). Red at ee20f0a, measured. WHAT THESE ROWS CLAIM: the name is OPSIN-verified, not that it is the preferred one; the book's own form for an amine oxide beside a
    # cation is unresolved ('azanium' versus 'methanaminium' as the parent), so the expected names are the engine's, pinned so the unreadable form cannot return.
    ("D-112a", "[NH3+]CC[N+](C)(C)[O-]", "(2-azaniumylethyl)di(methyl)(oxido)ammonium", "2-(dimethylamino)ethan-1-aminium N-oxide",
     "OPSIN-verified, preference not claimed; the additive name is declined when another positive centre exists"),
    ("D-112b", "[O-][n+]1ccccc1C[NH3+]", "[(1-oxidopyridin-1-ium-2-yl)methyl]azanium", "(pyridin-2-yl)methanaminium N-oxide",
     "OPSIN-verified, preference not claimed; the oxide goes inline as '1-oxidopyridin-1-ium' (the substitutive path already wrote it)"),
    ("D-112c", "[O-][n+]1ccc(cc1)C[NH3+]", "[(1-oxidopyridin-1-ium-4-yl)methyl]azanium", "(pyridin-4-yl)methanaminium N-oxide", "the 4-isomer of D-112b"),
    ("D-112d", "[O-][n+]1ccccc1C[N+](C)(C)C", "trimethyl[(1-oxidopyridin-1-ium-2-yl)methyl]ammonium",
     "N,N,N-trimethyl-1-(pyridin-2-yl)methanaminium N-oxide", "a quaternary ammonium as the other cationic centre"),
    ("D-112e", "c1cc[n+]([O-])cc1C[n+]1ccccc1", "1-oxido-3-[(pyridinium-1-yl)methyl]pyridin-1-ium", "1-[(pyridin-3-yl)methyl]pyridine N-oxide",
     "a WRONG MOLECULE before: the pyridinium was named as a pyridine and the oxide attached to the other ring's name; it read back as another compound"),
    ("D-112x", "C[N+](C)(C)[O-]", "N,N-dimethylmethanamine N-oxide", "(unchanged)", "converse, p. 108 style: a NEUTRAL amine oxide keeps the additive form"),
    ("D-112y", "[O-][n+]1ccccc1", "pyridine 1-oxide", "(unchanged)", "converse: a neutral heteroaromatic N-oxide"),
    ("D-112z", "[O-]C(=O)c1cc[n+]([O-])cc1", "pyridine-4-carboxylate 1-oxide", "(unchanged)",
     "converse: an oxide beside only a NEGATIVE centre keeps the additive form, which is the case the source comment reserves it for"),
    ("D-112w", "[O-][n+]1ccc(N)cc1", "pyridin-4-amine 1-oxide", "(unchanged)", "converse: a neutral amine beside the oxide is not a cationic centre"),
    # ---- naming round 8, limitations sweep: n >= 5 condensed guanidines and ureas are skeletal-replacement names (P-66.4.1.2, pdf p. 677). Before, plan search failed inside a
    # substituent and the NAMING ERROR was EMBEDDED in a real-looking name. Unsubstituted chains only; a substituted one still has no name (and the provider now says so).
    ("D-113a", "N=C(N)NC(=N)NC(=N)NC(=N)NC(=N)N", "3,5,7-triimino-2,4,6,8-tetraazanonane-1,9-diimidamide",
     "bis{[NAMING ERROR: No valid naming plan found for N=C(N)NC(=N)N]}methanimine",
     "p. 677 verbatim '3,5,7-triimino-2,4,6,8-tetraazanonane-1,9-diimidamide (PIN)'"),
    ("D-113b", "N=C(N)NC(=N)NC(=N)NC(=N)NC(=N)NC(=N)N", "3,5,7,9-tetraimino-2,4,6,8,10-pentaazaundecane-1,11-diimidamide", "(a NAMING ERROR embedded in a name)",
     "derived: the next member of the printed series; OPSIN reads it back"),
    ("D-113c", "NC(=O)NC(=O)NC(=O)NC(=O)NC(N)=O", "3,5,7-trioxo-2,4,6,8-tetraazanonane-1,9-diamide", "N-{[(carbamoylcarbamoyl)carbamoyl]carbamoyl}urea",
     "derived: the urea analogue of the printed guanidine, the same construction with oxo and diamide"),
    ("D-113d", "NC(=O)NC(=O)NC(=O)NC(=O)NC(=O)NC(N)=O", "3,5,7,9-tetraoxo-2,4,6,8,10-pentaazaundecane-1,11-diamide", "(an acyl-prefix chain)",
     "derived: n = 6"),
    ("D-113x", "N=C(N)NC(=N)NC(=N)NC(=N)N", "triimidotetracarbonimidic diamide", "(unchanged)", "converse: n = 4 is still the condensed-diamide name (p. 677 prints n = 2, 3, 4)"),
    ("D-113y", "NC(=O)NC(=O)NC(=O)NC(=O)N", "2,4,6-triimidotetracarbonic diamide", "(unchanged)", "converse: the n = 4 urea"),
    # Added when a first draft of the tetrazolium rule (a bare [n+] is not an indicated-hydrogen target) was found to have LOST the retained names of every SATURATED quaternary
    # ring cation: no corpus row exercised one, so the firewall stayed silent and only a probe found it. These pin what the pre-round-8 engine wrote and the rule must keep.
    ("D-111v", "C[N+]1(C)CCCCC1", "1,1-dimethylpiperidin-1-ium", "(unchanged)", "converse: a saturated quaternary ring cation keeps its retained ring name"),
    ("D-111u", "C[N+]1(C)CCOCC1", "4,4-dimethylmorpholin-4-ium", "(unchanged)", "converse: morpholinium"),
    ("D-111t", "C[N+]1(C)CCc2ccccc2C1", "2,2-dimethyl-1,2,3,4-tetrahydroisoquinolin-2-ium", "(unchanged)",
     "converse: a fused saturated ring, which the first draft named '(2-methyl-...-2-yl)methane'"),
    ("D-111s", "c1cc[n-]c1", "1H-pyrrol-1-ide", "(unchanged)",
     "converse: an aromatic ANION [n-] is an indicated-hydrogen target and must stay one, which the aromatic-cation rule above must not touch"),
    # ---- naming round 8, limitations sweep: a PROTONATED saturated ring nitrogen ([NH2+], no exocyclic substituent). The carve left it charged, so the retained ring key (piperidine,
    # pyrrolidine, morpholine, tetrahydroisoquinoline) never matched: the Hantzsch-Widman 'azinan-1-ium' for the retained 'piperidin-1-ium' (printed as a ring name on pdf p. 833),
    # and for a FUSED ring no plan at all (an embedded NAMING ERROR). Red at 7f2ca01, measured. Targets are the cation of the printed retained ring; each reads back under OPSIN.
    ("D-114a", "C1CC[NH2+]CC1", "piperidin-1-ium", "azinan-1-ium", "the ring name printed on p. 833 ('2-(piperidin-1-ium-3-yl)propane-1,2-bis(aminium) (PIN)')"),
    ("D-114b", "C1CC[NH2+]C1", "pyrrolidin-1-ium", "azolidin-1-ium", "derived: pyrrolidine is the retained PIN; the cation follows P-73.1.1.2"),
    ("D-114c", "C1COCC[NH2+]1", "morpholin-4-ium", "1,4-oxazinan-4-ium", "derived: morpholine is the retained PIN"),
    ("D-114d", "Cc1ccc(cc1)C1CC[NH2+]CC1", "4-(4-methylphenyl)piperidin-1-ium", "4-(4-methylphenyl)azinan-1-ium", "a substituted piperidinium, the drug-like case"),
    ("D-114e", "C1Cc2ccccc2C[NH2+]1", "1,2,3,4-tetrahydroisoquinolin-2-ium", "[NAMING ERROR: No valid naming plan found for c1ccc2c(c1)CC[NH2+]C2]",
     "a FUSED ring: no name at all before (the neutral 1,2,3,4-tetrahydroisoquinoline was always named)"),
    ("D-114f", "C1CC2CC[NH2+]C2C1", "octahydrocyclopenta[b]pyrrol-1-ium", "[NAMING ERROR: No valid naming plan found for C1CC2CC[NH2+]C2C1]",
     "a saturated fused ring with a bridgehead-adjacent nitrogen"),
    ("D-114g", "C1CC[NH2+]CC1.[Cl-]", "piperidin-1-ium chloride", "azinan-1-ium chloride", "the salt: the cation is named apart from its anion"),
    ("D-114h", "[NH2+]1CCOCC1C(=O)O", "3-carboxymorpholin-4-ium", "3-carboxy-1,4-oxazinan-4-ium", "a substituent on the ring"),
    ("D-114x", "C1CCNCC1", "piperidine", "(unchanged)", "converse: the NEUTRAL ring, which goes through the same carve"),
    ("D-114y", "C[NH+]1CCCCC1", "1-methylpiperidin-1-ium", "(unchanged)", "converse: an N-alkyl protonated ring, already a target through its exocyclic substituent"),
    ("D-114z", "C1CCC(CC1)[NH3+]", "cyclohexanaminium", "(unchanged)", "converse: an EXOCYCLIC ammonium is not a ring nitrogen"),
    # ---- naming round 8, limitations sweep: the '-ium' locant is compared with the suffix locants. It was not compared at all, so the atom order of the SMILES decided it: the same
    # molecule was 'piperazin-4-ium' or 'piperazin-1-ium'. P-31.1.4.3 (suffixes, after indicated hydrogen) puts a ring cation's locant in the suffix tier. Red at 2d70678, measured.
    ("D-115a", "C1C[NH2+]CCN1", "piperazin-1-ium", "piperazin-4-ium", "derived (lowest locant to the cationic centre): one of two atom-order twins of the same molecule"),
    ("D-115b", "C[NH+]1CCN(C)CC1", "1,4-dimethylpiperazin-1-ium", "1,4-dimethylpiperazin-4-ium", "the same tie with two methyls, where the ium locant is what decides"),
    ("D-115x", "C1CNCC[NH2+]1", "piperazin-1-ium", "(unchanged)", "converse: the atom-order twin of D-115a, which already read 1; both must now agree"),
    ("D-115y", "CN1CC[NH+](C)CC1", "1,4-dimethylpiperazin-1-ium", "(unchanged)", "converse: the twin of D-115b written the other way round"),
    ("D-115z", "C[N+]1(C)CCN(C)CC1", "1,1,4-trimethylpiperazin-1-ium", "(unchanged)", "converse: the ium locant and a substituent locant both 1: the tie must not move a case that was already lowest"),
    # ---- naming round 8, limitations sweep: a biguanide-route substituent joined by a DOUBLE bond. The route hard-coded the attachment bond order to 1, so the tautomer drawn with
    # =C(N)N on a terminal nitrogen was named 'diaminomethyl' (an sp3 carbon, the wrong hydrogens: a WRONG molecule in the app's canonical spelling). The real bond order gives
    # 'diaminomethylidene', which OPSIN reads back as exactly that tautomer. Red at f092917, measured; the app names the RDKit CANONICAL spelling, which is what these use.
    ("D-116a", "N=C(N)NC(=N)N=C(N)N", "N1-(diaminomethylidene)imidodicarbonimidic diamide", "N1-(diaminomethyl)imidodicarbonimidic diamide",
     "derived (P-66.4.1.2's parent with an ylidene substituent; the book prints no such tautomer); enclosed as a substituted ylidene"),
    ("D-116x", "ClC(Cl)=C1CCCC1", "(dichloromethylidene)cyclopentane", "(unchanged)", "converse: a substituted ylidene that was ALREADY enclosed and must stay so"),
    ("D-116y", "S=C1CCCCC1", "cyclohexanethione", "(unchanged)", "converse: a thione, not a substituent prefix"),
    ("D-116z", "S=C1C=CC=CC1=O", "6-sulfanylidenecyclohexa-2,4-dien-1-one", "(unchanged)",
     "converse, the reason the ylidene shortcut exists: 'sulfanylidene' is ONE stem and the book prints it bare ('3-sulfanylidene-2-benzothiophen-1-one', pdf p. 642)"),
    ("D-088a", "O=C(NNC(=O)c1ccccc1)c1ccccc1", "N'-benzoylbenzohydrazide",
     "1,2-dibenzoylhydrazine", "'N'-benzoylbenzohydrazide (PIN) (not "
     "1,2-dibenzoylhydrazine)' (p. 670). Admitting an acylated N' to the hydrazide "
     "pattern reaches it, but turned 4-(2-benzoylhydrazinyl)-4-oxobutanoic acid into "
     "a butanedioyl name: the demoted, prefix form is not built"),
    # ---- naming round 8, limitations sweep (W4c): the hydrazide as a PREFIX. A hydrazide is a prefix ('hydrazinecarbonyl') only when it attaches through its CARBONYL carbon and
    # that carbon is outside the parent. With the carbonyl INSIDE an acid chain its =O is 'oxo' and its N-N a 'hydrazinyl', which p. 670 prints as a PIN ('3-hydrazinyl-3-oxopropanoic acid');
    # attached through a nitrogen it is an N-acyl hydrazine. In both the group had no prefix form, the top-ranked acid plan died with 'heavy atoms unclaimed', and the engine fell back to a
    # hydrazide parent: the hydrazide ABOVE a carboxylic acid, against Table 4.1. Round 4 found the coupling and stopped; the pattern change (an acylated N') needs this to be safe.
    ("D-117a", "NNC(=O)CC(=O)O", "3-hydrazinyl-3-oxopropanoic acid", "2-carboxyacetohydrazide",
     "p. 670 VERBATIM '3-hydrazinyl-3-oxopropanoic acid (PIN)'; a lone locanted 'hydrazinyl' is printed bare"),
    ("D-117b", "NNC(=O)CCC(=O)O", "4-hydrazinyl-4-oxobutanoic acid", "3-carboxypropanehydrazide", "derived: the next member; the acid is the parent, as an amide on the same chain is ('4-amino-4-oxobutanoic acid')"),
    ("D-117c", "NNC(=O)CCC(=O)N", "4-hydrazinyl-4-oxobutanamide", "4-amino-4-oxobutanehydrazide", "derived: an AMIDE is senior to a hydrazide (Table 4.1), so it is the parent"),
    ("D-117d", "CC(=O)NNC(=O)c1ccccc1", "N'-acetylbenzohydrazide", "1-acetyl-2-benzoylhydrazine", "derived from the printed N'-benzoylbenzohydrazide: the ring acyl is the hydrazide, the other an N'-substituent"),
    ("D-117e", "CC(=O)NNC(C)=O", "N'-acetylacetohydrazide", "1,2-diacetylhydrazine", "derived: the symmetric analogue of the printed dibenzoyl case"),
    ("D-117f", "O=C(NNC)c1ccc(C(=O)O)cc1", "4-[(2-methylhydrazinyl)(oxo)methyl]benzoic acid", "4-carboxy-N'-methylbenzohydrazide",
     "OPSIN-verified, the ACID is the parent (Table 4.1); the PIN spelling of the prefix, '2-methylhydrazine-1-carbonyl', is D-088d and still open"),
    ("D-117x", "O=C(O)CCC(=O)NNC(=O)c1ccccc1", "4-(2-benzoylhydrazinyl)-4-oxobutanoic acid", "(unchanged)",
     "converse, THE ROUND-4 BLOCKER: widening the pattern alone turned this into an unreadable 'N'-butanedioylbenzohydrazide'; it must not"),
    ("D-117y", "NNC(=O)c1ccc(cc1)C(=O)O", "4-(hydrazinecarbonyl)benzoic acid", "(unchanged)", "converse: a hydrazide that attaches through its CARBONYL carbon keeps the prefix form"),
    ("D-117z", "NNCC(=O)O", "(hydrazinyl)acetic acid", "(unchanged)", "converse: an UNLOCANTED hydrazinyl keeps its brackets, which are load-bearing for OPSIN there"),
    ("D-117w", "CNNC(=O)c1ccccc1", "N'-methylbenzohydrazide", "(unchanged)", "converse: the substituted hydrazide as the parent"),
    ("D-117v", "O=C(NNS(=O)(=O)c1ccccc1)c1ccccc1", "N-benzamidobenzenesulfonamide", "(unchanged)", "converse: a sulfonamide, not an acylated N'"),
    ("D-117u", "CC(=O)NNc1ccc(cc1)C(=O)O", "4-(2-acetylhydrazinyl)benzoic acid", "(unchanged)",
     "converse, the ONLY row where a hydrazide attaches through NITROGEN alone: giving it the carbonyl-carbon prefix 'hydrazinecarbonyl' would name another molecule"),
    ("D-117t", "NNC(=O)CCc1ccc(cc1)C(=O)O", "4-(3-hydrazinyl-3-oxopropyl)benzoic acid", "3-(4-carboxyphenyl)propanehydrazide",
     "a REMOTE hydrazide (no bond to the ring): the acid outranks it (Table 4.1); the hydrazide was the parent"),
    ("D-117s", "O=C(NNc1ccccc1)c1ccc(cc1)C(=O)O", "4-[(oxo)(2-phenylhydrazinyl)methyl]benzoic acid", "4-carboxy-N'-phenylbenzohydrazide",
     "OPSIN-verified, the ACID is the parent; the spelling of the prefix is not claimed (D-088d)"),
    ("D-088c", "O=C(N=Nc1ccccc1)N=Nc1ccccc1", "bis(phenyldiazenyl)methanone",
     "1-[(oxo)(phenyldiazenyl)methyl]-2-phenyldiazene",
     "p. 110: a C=O between two N= is not perceived as a ketone"),
    # ---- naming round 8, limitations sweep (W4b): PSEUDOKETONES, P-64.3.2 (pdf p. 567). "Acyclic pseudoketones, including those in which the carbonyl group is linked to a heteroatom of a
    # heterocycle (hidden amides, for instance), are named substitutively by using the suffix 'one'. This method is preferred to that using acyl groups". The engine had no such group at all, so
    # every carbonyl on a ring nitrogen, an azo nitrogen or silicon was named with an acyl prefix ('1-propanoylpiperidine'). The fix is four ketone definitions in the group data with a new key,
    # context_indices, declaring the heteroatom as the ROOT of the substituent, plus three places that had claimed every heteroatom of a group as the group's own.
    ("D-118a", "CCC(=O)N1CCCCC1", "1-(piperidin-1-yl)propan-1-one", "1-propanoylpiperidine", "p. 567 VERBATIM '1-(piperidin-1-yl)propan-1-one (PIN)'"),
    ("D-118b", "CC(=O)N1c2ccccc2CCC1", "1-(3,4-dihydroquinolin-1(2H)-yl)ethan-1-one", "1-acetyl-1,2,3,4-tetrahydroquinoline", "p. 567 VERBATIM '1-(3,4-dihydroquinolin-1(2H)-yl)ethan-1-one (PIN)'"),
    ("D-118c", "CC(=O)[Si](C)(C)C", "1-(trimethylsilyl)ethan-1-one", "acetyltri(methyl)silane", "p. 567 VERBATIM '1-(trimethylsilyl)ethan-1-one (PIN)'"),
    ("D-118d", "CC(=O)n1ccnc1", "1-(1H-imidazol-1-yl)ethan-1-one", "1-acetyl-1H-imidazole", "derived (the same rule on an AROMATIC nitrogen, also a hidden amide); OPSIN reads it back"),
    ("D-118e", "O=C(c1ccccc1)N1CCCC1", "phenyl(pyrrolidin-1-yl)methanone", "1-benzoylpyrrolidine", "derived: a one-carbon ketone parent with two different substituents, cited alphabetically"),
    ("D-118f", "CC(=O)N=NC", "1-(methyldiazenyl)ethan-1-one", "acetyl(methyl)diazene", "derived (the azo nitrogen, the case of D-088c with one carbon side)"),
    ("D-118g", "O=C(CCCCCCCCC(=O)N1CC1)N1CC1", "1,10-di(aziridin-1-yl)decane-1,10-dione", "1-[10-(aziridin-1-yl)-10-oxodecanoyl]aziridine",
     "a heldout_v4 corpus row (its PubChem name is the same ketone form); 'di' not 'bis' for a prefix that is compound only because it carries a locant, the rule of round 4"),
    ("D-118x", "O=C(O)CC(=O)N1CCCCC1", "3-oxo-3-(piperidin-1-yl)propanoic acid", "(unchanged)",
     "converse, the one a first draft got wrong: an ACID on the same chain is senior to a pseudoketone (Table 4.1). The ketone plan won because the acid plan died with 'atom 6 owned by two prefixes'"),
    ("D-118y", "NC(=O)CC(=O)N1CCCCC1", "3-oxo-3-(piperidin-1-yl)propanamide", "(unchanged)", "converse: an AMIDE on the same chain is senior to a pseudoketone"),
    ("D-118z", "CC(=O)N1CCC(CC1)C(=O)O", "1-acetylpiperidine-4-carboxylic acid", "(unchanged)", "converse: an acid on the RING keeps the ring as the parent and the N-acetyl as a prefix"),
    ("D-118w", "CC(=O)N1CCCC1=O", "1-acetylpyrrolidin-2-one", "(unchanged)", "converse: a lactam's ring carbonyl is the ketone, and the exocyclic acetyl is a prefix"),
    ("D-118v", "CC(=O)N1CCC(=O)CC1", "1-acetylpiperidin-4-one", "(unchanged)", "converse: a ring ketone is senior to the acyclic pseudoketone"),
    ("D-118u", "CC(=O)NC", "N-methylacetamide", "(unchanged)", "converse: an ACYCLIC amide is an amide, not a pseudoketone"),
    ("D-118t", "CC(=O)OC", "methyl acetate", "(unchanged)", "converse: an ester"),
    ("D-119a", "O=C(n1ccnc1)n1ccnc1", "bis(1H-imidazol-1-yl)methanone", "(a KekulizeException out of the whole naming call)",
     "carbonyldiimidazole, a common reagent, CRASHED the engine: the multiplicative route carved a half-molecule whose aromatic n had lost its H and did not catch the sanitise failure. It then "
     "declined and the generic route named it '1-[(1H-imidazol-1-yl)(oxo)methyl]-1H-imidazole'; the pseudoketone group for TWO ring nitrogens (D-126) makes it the ketone the book prints for the "
     "one-nitrogen case, with 'bis' because the prefix begins with a locant"),
    ("D-119b", "O=C(n1cccc1)n1cccc1", "bis(1H-pyrrol-1-yl)methanone", "(the same crash)", "the pyrrole analogue"),
    # ---- naming round 8, limitations sweep: THE 'e' OF 'ene'/'yne' IS ELIDED BEFORE AN 'amide' OR 'amine' (P-16.7; pdf pp. 646, 525, 76). The assembler's elision skipped
    # every suffix that begins 'amine'/'amide'/'amino', a list meant for the 'amino' PREFIX, so an unsaturated parent kept its 'e' before the two commonest vowel suffixes:
    # acrylamide was 'prop-2-eneamide' and allylamine 'prop-2-ene-1-amine', both of which OPSIN reads and neither of which is a name. Found by probing common compounds, not by
    # a corpus (no corpus row is an enamide). The junctions before a consonant suffix ('but-2-enethioamide', 'but-2-enediamide', 'but-2-enehydrazide') keep their 'e'.
    ("D-120a", "C=CC(N)=O", "prop-2-enamide", "prop-2-eneamide",
     "p. 646 VERBATIM 'prop-2-enamide (PIN)': acrylamide"),
    ("D-120b", "C=CCN", "prop-2-en-1-amine", "prop-2-ene-1-amine",
     "p. 525 VERBATIM 'prop-2-en-1-amine (PIN)': allylamine"),
    ("D-120c", "C=CC(=O)NC", "N-methylprop-2-enamide", "N-methylprop-2-eneamide",
     "p. 646 VERBATIM 'N-methylprop-2-enamide'"),
    ("D-120d", "C=CN", "ethenamine", "etheneamine",
     "derived: the same rule with no locant"),
    ("D-120e", "CC=C(N)C=C", "penta-1,3-dien-3-amine", "penta-1,3-diene-3-amine",
     "derived: a diene ('e' of 'diene')"),
    ("D-120f", "C#CC(N)=O", "prop-2-ynamide", "prop-2-yneamide",
     "derived: the 'yne' infix"),
    ("D-120g", "CC=CC(=O)N1CCCC1", "1-(pyrrolidin-1-yl)but-2-en-1-one", "(unchanged)",
     "converse: a pseudoketone, no amide suffix"),
    ("D-120h", "CC=CC(N)=S", "but-2-enethioamide", "(unchanged)",
     "converse: 'thioamide' begins with a consonant, so the 'e' stays"),
    ("D-120i", "NC(=O)C=CC(N)=O", "but-2-enediamide", "(unchanged)",
     "converse: 'diamide' begins with a consonant"),
    ("D-120j", "CC=CC(=N)N", "but-2-enimidamide", "(unchanged)",
     "converse: 'imidamide' was already elided"),
    ("D-120k", "NC1CCCC=C1", "cyclohex-2-en-1-amine", "(unchanged)",
     "converse: p. 76 VERBATIM 'cyclohex-2-en-1-amine (PIN)', the ring form had it right"),
    ("D-120l", "Nc1ccccc1", "aniline", "(unchanged)",
     "converse: a retained ring amine"),
    # ---- naming round 8, limitations sweep: AN ALKOXY GROUP ON A NITROGEN IS 'methoxy', NOT 'methyloxy'. The ether_prefix branch of plan execution contracts 'methyl'+'oxy' to
    # 'methoxy' (P-63.2.2.2, pdf p. 541: methoxy, ethoxy, propoxy, butoxy and phenoxy are retained, 'fully substitutable'), but an O-attached group whose parent atom is a
    # NITROGEN (an oxime ether, a hydroxylamine ether) reaches the heteroatom-substituent path instead, which only appended 'oxy': '(methyloxyimino)', 'N-(ethyloxy)ethanimine'.
    # Strobilurin and cephalosporin oxime ethers are this shape. The contraction is now one helper used by the heteroatom path; an acyl ('acetyloxy'), a ring attachment
    # ('pyridin-3-yloxy'), and an uncontracted group ('hexyloxy', '(propan-2-yl)oxy') keep their forms.
    ("D-124a", "COC(=O)C(=NOC)c1ccccc1", "methyl (methoxyimino)(phenyl)acetate", "methyl (methyloxyimino)(phenyl)acetate",
     "derived: the oxime ether of a phenylglyoxylate (the strobilurin shape)"),
    ("D-124b", "CON=Cc1ccccc1", "N-methoxy-1-phenylmethanimine", "N-(methyloxy)-1-phenylmethanimine",
     "derived: an oxime ether"),
    ("D-124c", "ClCCON=CC", "N-(2-chloroethoxy)ethanimine", "N-[(2-chloroethyl)oxy]ethanimine",
     "derived: a substituted ethyl contracts too (P-63.2.2.2 'fully substitutable')"),
    ("D-124d", "c1ccccc1ON=CC", "N-phenoxyethanimine", "N-(phenyloxy)ethanimine",
     "derived: phenoxy is retained"),
    ("D-124e", "CC(C)ON=CC", "N-[(propan-2-yl)oxy]ethanimine", "(unchanged)",
     "converse: the book does not contract a locanted group"),
    ("D-124f", "CCCCCCON=CC", "N-(hexyloxy)ethanimine", "(unchanged)",
     "converse: only methoxy to butoxy, phenoxy, are contracted"),
    ("D-124g", "c1ccncc1ON=CC", "N-[(pyridin-3-yl)oxy]ethanimine", "(unchanged)",
     "converse: a ring attachment keeps 'yloxy'"),
    ("D-124h", "CC(=O)ON=CC", "N-(acetyloxy)ethanimine", "(unchanged)",
     "converse: an acyl is 'acetyloxy', never 'acetoxy' here"),
    ("D-124i", "CON1CCCC1", "1-methoxypyrrolidine", "(unchanged)",
     "converse: a ring nitrogen already took the ether_prefix branch"),
    ("D-124j", "CCON=CC", "N-ethoxyethanimine", "N-(ethyloxy)ethanimine",
     "derived: ethoxy"),
    # (D-124, continued: the groups the contraction must and must not reach.)
    ("D-124k", "C1CCC1ON=CC", "N-(cyclobutyloxy)ethanimine", "(unchanged)",
     "converse: 'cyclobutyl' ends in 'butyl' and is a RING attachment, so it keeps 'yloxy' (P-63.2.2.2 contracts acyclic groups)"),
    ("D-124l", "C1CC1ON=CC", "N-(cyclopropyloxy)ethanimine", "(unchanged)",
     "converse: the same for a cyclopropyl"),
    ("D-124m", "CC(C)CON=CC", "N-(2-methylpropoxy)ethanimine", "N-[(2-methylpropyl)oxy]ethanimine",
     "p. 541 VERBATIM '2-methylpropoxy (PIN)' as a prefix: a substituted butyl contracts"),
    ("D-124n", "CCOON=CC", "N-(ethylperoxy)ethanimine", "(unchanged)",
     "converse: an O bonded to O is 'peroxy', whose alkyl is not contracted (the D-065d rule, reached through a nitrogen)"),
    # ---- naming round 8, limitations sweep: AN AMIDE OR AN AMINE WHOSE NITROGEN CARRIES AN ALKOXY GROUP. The amide and amine group definitions require carbon on the nitrogen,
    # so N-methoxy-N-methylacetamide (the Weinreb amide) and N-methoxymethanamine were not an amide and an amine to the engine: a molecule with one nitrogen was named an ESTER
    # OF AZINOUS ACID ('methyl acetylmethylazinite', a name the book reserves for polyazanes, P-67.1.2.6.1, p. 707), and one with two, an amide named as 'carbamoyl' on an
    # aniline: '4-[(methyloxy)carbamoyl]aniline' for 4-amino-N-methoxybenzamide. The book prints the amines: 'N-methoxymethanamine (PIN)' (p. 753), 'N-methoxyethanamine (PIN)'
    # (p. 528), 'N-ethoxyaniline (PIN)' (p. 753). Four group definitions declare the oxygen as the ROOT of the N-substituent (context_indices, the mechanism of the W4b
    # pseudoketones), the demoted N-bearing branch honours that declaration, and the azinite generator declines a nitrogen with no oxo.
    ("D-125a", "CNOC", "N-methoxymethanamine", "methyl methylazinite",
     "p. 753 VERBATIM 'N-methoxymethanamine (PIN)'"),
    ("D-125b", "CCNOC", "N-methoxyethanamine", "methyl ethylazinite",
     "p. 528 VERBATIM 'N-methoxyethanamine (PIN)'"),
    ("D-125c", "c1ccccc1NOCC", "N-ethoxyaniline", "ethyl phenylazinite",
     "p. 753 VERBATIM 'N-ethoxyaniline (PIN)'"),
    ("D-125d", "CON(C)C(C)=O", "N-methoxy-N-methylacetamide", "methyl acetylmethylazinite",
     "derived: the Weinreb amide, the tertiary amide with an alkoxy on the nitrogen"),
    ("D-125e", "CC(=O)NOC", "N-methoxyacetamide", "methyl acetylazinite",
     "derived: the secondary amide"),
    ("D-125f", "CONC(=O)c1ccc(N)cc1", "4-amino-N-methoxybenzamide", "4-[(methyloxy)carbamoyl]aniline",
     "derived: an amide outranks an amine (Table 4.1), so the amide is the parent"),
    ("D-125g", "CON(C)C(=O)CC(=O)O", "3-[methoxy(methyl)amino]-3-oxopropanoic acid", "methyl methylpropanedioylazinite",
     "derived: an ACID outranks the amide; the first draft named this '2-carboxy-N-methoxyacetamide'"),
    ("D-125h", "CON(C)C(=O)c1ccc(C(=O)O)cc1", "4-[methoxy(methyl)carbamoyl]benzoic acid", "methyl (benzene-1,4-dicarbonyl)methylazinite",
     "derived: the same beside a ring acid, as '4-(dimethylcarbamoyl)benzoic acid'"),
    ("D-125i", "CON(C)Cc1ccc(O)cc1", "4-{[methoxy(methyl)amino]methyl}phenol", "methyl [(4-hydroxyphenyl)methyl]methylazinite",
     "derived: an alcohol outranks an amine"),
    ("D-125j", "CCON(CC)C(=O)C1CC1", "N-ethoxy-N-ethylcyclopropanecarboxamide", "ethyl (cyclopropanecarbonyl)ethylazinite",
     "derived: the same amide with a longer alkoxy, an 'azinite' before"),
    ("D-125k", "CON(C)C(=O)N(C)C", "N-methoxy-N,N',N'-trimethylurea", "(unchanged)",
     "converse: a urea carbonyl with an N-alkoxy was already named as a urea"),
    ("D-125x", "CON1CCCC1", "1-methoxypyrrolidine", "(unchanged)",
     "converse: a ring nitrogen with an alkoxy was never affected"),
    ("D-125y", "CN(C)C(C)=O", "N,N-dimethylacetamide", "(unchanged)",
     "converse: an ordinary tertiary amide"),
    ("D-125z", "CC(=O)NO", "N-hydroxyacetamide", "(unchanged)",
     "converse: a hydroxamic acid is its own group"),
    # (D-125, continued: the tertiary amine, which the amide rows do not exercise.)
    ("D-125l", "CN(C)OC", "N-methoxy-N-methylmethanamine", "methyl dimethylazinite",
     "derived from p. 753 'N-methoxymethanamine (PIN)': the tertiary amine with an alkoxy"),
    ("D-125m", "CON(C)Cc1ccccc1", "N-methoxy-N-methyl-1-phenylmethanamine", "methyl benzylmethylazinite",
     "derived: a tertiary amine with a benzyl"),
    # ---- naming round 8, limitations sweep: A CARBONYL BETWEEN TWO RING NITROGENS IS A PSEUDOKETONE TOO (P-64.3.2, pdf p. 567, the one-nitrogen case of D-118):
    # 'bis(1H-imidazol-1-yl)methanone' for carbonyldiimidazole, 'di(piperidin-1-yl)methanone' for 1,1'-carbonyldipiperidine. One more ketone group for a NON-RING carbonyl
    # carbon between two ring nitrogens, both declared as the roots of their substituents. A carbonyl IN a ring (a cyclic urea, hydantoin) is not matched, and an acyclic urea
    # keeps its name.
    ("D-126a", "O=C(N1CCCCC1)N1CCCCC1", "di(piperidin-1-yl)methanone", "1-[(oxo)(piperidin-1-yl)methyl]piperidine",
     "derived from p. 567: the two-nitrogen case of '1-(piperidin-1-yl)propan-1-one (PIN)'; 'di' because 'piperidin-1-yl' begins with a letter"),
    ("D-126b", "O=C(N1CCOCC1)N1CCOCC1", "di(morpholin-4-yl)methanone", "4-[(morpholin-4-yl)(oxo)methyl]morpholine",
     "derived: the morpholine analogue"),
    ("D-126c", "O=C(n1ccnc1)N1CCCCC1", "(1H-imidazol-1-yl)(piperidin-1-yl)methanone", "1-[(1H-imidazol-1-yl)(oxo)methyl]piperidine",
     "derived: two DIFFERENT ring nitrogens, cited alphabetically"),
    ("D-126x", "O=C1NC(=O)CN1", "imidazolidine-2,4-dione", "(unchanged)",
     "converse: hydantoin, the carbonyl is IN the ring"),
    ("D-126y", "O=C1N(C)CCN1C", "1,3-dimethylimidazolidin-2-one", "(unchanged)",
     "converse: a cyclic urea"),
    ("D-126z", "CN(C)C(=O)N(C)C", "N,N,N',N'-tetramethylurea", "(unchanged)",
     "converse: an acyclic urea keeps its name"),
    # ---- naming round 8, limitations sweep: NITRIC AND NITROUS ESTERS ARE NAMED AS ESTERS. The book prints 'pentyl nitrite (PIN)' (P-67.1.3.2, pdf p. 710), and treats
    # nitrates and nitrites as the esters of nitric and nitrous acid (p. 717). The engine's oxoacid ester generator declines every nitrogen centre (the charge-separated
    # [N+](=O)[O-] of a nitrate, and a nitrogen is in most molecules), so a nitrate was '1-(nitrooxy)pentane' and a nitrite '(nitrosooxy)pentane', both of which read back and
    # neither of which is the PIN. Deliberately narrow: ONE such group, on a carbon, in a neutral single-fragment molecule with nothing senior to an ester and no other ester or
    # acid halide; a polynitrate (nitroglycerin needs 'propane-1,2,3-triyl trinitrate') and a nitrate beside an acid or another ester keep their names.
    ("D-123a", "CCCCCON=O", "pentyl nitrite", "1-(nitrosooxy)pentane",
     "p. 710 VERBATIM 'pentyl nitrite (PIN)'"),
    ("D-123b", "CCCCCO[N+](=O)[O-]", "pentyl nitrate", "1-(nitrooxy)pentane",
     "derived from the nitrite: the ester of nitric acid (p. 717)"),
    ("D-123c", "OCCO[N+](=O)[O-]", "2-hydroxyethyl nitrate", "2-(nitrooxy)ethan-1-ol",
     "derived: an alcohol is junior to an ester"),
    ("D-123d", "NCCO[N+](=O)[O-]", "2-aminoethyl nitrate", "2-(nitrooxy)ethan-1-amine",
     "derived: an amine is junior to an ester"),
    ("D-123e", "N#CCCO[N+](=O)[O-]", "2-cyanoethyl nitrate", "3-(nitrooxy)propanenitrile", "derived: a nitrile is junior to an ester (nicorandil's amide is too; its prefix spelling is not this row's business)"),
    ("D-123f", "O=[N+]([O-])OCc1ccccc1", "phenylmethyl nitrate", "[(nitrooxy)methyl]benzene",
     "derived: benzyl nitrate"),
    ("D-123g", "ClCCON=O", "2-chloroethyl nitrite", "1-chloro-2-(nitrosooxy)ethane",
     "derived: a halogen is only a prefix"),
    ("D-123h", "CO[N+](=O)[O-]", "methyl nitrate", "(nitrooxy)methane",
     "derived: the simplest nitrate; the oxoacid ester generator's own docstring names 'methyl nitrate' as the target it declines"),
    ("D-123x", "O=[N+]([O-])OCC(CO[N+](=O)[O-])O[N+](=O)[O-]", "1,2,3-tris(nitrooxy)propane", "(unchanged)",
     "converse: nitroglycerin, three nitrate groups, is not built (it needs a multivalent organyl)"),
    ("D-123y", "OC(=O)CCO[N+](=O)[O-]", "3-(nitrooxy)propanoic acid", "(unchanged)",
     "converse: an acid outranks an ester, so the nitrate is the 'nitrooxy' prefix"),
    ("D-123z", "CC(=O)OCCO[N+](=O)[O-]", "2-(nitrooxy)ethyl acetate", "(unchanged)",
     "converse: another ester of the same class; the carboxylic ester is the parent here"),
    # (D-123, continued: what a nitrate must NOT swallow, one row per blocker, and a ring alkyl.)
    ("D-123i", "O=[N+]([O-])OC1CCCC1", "cyclopentyl nitrate", "(nitrooxy)cyclopentane",
     "derived: a ring alkyl is an ordinary organyl"),
    ("D-123v", "ClC(=O)CCO[N+](=O)[O-]", "3-(nitrooxy)propanoyl chloride", "(unchanged)",
     "converse: an acid halide is senior to an ester"),
    ("D-123u", "OS(=O)(=O)CCO[N+](=O)[O-]", "2-(nitrooxy)ethane-1-sulfonic acid", "(unchanged)",
     "converse: a sulfonic acid is senior to an ester"),
    ("D-123t", "OP(=O)(O)CCO[N+](=O)[O-]", "[2-(nitrooxy)ethyl]phosphonic acid", "(unchanged)",
     "converse: a phosphonic acid is senior to an ester"),
    ("D-123s", "C[N+](C)(C)CCO[N+](=O)[O-]", "trimethyl[2-(nitrooxy)ethyl]ammonium", "(unchanged)",
     "converse: a cation is senior to an ester, and a charged molecule is not this route's"),
    ("D-123r", "O=C(OC)CCO[N+](=O)[O-]", "methyl 3-(nitrooxy)propanoate", "(unchanged)",
     "converse: a carboxylic ester of the same class is the parent"),
    # ---- naming round 8, limitations sweep: AN ACYCLIC ONIUM CATION IS NAMED ON ITS ONIUM CENTRE. Table 4.1 (pdf p. 360) ranks a cation above every acid, amide, nitrile and
    # alcohol, and the book prints the result: 'benzoyldi(methyl)sulfanium (PIN)' (p. 820), '[6-(dimethylsulfaniumyl)hexyl]tri(methyl)phosphanium (PIN)' (p. 834). The engine
    # did it for a nitrogen (its 'aminium' is a suffix, priority 650) and for a ring, but a phosphonium, sulfonium or arsonium beside an acid, amide or alcohol was named on the
    # junior group with the onium as a prefix, '2-(trimethylphosphaniumyl)acetamide', which reads back and is not preferred. The onium parent plan existed and lost at the first
    # ranking tier; it now takes the cation band when the onium centre is the ONLY genuine charge in the molecule (an anion outranks a cation, so a betaine is named on its
    # anion, and two cations are a different plan kind).
    ("D-122a", "C[P+](C)(C)CC(N)=O", "(2-amino-2-oxoethyl)tri(methyl)phosphanium", "2-(trimethylphosphaniumyl)acetamide",
     "derived from Table 4.1 and the printed 'benzoyldi(methyl)sulfanium (PIN)' style"),
    ("D-122b", "C[S+](C)CCO", "(2-hydroxyethyl)di(methyl)sulfanium", "2-(dimethylsulfaniumyl)ethan-1-ol",
     "derived: an alcohol is junior to a cation"),
    ("D-122c", "C[P+](C)(C)CC(=O)O", "(carboxymethyl)tri(methyl)phosphanium", "(trimethylphosphaniumyl)acetic acid",
     "derived: an acid is junior to a cation (the ring form '4-carboxy-1-methylpyridin-1-ium chloride (PIN)' is printed, p. 580)"),
    ("D-122d", "C[As+](C)(C)CC(=O)O", "(carboxymethyl)tri(methyl)arsanium", "(trimethylarsaniumyl)acetic acid",
     "derived: the same for an arsonium"),
    ("D-122e", "C[P+](C)(C)CC(=O)O.[Cl-]", "(carboxymethyl)tri(methyl)phosphanium chloride", "(trimethylphosphaniumyl)acetic acid chloride",
     "the salt of D-122c"),
    ("D-122x", "C[P+](C)(C)CC(=O)[O-]", "(trimethylphosphaniumyl)acetate", "(unchanged)",
     "converse: an anion outranks a cation, so the betaine is named on its anion"),
    ("D-122y", "C[P+](C)(C)CCC[P+](C)(C)C", "trimethyl[3-(trimethylphosphaniumyl)propyl]phosphanium", "(unchanged)",
     "converse: two cations are not this band"),
    ("D-122z", "C[S+](C)C(=O)c1ccccc1", "benzoyldi(methyl)sulfanium", "(unchanged)",
     "converse: p. 820 VERBATIM 'benzoyldi(methyl)sulfanium (PIN)'"),
    ("D-122w", "C[N+](C)(C)CCC(N)=O", "3-amino-N,N,N-trimethyl-3-oxopropan-1-aminium", "(unchanged)",
     "converse: a nitrogen's cation is a suffix and was already senior"),
    ("D-122v", "CCC[P+](C)(C)C", "trimethyl(propyl)phosphanium", "(unchanged)",
     "converse: no junior group, the same plan won before"),
    # (D-122, continued: a nitro group is not a second charge, and what the band must leave alone. THREE MUTANTS OF THE BAND ARE EQUIVALENT (measured, four others are caught):
    # counting an ANION centre (a boranuide is named on its anion by its own route, so the same name results), dropping the condition that the charge is on the parent centre,
    # and dropping the parent-kind condition; no input separates them today, and they are kept because each states the contract.)
    ("D-122f", "C[P+](C)(C)Cc1cc(ccc1C(N)=O)[N+](=O)[O-]", "[(2-carbamoyl-5-nitrophenyl)methyl]tri(methyl)phosphanium", "4-nitro-2-[(trimethylphosphaniumyl)methyl]benzamide",
     "derived: a nitro group is a charge-separated NEUTRAL group, so the phosphonium is still the only genuine charge"),
    ("D-122u", "C[B-](C)(C)CC(N)=O", "(2-amino-2-oxoethyl)trimethylboranuide", "(unchanged)",
     "converse: an anion centre is named on its anion by its own route"),
    ("D-122t", "C[Si](C)(C)C[P+](C)(C)C", "trimethyl[(trimethylsilyl)methyl]phosphanium", "(unchanged)",
     "converse: the cation's centre is the parent, not another heteroatom centre"),
    # ---- naming round 8, limitations sweep: MIXED-CLASS ACID POLYANIONS. acid_anion_route returned None for a molecule whose anions are of two classes (a carboxylate and a
    # sulfonate) or an olate beside an acid anion, so no route owned it and the plan search named it '1-[oxido(oxo)methyl]-4-(oxidosulfonyl)benzene', which round-trips and is
    # not a name. The carved route now owns it: the senior acid anion is the principal group (P-72.7 e, pdf p. 815: '3-oxidonaphthalene-2-carboxylate (PIN)', carboxylate senior
    # to olate) and the junior anion is its anionic PREFIX, 'sulfonato' / 'oxido' (P-65.6.2.3.1, p. 619, and P-72.6, p. 814), never the neutral 'sulfo' / 'hydroxy', which would
    # drop the charge. 'sulfonato' and 'carboxylato' are ONE group each and are printed bare (p. 1020: '2-O-sulfonato-alpha-D-glucopyranose').
    ("D-121a", "[O-]C(=O)c1ccc(cc1)S(=O)(=O)[O-]", "4-sulfonatobenzoate", "1-[oxido(oxo)methyl]-4-(oxidosulfonyl)benzene",
     "derived from p. 619 (the prefix 'sulfonato') and P-72.7 (e): the carboxylate outranks the sulfonate"),
    ("D-121b", "[O-]C(=O)c1cc2ccccc2cc1[O-]", "3-oxidonaphthalene-2-carboxylate", "3-[oxido(oxo)methyl]naphthalen-2-olate",
     "p. 815 VERBATIM '3-oxidonaphthalene-2-carboxylate (PIN)'"),
    ("D-121c", "[O-]C(=O)c1ccccc1[O-]", "2-oxidobenzoate", "2-[oxido(oxo)methyl]benzen-1-olate",
     "the salicylate dianion, derived from D-121b's rule"),
    ("D-121d", "[NH3+]C(C[O-])C([O-])=O", "2-azaniumyl-3-oxidopropanoate", "2-azaniumyl-3-oxido-3-oxopropan-1-olate",
     "the serinate zwitterion as drawn: the cation is the 'azaniumyl' prefix as in aspartate"),
    ("D-121e", "O=C([O-])CS(=O)(=O)[O-]", "sulfonatoacetate", "1-oxido-2-(oxidosulfonyl)-1-oxoethane",
     "derived: a retained acetic acid takes the prefix bare, as 'sulfoacetic acid' does"),
    ("D-121f", "[O-]C(=O)c1cc(cc(c1)S(=O)(=O)[O-])S(=O)(=O)[O-]", "3,5-disulfonatobenzoate", "1-[oxido(oxo)methyl]-3,5-bis(oxidosulfonyl)benzene",
     "derived: the class decides the parent (carboxylate), not the count of sulfonates"),
    ("D-121g", "[O-]C(=O)CC(C(=O)[O-])S(=O)(=O)[O-]", "2-sulfonatobutanedioate", "1,4-dioxido-2-(oxidosulfonyl)-1,4-dioxobutane",
     "derived: two carboxylates and a sulfonate; the carboxylates are the suffix"),
    ("D-121h", "[O-]C(=O)c1ccc(cc1)S(=O)(=O)[O-].[Na+].[Na+]", "disodium 4-sulfonatobenzoate", "disodium 1-[oxido(oxo)methyl]-4-(oxidosulfonyl)benzene",
     "the salt: the cations do not change the anion's name"),
    ("D-121x", "OC(=O)c1ccc(cc1)S(=O)(=O)[O-]", "4-carboxybenzene-1-sulfonate", "(unchanged)",
     "converse: ONE anion beside a neutral acid is the D-095 family, an anion outranks an acid"),
    ("D-121y", "[O-]C(=O)c1ccc(cc1)S(=O)(=O)O", "4-sulfobenzoate", "(unchanged)",
     "converse: the neutral sulfonic acid keeps 'sulfo'"),
    ("D-121z", "[O-]C(=O)c1ccc(cc1)C(=O)[O-]", "benzene-1,4-dicarboxylate", "(unchanged)",
     "converse: one class, the classifier route"),
    ("D-121w", "[O-]S(=O)(=O)c1ccc(cc1)S(=O)(=O)[O-]", "benzene-1,4-disulfonate", "(unchanged)",
     "converse: one class"),
    ("D-121v", "O=C([O-])c1ccccc1O", "2-hydroxybenzoate", "(unchanged)",
     "converse: an anion and a neutral OH"),
    # (D-121, continued: two more shapes the route now owns, and what it must leave alone.)
    ("D-121i", "[O-]CCC(=O)[O-]", "3-oxidopropanoate", "3-oxido-3-oxopropan-1-olate",
     "derived: a chain olate beside a carboxylate, the same rule as D-121b"),
    ("D-121j", "C[N+](C)(C)CC([O-])C(=O)[O-]", "2-oxido-3-(trimethylazaniumyl)propanoate", "1-oxido-1-oxo-3-(trimethylazaniumyl)propan-2-olate",
     "derived: an olate and a carboxylate beside a cation, net negative"),
    ("D-121u", "[S-]c1ccccc1C(=O)[O-]", "2-[oxido(oxo)methyl]benzene-1-thiolate", "(unchanged)",
     "converse and OPEN: a THIOLATE beside an acid anion is not claimed, its anionic prefix ('sulfanido') is not built; the name reads back and is not preferred"),
    # ---- naming round 8, limitations sweep: TWO ADJACENT ACYCLIC KETONES ARE A DIONE. Perception's ketone pattern, [#6][CX3](=O)[#6], matches biacetyl twice and the two
    # matches share their middle carbons, so deconfliction kept ONE and the second carbonyl fell to an 'oxo' prefix: 'CC(=O)C(=O)C' was '3-oxobutan-2-one' and benzil
    # '2-oxo-1,2-diphenylethan-1-one', where the book prints 'butane-2,3-dione (PIN) (not biacetyl)' and 'diphenylethanedione (PIN) (not benzil)' (p. 559). The ring case had
    # its own repair (_synthesise_ring_carbonyl_fgs, for 1,2-cyclohexanedione); it now also promotes the unclaimed carbonyl of an acyclic carbon with two carbon neighbours.
    # Found by probing common compounds.
    ("D-127a", "CC(=O)C(=O)C", "butane-2,3-dione", "3-oxobutan-2-one",
     "p. 559 VERBATIM 'butane-2,3-dione (PIN)': biacetyl"),
    ("D-127b", "CCC(=O)C(=O)CC", "hexane-3,4-dione", "4-oxohexan-3-one",
     "derived: the same, two ethyl flanks"),
    ("D-127c", "CC(=O)C(=O)C(C)=O", "pentane-2,3,4-trione", "3-oxopentane-2,4-dione",
     "derived: three adjacent carbonyls"),
    ("D-127d", "CC(=O)C(=O)c1ccccc1", "1-phenylpropane-1,2-dione", "1-oxo-1-phenylpropan-2-one",
     "derived: an aryl flank"),
    ("D-127e", "CC(C)C(=O)C(=O)C(C)C", "2,5-dimethylhexane-3,4-dione", "2,5-dimethyl-4-oxohexan-3-one",
     "derived: branched flanks"),
    ("D-127f", "CC(=O)C(=O)CC(C)=O", "hexane-2,3,5-trione", "3-oxohexane-2,5-dione",
     "derived: an adjacent pair beside a separate ketone"),
    ("D-127x", "CC(=O)CC(C)=O", "pentane-2,4-dione", "(unchanged)",
     "converse: separated ketones were always a dione"),
    ("D-127y", "CC(=O)C(=O)O", "2-oxopropanoic acid", "(unchanged)",
     "converse: an acid outranks the ketone, so the oxo stays a prefix"),
    ("D-127z", "O=CC(=O)C", "2-oxopropanal", "(unchanged)",
     "converse: an aldehyde outranks the ketone"),
    ("D-127w", "O=C1C(=O)CCCC1", "cyclohexane-1,2-dione", "(unchanged)",
     "converse: the ring case, repaired before"),
    # (D-127, continued: benzil, whose printed name omits the locants, and an enone.)
    ("D-127g", "O=C(c1ccccc1)C(=O)c1ccccc1", "1,2-diphenylethane-1,2-dione", "2-oxo-1,2-diphenylethan-1-one",
     "p. 559 prints 'diphenylethanedione (PIN) (not benzil)' WITHOUT the locants (a locant-omission rule for a symmetrical ethane, not built); the structure and the dione are the book's"),
    ("D-127v", "C=CC(=O)C(=O)C", "pent-4-ene-2,3-dione", "3-oxopent-4-en-2-one",
     "derived: an adjacent pair beside a double bond"),
    # ---- naming round 8, limitations sweep: A CARBONIC ACID DIESTER IS 'dimethyl carbonate'. Carbonic acid is a functional parent whose esters are named as esters of the
    # anion, 'sodium hydrogen carbonate (PIN)' (P-65.6.2.3, pdf p. 620) and the book's printed ester words 'O-ethyl O-methyl (18O1)carbonate' (p. 862), 'bis(oxomethyl)
    # carbonate' (p. 693). The engine had no carbonate ester at all: dimethyl carbonate, a common solvent and reagent, was 'dimethoxyoxomethane', diphenyl carbonate
    # '[(oxo)(phenoxy)methoxy]benzene', di-tert-butyl carbonate a nine-part prefix name. Deliberately narrow: ONE acyclic carbonic ester group on organyl groups that are not
    # acyl (a mixed anhydride is another class), in a neutral molecule with no acid, acid halide, other ester, sulfonic or phosphorus acid beside it; a cyclic carbonate
    # ('1,3-dioxolan-2-one') keeps its ring name. The hydrogen ester ('methyl hydrogen carbonate') is the same generator. Chloroformates ('methyl carbonochloridate') are NOT
    # built.
    ("D-128a", "COC(=O)OC", "dimethyl carbonate", "dimethoxyoxomethane",
     "derived from 'sodium hydrogen carbonate (PIN)' (p. 620) and the ester-word style of P-65.6.3"),
    ("D-128b", "CCOC(=O)OC", "ethyl methyl carbonate", "[methoxy(oxo)methoxy]ethane",
     "derived: two different organyl words, alphabetical"),
    ("D-128c", "O=C(Oc1ccccc1)OC", "methyl phenyl carbonate", "[methoxy(oxo)methoxy]benzene",
     "derived: an aryl word"),
    ("D-128d", "CC(C)(C)OC(=O)OC(C)(C)C", "bis(2-methylpropan-2-yl) carbonate", "2-methyl-2-{[(2-methylpropan-2-yl)oxy](oxo)methoxy}propane",
     "derived: a compound word takes 'bis'"),
    ("D-128e", "O=C(OCC=C)OCC=C", "di(prop-2-en-1-yl) carbonate", "3-{(oxo)[(prop-2-en-1-yl)oxy]methoxy}prop-1-ene",
     "derived: diallyl carbonate"),
    ("D-128f", "OC(=O)OC", "methyl hydrogen carbonate", "methoxymethanoic acid",
     "derived from 'sodium hydrogen carbonate (PIN)': the acid ester keeps its hydrogen as a word"),
    ("D-128g", "COC(=O)OCCC#N", "(2-cyanoethyl) methyl carbonate", "3-[methoxy(oxo)methoxy]propanenitrile",
     "derived: a nitrile is junior to an ester; a compound word is enclosed beside a second word, as in the engine's '(2-chloroethyl) methyl sulfate'"),
    ("D-128x", "O=C1OCCO1", "1,3-dioxolan-2-one", "(unchanged)",
     "converse: a CYCLIC carbonate keeps its ring name"),
    ("D-128y", "COC(=O)OCC(=O)O", "[methoxy(oxo)methoxy]acetic acid", "(unchanged)",
     "converse: an acid outranks the ester"),
    ("D-128z", "COC(=O)OCC(=O)OC", "methyl [methoxy(oxo)methoxy]acetate", "(unchanged)",
     "converse: another carboxylic ester is the parent"),
    ("D-128w", "CC(=O)OC(=O)OC", "1-[methoxy(oxo)methoxy]-1-oxoethane", "(unchanged)",
     "converse: a mixed anhydride (an acyl on the oxygen) is another class; not built"),
    ("D-128v", "O=C(OC)N(C)C", "methyl dimethylcarbamate", "(unchanged)",
     "converse: a carbamate is its own group"),
    # (D-128, continued: two carbonate groups are not named by this generator.)
    ("D-128u", "COC(=O)OCCOC(=O)OC", "1,2-bis[methoxy(oxo)methoxy]ethane", "(unchanged)",
     "converse: TWO carbonate groups; the first one's remainder holds the second, which is another ester, so it declines"),
    # ---- naming round 8, limitations sweep: THE ACYL PREFIX OF A RING-NITROGEN AMIDE IS 'piperidine-1-carbonyl'. The book prints it as the acyl group of the ring's
    # N-carboxylic acid: 'piperidine-1-carbohydrazide (PIN) [not (piperidine-1-carbonyl)hydrazine]' (P-65.1.7.3, pdf p. 667), beside 'pyridine-3-carbonyl' for the carbon-
    # attached ring (p. 622), which the engine already wrote. A formyl on a ring NITROGEN was named on the methane parent, '(oxo)(piperidin-1-yl)methyl', which reads back and
    # is not the prefix; amides of piperidine, morpholine, pyrrolidine and piperazine on a benzoic acid are the commonest drug-like instance, and no corpus row has one. A pre-
    # plan helper takes a fragment that is exactly a carbonyl carbon, its oxygen and ONE ring system joined through a neutral ring nitrogen, names the ring as a substituent and
    # renames its '-yl' by the acid rule ('-yl' becomes 'e-<locant>-carbonyl').
    ("D-129a", "OC(=O)c1ccc(cc1)C(=O)N1CCCCC1", "4-(piperidine-1-carbonyl)benzoic acid", "4-[(oxo)(piperidin-1-yl)methyl]benzoic acid",
     "p. 667 prints the prefix '(piperidine-1-carbonyl)'"),
    ("D-129b", "OC(=O)c1ccc(cc1)C(=O)N1CCOCC1", "4-(morpholine-4-carbonyl)benzoic acid", "4-[(morpholin-4-yl)(oxo)methyl]benzoic acid",
     "derived: the same, a heteroatom in the ring, locant 4"),
    ("D-129c", "OC(=O)c1ccc(cc1)C(=O)N1CCCC1", "4-(pyrrolidine-1-carbonyl)benzoic acid", "4-[(oxo)(pyrrolidin-1-yl)methyl]benzoic acid",
     "derived"),
    ("D-129d", "OC(=O)c1ccc(cc1)C(=O)n1ccnc1", "4-(1H-imidazole-1-carbonyl)benzoic acid", "4-[(1H-imidazol-1-yl)(oxo)methyl]benzoic acid",
     "derived: an AROMATIC ring nitrogen"),
    ("D-129e", "OC(=O)c1ccc(cc1)C(=O)N1CCN(C)CC1", "4-(4-methylpiperazine-1-carbonyl)benzoic acid", "4-[(4-methylpiperazin-1-yl)(oxo)methyl]benzoic acid",
     "derived: a substituted ring keeps its prefix"),
    ("D-129f", "OC(=O)c1ccc(cc1)C(=O)N1C(=O)CCC1", "4-(2-oxopyrrolidine-1-carbonyl)benzoic acid", "4-[(oxo)(2-oxopyrrolidin-1-yl)methyl]benzoic acid",
     "derived: an N-acyl lactam"),
    ("D-129g", "NC(=O)c1ccc(cc1)C(=O)N1CCCCC1", "4-(piperidine-1-carbonyl)benzamide", "4-[(oxo)(piperidin-1-yl)methyl]benzamide",
     "derived: beside an amide parent"),
    ("D-129h", "OC(=O)C1CCCCC1C(=O)N1CCCCC1", "2-(piperidine-1-carbonyl)cyclohexane-1-carboxylic acid", "2-[(oxo)(piperidin-1-yl)methyl]cyclohexane-1-carboxylic acid",
     "derived: on a saturated ring"),
    ("D-129x", "OC(=O)CCC(=O)N1CCCC1", "4-oxo-4-(pyrrolidin-1-yl)butanoic acid", "(unchanged)",
     "converse: on a CHAIN acid the amide carbon is in the parent, so 'oxo' plus the ring prefix is right"),
    ("D-129y", "OC(=O)c1ccc(cc1)C(=O)C(C)C", "4-(2-methylpropanoyl)benzoic acid", "(unchanged)",
     "converse: an ordinary acyl group is not a ring nitrogen's"),
    ("D-129z", "OC(=O)c1ccc(cc1)C(=O)c1ccncc1", "4-(pyridine-4-carbonyl)benzoic acid", "(unchanged)",
     "converse: the carbon-attached ring acyl was already right (p. 622)"),
    ("D-129w", "OC(=O)c1ccc(cc1)C(=O)N(C)C", "4-(dimethylcarbamoyl)benzoic acid", "(unchanged)",
     "converse: an acyclic amide is 'carbamoyl'"),
    # Round 9 (admissions ledger, item "carbamimidoyl-locant"):
    ("D-131", "CCN=C(N)C1(C(=N)N(C)C)CCCCC1",
     "N'-ethyl-N'',N''-dimethylcyclohexane-1,1-dicarboximidamide",
     "N'-ethyl-N,N-dimethylcyclohexane-1,1-dicarboximidamide",
     "engine.py's _role_primes assigned amino=N/imino=N' by ROLE alone, "
     "ignoring which of the two identical carboximidamide instances at the "
     "same parent position (1,1-) an atom belonged to, so both instances' "
     "primes collided and OPSIN put both substituents on the same group; "
     "instances sharing a parent position are now ordered by anchor atom "
     "index and each later instance's role primes are shifted by two more "
     "prime marks (N/N' -> N''/N'''), verified via OPSIN round-trip"),
    # Round 9 (admissions ledger, item "naphthalene-ring-drop", target_source
    # = "none" -- wrong molecule only, no PIN claimed or sourced). The
    # multiplicative linker builder's _divalent_linker walked the SHORTEST
    # path between the two attachment atoms; on a naphthalene-2,3-diyl
    # linker that path is the single ortho bond across ONE ring, so the
    # entire OTHER fused ring (4 of naphthalene's 10 ring atoms) was
    # silently treated as "off the path, and merely aromatic" and dropped --
    # "2,2'-(1,2-phenylene)diacetic acid" names plain benzene-1,2-
    # diylbis(acetic acid), a different, smaller molecule (verified via
    # OPSIN: different structure). multiplicative.py's new
    # _fused_ring_count check declines whenever the linker's skeleton spans
    # more than one SSSR ring, the same declining style the existing "a
    # ring other than benzene in the linker" check already uses. The engine
    # falls back to substitutive naming (one arm as parent, the ring plus
    # the other arm as one substituent), which keeps every ring atom;
    # verified via OPSIN round-trip. The preferred multiplicative form
    # ('naphthalene-2,3-diyldiacetic acid') needs fused-ring-system linker
    # naming, which P-15.3 multiplicative constructions on a fused ring
    # were explicitly out of round 9's scope (the plan's seed-list note) --
    # not tracked here without a sourced target to check it against.
    ("D-132", "O=C(O)Cc1cc2ccccc2cc1CC(=O)O", "[3-(carboxymethyl)naphthalen-2-yl]acetic acid",
     "2,2'-(1,2-phenylene)diacetic acid",
     "no printed or derived target (target_source: none); this row exists "
     "to catch a regression back to the wrong molecule, not to claim IUPAC "
     "preference"),
    # Round 9 (admissions ledger, item "sulfinyl-bromide", target_source =
    # "none" -- wrong molecule only). engine.py's {R}sulfonyl/{R}sulfinyl
    # substituent shortcut assumed S has exactly one substituent beside its
    # oxo oxygens; on a hypervalent centre with MORE substituents (here:
    # =N-CH3, Br, and -NH-CH3 beside =O) it silently kept whichever one
    # GetNeighbors() happened to reach first and dropped the rest -- the
    # bromine AND the S=N double bond both vanished, "[(methylaminosulfinyl)
    # amino]methane" (verified via OPSIN: a different, smaller molecule).
    # The new _sulfonyl_sulfinyl_has_single_substituent guard declines the
    # shortcut whenever S carries more than one non-oxo substituent, the
    # same declining style D-130's _linker_has_imine and D-132's
    # _fused_ring_count use. There is no OTHER substituent-naming route in
    # this engine for a sulfinimidoyl/sulfonimidoyl-halide shape (S(=O)(=N-)
    # (Hal)(N<)) -- building one is a separate, unbuilt gap -- so declining
    # here surfaces an honest naming failure instead of a wrong molecule.
    # Verified: RoundTrip classifies the result PARSER_FAILED, never a false
    # MATCH; the wrong molecule this item was admitted for cannot recur.
    ("D-133", "CN=S(=O)(Br)NC", "{[NAMING ERROR: No valid naming plan found for CN=S(N)(=O)Br]}methane",
     "[(methylaminosulfinyl)amino]methane",
     "no printed or derived target (target_source: none); an honest naming "
     "failure (RoundTrip.PARSER_FAILED) replaces the wrong molecule, which "
     "is what this item was admitted to fix -- a real sulfinimidoyl/"
     "sulfonimidoyl-halide name is a separate, unbuilt gap"),
    # Round 9 (admissions ledger, item "phosphine-oxide-trihydrazide",
    # target_source = "none" -- wrong molecule only). A P(V) phosphine oxide
    # bearing three hydrazino substituents named as a trivalent P(III)
    # phosphane via multiplicative.py's _polyvalent_linker: the P=O oxygen is
    # stripped from the linker's "skeleton" before the linker is named
    # (_linker_name strips oxo atoms for every case, including the plain
    # trivalent one where there IS no oxo to strip), and nothing checked
    # whether that stripped =O should have blocked the construction --
    # "1,1',1''-phosphanetriyltris(1-methylhydrazine)" (verified via OPSIN: a
    # different molecule, no P=O at all). The new _linker_has_phosphine_oxide
    # check declines whenever the linker carries a P=O, the same declining
    # style _linker_has_carbonyl and _linker_has_imine already use. The
    # engine falls back to substitutive naming that keeps the P=O; verified
    # via OPSIN round-trip.
    ("D-134", "CN(N)P(=O)(N(C)N)N(C)N",
     "1-methyl-1-[bis(1-methylhydrazinyl)(oxo)phosphanyl]hydrazine",
     "1,1',1''-phosphanetriyltris(1-methylhydrazine)",
     "no printed or derived target (target_source: none); this row exists "
     "to catch a regression back to the wrong molecule, not to claim IUPAC "
     "preference"),
    # Round 9 (admissions ledger, item "peptide-acyl-naming", target_source =
    # "book:p.1048"). Every one of B2's 20 rule-built dipeptides (20/20) named
    # with fully systematic substitutive nomenclature instead of the Blue
    # Book's retained "-yl" acyl convention for peptide bonds (P-103.2.5's
    # rule; P-103.3.2's own worked example, verbatim, is THIS exact row:
    # "glycine + alanine -> glycylalanine (PIN)", pdf p. 1048). A new module
    # (perception/fg/peptide_acyl.py) matches a dipeptide's two residues
    # against a closed table of the 20 proteinogenic amino acids (exact
    # canonical structure, stereo included) and, on a match, emits the
    # retained acyl-plus-parent form directly -- a preference gap, not a
    # wrong-molecule one (the systematic name was always structurally
    # correct), but total within the round's own worked example.
    ("D-135", "NCC(=O)N[C@@H](C)C(=O)O", "glycylalanine",
     "2-[(2-amino-1-oxoethyl)amino]propanoic acid",
     "P-103.3.2 (pdf p. 1048), verbatim 'glycine + alanine -> glycylalanine "
     "(PIN)'; verified via OPSIN round-trip"),
    # Round 9 (admissions ledger, item "charge-alkynyl-dianion", target_source
    # = "none"). Ethynediide ([C-]#[C-], a simple dianion) named as neutral
    # ethyne, both charges silently dropped: the existing alkynyl-anion
    # classifier's mono-anion gate (exactly one charged carbon, one neutral)
    # correctly declined (there is no neutral carbon at all here), and
    # nothing else in charge_perception.py claimed the shape.
    # _classify_alkynyl_anion now also detects the symmetric di-anion and
    # emits the pre-cooked surface name directly; verified via OPSIN
    # round-trip.
    ("D-136", "[C-]#[C-]", "ethynediide", "ethyne",
     "no printed or derived target (target_source: none); this row exists "
     "to catch a regression back to the wrong molecule"),
    # Round 9 (admissions ledger, item "charge-phosphide-anion", target_source
    # = "none"). A bicyclic phosphide anion (1-phosphabicyclo[2.2.2]octan-1-
    # uide) named as the neutral phosphane, the charge dropped: no classifier
    # existed for phosphorus-centred anions at all, unlike the carbon- and
    # nitrogen-centred ones. A new _classify_phosphide_anion (mirroring
    # _classify_amine_anion's shape) plus _render_phosphide_anion (mirroring
    # _render_simple_carbon's "name as substituent, strip yl, append suffix"
    # technique, but suffix "uide" -- a skeletal-replacement parent takes the
    # P-73 linking "u" -- and a phosphorus-specific neutralization that
    # REMOVES the anion's own H rather than keeping it, see
    # _neutralized_site_changes) reaches the exact printed PIN; verified via
    # OPSIN round-trip.
    ("D-137", "C1C[PH-]2CCC1CC2", "1-phosphabicyclo[2.2.2]octan-1-uide",
     "1-phosphabicyclo[2.2.2]octane",
     "P-73 (skeletal-replacement anion, verified via OPSIN); the same "
     "structure and name appear in the Blue Book harvest (bb-4ec6c6c83b27)"),
    # Round 9 (admissions ledger, item "charge-imine-anion", target_source =
    # "none"). Butaniminide (CCCC=[N-], an imine-nitrogen anion) named as
    # neutral 1-iminobutane, the charge dropped: the amine-anion classifier
    # requires a SINGLE N-C bond and correctly declined (this N's only bond
    # is a double one), and nothing else claimed the shape -- a gap between
    # the amine-anion and amide-anion classifiers, neither of which covers
    # an imine-type nitrogen anion. A new _classify_imine_anion /
    # _render_imine_anion pair mirrors _classify_amine_anion /
    # _render_amine_anion exactly, plus a new
    # ("imine", OutputForm.ANION): "iminide" SUFFIX_VARIANT_TABLE entry
    # (assembly.py) mirroring the existing "amine"/"aminide" one; verified
    # via OPSIN round-trip.
    ("D-138", "CCCC=[N-]", "butan-1-iminide", "1-iminobutane",
     "no printed or derived target (target_source: none); this row exists "
     "to catch a regression back to the wrong molecule"),
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
    ("D-088b", "CCOC(=O)NN", "ethyl hydrazinecarboxylate", "(ethoxycarbonyl)hydrazine",
     "the ester of hydrazinecarboxylic acid; its anion is not nameable yet "
     "('oxidooxomethylhydrazine'), so no ester plan is offered"),
    ("D-088d", "O=C(NNC)c1ccc(C(=O)O)cc1", "4-(2-methylhydrazine-1-carbonyl)benzoic acid",
     "4-[(2-methylhydrazinyl)(oxo)methyl]benzoic acid",
     "derived from 'hydrazinecarbonyl (preferred prefix)' (p. 668). PARTLY FIXED in round 8 (D-117f): the acid is now the parent, as Table 4.1 requires (it was "
     "'4-carboxy-N'-methylbenzohydrazide', the hydrazide ABOVE the acid); what remains is the SPELLING of the prefix, an acyl-style '(2-methylhydrazinyl)(oxo)methyl' where the book's is "
     "'2-methylhydrazine-1-carbonyl'"),
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
    # Round 9 (admissions ledger, item "carbodiimide"): PARTLY FIXED. The
    # admission's own defect -- the multiplicative-linker route silently
    # treating N=C=N as a neutral bridge between two identical rings, giving
    # the WRONG STRUCTURE "1,1'-[methylenebis(azanediyl)]dicyclohexane" -- is
    # resolved (see test_a_symmetric_carbodiimide_is_no_longer_a_wrong_molecule
    # below): multiplicative.py's _linker_has_imine now declines that route
    # the same way _linker_has_carbonyl already declines it for a ketone
    # linker. What remains open is reaching the PIN itself: the engine falls
    # back to a substitutive name, "{[(cyclohexylimino)methylidene]amino}
    # cyclohexane" -- structurally correct, not preferred. Measured:
    # Perception(mol).fgs.detected_fgs is EMPTY for DCC in every context
    # tried, not only the multiplicative-decomposition one, so the imine FG
    # never becomes a suffix candidate at all -- a narrower, separate
    # candidate-generation question than this item's admission reason.
    ("D-130", "C(=NC1CCCCC1)=NC1CCCCC1", "dicyclohexylmethanediimine",
     "1,1'-[methylenebis(azanediyl)]dicyclohexane",
     "P-62.3.1.4 (pdf p. 528), verbatim 'dicyclohexylmethanediimine (PIN)'; "
     "today's output is '{[(cyclohexylimino)methylidene]amino}cyclohexane' "
     "-- the WRONG MOLECULE this item was admitted for is fixed, the PIN is "
     "a separate, still-open gap (imine FG perception is empty for this "
     "structure in every context, not only the multiplicative one)"),
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


def test_a_symmetric_carbodiimide_is_no_longer_a_wrong_molecule():
    """D-130's admission reason (carbodiimide): DCC named as a saturated
    bis-amine via the multiplicative-linker route, "1,1'-[methylenebis
    (azanediyl)]dicyclohexane" -- verified via OPSIN as a DIFFERENT molecule
    from the input (a CH2 bridge, no N=C=N). That specific wrong string must
    never come back, regardless of whether the engine later reaches the PIN
    (D-130, still open in OPEN above)."""
    wrong_former_output = "1,1'-[methylenebis(azanediyl)]dicyclohexane"
    got = name_smiles("C(=NC1CCCCC1)=NC1CCCCC1")
    assert got != wrong_former_output
    # The specific structurally-correct fallback measured 2026-09-22, pinned
    # so a further improvement toward the PIN is a deliberate D-130 update,
    # not a silent drift this test stays blind to either way.
    assert got == "{[(cyclohexylimino)methylidene]amino}cyclohexane"


def test_a_fused_ring_linker_no_longer_drops_a_ring():
    """D-132's admission reason (naphthalene-ring-drop): the multiplicative
    linker builder's shortest-path walk crossed a fused ring's ortho bond and
    silently dropped the OTHER ring entirely -- verified via OPSIN as a
    DIFFERENT, smaller molecule (plain benzene, not naphthalene). That wrong
    string must never come back."""
    wrong_former_output = "2,2'-(1,2-phenylene)diacetic acid"
    got = name_smiles("O=C(O)Cc1cc2ccccc2cc1CC(=O)O")
    assert got != wrong_former_output
    assert got == "[3-(carboxymethyl)naphthalen-2-yl]acetic acid"


def test_a_single_benzo_ring_linker_still_uses_phenylene():
    """Converse of D-132: the new fused-ring check (multiplicative.py's
    _fused_ring_count) must decline ONLY when the linker's skeleton spans
    more than one SSSR ring. A single, non-fused ortho-substituted benzene
    ring linker -- structurally identical to the wrong output above, minus
    the second ring -- is the legitimate case '2,2'-(1,2-phenylene)diacetic
    acid' was built for, and must still reach it."""
    assert name_smiles("O=C(O)Cc1ccccc1CC(=O)O") == "2,2'-(1,2-phenylene)diacetic acid"


def test_a_peri_fused_linker_also_keeps_every_ring_atom():
    """A second fused-ring converse of D-132, with the two arms attached
    across the ring-fusion peri positions (naphthalene-1,8-diyl) rather than
    D-132's 2,3-diyl -- a different attachment geometry on the same fused
    system, to check the decline is not narrowly tuned to one case."""
    got = name_smiles("O=C(O)Cc1cccc2cccc(CC(O)=O)c12")
    assert got == "[8-(carboxymethyl)naphthalen-1-yl]acetic acid"


def test_a_hypervalent_sulfinyl_no_longer_drops_atoms():
    """D-133's admission reason (sulfinyl-bromide): a sulfinyl bromide with
    an additional imine substituent lost both its bromine and its S=N double
    bond -- verified via OPSIN as a DIFFERENT, smaller molecule. That wrong
    string must never come back; the honest failure it is replaced with is
    checked structurally too (PARSER_FAILED, never a false MATCH)."""
    from rdkit import Chem

    from openchem.chem.naming_providers import verify_name_round_trip, RoundTrip

    wrong_former_output = "[(methylaminosulfinyl)amino]methane"
    smiles = "CN=S(=O)(Br)NC"
    got = name_smiles(smiles)
    assert got != wrong_former_output
    assert verify_name_round_trip(got, Chem.MolFromSmiles(smiles)) == RoundTrip.PARSER_FAILED


def test_a_plain_sulfinyl_halide_still_uses_the_shortcut():
    """Converse of D-133: the new _sulfonyl_sulfinyl_has_single_substituent
    guard must decline ONLY when S carries more than one non-oxo
    substituent. A plain sulfinyl bromide with no third substituent --
    D-133's molecule minus the extra N-methylamino branch -- is exactly the
    shape the {R}sulfinyl shortcut was built for, and must still reach it."""
    assert name_smiles("CN=S(=O)Br") == "[(bromosulfinyl)amino]methane"


def test_a_plain_sulfonyl_substituent_still_uses_the_shortcut():
    """A second converse of D-133, on the sulfonyl (oxo_count=2) side of the
    same shortcut rather than the sulfinyl side."""
    assert name_smiles("CS(=O)(=O)c1ccccc1") == "(methanesulfonyl)benzene"


def test_a_phosphine_oxide_no_longer_loses_its_oxidation_state():
    """D-134's admission reason (phosphine-oxide-trihydrazide): a P(V)
    phosphine oxide named as a trivalent P(III) phosphane, dropping the P=O
    entirely -- verified via OPSIN as a DIFFERENT molecule. That wrong
    string must never come back."""
    wrong_former_output = "1,1',1''-phosphanetriyltris(1-methylhydrazine)"
    got = name_smiles("CN(N)P(=O)(N(C)N)N(C)N")
    assert got != wrong_former_output
    assert got == "1-methyl-1-[bis(1-methylhydrazinyl)(oxo)phosphanyl]hydrazine"


def test_a_plain_trivalent_phosphanetriyl_linker_still_works():
    """Converse of D-134: the new _linker_has_phosphine_oxide check must
    decline ONLY when the linker carries a real P=O. A plain trivalent P
    linker -- D-134's molecule minus the oxide -- is exactly the shape
    "phosphanetriyl" was built for, and must still reach it."""
    assert name_smiles("CN(N)P(N(C)N)N(C)N") == "1,1',1''-phosphanetriyltris(1-methylhydrazine)"


def test_glycylalanine_is_the_book_own_worked_example():
    """D-135, P-103.3.2's own worked example verbatim (pdf p. 1048):
    'glycine + alanine -> glycylalanine (PIN)'. Verified via OPSIN round-trip
    that the retained form denotes the SAME structure the systematic form
    it replaces did."""
    from rdkit import Chem

    from openchem.chem.naming_providers import verify_name_round_trip, RoundTrip

    smiles = "NCC(=O)N[C@@H](C)C(=O)O"
    got = name_smiles(smiles)
    assert got == "glycylalanine"
    assert verify_name_round_trip(got, Chem.MolFromSmiles(smiles)) == RoundTrip.MATCH


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # Both directions (which residue is acyl vs. base), several side
        # chains, and the two shapes _match_dipeptide has to tell apart:
        # an open-chain base (most residues) and a ring base (proline).
        ("N[C@@H](Cc1ccccc1)C(=O)N[C@@H](Cc1c[nH]c2ccccc12)C(=O)O", "phenylalanyltryptophan"),
        ("N[C@@H](CC(=O)O)C(=O)N[C@@H](CCC(=O)O)C(=O)O", "aspartylglutamic acid"),
        ("N[C@@H](Cc1c[nH]cn1)C(=O)N1CCC[C@H]1C(=O)O", "histidylproline"),
        ("NC(=O)CC[C@H](N)C(=O)N1CCC[C@H]1C(=O)O", "glutaminylproline"),
        ("O=C(O)[C@@H]1CCCN1C(=O)[C@@H](N)CO", "serylproline"),
    ],
)
def test_other_dipeptides_also_reach_the_retained_form(smiles, expected):
    """The B2 battery's own 20 dipeptides: 14/20 reach the retained form
    (measured 2026-09-22); the other 6 all involve threonine or isoleucine,
    whose battery-generated SMILES specify stereo on the alpha carbon only,
    not the side-chain stereocentre -- see test_under_specified_stereo_
    correctly_declines below for why that is the matcher declining
    correctly, not a bug."""
    assert name_smiles(smiles) == expected


def test_under_specified_stereo_correctly_declines_not_guesses():
    """A residue with a SECOND stereocentre (threonine, isoleucine) whose
    SMILES specifies only the alpha carbon's configuration must NOT match
    the retained-name table: "threonyl" denotes ONE specific diastereomer
    (2S,3R), and an input that does not say which diastereomer this is
    cannot honestly be called that. Measured: this is the exact shape of
    6 of the B2 battery's 20 dipeptide rows (threonine or isoleucine on
    either side), all of which correctly still name systematically."""
    # threonine's own alpha carbon specified, side-chain carbon left
    # unspecified -- matches battery row "dipeptide-threonine+valine".
    under_specified = "CC(O)[C@H](N)C(=O)N[C@@H](C(C)C)C(=O)O"
    got = name_smiles(under_specified)
    assert "threonyl" not in got and "valyl" not in got
    # the fully stereo-specified version of the SAME dipeptide DOES match.
    fully_specified = "C[C@@H](O)[C@H](N)C(=O)N[C@@H](C(C)C)C(=O)O"
    assert name_smiles(fully_specified) == "threonylvaline"


def test_a_tripeptide_is_declined_not_partially_named():
    """Scope converse: this module handles a single peptide bond only
    (matches every B2 battery row). A tripeptide (two peptide bonds) must
    fall through to the general engine untouched, not produce a partial or
    malformed retained-form name."""
    tripeptide = "NCC(=O)N[C@@H](C)C(=O)N[C@@H](Cc1ccccc1)C(=O)O"  # Gly-Ala-Phe
    got = name_smiles(tripeptide)
    assert "glycylalanyl" not in got and "alanylphenylalanine" not in got


def test_an_unnatural_amino_acid_dipeptide_is_declined():
    """Scope converse: a residue outside the 20 proteinogenic amino acids
    (here, 2-methylalanine / alpha-aminoisobutyric acid, achiral and with no
    retained acyl prefix) must not match by accident -- the table is closed,
    not a general alpha-amino-acid rule."""
    got = name_smiles("CC(C)(N)C(=O)N[C@@H](C)C(=O)O")
    assert got == "(2S)-2-(2-amino-2-methylpropanamido)propanoic acid"


def test_the_alkynyl_dianion_no_longer_loses_both_charges():
    """D-136's admission reason (charge-alkynyl-dianion): ethynediide named
    as plain neutral ethyne, both charges dropped -- verified via OPSIN as a
    DIFFERENT molecule. That wrong string must never come back."""
    wrong_former_output = "ethyne"
    got = name_smiles("[C-]#[C-]")
    assert got != wrong_former_output
    assert got == "ethynediide"


def test_the_alkynyl_monoanion_still_works():
    """Converse of D-136: the mono-anion branch this extends must still
    reach its own pre-existing correct name."""
    assert name_smiles("[C-]#C") == "ethyn-1-ide"


def test_the_phosphide_anion_no_longer_loses_its_charge():
    """D-137's admission reason (charge-phosphide-anion): a bicyclic
    phosphide named as the neutral phosphane, the charge dropped --
    verified via OPSIN as a DIFFERENT molecule. That wrong string must
    never come back."""
    wrong_former_output = "1-phosphabicyclo[2.2.2]octane"
    got = name_smiles("C1C[PH-]2CCC1CC2")
    assert got != wrong_former_output
    assert got == "1-phosphabicyclo[2.2.2]octan-1-uide"


@pytest.mark.parametrize(
    "smiles",
    [
        "C1CP2CCC1CC2",       # the plain neutral phosphine (no anion at all)
        "C[PH3+]",            # a phosphonium cation, a different classifier
        "CP(C)(C)=O",         # a phosphine oxide, D-134's own item
    ],
)
def test_the_phosphide_classifier_does_not_over_fire(smiles):
    """Converse of D-137: the new phosphide-anion classifier requires
    EXACTLY one charge -1 on P with every neighbour carbon. A neutral
    phosphine, a phosphonium cation, and a phosphine oxide (P=O counts as
    a non-carbon neighbour) must all reach their own, unrelated, unaffected
    names -- none of them is a phosphide anion."""
    got = name_smiles(smiles)
    assert "uide" not in got


def test_an_acyclic_phosphide_keeps_its_pre_existing_correct_name():
    """A second, load-bearing converse of D-137, found by the stage
    comparison itself (r9-items-10-12-13, bb-fe3343956898): an ACYCLIC
    phosphide (dimethylphosphide, C[P-]C) was ALREADY named correctly
    ("dimethylphosphanide") through a different, pre-existing route -- P
    itself as the "phosphane" parent, contracted with its substituents.
    Without the classifier's ring-membership gate, this case was claimed
    too and rendered through the skeletal-replacement "uide" path built for
    the bridgehead case, producing "dimethylphosphan-1-uide" -- verified via
    OPSIN as a DIFFERENT, wrong structure. That regression must never come
    back; this is why the classifier requires P to be a ring atom."""
    assert name_smiles("C[P-]C") == "dimethylphosphanide"


def test_the_imine_anion_no_longer_loses_its_charge():
    """D-138's admission reason (charge-imine-anion): butaniminide named as
    neutral 1-iminobutane, the charge dropped -- verified via OPSIN as a
    DIFFERENT molecule. That wrong string must never come back."""
    wrong_former_output = "1-iminobutane"
    got = name_smiles("CCCC=[N-]")
    assert got != wrong_former_output
    assert got == "butan-1-iminide"


def test_the_amine_anion_is_unaffected_by_the_imine_anion_addition():
    """Converse of D-138: the amine-anion classifier's own single-bond gate
    (which the imine-anion classifier mirrors with a double-bond gate
    instead) must still claim ordinary primary and secondary amine anions,
    unaffected by the new classifier running immediately before it."""
    assert name_smiles("CC[NH-]") == "ethanaminide"
    assert name_smiles("CCC[N-]CCC") == "N-propylpropan-1-aminide"


@pytest.mark.parametrize(
    "smiles",
    [
        "CN=C(N)NC(=N)NC(=N)NC(=N)NC(=N)N",     # a methyl on an end imino nitrogen
        "CNC(=N)NC(=N)NC(=N)NC(=N)NC(=N)N",     # a methyl on an end amino nitrogen
        "N=C(N)NC(=N)N(C)C(=N)NC(=N)NC(=N)N",   # a methyl on a bridging nitrogen
        "NC(N)=NC(=N)NC(=N)NC(=N)NC(=N)N",      # a tautomer with a double bond into a bridge
    ],
)
def test_a_substituted_or_tautomeric_long_condensed_chain_is_never_named_as_the_bare_one(smiles):
    """Naming round 8: the n >= 5 skeletal-replacement name is for the UNSUBSTITUTED chain only. Without the atom-count guard a methylated
    chain would be given the bare chain's name, which OPSIN reads as a different molecule. What it gets instead is unspecified (today an error
    the provider refuses to show); that it is NOT the bare name is the whole claim."""
    bare = name_smiles("N=C(N)NC(=N)NC(=N)NC(=N)NC(=N)N")
    assert bare == "3,5,7-triimino-2,4,6,8-tetraazanonane-1,9-diimidamide"
    assert name_smiles(smiles) != bare
