"""Which atom of one structure version is which atom of another.

Round 3, Track 2 (`benchmarks/charges/consumers/preregistration.md`). A
GEOMETRY per-atom dataset is keyed by the CONFORMER's atom indices, and the
Atom Inspector reads by the DRAWING's (`atom_report.collect_per_atom_data`).
They agree only while the conformer's atoms come in the drawing's order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdkit import Chem

#: Refusal codes a projection can return. Each is shown to the user with its
#: reason; a projection never falls back to reading the index as-is.
REFUSE_CONFORMER_GONE = "REFUSE_CONFORMER_GONE"
#: No graph correspondence exists between the two structures (not the same molecule).
REFUSE_NO_CORRESPONDENCE = "REFUSE_NO_CORRESPONDENCE"
#: Several correspondences exist, and the dataset differs between them at display precision.
REFUSE_AMBIGUOUS_IDENTITY = "REFUSE_AMBIGUOUS_IDENTITY"
#: The isomorphism enumeration passed SEARCH_LIMIT before it finished.
REFUSE_IDENTITY_SEARCH_LIMIT = "REFUSE_IDENTITY_SEARCH_LIMIT"

#: How the correspondence was established, recorded on every projection.
POLICY_SAME_SPACE = "same_space"
#: The conformer carries the drawing atom ids stored when it was made, checked against its fingerprint.
POLICY_RECORDED = "recorded_at_creation"
#: No record, and the graph search found exactly one correspondence.
POLICY_GRAPH_UNIQUE = "conformer_of_drawing:unique_isomorphism"
#: Several correspondences, but this dataset is the same under all of them; a property of the projection only.
POLICY_GRAPH_VALUE_INVARIANT = "conformer_of_drawing:value_invariant"
#: Bumped whenever the rules above change, so a stored projection says which rules made it.
MAPPING_VERSION = 1
#: Isomorphisms enumerated before refusing; symmetric molecules reach thousands, a runaway never ends.
SEARCH_LIMIT = 10_000
#: Two projections agree when every shown value is equal to this.
VALUE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class DrawingProjection:
    """A per-atom dataset's values placed on DRAWING atoms, or why they cannot be.

    `values` is None exactly when `refusal` is set. `policy` says how the
    correspondence was made; `detail` is the sentence a reader is shown.
    """

    values: dict[int, float] | None
    policy: str = ""
    refusal: str = ""
    detail: str = ""
    mapping_version: int = MAPPING_VERSION
    #: conformer atom index -> drawing atom index, for the atoms that have one.
    mapping: dict[int, int] = field(default_factory=dict)


#: The RDKit atom property a first-party conformer route stamps on the drawing's
#: atoms before generating geometry. RDKit carries atom properties through
#: `AddHs`, embedding and force-field optimisation (tested), and a hydrogen
#: added on the way has none -- which is exactly "no drawing atom".
DRAWING_INDEX_PROP = "openchem_drawing_index"


def tag_drawing_atoms(mol: Chem.Mol) -> Chem.Mol:
    """Stamp each atom with its drawing (molfile) position, in place, and return `mol`."""
    for atom in mol.GetAtoms():
        atom.SetIntProp(DRAWING_INDEX_PROP, atom.GetIdx())
    return mol


def recorded_drawing_ids(mol: Chem.Mol) -> list[int] | None:
    """Per atom of `mol`, the drawing index it was tagged with or -1 for an added atom.

    None when no atom carries the tag at all: a provider that rebuilt the
    molecule and lost the properties must record NOTHING rather than a map
    of -1s that would read as "these atoms are all hydrogens".
    """
    ids = [atom.GetIntProp(DRAWING_INDEX_PROP) if atom.HasProp(DRAWING_INDEX_PROP) else -1 for atom in mol.GetAtoms()]
    return ids if any(i >= 0 for i in ids) else None


def renumbered_molblock(molblock: str, order: str | list[int] = "reverse") -> str:
    """The same structure with its atoms in a different molfile order.

    A drive and test instrument: it is what the editor emits after an atom is
    erased and redrawn (same canonical SMILES, different molfile positions),
    produced without driving a drawing gesture. `order` is `"reverse"` or a
    permutation: new position k holds old atom `order[k]`.
    """
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=True)
    if mol is None:
        raise ValueError("molblock does not parse")
    n = mol.GetNumAtoms()
    permutation = list(range(n - 1, -1, -1)) if order == "reverse" else [int(i) for i in order]
    if sorted(permutation) != list(range(n)):
        raise ValueError(f"not a permutation of {n} atoms: {permutation}")
    return Chem.MolToMolBlock(Chem.RenumberAtoms(mol, permutation))


def element_order(molblock: str) -> list[str]:
    """Element symbols in molfile order, explicit hydrogens included."""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    return [] if mol is None else [atom.GetSymbol() for atom in mol.GetAtoms()]


def dataset_conformer_id(dataset) -> str | None:
    """The conformer a per-atom dataset is keyed by, or None when it is keyed by the drawing.

    DERIVED FROM WHAT EVERY RESULT ALREADY RECORDS: `geometry_provenance` stamps
    `input_source` and `input_conformer_id` on anything computed on a stored
    conformer, so a saved project's older results project correctly too.
    """
    provenance = getattr(dataset, "provenance", None)
    parameters = getattr(provenance, "parameters", None) or {}
    if parameters.get("input_source") in (None, "drawing"):
        return None
    conformer_id = parameters.get("input_conformer_id")
    return str(conformer_id) if conformer_id else None


def _atom_signature(atom: Chem.Atom) -> tuple:
    return (atom.GetAtomicNum(), atom.GetIsotope(), atom.GetFormalCharge(), atom.GetTotalNumHs(includeNeighbors=True))


def _cip(mol: Chem.Mol) -> dict[int, str]:
    return {atom.GetIdx(): atom.GetProp("_CIPCode") for atom in mol.GetAtoms() if atom.HasProp("_CIPCode")}


def graph_correspondences(drawing: Chem.Mol, conformer: Chem.Mol, limit: int = SEARCH_LIMIT) -> list[dict[int, int]] | None:
    """Every drawing->conformer atom correspondence that preserves element, isotope,
    formal charge, hydrogen count, bonds and CIP stereo labels. None past `limit`.

    STRUCTURAL CORRESPONDENCE only: it knows nothing about any dataset, and
    several answers mean the structures alone cannot say which is which.
    """
    heavy = lambda m: sum(1 for a in m.GetAtoms() if a.GetAtomicNum() > 1)  # noqa: E731
    if heavy(drawing) != heavy(conformer):
        return []
    matches = conformer.GetSubstructMatches(drawing, uniquify=False, useChirality=True, maxMatches=limit + 1)
    if len(matches) > limit:
        return None
    drawn_cip, conformer_cip = _cip(drawing), _cip(conformer)
    out = []
    for match in matches:
        pairs = dict(enumerate(match))
        if any(_atom_signature(drawing.GetAtomWithIdx(d)) != _atom_signature(conformer.GetAtomWithIdx(c)) for d, c in pairs.items()):
            continue
        # Only where the DRAWING states a configuration. A conformer always
        # has one (it is 3D), and an unwedged drawing is a claim about neither
        # hand -- refusing it would refuse every ordinary drawing after a reorder.
        if any(drawn_cip[d] != conformer_cip.get(c) for d, c in pairs.items() if d in drawn_cip):
            continue
        out.append(pairs)
    return out


def _project(values: dict[int, float], drawing_to_conformer: dict[int, int]) -> dict[int, float]:
    return {d: values[c] for d, c in drawing_to_conformer.items() if c in values}


def project_to_drawing(engine, model, dataset, display=None) -> DrawingProjection:
    """Place `dataset`'s values on the drawing's atoms, at DISPLAY time.

    At display time and not when the result arrives, because the drawing can
    be reordered afterwards while the conformer -- and so the result's
    freshness -- stays put. The order of preference:

    1. a dataset keyed by the drawing already: as it is;
    2. the map recorded when the conformer was made, ONLY while the drawing
       is byte-identical to that one, and only if it checks out atom by atom;
    3. the structures themselves: one graph correspondence is the answer;
       several are accepted only if every one puts the same value on every
       drawn atom (value-observational uniqueness, a property of THIS dataset,
       never stored as the structure map); otherwise refused.

    `display` is how the consumer prints a value. "The same value" means the
    same PRINTED value, as preregistration.md E1 fixed before this was
    written: two numbers that print alike cannot be put on the wrong atom in
    any way a reader could see. Without it, equality is within
    `VALUE_TOLERANCE`, which is the stricter reading.
    """
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import DRAWING

    values = dict(getattr(dataset, "values", {}) or {})
    conformer_id = dataset_conformer_id(dataset)
    if conformer_id is None:
        return DrawingProjection(values, POLICY_SAME_SPACE)
    conformer = next((c for c in model.conformers if c.conformer_id == conformer_id), None)
    if conformer is None:
        return DrawingProjection(None, refusal=REFUSE_CONFORMER_GONE,
                                 detail="The conformer these values were computed on is no longer stored.")
    drawing = engine.mol_from_model(model)
    conformer_mol = engine.mol_from_molblock(conformer.molblock)
    ids = conformer.drawing_atom_ids
    if ids is not None and conformer.drawing_fingerprint == input_fingerprint(engine, model, DRAWING) \
            and len(ids) == conformer_mol.GetNumAtoms():
        mapping = {c: d for c, d in enumerate(ids) if d >= 0}
        consistent = all(d < drawing.GetNumAtoms() and drawing.GetAtomWithIdx(d).GetAtomicNum() == conformer_mol.GetAtomWithIdx(c).GetAtomicNum()
                         for c, d in mapping.items())
        if consistent and len(set(mapping.values())) == len(mapping) == drawing.GetNumAtoms():
            return DrawingProjection(_project(values, {d: c for c, d in mapping.items()}), POLICY_RECORDED, mapping=mapping)
    found = graph_correspondences(drawing, conformer_mol)
    if found is None:
        return DrawingProjection(None, refusal=REFUSE_IDENTITY_SEARCH_LIMIT,
                                 detail=f"More than {SEARCH_LIMIT} ways to match the drawing to the conformer; none is shown.")
    if not found:
        return DrawingProjection(None, refusal=REFUSE_NO_CORRESPONDENCE,
                                 detail="The drawing no longer matches the conformer these values were computed on.")
    found.sort(key=lambda m: [m[d] for d in sorted(m)])
    first = _project(values, found[0])
    if len(found) == 1:
        return DrawingProjection(first, POLICY_GRAPH_UNIQUE, mapping={c: d for d, c in found[0].items()})
    def same(a: float, b: float) -> bool:
        return display(a) == display(b) if display is not None else abs(a - b) <= VALUE_TOLERANCE

    for other in found[1:]:
        projected = _project(values, other)
        if projected.keys() != first.keys() or not all(same(projected[k], first[k]) for k in first):
            return DrawingProjection(
                None, refusal=REFUSE_AMBIGUOUS_IDENTITY,
                detail=("Symmetry-equivalent atoms of the drawing carry different values in this conformer, and the "
                        "drawing was changed since the conformer was made, so which is which cannot be known."))
    return DrawingProjection(first, POLICY_GRAPH_VALUE_INVARIANT, mapping={c: d for d, c in found[0].items()})


def depiction_values(engine, model, dataset, depiction_molblock: str, display=None) -> tuple[dict[int, float] | None, DrawingProjection]:
    """`dataset`'s values keyed by atoms of a 2D DEPICTION, and the projection behind them.

    The depiction is the drawing, possibly with its implicit hydrogens made
    into atoms after the drawn ones (`ChemistryEngine.molblock_with_explicit_hydrogens`).
    Drawn atoms take the projection's values. A depicted hydrogen takes a
    value only when every hydrogen on the same parent in the conformer PRINTS
    ALIKE: hydrogens on one parent are interchangeable in the drawing, so
    which conformer hydrogen is which cannot be known, and a label is shown
    only when it could not be wrong. Otherwise that hydrogen is left unlabelled.
    """
    projection = project_to_drawing(engine, model, dataset, display=display)
    if projection.values is None:
        return None, projection
    if projection.policy == POLICY_SAME_SPACE or not depiction_molblock:
        return dict(projection.values), projection
    depiction = engine.mol_from_molblock(depiction_molblock)
    drawn_count = engine.mol_from_model(model).GetNumAtoms()
    out = {i: v for i, v in projection.values.items() if i < drawn_count}
    conformer = next(c for c in model.conformers if c.conformer_id == dataset_conformer_id(dataset))
    conformer_mol = engine.mol_from_molblock(conformer.molblock)
    drawing_of = projection.mapping  # conformer index -> drawing index
    same = (lambda a, b: display(a) == display(b)) if display is not None else (lambda a, b: abs(a - b) <= VALUE_TOLERANCE)
    hydrogens_on: dict[int, list[float]] = {}
    for atom in conformer_mol.GetAtoms():
        if atom.GetAtomicNum() == 1 and atom.GetIdx() in dataset.values and atom.GetDegree() == 1:
            parent = atom.GetNeighbors()[0].GetIdx()
            if parent in drawing_of:
                hydrogens_on.setdefault(drawing_of[parent], []).append(dataset.values[atom.GetIdx()])
    for atom in depiction.GetAtoms():
        if atom.GetIdx() < drawn_count or atom.GetAtomicNum() != 1 or atom.GetDegree() != 1:
            continue
        candidates = hydrogens_on.get(atom.GetNeighbors()[0].GetIdx(), [])
        if candidates and all(same(candidates[0], v) for v in candidates[1:]):
            out[atom.GetIdx()] = candidates[0]
    return out, projection
