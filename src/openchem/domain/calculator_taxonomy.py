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

from dataclasses import dataclass

from openchem.domain.report import FactCategory


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


#: **TASK GROUPS: THE BROWSE LAYER ABOVE CATEGORIES.** Twenty-two categories read
#: as a wall; nine headings named for what somebody wants to FIND OUT do not.
#: A group is navigation only -- it never replaces a category id, so stored
#: results, caches and `ReportResult.category` are untouched. Order here is the
#: order down the panel; labels are validated by a test (no `&`, which a
#: `QToolButton` eats as a mnemonic, and 21 characters at most, the measured
#: ceiling at the panel's real width).
TASK_GROUPS: dict[str, str] = {
    "identity": "Identity and naming",
    "charge": "Charge and electrons",
    "solubility": "Solubility and pKa",
    "shape": "Shape and surface",
    "topology": "Topology and stereo",
    "druglike": "Drug-likeness",
    "structures": "Structure generation",
    "spectra": "Spectra and energy",
    "other": "Other calculators",
}

#: Where a category without a mapping lands. Visible rather than dropped, so a
#: plugin's calculators are always reachable and always say they are unfiled.
FALLBACK_TASK_GROUP = "other"

#: Category id -> task group. Every category this application can produce is
#: here (a test enumerates the registry, both descriptor tables and the
#: calculator results to prove it); `other` is the answer only for a category
#: nobody here has met.
#:
#: Judgement calls, recorded because they are not obvious:
#: - lipophilicity sits with solubility and pKa: logP/logD are read through
#:   ionisation, and they answer "how does it partition".
#: - substructure (functional groups, SMARTS) sits with identity: "what is in it".
#: - docking and quantum_chemistry are service-run categories that hold only a
#:   row opening their own panel; they sit with spectra and energy.
CATEGORY_TASK_GROUP: dict[str, str] = {
    "identity": "identity",
    "naming": "identity",
    "physicochemical": "identity",
    "substructure": "identity",
    "charge": "charge",
    "electronic": "charge",
    "quantum": "charge",
    "lewis": "charge",
    "solubility": "solubility",
    "pka": "solubility",
    "lipophilicity": "solubility",
    "geometry": "shape",
    "surface": "shape",
    "shape": "shape",
    "topology": "topology",
    "stereochemistry": "topology",
    "aromaticity": "topology",
    "admet": "druglike",
    "medicinal_chemistry": "druglike",
    "regulatory": "druglike",
    "structures": "structures",
    "nmr": "spectra",
    "energetic": "spectra",
    "thermophysical": "spectra",
    "docking": "spectra",
    "quantum_chemistry": "spectra",
}

#: Category -> group claimed by a PLUGIN calculator that declares
#: `task_group`. Only canonical group ids are accepted and a category this
#: application already files cannot be moved, so a plugin cannot reshuffle
#: built-in sections or invent a group. Module state on purpose: Properties and
#: Results must agree and both read it here; tests clear it through
#: `reset_plugin_category_groups`.
_PLUGIN_CATEGORY_GROUPS: dict[str, str] = {}


def assign_plugin_category_group(category: str, group: str | None) -> bool:
    """Honour a plugin's `task_group` for a category nobody here files.

    False (and nothing changes) for an absent or unknown group, or for a
    category already mapped -- never an error, because a plugin that knows
    nothing about groups must keep loading.
    """
    if not group or group not in TASK_GROUPS or group == FALLBACK_TASK_GROUP:
        return False
    if category in CATEGORY_TASK_GROUP or category in _PLUGIN_CATEGORY_GROUPS:
        return False
    _PLUGIN_CATEGORY_GROUPS[category] = group
    return True


def reset_plugin_category_groups() -> None:
    _PLUGIN_CATEGORY_GROUPS.clear()


def task_group_of(category: str) -> str:
    """The task group id a category is browsed under."""
    return (
        CATEGORY_TASK_GROUP.get(category)
        or _PLUGIN_CATEGORY_GROUPS.get(category)
        or FALLBACK_TASK_GROUP
    )


def task_group_label(group: str) -> str:
    return TASK_GROUPS.get(group) or TASK_GROUPS[FALLBACK_TASK_GROUP]


def task_group_order(group: str) -> int:
    ids = list(TASK_GROUPS)
    return ids.index(group) if group in TASK_GROUPS else len(ids)


def category_browse_key(category: str) -> tuple[int, str, str]:
    """Where a category sits in the BROWSE order: group, then visible label.

    **THE LABEL DECIDES, NOT THE ID.** `nmr` and `identity` sort one way as ids
    and another as the headings a reader sees; the reader sees headings. The id
    only breaks a tie between two categories that read identically. Properties
    and Results both order sections with this, so the two cannot disagree.
    """
    return (
        task_group_order(task_group_of(category)),
        category_label(category).casefold(),
        category,
    )


def calculator_browse_sort_key(definition) -> tuple:
    """The full browse key for one calculator definition.

    `(task group, category label, category id, display name, calculator id)`,
    every text part casefolded where it is a name. The calculator id is the
    last resort so two definitions with one display name still order the same
    way on every run. One helper for Properties, Find and the wizard.
    """
    category = str(getattr(definition, "category", "") or "") or "other"
    return (
        *category_browse_key(category),
        str(getattr(definition, "display_name", "") or "").casefold(),
        str(getattr(definition, "calculator_id", "") or ""),
    )


