"""The X-H bond dissociation enthalpy of a neutral molecule, from ORCA: the chemistry of the protocol, with no engine, no Qt and no file read.

This is the protocol that `benchmarks/bde/` preregistered (PARTIAL, 2026-10-21: the mean signed error was 1.53 kcal/mol against a limit of 1.5, the other limits passed) and that `benchmarks/restart_v2/` then measured again on bonds it had not seen (PASS, 2026-10-23, 27 bonds against the Active Thermochemical Tables).
Nothing here may drift from that protocol without a new benchmark: the keywords, the structure generation, the acceptance rule and the arithmetic are the benchmark's, and `tests/test_bond_dissociation_calculation.py` checks them against the benchmarks' own records.

THE PROTOCOL. `DH298(R-H) = H(R.) + H(H.) - H(RH)` at 298.15 K and 1 atm, each H the total enthalpy of an M062X/def2-TZVPD `Opt Freq` job of the closed-shell parent and of the doublet radical (unrestricted Kohn-Sham), and of the hydrogen atom (a single point of the same method, plus (5/2) kT).
* Structures: the parent is embedded with ETKDG (seed 7, 30 conformers), MMFF94-relaxed, deduplicated by all-atom RMSD 0.5 Angstrom, and the lowest three within 5 kcal/mol are optimized. **A radical's starts are the parent's kept conformers with one hydrogen of the atom deleted**, so the optimizer starts from the parent's shape and never from a fresh embedding of a radical.
* Acceptance: a structure with a vibrational frequency below -20 cm-1 is re-run once with `Calc_Hess` and dropped if it still has one; a radical must still be the radical of its bond (the parent's heavy-atom bonds and hydrogen counts, minus one hydrogen on the named atom): one that rearranged is a failed structure, not a low one.
* The lowest-enthalpy structure of each species, independently; no Boltzmann averaging. No symmetry number enters: an enthalpy has none.

WHAT IT CANNOT SAY (the benchmarks' own limits): 49 deciding bonds of neutral closed-shell molecules of at most nine heavy atoms of H, C, N, O and S. The calculation is measured to run LOW, about 1.4 kcal/mol on average, in every class (`BENCHMARK`), and the mean error of an O-H bond next to another oxygen or a nitrogen (a peroxide, a hydroxylamine, an oxime) is 3.3 kcal/mol, up to 4.6; those classes were named after the results were seen.
A bond whose radical keeps an imaginary mode after the one re-run has no value: the benchmark lost the S-H bond of methanethiol that way (the CH3S radical optimized to a saddle point at -1306 cm-1), and a second protocol that displaces the geometry along the imaginary mode (`benchmarks/restart_v2/`) did not repair thiyl radicals (0 of 2) and was therefore not adopted.
"""
from __future__ import annotations

#: Stage 1 of the calculator: the chemistry, tested against the benchmarks, with no engine behind it yet; stage 2 (the service) imports it and this line goes.
REACHED_BY = "tooling: stage 1 of the bond-dissociation calculator, imported by its tests until the service stage wires it"


import re
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem

from openchem.chem import proton_affinity as pa
from openchem.chem.proton_affinity import OutOfScope
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue

#: The preregistered job: one level for optimization and frequencies (the proton-affinity protocol's, so the two cannot drift apart).
HEADER = pa.HEADER
#: The hydrogen atom: a single point of the same method, basis and grid.
ATOM_HEADER = "! M062X def2-TZVPD TightSCF DefGrid3"
#: The model chemistry as a result states it.
METHOD_LABEL = pa.METHOD_LABEL
#: A vibrational frequency below this (cm-1) makes a structure not accepted.
IMAGINARY_CM = pa.IMAGINARY_CM
#: ORCA's memory per core in MB (the benchmark's setting).
MAXCORE_MB = pa.MAXCORE_MB
#: The temperature of the benchmarks and of every reference value in them.
T_STANDARD = pa.T_STANDARD
#: kcal/mol per Hartree.
HARTREE_TO_KCAL = pa.HARTREE_TO_KCAL
#: kJ per kcal.
KCAL_TO_KJ = pa.KCAL_TO_KJ
#: <S**2> of a clean doublet.
S2_DOUBLET = 0.75
#: How far above 0.75 a radical's <S**2> is flagged as spin-contaminated (reported, never a rule).
S2_FLAG_EXCESS = 0.05
#: The id of the hydrogen atom's structure.
ATOM_ID = "atom|H"

