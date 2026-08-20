"""Gutmann donor and acceptor numbers, read from the classical tables.

WHY THIS WAS DEFERRED, AND WHAT CHANGED. CLAUDE.md records the
assessment: the accessible source was
[source:gutmann_frontiers2022], which tabulates ionic liquids and deep
eutectic solvents rather than the classical molecular scale, and which
"reports its own acceptor-number model failing outright". That paper was
correctly rejected. What was missing was the original tables, and they
are here now -- Gutmann's own 1976 review ([source:gutmann1976]).

**TWO SCALES, AND CONFLATING THEM IS THE FAILURE TO AVOID.** They are
not two readings of one quantity:

    DN  donor number, kcal/mol, DILUTE in 1,2-dichloroethane
        DN = -dH for the donor's adduct with SbCl5
    AN  acceptor number, DIMENSIONLESS, from the 31P shift of Et3P=O
        on a two-point scale: hexane = 0, SbCl5/DCE = 100

A solvent can be high in both (water: DN 18.0, AN 54.8) or high in one
and nearly zero in the other (HMPA: DN 38.8, AN 10.6). Asking for "the
Gutmann number" of a solvent is not a well-formed question, so there is
no function here that answers it.

**AND BULK DONICITY IS A THIRD THING.** The paper's footnote a marks
values measured "in the associated liquid" rather than dilute, and six
amines plus hydrazine are reported ONLY that way. Water is reported both
ways and is the row that shows why they must not be merged: 18.0 dilute
against 33.0 bulk, a 15 kcal/mol gap. `donor_number` returns the dilute
value and `bulk_donicity` the other; neither silently substitutes for the
other.

RELATED TO THE SHIPPED DRAGO E/C TABLE, AND NOT A SECOND READING OF IT.
DN is defined as -dH against SbCl5, which `chem/lewis.py`'s parameters
can also predict, so the two scales are connected in principle. They are
NOT two implementations of one number -- different parameterisations,
different reference acids, different experimental bases -- so nothing
here is validated against that table, and a cross-scale comparison would
let a real transcription error hide behind a legitimate difference. The
acceptance oracle is the published values themselves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: DECLARED USER-FACING. Reached INDIRECTLY from two places: the
#: solubility report names the chosen solvent's DN and AN, and the Lewis
#: site report names them when the drawn structure IS one of these liquids.
USER_FACING_PROVIDER = (
    "Gutmann DN/AN, on the Solubility report and on Lewis Sites"
)

_DATA = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class SolventDonicity:
    """What the 1976 tables record for one solvent.

    Every field is optional because the tables are not rectangular: most
    solvents carry a DN and no AN, some the reverse, seven carry only a
    bulk donicity, and 1,2-dichloroethane deliberately carries no DN at
    all because it is the medium the measurement is made in.
    """

    name: str
    donor_number: float | None = None
    bulk_donicity: float | None = None
    acceptor_number: float | None = None
    #: The 31P shift of Et3P=O the acceptor number is derived from, ppm.
    p31_shift: float | None = None
    #: True where the paper writes "~" rather than a value.
    approximate: bool = False
    #: The paper's own remark, where it has one.
    note: str = ""


@lru_cache(maxsize=1)
def _payload() -> dict:
    return json.loads((_DATA / "gutmann_solvents.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _table() -> dict[str, SolventDonicity]:
    payload = _payload()
    donors = payload["donor_numbers"]
    acceptors = payload["acceptor_numbers"]
    out: dict[str, SolventDonicity] = {}
    for name in sorted(set(donors) | set(acceptors)):
        donor = donors.get(name, {})
        acceptor = acceptors.get(name, {})
        out[name] = SolventDonicity(
            name=name,
            donor_number=donor.get("dn"),
            bulk_donicity=donor.get("bulk_dn"),
            acceptor_number=acceptor.get("an"),
            p31_shift=acceptor.get("p31_shift"),
            approximate=bool(donor.get("approximate")),
            note=donor.get("note") or acceptor.get("note") or "",
        )
    return out


def solvent_names() -> list[str]:
    """Every solvent either table records, in the paper's own naming."""
    return sorted(_table())


