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

from rdkit import Chem

from openchem.chem import bond_dissociation
from openchem.chem.calculation_input import (
    ResolvedEnsemble,
    canonical_conformer,
    find_source_conformer,
    input_fingerprint,
    resolve_conformer_input,
    resolve_ensemble,
)
from openchem.chem.engine import ChemistryEngine
from openchem.chem.fukui import conformer_average_message, open_shell_message
from openchem.chem.proton_affinity import OutOfScope as ProtonAffinityOutOfScope
from openchem.chem.proton_affinity import Sequence as ProtonAffinitySequence
from openchem.chem.tautomer_distribution import (
    CONFIRMATION_THRESHOLD,
    ModelPolicy,
    TautomerCandidate,
    generate_tautomer_candidates,
    policy_for_mode,
)
from openchem.domain.calculator import DRAWING, ENSEMBLE, GEOMETRY
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


#: Said for an interaction breakdown of a structure that is not two separate species: they are the fragments it decomposes the interaction between.
TWO_PARTNERS_TITLE = "Two partners needed"
#: The sentence that goes with it: what an interaction breakdown needs and how to draw it.
TWO_PARTNERS_MESSAGE = (
    "An interaction breakdown needs exactly two separate species — "
    "they are the fragments it decomposes the interaction between.\n\n"
    "Draw the two partners as separate molecules (a Lewis acid and "
    "its base, a hydrogen-bonded pair) rather than joined by a bond."
)

#: What the estimate is, said wherever the cost is shown, so nobody takes a guide to the order of the cost for a prediction.
COST_ESTIMATE_CAVEAT = "The estimate is scaled from two measured jobs and is a guide to the order of the cost, not a prediction."


@dataclass(frozen=True)
class CostReview:
    """What `review_cost` found: nothing in the way (`ok`), a structure the job cannot be run on (`two_partners`, `geometry`), or a cost to be accepted (`expensive`)."""

    kind: str
    title: str = ""
    message: str = ""

    @property
    def refuses(self) -> bool:
        """The job cannot be run on this structure, whoever is asked."""
        return self.kind in ("two_partners", "geometry")


def led_cost_message(estimate) -> str:
    """The cost of an interaction breakdown in words: the advice, the size of the job and the caveat. One text for the panel's dialog and for an assistant's card."""
    return f"{estimate.advice}\n\n{estimate.atoms} atoms, {estimate.basis_functions} basis functions, DLPNO-CCSD(T).\n\n{COST_ESTIMATE_CAVEAT}"


def review_cost(prepared: PreparedRun) -> CostReview:
    """What a job that costs enough to ask first (`PreparedRun.asks_cost`) would be run on, and what it would cost, from the molecule that WOULD be handed to ORCA.

    The refusals are the structure's (two species, not interpenetrating) and apply however the question is put; `expensive` is the cost a person accepts. The panel asks it in a dialog; an assistant's
    card shows `led_cost_message` and its Approve is the acceptance.
    """
    return review_led(prepared.mol) if prepared.asks_cost else CostReview("ok")


def review_led(mol) -> CostReview:
    """`review_cost` for an interaction breakdown of `mol`, a 3D molecule."""
    from openchem.chem.orca_led import estimate_led_cost_for

    estimate = estimate_led_cost_for(mol)
    if estimate.fragment_count != 2:
        return CostReview("two_partners", TWO_PARTNERS_TITLE, TWO_PARTNERS_MESSAGE)
    if estimate.geometry_problem:
        # Refused, not warned. A live run of an overlapping pair produced +40619 kcal/mol -- arithmetically correct, physically meaningless, and indistinguishable from a real result once it is just a number.
        return CostReview("geometry", "This geometry cannot be decomposed", estimate.geometry_problem)
    if estimate.should_warn:
        return CostReview("expensive", "This calculation is expensive", led_cost_message(estimate))
    return CostReview("ok")