#: What the benchmarks measured: the elements and the size of the molecules.
SUPPORTED_ELEMENTS = frozenset({1, 6, 7, 8, 16})
#: The largest parent the benchmarks measured, in heavy atoms (benzoic acid, a bond whose reference is too loose to decide; the deciding bonds go up to seven, toluene).
MAX_HEAVY_ATOMS = 9
#: The elements whose X-H bond this calculates.
BOND_ELEMENTS = {6: "C", 7: "N", 8: "O", 16: "S"}
#: The most bonds one run computes: each costs up to three radical optimizations.
MAX_BONDS = 6


# --- the arithmetic ---------------------------------------------------------------------------------------------------------


def hydrogen_atom_enthalpy(electronic_energy: float, temperature: float = T_STANDARD) -> float:
    """H(H.) in Hartree: the atom's electronic energy plus (5/2) kT (translation and pV; an atom has no rotation or vibration)."""
    return electronic_energy + 2.5 * pa.K_B * temperature / pa.HARTREE_J


def bond_dissociation_enthalpy(h_parent: float, h_radical: float, h_hydrogen: float) -> float:
    """DH298(R-H) = H(R.) + H(H.) - H(RH), in Hartree, from the three total enthalpies."""
    return h_radical + h_hydrogen - h_parent


def spin_contaminated(s2: float) -> bool:
    """Whether an unrestricted doublet's <S**2> is more than `S2_FLAG_EXCESS` above the clean 0.75 (reported, never a rule)."""
    return s2 - S2_DOUBLET > S2_FLAG_EXCESS


def radical_start(symbols: list[str], coordinates: np.ndarray, heavy_atom: int, neighbors: list[int]) -> tuple[list[str], np.ndarray]:
    """A radical's starting geometry: the parent's atoms with ONE hydrogen of `heavy_atom` deleted (the lowest-numbered hydrogen among `neighbors`, the atom's bonded atoms).

    Every remaining atom keeps its place, so the optimizer starts from the parent's conformer. Raises ValueError if the atom carries no hydrogen."""
    hydrogens = [i for i in neighbors if symbols[i] == "H"]
    if not hydrogens:
        raise ValueError(f"atom {heavy_atom} carries no hydrogen")
    drop = min(hydrogens)
    keep = [i for i in range(len(symbols)) if i != drop]
    return [symbols[i] for i in keep], np.asarray(coordinates, dtype=float)[keep]


# --- scope ------------------------------------------------------------------------------------------------------------------


