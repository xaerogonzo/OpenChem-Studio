"""The hand-written calculator explainers in `docs/explainers/` and how they reach the reference.

`tools/calculator_explainers.py` PARSES AND RENDERS and judges nothing; this file owns
every judgement, for the reason `test_calculator_reference.py` owns the reference's: a
generator that also validated would report a problem in the one place nobody runs. Each
failure kind is its own assertion, so a failing run says whether a block is missing,
a method block is missing, an id is an orphan, a citation does not resolve or a keyword
list is wrong, and the family PRs can be reviewed by reading one line of output.

**THE COMPLETENESS RULE IS A RATCHET, AND IT HAS ITS OWN NAME.** `EXPLAINER_DEBT` is the
set of built-in calculators still awaiting authored text. Every built-in must be in the
debt set or have a block, never both, and a block must name a calculator that exists. The
set only SHRINKS: `_DEBT_CEILING` is its size and is lowered whenever ids leave it, never
raised, so adding to the set is a visible change in review. A new calculator therefore
cannot be registered with neither (it fails here), and the day the set is empty it is
deleted and replaced by the absolute rule. It is not `LEGACY_UNCLASSIFIED`, which is about
how mature an implementation is; this is about whether anything explains it.

**SCOPE: THE BUILT-IN REGISTRY.** A checked-in source cannot curate a runtime plugin's ids.
A plugin calculator keeps its declared metadata as the fallback and is outside this guard.

**WHAT THESE GUARDS CANNOT DO.** A resolving `[source:key]` proves provenance and not that
the source supports the sentence beside it; that is read against the paper by a person, and
the explainer's own header says which claims are published, shipped or measured here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from openchem import help as help_docs

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import calculator_explainers as ce  # noqa: E402
from build_calculator_reference import anchor_for  # noqa: E402

_DOC = _ROOT / "docs" / "CALCULATOR_REFERENCE.md"

#: Built-in calculators with no authored explainer yet. LOWER `_DEBT_CEILING` whenever ids
#: leave this set; never raise it. Emptied by the last family PR, then deleted.
EXPLAINER_DEBT = frozenset({
    "admet_ml", "alignment_3d", "atomic_polarizability", "bbb_descriptors",
    "bird_aromaticity", "cns_mpo", "crippen_logp_contrib", "crippen_mr_contrib", "detonation",
    "docking.vina", "elemental_analysis", "functional_groups",
    "hansen_solubility", "hbond_sites", "hbond_vs_ph", "homa_aromaticity", "huckel_analysis",
    "huckel_pi_density", "interaction_analysis", "ionisable_sites", "iupac_name", "isoelectric_point",
    "joback_properties", "lewis_adduct", "lewis_hsab", "lewis_sites", "locants", "logd",
    "major_microspecies", "markush_enumeration", "mass_spectrum", "molecular_dynamics",
    "nmr_database", "orca.delta_scf", "orca.led", "orca.nmr", "orca.nmr_coupling", "orca.opt",
    "orca.opt_freq", "orca.sp", "orca.tautomer_distribution", "oxidation_states", "oxygen_balance",
    "pka", "pka_microspecies", "polarizability", "regulatory_screen",
    "resonance_forms", "ring_systems", "solubility", "stereo_descriptors", "stereocenters",
    "stereoisomers", "structural_frameworks", "substance_analysis",
    "substructure_search", "tautomers", "topology_analysis",
    "topology_distance_degree", "topology_eccentricity", "tsei_projection",
})
_DEBT_CEILING = 61


@pytest.fixture(scope="module")
def registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def definitions(registry):
    return {
        definition.calculator_id: definition
        for category in registry.categories()
        for definition in registry.by_category(category)
    }


@pytest.fixture(scope="module")
def explainers():
    return ce.parse()


@pytest.fixture(scope="module")
def sources():
    return ce.load_sources()


@pytest.fixture(scope="module")
def text():
    return _DOC.read_text(encoding="utf-8")


def _problems(explainers, kind):
    return [f"{where}: {detail}" for k, where, detail in explainers.problems if k == kind]


# --- the source parses ---------------------------------------------------


def test_the_explainer_source_has_no_structural_problems(explainers):
    """Unknown headings, stray text, duplicates and wrong levels, each reported by kind."""
    by_kind = {}
    for kind, where, detail in explainers.problems:
        by_kind.setdefault(kind, []).append(f"{where}: {detail}")

    assert not by_kind, "\n".join(f"{kind}: {items}" for kind, items in sorted(by_kind.items()))


def test_there_is_at_least_one_explainer(explainers):
    """A parse that silently found nothing would make every other test here vacuous."""
    assert explainers.blocks, "no explainer blocks were parsed from docs/explainers/"


# --- completeness: the partition and the ratchet -------------------------


def test_every_built_in_calculator_is_explained_or_in_debt(definitions, explainers):
    explained = set(explainers.blocks)
    missing = sorted(set(definitions) - explained - EXPLAINER_DEBT)

    assert not missing, (
        f"{len(missing)} registered calculators have neither an explainer block nor an "
        f"EXPLAINER_DEBT entry: {missing}"
    )


def test_no_calculator_is_both_explained_and_in_debt(explainers):
    both = sorted(set(explainers.blocks) & EXPLAINER_DEBT)

    assert not both, f"explained, so remove from EXPLAINER_DEBT and lower _DEBT_CEILING: {both}"


def test_every_debt_id_is_still_a_registered_calculator(definitions):
    stale = sorted(EXPLAINER_DEBT - set(definitions))

    assert not stale, f"EXPLAINER_DEBT names calculators that no longer exist: {stale}"


def test_every_block_names_a_registered_calculator(definitions, explainers):
    orphans = sorted(set(explainers.blocks) - set(definitions))

    assert not orphans, f"explainer blocks for calculators that do not exist (an id, not a display name): {orphans}"


def test_the_debt_set_only_shrinks():
    """The ratchet itself: lower `_DEBT_CEILING` when ids leave, never raise it."""
    assert len(EXPLAINER_DEBT) <= _DEBT_CEILING, (
        f"EXPLAINER_DEBT grew to {len(EXPLAINER_DEBT)} from {_DEBT_CEILING}; a new calculator "
        "needs an explainer, not a debt entry"
    )
    assert len(EXPLAINER_DEBT) == _DEBT_CEILING, (
        f"{_DEBT_CEILING - len(EXPLAINER_DEBT)} ids left EXPLAINER_DEBT: lower _DEBT_CEILING to "
        f"{len(EXPLAINER_DEBT)} so the ratchet cannot be climbed back"
    )


# --- the schema ----------------------------------------------------------


def test_a_calculator_with_no_methods_has_every_section(explainers):
    missing = {
        block.calculator_id: [s for s in ce.REQUIRED_SINGLE if not block.sections.get(s, "").strip()]
        for block in explainers.blocks.values()
        if not block.methods
    }
    missing = {k: v for k, v in missing.items() if v}

    assert not missing, f"sections missing or empty (single-method calculators need all six): {missing}"


def test_a_multi_method_calculator_has_its_shared_sections_and_every_method_has_its_own(explainers):
    """Checked at each level separately: a method with no explanation must fail even when
    its parent carries every heading."""
    parent_missing, method_missing = {}, {}
    for block in explainers.blocks.values():
        if not block.methods:
            continue
        gone = [s for s in ce.REQUIRED_PARENT_OF_METHODS if not block.sections.get(s, "").strip()]
        if gone:
            parent_missing[block.calculator_id] = gone
        for method in block.methods:
            gone = [s for s in ce.REQUIRED_METHOD if not method.sections.get(s, "").strip()]
            if gone:
                method_missing[f"{block.calculator_id} / {', '.join(method.choices)}"] = gone

    assert not parent_missing, f"shared sections missing at the calculator level: {parent_missing}"
    assert not method_missing, f"sections missing in a method block: {method_missing}"


def test_method_blocks_cover_exactly_the_calculators_method_choices(definitions, explainers):
    """Real choice values, never a locally invented spelling, and none left out. Applies to
    a parameter named `method`; another option (a charge model, a component) is explained
    inside its calculator's own sections."""
    wrong = {}
    for block in explainers.blocks.values():
        if not block.methods or block.calculator_id not in definitions:
            continue
        parameter = next((p for p in definitions[block.calculator_id].parameters if p.name == "method"), None)
        real = set(parameter.choices or ()) if parameter else set()
        written = [c for m in block.methods for c in m.choices]
        problems = []
        if len(written) != len(set(written)):
            problems.append("a choice appears in more than one block")
        if set(written) != real:
            problems.append(f"missing {sorted(real - set(written))}, unknown {sorted(set(written) - real)}")
        if problems:
            wrong[block.calculator_id] = problems

    assert not wrong, f"method blocks disagree with the calculator's `method` choices: {wrong}"


