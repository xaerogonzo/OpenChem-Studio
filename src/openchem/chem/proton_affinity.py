"""Proton affinity (PA) and gas-phase basicity (GB) of a neutral base, from ORCA: the chemistry of the protocol, with no engine, no Qt and no file read.

This is the protocol that `benchmarks/proton_affinity/` preregistered and measured (PASS for both PA and GB on 2026-10-20, ORCA 6.1.1: on 21 bases whose reference PA is above propene's, PA has a mean absolute error of 1.55 kcal/mol and GB 1.53, both with a mean signed error of about -1.2 to -1.3 kcal/mol, i.e. the proton is bound about that much too weakly, against the NIST evaluation of Hunter and Lias).
Nothing here may drift from that protocol without a new benchmark: the keywords, the structure generation, the protonation sites, the acceptance rule and the symmetry-number override are the benchmark's, and `tests/test_proton_affinity_calculation.py` checks them against the benchmark's own records.

THE PROTOCOL. `PA = H(B) + H(H+) - H(BH+)` and `GB = G(B) + G(H+) - G(BH+)` at 298.15 K and 1 atm, from M062X/def2-TZVPD `Opt Freq` jobs of the base and of every conjugate acid.
* Structures: each species is embedded with ETKDG (seed 7, 30 conformers), MMFF94-relaxed, deduplicated by all-atom RMSD 0.5 Angstrom, and the lowest three within 5 kcal/mol are optimized.
* Sites: every N, O, S or P without a positive charge and every carbon of a C=C, C#C or aromatic bond (plus the carbon of carbon monoxide), sites equivalent by the graph's symmetry merged; EVERY site is optimized and the lowest wins. An optimization that moves the proton to another atom is recorded as that atom's.
* Acceptance: a structure with a vibrational frequency below -20 cm-1 is re-run once with `Calc_Hess` and dropped if it still has one; the conjugate acid must have gained exactly one hydrogen on exactly one heavy atom of the base.
* The proton has no electrons: its enthalpy and Gibbs energy are the translational ones (`proton_terms`).
* THE SYMMETRY NUMBER IS OVERRIDDEN: ORCA gave a C3v H3O+ the number 1, which is 0.65 kcal/mol in G; `rotational_symmetry_number` counts the proper rotations from the graph's automorphisms and `symmetry_correction_eh` is added to ORCA's Gibbs energy. The enthalpy has no symmetry term.
* No Boltzmann averaging over conformers: the lowest structure only.

WHAT IT CANNOT SAY (the benchmark's own limits): 28 neutral bases of at most ten heavy atoms with H, C, N, O, P and S; nothing about larger or charged bases, radicals, metals, halogens or solutions. A base outside that scope is refused by `check_scope`, not computed with an unmeasured error. A structure that keeps an imaginary mode after the one re-run is dropped, so a base with no accepted structure has no value (the benchmark lost water to it: its H3O+ optimized planar, a saddle point).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds, rdMolAlign

from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue

#: CODATA 2018 (exact SI definitions where defined).
K_B = 1.380649e-23  # J/K
#: Planck constant, J s.
H_PLANCK = 6.62607015e-34  # J s
#: Avogadro constant, 1/mol.
N_A = 6.02214076e23
#: One Hartree in joules.
HARTREE_J = 4.3597447222071e-18
#: Proton mass, kg.
M_PROTON = 1.67262192369e-27  # kg
#: The standard pressure of the thermochemistry, 1 atm in pascals.
ATM_PA = 101325.0
#: One thermochemical kcal/mol in joules per mole.
KCAL_J = 4184.0
#: The temperature of the benchmark and of every NIST value in it.
T_STANDARD = 298.15

#: kcal/mol per Hartree (627.5095).
HARTREE_TO_KCAL = HARTREE_J * N_A / KCAL_J  # 627.5095 kcal/mol per Eh
#: kJ per kcal, the factor between the benchmark's kcal/mol and NIST's kJ/mol.
KCAL_TO_KJ = 4.184

#: The preregistered job (PREREGISTRATION.md): one level for optimization and frequencies.
HEADER = "! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq"
#: The model chemistry as a result states it.
METHOD_LABEL = "M062X/def2-TZVPD"
#: The ETKDG seed of the conformer search (the benchmark's).
SEED = 7
#: How many conformers ETKDG embeds before the MMFF relaxation and the deduplication.
CONFORMERS = 30
#: Two conformers closer than this all-atom RMSD (Angstrom) are one.
DEDUPE_RMSD = 0.5
#: How many conformers per species are optimized.
KEEP = 3
#: Only conformers within this MMFF energy of the lowest are optimized.
KEEP_WINDOW_KCAL = 5.0
#: A vibrational frequency below this (cm-1) makes a structure not accepted.
IMAGINARY_CM = -20.0
#: ORCA's memory per core in MB (the benchmark's setting).
MAXCORE_MB = 3000

#: What the benchmark measured: the elements and the size of its 28 bases.
SUPPORTED_ELEMENTS = frozenset({1, 6, 7, 8, 15, 16})
#: The largest base the benchmark measured, in heavy atoms.
MAX_HEAVY_ATOMS = 10

#: The elements whose lone pair is a protonation site: N, O, P and S.
LONE_PAIR_ELEMENTS = {7, 8, 15, 16}  # N, O, P, S
#: The X-H distance (Angstrom) a new proton starts at, by the atomic number of X.
XH_DISTANCE = {6: 1.09, 7: 1.02, 8: 0.97, 15: 1.42, 16: 1.34}


class OutOfScope(ValueError):
    """The base is outside what the benchmark measured. The message says why and is meant to be shown."""


# --- the arithmetic ---------------------------------------------------------------------------------------------------------


def proton_terms(temperature: float = T_STANDARD, pressure: float = ATM_PA) -> tuple[float, float, float]:
    """(H, S, G) of the gas-phase proton: Hartree, Hartree per kelvin and Hartree, at `temperature` and `pressure` (Sackur-Tetrode, translation only)."""
    kt = K_B * temperature
    wavelength = H_PLANCK / math.sqrt(2.0 * math.pi * M_PROTON * kt)
    s_per_particle = K_B * (math.log(kt / (pressure * wavelength**3)) + 2.5)  # J/K
    h = 2.5 * kt / HARTREE_J
    s = s_per_particle / HARTREE_J
    return h, s, h - temperature * s


def proton_affinity(h_base: float, h_acid: float, temperature: float = T_STANDARD) -> float:
    """PA(B) = H(B) + H(H+) - H(BH+), in Hartree, from the total enthalpies of the base and its conjugate acid."""
    return h_base + proton_terms(temperature)[0] - h_acid


def gas_basicity(g_base: float, g_acid: float, temperature: float = T_STANDARD) -> float:
    """GB(B) = G(B) + G(H+) - G(BH+), in Hartree, from the Gibbs energies of the base and its conjugate acid."""
    return g_base + proton_terms(temperature)[2] - g_acid


def symmetry_correction_eh(sigma_true: int, sigma_orca: int, temperature: float = T_STANDARD) -> float:
    """What to ADD to ORCA's Gibbs energy (Hartree) when its symmetry number is `sigma_orca` and the molecule's is `sigma_true`: RT ln(sigma_true / sigma_orca)."""
    if sigma_true < 1 or sigma_orca < 1:
        raise ValueError("a symmetry number is at least 1")
    return K_B * temperature / HARTREE_J * math.log(sigma_true / sigma_orca)


def _best_rotation_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """The RMSD of `a` onto `b` over all atoms after the best PROPER rotation (a mirror image does not count), both centred."""
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    u, _s, vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(u @ vt))
    rotation = u @ np.diag([1.0, 1.0, d]) @ vt
    return float(np.sqrt(((a @ rotation - b) ** 2).sum() / len(a)))


def rotational_symmetry_number(mol, coordinates: np.ndarray, tolerance: float = 0.05) -> int:
    """The external rotational symmetry number: how many proper rotations (the identity included) map the molecule onto itself within `tolerance` Angstrom.

    `mol` is an RDKit molecule with explicit hydrogens whose atom order matches `coordinates` (N x 3, Angstrom). Every graph automorphism is a candidate permutation of the atoms; one is a symmetry operation if the permuted structure
    coincides with the original after a proper rotation (a reflection is not a rotation, so an automorphism that needs one is not counted). Internal rotors (a methyl group) are not counted: methanol is 1 and not 3.
    """
    coordinates = np.asarray(coordinates, dtype=float)
    if len(coordinates) != mol.GetNumAtoms():
        raise ValueError("the coordinates do not match the molecule's atoms")
    matches = mol.GetSubstructMatches(mol, uniquify=False, maxMatches=200000, useChirality=False)
    count = 0
    seen: set[tuple[int, ...]] = set()
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        permuted = coordinates[list(match)]
        if _best_rotation_rmsd(coordinates, permuted) <= tolerance:
            count += 1
    return max(count, 1)


# --- scope ------------------------------------------------------------------------------------------------------------------


def base_from_smiles(smiles: str) -> Chem.Mol:
    """The base with explicit hydrogens, or OutOfScope with the reason the calculation does not apply."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise OutOfScope("the structure could not be read")
    return check_scope(Chem.AddHs(mol))