def molecule_from_smiles(smiles: str) -> Chem.Mol:
    """The molecule with explicit hydrogens (which RDKit appends after the heavy atoms, so a heavy atom's index is the one the SMILES gives it), or OutOfScope with the reason the calculation does not apply."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise OutOfScope("the structure could not be read")
    return check_scope(Chem.AddHs(mol))


def check_scope(mol: Chem.Mol) -> Chem.Mol:
    """Returns `mol` if it is the kind of molecule the benchmarks measured, else raises OutOfScope saying which limit it passes.

    The kind: one neutral closed-shell molecule of at most nine heavy atoms made of H, C, N, O and S, with at least one C-H, N-H, O-H or S-H bond."""
    if len(Chem.GetMolFrags(mol)) != 1:
        raise OutOfScope("more than one component: a bond dissociation enthalpy is one molecule's")
    heavy = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() > 1)
    if heavy == 0:
        raise OutOfScope("no heavy atom: there is no X-H bond")
    if heavy > MAX_HEAVY_ATOMS:
        raise OutOfScope(f"{heavy} heavy atoms: the benchmarks measured molecules of at most {MAX_HEAVY_ATOMS}")
    odd = sorted({a.GetSymbol() for a in mol.GetAtoms() if a.GetAtomicNum() not in SUPPORTED_ELEMENTS})
    if odd:
        raise OutOfScope(f"{', '.join(odd)}: the benchmarks measured only H, C, N, O and S")
    if any(a.GetNumRadicalElectrons() for a in mol.GetAtoms()):
        raise OutOfScope("a radical: the benchmarks measured closed-shell molecules")
    if any(a.GetFormalCharge() for a in mol.GetAtoms()):
        raise OutOfScope("a charged or zwitterionic structure: the benchmarks measured neutral molecules")
    if not bond_classes(mol):
        raise OutOfScope("no C-H, N-H, O-H or S-H bond")
    return mol


# --- the bonds --------------------------------------------------------------------------------------------------------------


def bond_classes(mol: Chem.Mol) -> list[dict]:
    """The X-H bonds of a molecule (explicit hydrogens), atoms equivalent by the graph's symmetry merged into one: the heavy atom of lowest index of each class.

    Returns `{"atom", "element", "hydrogens", "label", "next_to_heteroatom", "aromatic"}`. `next_to_heteroatom` is an O-H whose oxygen is bonded to another oxygen or a nitrogen (a peroxide, a hydroxylamine, an oxime): the class the benchmarks measured to run lowest."""
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    seen: set[int] = set()
    out = []
    for atom in mol.GetAtoms():
        symbol = BOND_ELEMENTS.get(atom.GetAtomicNum())
        hydrogens = sum(1 for n in atom.GetNeighbors() if n.GetAtomicNum() == 1)
        if symbol is None or not hydrogens or ranks[atom.GetIdx()] in seen:
            continue
        seen.add(ranks[atom.GetIdx()])
        heavy_neighbors = sorted(n.GetSymbol() for n in atom.GetNeighbors() if n.GetAtomicNum() > 1)
        next_to = symbol == "O" and any(n in ("O", "N") for n in heavy_neighbors)
        out.append({
            "atom": atom.GetIdx(), "element": symbol, "hydrogens": hydrogens, "aromatic": atom.GetIsAromatic(), "next_to_heteroatom": next_to,
            "label": f"{symbol}{'H' + str(hydrogens) if hydrogens > 1 else 'H'}{' (aromatic)' if atom.GetIsAromatic() else ''}-H, bonded to {', '.join(heavy_neighbors) if heavy_neighbors else 'no other heavy atom'}",
        })
    return out


def class_key(bond: dict) -> str:
    """Which measured class a bond belongs to, for the error `BENCHMARK` states beside it."""
    if bond["next_to_heteroatom"]:
        return "O-H next to O or N"
    return f"{bond['element']}-H"


def build_structures(mol: Chem.Mol, atoms: list[int], key: str = "mol") -> list[dict]:
    """Every ORCA job of a molecule for the bonds on `atoms` (one heavy atom per bond class, from `bond_classes`): the hydrogen atom, the kept parent conformers, and one radical start per bond and conformer.

    Each structure is a dict with `id`, `role` ('atom', 'parent' or 'radical'), `charge`, `mult`, `symbols`, `coordinates` (Angstrom) and, for a radical, `atom`."""
    allowed = {b["atom"] for b in bond_classes(mol)}
    for atom in atoms:
        if atom not in allowed:
            raise ValueError(f"atom {atom} is not the representative of an X-H bond class")
    structures = [{"id": ATOM_ID, "role": "atom", "charge": 0, "mult": 2, "symbols": ["H"], "coordinates": [[0.0, 0.0, 0.0]]}]
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    conformers = pa.conformers_of(mol)
    for k, xyz in enumerate(conformers):
        structures.append({"id": f"{key}|parent|{k}", "role": "parent", "charge": 0, "mult": 1, "symbols": symbols, "coordinates": xyz.tolist()})
    for atom in atoms:
        neighbors = [n.GetIdx() for n in mol.GetAtomWithIdx(atom).GetNeighbors()]
        for k, xyz in enumerate(conformers):
            radical_symbols, radical_xyz = radical_start(symbols, xyz, atom, neighbors)
            structures.append({"id": f"{key}|radical|{atom}|{k}", "role": "radical", "atom": atom, "charge": 0, "mult": 2, "symbols": radical_symbols, "coordinates": radical_xyz.tolist()})
    return structures


# --- the ORCA job and its output --------------------------------------------------------------------------------------------


def orca_input(structure: dict, cores: int, retry: bool = False) -> str:
    """The input of one job: the preregistered keywords, the structure's own charge and multiplicity (a radical's is 2, so ORCA runs it unrestricted), and for the atom a single point. `retry` adds `Calc_Hess`."""
    if structure["role"] == "atom":
        lines = [ATOM_HEADER, f"%maxcore {MAXCORE_MB}"]
    else:
        lines = [HEADER, f"%pal nprocs {cores} end", f"%maxcore {MAXCORE_MB}"]
        if retry:
            lines += ["%geom", "  Calc_Hess true", "end"]
    lines.append(f"* xyz {structure['charge']} {structure['mult']}")
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])]
    lines += ["*", ""]
    return "\n".join(lines)


def parse_s2(text: str) -> float | None:
    """The unrestricted <S**2> of the LAST SCF of the output (an optimization prints one per geometry; the last belongs to the final structure); None for a restricted run."""
    found = re.findall(r"Expectation value of <S\*\*2>\s+:\s+(-?\d+\.\d+)", text)
    return float(found[-1]) if found else None


def parse_atom(text: str) -> dict:
    """The hydrogen atom's electronic energy from its single-point output; raises ValueError if the job did not finish normally."""
    if "ORCA TERMINATED NORMALLY" not in text:
        raise ValueError("the atom's job did not finish normally")
    found = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
    if not found:
        raise ValueError("no energy in the atom's output")
    return {"energy": float(found[-1]), "s2": parse_s2(text), "orca_version": (re.findall(r"Program Version\s+(\S+)", text) or [None])[-1]}