def test_a_calculator_with_several_method_choices_must_document_each(definitions, explainers):
    """The other direction: a block with no method sub-blocks for a calculator that has a
    `method` parameter with more than one choice would explain only one of them."""
    flat = []
    for cid, block in explainers.blocks.items():
        definition = definitions.get(cid)
        parameter = next((p for p in definition.parameters if p.name == "method"), None) if definition else None
        if parameter is not None and len(parameter.choices or ()) > 1 and not block.methods:
            flat.append(cid)

    assert not flat, f"calculators with several `method` choices but no method blocks: {flat}"


# --- citations ----------------------------------------------------------


def _all_texts(block):
    texts = list(block.sections.values())
    for method in block.methods:
        texts += list(method.sections.values())
    return texts


def test_every_source_reference_resolves_to_the_registry(explainers, sources):
    unknown = sorted({
        (block.calculator_id, key)
        for block in explainers.blocks.values()
        for body in _all_texts(block)
        for key in ce.source_keys(body)
        if key not in sources
    })

    assert not unknown, f"[source:key] references with no row in docs/sources.toml: {unknown}"


def test_a_cited_source_is_not_left_unnumbered_in_the_rendered_reference(explainers, sources):
    """Every key written in prose renders as a number; none is printed as written."""
    for block in explainers.blocks.values():
        rendered = "\n".join(ce.render(block, sources))
        assert "[source:" not in rendered, f"{block.calculator_id}: an unrendered source marker"


