"""Oxidation states, built around refusing to answer.

The rule is IUPAC's: give every bond's electrons to the more electronegative
of the two atoms, split homonuclear bonds evenly, and add the formal charge.
It is a formalism -- a bookkeeping convention for electron counting -- and
not a measurement. No instrument reads +3 off an iron atom.

**The refusal is the feature.** The rule was verified on eight cases and
then found to break on a ninth, and that ninth is why this module is shaped
the way it is:

    Fe3O4 magnetite  ->  Fe [+3, +4, +3]

Magnetite is one Fe(II) and two Fe(III). The rule invents an Fe(IV), misses
the mixed valence, and which iron gets the wrong number depends on how the
SMILES happened to be written. Further measurement found three more classes
of the same failure:

| structure          | this rule | the answer | why it fails            |
|--------------------|-----------|------------|-------------------------|
| Fe3O4              | +3 +4 +3  | +2 +3 +3   | mixed valence           |
| Cr(CO)6            | Cr +6     | Cr 0       | pi back-bonding         |
| Fe(CO)5            | Fe +5     | Fe 0       | pi back-bonding         |
| B2H6               | B +4      | B +3       | 3c-2e bridges           |

and, just as importantly, four near-misses where it is RIGHT and must not
be refused:

| Hg2Cl2   | Hg +1 each | correct -- a real M-M dimer      |
| CH3MgBr  | Mg +2      | correct -- polar main-group bond |
| CH3Li    | Li +1      | correct -- same                  |
| Fe2O3    | Fe +3 each | correct -- not mixed valence     |

Those four are what stop the refusals being written too widely. Refusing
every metal-carbon bond would throw away methyllithium; refusing every
metal-metal bond would throw away calomel. The line falls where the
measurement put it: at TRANSITION metals bonded to carbon, and at metal
CLUSTERS rather than dimers.

Everything here is drawing-dependent by nature, and that is a property of
the formalism rather than a defect here: an oxidation state describes the
structure you drew. Ferrocene written as an ion pair is a classical ionic
description and gets Fe(+2) correctly; written with Fe bonded into the
rings it is eta-5 coordination, which this rule cannot describe, and is
refused.

**One limitation found and deliberately NOT ruled on.** A formal charge
drawn on one atom of a delocalised ring makes that ring's per-atom states
depend on where the charge was typed: cyclopentadienide comes out
C(-2) once and C(-1) four times, when the charge is really spread over all
five. A rule refusing "a charge on an aromatic ring" would also refuse
pyridinium, where the charge genuinely is localised on the nitrogen, and
no measurement here separates the two cases. So it is documented rather
than guessed at -- the same call this project made on Miller
polarizability, HLB and TSEI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent / "data" / "electronegativity.json"

#: Categories that count as "a metal" for the cluster and mixed-valence
#: rules. Metalloids are deliberately out: boron and silicon behave as
#: main-group non-metals in this formalism.
_METAL_CATEGORIES = frozenset(
    {"alkali", "alkaline_earth", "transition", "post_transition", "lanthanide", "actinide"}
)

#: The narrower set for the metal-carbon rule. Measured: methyllithium and
#: methylmagnesium bromide come out right, chromium hexacarbonyl does not.
_BACKBONDING_CATEGORIES = frozenset({"transition", "lanthanide", "actinide"})

METHOD = "IUPAC electronegativity partition (Pauling scale)"


@dataclass(frozen=True)
class OxidationStates:
    """Per-atom states, or a refusal with its reason.

    `states` is empty whenever `refused` is set. There is deliberately no
    partial answer: the assignments are interdependent -- every atom's
    number is computed against its neighbours' -- so publishing the ones
    that "worked" beside a molecule the rule cannot describe would give
    them a credibility they have not got.
    """

    states: dict[int, int] = field(default_factory=dict)
    refused: bool = False
    reason: str = ""
    #: Which atoms drove the refusal, for highlighting.
    atom_indices: tuple[int, ...] = ()
    method: str = METHOD

    def __bool__(self) -> bool:
        return not self.refused


@lru_cache(maxsize=1)
def electronegativity_table() -> dict[str, dict[str, Any]]:
    data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _refuse(reason: str, indices: tuple[int, ...] = ()) -> OxidationStates:
    return OxidationStates(refused=True, reason=reason, atom_indices=indices)


def assign(mol: Any) -> OxidationStates:
    """Oxidation states for every atom, or one reason why not.

    Takes an RDKit molecule. Sanitization is not required -- the structures
    this is most often asked about are inorganic ones RDKit refuses -- but
    the property cache is updated so implicit hydrogen counts are available.
    """
    mol.UpdatePropertyCache(strict=False)
    table = electronegativity_table()

    unknown = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() > 0 and atom.GetSymbol() not in table
    ]
    if unknown:
        symbols = sorted({mol.GetAtomWithIdx(i).GetSymbol() for i in unknown})
        return _refuse(
            f"No Pauling electronegativity is tabulated for {', '.join(symbols)}, "
            "so there is nothing to partition the bonding electrons by.",
            tuple(unknown),
        )
    if any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
        return _refuse(
            "This structure contains query or R-group atoms, which have no element "
            "and therefore no electronegativity."
        )

    structural = _structural_refusal(mol, table)
    if structural is not None:
        return structural

    states = {atom.GetIdx(): _state_of(atom, table) for atom in mol.GetAtoms()}

    mixed = _mixed_valence(mol, states, table)
    if mixed is not None:
        return mixed

    return OxidationStates(states=states)


def _state_of(atom: Any, table: dict[str, dict[str, Any]]) -> int:
    """Formal charge, plus one signed contribution per bonding partner.

    Homonuclear bonds contribute nothing -- their electrons are split
    evenly, which is what makes the C-C backbone of an alkane invisible
    here and the O-O bond of a peroxide the reason its oxygens are -1
    rather than -2.
    """
    symbol = atom.GetSymbol()
    own = table[symbol]["pauling"]
    state = float(atom.GetFormalCharge())

    hydrogens = atom.GetTotalNumHs()
    if hydrogens and symbol != "H":
        state += -hydrogens if own > table["H"]["pauling"] else hydrogens

    for bond in atom.GetBonds():
        other = bond.GetOtherAtom(atom)
        other_symbol = other.GetSymbol()
        if other_symbol == symbol:
            continue
        order = bond.GetBondTypeAsDouble()
        state += -order if own > table[other_symbol]["pauling"] else order

    return int(round(state))


def _structural_refusal(mol: Any, table: dict[str, dict[str, Any]]) -> OxidationStates | None:
    """The three bonding situations the partition rule cannot describe."""

    # 3c-2e bridges. A hydrogen bonded to two heavy atoms is not sharing a
    # pair with either of them, and the rule hands it a full pair from
    # both: diborane's bridging hydrogens come out at -2 and its borons at
    # +4, against the real +3.
    bridging = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 1 and atom.GetDegree() > 1
    ]
    if bridging:
        return _refuse(
            "A hydrogen here bridges two atoms (a three-centre two-electron bond, as in "
            "the boranes). Electron-deficient bonding cannot be described by giving each "
            "bond's pair to one atom.",
            tuple(bridging),
        )

    # Metal clusters, but not dimers. Calomel's Hg-Hg gives +1 on each
    # mercury, which is right, so a rule refusing every metal-metal bond
    # would throw away a correct answer. A metal bonded to TWO other metals
    # is a cluster, where the framework's electrons are delocalised.
    cluster = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if _is_metal(atom, table)
        and sum(1 for n in atom.GetNeighbors() if _is_metal(n, table)) >= 2
    ]
    if cluster:
        return _refuse(
            "This is a metal cluster: at least one metal atom is bonded to two others. "
            "Cluster bonding is delocalised over the metal framework, so there is no "
            "per-atom partition to make.",
            tuple(cluster),
        )

    # Transition-metal-carbon bonds. THIS is the boundary the measurement
    # drew. Cr(CO)6 comes out at Cr(+6) and Fe(CO)5 at Fe(+5), both of
    # which are zero-valent complexes -- the rule counts the M-C electrons
    # as carbon's and never sees the back-donation going the other way.
    # Main-group organometallics are not affected: CH3Li gives Li(+1) and
    # CH3MgBr gives Mg(+2), both correct, so the rule is kept for them.
    organometallic = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if table.get(atom.GetSymbol(), {}).get("category") in _BACKBONDING_CATEGORIES
        and any(n.GetAtomicNum() == 6 for n in atom.GetNeighbors())
    ]
    if organometallic:
        symbols = sorted({mol.GetAtomWithIdx(i).GetSymbol() for i in organometallic})
        return _refuse(
            f"{', '.join(symbols)} is bonded directly to carbon. In transition-metal "
            "organometallics the metal donates electrons back to the ligand, which this "
            "rule cannot see -- it gives Cr(CO)6 a chromium of +6, where the answer is 0.",
            tuple(organometallic),
        )

    return None


def _mixed_valence(
    mol: Any, states: dict[int, int], table: dict[str, dict[str, Any]]
) -> OxidationStates | None:
    """Magnetite, and everything shaped like it.

    Scoped to METALS within one connected fragment. Carbon routinely takes
    several different states in one molecule -- ethanol's two carbons are
    -3 and -1 -- and that is ordinary rather than suspicious, so applying
    this to every element would refuse most of organic chemistry.

    Refusing whenever the states differ is deliberately conservative. A
    genuinely mixed-valence compound that the rule happens to get right is
    refused too, because nothing here can tell that case from magnetite,
    and "we cannot tell" is the honest output.
    """
    from rdkit import Chem

    for fragment in Chem.GetMolFrags(mol):
        by_element: dict[str, set[int]] = {}
        indices: dict[str, list[int]] = {}
        for index in fragment:
            atom = mol.GetAtomWithIdx(index)
            if not _is_metal(atom, table):
                continue
            by_element.setdefault(atom.GetSymbol(), set()).add(states[index])
            indices.setdefault(atom.GetSymbol(), []).append(index)

        for symbol, found in by_element.items():
            if len(found) > 1:
                spread = ", ".join(f"{value:+d}" for value in sorted(found))
                return _refuse(
                    f"The {symbol} atoms here come out at different oxidation states "
                    f"({spread}), which means this is a mixed-valence framework. The "
                    "partition rule cannot resolve those -- on magnetite it reports "
                    "+3, +4, +3 where the answer is +2, +3, +3, and which iron gets "
                    "the wrong number depends on how the structure was drawn.",
                    tuple(indices[symbol]),
                )
    return None


def _is_metal(atom: Any, table: dict[str, dict[str, Any]]) -> bool:
    return table.get(atom.GetSymbol(), {}).get("category") in _METAL_CATEGORIES


def format_state(state: int) -> str:
    """The conventional written form: a sign always, and 0 rather than +0."""
    if state == 0:
        return "0"
    return f"{state:+d}"


def compute_oxidation_states(
    mol: Any,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> "PerAtomDataset":
    """The registered per-atom calculator.

    Returns a `PerAtomDataset` so it renders through the path
    `ring_systems` and the charge calculators already use -- the Calculator
    Inspector draws the states as atom labels with no new rendering code.

    A REFUSAL IS NOT A FAILURE. It comes back as an empty dataset carrying
    its reason, not as `CacheState.FAILED`, for the same reason an acyclic
    molecule's ring-system dataset is empty rather than failed: "this rule
    cannot describe magnetite" is a fact about the rule, and a permanent
    red error row would misfile it as something broken.

    Marked `scale="categorical"` because an oxidation state is not a
    magnitude. Iron(+3) is not "one more" of anything than iron(+2), and a
    continuous colour ramp across them would imply an ordering the
    formalism does not carry -- the same call `ring_systems` made.
    """
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import PerAtomDataset

    result = assign(mol)
    provenance_parameters: dict[str, Any] = {
        "scale": "categorical",
        "decimal_places": 0,
        "source": "Pauling electronegativities; see chem/data/electronegativity.json",
        "caveat": (
            "An oxidation state is a bookkeeping formalism, not a measurement, and it "
            "describes the structure as drawn."
        ),
    }

    if result.refused:
        provenance_parameters["refusal"] = result.reason
        provenance_parameters["summary"] = f"Not assigned. {result.reason}"
        return PerAtomDataset(
            property_id="oxidation_states",
            name="Oxidation States",
            units="",
            method=METHOD,
            molecule_uuid=molecule_uuid,
            values={},
            provenance=Provenance(created_by="core", method=METHOD, parameters=provenance_parameters),
        )

    # Explicit hydrogens are dropped by default. They are almost all -1,
    # they outnumber the heavy atoms, and a label on every one buries the
    # single number anybody opened this for. The states themselves are
    # unaffected -- the hydrogens still contributed to their neighbours.
    show_hydrogens = bool((parameters or {}).get("show_hydrogens", False))
    shown = {
        index: state
        for index, state in result.states.items()
        if show_hydrogens or mol.GetAtomWithIdx(index).GetAtomicNum() != 1
    }
    provenance_parameters["show_hydrogens"] = show_hydrogens
    provenance_parameters["atom_notes"] = {
        index: format_state(state) for index, state in shown.items()
    }
    provenance_parameters["summary"] = _summary(mol, result)
    return PerAtomDataset(
        property_id="oxidation_states",
        name="Oxidation States",
        units="",
        method=METHOD,
        molecule_uuid=molecule_uuid,
        values={index: float(state) for index, state in shown.items()},
        provenance=Provenance(created_by="core", method=METHOD, parameters=provenance_parameters),
    )


def _summary(mol: Any, result: OxidationStates) -> str:
    """One line naming the states actually present, per element.

    Per element rather than per atom because that is how the answer is
    usually wanted -- "Fe +3, O -2" is the useful sentence about iron(III)
    oxide, and listing five atoms is not.
    """
    by_element: dict[str, set[int]] = {}
    for index, state in result.states.items():
        by_element.setdefault(mol.GetAtomWithIdx(index).GetSymbol(), set()).add(state)
    parts = [
        f"{symbol} {', '.join(format_state(v) for v in sorted(states))}"
        for symbol, states in sorted(by_element.items())
    ]
    return "; ".join(parts)