def led_cost_of_smiles(smiles: str) -> tuple[str, str]:
    """`(refusal, cost text)` of an interaction breakdown of a structure given as SMILES, before any conformer exists: what a card shows so that Approve is an informed acceptance.

    The refusal is "" when the structure is two species. The size is counted with explicit hydrogens, as ORCA is handed them, and the geometry is not judged (there is none yet): `review_cost` does
    that on the molecule that would really be run.
    """
    from rdkit import Chem

    from openchem.chem.orca_led import estimate_led_cost_for

    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return "The drawn structure could not be read, so its cost cannot be estimated.", ""
    estimate = estimate_led_cost_for(Chem.AddHs(mol))
    if estimate.fragment_count != 2:
        return TWO_PARTNERS_MESSAGE, ""
    return "", led_cost_message(estimate)


# --- proton affinity: a fixed protocol, so the whole of its request is the structure -------------------------------------------------------------------------

#: The calculation type a proton-affinity run is recorded under (`QuantumChemistryService._new_proton_affinity_run`), and so what its run record is matched by.
PROTON_AFFINITY = "proton_affinity"

#: Above this many ORCA jobs a proton-affinity run asks before it starts (a base with one site is two jobs; pyridine's four sites make five).
PROTON_AFFINITY_CONFIRM_ABOVE = 4


def outside_scope_text(warnings: list[str]) -> str:
    """The paragraph a run's question opens with when the molecule is outside what the benchmark measured (empty inside it): computed anyway, and said so."""
    if not warnings:
        return ""
    return ("This molecule is outside what the benchmark measured: " + "; ".join(warnings) + ". It can still be computed, but the measured error does not apply to it, "
            "so read the result as an estimate.\n\n")


@dataclass(frozen=True)
class PreparedProtonAffinity:
    """A base the proton-affinity protocol can run on: the structure, how many ORCA jobs it is and what the benchmark did not measure about it."""

    smiles: str
    jobs: int
    scope_warnings: tuple[str, ...]

    @property
    def asks_cost(self) -> bool:
        """A person must accept this before it starts: a long run, or a base outside what was measured."""
        return self.jobs > PROTON_AFFINITY_CONFIRM_ABOVE or bool(self.scope_warnings)

    def question(self) -> str:
        """The cost in words: the scope paragraph, the job count and that it can take hours. One text for the panel's dialog and for an assistant's card."""
        return (
            outside_scope_text(list(self.scope_warnings))
            + f"This will run {self.jobs} ORCA geometry optimizations with frequencies (M062X/def2-TZVPD) for the base and its conjugate acids, "
            "one after another, and a structure that keeps an imaginary vibration is run once more. It can take minutes to hours."
        )

    def card_text(self) -> str:
        """What a card says: nothing beyond the cost, since the base is the whole of the request."""
        return self.question()


def prepare_proton_affinity(smiles: str) -> PreparedProtonAffinity | RunRefusal:
    """Whether the protocol can run on `smiles`, and what it would take. Starts nothing.

    Needs no conformer and no method: every structure is embedded fresh from the 2D structure and the protocol is exactly the one that was measured. A base it cannot compute is refused with its
    reason; one it can compute but the benchmark did not measure comes back with its warnings (computed anyway, the result labelled an estimate).
    """
    if not smiles:
        return RunRefusal("Select a molecule with a structure first.")
    try:
        sequence = ProtonAffinitySequence(smiles)
    except ProtonAffinityOutOfScope as refusal:
        return RunRefusal(f"Proton affinity does not apply: {refusal}")
    except Exception as error:  # noqa: BLE001 - a structure that cannot be embedded is refused with its reason, not crashed on
        return RunRefusal(f"Proton affinity could not start: {error}")
    return PreparedProtonAffinity(smiles, sequence.total, tuple(sequence.scope_warnings))


def prepare_proton_affinity_for(molecule: MoleculeModel | None) -> PreparedProtonAffinity | RunRefusal:
    """`prepare_proton_affinity` for a molecule in the project: the structure it would run on is the drawing's canonical SMILES."""
    if molecule is None or not molecule.molblock or not molecule.canonical_smiles:
        return RunRefusal("Select a molecule with a structure first.")
    return prepare_proton_affinity(molecule.canonical_smiles)


