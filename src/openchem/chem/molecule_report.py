"""Collectors for `MoleculeReport` -- everything already known, molecule-wide.

Same shape and same rule as the atom and bond collectors: read, never
compute. The one deliberate exception is `collect_identity`, which calls
RDKit for the formula and InChI -- those are microsecond-scale string
operations on a structure already in memory, and a report that omitted the
formula because nobody had "run" it would be absurd.

Everything expensive arrives through `context`: descriptors, alerts,
structure-check issues and spectra are whatever the session has already
computed. An empty context gives a short report, not a slow one.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from openchem.domain.molecule_report import MoleculeReport
from openchem.domain.report import Fact, FactCategory, FactLink
from openchem.domain.structure_issue import Basis

_ASSUMPTIONS: tuple[str, ...] = (
    "Assembled from results this session already had. Nothing here starts "
    "a calculation, so a property that has not been run is absent rather "
    "than zero.",
)


def _fact(
    category: FactCategory,
    label: str,
    value: Any,
    display: str,
    source: str,
    basis: Basis = Basis.DETERMINISTIC,
    evidence: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    link: FactLink | None = None,
    units: str = "",
) -> Fact:
    return Fact(
        category=category,
        label=label,
        value=value,
        display_value=display,
        source=source,
        basis=basis,
        evidence=evidence,
        limitations=limitations,
        link=link,
        units=units,
    )


def collect_identity(mol: Any, context: dict) -> list[Fact]:
    """Formula, mass and the three identifiers.

    InChIKey is here rather than only in the Edit menu because it is the
    one string that survives a spreadsheet cell or a URL unmangled, and is
    what most databases index on -- so it is the identifier somebody
    copying a report actually wants.
    """
    facts = [
        _fact(FactCategory.IDENTITY, "Formula", rdMolDescriptors.CalcMolFormula(mol),
              rdMolDescriptors.CalcMolFormula(mol), "RDKit"),
        _fact(FactCategory.IDENTITY, "Molecular weight", Descriptors.MolWt(mol),
              f"{Descriptors.MolWt(mol):.2f}", "RDKit", units="g/mol"),
        _fact(FactCategory.IDENTITY, "Exact mass", Descriptors.ExactMolWt(mol),
              f"{Descriptors.ExactMolWt(mol):.4f}", "RDKit", units="g/mol"),
    ]
    name = context.get("display_name") or ""
    if name:
        facts.insert(0, _fact(FactCategory.IDENTITY, "Name", name, name, "project"))

    try:
        # Implicit hydrogens. A report is often built on an H-added
        # molecule (anything that has been through 3D embedding is), and
        # `[H]OC(=O)c1c([H])c([H])...` is the truthful SMILES of that
        # object while being useless as the identifier somebody wants to
        # copy. The structure is unchanged; only the writing of it is.
        smiles = Chem.MolToSmiles(Chem.RemoveHs(mol))
        facts.append(_fact(FactCategory.IDENTITY, "SMILES", smiles, smiles, "RDKit"))
    except Exception:  # noqa: BLE001 - an unwriteable structure loses one line
        pass
    try:
        key = Chem.MolToInchiKey(mol)
        if key:
            facts.append(_fact(FactCategory.IDENTITY, "InChIKey", key, key, "RDKit"))
    except Exception:  # noqa: BLE001 - InChI refuses some valid structures outright
        pass
    return facts


def collect_composition(mol: Any, _context: dict) -> list[Fact]:
    """Counts, from the graph. All exact, none of them a prediction."""
    ring_info = mol.GetRingInfo()
    aromatic_rings = sum(
        1
        for ring in ring_info.AtomRings()
        if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring)
    )
    heavy = mol.GetNumHeavyAtoms()
    charge = Chem.GetFormalCharge(mol)
    fragments = len(Chem.GetMolFrags(mol))
    facts = [
        _fact(FactCategory.STRUCTURE, "Heavy atoms", heavy, str(heavy), "RDKit"),
        _fact(FactCategory.STRUCTURE, "Bonds", mol.GetNumBonds(),
              str(mol.GetNumBonds()), "RDKit"),
        _fact(FactCategory.TOPOLOGY, "Rings", ring_info.NumRings(),
              str(ring_info.NumRings()), "RDKit"),
        _fact(FactCategory.TOPOLOGY, "Aromatic rings", aromatic_rings,
              str(aromatic_rings), "RDKit"),
        _fact(FactCategory.STRUCTURE, "Rotatable bonds",
              rdMolDescriptors.CalcNumRotatableBonds(mol),
              str(rdMolDescriptors.CalcNumRotatableBonds(mol)), "RDKit",
              limitations=(
                  "The strict definition, which excludes amide and ester "
                  "bonds. A per-bond view flags more bonds than this counts.",
              )),
        _fact(FactCategory.ELECTRONIC, "Formal charge", charge,
              f"{charge:+d}" if charge else "0", "RDKit"),
    ]
    if fragments > 1:
        # Worth saying explicitly: a great deal of chemistry silently
        # assumes one connected species, and a salt or a drawn pair is the
        # commonest reason a result looks wrong.
        facts.append(
            _fact(FactCategory.STRUCTURE, "Separate species", fragments,
                  f"{fragments} disconnected fragments", "RDKit",
                  limitations=(
                      "Several properties assume a single connected "
                      "molecule and will describe the whole assembly.",
                  ))
        )
    return facts


def collect_conformers(mol: Any, context: dict) -> list[Fact]:
    """How much geometry exists, and whether it is real 3D.

    A 2D depiction has conformers too, and anything that needs a geometry
    will refuse or mislead on one. Saying which kind is present is what
    turns "why is this greyed out" into an answer.
    """
    count = context.get("conformer_count")
    if count is None:
        count = mol.GetNumConformers()
    if not count:
        return [
            _fact(FactCategory.GEOMETRY, "3D conformers", 0,
                  "none -- generate conformers for anything needing geometry",
                  "project")
        ]
    is_3d = mol.GetNumConformers() > 0 and mol.GetConformer().Is3D()
    return [
        _fact(FactCategory.GEOMETRY, "3D conformers", count, str(count), "project"),
        _fact(FactCategory.GEOMETRY, "Coordinates", is_3d,
              "3D" if is_3d else "2D depiction only", "RDKit",
              limitations=() if is_3d else (
                  "2D coordinates are drawing units. Distances and angles "
                  "read off them are not measurements.",
              )),
    ]


def collect_descriptors(_mol: Any, context: dict) -> list[Fact]:
    """Whatever descriptors the session has already computed.

    Grouped into report categories by the descriptor's OWN category string,
    so a new calculator lands somewhere sensible without this function
    learning about it.
    """
    mapping = {
        "physicochemical": FactCategory.STRUCTURE,
        "identity": FactCategory.IDENTITY,
        "topology": FactCategory.TOPOLOGY,
        "charge": FactCategory.ELECTRONIC,
        "quantum": FactCategory.QUANTUM,
        "quantum_chemistry": FactCategory.QUANTUM,
        "geometry": FactCategory.GEOMETRY,
        "regulatory": FactCategory.REGULATORY,
        "nmr": FactCategory.SPECTROSCOPY,
    }
    facts: list[Fact] = []
    for descriptor in context.get("descriptors", ()) or ():
        value = getattr(descriptor, "value", None)
        if value is None:
            continue
        category = mapping.get(getattr(descriptor, "category", ""), FactCategory.STRUCTURE)
        display = f"{value:.4g}" if isinstance(value, float) else str(value)
        facts.append(
            _fact(
                category,
                getattr(descriptor, "name", "") or getattr(descriptor, "descriptor_id", ""),
                value,
                display,
                getattr(descriptor, "provider", "descriptor"),
                units=getattr(descriptor, "units", "") or "",
                link=FactLink(
                    target="calculator_inspector",
                    params={"descriptor_id": getattr(descriptor, "descriptor_id", "")},
                    label="Open in Properties",
                ),
            )
        )
    return facts


def collect_alerts(_mol: Any, context: dict) -> list[Fact]:
    """Structural-alert catalogues that have run.

    An alert that matched NOTHING is still reported, because "PAINS: none
    matched" and "PAINS was never run" are different statements and the
    difference is the whole reason the catalogue was run.
    """
    facts: list[Fact] = []
    for alert in context.get("alerts", ()) or ():
        matched = list(getattr(alert, "matched", ()) or ())
        facts.append(
            _fact(
                FactCategory.REGULATORY,
                getattr(alert, "name", "") or getattr(alert, "alert_id", "alert"),
                matched,
                ", ".join(matched) if matched else "none matched",
                getattr(alert, "alert_id", "alerts"),
                basis=Basis.HEURISTIC,
            )
        )
    return facts


def collect_structure_check(_mol: Any, context: dict) -> list[Fact]:
    """A summary of the checker's findings, not a copy of them.

    The Structure Check panel already lists every issue with its fix. What
    a molecule report adds is the one-line state -- and a link to the panel
    that has the detail.
    """
    issues = list(context.get("issues", ()) or ())
    if not issues:
        return []
    by_severity: dict[str, int] = {}
    for issue in issues:
        name = str(getattr(getattr(issue, "severity", ""), "value", "")) or "issue"
        by_severity[name] = by_severity.get(name, 0) + 1
    summary = ", ".join(f"{count} {name}" for name, count in sorted(by_severity.items()))
    return [
        _fact(
            FactCategory.STRUCTURE, "Structure check", by_severity, summary,
            "StructureCheck", basis=Basis.HEURISTIC,
            link=FactLink(target="structure_check", params={},
                          label="Open Structure Check"),
        )
    ]


def collect_lewis(mol: Any, _context: dict) -> list[Fact]:
    """The molecule's Lewis character, as counts rather than a site list.

    The per-atom detail belongs on the atom report; what belongs here is
    "this molecule has 3 donor sites and 1 acceptor", which is the shape
    of the question somebody asks before choosing a partner for it.
    """
    from openchem.chem.lewis import analyse

    analysis = analyse(mol)
    sites = list(getattr(analysis, "sites", ()) or ())
    if not sites:
        return []
    roles: dict[str, int] = {}
    for site in sites:
        name = str(getattr(site.role, "value", site.role))
        roles[name] = roles.get(name, 0) + 1
    return [
        _fact(
            FactCategory.ELECTRONIC, "Lewis sites", roles,
            ", ".join(f"{count} {name}" for name, count in sorted(roles.items())),
            "LewisAnalysis", basis=Basis.HEURISTIC,
            link=FactLink(target="interactions", params={}, label="Open Interactions"),
        )
    ]


def collect_spectra(_mol: Any, context: dict) -> list[Fact]:
    """Which spectra exist, not their contents."""
    facts: list[Fact] = []
    for spectrum in context.get("spectra", ()) or ():
        name = getattr(spectrum, "name", "") or getattr(spectrum, "spectrum_type", "")
        values = getattr(spectrum, "values", {}) or {}
        facts.append(
            _fact(
                FactCategory.SPECTROSCOPY, name, spectrum,
                f"{len(values)} predicted shifts",
                getattr(spectrum, "method", "spectrum"),
                link=FactLink(target="nmr_view", params={}, label="Open NMR"),
            )
        )
    return facts


_COLLECTORS: tuple[Callable[[Any, dict], list[Fact]], ...] = (
    collect_identity,
    collect_composition,
    collect_conformers,
    collect_descriptors,
    collect_alerts,
    collect_structure_check,
    collect_lewis,
    collect_spectra,
)


def build_molecule_report(
    mol: Any,
    *,
    molecule_uuid: str = "",
    structure_version: int = 0,
    context: dict | None = None,
    providers: Iterable[Any] = (),
) -> MoleculeReport:
    """Everything known about a molecule.

    A collector that raises is SKIPPED, for the same reason as the atom and
    bond reports: one bad source should cost its own facts and no others.
    """
    mol.UpdatePropertyCache(strict=False)
    context = context or {}
    facts: list[Fact] = []

    for collector in _COLLECTORS:
        try:
            facts.extend(collector(mol, context))
        except Exception:  # noqa: BLE001 - a failing source costs its own facts only
            continue

    for provider in providers:
        try:
            facts.extend(provider.collect_molecule_facts(mol, context))
        except Exception:  # noqa: BLE001 - a plugin must not break the report
            continue

    formula = ""
    try:
        formula = rdMolDescriptors.CalcMolFormula(mol)
    except Exception:  # noqa: BLE001 - label only
        pass

    return MoleculeReport(
        molecule_uuid=molecule_uuid,
        display_name=context.get("display_name", "") or "",
        formula=formula,
        atom_count=mol.GetNumAtoms(),
        bond_count=mol.GetNumBonds(),
        structure_version=structure_version,
        facts=tuple(facts),
        assumptions=_ASSUMPTIONS,
        limitations=_limitations(facts),
    )


def _limitations(facts: list[Fact]) -> tuple[str, ...]:
    limitations: list[str] = []
    for fact in facts:
        for text in fact.limitations:
            if text not in limitations:
                limitations.append(text)
    return tuple(limitations)
