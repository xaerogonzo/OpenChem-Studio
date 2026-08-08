"""What the app can honestly say about a periodic solid, and what it cannot.

Reuses `Fact` and `ReportResult` -- the same shapes the atom, bond,
molecule and substance reports use -- so a reader who has learned the
headings once does not learn them again for a crystal. That reuse is
possible precisely BECAUSE `Fact` was kept free of anything molecular.

## The refusal is half the report

**Most molecular calculators mean nothing here.** A molecular weight, a
logP, a rotatable-bond count and a TPSA are all properties of a discrete
molecule; halite has no molecule and no bond. Running them against one
arbitrary formula unit would produce numbers that are arithmetically
fine and chemically meaningless -- the failure this project keeps
refusing -- so the report NAMES them as inapplicable rather than leaving
a reader to wonder why the Properties panel looks empty.

That listing is derived from the live calculator registry, not written
out by hand, so a calculator added tomorrow is covered without anybody
remembering to come back here. It is the same direction that caught two
panels missing a help topic.
"""

from __future__ import annotations

from typing import Any

from openchem.chem.crystal_analysis import (
    CrystalAnalysisError,
    coordination_shell,
    density,
    describe_cell,
    volume_per_formula_unit,
)
from openchem.domain.crystal import Crystal
from openchem.domain.report import Basis, Detail, Fact, FactCategory, ReportResult

#: Categories whose calculators are about a discrete molecule and have no
#: meaning for an infinite periodic structure. Everything registered under
#: these is listed as inapplicable.
_MOLECULAR_CATEGORIES = frozenset(
    {
        "physicochemical",
        "logp",
        "logd",
        "medicinal_chemistry",
        "admet",
        "pka",
        "topology",
        "shape",
        "surface",
        "molar_refractivity",
        "lewis",
        "stereochemistry",
        "regulatory",
    }
)


def _fact(
    category: FactCategory,
    label: str,
    value: Any,
    display: str,
    *,
    units: str = "",
    basis: Basis = Basis.DETERMINISTIC,
    evidence: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    detail: Detail = Detail.STANDARD,
) -> Fact:
    return Fact(
        category=category,
        label=label,
        value=value,
        display_value=display,
        source="Crystal",
        basis=basis,
        units=units,
        evidence=evidence,
        limitations=limitations,
        detail=detail,
    )


def inapplicable_calculators(registry: Any = None) -> list[str]:
    """Which registered calculators do not apply to a periodic solid.

    Read from the registry rather than listed here, so nothing has to be
    remembered when a calculator is added.
    """
    if registry is None:
        from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

        definitions = CALCULATOR_DEFINITIONS
    else:
        definitions = [
            definition
            for category in registry.categories()
            for definition in registry.by_category(category)
        ]
    return sorted(
        definition.display_name
        for definition in definitions
        if getattr(definition, "category", "") in _MOLECULAR_CATEGORIES
    )