def parse_species(text: str) -> dict:
    """One Opt Freq output of a parent or radical: the proton-affinity protocol's reading (energy, enthalpy, frequencies, final geometry, 298.15 K and 1 atm checked) plus the radical's <S**2>."""
    return dict(pa.parse_output(text), s2=parse_s2(text))


def _heavy_bonds(mol: Chem.Mol) -> set[tuple[int, int]]:
    return {tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))) for b in mol.GetBonds() if b.GetBeginAtom().GetAtomicNum() > 1 and b.GetEndAtom().GetAtomicNum() > 1}


def same_skeleton(structure: dict, result: dict, mol: Chem.Mol) -> bool:
    """Whether an optimized structure is still the species it was meant to be: the parent's heavy-atom bonds and hydrogen counts, minus ONE hydrogen on the named atom for a radical.

    A radical that ORCA took to a rearranged structure (a hydrogen that migrated, a ring or chain that opened) has a lower energy and is not the radical of the bond; it is a failed structure, not a low one. Perception is from the optimized distances only."""
    perceived = pa.connectivity(result["symbols"], result["coordinates"])
    expected = pa.hydrogen_counts(mol)
    if structure["role"] == "radical":
        expected[structure["atom"]] -= 1
    return _heavy_bonds(perceived) == _heavy_bonds(mol) and pa.hydrogen_counts(perceived) == expected


def finish(structure: dict, result: dict, mol: Chem.Mol) -> dict:
    return dict(result, skeleton_kept=same_skeleton(structure, result, mol))


