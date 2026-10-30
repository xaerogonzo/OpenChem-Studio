"""Every rule for "may this molecule be run as asked, and with what", in one place (`docs/AI_CALCULATION_BRIDGE.md`, section 15, "Not here: dispatch").

**THE QUANTUM CHEMISTRY PANEL'S RUN BUTTON HELD THESE RULES IN ONE 125-LINE HANDLER, AND NOTHING ELSE COULD ASK THE SAME QUESTION.** To let a person's Approve on an assistant's card start an ORCA
job, the card has to be checked by exactly the rules the button is: the same refusals in the same order, the same conformer, the same fingerprint and the same arguments to the service. A second
implementation would be a second set of rules, and the first time they disagreed an approved job would run on a structure the button would have refused. So the rules live here, the button reads its widgets
into a `RunChoice` and calls `prepare_run`, and a card builds the same `RunChoice` from the settings it was shown.

`prepare_run` decides and starts nothing. It returns a `PreparedRun` (the structure to hand ORCA, which conformer it is, the identity stamped on every result, and for an average the whole set) or a
`RunRefusal` whose message is the sentence a person is shown. `start` hands a `PreparedRun` to the service with the arguments the panel always sent. Between the two sits the one decision that is a
person's and not a rule's: a cost (`PreparedRun.asks_cost`, today the LED job) that must be accepted before anything starts. The button asks with a dialog; a card is that acceptance.

**NOTHING HERE READS A WIDGET OR PUBLISHES AN EVENT.** The panel's own bookkeeping (what is pending, which buttons are disabled, the status line) stays in the panel, since it is what its result handlers read.

Refusals are in the order the handler made them, which is the order a person fixes them in: a molecule, a conformer, a usable one, a method, a Fukui restriction, an average that resolves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.chem.calculation_input import (
    ResolvedEnsemble,
    canonical_conformer,
    find_source_conformer,
    resolve_conformer_input,
    resolve_ensemble,
)
from openchem.chem.engine import ChemistryEngine
from openchem.chem.fukui import conformer_average_message, open_shell_message
from openchem.domain.calculator import ENSEMBLE, GEOMETRY
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel

#: The calculation types that cost enough that a person must accept the cost before the job starts (`docs/AI_CALCULATION_BRIDGE.md`): it takes days, or it fills the scratch disk.
COSTLY_CALC_TYPES = frozenset({"led"})

#: What a molecule with a conformer that cannot be read is told. Said as a refusal, never run on the drawing: the drawing carries no hydrogens and ORCA would compute a plausible answer for a different molecule.
NO_USABLE_CONFORMER = (
    "The selected molecule's conformer has no usable 3D coordinates. Regenerate "
    "it with Structure ▸ Generate Conformers... first."
)

#: What a molecule with no conformer at all is told: quantum chemistry needs explicit hydrogens with real 3D positions, which the 2D editor's structure alone does not have.
NO_CONFORMER = (
    "Generate one with Structure ▸ Generate Conformers... first -- "
    "quantum chemistry needs explicit hydrogens with real 3D positions, which "
    "the 2D editor's structure alone doesn't have."
)


@dataclass(frozen=True)
class RunChoice:
    """What was asked for: a person's controls, or the settings an assistant's card showed. No structure, no rule applied."""

    #: The ORCA calculation type code (`sp`, `opt`, `opt_freq`, `nmr` ...), not its label.
    calc_type: str
    #: The whole ORCA `!` header body: method and basis, with the CPCM solvent keyword when one is chosen.
    method_basis: str
    charge: int
    multiplicity: int
    provider_id: str = "orca"
    #: Average over every stored conformer instead of running one. Only an average when the molecule holds more than one.
    average_conformers: bool = False
    #: The conformer to run on, or "" for the one every calculation uses. Ignored while averaging, as the panel's box is greyed then.
    conformer_id: str = ""


@dataclass(frozen=True)
class RunRefusal:
    """Why a run was not prepared, in the words a person is shown."""

    message: str


@dataclass(frozen=True)
class PreparedRun:
    """A run every rule has passed, ready to start: the structure to hand ORCA, which conformer it is and the identity every result is stamped with."""

    choice: RunChoice
    molecule_uuid: str
    #: What the molecule IS when the run is prepared: compared with what it is when the job lands, because an edit while ORCA runs must not hand the old structure's geometry to the new one.
    structure_identity: str
    #: The 3D molecule of the one conformer this run is about (also what a cost is asked about, for an average).
    mol: Any
    #: That conformer's own molblock, kept so the panel can show what was submitted.
    conformer_molblock: str
    fingerprint: str
    #: One-based position of that conformer among the molecule's when the run was prepared; 0 for none.
    source_slot: int
    #: What a result must say when the conformer is not the one every calculation uses; empty when it is, and for an optimization.
    conformer_note: str
    #: The whole set, for an average; None for a single run.
    ensemble: ResolvedEnsemble | None = None

    @property
    def asks_cost(self) -> bool:
        """A person must accept the cost before this starts. The button shows a dialog; an assistant's card is the acceptance."""
        return self.choice.calc_type in COSTLY_CALC_TYPES


def slot_of(molecule: MoleculeModel, fingerprint: str) -> int:
    """The one-based slot of the conformer `fingerprint` names, or 0 when it is none of the stored ones."""
    located = find_source_conformer(molecule.conformers, fingerprint)
    return located[0] + 1 if located is not None else 0