def start_proton_affinity(service: Any, engine: ChemistryEngine, molecule: MoleculeModel) -> None:
    """Hand the proton-affinity run to the service with the identity of the drawing as it is NOW, the arguments the panel's button always sent."""
    service.request_proton_affinity(
        smiles=molecule.canonical_smiles,
        molecule_uuid=molecule.uuid,
        calculation_input=DRAWING,
        input_fingerprint=input_fingerprint(engine, molecule, DRAWING),
        structure_identity=molecule.canonical_smiles,
    )


# --- bond dissociation: a fixed protocol whose one choice, which bonds, is stated on the card --------------------------------------------------------------------

#: The calculation type a bond-dissociation run is recorded under (`QuantumChemistryService._new_bond_dissociation_run`), and so what its run record is matched by.
BOND_DISSOCIATION = "bond_dissociation"

#: Above this many ORCA jobs the button asks before it starts (a molecule with three conformers and three bonds is a dozen).
BOND_DISSOCIATION_CONFIRM_ABOVE = 6


@dataclass(frozen=True)
class PreparedBondDissociation:
    """The bonds a bond-dissociation run would compute on a structure, how many ORCA jobs that is, and what the benchmark did not measure about it."""

    smiles: str
    #: the heavy atom of each bond class that will be computed, in the order the choice dialog shows them
    atoms: tuple[int, ...]
    labels: tuple[str, ...]
    #: the bond classes the run does NOT compute because one run takes at most `MAX_BONDS` (the dialog ticks the first ones, so does a card)
    left_out: tuple[str, ...]
    jobs: int
    scope_warnings: tuple[str, ...]

    def question(self) -> str:
        """The cost in words: the scope paragraph, the job count and that it can take hours. One text for the panel's dialog and for an assistant's card."""
        return (
            outside_scope_text(list(self.scope_warnings))
            + f"This will run {self.jobs} ORCA jobs (M062X/def2-TZVPD: the hydrogen atom, then optimizations with frequencies of the molecule and of each radical), one after another, "
            "and a structure that keeps an imaginary vibration is run once more. It can take minutes to hours."
        )

    def card_text(self) -> str:
        """What a card says: which bonds, which are left out and why, then the cost. A person who wants other bonds starts the run from the panel, where they are chosen."""
        text = "The bonds it would compute: " + "; ".join(self.labels) + "."
        if self.left_out:
            text += (
                f" One run computes at most {bond_dissociation.MAX_BONDS}, so it leaves out: " + "; ".join(self.left_out)
                + ". To compute those, use the Quantum Chemistry panel's Bond dissociation button, where the bonds are chosen."
            )
        return text + " The result states the weakest bond computed and every bond's own value. " + self.question()


def bond_choices(smiles: str) -> list[dict] | RunRefusal:
    """The X-H bonds a person can choose from on `smiles`, or the sentence that says the calculation does not apply. Starts nothing."""
    if not smiles:
        return RunRefusal("Select a molecule with a structure first.")
    try:
        return bond_dissociation.describe_bonds(smiles)
    except ProtonAffinityOutOfScope as refusal:
        return RunRefusal(f"Bond dissociation does not apply: {refusal}")
    except Exception as error:  # noqa: BLE001 - a structure that cannot be read is refused with its reason, not crashed on
        return RunRefusal(f"Bond dissociation could not start: {error}")


def prepare_bond_dissociation(smiles: str, atoms: list[int] | None = None) -> PreparedBondDissociation | RunRefusal:
    """Whether the protocol can run on `smiles` for `atoms`, and what it would take. Starts nothing.

    `atoms` None is the choice dialog's own default: the first `MAX_BONDS` bond classes, all of them when there are no more. Which bond is the WEAKEST is what the run finds, so there is nothing to
    pre-select. A molecule it cannot compute is refused with its reason; one it can compute but the benchmark did not measure comes back with its warnings (computed anyway, an estimate).
    """
    classes = bond_choices(smiles)
    if isinstance(classes, RunRefusal):
        return classes
    chosen = [b["atom"] for b in classes[: bond_dissociation.MAX_BONDS]] if atoms is None else list(atoms)
    try:
        sequence = bond_dissociation.Sequence(smiles, chosen)
    except ProtonAffinityOutOfScope as refusal:
        return RunRefusal(f"Bond dissociation does not apply: {refusal}")
    except Exception as error:  # noqa: BLE001
        return RunRefusal(f"Bond dissociation could not start: {error}")
    by_atom = {b["atom"]: b["label"] for b in classes}
    left_out = tuple(b["label"] for b in classes if b["atom"] not in chosen)
    return PreparedBondDissociation(smiles, tuple(chosen), tuple(by_atom[a] for a in chosen), left_out, sequence.total, tuple(sequence.scope_warnings))


