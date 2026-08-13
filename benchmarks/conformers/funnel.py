"""Where conformer candidates are lost: sampling, minimisation, merge, cap.

Built because "I got 17" is not an answer to "is the generator throwing
things away". A count cannot tell an under-sampling problem from an
over-merging one, and the two call for opposite responses -- more
embeddings, or a different criterion. This prints every stage, and then
the pairs that were actually DISCARDED, which is the population no
existing tool reported.

**OBSERVATIONAL. It runs production and reports on it.** Every stage below
is the application's own function: `RDKitConformerProvider` for the
sampling, `distinct_conformers` for both de-duplication arms,
`select_for_return` for the cap. There is no funnel-local notion of what
makes two conformers the same, no funnel-local ordering, and no
funnel-local truncation. **A discrepancy between this and the running app
is a bug in this file, not evidence about conformer quality.**

The one thing it varies is documented and singular: the RMSD-only arm is
production de-duplication with the energy window at infinity, reusing
`NO_VETO` from `build_predictions.py`. Nothing else differs.

Usage:
    python funnel.py "CCCCO"
    python funnel.py ethylmorphine --seeds 3
    python funnel.py "CCCCO" --inspect "seed=0 embedding=17"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rdkit import Chem, RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from openchem.chem.conformer_providers import (  # noqa: E402
    DEFAULT_ENERGY_WINDOW,
    ORIGIN_PROPERTY,
    DEFAULT_RMS_THRESHOLD,
    GenerationOptions,
    RDKitConformerProvider,
    distinct_conformers,
    merge_candidates,
    select_for_return,
)
from openchem.ui.dialogs.conformer_options_dialog import (  # noqa: E402
    DEFAULT_CONFORMERS_TO_KEEP,
    DEFAULT_EMBEDDINGS_TO_TRY,
)

from build_predictions import NO_VETO, SEED_STRIDE  # noqa: E402

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent


def _corpus() -> dict[str, str]:
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    return {entry["name"]: entry["smiles"] for entry in corpus["molecules"]}


def _origin_index(batch) -> dict[str, Chem.Mol]:
    """`ORIGIN_PROPERTY` -> the molecule, for both populations.

    Keyed on the tag rather than on a position, because `results` is sorted
    by energy and `pre_optimisation` is not, so index `i` names two
    different embeddings the moment anything fails to converge.
    """
    index = {mol.GetProp(ORIGIN_PROPERTY): mol for mol, _energy in batch.results}
    for mol in batch.pre_optimisation:
        index.setdefault(mol.GetProp(ORIGIN_PROPERTY) + " (pre-opt)", mol)
    return index


def _one_seed(smiles: str, seed: int, args) -> dict:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise SystemExit(f"SMILES did not parse: {smiles}")
    batch = RDKitConformerProvider(random_seed=seed).generate_conformer_batch(
        mol,
        args.embeddings,
        optimize=True,
        options=GenerationOptions(
            diversity_rmsd=args.rmsd_threshold, record_pre_optimisation=True
        ),
    )
    # PRE-OPT GOES THROUGH THE SAME MACHINERY, energy window at infinity.
    # These geometries have no energy anyway, so the veto could not fire on
    # them -- passing NO_VETO says that explicitly rather than relying on it.
    pre = distinct_conformers(
        [(m, None) for m in batch.pre_optimisation], args.rmsd_threshold, NO_VETO
    )
    rmsd_only = distinct_conformers(batch.results, args.rmsd_threshold, NO_VETO)
    shipped = distinct_conformers(batch.results, args.rmsd_threshold, args.energy_window)
    returned = select_for_return(shipped, args.keep)
    candidates = merge_candidates(
        batch.results, args.rmsd_threshold, args.energy_window, with_torsions=True
    )
    return {
        "seed": seed,
        "batch": batch,
        "requested": args.embeddings,
        "attempted": batch.attempted,
        "embedded": batch.embedded,
        "converged": batch.converged,
        "embedding_failures": batch.embedding_failures,
        "convergence_failures": batch.convergence_failures,
        "pre": len(pre),
        "rmsd_only": len(rmsd_only),
        "shipped": len(shipped),
        "returned": len(returned),
        "retained": shipped,
        "candidates": candidates,
    }


def _print_funnel(run: dict, args) -> None:
    print(f"  requested embeddings          {run['requested']:>6}")
    print(f"  attempted                     {run['attempted']:>6}")
    print(f"  embedded                      {run['embedded']:>6}"
          f"   ({run['embedding_failures']} failed to embed)")
    print(f"  converged                     {run['converged']:>6}"
          f"   ({run['convergence_failures']} failed to converge)")
    print(f"  distinct PRE-opt              {run['pre']:>6}"
          f"   RMSD-only; UPPER BOUND on candidate diversity, not a basin count")
    print(f"  distinct POST-opt, RMSD only  {run['rmsd_only']:>6}"
          f"   production dedup, energy window = inf")
    print(f"  distinct, shipped criterion   {run['shipped']:>6}"
          f"   production dedup")
    print(f"  returned                      {run['returned']:>6}"
          f"   production cap at {args.keep}")

    # A hard production invariant: the cap can only remove.
    assert run["returned"] <= run["shipped"], (
        f"returned {run['returned']} exceeds distinct {run['shipped']} -- "
        f"the cap is not slicing the production result"
    )
    # NOT an invariant, and printed as what it is. The veto can only
    # DECLINE merges, but greedy leader clustering is order-dependent and
    # the two arms retain different SETS, so this is an observation that
    # has held on every corpus molecule rather than something guaranteed.
    relation = "observed" if run["shipped"] >= run["rmsd_only"] else "VIOLATED"
    print(f"\n  expected current relationship: shipped >= RMSD-only ... {relation}")
    if relation == "VIOLATED":
        print("    ^ investigate; this is a finding, not a crash. Greedy clustering")
        print("      is order-dependent, so the arms can retain different sets.")

    lost = run["shipped"] - run["returned"]
    if lost:
        print(f"\n  {lost} distinct conformer(s) found and NOT returned, removed only by")
        print(f"  the cap of {args.keep}. They converged and are distinct under the")
        print("  shipped criterion; raising the cap returns them.")


def _name_torsion(mol: Chem.Mol | None, atoms) -> str:
    """`C7-C10=C12-O14`, or the bare indices when no molecule is to hand.

    NAMING THE ATOMS IS THE POINT. "a torsion moved 134 degrees" cannot be
    classified; "the carboxyl C-C(=O)-O rotated" can, and the difference
    between a real conformational degree of freedom and a force-field
    artefact is exactly what the decision gate turns on.
    """
    if atoms is None:
        return "-"
    if mol is None:
        return "-".join(str(i) for i in atoms)
    parts = []
    for index in atoms:
        atom = mol.GetAtomWithIdx(int(index))
        parts.append(f"{atom.GetSymbol()}{index}{'*' if atom.GetIsAromatic() else ''}")
    return "-".join(parts)


def _print_discarded(run: dict, limit: int) -> None:
    merged = [c for c in run["candidates"] if c.merged]
    if not merged:
        print("\n  nothing was merged away.")
        return
    index = _origin_index(run["batch"])
    unavailable = sum(1 for c in merged if c.max_dihedral_change is None)
    print(f"\n  MERGED AWAY: {len(merged)} pair(s) discarded as the same conformer.")
    print("  Ranked by corrected max dihedral, because that is the measure that")
    print("  can show a real torsional difference the RMSD gate did not see.")
    print("  A large value is a pair to LOOK AT, not a defect on its own.")
    if unavailable:
        print(f"  {unavailable} pair(s) could not be measured -- reported as n/a, never as 0.")
    print(f"    {'candidate':<22} {'merged into':<22} {'RMSD':>6} {'dE':>7} "
          f"{'TFD':>7} {'maxDih':>8}  torsion")
    ranked = sorted(merged, key=lambda c: -(c.max_dihedral_change or -1.0))
    for c in ranked[:limit]:
        dih = "     n/a" if c.max_dihedral_change is None else f"{c.max_dihedral_change:>8.1f}"
        tfd = "    n/a" if c.tfd is None else f"{c.tfd:>7.4f}"
        de = "    n/a" if c.energy_difference is None else f"{c.energy_difference:>7.3f}"
        print(
            f"    {str(c.candidate_origin):<22} {str(c.representative_origin):<22} "
            f"{c.rmsd:>6.3f} {de} {tfd} {dih}  "
            f"{_name_torsion(index.get(c.candidate_origin), c.largest_torsion)}"
        )
    if len(ranked) > limit:
        print(f"    ... {len(ranked) - limit} more")


def _inspect(runs: list[dict], origin: str, out: Path) -> int:
    """Write the named merged-away candidate AND its representative.

    The pair is the artefact, not the candidate: "this was discarded" is
    only meaningful beside "in favour of that".
    """
    for run in runs:
        index = _origin_index(run["batch"])
        match = next(
            (c for c in run["candidates"] if c.merged and c.candidate_origin == origin), None
        )
        if match is None:
            continue
        candidate = index.get(match.candidate_origin)
        representative = index.get(match.representative_origin)
        if candidate is None or representative is None:
            print(f"{origin} was merged away but its molecules are no longer in the batch")
            return 1
        writer = Chem.SDWriter(str(out))
        for mol, role in ((candidate, "discarded"), (representative, "representative")):
            tagged = Chem.Mol(mol)
            tagged.SetProp("_Name", f"{role}: {mol.GetProp(ORIGIN_PROPERTY)}")
            tagged.SetProp("role", role)
            tagged.SetProp("origin", mol.GetProp(ORIGIN_PROPERTY))
            tagged.SetProp("pair_rmsd", f"{match.rmsd:.4f}")
            tagged.SetProp(
                "pair_max_dihedral",
                "unavailable" if match.max_dihedral_change is None
                else f"{match.max_dihedral_change:.1f}",
            )
            writer.write(tagged)
        writer.close()
        print(f"Wrote {out}")
        print(f"  discarded      {match.candidate_origin}")
        print(f"  representative {match.representative_origin}")
        print(f"  RMSD {match.rmsd:.4f}   corrected max dihedral "
              f"{'unavailable' if match.max_dihedral_change is None else f'{match.max_dihedral_change:.1f} deg'}")
        return 0
    print(f"No merged-away candidate with origin {origin!r}. Run without --inspect to list them.")
    return 1


def main() -> int:
    corpus = _corpus()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("molecule", help="a SMILES, or a name from corpus.json")
    # Named after the PRODUCTION settings they change. A generic
    # `--threshold` invites changing the energy window while believing you
    # changed the RMSD one; defaults come from production so this file
    # cannot drift from the thing it is diagnosing.
    parser.add_argument("--rmsd-threshold", type=float, default=DEFAULT_RMS_THRESHOLD)
    parser.add_argument("--energy-window", type=float, default=DEFAULT_ENERGY_WINDOW)
    parser.add_argument("--embeddings", type=int, default=DEFAULT_EMBEDDINGS_TO_TRY)
    parser.add_argument("--keep", type=int, default=DEFAULT_CONFORMERS_TO_KEEP)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--rows", type=int, default=12, help="discarded pairs to print")
    parser.add_argument("--inspect", metavar="ORIGIN", help='e.g. "seed=0 embedding=17"')
    parser.add_argument("--sdf", default="pair.sdf", help="where --inspect writes")
    args = parser.parse_args()

    smiles = corpus.get(args.molecule, args.molecule)
    label = args.molecule if args.molecule in corpus else smiles

    print(f"{label}")
    print(f"  {smiles}")
    print(f"  rmsd_threshold {args.rmsd_threshold} | energy_window {args.energy_window} | "
          f"keep {args.keep} | {args.seeds} seed(s) x {args.embeddings} embeddings")

    runs = [_one_seed(smiles, index * SEED_STRIDE, args) for index in range(args.seeds)]

    if args.inspect:
        return _inspect(runs, args.inspect, Path(args.sdf))

    # PER SEED IS THE AUTHORITATIVE VIEW: one seed is one production run.
    for run in runs:
        print(f"\n--- seed {run['seed']} " + "-" * 52)
        _print_funnel(run, args)
        _print_discarded(run, args.rows)

    if len(runs) > 1:
        pooled = distinct_conformers(
            [item for run in runs for item in run["retained"]],
            args.rmsd_threshold,
            args.energy_window,
        )
        mean = sum(run["shipped"] for run in runs) / len(runs)
        print(f"\n--- pooled across seeds " + "-" * 44)
        print("  SECONDARY, AND IT EXCEEDS PRODUCTION SEMANTICS: the application")
        print("  never pools seeds, so this cannot be read as a number of conformers")
        print("  production keeps or loses. It shows how much of the space one run")
        print("  misses, and nothing else.")
        print(f"  union across {len(runs)} seeds       {len(pooled):>6}")
        print(f"  mean distinct per seed        {mean:>6.1f}")
        print(f"  coverage                      {mean / len(pooled):>6.2f}"
              f"   1.00 = every run finds the whole discovered set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