def build_crystal_report(crystal: Crystal, *, report_id: str = "crystal") -> ReportResult:
    """Everything known about one periodic structure."""
    from openchem.domain.common import Provenance

    facts: list[Fact] = [
        _fact(
            FactCategory.IDENTITY,
            "Structure",
            crystal.name or "unnamed",
            crystal.name or "unnamed",
        ),
        _fact(
            FactCategory.STRUCTURE,
            "Unit cell",
            describe_cell(crystal),
            describe_cell(crystal),
            evidence=(
                "a along x, b in the xy plane -- the standard setting. Another "
                "orientation is equally valid and would not match these numbers.",
            ),
        ),
        _fact(
            FactCategory.GEOMETRY,
            "Cell volume",
            round(crystal.lattice.volume, 4),
            f"{crystal.lattice.volume:.4f}",
            units="A^3",
        ),
    ]

    if crystal.space_group:
        facts.append(
            _fact(
                FactCategory.STRUCTURE,
                "Space group",
                crystal.space_group,
                crystal.space_group
                + (f" (No. {crystal.space_group_number})" if crystal.space_group_number else ""),
            )
        )

    facts.append(
        _fact(
            FactCategory.STRUCTURE,
            "Symmetry operations",
            len(crystal.operations),
            str(len(crystal.operations)),
            evidence=(
                "as listed in the file. A file may give the centring only, which is "
                "enough when every site sits on a special position and not otherwise.",
            ),
        )
    )

    composition = crystal.composition()
    facts.append(
        _fact(
            FactCategory.IDENTITY,
            "Atoms per unit cell",
            sum(composition.values()),
            ", ".join(
                f"{element} {count:g}" for element, count in sorted(composition.items())
            ),
            evidence=(
                "counted after expanding the asymmetric unit by the symmetry "
                "operations and folding every atom back into the cell",
            ),
        )
    )

    if crystal.formula_units_z:
        per_unit = volume_per_formula_unit(crystal)
        facts.append(
            _fact(
                FactCategory.GEOMETRY,
                "Volume per formula unit",
                round(per_unit, 4),
                f"{per_unit:.4f}",
                units="A^3",
                evidence=(f"Z = {crystal.formula_units_z}",),
                detail=Detail.ADVANCED,
            )
        )

    try:
        value = density(crystal)
    except CrystalAnalysisError as error:
        facts.append(
            _fact(FactCategory.GEOMETRY, "Density", None, str(error), basis=Basis.DETERMINISTIC)
        )
    else:
        facts.append(
            _fact(
                FactCategory.GEOMETRY,
                "Density",
                round(value, 4),
                f"{value:.4f}",
                units="g/cm^3",
                evidence=(
                    "from the cell contents and volume, honouring occupancies",
                ),
                limitations=(
                    "The X-ray density of an ideal cell. A measured density is "
                    "lower where the real material has vacancies, porosity or "
                    "inclusions, and this cannot see any of those.",
                ),
            )
        )

    for site in crystal.sites:
        try:
            shell = coordination_shell(crystal, site.label)
        except CrystalAnalysisError as error:
            facts.append(
                _fact(
                    FactCategory.STRUCTURE,
                    f"Coordination of {site.label}",
                    None,
                    str(error),
                )
            )
            continue
        partners = ", ".join(
            sorted({neighbour.element for neighbour in shell.neighbours})
        )
        facts.append(
            _fact(
                FactCategory.STRUCTURE,
                f"Coordination of {site.label}",
                shell.coordination_number,
                f"{shell.coordination_number} {partners}"
                f" at {shell.mean_distance:.3f} A" if shell.neighbours else "none found",
                basis=Basis.HEURISTIC,
                evidence=(
                    f"first shell ended at a {100 * shell.gap_fraction:.0f}% jump in "
                    f"neighbour distance, searching to {shell.search_radius:.1f} A",
                    "clear-cut" if shell.is_clear_cut else
                    "NOT clear-cut -- the shell boundary here depends on the threshold",
                ),
                limitations=(
                    "A coordination number is a judgement about where a shell ends, "
                    "not a measurement. The distances are the measurement.",
                ),
            )
        )

    if crystal.unhandled:
        facts.append(
            _fact(
                FactCategory.IDENTITY,
                "Fields not interpreted",
                list(crystal.unhandled),
                f"{len(crystal.unhandled)} CIF fields were read but not used",
                evidence=tuple(crystal.unhandled[:8]),
                limitations=(
                    "Anisotropic displacement, disorder groups and refinement "
                    "statistics are carried but not interpreted. Nothing above "
                    "depends on them; nothing above accounts for them either.",
                ),
                detail=Detail.ADVANCED,
            )
        )

    return ReportResult(
        molecule_uuid="",
        report_id=report_id,
        name="Crystal Structure",
        category="structure",
        facts=tuple(facts),
        limitations=(
            "This is a periodic solid, not a molecule. It has no molecular weight, "
            "no bonds and no logP, and the molecular calculators are not applicable "
            "to it -- see the report's assumptions for which.",
        ),
        assumptions=(
            "Molecular descriptors are not computed for a crystal. Running them on "
            "one arbitrary formula unit would give arithmetically correct numbers "
            "about a species that does not exist in the material.",
        ),
        provenance=Provenance(created_by="core", method="crystallography"),
    )
