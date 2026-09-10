"""The calculator taxonomy: which categories exist, what they are called,
and in what order they are shown.

**IT LIVED IN `ui/panels/property_panel.py` AND WAS PRIVATE TO IT.** That was
honest while Properties was the only surface that grouped calculators. It stops
being honest the moment Results groups them too -- and the alternative, having
the Results reader import `property_panel._CATEGORY_LABELS`, would make a panel
about to LOSE its presentation role the owner of the application's calculator
taxonomy.

**THE REGISTRY CANNOT SUPPLY THIS, WHICH IS WHY THE PANEL KEPT ITS OWN COPY.**
`CalculatorRegistry.categories()` returns `sorted({d.category for ...})` --
alphabetical, no display labels, no chosen order. So a consumer that wanted
"ADMET / Regulatory" before "Shape" had nowhere to ask. It asks here.

**THIS IS NOT `FactCategory`, AND THE TWO MUST NOT MERGE.** They answer
different questions and the 21-vs-9 split is the reason both exist:

    calculator category   WHICH PRODUCER ran -- the section a button lives in
                          ("admet", "solubility", "lipophilicity"), a free
                          string so a plugin needs no code change here
    FactCategory          WHAT KIND OF FACT a value is -- a closed enum in
                          `domain/report.py`, describing the fact rather than
                          whoever computed it

A regulatory screen's facts carry `FactCategory.REGULATORY` while its
calculator sits in the `admet` section, and both are correct. Collapsing them to
simplify a grouping would destroy that.

Nothing here imports Qt, RDKit or anything from `ui/` -- it is a vocabulary, and
`tests/test_layering.py` holds the line.
"""

from __future__ import annotations