def donicity(solvent_name: str) -> SolventDonicity | None:
    """Both scales for one solvent, or None if it is in neither table.

    Returns the WHOLE record rather than a number, deliberately: a caller
    that wanted "the Gutmann number" has asked a question with two
    answers, and handing back one of them would pick for them.
    """
    return _table().get(solvent_name.strip().lower())


def scale_anchors() -> dict[str, float]:
    """The two points that define the acceptor scale.

    Exposed because AN is meaningless without them -- it is not a
    measured quantity in its own units but a position between hexane and
    SbCl5 -- and because a transcription slip in either would silently
    rescale the whole column.
    """
    acceptors = _payload()["acceptor_numbers"]
    return {
        "hexane": acceptors["hexane"]["an"],
        "antimony pentachloride in dichloroethane": acceptors[
            "antimony pentachloride in dichloroethane"
        ]["an"],
    }


# ---------------------------------------------------------------------------
# Reaching the table from OTHER solvent vocabularies
# ---------------------------------------------------------------------------
#
# The Abraham solvent table (`chem/abraham.py`) and this one were
# transcribed from different papers a generation apart, so 21 of the 92
# solvents the solubility calculator offers reach these tables by exact
# name and the rest do not -- some because Gutmann never measured them,
# and some only because the two papers spell the same liquid differently.
#
# **EVERY BRIDGE IS DECLARED, NEVER INFERRED.** A fuzzy match is how a
# value silently changes owner: `difflib` pairs "dichloroethylene
# carbonate" with "propylene carbonate" and "isopropylamine" with
# "isopropyl myristate", both confidently and both wrong. Each entry below
# is one deliberate identification of one liquid, and
# `tests/test_gutmann_bridge.py` asserts every target exists.

#: `{name in another vocabulary: name in Gutmann's tables}`.
#:
#: Only genuine spelling differences for the SAME liquid. A solvent absent
#: from Gutmann's tables must stay absent -- there is nothing to bridge to,
#: and the calculator says so rather than guessing.
_NAME_BRIDGE: dict[str, str] = {
    "1,4-dioxane": "dioxan",
    "2-propanol": "isopropanol",
    "dimethyl sulfoxide": "dimethyl sulphoxide",
    "dimethylacetamide": "n,n-dimethylacetamide",
    "glyme": "dimethoxyethane",
    "n,n-dimethylformamide": "dimethylformamide",
    "n-methylpyrrolidinone": "n-methyl-2-pyrrolidinone",
    "sulfolane": "sulpholane",
    "1,2-dimethoxyethane": "dimethoxyethane",
    # The Abraham solute table names these systematically, which is how a
    # structure lookup reaches them at all.
    "propanone": "acetone",
    "trichloromethane": "chloroform",
    "tetrachloromethane": "carbon tetrachloride",
    "1,2-ethanediamine": "ethylenediamine",
}


def donicity_for(name: str) -> SolventDonicity | None:
    """Both scales for a solvent named in ANY of this app's vocabularies.

    Tries the name as given, then the declared bridge. Returns None rather
    than a nearest match: Gutmann simply did not measure every liquid, and
    "no donor number is published for this solvent" is the honest answer.
    """
    key = name.strip().lower()
    direct = donicity(key)
    if direct is not None:
        return direct
    bridged = _NAME_BRIDGE.get(key)
    return donicity(bridged) if bridged else None


def name_bridge() -> dict[str, str]:
    """The declared spelling bridges, for the guard that checks them."""
    return dict(_NAME_BRIDGE)