def check_scope(mol: Chem.Mol) -> Chem.Mol:
    """Returns `mol` if it is the kind of base the benchmark measured, else raises OutOfScope saying which limit it passes.

    The kind: one neutral closed-shell molecule of at most ten heavy atoms made of H, C, N, O, P and S (carbon monoxide, the benchmark's one charge-separated structure, is allowed)."""
    if len(Chem.GetMolFrags(mol)) != 1:
        raise OutOfScope("more than one component: a base is one molecule")
    heavy = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() > 1)
    if heavy == 0:
        raise OutOfScope("no heavy atom to protonate")
    if heavy > MAX_HEAVY_ATOMS:
        raise OutOfScope(f"{heavy} heavy atoms: the benchmark measured bases of at most {MAX_HEAVY_ATOMS}")
    odd = sorted({a.GetSymbol() for a in mol.GetAtoms() if a.GetAtomicNum() not in SUPPORTED_ELEMENTS})
    if odd:
        raise OutOfScope(f"{', '.join(odd)}: the benchmark measured only H, C, N, O, P and S")
    if any(a.GetNumRadicalElectrons() for a in mol.GetAtoms()):
        raise OutOfScope("a radical: the benchmark measured closed-shell bases")
    if _is_charged(mol):
        raise OutOfScope("a charged or zwitterionic structure: the benchmark measured neutral bases")
    if not candidate_sites(mol):
        raise OutOfScope("no protonation site (no N, O, S or P lone pair and no pi-system carbon)")
    return mol