# --- selection ---------------------------------------------------------------------------------------------------------------


def accepted(records: list[dict]) -> list[dict]:
    """The records that count: a completed job (a species also with no imaginary frequency and its skeleton kept). A structure's retry replaces its first attempt."""
    latest: dict[str, dict] = {}
    for record in records:
        if record.get("completed"):
            latest[record["structure"]] = record
    return [r for r in latest.values() if r["role"] == "atom" or (r["lowest_frequency"] >= IMAGINARY_CM and r["skeleton_kept"])]


def select(parents: list[dict], radicals: list[dict], h_atom: float) -> dict:
    """One bond's DH298 (Hartree) from its accepted parent and radical records and the hydrogen atom's enthalpy: the lowest-enthalpy structure of each, independently."""
    parent, radical = min(parents, key=lambda r: r["enthalpy"]), min(radicals, key=lambda r: r["enthalpy"])
    return {"value_eh": bond_dissociation_enthalpy(parent["enthalpy"], radical["enthalpy"], h_atom), "s2": radical.get("s2"), "structures": len(parents) + len(radicals)}


@dataclass(frozen=True)
class BondRow:
    """One X-H bond of a molecule: its DH298 (kcal/mol) or None with the reason, and what stood behind it."""

    atom: int
    element: str
    label: str
    class_key: str
    dh_kcal: float | None
    s2: float | None = None
    structures: int = 0
    reason: str | None = None
    weakest: bool = False

    @property
    def dh_kj(self) -> float | None:
        return None if self.dh_kcal is None else self.dh_kcal * KCAL_TO_KJ

    @property
    def spin_contaminated(self) -> bool:
        return self.s2 is not None and spin_contaminated(self.s2)


@dataclass(frozen=True)
class BondResult:
    """The bonds of one run, each with a value or the reason it has none."""

    bonds: tuple[BondRow, ...] = ()
    parent_structures: int = 0
    dropped: tuple[str, ...] = field(default=())

    @property
    def computed(self) -> tuple[BondRow, ...]:
        return tuple(b for b in self.bonds if b.dh_kcal is not None)

    @property
    def weakest(self) -> BondRow | None:
        return next((b for b in self.bonds if b.weakest), None)


def _reason(parents: list[dict], radical_ids: list[str], records: list[dict], h_atom: float | None) -> str:
    """Why a bond has no value, in the words of the structures that were dropped."""
    if h_atom is None:
        return "the hydrogen atom's single point did not finish"
    if not parents:
        return "no accepted parent structure"
    latest = {r["structure"]: r for r in records}
    reasons = []
    for rid in radical_ids:
        r = latest.get(rid)
        if r is None:
            reasons.append(f"{rid}: not run")
        elif not r.get("completed"):
            reasons.append(f"{rid}: {r.get('error', 'did not finish')}")
        elif r["lowest_frequency"] < IMAGINARY_CM:
            reasons.append(f"{rid}: still a vibration at {r['lowest_frequency']:.0f} cm-1 after the one Calc_Hess re-run (a saddle point, not a minimum)")
        elif not r["skeleton_kept"]:
            reasons.append(f"{rid}: the radical rearranged, it is not the radical of this bond")
    return "no accepted radical structure (" + "; ".join(reasons) + ")" if reasons else "no accepted radical structure"