# ---------------------------------------------------------------------------
# Reaching the table from a DRAWN STRUCTURE
# ---------------------------------------------------------------------------
#
# `domain/lewis.py` says its shape "has room for what is coming -- donor
# and acceptor numbers... without any consumer changing". Filling that
# needs a name -> structure map for the solvents in these tables, and the
# obvious way to build one is to write sixty SMILES by hand.
#
# **NOT ONE SMILES IS TYPED HERE, AND THAT IS THE DESIGN.** Sixty
# hand-written structures for liquids like selenium oxychloride and
# phenylphosphonic difluoride would be sixty chances to ship a plausible
# wrong molecule, which is the "fields nobody can check" failure this
# project has already paid for once. The structures come instead from
# `abraham_solutes.json`, which is a SHIPPED, SOURCED dataset keyed by
# InChIKey and carrying each solute's name -- so the join is name to name,
# and every structure in it was somebody else's transcription with its own
# provenance.
#
# The cost is coverage: a Gutmann solvent the Abraham solute table does
# not carry simply has no structure here, and a drawn molecule that is one
# of those gets no donicity rather than a guessed one.


@lru_cache(maxsize=1)
def _by_inchikey() -> dict[str, str]:
    """`{InChIKey: Gutmann solvent name}`, DERIVED at runtime.

    Derived rather than generated into a file on purpose: both inputs are
    shipped and sourced, so a join computed here cannot fall behind either
    of them -- which is the way `inapplicable_calculators` rotted.

    **EVERY DISPLAYED VALUE TRACES TO EXACTLY ONE TABLE ROW.** The join is
    asserted injective in both directions by
    `tests/test_gutmann_bridge.py`: two names collapsing onto one key
    would mean one liquid wearing two rows, which is exactly the defect
    that turned up in the shipped table itself (dioxan/dioxane and
    glyme/dimethoxyethane each carried half a solvent's data until they
    were merged).
    """
    import json
    from pathlib import Path as _Path

    solutes = json.loads(
        (_Path(__file__).resolve().parent / "data" / "abraham_solutes.json").read_text(
            encoding="utf-8"
        )
    )["solutes"]
    by_name: dict[str, str] = {}
    for key, row in solutes.items():
        by_name.setdefault(str(row["name"]).strip().lower(), key)

    # A solvent may have SEVERAL declared synonyms -- dimethoxyethane is
    # "glyme" in one vocabulary and "1,2-dimethoxyethane" in another --
    # so every one is tried, in sorted order so the walk is deterministic
    # rather than dict-order-dependent. Two synonyms resolving to
    # DIFFERENT structures would be a real conflict; the first key wins
    # here and `test_two_synonyms_never_name_two_structures` is what makes
    # that visible instead of silent.
    reverse: dict[str, list[str]] = {}
    for other, gutmann in _NAME_BRIDGE.items():
        reverse.setdefault(gutmann, []).append(other)

    out: dict[str, str] = {}
    for name in _table():
        for candidate in [name] + sorted(reverse.get(name, ())):
            key = by_name.get(candidate)
            if key is not None:
                out.setdefault(key, name)
                break
    return out


def synonym_keys(name: str) -> set[str]:
    """Every InChIKey the declared synonyms of `name` resolve to.

    Exposed for the guard: one liquid must not reach two structures.
    """
    import json
    from pathlib import Path as _Path

    solutes = json.loads(
        (_Path(__file__).resolve().parent / "data" / "abraham_solutes.json").read_text(
            encoding="utf-8"
        )
    )["solutes"]
    by_name: dict[str, str] = {}
    for key, row in solutes.items():
        by_name.setdefault(str(row["name"]).strip().lower(), key)

    candidates = [name] + [o for o, g in _NAME_BRIDGE.items() if g == name]
    return {by_name[c] for c in candidates if c in by_name}


def donicity_for_structure(mol) -> SolventDonicity | None:
    """Both scales for a DRAWN molecule, or None if it is not a solvent here.

    Matched by InChIKey, so a tautomer or a differently-drawn but
    identical structure still resolves and a near-miss does not. Returns
    None for anything the tables do not carry -- Gutmann measured 68
    liquids, not every molecule.
    """
    if mol is None:
        return None
    try:
        from rdkit import Chem as _Chem

        key = _Chem.MolToInchiKey(mol)
    except Exception:  # pragma: no cover - a structure InChI cannot read
        return None
    name = _by_inchikey().get(key)
    return _table().get(name) if name else None


def structural_coverage() -> dict[str, str]:
    """`{InChIKey: solvent name}` for every solvent a structure can reach."""
    return dict(_by_inchikey())