def test_every_inline_citation_has_an_entry_in_a_sources_section_of_its_block(explainers):
    """A `[3]` in the prose must have a reference line somewhere in the same calculator's
    explainer, or a reader meets a number that points at nothing."""
    orphans = {}
    for block in explainers.blocks.values():
        listed = set()
        for sections in [block.sections] + [m.sections for m in block.methods]:
            listed |= set(ce.source_keys(sections.get("Sources", "")))
        cited = {
            key
            for sections in [block.sections] + [m.sections for m in block.methods]
            for title, body in sections.items()
            if title != "Sources"
            for key in ce.source_keys(body)
        }
        if cited - listed:
            orphans[block.calculator_id] = sorted(cited - listed)

    assert not orphans, f"cited in the text but listed under no Sources heading: {orphans}"


def test_every_sources_section_lists_only_marked_sources_and_something_is_cited(explainers):
    bare = {}
    for block in explainers.blocks.values():
        for label, sections in [("", block.sections)] + [(", ".join(m.choices), m.sections) for m in block.methods]:
            body = sections.get("Sources", "")
            if body and not ce.source_keys(body):
                bare[f"{block.calculator_id} {label}".strip()] = body[:50]

    assert not bare, f"Sources sections that cite nothing as [source:key]: {bare}"


# --- search keywords and URLs --------------------------------------------


def test_search_keywords_are_two_to_four_distinct(explainers):
    bad = {}
    for block in explainers.blocks.values():
        for label, holder in [("", block)] + [(", ".join(m.choices), m) for m in block.methods]:
            if "Search for" not in holder.sections:
                continue
            words = ce.keywords(holder)
            if not 2 <= len(words) <= 4:
                bad[f"{block.calculator_id} {label}".strip()] = words

    assert not bad, f"Search for needs two to four distinct keywords: {bad}"


def test_no_url_appears_in_authored_explainers(explainers):
    """A URL rots; a DOI, printed as plain text from the registry, is the one identifier
    designed to outlive a site."""
    urls = sorted({
        (block.calculator_id, match)
        for block in explainers.blocks.values()
        for body in _all_texts(block)
        for match in re.findall(r"https?://\S+|www\.\S+", body)
    })

    assert not urls, f"URLs in explainer text: {urls}"


# --- the generator --------------------------------------------------------