def resolve(mol: Chem.Mol, records: list[dict], atoms: list[int], key: str = "mol") -> BondResult:
    """The bonds of one run from the job records (every record of `build_structures`' jobs, retries included).

    A bond has a value when the hydrogen atom, one parent structure and one radical structure of the bond were accepted; the weakest of the computed bonds is marked."""
    done = accepted(records)
    h_atom = next((hydrogen_atom_enthalpy(r["energy"]) for r in reversed(done) if r["role"] == "atom"), None)
    parents = [r for r in done if r["role"] == "parent"]
    classes = {b["atom"]: b for b in bond_classes(mol)}
    rows = []
    for atom in atoms:
        bond = classes[atom]
        ids = sorted({r["structure"] for r in records if r["role"] == "radical" and r["atom"] == atom})
        radicals = [r for r in done if r["role"] == "radical" and r["atom"] == atom]
        base = {"atom": atom, "element": bond["element"], "label": bond["label"], "class_key": class_key(bond)}
        if h_atom is None or not parents or not radicals:
            rows.append(BondRow(**base, dh_kcal=None, reason=_reason(parents, ids, records, h_atom)))
            continue
        picked = select(parents, radicals, h_atom)
        rows.append(BondRow(**base, dh_kcal=picked["value_eh"] * HARTREE_TO_KCAL, s2=picked["s2"], structures=picked["structures"]))
    computed = [r for r in rows if r.dh_kcal is not None]
    if computed:
        low = min(computed, key=lambda r: r.dh_kcal)
        rows = [BondRow(**{**r.__dict__, "weakest": r is low}) for r in rows]
    all_ids = {r["structure"] for r in records}
    dropped = tuple(sorted(all_ids - {r["structure"] for r in done}))
    return BondResult(bonds=tuple(rows), parent_structures=len(parents), dropped=dropped)


# --- what was measured, stated beside every result --------------------------------------------------------------------------

#: The benchmarks' statistics on the 49 deciding bonds (kcal/mol, calculated minus experiment): 22 computed of the first run's 25, against Blanksby and Ellison (2003), and 27 held-out bonds against the Active Thermochemical Tables (1.228). Computed from the committed records
#: by `benchmarks/restart_v2/` and held to them by `tests/test_bond_dissociation_calculation.py`. `mse` is negative: the calculation runs LOW. The two O-H classes were separated after the results were seen.
BENCHMARK = {
    "all": {"n": 49, "mae": 1.48, "mse": -1.38, "max": 4.57},
    "first_run": {"n": 22, "mae": 1.76, "mse": -1.53, "max": 4.57, "reference": "Blanksby and Ellison (2003)"},
    "held_out": {"n": 27, "mae": 1.25, "mse": -1.25, "max": 3.27, "reference": "the Active Thermochemical Tables 1.228"},
    "C-H": {"n": 32, "mae": 1.28, "mse": -1.13, "max": 2.53},
    "N-H": {"n": 7, "mae": 1.02, "mse": -1.02, "max": 1.44},
    "O-H": {"n": 4, "mae": 1.68, "mse": -1.68, "max": 1.93},
    "O-H next to O or N": {"n": 4, "mae": 3.30, "mse": -3.30, "max": 4.57},
    "S-H": {"n": 1, "mae": 1.39, "mse": -1.39, "max": 1.39},
}


def validation_note(class_keys: list[str]) -> str:
    """The sentence that goes beside a result: what the protocol scored, in the classes this molecule's bonds belong to, and what that does not cover."""
    total = BENCHMARK["all"]
    parts = [
        (f"{METHOD_LABEL} protocol benchmarked on {total['n']} X-H bonds against experiment and the Active Thermochemical Tables: mean absolute error {total['mae']:.2f} kcal/mol ({total['mae'] * KCAL_TO_KJ:.1f} kJ/mol), "
        f"mean signed error {total['mse']:+.2f} (computed values run LOW, in every class), largest {total['max']:.2f}."),
    ]
    for key in sorted(set(class_keys)):
        stats = BENCHMARK.get(key)
        if stats is None:
            continue
        thin = " (one bond: not an error bar)" if stats["n"] < 3 else ""
        parts.append(f"{key}: {stats['n']} bonds, mean absolute error {stats['mae']:.2f}, mean signed error {stats['mse']:+.2f}, largest {stats['max']:.2f}{thin}.")
    if "S-H" in class_keys:
        parts.append("An S-H bond's radical may have no value: the benchmark's CH3S radical kept a -1306 cm-1 mode after the re-run.")
    parts.append(f"Measured for neutral closed-shell molecules of at most {MAX_HEAVY_ATOMS} heavy atoms of H, C, N, O and S; the lowest structure is used, with no Boltzmann averaging.")
    return " ".join(parts)


