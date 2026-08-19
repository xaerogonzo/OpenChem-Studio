"""How to build every dialog for INSPECTION, in one place.

WHY THIS EXISTS, and it is the same argument as `tooltip_inventory`'s.
Two things need to construct every dialog in this application: the
`OPENCHEM_DRIVE` harness, which opens one so a screenshot can be taken of
it, and the help-contract guard, which walks one to ask whether its
controls are documented. Left to themselves those would become two
separate ideas of "the dialogs and what each needs", and the one that
falls out of step is always the one nobody remembers to update -- which
is exactly how `inapplicable_calculators` rotted into 27 wrong entries.

**IT KNOWS NO CHEMISTRY.** `tests/test_layering.py` forbids a `ui/`
module importing RDKit, and that rule is right here rather than
inconvenient: what a dialog needs is a MoleculeModel or a report, not the
means of computing one. `DialogContext` carries whatever the caller
already has, so this module only records which dialog takes what.

**A DIALOG THAT CANNOT BE BUILT IS REPORTED, NEVER SKIPPED.** Six of
these need a computed result -- a batch table, a per-atom calculator
result, an NMR spectrum -- and a context that has none of those must
yield "not available" rather than silently shrinking the universe. An
inventory that quietly omits what it could not construct reports full
coverage of a smaller world, which is the failure mode the whole
contract layer is written against.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DialogContext:
    """Whatever the caller already has, for builders to draw on.

    Every field is optional and defaults to None. A builder that needs one
    it has not been given raises `DialogUnavailable`, which the caller
    reports -- see the module docstring for why that is not a skip.
    """

    services: Any = None
    settings: Any = None
    molecule: Any = None
    project: Any = None
    #: A 3D molblock for the dialogs that draw one.
    conformer_molblock: str | None = None
    #: Producer-supplied results, keyed by the dialog that wants one, so a
    #: caller can supply only the ones it can afford to compute.
    results: dict[str, Any] = field(default_factory=dict)


class DialogUnavailable(RuntimeError):
    """This dialog needs something the context does not carry."""


@dataclass(frozen=True)
class DialogFixture:
    """One dialog, and how to build it."""

    #: The class name, which is also the `instance_path` prefix the walk
    #: is given -- so a control's path reads `PeriodicTableDialog/...`
    #: exactly as a panel's reads `MainWindow/Batch/...`.
    name: str
    build: Callable[[DialogContext], Any]
    #: What it needs beyond a bare context, in prose, for the report.
    needs: str = ""


def _require(context: DialogContext, *names: str) -> None:
    missing = [n for n in names if getattr(context, n, None) is None]
    if missing:
        raise DialogUnavailable(f"context carries no {', '.join(missing)}")


def _result(context: DialogContext, key: str) -> Any:
    value = context.results.get(key)
    if value is None:
        raise DialogUnavailable(f"context carries no {key!r} result")
    return value


def iter_dialog_fixtures() -> Iterator[DialogFixture]:
    """Every dialog this application can open, in a stable order.

    Imports live inside the builders so that importing this module costs
    nothing -- several of these pull in a web engine view.
    """

    def about(_context: DialogContext):
        from openchem.ui.dialogs.about_dialog import AboutDialog

        return AboutDialog()

    def conformer_options(_context: DialogContext):
        from openchem.ui.dialogs.conformer_options_dialog import ConformerOptionsDialog

        return ConformerOptionsDialog()

    def help_window(_context: DialogContext):
        from openchem.ui.dialogs.help_dialog import HelpDialog

        return HelpDialog()

    def periodic_table(_context: DialogContext):
        from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog

        return PeriodicTableDialog()

    def receptor_library(_context: DialogContext):
        from openchem.ui.dialogs.receptor_library_dialog import ReceptorLibraryDialog

        return ReceptorLibraryDialog()

    def external_tools(context: DialogContext):
        from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog

        _require(context, "settings")
        return ExternalToolsDialog(context.settings)

    def command_palette(_context: DialogContext):
        from openchem.ui.dialogs.command_palette import CommandPalette

        return CommandPalette([])

    def structure_lookup(context: DialogContext):
        from openchem.ui.dialogs.structure_lookup_dialog import StructureLookupDialog

        _require(context, "molecule")
        return StructureLookupDialog(
            context.molecule.canonical_smiles or "",
            context.molecule.inchikey or "",
        )

    def calculator_settings(context: DialogContext):
        from openchem.ui.dialogs.calculator_settings_dialog import CalculatorSettingsDialog

        _require(context, "services")
        registry = context.services.calculator_registry
        categories = registry.categories()
        if not categories:
            raise DialogUnavailable("no calculator is registered")
        return CalculatorSettingsDialog(registry.by_category(categories[0])[0])

    def lewis(context: DialogContext):
        from openchem.ui.dialogs.lewis_diagram_dialog import LewisDiagramDialog

        _require(context, "molecule")
        return LewisDiagramDialog(context.molecule.molblock)

    def conformer_details(context: DialogContext):
        from openchem.ui.dialogs.conformer_details_dialog import ConformerDetailsDialog

        return ConformerDetailsDialog(_result(context, "conformer"))

    def virtual_screening(context: DialogContext):
        from openchem.ui.dialogs.virtual_screening_dialog import VirtualScreeningDialog

        _require(context, "services", "project")
        return VirtualScreeningDialog(
            context.services.screening_service,
            context.services.event_bus,
            context.project,
        )

    def structure_contents(context: DialogContext):
        from openchem.ui.dialogs.structure_contents_dialog import StructureContentsDialog

        return StructureContentsDialog("Receptor", _result(context, "structure_summary"))

    def batch_analysis(context: DialogContext):
        from openchem.ui.dialogs.batch_analysis_dialog import BatchAnalysisDialog

        _require(context, "services")
        return BatchAnalysisDialog(
            _result(context, "batch_table"), context.services.chemistry_engine
        )

    def calculator_inspector(context: DialogContext):
        from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog

        _require(context, "services", "molecule")
        return CalculatorInspectorDialog(
            context.services.chemistry_engine,
            context.molecule,
            _result(context, "per_atom"),
            context.conformer_molblock,
        )

    def nmr_view(context: DialogContext):
        from openchem.ui.dialogs.nmr_view_dialog import NmrViewDialog

        _require(context, "services", "molecule")
        return NmrViewDialog(
            context.services.chemistry_engine,
            context.molecule,
            _result(context, "nmr_spectrum"),
            context.conformer_molblock,
        )

    def spatial_result(context: DialogContext):
        from openchem.ui.dialogs.spatial_result_dialog import SpatialResultDialog

        return SpatialResultDialog(
            _result(context, "spatial_report"), context.conformer_molblock or ""
        )

    yield DialogFixture("AboutDialog", about)
    yield DialogFixture("ConformerOptionsDialog", conformer_options)
    yield DialogFixture("HelpDialog", help_window)
    yield DialogFixture("PeriodicTableDialog", periodic_table)
    yield DialogFixture("ReceptorLibraryDialog", receptor_library)
    yield DialogFixture("CommandPalette", command_palette)
    yield DialogFixture("ExternalToolsDialog", external_tools, needs="settings")
    yield DialogFixture("StructureLookupDialog", structure_lookup, needs="a molecule")
    yield DialogFixture("CalculatorSettingsDialog", calculator_settings, needs="the registry")
    yield DialogFixture("LewisDiagramDialog", lewis, needs="a molecule")
    yield DialogFixture("VirtualScreeningDialog", virtual_screening, needs="a project")
    yield DialogFixture("ConformerDetailsDialog", conformer_details, needs="a conformer")
    yield DialogFixture(
        "StructureContentsDialog", structure_contents, needs="a parsed structure summary"
    )
    yield DialogFixture("BatchAnalysisDialog", batch_analysis, needs="a computed batch table")
    yield DialogFixture(
        "CalculatorInspectorDialog", calculator_inspector, needs="a per-atom result"
    )
    yield DialogFixture("NmrViewDialog", nmr_view, needs="an NMR spectrum")
    yield DialogFixture("SpatialResultDialog", spatial_result, needs="a report carrying shapes")


def dialog_names() -> list[str]:
    """Every fixture name, for a caller that wants to offer a choice."""
    return [fixture.name for fixture in iter_dialog_fixtures()]