#: `Fact` needs one of the nine `FactCategory` values. Anything unlisted
#: becomes STRUCTURE rather than being dropped -- a fact filed under the
#: wrong heading is recoverable, a missing one is not.
_CATEGORY_BY_NAME: dict[str, FactCategory] = {
    "identity": FactCategory.IDENTITY,
    "naming": FactCategory.IDENTITY,
    "physicochemical": FactCategory.IDENTITY,
    # **ADDED WHEN THE DESCRIPTORS STOPPED BEING GROUPED BY THE PANEL.**
    # Both were unlisted and took the STRUCTURE default, which nobody saw
    # while the Properties panel filed LogP under its own "Lipophilicity"
    # heading and Aqueous Solubility under "Solubility". 2c makes the
    # reader's grouping the only grouping, and measured there, LogP
    # appeared under Structure.
    #
    # IDENTITY because that is where their siblings already are: Molecular
    # Weight and TPSA declare `physicochemical` and map here. This is
    # consistency with an existing entry rather than a new taxonomy call --
    # the taxonomy review itself is stage 3, and the six categories still
    # taking the default are named in `test_calculator_taxonomy.py`.
    "lipophilicity": FactCategory.IDENTITY,
    "solubility": FactCategory.IDENTITY,
    "charge": FactCategory.ELECTRONIC,
    "electronic": FactCategory.ELECTRONIC,
    "quantum": FactCategory.QUANTUM,
    "lewis": FactCategory.ELECTRONIC,
    "nmr": FactCategory.SPECTROSCOPY,
    "topology": FactCategory.TOPOLOGY,
    "geometry": FactCategory.GEOMETRY,
    "surface": FactCategory.GEOMETRY,
    "shape": FactCategory.GEOMETRY,
    "regulatory": FactCategory.REGULATORY,
    "medicinal_chemistry": FactCategory.STRUCTURE,
    "admet": FactCategory.STRUCTURE,
    "substructure": FactCategory.STRUCTURE,
    "stereochemistry": FactCategory.STRUCTURE,
    "interactions": FactCategory.STRUCTURE,
    "pka": FactCategory.ELECTRONIC,
}


@dataclass(frozen=True)
class Retirement:
    """A calculator id that is no longer offered, and what became of it."""

    #: What it was called on screen. **THE SEARCHABLE HALF**: people look
    #: for "Solubility vs pH" without knowing it was folded in, so the
    #: reference carries the old name as an alias beside the new one.
    display_name: str
    #: The calculator id that does its job now, or "" if nothing does.
    replaced_by: str
    #: One sentence, in the past tense, saying what happened.
    reason: str


#: Calculator ids this application used to offer.
#:
#: **RETIRED IS NOT DELETED, AND THIS TABLE IS THE DIFFERENCE.** The
#: recorded policy has three halves and only one of them is about the
#: registry:
#:
#:   not offered      the id is simply absent from the registry, so nothing
#:                    can start a new calculation under it
#:   still readable   a STORED result keeps working, because the reader
#:                    renders what it was handed rather than asking the
#:                    registry what produced it
#:   never aliased    an old cache key MISSES and recomputes under the new
#:                    identity; silently serving a new result under an old
#:                    key would be the plausible-looking lie this project
#:                    spends its time removing
#:
#: The display name is here so a retired calculator stays FINDABLE. A
#: reference that only lists what exists today sends somebody looking for
#: "Solubility vs pH" away empty, which is the same dead end as a search
#: box that cannot match a synonym.
RETIREMENTS: dict[str, Retirement] = {
    "solubility_curve": Retirement(
        display_name="Solubility vs pH",
        replaced_by="solubility",
        reason=(
            "Folded into Solubility, which reported the same nine facts and "
            "the same curve points and already honoured the pH range it now "
            "offers."
        ),
    ),
    "logd_curve": Retirement(
        display_name="LogD vs pH",
        replaced_by="logd",
        reason=(
            "Folded into LogD, which now declares the curve it lies on -- the same "
            "Henderson-Hasselbalch function over the same pH range, with the chosen pH "
            "as a sample -- so reading logD at one pH and seeing the curve is one run."
        ),
    ),
}


def category_for(name: str) -> FactCategory:
    """Which `FactCategory` a calculator category's facts belong under.

    **THE BRIDGE BETWEEN THE TWO VOCABULARIES, AND IT LIVES WITH ONE OF
    THEM.** It was in `chem/report_adapter.py`, which imports nothing from
    `chem/` at all -- it is a domain-level projection filed under the
    chemistry layer. Both ENDPOINTS are domain vocabularies: the calculator
    category above, and `FactCategory` in `domain/report.py`. A second copy
    would be the drift `CATEGORY_LABELS` was moved here to prevent.

    Unlisted becomes STRUCTURE rather than raising, and that asymmetry is
    deliberate: `category` is a FREE STRING so a plugin may invent one, and a
    fact filed under the wrong heading is recoverable where a refused fact is
    not. The closed vocabularies in this project refuse; this one cannot.
    """
    return _CATEGORY_BY_NAME.get(name, FactCategory.STRUCTURE)