# --- the sequence of jobs --------------------------------------------------------------------------------------------------


class Sequence:
    """The ordered ORCA jobs of one molecule and what each finished job does to the plan: no process, no Qt, so the order, the one retry and the failure bookkeeping are testable without ORCA.

    `next_job()` hands out the structure to run (and whether it is the `Calc_Hess` retry); `finish(output_text)` reads that job's output, records it, and queues the one retry of a structure that kept an imaginary mode, from its own final geometry.
    A job whose output cannot be read is a failed structure with its reason and is NOT retried; the sequence goes on, because the other structures survive it. The hydrogen atom runs FIRST, and if it fails the rest is dropped: with no atom no bond has a value,
    and the molecule's other jobs would be hours for nothing. `result()` is `resolve` over what has been recorded.
    """

    def __init__(self, smiles: str, atoms: list[int] | None = None) -> None:
        self.smiles = smiles
        self.mol = molecule_from_smiles(smiles)  # raises OutOfScope
        classes = bond_classes(self.mol)
        chosen = [b["atom"] for b in classes] if atoms is None else list(atoms)
        if not chosen:
            raise OutOfScope("no bond was chosen")
        if len(chosen) > MAX_BONDS:
            raise OutOfScope(f"{len(chosen)} bonds: one run computes at most {MAX_BONDS}")
        if len(set(chosen)) != len(chosen):
            raise OutOfScope("a bond was chosen twice")
        self.atoms = chosen
        self.structures = build_structures(self.mol, chosen, key="mol")
        self._queue: list[tuple[dict, bool]] = [(s, False) for s in self.structures]
        self.current: tuple[dict, bool] | None = None
        self.records: list[dict] = []
        #: structure id -> why its output could not be read
        self.failures: dict[str, str] = {}
        #: set when the run cannot give any value (the hydrogen atom failed)
        self.fatal: str | None = None

    @property
    def total(self) -> int:
        """The structures to run (a retry is not a new structure)."""
        return len(self.structures)

    @property
    def settled(self) -> int:
        """How many structures are finished: recorded without a pending retry, or failed."""
        retrying = {s["id"] for s, retry in self._queue if retry}
        done = {r["structure"] for r in self.records if r.get("completed")} | set(self.failures)
        return len(done - retrying)

    @property
    def done(self) -> bool:
        return not self._queue

    def next_job(self) -> tuple[dict, bool]:
        """The next structure to run and whether this is its `Calc_Hess` retry. Raises IndexError when the sequence is finished."""
        self.current = self._queue.pop(0)
        return self.current

    def finish(self, output_text: str) -> str:
        """Reads the output of the job `next_job` handed out. Returns 'recorded', 'retrying' (the same structure is queued again with `Calc_Hess`) or 'failed'."""
        if self.current is None:
            raise RuntimeError("no job is running")
        structure, retry = self.current
        try:
            if structure["role"] == "atom":
                record = parse_atom(output_text)
            else:
                record = finish(structure, parse_species(output_text), self.mol)
        except Exception as error:  # noqa: BLE001 - one structure's output costs that structure, never the sequence
            reason = str(error) or type(error).__name__
            self.failures[structure["id"]] = reason
            self.records.append({"structure": structure["id"], "role": structure["role"], "retry": retry, "completed": False, "error": reason,
                                 **({"atom": structure["atom"]} if "atom" in structure else {})})
            if structure["role"] == "atom":
                self.fatal = f"the hydrogen atom's single point failed ({reason}); no bond can have a value without it"
                self._queue.clear()
            return "failed"
        record.update(structure=structure["id"], role=structure["role"], retry=retry, completed=True)
        if "atom" in structure:
            record["atom"] = structure["atom"]
        self.failures.pop(structure["id"], None)
        if retry:
            record["final"] = True
        self.records.append(record)
        if structure["role"] != "atom" and record["lowest_frequency"] < IMAGINARY_CM and not retry:
            self._queue.insert(0, (dict(structure, symbols=record["symbols"], coordinates=record["coordinates"]), True))
            return "retrying"
        return "recorded"

    def result(self) -> BondResult:
        return resolve(self.mol, self.records, self.atoms)


