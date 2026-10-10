"""Build a population of variants from seed molecules, name it, and check whether a name depends on how the SMILES is written.

    python tools/naming_variants.py "C1CC2CC(C1)c1ccccc12" --ops swap_hetero
    python tools/naming_variants.py "c1cnc2ccnn2c1" --ops "add_substituent>protonate_aromatic_n,protonate_sp3_nh"
    python tools/naming_variants.py --file seeds.txt --ops swap_hetero --orderings 20 --seed 7 --json out.json
    python tools/naming_variants.py --list-ops

**WHY IT EXISTS.** Naming rounds 32-37 each built their population in a throwaway script (`gen_bb.py`, `gen_cat.py`, `genpop.py`,
`genpop2.py`): replace one ring atom, protonate one nitrogen, hang a substituent on every free carbon. The rules were rewritten each
time, so two rounds' populations were never comparable and a bug in a generator read as a bug in the engine. These operators are those
scripts' rules, ported and named by the round that wrote them; they are NOT broadened.

**THE OPERATORS ARE THE PRIOR ROUNDS' ELIGIBILITY TESTS, not a general chemistry.** `protonate_*` in particular does not ask what is
basic: it protonates what rounds 33-35 protonated (an aromatic N of degree 2 with no H, a non-aromatic N with one H, the N of a ring
C=N). An amide N is not excluded because the old scripts never met one. `exo_ylidene` (round 36) is absent because no generator
for it was saved, and a rule rebuilt from memory is not the rule that round used.

**`--ops` is a chain.** `a,b` applies each of a and b to the seeds independently; `a>b` applies a, keeps its outputs AND its inputs,
then applies b to all of them and keeps only b's outputs. That is exactly how round 34 and 35 built theirs (substituents first, then
the cation of each). The population is the output of the last stage.

**THE ORDERING DIAGNOSTIC DOES NOT GO THROUGH `naming_census_scan.name_rows`**, which canonicalises every SMILES it is handed: random
spellings pushed through it would all arrive as one canonical string and the report would find every structure stable. Each spelling is
passed to the namer exactly as written. The reference for the read-back is always the canonical structure, and a spelling whose
InChIKey differs from it is reported as SERIALIZATION_MISMATCH, never as a naming defect (a spelling written from a molecule that did not come
from SMILES can be a different stereoisomer; tests/test_namer_stereo_locant_tie.py met this once).

**FROZEN POPULATIONS.** The canonical seed is checked before anything is generated from it, and every generated structure before
anything is named. A refused structure is reported by its id and the population that holds it, never by its SMILES, and the exit
status is 3 if anything was refused. The check is `naming_populations.frozen_key_of`, a hash question answered from the meta files.

Site numbers in the provenance are atom indices in the CANONICAL SMILES of the structure the operator was applied to (the structure
named by `on`), not chemical locants. Needs a JRE on PATH for the read-back unless `--names-only`.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import shutil
import sys
import warnings
from pathlib import Path
from typing import Callable, Iterator, NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import naming_census_scan as census_scan  # noqa: E402
import naming_populations as populations  # noqa: E402

#: The substituents `add_substituent` hangs on a carbon (rounds 34 and 35 together: C N O Cl phenyl, plus acetyl and acetamido).
SUBSTITUENTS = ("C", "N", "O", "Cl", "c1ccccc1", "C(=O)C", "NC(=O)C")

#: Atomic numbers `swap_hetero` writes (round 32): O, N, S.
_SWAP_TO = (8, 7, 16)

#: At most this many origin paths are kept per structure; `origin_count` always carries the real number.
_ORIGINS_KEPT = 20

SERIALIZATION_MISMATCH = "SERIALIZATION_MISMATCH"


class Candidate(NamedTuple):
    """One site an operator considered: a molecule, or `None` and the reason it produced none."""

    site: str
    mol: object | None
    skip: str | None = None


@contextlib.contextmanager
def _rdkit_quiet() -> Iterator[None]:
    """RDKit logs every failed sanitisation; a generator that tries sites expects most of them to fail."""
    from rdkit import rdBase

    block = rdBase.BlockLogs()
    try:
        yield
    finally:
        del block


def _sanitised(rw) -> object | None:
    from rdkit import Chem

    try:
        mol = rw.GetMol()
        Chem.SanitizeMol(mol)
        return mol
    except Exception:  # noqa: BLE001 - a site that does not sanitise is skipped, with its reason, by the caller
        return None


def _writable(mol):
    from rdkit import Chem

    return Chem.RWMol(mol)


def swap_hetero(mol) -> Iterator[Candidate]:
    """Round 32 (`gen_bb.py`): each NON-aromatic ring atom replaced in turn by O, N or S.

    An O or S needs a ring atom of degree 2 or less and an N of degree 3 or less; the replaced atom's hydrogens are reset so the
    valence is recomputed, as round 32 did.
    """
    for atom in mol.GetAtoms():
        if not atom.IsInRing() or atom.GetIsAromatic():
            continue
        for number in _SWAP_TO:
            site = f"atom {atom.GetIdx()} -> {number}"
            if atom.GetAtomicNum() == number:
                yield Candidate(site, None, "same element")
                continue
            if atom.GetDegree() > (2 if number in (8, 16) else 3):
                yield Candidate(site, None, "degree too high for the element")
                continue
            rw = _writable(mol)
            target = rw.GetAtomWithIdx(atom.GetIdx())
            target.SetAtomicNum(number)
            target.SetNumExplicitHs(0)
            target.SetNoImplicit(False)
            out = _sanitised(rw)
            yield Candidate(site, out, None if out is not None else "does not sanitise")


def protonate_aromatic_n(mol) -> Iterator[Candidate]:
    """Rounds 33 and 35: an aromatic N of degree 2, charge 0 and no hydrogen becomes `[nH+]`, and also its N-methyl cation.

    Round 33 additionally chose only molecules whose ring was fused to another aromatic ring; that was a choice of SEEDS and is left
    to the caller. The hydrogen test is the one round 33 had; round 35 relied on sanitisation to refuse a pyrrole-type `[nH]`.
    """
    for atom in mol.GetAtoms():
        if not (atom.GetAtomicNum() == 7 and atom.GetIsAromatic() and atom.GetFormalCharge() == 0 and atom.GetDegree() == 2):
            continue
        if atom.GetTotalNumHs() != 0:
            yield Candidate(f"atom {atom.GetIdx()}", None, "aromatic N already carries a hydrogen")
            continue
        rw = _writable(mol)
        target = rw.GetAtomWithIdx(atom.GetIdx())
        target.SetFormalCharge(1)
        target.SetNumExplicitHs(1)
        target.SetNoImplicit(True)
        out = _sanitised(rw)
        yield Candidate(f"atom {atom.GetIdx()} [nH+]", out, None if out is not None else "does not sanitise")
        yield _n_methyl(mol, atom.GetIdx())


def protonate_sp3_nh(mol) -> Iterator[Candidate]:
    """Round 35: a non-aromatic, uncharged N with exactly one hydrogen becomes `[NH2+]`."""
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 7 and not atom.GetIsAromatic() and atom.GetFormalCharge() == 0 and atom.GetTotalNumHs() == 1:
            rw = _writable(mol)
            target = rw.GetAtomWithIdx(atom.GetIdx())
            target.SetFormalCharge(1)
            target.SetNumExplicitHs(2)
            target.SetNoImplicit(True)
            out = _sanitised(rw)
            yield Candidate(f"atom {atom.GetIdx()}", out, None if out is not None else "does not sanitise")


def protonate_ring_imine(mol) -> Iterator[Candidate]:
    """Round 34: the N of a non-aromatic ring C=N becomes `[NH+]` (hydrogens + 1), and also its N-methyl iminium."""
    for atom in mol.GetAtoms():
        if not (atom.GetAtomicNum() == 7 and atom.GetFormalCharge() == 0 and not atom.GetIsAromatic()):
            continue
        if not any(b.GetBondTypeAsDouble() == 2 and b.IsInRing() for b in atom.GetBonds()):
            continue
        rw = _writable(mol)
        target = rw.GetAtomWithIdx(atom.GetIdx())
        target.SetFormalCharge(1)
        target.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
        target.SetNoImplicit(True)
        out = _sanitised(rw)
        yield Candidate(f"atom {atom.GetIdx()} [NH+]", out, None if out is not None else "does not sanitise")
        yield _n_methyl(mol, atom.GetIdx())


def _n_methyl(mol, index: int) -> Candidate:
    """The N-methyl cation of the nitrogen at `index`: a carbon is bonded on, the charge is set, hydrogens are recomputed."""
    from rdkit import Chem

    rw = _writable(mol)
    carbon = rw.AddAtom(Chem.Atom(6))
    rw.AddBond(index, carbon, Chem.BondType.SINGLE)
    target = rw.GetAtomWithIdx(index)
    target.SetFormalCharge(1)
    target.SetNoImplicit(False)
    out = _sanitised(rw)
    return Candidate(f"atom {index} N-methyl", out, None if out is not None else "does not sanitise")


def add_substituent(mol) -> Iterator[Candidate]:
    """Rounds 34 and 35: each carbon with at least one hydrogen (aromatic ones too) takes one of `SUBSTITUENTS` by a single bond."""
    from rdkit import Chem

    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6 or atom.GetTotalNumHs() < 1:
            continue
        for sub in SUBSTITUENTS:
            combined = Chem.RWMol(Chem.CombineMols(mol, Chem.MolFromSmiles(sub)))
            combined.AddBond(atom.GetIdx(), mol.GetNumAtoms(), Chem.BondType.SINGLE)
            out = _sanitised(combined)
            yield Candidate(f"atom {atom.GetIdx()} + {sub}", out, None if out is not None else "does not sanitise")


#: In the order they are applied and listed. Dict order is the only ordering the output depends on.
OPERATORS: dict[str, Callable] = {
    "swap_hetero": swap_hetero,
    "protonate_aromatic_n": protonate_aromatic_n,
    "protonate_sp3_nh": protonate_sp3_nh,
    "protonate_ring_imine": protonate_ring_imine,
    "add_substituent": add_substituent,
}


def parse_ops(spec: str) -> list[list[str]]:
    """`"a,b>c"` -> `[["a","b"],["c"]]`: stages joined by `>`, the alternatives of a stage by `,`."""
    stages = [[name.strip() for name in stage.split(",") if name.strip()] for stage in spec.split(">")]
    if not stages or any(not stage for stage in stages):
        raise ValueError(f"empty stage in --ops {spec!r}")
    unknown = sorted({name for stage in stages for name in stage} - set(OPERATORS))
    if unknown:
        raise ValueError(f"unknown operator(s) {unknown}; known: {list(OPERATORS)}")
    return stages


def structure_id(canonical: str) -> str:
    """A stable id from the structure itself, so it does not move when the population around it does."""
    return "v" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:10]


def canonical_of(mol) -> str:
    from rdkit import Chem

    return Chem.MolToSmiles(mol)


class _FrozenGuard:
    """`naming_populations.frozen_key_of`, with the membership read ONCE per run instead of once per structure.

    `frozen_key_of` re-reads every frozen population's meta file on each call, which is right for the probe (a handful of structures)
    and several seconds per thousand for a generator. This asks the same question of the same registry: the salted hash of the
    canonical SMILES against the hashes the meta files carry. No frozen population file is opened.
    """

    def __init__(self) -> None:
        self._membership = populations.frozen_membership()

    def key_of(self, canonical: str) -> str | None:
        for key, (salt, hashes) in self._membership.items():
            if populations.membership_hash(canonical, salt) in hashes:
                return key
        return None


def build_population(seeds: list[str], stages: list[list[str]]) -> dict:
    """Seeds -> the population, with provenance, yield accounting and what was refused. Pure chemistry: nothing here names a molecule.

    `population` maps canonical SMILES to `{id, origins, origin_count}`; a structure produced twice is one entry with both origins.
    Each origin is `{seed, path: [{op, site, on}]}`, `on` being the id of the structure the operator was applied to.
    """
    from rdkit import Chem

    guard = _FrozenGuard()
    yield_of: dict[str, collections.Counter] = {name: collections.Counter() for stage in stages for name in stage}
    skips: dict[str, collections.Counter] = {name: collections.Counter() for name in yield_of}
    refused: dict[str, dict] = {}
    invalid_seeds: list[str] = []
    seed_ids: dict[str, str] = {}

    current: dict[str, list[dict]] = {}
    with _rdkit_quiet():
        for index, text in enumerate(seeds):
            mol = Chem.MolFromSmiles(text)
            if mol is None:
                invalid_seeds.append(text)
                continue
            canonical = canonical_of(mol)
            seed_id = f"s{index}"
            frozen = guard.key_of(canonical)
            if frozen is not None:
                refused[seed_id] = {"kind": "seed", "population": frozen}
                continue
            seed_ids[seed_id] = canonical
            current.setdefault(canonical, []).append({"seed": seed_id, "path": []})

        intermediates: dict[str, str] = {}
        outputs: dict[str, dict] = {}
        for stage_index, stage in enumerate(stages):
            outputs = {}
            for canonical in sorted(current):
                mol = Chem.MolFromSmiles(canonical)
                on = structure_id(canonical)
                for name in stage:
                    for candidate in OPERATORS[name](mol):
                        yield_of[name]["attempted"] += 1
                        if candidate.mol is None:
                            yield_of[name]["skipped"] += 1
                            skips[name][candidate.skip or "unspecified"] += 1
                            continue
                        made = canonical_of(candidate.mol)
                        if made == canonical:
                            yield_of[name]["duplicate"] += 1  # the operator changed nothing (a swap to the element already there)
                            continue
                        frozen = guard.key_of(made)
                        if frozen is not None:
                            yield_of[name]["refused"] += 1
                            refused.setdefault(structure_id(made), {"kind": "generated", "population": frozen})
                            continue
                        yield_of[name]["duplicate" if made in outputs else "unique"] += 1
                        step = {"op": name, "site": candidate.site, "on": on}
                        entry = outputs.setdefault(made, {"origins": [], "origin_count": 0})
                        for origin in current[canonical]:
                            entry["origin_count"] += 1
                            if len(entry["origins"]) < _ORIGINS_KEPT:
                                entry["origins"].append({"seed": origin["seed"], "path": [*origin["path"], step]})
            last = stage_index == len(stages) - 1
            if not last:
                merged = {c: list(o) for c, o in current.items()}
                for canonical, entry in outputs.items():
                    merged.setdefault(canonical, []).extend(entry["origins"])
                current = merged
                # Recorded AFTER the merge: a step's `on` can be a structure the previous stage made, not only a seed.
                for canonical in current:
                    intermediates[structure_id(canonical)] = canonical
        population = {
            canonical: {"id": structure_id(canonical), "origins": entry["origins"], "origin_count": entry["origin_count"]}
            for canonical, entry in sorted(outputs.items())
        }
    return {
        "population": population,
        "yield": {name: {**{k: yield_of[name][k] for k in ("attempted", "skipped", "refused", "duplicate", "unique")}, "skip_reasons": dict(skips[name])}
                  for name in yield_of},
        "refused": refused,
        "invalid_seeds": invalid_seeds,
        "seeds": seed_ids,
        "intermediates": intermediates,
    }


# --- the ordering diagnostic ---------------------------------------------------------------------------------------------------------

def spellings(canonical: str, count: int, seed: int) -> list[str]:
    """`count` spellings of one structure, each from a random permutation of its atoms, written in that order; `seed` reproduces them.

    **Not `MolToSmiles(doRandom=True)`.** In the RDKit this was written against (2025.09.6) `doRandom` ignores
    `rdBase.SeedRandomNumberGenerator`: the same seed wrote different strings on each call (measured), so a finding could not be
    reproduced from the seed the report recorded. A seeded `random.Random` shuffles the atom numbering instead, and
    `MolToSmiles(..., canonical=False)` writes the atoms in that order: a random root and a random branch order, deterministically.

    The generator is seeded PER STRUCTURE: a structure's spellings must not depend on which structures came before it, or the same
    finding could not be reproduced from a smaller population. The InChIKey check in `order_report` still decides whether a spelling
    is that structure.
    """
    import random

    from rdkit import Chem

    mol = Chem.MolFromSmiles(canonical)
    rng = random.Random(seed)
    out: list[str] = []
    for _ in range(count):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        out.append(Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False))
    return out


def _identity_key(smiles: str) -> str | None:
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToInchiKey(mol) if mol is not None else None


def _engine_namer() -> Callable[[str], str]:
    from openchem.vendor.iupac_namer import name_smiles

    def namer(smiles: str) -> str:
        try:
            return name_smiles(smiles)
        except Exception as exc:  # noqa: BLE001 - the refusal guard raises ValueError on purpose
            return f"RAISED: {type(exc).__name__}: {str(exc)[:100]}"

    return namer


def order_report(
    structures: dict[str, str],
    count: int,
    seed: int,
    *,
    namer: Callable[[str], str] | None = None,
    reader: Callable[[list[str]], list[str]] | None = None,
) -> dict[str, dict]:
    """For each `{id: canonical SMILES}`: name the canonical spelling and `count` random ones, each AS WRITTEN, and group by name.

    A spelling is used only if its InChIKey equals the canonical structure's; one that is not is recorded as
    `SERIALIZATION_MISMATCH` and takes no part in the comparison. `reader` turns names into read-back SMILES (None skips the
    read-back). Every read-back is classified against the CANONICAL structure, never against the spelling it came from.
    """
    namer = namer or _engine_namer()
    report: dict[str, dict] = {}
    for sid, canonical in structures.items():
        want = _identity_key(canonical)
        samples = [{"spelling": canonical, "kind": "canonical"}]
        samples += [{"spelling": s, "kind": "random"} for s in spellings(canonical, count, seed)]
        by_name: dict[str, list[str]] = collections.defaultdict(list)
        mismatched: list[str] = []
        for sample in samples:
            if _identity_key(sample["spelling"]) != want:
                sample["status"] = SERIALIZATION_MISMATCH
                mismatched.append(sample["spelling"])
                continue
            sample["name"] = namer(sample["spelling"])
            by_name[sample["name"]].append(sample["spelling"])
        names = sorted(by_name)
        backs = reader(names) if (reader is not None and names) else [None] * len(names)
        report[sid] = {
            "canonical": canonical,
            "seed": seed,
            "requested": count,
            "valid_samples": sum(len(v) for v in by_name.values()),
            "serialization_mismatches": mismatched,
            "distinct_names": len(names),
            "names": [
                {"name": n, "spellings": by_name[n], "back": b, "cls": census_scan.classify(canonical, n, b if reader is not None else None)}
                for n, b in zip(names, backs)
            ],
        }
    return report


# --- reporting -----------------------------------------------------------------------------------------------------------------------

def yield_lines(built: dict) -> list[str]:
    lines = ["operator yield (attempted = sites considered; skipped never produced a molecule; unique counts a structure once, for its first maker)"]
    for name, y in built["yield"].items():
        lines.append(f"  {name:22s} attempted {y['attempted']:5d}  skipped {y['skipped']:5d}  refused {y['refused']:3d}  duplicate {y['duplicate']:5d}  unique {y['unique']:5d}")
        for reason, n in sorted(y["skip_reasons"].items()):
            lines.append(f"    skipped {n:5d}  {reason}")
    return lines


def order_lines(report: dict[str, dict]) -> list[str]:
    unstable = {k: v for k, v in report.items() if v["distinct_names"] > 1}
    mismatched = sum(len(v["serialization_mismatches"]) for v in report.values())
    lines = [f"ordering diagnostic: {len(report)} structures, {len(unstable)} with more than one name; "
             f"{mismatched} spellings were not the same structure ({SERIALIZATION_MISMATCH}) and were not counted"]
    for sid, v in unstable.items():
        lines.append(f"  {sid} {v['canonical']}  ({v['valid_samples']} valid samples, seed {v['seed']})")
        for entry in v["names"]:
            lines.append(f"    {entry['cls']:18s} {len(entry['spellings']):3d} spellings  {entry['name'][:110]}")
            lines.append(f"    {'':18s} e.g. {entry['spellings'][0]}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("smiles", nargs="*", help="seed structures")
    parser.add_argument("--file", type=Path, help="one seed SMILES per line; blank lines and '#' comments are skipped")
    parser.add_argument("--ops", default=",".join(OPERATORS), help="stages joined by '>', alternatives by ','; default: every operator, one stage")
    parser.add_argument("--list-ops", action="store_true", help="print the operators and exit")
    parser.add_argument("--with-seeds", action="store_true", help="also name the seeds, as a control")
    parser.add_argument("--orderings", type=int, default=0, metavar="N", help="also name N random spellings of each structure, as written")
    parser.add_argument("--seed", type=int, default=0, help="RDKit random seed for the spellings (recorded in the report)")
    parser.add_argument("--names-only", action="store_true", help="skip the OPSIN read-back (no JRE needed)")
    parser.add_argument("--json", type=Path, help="write the full record set here")
    args = parser.parse_args(argv)

    if args.list_ops:
        for name, fn in OPERATORS.items():
            print(f"{name:22s} {fn.__doc__.strip().splitlines()[0]}")
        return 0
    seeds = list(args.smiles)
    if args.file:
        seeds += [line.strip() for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not seeds:
        parser.error("no seed molecules given")
    if not args.names_only and shutil.which("java") is None:
        print("No bare `java` on PATH: OPSIN needs one, and without it every name reads as unparsable. Put the JRE on PATH "
              "(as `/c/...`, not `C:/...`, in bash) or pass --names-only.", file=sys.stderr)
        return 2
    warnings.filterwarnings("ignore")

    built = build_population(seeds, parse_ops(args.ops))
    population = built["population"]
    rows = {c: v["id"] for c, v in population.items()}
    if args.with_seeds:
        for seed_id, canonical in built["seeds"].items():
            rows.setdefault(canonical, structure_id(canonical))
    for seed_id, info in sorted(built["refused"].items()):
        print(f"{'FROZEN':10} refused {info['kind']} {seed_id}: in {info['population']}, which is evaluation-only (tools/naming_populations.py)")
    for text in built["invalid_seeds"]:
        print(f"{'INVALID':10} {text}")

    print(f"{len(built['seeds'])} seeds -> {len(population)} unique structures")
    for line in yield_lines(built):
        print(line)

    records = census_scan.scan([{"label": sid, "smiles": c} for c, sid in rows.items()], names_only=args.names_only) if rows else {}
    for line in census_scan.summarise(records) if records else []:
        print(line)
    for sid, record in records.items():
        if record["cls"] != "exact":
            print(f"  {record['cls']:22s} {record['smiles']}  ->  {record['name'][:100]}")

    order = {}
    if args.orderings > 0 and rows:
        with census_scan._engine_logging_silenced():
            order = order_report({sid: c for c, sid in rows.items()}, args.orderings, args.seed,
                                 reader=None if args.names_only else census_scan.read_back)
        for line in order_lines(order):
            print(line)

    if args.json:
        by_smiles = {v["id"]: (c, v) for c, v in population.items()}
        payload = {
            "tool": "tools/naming_variants.py",
            "ops": args.ops,
            "seeds": built["seeds"],
            "invalid_seeds": built["invalid_seeds"],
            "refused": built["refused"],
            "yield": built["yield"],
            "intermediates": built["intermediates"],
            "population": [
                {"id": sid, "smiles": records[sid]["smiles"], "name": records[sid]["name"], "back": records[sid]["back"],
                 "cls": records[sid]["cls"], "delta": records[sid].get("delta"),
                 "origins": by_smiles[sid][1]["origins"] if sid in by_smiles else [{"seed": "control", "path": []}],
                 "origin_count": by_smiles[sid][1]["origin_count"] if sid in by_smiles else 1}
                for sid in sorted(records)
            ],
            "orderings": {"count": args.orderings, "seed": args.seed, "structures": order},
        }
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        print(f"-> {args.json}")
    return 3 if built["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