def _is_charged(mol: Chem.Mol) -> bool:
    charges = [a.GetFormalCharge() for a in mol.GetAtoms() if a.GetFormalCharge()]
    if not charges:
        return False
    # carbon monoxide ([C-]#[O+]) is the one charge-separated structure the benchmark measured
    return sorted(charges) != [-1, 1] or sorted(a.GetSymbol() for a in mol.GetAtoms()) != ["C", "O"]


# --- structures -------------------------------------------------------------------------------------------------------------


def candidate_sites(mol: Chem.Mol) -> list[dict]:
    """The protonation sites of a base (explicit hydrogens), equivalent sites by graph symmetry merged into one.

    (a) every N, O, S or P without a positive charge ('lone_pair'); (b) every carbon of a C=C, C#C or aromatic bond ('pi_carbon'); plus the carbon of carbon monoxide ('lone_pair': it carries the negative charge).
    Returns `{"atom": index, "kind": ..., "class": rank}` with the lowest-index atom of each symmetry class.
    """
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    seen: set[tuple[str, int]] = set()
    sites = []
    for atom in mol.GetAtoms():
        kind = None
        if (atom.GetAtomicNum() in LONE_PAIR_ELEMENTS and atom.GetFormalCharge() <= 0) or (atom.GetAtomicNum() == 6 and atom.GetFormalCharge() < 0):
            kind = "lone_pair"  # N, O, P, S, and carbon monoxide's carbon
        elif atom.GetAtomicNum() == 6 and any(b.GetBondType() == Chem.BondType.AROMATIC for b in atom.GetBonds()):
            kind = "pi_carbon"  # every carbon of an aromatic ring, including one bonded only to heteroatoms
        elif atom.GetAtomicNum() == 6 and any(b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(atom).GetAtomicNum() == 6 for b in atom.GetBonds()) or atom.GetAtomicNum() == 6 and any(b.GetBondType() == Chem.BondType.TRIPLE and b.GetOtherAtom(atom).GetAtomicNum() == 6 for b in atom.GetBonds()):
            kind = "pi_carbon"
        if kind is None or (kind, ranks[atom.GetIdx()]) in seen:
            continue
        seen.add((kind, ranks[atom.GetIdx()]))
        sites.append({"atom": atom.GetIdx(), "kind": kind, "class": int(ranks[atom.GetIdx()])})
    return sites


def _rmsd(mol: Chem.Mol, probe: int, reference: int) -> float:
    """All-atom (hydrogens included) symmetry-aware RMSD of two conformers of one molecule; works on copies because the call aligns the probe in place."""
    return rdMolAlign.GetBestRMS(Chem.Mol(mol), Chem.Mol(mol), probe, reference)