# --- the typed output --------------------------------------------------------------------------------------------------------

#: The id of the bond-dissociation output (an enthalpy).
DESCRIPTOR_ID = "orca.bond_dissociation_enthalpy"
#: The unit it is given in, as the other thermochemical outputs are.
UNITS = "kJ/mol"


def descriptors(sequence: Sequence, molecule_uuid: str, run_id: str = "", timestamp: float | None = None) -> list[DescriptorValue]:
    """The typed output of a finished sequence: `orca.bond_dissociation_enthalpy`, the weakest of the bonds that have a value, in kJ/mol, with the whole bond table and the benchmarks' measured error in its provenance.

    A bond with no value is listed with its reason and never zero; if NO bond has one the output is a FAILED descriptor naming the structures that were dropped. A value is the weakest OF THE BONDS COMPUTED, and the provenance says how many bonds had none."""
    result = sequence.result()
    h = pa.K_B * T_STANDARD / pa.HARTREE_J
    class_keys = [b.class_key for b in result.bonds]
    weakest = result.weakest
    value = None if weakest is None else weakest.dh_kj
    parameters = {
        "method": METHOD_LABEL, "program": "ORCA", "temperature_k": T_STANDARD, "pressure_atm": 1.0, "smiles": sequence.smiles, "quantity": "bond_dissociation_enthalpy",
        "hydrogen_atom_translation_kcal": 2.5 * h * HARTREE_TO_KCAL, "validation": validation_note(class_keys),
        "bonds": [{"atom": b.atom, "element": b.element, "label": b.label, "class": b.class_key, "dh_kj": b.dh_kj, "dh_kcal": b.dh_kcal, "s2": b.s2, "spin_contaminated": b.spin_contaminated,
                   "structures": b.structures, "weakest": b.weakest, "reason": b.reason} for b in result.bonds],
        "bonds_without_value": sum(1 for b in result.bonds if b.dh_kcal is None), "parent_structures": result.parent_structures, "dropped_structures": list(result.dropped),
        "failures": dict(sequence.failures), "lowest_structure_only": True,
    }
    if weakest is not None:
        parameters["weakest_atom"] = weakest.atom
    if run_id:
        parameters["run_id"] = run_id
    provenance = Provenance(created_by="core", method=METHOD_LABEL, parameters=parameters, **({} if timestamp is None else {"timestamp": timestamp}))
    error = None if value is not None else _missing_reason(result, sequence)
    return [DescriptorValue(
        descriptor_id=DESCRIPTOR_ID, name="Weakest X-H bond dissociation enthalpy (298.15 K)", units=UNITS, category="quantum_chemistry", provider="orca", molecule_uuid=molecule_uuid, value=value,
        timestamp=timestamp, cache_state=CacheState.COMPLETED if value is not None else CacheState.FAILED, error=error, error_summary=None if error is None else "No bond has a value", provenance=provenance,
    )]


def _missing_reason(result: BondResult, sequence: Sequence) -> str:
    """Why no bond has a value, in the words of the first bond's reason (or the run's fatal failure)."""
    if sequence.fatal:
        return sequence.fatal
    reasons = "; ".join(f"{b.label}: {b.reason}" for b in result.bonds if b.reason)
    return f"No bond has a value: a structure is accepted only when its optimization converged, no vibrational frequency is below {IMAGINARY_CM:.0f} cm-1 after the one Calc_Hess re-run and a radical is still the radical of its bond. {reasons}"