def chosen_conformer(molecule: MoleculeModel, choice: RunChoice) -> ConformerModel | None:
    """The conformer `choice` names, or None for Automatic (and for a pick that is not there, and while averaging, which has none to choose)."""
    if not choice.conformer_id or choice.average_conformers:
        return None
    return next((c for c in molecule.conformers if c.conformer_id == choice.conformer_id), None)


def chosen_conformer_note(molecule: MoleculeModel, chosen: ConformerModel | None, calc_type: str) -> str:
    """What a result must say when it was computed on a conformer that is NOT the one every calculation uses.

    **A MEASURED FACT, NOT A WARNING FOR ITS OWN SAKE.** Properties shows the results for the conformer every calculation uses (a stored result is replayed only while its input is still that
    conformer's), so a single point or an NMR run on another conformer shows in the run history and is not replayed in Properties when the molecule is selected again. Said at the moment it matters.
    An optimization is not noted: its result is a geometry that REPLACES the conformer it came from, and the 3D viewer shows it.
    """
    if chosen is None or calc_type in ("opt", "opt_freq"):
        return ""
    automatic = canonical_conformer(molecule)
    if chosen is automatic:
        return ""
    slot = next(i for i, c in enumerate(molecule.conformers) if c is chosen) + 1
    automatic_slot = next(i for i, c in enumerate(molecule.conformers) if c is automatic) + 1
    return (
        f"Computed on conformer {slot}, not the one every calculation uses (conformer {automatic_slot}). It is "
        "kept in this panel's run history; Properties shows results for the other one, so it does not come back "
        "there when the molecule is selected again."
    )


def prepare_run(engine: ChemistryEngine, molecule: MoleculeModel | None, choice: RunChoice) -> PreparedRun | RunRefusal:
    """Apply every rule to `choice` for `molecule`. Starts nothing, publishes nothing, reads no widget."""
    if molecule is None or not molecule.molblock:
        return RunRefusal("Select a molecule with a structure first.")
    if not molecule.conformers:
        # Confirmed live against a real ORCA install: molecule.molblock alone (from a SMILES import or the 2D editor) carries only heavy atoms, with hydrogens implicit, so building an ORCA
        # input straight from it silently sends an incomplete structure (a bare oxygen atom for water, not H2O) rather than failing loudly. `RDKitConformerProvider` adds explicit hydrogens before
        # embedding, so requiring a real conformer guarantees explicit hydrogens with real 3D positions.
        return RunRefusal(NO_CONFORMER)

    # THROUGH THE RESOLVER, so the molecule ORCA is handed and the identity stamped on its spectra come from one resolution: the canonical conformer, not `conformers[0]`, which agrees only while the
    # list happens to be energy-sorted.
    chosen = chosen_conformer(molecule, choice)
    target = chosen if chosen is not None else canonical_conformer(molecule)
    resolved = resolve_conformer_input(engine, molecule, target)
    if resolved.used != GEOMETRY:
        # The resolver fell back to the DRAWING (the conformer would not parse, or is flat): refused, never run.
        return RunRefusal(NO_USABLE_CONFORMER)

    if not choice.method_basis.strip():
        return RunRefusal("Enter a method/basis (e.g. 'B3LYP def2-SVP').")

    # Said here as well as by the engine and the service, so the person is told before a job is queued and not by a failed one: an open-shell species has no Fukui function until a spin state is
    # chosen, and the per-atom values do not survive the conformer-averaging path.
    if choice.calc_type == "fukui":
        if choice.multiplicity != 1:
            return RunRefusal(open_shell_message(choice.multiplicity))
        if choice.average_conformers and len(molecule.conformers) > 1:
            return RunRefusal(conformer_average_message())

    ensemble = None
    if choice.average_conformers and len(molecule.conformers) > 1:
        # Resolved BEFORE anything commits to a run, so a refusal leaves the caller as it was.
        try:
            ensemble = resolve_ensemble(engine, molecule)
        except ValueError as exc:
            return RunRefusal(f"Cannot average over the conformers: {exc}")

    return PreparedRun(
        choice=choice,
        molecule_uuid=molecule.uuid,
        structure_identity=molecule.canonical_smiles or "",
        mol=resolved.mol,
        conformer_molblock=target.molblock,
        fingerprint=resolved.fingerprint,
        source_slot=slot_of(molecule, resolved.fingerprint),
        conformer_note=chosen_conformer_note(molecule, chosen, choice.calc_type),
        ensemble=ensemble,
    )


def start(service: Any, prepared: PreparedRun) -> None:
    """Hand a prepared run to the quantum chemistry service with the arguments the panel always sent. Does what the service does: queue one job (or one per conformer) under the molecule's slot."""
    choice = prepared.choice
    if prepared.ensemble is not None:
        service.request_boltzmann_nmr(
            mols=list(prepared.ensemble.mols),
            molecule_uuid=prepared.molecule_uuid,
            calc_type=choice.calc_type,
            charge=choice.charge,
            multiplicity=choice.multiplicity,
            method_basis=choice.method_basis,
            provider_id=choice.provider_id,
            input_fingerprint=prepared.ensemble.fingerprint,
            calculation_input=ENSEMBLE,
            structure_identity=prepared.structure_identity,
        )
        return
    service.request_calculation(
        mol=prepared.mol,
        molecule_uuid=prepared.molecule_uuid,
        calc_type=choice.calc_type,
        charge=choice.charge,
        multiplicity=choice.multiplicity,
        method_basis=choice.method_basis,
        provider_id=choice.provider_id,
        input_fingerprint=prepared.fingerprint,
        calculation_input=GEOMETRY,
        structure_identity=prepared.structure_identity,
        source_slot=prepared.source_slot,
    )