def conformers_of(mol: Chem.Mol) -> list[np.ndarray]:
    """The kept conformers of a base: ETKDG (seed 7, 30), MMFF94, deduplicated by all-atom RMSD 0.5 Angstrom (symmetry-aware), the lowest three within 5 kcal/mol of the lowest."""
    work = Chem.Mol(mol)
    ids = list(AllChem.EmbedMultipleConfs(work, numConfs=CONFORMERS, randomSeed=SEED))
    if not ids:
        raise RuntimeError("no conformer could be embedded")
    if work.GetNumAtoms() < 3:
        results = [(0.0, cid) for cid in ids]
    else:
        energies = AllChem.MMFFOptimizeMoleculeConfs(work, maxIters=5000)
        results = sorted(((e, cid) for (_c, e), cid in zip(energies, ids)), key=lambda pair: pair[0])
    lowest = results[0][0]
    kept: list[int] = []
    for energy, cid in results:
        if energy - lowest > KEEP_WINDOW_KCAL or len(kept) >= KEEP:
            break
        if all(_rmsd(work, cid, k) > DEDUPE_RMSD for k in kept):
            kept.append(cid)
    return [np.array(work.GetConformer(cid).GetPositions()) for cid in kept]


def _bent(direction: np.ndarray, bond: np.ndarray, atom: Chem.Atom, mol: Chem.Mol, coordinates: np.ndarray) -> np.ndarray:
    """A carbonyl-type oxygen's proton, tilted 60 degrees off the C=O axis (in the plane of the carbon's other neighbours, else any plane containing the axis).

    Exactly on the axis the start has C-infinity-like symmetry and an optimizer can stay on a saddle whose bend is imaginary; the real ion is bent (about 120 degrees at O)."""
    neighbor = atom.GetNeighbors()[0]
    others = [coordinates[n.GetIdx()] - coordinates[neighbor.GetIdx()] for n in neighbor.GetNeighbors() if n.GetIdx() != atom.GetIdx()]
    perpendicular = None
    if others:
        n = np.cross(bond, others[0])
        if np.linalg.norm(n) > 1e-6:
            perpendicular = np.cross(n, direction)
    if perpendicular is None or np.linalg.norm(perpendicular) < 1e-6:
        trial = np.array([1.0, 0.0, 0.0]) if abs(direction[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        perpendicular = np.cross(direction, trial)
    perpendicular /= np.linalg.norm(perpendicular)
    angle = np.radians(60.0)
    return np.cos(angle) * direction + np.sin(angle) * perpendicular


def add_proton(mol: Chem.Mol, coordinates: np.ndarray, site: dict) -> tuple[list[str], np.ndarray]:
    """A conjugate acid's starting geometry: the base's atoms and one more hydrogen on the site.

    A heteroatom (or carbon monoxide's carbon) takes it along the lone-pair direction, the negative sum of the unit vectors to its neighbours (the plane's normal if that sum is nearly zero); a pi carbon takes it perpendicular to the plane of its neighbours.
    Returns (the element symbols, the coordinates) with the new hydrogen LAST, so the base's atom indices are unchanged."""
    atom = mol.GetAtomWithIdx(site["atom"])
    origin = coordinates[site["atom"]]
    vectors = []
    for neighbor in atom.GetNeighbors():
        v = coordinates[neighbor.GetIdx()] - origin
        vectors.append(v / np.linalg.norm(v))
    normal = None
    if len(vectors) >= 2:
        n = np.cross(vectors[0], vectors[1])
        if np.linalg.norm(n) > 1e-6:
            normal = n / np.linalg.norm(n)
    away = -np.sum(vectors, axis=0)
    if site["kind"] == "pi_carbon" and normal is not None:
        direction = normal
    elif np.linalg.norm(away) > 0.3:
        direction = away / np.linalg.norm(away)
    elif normal is not None:
        direction = normal
    else:
        raise ValueError(f"no direction for the proton on atom {site['atom']}")
    if len(vectors) == 1 and atom.GetBonds()[0].GetBondType() == Chem.BondType.DOUBLE:
        direction = _bent(direction, vectors[0], atom, mol, coordinates)
    distance = XH_DISTANCE.get(atom.GetAtomicNum(), 1.1)
    symbols = [a.GetSymbol() for a in mol.GetAtoms()] + ["H"]
    return symbols, np.vstack([coordinates, origin + distance * direction])


def build_structures(mol: Chem.Mol, key: str = "base") -> list[dict]:
    """Every ORCA job of a base: its kept conformers and, for each, the conjugate acid at every candidate site. `mol` has explicit hydrogens and passed `check_scope`.

    Each structure is a dict with `id`, `base` (= `key`), `role` ('base' or 'ion'), `charge`, `symbols`, `coordinates` (Angstrom) and, for an ion, `site_atom`, `site_class`, `site_kind`."""
    structures = []
    sites = candidate_sites(mol)
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    for index, coordinates in enumerate(conformers_of(mol)):
        structures.append({"id": f"{key}|base|{index}", "base": key, "role": "base", "charge": 0, "symbols": symbols, "coordinates": coordinates.tolist()})
        for site in sites:
            s, xyz = add_proton(mol, coordinates, site)
            structures.append({"id": f"{key}|ion|{site['kind']}{site['atom']}|{index}", "base": key, "role": "ion", "charge": 1, "site_atom": site["atom"], "site_class": site["class"],
                               "site_kind": site["kind"], "symbols": s, "coordinates": xyz.tolist()})
    return structures


# --- the ORCA job and its output --------------------------------------------------------------------------------------------


def orca_input(structure: dict, cores: int, retry: bool = False) -> str:
    """The input of one job: the preregistered keywords; `retry` adds `Calc_Hess` (the one re-run of a structure that kept an imaginary mode)."""
    lines = [HEADER, f"%pal nprocs {cores} end", f"%maxcore {MAXCORE_MB}"]
    if retry:
        lines += ["%geom", "  Calc_Hess true", "end"]
    lines.append(f"* xyz {structure['charge']} 1")
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])]
    lines += ["*", ""]
    return "\n".join(lines)