def prepare_bond_dissociation_for(molecule: MoleculeModel | None, atoms: list[int] | None = None) -> PreparedBondDissociation | RunRefusal:
    """`prepare_bond_dissociation` for a molecule in the project: the structure it would run on is the drawing's canonical SMILES."""
    if molecule is None or not molecule.molblock or not molecule.canonical_smiles:
        return RunRefusal("Select a molecule with a structure first.")
    return prepare_bond_dissociation(molecule.canonical_smiles, atoms)


def start_bond_dissociation(service: Any, engine: ChemistryEngine, molecule: MoleculeModel, atoms: list[int]) -> None:
    """Hand the bond-dissociation run to the service with the identity of the drawing as it is NOW, the arguments the panel's button always sent."""
    service.request_bond_dissociation(
        smiles=molecule.canonical_smiles,
        atoms=atoms,
        molecule_uuid=molecule.uuid,
        calculation_input=DRAWING,
        input_fingerprint=input_fingerprint(engine, molecule, DRAWING),
        structure_identity=molecule.canonical_smiles,
    )


# --- tautomer distribution: the three settings, run on the drawing, and a job count that enumeration decides -----------------------------------------------

#: The calculation type a tautomer-distribution run is recorded under (`QuantumChemistryService._new_tautomer_distribution_run`), and so what its run record is matched by.
TAUTOMER_DISTRIBUTION = "tautomer_distribution"


def no_tautomers_message(embedding_failures: int) -> str:
    """Why a molecule has no candidates to run: none could be generated, and how many of them failed to embed in 3D."""
    message = "No tautomer candidates could be generated for this molecule."
    if embedding_failures:
        message += f" ({embedding_failures} failed to embed in 3D.)"
    return message


@dataclass(frozen=True)
class PreparedTautomers:
    """The candidates a tautomer-distribution run would optimize on ORCA, and what that costs: the jobs, the tautomers and stereoisomers they stand for, and what is incomplete.

    **A candidate is one ORCA job**, so the number that matters for cost is `jobs`, named beside the tautomers. A tautomer over the stereo cap costs less than it would but yields an INCOMPLETE
    result, which the person must hear before confirming (`question`).
    """

    candidates: tuple[TautomerCandidate, ...]
    embedding_failures: int
    policy: ModelPolicy

    @property
    def jobs(self) -> int:
        return len(self.candidates)

    @property
    def tautomers(self) -> int:
        return len({c.tautomer_fingerprint or c.fingerprint for c in self.candidates})

    @property
    def stereo_classes(self) -> int:
        return len({c.conformer.stereo_fingerprint or c.fingerprint for c in self.candidates})

    @property
    def truncated(self) -> int:
        """Tautomers over the stereoisomer cap, which use a single fallback configuration."""
        return len({c.tautomer_fingerprint for c in self.candidates if c.stereo.truncated})

    @property
    def conformer_truncated(self) -> int:
        """Stereoisomers with more distinct conformers than the cap, of which the lowest are used."""
        return len({c.conformer.stereo_fingerprint for c in self.candidates if c.conformer.truncated})

    def asks_cost(self, threshold: int = CONFIRMATION_THRESHOLD) -> bool:
        """A person must accept this before it starts: more jobs than `threshold`, or a result that will be incomplete. The panel passes its own name for the threshold, which its tests lower."""
        return self.jobs > threshold or bool(self.truncated) or bool(self.conformer_truncated)

    def question(self) -> str:
        """The cost in words: the jobs, the tautomers and stereoisomers, the conformer search and what will be marked incomplete. One text for the panel's dialog and for an assistant's card."""
        which = "every retained sampled conformer" if self.policy.conformer_search == "full_orca" else "the lowest distinct conformers"
        text = (
            f"This will run {self.jobs} real ORCA geometry optimizations "
            f"for {self.tautomers} tautomer(s) and {self.stereo_classes} stereoisomer(s) "
            f"({which} of each; conformer search {self.policy.conformer_search}). "
        )
        if self.conformer_truncated:
            text += (
                f"{self.conformer_truncated} stereoisomer(s) have more distinct conformers than the cap "
                f"({self.policy.conformer_cap}); the lowest ones are used and the result will be marked "
                f"incomplete, with no population percentages. "
            )
        if self.truncated:
            text += (
                f"{self.truncated} tautomer(s) exceed the stereoisomer cap and will use a single "
                f"fallback configuration, so the result will be marked incomplete and show no "
                f"population percentages. "
            )
        return text + "This can take a long time."

    def card_text(self) -> str:
        """What a card says: the cost, and that the conformer search is the default one (the panel's Full ORCA conformers box, on the Tautomers button, chooses the other)."""
        return (
            "It uses the default conformer search; the Quantum Chemistry panel's Full ORCA conformers box, on its Tautomers button, runs every retained sampled conformer instead. "
            + self.question()
        )

    def queued_text(self) -> str:
        """The panel's status line once the run is handed to the service."""
        return f"queued -- {self.jobs} optimization(s) for {self.tautomers} tautomer(s)" + (
            f", {self.embedding_failures} embedding failure(s) excluded" if self.embedding_failures else ""
        )