#: The order sections are shown in, top to bottom. A category absent from this
#: list is not an error -- it is appended alphabetically by `category_sort_key`,
#: which is the ordinary case for the five this application ships unlisted.
#:
#: The merge rationale for these twenty sits in the block below the list, where
#: it was written; it explains WHICH categories exist rather than what this
#: constant is, so it stays there rather than being folded in here.
CATEGORY_ORDER = [
    "physicochemical",
    "identity",
    "naming",
    "charge",
    "lipophilicity",
    "structures",
    "quantum",
    "electronic",
    "topology",
    "geometry",
    "surface",
    "substructure",
    "stereochemistry",
    "aromaticity",
    "medicinal_chemistry",
    # Before pKa rather than after, because the pH-solubility curve is read
    # THROUGH pKa and somebody arriving at "how soluble is this" should meet
    # the answer before the machinery behind it.
    "solubility",
    "pka",
    # Directly after pKa on purpose. Somebody reading "how basic is this"
    # is standing exactly where the Bronsted answer stops being the whole
    # answer, and carbon monoxide is the case that proves it.
    "lewis",
    "admet",
    "shape",
]
#: **26 SECTIONS HELD 49 BUTTONS, AND ELEVEN OF THEM HELD EXACTLY ONE.**
#: Finding a calculator meant scrolling twenty-six headings, most
#: concealing a single item -- counted in `docs/NAVIGATION_AUDIT.md`, and
#: the strongest single number behind "this is extremely difficult
#: software to use".
#:
#: The merge is a taxonomy decision, so each one is justified where it is
#: not obvious:
#:
#: - `structure` (Substance & Bonding) joined `identity`. Both answer
#:   "what IS this", and the old pair rendered as "Structure" beside
#:   "Structure Generators" -- two headings a page apart, one of which
#:   was `category.title()` rather than a name anybody chose.
#: - `logp` + `logd` became `lipophilicity`. `logd` was NOT a singleton
#:   and is merged anyway, because logP contributions in one section and
#:   logD in another is the split that made no sense to begin with.
#: - `molar_refractivity` went to `electronic`, NOT to lipophilicity with
#:   the rest of the Crippen family. Molar refractivity is molar
#:   POLARIZABILITY by Lorentz-Lorenz, so it belongs beside the two
#:   polarizability calculators; filing it under lipophilicity would have
#:   put a heading on the section that was not true of its contents.
#:
#: **A HEADING MAY NOT CONTAIN `&`, AND MUST BE SHORT.** The section
#: header is a `QToolButton`, which eats `&` as a mnemonic -- "Lipophilicity
#: & Refractivity" rendered as "Lipophilicity  Refractivity", with the
#: ampersand simply gone -- and elides when too long, which turned
#: "Identity & Composition" into "Identity ...mposition". Both were caught
#: by looking at the running app after a merge that every test passed.
#: - `alignment`, `dynamics` and `interactions` joined `geometry`: a
#:   superposition, a trajectory and a contact map are all things you can
#:   only ask of a 3D structure.
#: - `stereocenters` moved OUT of `geometry` to sit with
#:   `stereo_descriptors`. A CIP label and the centre it labels belong
#:   together, and this is the one move that gives a singleton a partner
#:   rather than absorbing it.
#: - `regulatory` joined `admet`. Costs nothing in the fact view: those
#:   Facts carry `FactCategory.REGULATORY` themselves, so only the
#:   section changed.
#:
#: `nmr` IS STILL A SINGLETON AND DELIBERATELY SO. `nmr_database` has no
#: registry sibling -- the ORCA NMR jobs are ServiceExecution and live in
#: their own panel -- and filing a spectroscopic measurement under a
#: structural heading to flatten a count would be worse than the count.
#: `test_no_category_holds_a_single_calculator` asserts the exception BY
#: NAME, so a second one cannot arrive quietly.
CATEGORY_LABELS = {
    # Joback's eleven properties. Not "Physicochemical", which is already
    # the descriptor section and would put a critical volume next to a
    # hydrogen-bond donor count.
    "thermophysical": "Thermophysical",
    # Oxygen balance, and the detonation properties when they land.
    "energetic": "Energetic Materials",
    "physicochemical": "Physicochemical",
    "identity": "Identity",
    "naming": "Naming",
    "charge": "Charge",
    "lipophilicity": "Lipophilicity",
    "structures": "Structure Generators",
    "quantum": "Quantum (Huckel)",
    "electronic": "Electronic Properties",
    "topology": "Topology",
    "geometry": "Geometry (3D)",
    "surface": "Surface Area",
    "substructure": "Substructure Search",
    "stereochemistry": "Stereochemistry",
    "aromaticity": "Aromaticity",
    "medicinal_chemistry": "Medicinal Chemistry",
    "solubility": "Solubility",
    "pka": "pKa",
    "lewis": "Lewis Acid/Base",
    "admet": "ADMET / Regulatory",
    "shape": "Shape",
    # Without these the panel falls back to `category.title()`, which
    # rendered the NMR section as "Nmr". Found during a documentation
    # sweep: the guide had to describe a heading that was a formatting
    # accident rather than a name anybody chose.
    "nmr": "NMR",
    # These two hold no buttons at all -- both are ServiceExecution, run
    # from their own panels, and the section exists only to carry the
    # hint that says so. They were relying on `category.title()` giving
    # the right answer by luck, which is the same accident as "Nmr" with
    # a happier outcome.
    "docking": "Docking",
    "quantum_chemistry": "Quantum Chemistry",
}
def category_label(category: str) -> str:
    """What a section is called, in the ONE place that decides.

    **THERE WERE TWO OF THESE AND THEY DISAGREED.** The heading fell back
    to `category.replace("_", " ").title()` and the "Copy all" text fell
    back to `category.title()`, so an unlabelled `medicinal_chemistry`
    would show as "Medicinal Chemistry" on screen and copy as
    "Medicinal_Chemistry" -- two names for one section, in one panel.

    Latent rather than shipped: measured across all four sources that can
    reach `_section_for` (the registry, both descriptor spec tables, a
    calculator's result, and a provider's alerts), every category in the
    app today HAS a chosen label, so neither fallback runs. It is unified
    because a divergence that only appears for the next category added is
    the kind this document is about.

    The fallback stays for plugins, which may register a category nobody
    here has named. It reads `my_tools` as "My Tools", which is right;
    what it cannot do is acronyms, and `nmr` becoming "Nmr" is exactly
    how this finding was noticed.
    """
    return CATEGORY_LABELS.get(category) or category.replace("_", " ").title() or "Other"




def category_sort_key(category: str) -> tuple[int, str]:
    """Where a category sits, for ANY consumer that orders them.

    **EXTRACTED FROM `PropertyPanel._reorder_sections`, WHICH WAS THE ONLY
    IMPLEMENTATION.** Listed categories in `CATEGORY_ORDER`'s order, unlisted
    ones appended alphabetically -- unchanged, so the Properties sections do
    not move. What changes is that the Results selector can ask the same
    question instead of inventing a second answer to it.

    The alphabetical tail is what makes a plugin category deterministic. Five
    categories this application ships are ALSO unlisted -- `thermophysical`,
    `energetic`, `nmr`, `docking` and `quantum_chemistry` -- so that tail is
    the ordinary case here rather than a plugin-only fallback, and a sort that
    left them unordered would visibly reshuffle five real sections.
    """
    listed = category in CATEGORY_ORDER
    return (CATEGORY_ORDER.index(category) if listed else len(CATEGORY_ORDER), category)
