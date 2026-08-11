"""Gather every known fact about one atom into an `AtomReport`.

One collector per source, each free to return nothing. Adding a source is
adding a function to `_COLLECTORS`; no consumer changes, and no collector
knows about any other.

**Nothing here computes.** Every collector either reads the molecule
directly (RDKit intrinsics, element data) or reads a result somebody else
already produced and handed in (`PerAtomDataset`s, spectra, checker
issues). Building a report never starts a job, which is what lets the
inspector be free to open -- an inspector that launches ORCA when you
click an atom is a calculator launcher, and people stop trusting it.

The analyses that ARE run here -- Lewis sites, oxidation states -- are
structural, in-process and measured in milliseconds, the same ones the
Structure Check panel already runs on every edit.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from openchem.domain.atom_report import AtomFact, AtomReport, FactCategory, FactLink
from openchem.domain.scientific_result import PerAtomDataset, SpectrumResult
from openchem.domain.structure_issue import Basis, StructureIssue

METHOD = "Atom report"

_ASSUMPTIONS = (
    "This report shows what has ALREADY been computed. Opening it runs "
    "nothing, so a property you have not calculated is absent rather than "
    "wrong -- run its calculator and it appears here.",
)

#: Which `FactCategory` a `PerAtomDataset` belongs under, by `property_id`.
#: Unlisted ids fall back to ELECTRONIC, which is where most per-atom
#: numbers in this application live.
_PROPERTY_CATEGORY: dict[str, FactCategory] = {
    "gasteiger_charge": FactCategory.ELECTRONIC,
    "gasteiger_charge_at_ph": FactCategory.ELECTRONIC,
    "atomic_polarizability": FactCategory.ELECTRONIC,
    "orbital_electronegativity": FactCategory.ELECTRONIC,
    "huckel_pi_density": FactCategory.QUANTUM,
    "oxidation_states": FactCategory.ELECTRONIC,
    "crippen_logp_contrib": FactCategory.STRUCTURE,
    "crippen_mr_contrib": FactCategory.STRUCTURE,
    "atom_sasa": FactCategory.GEOMETRY,
    "topology_eccentricity": FactCategory.TOPOLOGY,
    "topology_distance_degree": FactCategory.TOPOLOGY,
    "ring_systems": FactCategory.TOPOLOGY,
    "functional_groups": FactCategory.STRUCTURE,
    "locants": FactCategory.IDENTITY,
    "stereocenters": FactCategory.STRUCTURE,
    "substructure_match": FactCategory.STRUCTURE,
}


def _fact(
    category: FactCategory,
    label: str,
    value: Any,
    source: str,
    basis: Basis = Basis.DETERMINISTIC,
    display: str | None = None,
    **extra: Any,
) -> AtomFact:
    return AtomFact(
        category=category,
        label=label,
        value=value,
        display_value=display if display is not None else str(value),
        source=source,
        basis=basis,
        **extra,
    )


# --- collectors -------------------------------------------------------------


def collect_intrinsic(mol: Any, index: int, _context: dict) -> list[AtomFact]:
    """What RDKit knows without anybody calculating anything."""
    atom = mol.GetAtomWithIdx(index)
    facts = [
        _fact(FactCategory.IDENTITY, "Element", atom.GetSymbol(), "RDKit"),
        _fact(FactCategory.IDENTITY, "Atom index", index, "RDKit", display=str(index + 1)),
        _fact(FactCategory.STRUCTURE, "Hybridisation", str(atom.GetHybridization()), "RDKit"),
        _fact(FactCategory.ELECTRONIC, "Formal charge", atom.GetFormalCharge(), "RDKit",
              display=f"{atom.GetFormalCharge():+d}" if atom.GetFormalCharge() else "0"),
        _fact(FactCategory.STRUCTURE, "Aromatic", atom.GetIsAromatic(), "RDKit",
              display="yes" if atom.GetIsAromatic() else "no"),
        _fact(FactCategory.TOPOLOGY, "Connections", atom.GetDegree(), "RDKit"),
        _fact(FactCategory.STRUCTURE, "Hydrogens", atom.GetTotalNumHs(), "RDKit"),
    ]
    if atom.GetIsotope():
        facts.append(_fact(FactCategory.IDENTITY, "Isotope", atom.GetIsotope(), "RDKit"))
    if atom.GetNumRadicalElectrons():
        facts.append(
            _fact(FactCategory.ELECTRONIC, "Radical electrons",
                  atom.GetNumRadicalElectrons(), "RDKit")
        )

    ring_info = mol.GetRingInfo()
    if ring_info.NumAtomRings(index):
        sizes = sorted(len(ring) for ring in ring_info.AtomRings() if index in ring)
        facts.append(
            _fact(FactCategory.TOPOLOGY, "In ring", sizes, "RDKit",
                  display=", ".join(f"{size}-membered" for size in sizes))
        )
    return facts


def collect_element(mol: Any, index: int, _context: dict) -> list[AtomFact]:
    """Reference data for the element, from the periodic-table work."""
    from openchem.chem.element_reference import facts_for

    symbol = mol.GetAtomWithIdx(index).GetSymbol()
    element = facts_for(symbol)
    if element is None:
        return []

    link = FactLink(target="periodic_table", params={"symbol": symbol},
                    label=f"Open {symbol} in the periodic table")
    facts = [
        _fact(FactCategory.ELEMENT, "Name", element.name, "element_reference", link=link),
        _fact(FactCategory.ELEMENT, "Atomic number", element.atomic_number, "element_reference"),
        _fact(FactCategory.ELEMENT, "Group / period", (element.group, element.period),
              "element_reference",
              display=f"group {element.group}, period {element.period}"),
        _fact(FactCategory.ELEMENT, "Block", element.block, "element_reference"),
        _fact(FactCategory.ELEMENT, "Configuration", element.electron_configuration,
              "element_reference"),
    ]
    if element.electronegativity is not None:
        facts.append(
            _fact(FactCategory.ELEMENT, "Electronegativity", element.electronegativity,
                  "element_reference", display=f"{element.electronegativity:.2f} (Pauling)")
        )
    if element.covalent_radius is not None:
        facts.append(
            _fact(FactCategory.ELEMENT, "Covalent radius", element.covalent_radius,
                  "element_reference", display=f"{element.covalent_radius:.2f} A", units="A")
        )
    return facts


def collect_lewis(mol: Any, index: int, _context: dict) -> list[AtomFact]:
    """Donor/acceptor character, with the rule that found it.

    Each `LewisEvidence` becomes the fact's evidence rather than a fact of
    its own -- "why is this a donor" belongs to the role, not beside it.
    """
    from openchem.chem.lewis import analyse, lone_pairs

    result = analyse(mol)
    if result.refused:
        return [
            _fact(FactCategory.ELECTRONIC, "Lewis analysis", None, "LewisAnalysis",
                  basis=Basis.DETERMINISTIC, display="not applicable",
                  limitations=(result.reason,))
        ]
    site = result.site_for(index)
    if site is None:
        # **NO LEWIS ROLE IS NOT NOTHING TO SAY.** `analyse` builds a site
        # only for atoms that donate or accept, so an ammonium nitrogen --
        # which does neither, precisely because it has no lone pair --
        # produced no facts at all. Asked "does this nitrogen have a lone
        # pair?", a question with a definite answer, the inspector said
        # nothing, which reads as "not computed" rather than "none".
        #
        # Safe to fall back to the raw arithmetic HERE and nowhere else:
        # the refusal above has already caught the cases where a pair
        # count is meaningless (an unpaired electron on a main-group
        # atom), and `lone_pairs` itself answers None for a metal.
        pairs = lone_pairs(mol.GetAtomWithIdx(index))
        if pairs is None:
            return []
        return [_fact(FactCategory.ELECTRONIC, "Lone pairs", pairs, "LewisAnalysis")]

    link = FactLink(target="interactions", params={"atom": index},
                    label="Open the Interactions panel")
    evidence = tuple(f"{e.rule} [{e.basis.value}]" for e in site.evidence)
    # A site is heuristic if ANY rule behind it was -- the weakest link is
    # what a reader needs to know about.
    basis = (
        Basis.HEURISTIC
        if any(e.basis is Basis.HEURISTIC for e in site.evidence)
        else Basis.DETERMINISTIC
    )
    facts = [
        _fact(FactCategory.ELECTRONIC, "Lewis role", site.role, "LewisAnalysis",
              basis=basis, display=site.role.value, evidence=evidence, link=link,
              limitations=result.limitations)
    ]
    if site.lone_pairs is not None:
        facts.append(
            _fact(FactCategory.ELECTRONIC, "Lone pairs", site.lone_pairs, "LewisAnalysis")
        )
    if site.mechanisms:
        facts.append(
            _fact(FactCategory.ELECTRONIC, "Accepts via", list(site.mechanisms),
                  "LewisAnalysis", basis=basis,
                  display=", ".join(m.value.replace("_", " ") for m in site.mechanisms))
        )
    return facts


def collect_oxidation_state(mol: Any, index: int, _context: dict) -> list[AtomFact]:
    """The IUPAC electronegativity partition, refusals included.

    A refusal is reported rather than dropped: "our bonding model does not
    apply here" is a fact about the atom, and silence would read as "not
    computed yet".
    """
    from openchem.chem.oxidation_states import assign

    result = assign(mol)
    if result.refused:
        return [
            _fact(FactCategory.ELECTRONIC, "Oxidation state", None, "oxidation_states",
                  display="not assigned", limitations=(result.reason,))
        ]
    if index not in result.states:
        return []
    state = result.states[index]
    return [
        _fact(FactCategory.ELECTRONIC, "Oxidation state", state, "oxidation_states",
              display=f"{state:+d}" if state else "0")
    ]


def collect_per_atom_data(mol: Any, index: int, context: dict) -> list[AtomFact]:
    """Whatever per-atom results have already arrived by event.

    `context["per_atom"]` is `{property_id: PerAtomDataset}`, filled by the
    panel as `PerAtomDataComputed` events land. Absent means not computed,
    which is a different statement from zero.
    """
    datasets: Iterable[PerAtomDataset] = context.get("per_atom", {}).values()
    facts: list[AtomFact] = []
    for dataset in datasets:
        if index not in dataset.values:
            continue
        value = dataset.values[index]
        units = f" {dataset.units}" if dataset.units else ""
        facts.append(
            _fact(
                _PROPERTY_CATEGORY.get(dataset.property_id, FactCategory.ELECTRONIC),
                dataset.name,
                value,
                dataset.property_id,
                display=f"{value:.4g}{units}",
                units=dataset.units,
                link=FactLink(
                    target="calculator_inspector",
                    params={"calculator_id": dataset.property_id, "atom": index},
                    label=f"Open {dataset.name}",
                ),
            )
        )
    return facts


def collect_spectra(mol: Any, index: int, context: dict) -> list[AtomFact]:
    """NMR shieldings and any other per-nucleus spectrum already computed."""
    spectra: Iterable[SpectrumResult] = context.get("spectra", {}).values()
    facts: list[AtomFact] = []
    for spectrum in spectra:
        if index not in spectrum.values:
            continue
        value = spectrum.values[index]
        units = f" {spectrum.units}" if spectrum.units else ""
        facts.append(
            _fact(
                FactCategory.SPECTROSCOPY,
                spectrum.name,
                value,
                spectrum.spectrum_type,
                display=f"{value:.3f}{units}",
                units=spectrum.units,
                link=FactLink(
                    target="nmr_view",
                    params={"spectrum_type": spectrum.spectrum_type, "atom": index},
                    label=f"Open {spectrum.name}",
                ),
            )
        )
    return facts


def collect_structure_issues(mol: Any, index: int, context: dict) -> list[AtomFact]:
    """Structure-check findings that name this atom."""
    issues: Iterable[StructureIssue] = context.get("issues", ())
    facts: list[AtomFact] = []
    for issue in issues:
        if index not in issue.atom_indices:
            continue
        facts.append(
            _fact(
                FactCategory.REGULATORY if issue.category == "regulatory" else FactCategory.STRUCTURE,
                f"{issue.severity.value.title()}: {issue.checker_id}",
                issue,
                issue.checker_id,
                basis=issue.basis,
                display=issue.message,
                link=FactLink(target="structure_check", params={"atom": index},
                              label="Open the Structure Check panel"),
            )
        )
    return facts


#: Order matters only for display -- facts are grouped by category, and
#: within a category they appear in collection order.
_COLLECTORS: tuple[Callable[[Any, int, dict], list[AtomFact]], ...] = (
    collect_intrinsic,
    collect_element,
    collect_lewis,
    collect_oxidation_state,
    collect_per_atom_data,
    collect_spectra,
    collect_structure_issues,
)


def build_atom_report(
    mol: Any,
    atom_index: int,
    *,
    molecule_uuid: str = "",
    structure_version: int = 0,
    context: dict | None = None,
    providers: Iterable[Any] = (),
) -> AtomReport:
    """Everything known about one atom.

    `context` carries results that arrived by event -- `per_atom`,
    `spectra`, `issues`. `providers` are plugin-supplied
    `AtomFactProvider`s, each asked last so a plugin cannot shadow a core
    fact by accident.

    A collector that raises is SKIPPED rather than allowed to take the
    whole report down: one badly-behaved plugin, or one analysis that
    dislikes an exotic structure, should cost its own facts and nothing
    else.
    """
    mol.UpdatePropertyCache(strict=False)
    context = context or {}
    facts: list[AtomFact] = []

    for collector in _COLLECTORS:
        try:
            facts.extend(collector(mol, atom_index, context))
        except Exception:  # noqa: BLE001 - a failing source costs its own facts only
            continue

    for provider in providers:
        try:
            facts.extend(provider.collect_atom_facts(mol, atom_index, context))
        except Exception:  # noqa: BLE001 - a plugin must not break the report
            continue

    return AtomReport(
        molecule_uuid=molecule_uuid,
        atom_index=atom_index,
        symbol=mol.GetAtomWithIdx(atom_index).GetSymbol(),
        structure_version=structure_version,
        facts=tuple(facts),
        assumptions=_ASSUMPTIONS,
        limitations=_limitations(facts),
    )


def _limitations(facts: list[AtomFact]) -> tuple[str, ...]:
    """Each source's own limitations, once each.

    Deliberately NO generic "some of these are heuristic" line: every fact
    already carries its own `basis` and the UI shows it per row, so a
    blanket restatement is noise that competes with the specific warnings
    a source actually wrote -- and the Lewis module's caveat about motif
    matching says the same thing better.
    """
    limitations: list[str] = []
    for fact in facts:
        for text in fact.limitations:
            if text not in limitations:
                limitations.append(text)
    return tuple(limitations)