def tautomers_prepared(candidates: list[TautomerCandidate], embedding_failures: int, policy: ModelPolicy) -> PreparedTautomers | RunRefusal:
    """The candidates `generate_tautomer_candidates` returned as a run, or the sentence that says there is none."""
    if not candidates:
        return RunRefusal(no_tautomers_message(embedding_failures))
    return PreparedTautomers(tuple(candidates), embedding_failures, policy)


def prepare_tautomers(smiles: str, full: bool = False) -> PreparedTautomers | RunRefusal:
    """Whether a tautomer distribution can run on `smiles`, and what it would take. Starts nothing.

    The candidates are enumerated and embedded from the SMILES, every seed fixed, so the same SMILES gives the same jobs: the card and the run that follows it are the same count by construction. `full`
    is the conformer search the panel's "Full ORCA conformers" box selects; a card uses the default.
    """
    if not smiles:
        return RunRefusal("Select a molecule with a structure first.")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return RunRefusal("Tautomer distribution could not start: the structure could not be read.")
    policy = policy_for_mode(full)
    try:
        candidates, embedding_failures = generate_tautomer_candidates(mol, policy=policy)
    except Exception as error:  # noqa: BLE001 - a structure that cannot be enumerated is refused with its reason, not crashed on
        return RunRefusal(f"Tautomer distribution could not start: {error}")
    return tautomers_prepared(candidates, embedding_failures, policy)


def prepare_tautomers_for(molecule: MoleculeModel | None, full: bool = False) -> PreparedTautomers | RunRefusal:
    """`prepare_tautomers` for a molecule in the project: the structure it runs on is the drawing's canonical SMILES."""
    if molecule is None or not molecule.molblock or not molecule.canonical_smiles:
        return RunRefusal("Select a molecule with a structure first.")
    return prepare_tautomers(molecule.canonical_smiles, full)


def start_tautomer_distribution(service: Any, engine: ChemistryEngine, molecule: MoleculeModel, prepared: PreparedTautomers, charge: int, multiplicity: int, method_basis: str) -> None:
    """Hand the tautomer-distribution run to the service with the identity of the drawing as it is NOW, the arguments the panel's button always sent."""
    service.request_tautomer_distribution(
        candidates=list(prepared.candidates),
        molecule_uuid=molecule.uuid,
        charge=charge,
        multiplicity=multiplicity,
        method_basis=method_basis,
        calculation_input=DRAWING,
        input_fingerprint=input_fingerprint(engine, molecule, DRAWING),
        policy=prepared.policy,
    )


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