def _section_of(text, calculator_id):
    start = text.index(f"<!-- help:{anchor_for(calculator_id)} -->")
    end = text.find("<!-- help:", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_the_generator_emits_each_block_once_under_its_own_calculator(explainers, text):
    wrong = {}
    for block in explainers.blocks.values():
        section = _section_of(text, block.calculator_id)
        problems = []
        for title in block.sections:
            if section.count(f"\n#### {title}\n") != 1:
                problems.append(f"'{title}' x{section.count(chr(10) + '#### ' + title + chr(10))}")
        for method in block.methods:
            label = ", ".join(f"`{c}`" for c in method.choices)
            if section.count(f"\n#### Method: {label}\n") != 1:
                problems.append(f"method {label}")
        # A method's own sections are bold labels, one per method that has them.
        for title in ce.SECTIONS:
            expected = sum(1 for m in block.methods if title in m.sections)
            if section.count(f"\n**{title}**\n") != expected:
                problems.append(f"method label '{title}' x{section.count(chr(10) + '**' + title + '**' + chr(10))}, wanted {expected}")
        if problems:
            wrong[block.calculator_id] = problems

    assert not wrong, f"explainer text not rendered exactly once under its calculator: {wrong}"
    assert text.count("\n#### What it does\n") == len(explainers.blocks), (
        "an explainer was rendered under the wrong calculator, or twice"
    )


def test_an_explainer_never_ends_its_calculators_help_topic_early(explainers):
    """The Help window ends a topic at the next heading of the same or a higher level, so
    nothing the explainer emits may be at level 3 or above or it would be cut off from its
    calculator (and from that calculator's search hits). And nothing may be deeper than 4:
    the Help window draws levels 5 and 6 smaller than body text."""
    for number, line in enumerate(_DOC.read_text(encoding="utf-8").splitlines(), 1):
        assert not line.startswith("#####"), f"CALCULATOR_REFERENCE.md:{number} is a level-5+ heading: {line[:60]}"
    for block in explainers.blocks.values():
        topic = help_docs.topic_markdown(anchor_for(block.calculator_id))
        for title in block.sections:
            assert f"#### {title}" in topic, f"{block.calculator_id}: '{title}' is outside its Help topic"
        for method in block.methods:
            label = ", ".join(f"`{c}`" for c in method.choices)
            assert f"#### Method: {label}" in topic, f"{block.calculator_id}: method {label} is outside its topic"


def test_rendered_citations_carry_a_plain_text_doi_and_no_link(explainers, sources, text):
    """The renderer prints the registry's citation and its DOI as text. No URL, ever."""
    cited_with_doi = [
        key
        for block in explainers.blocks.values()
        for body in _all_texts(block)
        for key in ce.source_keys(body)
        if sources.get(key, {}).get("identifier_type") == "doi"
    ]
    assert cited_with_doi, "expected at least one DOI-bearing citation in the charge family"
    for key in set(cited_with_doi):
        assert f"DOI {sources[key]['identifier']}" in text, f"{key}: its DOI is not printed"
    for block in explainers.blocks.values():
        assert "http" not in "\n".join(ce.render(block, sources)), block.calculator_id


# --- the help window finds it ---------------------------------------------

#: A term that exists ONLY in the authored explainer (asserted below), and the calculator
#: topic that must be found by it. Searching the Help window proves the feature delivers its
#: point, which is being findable by what a person would actually type.
_SEARCHES = [
    ("Sanderson", "geometry_partial_charge"),
    ("shielded", "geometry_partial_charge"),
    ("bond charge increment", "gasteiger_charge_at_ph"),
    ("damped by one half", "gasteiger_charge_at_ph"),
    ("SD-POE", "orbital_electronegativity"),
    ("centre of mass", "dipole_moment"),
    ("World Drug Index", "polar_surface_area"),
    ("asymptotically", "griffin_hlb"),
    ("anti and 0 is syn", "torsion_table"),
    ("Universal force field", "geometry_analysis"),
    ("Fibonacci", "atom_sasa"),
    ("chlorine counts as hydrophobic", "surface_analysis"),
    ("right circular cone", "steric_analysis"),
]


@pytest.mark.parametrize("term,calculator_id", _SEARCHES)
def test_help_search_finds_the_explainer_under_the_right_calculator(term, calculator_id, definitions):
    assert term.lower() not in definitions[calculator_id].description.lower(), (
        f"'{term}' is in the registry description already, so this search proves nothing about the explainer"
    )
    help_docs.reload()
    hits = [hit.topic.key for hit in help_docs.search(term)]

    assert anchor_for(calculator_id) in hits, f"searching '{term}' did not reach {calculator_id}: {hits[:6]}"