def parse_output(text: str) -> dict:
    """What the protocol needs from one Opt Freq output; raises ValueError naming the first thing missing."""

    def last(pattern: str):
        found = re.findall(pattern, text)
        return found[-1] if found else None

    if "THE OPTIMIZATION HAS CONVERGED" not in text:
        raise ValueError("the geometry optimization did not converge")
    block_start = text.rfind("CARTESIAN COORDINATES (ANGSTROEM)")
    if block_start < 0:
        raise ValueError("no final geometry")
    symbols, coordinates = [], []
    for line in text[block_start:].splitlines()[2:]:
        m = re.match(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", line)
        if not m:
            break
        symbols.append(m.group(1))
        coordinates.append([float(m.group(2)), float(m.group(3)), float(m.group(4))])
    frequencies = []
    freq_start = text.rfind("VIBRATIONAL FREQUENCIES")
    if freq_start >= 0:
        for line in text[freq_start:].splitlines():
            m = re.match(r"^\s*\d+:\s+(-?\d+\.\d+) cm\*\*-1", line)
            if m:
                frequencies.append(float(m.group(1)))
            elif frequencies and not line.strip():
                break
    enthalpy, gibbs, energy = last(r"Total enthalpy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), last(r"Final Gibbs free energy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), last(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
    sigma, temperature, pressure = last(r"Symmetry Number:\s+(\d+)"), last(r"Temperature\s+\.\.\.\s+(\d+\.\d+) K"), last(r"Pressure\s+\.\.\.\s+(\d+\.\d+) atm")
    for label, value in (("enthalpy", enthalpy), ("Gibbs free energy", gibbs), ("electronic energy", energy), ("symmetry number", sigma), ("frequencies", frequencies or None)):
        if value is None:
            raise ValueError(f"no {label} in the output")
    if abs(float(temperature) - T_STANDARD) > 1e-6 or abs(float(pressure) - 1.0) > 1e-6:
        raise ValueError(f"thermochemistry at {temperature} K and {pressure} atm, not 298.15 K and 1 atm")
    version = last(r"Program Version\s+(\S+)")
    return {"energy": float(energy), "enthalpy": float(enthalpy), "gibbs": float(gibbs), "sigma_orca": int(sigma), "frequencies": frequencies, "lowest_frequency": min(frequencies),
            "symbols": symbols, "coordinates": coordinates, "orca_version": version}


def connectivity(symbols: list[str], coordinates) -> Chem.Mol:
    """An RDKit molecule with bonds perceived from distances only (no bond orders, no charges): what the symmetry number and the site assignment need."""
    block = f"{len(symbols)}\n\n" + "\n".join(f"{s} {x:.6f} {y:.6f} {z:.6f}" for s, (x, y, z) in zip(symbols, coordinates)) + "\n"
    mol = Chem.MolFromXYZBlock(block)
    rdDetermineBonds.DetermineConnectivity(mol)
    mol.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(mol)
    return mol


def hydrogen_counts(mol: Chem.Mol) -> dict[int, int]:
    return {a.GetIdx(): sum(1 for n in a.GetNeighbors() if n.GetAtomicNum() == 1) for a in mol.GetAtoms() if a.GetAtomicNum() != 1}


def assigned_site(base: Chem.Mol, result: dict) -> int | None:
    """The base atom that gained the proton in the optimized ion: the ONE heavy atom (of the base's atoms, which come first) whose hydrogen count rose, or None if it is not exactly one (the proton was lost or went somewhere a count cannot place)."""
    before = hydrogen_counts(base)
    after = hydrogen_counts(connectivity(result["symbols"], result["coordinates"]))
    gained = [i for i in before if after.get(i, 0) - before[i] == 1]
    lost = [i for i in before if after.get(i, 0) - before[i] < 0]
    return gained[0] if len(gained) == 1 and not lost else None


def finish(structure: dict, result: dict, base: Chem.Mol) -> dict:
    """Adds what the protocol computes from one parsed output: the symmetry number of the optimized structure, the Gibbs correction it implies, and the corrected G (and, for an ion, the site the proton ended on)."""
    mol = connectivity(result["symbols"], result["coordinates"])
    sigma_true = rotational_symmetry_number(mol, np.array(result["coordinates"]))
    correction = symmetry_correction_eh(sigma_true, result["sigma_orca"])
    out = dict(result, sigma_true=sigma_true, symmetry_correction=correction, gibbs_corrected=result["gibbs"] + correction)
    if structure["role"] == "ion":
        out["site_assigned"] = assigned_site(base, result)
    return out


# --- selection ---------------------------------------------------------------------------------------------------------------


def accepted(records: list[dict]) -> list[dict]:
    """The records that count: a completed job whose lowest frequency is not imaginary. A structure's retry replaces its first attempt."""
    latest: dict[str, dict] = {}
    for record in records:
        if record.get("completed", True):
            latest[record["structure"]] = record
    return [r for r in latest.values() if r["lowest_frequency"] >= IMAGINARY_CM]


@dataclass(frozen=True)
class SiteRow:
    """One protonation site of a base: its best conjugate acid, with PA and GB (kcal/mol) from the lowest base structure."""

    atom: int
    element: str
    kind: str
    pa_kcal: float
    gb_kcal: float
    structures: int
    chosen_pa: bool = False
    chosen_gb: bool = False


@dataclass(frozen=True)
class ProtonationResult:
    """PA and GB of one base, each with the site that won; None for a quantity with no accepted base or conjugate acid."""

    pa_kcal: float | None
    gb_kcal: float | None
    pa_site: int | None
    gb_site: int | None
    sites: tuple[SiteRow, ...] = ()
    base_structures: int = 0
    ion_structures: int = 0
    dropped: tuple[str, ...] = field(default=())

    @property
    def pa_kj(self) -> float | None:
        return None if self.pa_kcal is None else self.pa_kcal * KCAL_TO_KJ

    @property
    def gb_kj(self) -> float | None:
        return None if self.gb_kcal is None else self.gb_kcal * KCAL_TO_KJ


def resolve(base: Chem.Mol, records: list[dict]) -> ProtonationResult:
    """PA and GB from the job records of one base (every record of `build_structures(base)`'s jobs, retries included).

    PA: the base structure of lowest H and the conjugate acid of lowest H over every site and conformer; GB: likewise by the corrected G, chosen independently. A site is the base atom that gained the proton, equivalent atoms merged.
    `dropped` names the structures that are not accepted (an imaginary mode left, or the proton moved off the base's atoms), so a missing value has its reason."""
    done = accepted(records)
    all_ids = {r["structure"] for r in records}  # a structure whose output could not be read is dropped too, with its record naming why
    dropped = tuple(sorted(all_ids - {r["structure"] for r in done}))
    bases = [r for r in done if r["role"] == "base"]
    ions = [r for r in done if r["role"] == "ion" and r.get("site_assigned") is not None]
    dropped += tuple(sorted(r["structure"] for r in done if r["role"] == "ion" and r.get("site_assigned") is None))
    if not bases or not ions:
        return ProtonationResult(None, None, None, None, base_structures=len(bases), ion_structures=len(ions), dropped=dropped)
    ranks = list(Chem.CanonicalRankAtoms(base, breakTies=False))
    best_base_h = min(bases, key=lambda r: r["enthalpy"])
    best_base_g = min(bases, key=lambda r: r["gibbs_corrected"])
    by_class: dict[int, list[dict]] = {}
    for ion in ions:
        by_class.setdefault(ranks[ion["site_assigned"]], []).append(ion)
    rows = []
    for group in by_class.values():
        atom = min(r["site_assigned"] for r in group)
        pa = proton_affinity(best_base_h["enthalpy"], min(r["enthalpy"] for r in group)) * HARTREE_TO_KCAL
        gb = gas_basicity(best_base_g["gibbs_corrected"], min(r["gibbs_corrected"] for r in group)) * HARTREE_TO_KCAL
        rows.append((atom, pa, gb, len(group)))
    pa_row = max(rows, key=lambda row: row[1])
    gb_row = max(rows, key=lambda row: row[2])
    table = tuple(
        SiteRow(atom=atom, element=base.GetAtomWithIdx(atom).GetSymbol(), kind="pi_carbon" if base.GetAtomWithIdx(atom).GetAtomicNum() == 6 and not base.GetAtomWithIdx(atom).GetFormalCharge() else "lone_pair",
                pa_kcal=pa, gb_kcal=gb, structures=n, chosen_pa=atom == pa_row[0], chosen_gb=atom == gb_row[0])
        for atom, pa, gb, n in sorted(rows, key=lambda row: -row[1])
    )
    return ProtonationResult(pa_kcal=pa_row[1], gb_kcal=gb_row[2], pa_site=pa_row[0], gb_site=gb_row[0], sites=table, base_structures=len(bases), ion_structures=len(ions), dropped=dropped)


# --- what was measured, stated beside every result --------------------------------------------------------------------------

#: The benchmark's statistics on the 21 deciding bases (reference PA above propene's), kcal/mol, from `benchmarks/proton_affinity/artifacts/report.txt` (run 2026-10-20, commit 6ec0fd29): mean absolute error,
#: mean signed error (negative: the calculation binds the proton too weakly) and the largest absolute error. A result carries these so a number is never shown without the accuracy it was measured to have.
BENCHMARK = {
    "pa": {"mae": 1.55, "mse": -1.19, "max": 2.94},
    "gb": {"mae": 1.53, "mse": -1.27, "max": 2.99},
    "bases": 21,
    "reference": "NIST evaluation of Hunter and Lias (1998)",
}


def validation_note(quantity: str) -> str:
    """The sentence that goes beside a PA ('pa') or GB ('gb') value: what the protocol scored against NIST, and what that does not cover."""
    stats = BENCHMARK[quantity]
    kj = KCAL_TO_KJ
    return (
        f"{METHOD_LABEL} protocol benchmarked on {BENCHMARK['bases']} bases against the {BENCHMARK['reference']}: mean absolute error {stats['mae']:.2f} kcal/mol ({stats['mae'] * kj:.1f} kJ/mol), "
        f"mean signed error {stats['mse']:+.2f} kcal/mol (the proton is bound too weakly), largest {stats['max']:.2f}. Measured for neutral bases of at most {MAX_HEAVY_ATOMS} heavy atoms of H, C, N, O, P and S; "
        "the lowest structure is used, with no Boltzmann averaging."
    )


# --- the sequence of jobs --------------------------------------------------------------------------------------------------


class Sequence:
    """The ordered ORCA jobs of one base and what each finished job does to the plan: no process, no Qt, so the order, the one retry and the failure bookkeeping are testable without ORCA.

    `next_job()` hands out the structure to run (and whether it is the `Calc_Hess` retry); `finish(output_text)` reads that job's output, records it, and queues the one retry of a structure that kept an imaginary mode,
    from its own final geometry. A job whose output cannot be read (the optimization did not converge, say) is a failed structure with its reason and is NOT retried (the benchmark retried only imaginary modes);
    the sequence goes on, because the other structures' results survive it. `result()` is `resolve` over what has been recorded.
    """

    def __init__(self, smiles: str) -> None:
        self.smiles = smiles
        self.base = base_from_smiles(smiles)  # raises OutOfScope
        self.structures = build_structures(self.base, key="mol")
        self._queue: list[tuple[dict, bool]] = [(s, False) for s in self.structures]
        self.current: tuple[dict, bool] | None = None
        self.records: list[dict] = []
        #: structure id -> why its output could not be read
        self.failures: dict[str, str] = {}

    @property
    def total(self) -> int:
        """The structures to run (a retry is not a new structure)."""
        return len(self.structures)

    @property
    def settled(self) -> int:
        """How many structures are finished: recorded without a pending retry, or failed."""
        retrying = {s["id"] for s, retry in self._queue if retry}
        done = {r["structure"] for r in self.records if r.get("completed", True)} | set(self.failures)
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
            parsed = parse_output(output_text)
            record = finish(structure, parsed, self.base)
        except Exception as error:  # noqa: BLE001 - one structure's output costs that structure, never the sequence
            reason = str(error) or type(error).__name__
            self.failures[structure["id"]] = reason
            self.records.append({"structure": structure["id"], "base": structure["base"], "role": structure["role"], "retry": retry, "completed": False, "error": reason})
            return "failed"
        record.update(structure=structure["id"], base=structure["base"], role=structure["role"], retry=retry, completed=True)
        if structure["role"] == "ion" and "site_atom" in structure:
            record["site_start"] = structure["site_atom"]
        self.failures.pop(structure["id"], None)
        if retry:
            record["final"] = True
        self.records.append(record)
        if record["lowest_frequency"] < IMAGINARY_CM and not retry:
            self._queue.insert(0, (dict(structure, symbols=record["symbols"], coordinates=record["coordinates"]), True))
            return "retrying"
        return "recorded"

    def result(self) -> ProtonationResult:
        return resolve(self.base, self.records)


# --- the typed outputs -------------------------------------------------------------------------------------------------------

#: The id of the proton-affinity output (an enthalpy).
PA_DESCRIPTOR_ID = "orca.proton_affinity"
#: The id of the gas-basicity output (a Gibbs energy).
GB_DESCRIPTOR_ID = "orca.gas_basicity"
#: The unit both outputs are given in, as NIST tabulates them.
UNITS = "kJ/mol"


def descriptors(sequence: Sequence, molecule_uuid: str, run_id: str = "", timestamp: float | None = None) -> list[DescriptorValue]:
    """The two typed outputs of a finished sequence: `orca.proton_affinity` (an enthalpy) and `orca.gas_basicity` (a Gibbs energy), in kJ/mol as NIST tabulates them, each with its provenance.

    PA and GB are separate outputs and each can be missing alone. A quantity with no value is a FAILED descriptor whose error names the structures that were dropped, never a zero.
    The provenance records everything a reader needs to place the number: the method, 298.15 K and 1 atm, the proton's terms, the protonation site that won and the whole site table, how many structures stood behind it,
    the symmetry numbers ORCA reported against the ones used, and the benchmark's measured error with its limits."""
    result = sequence.result()
    now = timestamp
    h, s, g = proton_terms()
    symmetric = [r for r in accepted(sequence.records) if r.get("sigma_true") != r.get("sigma_orca")]
    common = {
        "method": METHOD_LABEL, "program": "ORCA", "temperature_k": T_STANDARD, "pressure_atm": 1.0, "smiles": sequence.smiles,
        "proton_terms_kcal": {"H": h * HARTREE_TO_KCAL, "TS": T_STANDARD * s * HARTREE_TO_KCAL, "G": g * HARTREE_TO_KCAL},
        "base_structures": result.base_structures, "ion_structures": result.ion_structures, "dropped_structures": list(result.dropped),
        "failures": dict(sequence.failures),
        "symmetry_number_overrides": len(symmetric),
        "sites": [{"atom": row.atom, "element": row.element, "kind": row.kind, "pa_kj": row.pa_kcal * KCAL_TO_KJ, "gb_kj": row.gb_kcal * KCAL_TO_KJ, "structures": row.structures,
                   "chosen_pa": row.chosen_pa, "chosen_gb": row.chosen_gb} for row in result.sites],
        "lowest_structure_only": True,
    }
    if run_id:
        common["run_id"] = run_id
    out = []
    for quantity, value, site, descriptor_id, name in (
        ("pa", result.pa_kj, result.pa_site, PA_DESCRIPTOR_ID, "Proton affinity (298.15 K)"),
        ("gb", result.gb_kj, result.gb_site, GB_DESCRIPTOR_ID, "Gas-phase basicity (298.15 K)"),
    ):
        parameters = dict(common, quantity=quantity, validation=validation_note(quantity), site_atom=site)
        if site is not None:
            parameters["site_element"] = sequence.base.GetAtomWithIdx(site).GetSymbol()
        provenance = Provenance(created_by="core", method=METHOD_LABEL, parameters=parameters, **({} if now is None else {"timestamp": now}))
        error = None if value is not None else _missing_reason(result, sequence)
        out.append(
            DescriptorValue(
                descriptor_id=descriptor_id, name=name, units=UNITS, category="quantum_chemistry", provider="orca", molecule_uuid=molecule_uuid, value=value, timestamp=now,
                cache_state=CacheState.COMPLETED if value is not None else CacheState.FAILED, error=error,
                error_summary=None if error is None else "No accepted structure", provenance=provenance,
            )
        )
    return out


def _missing_reason(result: ProtonationResult, sequence: Sequence) -> str:
    """Why a quantity has no value, in the words of the structures that were dropped."""
    if not result.base_structures:
        side = "the base"
    elif not result.ion_structures:
        side = "any conjugate acid"
    else:
        side = "a structure"
    named = ", ".join(result.dropped) or "none ran to completion"
    return (f"No accepted structure for {side}: a structure is accepted only when its optimization converged and no vibrational frequency is below {IMAGINARY_CM:.0f} cm-1 after the one "
            f"Calc_Hess re-run, and the proton must end on one atom of the base. Dropped: {named}.")
