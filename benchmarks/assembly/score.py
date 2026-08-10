"""Scores a built assembly against RCSB's own generated one.

THIS IS A GATE, NOT A BENCHMARK. Every other check on the assembly
builder tests it against this project's own reading of the two formats,
which cannot catch a misreading. RCSB generates its assemblies from the
mmCIF `_pdbx_struct_oper_list`; we build ours from the PDB `REMARK 350
BIOMT` records. Two independent readings of the same deposited
annotation, so agreement means something.

## Match on identity, validate on coordinates

The key is `(residue name, residue number, insertion code, atom name,
altloc)` WITHIN a chain, and chains are paired by their composition --
never by their serialized id. RCSB may legitimately call a generated
chain `A` where we call it `B`, and failing on that would be a false
negative about naming rather than a finding about geometry. Coordinates
then CHECK the pairing rather than establish it, so two atoms that happen
to sit in the same place cannot be matched to each other.

## Precision is two measurements, not one

Source, builder and reference all write three decimals, so a systematic
sub-millianstrom transform error would hide entirely inside the rounding.
They are separated:

  transform      our UNROUNDED coordinates against RCSB's written ones
  serialisation  our written coordinates against our own unrounded ones

and the reported `max_deviation` is the third, plainly visible quantity:
written against written.

The scorer RE-DERIVES the transform rather than reading it out of the
manifest, which makes it a second and independent check: a mutated
builder is caught by the scorer's own arithmetic as well as by RCSB. The
consequence is that under `build.py --mutate` the two error columns are
mislabelled -- the scorer is unmutated, so the mutation lands in
`serialisation` rather than in `transform`. That only affects deliberately
corrupted runs, and it is left alone because the alternative is teaching
the scorer about mutations it should not know exist.

Measured on this corpus, the transform agreement is limited by the input
and not by us: the PDB states each matrix to SIX decimals where the mmCIF
carries ten (2OMF's 3-fold is `-0.866025` against `-0.8660254038`). At a
60 A coordinate that is ~3e-5 A, which is invisible except for atoms
sitting within that distance of a rounding boundary -- 115 of 2OMF's 8481
do, and differ in the last written decimal by exactly 0.001.

Usage:
    python score.py predictions_shipped.json
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

sys.path.insert(0, str(HERE.parents[1] / "src"))

from openchem.chem.pose_analysis import _cif_tokens  # noqa: E402
from openchem.chem.structure_assembly import compose, operator_transforms  # noqa: E402

#: Half of the last written decimal. Rounding to three places cannot move
#: a value further than this, so exceeding it means the serializer is
#: doing something other than rounding -- a truncation, a unit slip, a
#: format overflow. It is a definition, not a tuning knob.
SERIALISATION_TOLERANCE = 5.0e-4

#: Our unrounded coordinate against RCSB's written one. Two contributions,
#: both bounded rather than guessed:
#:   * RCSB's own write rounding, <= 5e-4;
#:   * the matrix precision gap, |dR|*|x| + |dt|. The PDB writes six
#:     decimals and the mmCIF ten, so |dR| <= 5e-7 and |dt| <= 5e-6;
#:     at |x| <= 200 A that is <= 1.1e-4.
#: 6e-4 covers both with room to spare. A transposed, mis-composed or
#: wrongly-scoped operator misses by whole angstroms, not by fractions of
#: the last decimal, so this bound is nowhere near the interesting range.
TRANSFORM_TOLERANCE = 6.0e-4

#: What a human reads: written against written. The sum of the two above.
COORDINATE_TOLERANCE = SERIALISATION_TOLERANCE + TRANSFORM_TOLERANCE


def _cif_atom_site_rows(text: str) -> list[dict[str, str]]:
    """The `_atom_site` loop of an RCSB assembly file, by column NAME.

    By name rather than by position because the column order is not
    guaranteed and reading it positionally is exactly the class of
    mistake this gate exists to catch.

    Tokenised with the project's own `_cif_tokens` rather than `split()`.
    A CIF QUOTES any value containing a prime, so a detergent's sugar
    atoms arrive as `"C1'"` -- and `split()` keeps the quotes, which made
    11 of 5I6X's atoms look like a composition mismatch when the only
    thing that differed was how the name was written.
    """
    lines = text.splitlines()
    columns: list[str] = []
    rows: list[dict[str, str]] = []
    reading = False
    for line in lines:
        if line.startswith("_atom_site."):
            columns.append(line.split(".", 1)[1].strip())
            reading = True
            continue
        if not reading:
            continue
        if line.startswith(("ATOM ", "HETATM")):
            fields = _cif_tokens(line)
            if len(fields) == len(columns):
                rows.append(dict(zip(columns, fields)))
        elif line.startswith("#") and rows:
            break
    return rows


def _reference_atoms(text: str) -> dict[str, dict[tuple, tuple[float, float, float]]]:
    """chain -> {identity key -> coordinates}, from RCSB's assembly."""
    out: dict[str, dict[tuple, tuple[float, float, float]]] = defaultdict(dict)
    for row in _cif_atom_site_rows(text):
        chain = row.get("auth_asym_id") or row["label_asym_id"]
        key = (
            row.get("auth_comp_id") or row["label_comp_id"],
            row.get("auth_seq_id") or row["label_seq_id"],
            "" if row.get("pdbx_PDB_ins_code", "?") in ("?", ".") else row["pdbx_PDB_ins_code"],
            row.get("auth_atom_id") or row["label_atom_id"],
            "" if row.get("label_alt_id", ".") in ("?", ".") else row["label_alt_id"],
        )
        out[chain][key] = (
            float(row["Cartn_x"]),
            float(row["Cartn_y"]),
            float(row["Cartn_z"]),
        )
    return dict(out)


def _pdb_atoms(text: str) -> dict[str, dict[tuple, tuple[float, float, float]]]:
    """chain -> {identity key -> coordinates}, from a PDB file."""
    out: dict[str, dict[tuple, tuple[float, float, float]]] = defaultdict(dict)
    for line in text.splitlines():
        if not line.startswith(("ATOM  ", "HETATM")):
            continue
        key = (
            line[17:20].strip(),
            line[22:26].strip(),
            line[26].strip(),
            line[12:16].strip(),
            line[16].strip(),
        )
        out[line[21]][key] = (
            float(line[30:38]),
            float(line[38:46]),
            float(line[46:54]),
        )
    return dict(out)


def _centroid(atoms: dict) -> tuple[float, float, float]:
    n = len(atoms)
    return tuple(sum(xyz[i] for xyz in atoms.values()) / n for i in range(3))


def _pair_chains(
    mine: dict[str, dict], theirs: dict[str, dict], subset: bool = False
) -> tuple[list[tuple[str, str]], str]:
    """Pair our chains to theirs by COMPOSITION, then by position.

    Composition alone cannot separate the copies of a homo-oligomer --
    which is every structure in this corpus -- so within a group of
    identical compositions each of our chains takes the nearest unused
    reference centroid. That is position BREAKING A TIE between
    candidates identity has already narrowed, never establishing the
    match, and the per-atom check afterwards is what confirms it: a
    mispairing puts whole chains angstroms apart and fails loudly.

    Centroids rather than the exhaustive minimax the first version used.
    That version refused above six identical chains because the search is
    factorial, which was fine for a corpus of dimers and trimers and is
    not for 1A34's assembly 6 -- 120 chains, 15 copies of each
    composition. 15! is 1.3e12.

    `subset` is for an entry scored against a LARGER reference: 1A34's
    assembly 6 is 15 of the 60 operators its assembly 1 applies, and RCSB
    pre-generates only assembly 1. Every chain of ours must find a
    partner; theirs may have many left over.
    """
    def composition(atoms: dict) -> tuple:
        return tuple(sorted(atoms))

    ours: dict[tuple, list[str]] = defaultdict(list)
    for chain, atoms in mine.items():
        ours[composition(atoms)].append(chain)
    reference: dict[tuple, list[str]] = defaultdict(list)
    for chain, atoms in theirs.items():
        reference[composition(atoms)].append(chain)

    our_counts = Counter({k: len(v) for k, v in ours.items()})
    their_counts = Counter({k: len(v) for k, v in reference.items()})
    if subset:
        short = [k for k, n in our_counts.items() if their_counts.get(k, 0) < n]
        if short:
            return [], (
                f"{len(short)} chain composition(s) appear more often here than in "
                f"the reference, so this is not a subset of it"
            )
    elif our_counts != their_counts:
        return [], (
            f"chain composition multiset differs: {len(mine)} chains here "
            f"against {len(theirs)} there"
        )

    pairs: list[tuple[str, str]] = []
    for comp, our_chains in ours.items():
        available = list(reference[comp])
        centroids = {chain: _centroid(theirs[chain]) for chain in available}
        for our_chain in our_chains:
            here = _centroid(mine[our_chain])
            nearest = min(
                available,
                key=lambda c: sum((p - q) ** 2 for p, q in zip(here, centroids[c])),
            )
            available.remove(nearest)
            pairs.append((our_chain, nearest))
    return pairs, ""


def _atoms(text: str, source_format: str) -> dict:
    """chain -> {identity key -> coordinates}, whichever format it is in."""
    return _pdb_atoms(text) if source_format == "pdb" else _reference_atoms(text)


def _unrounded(
    source_text: str, source_format: str, instances: list[list[str]], assembly_id: str
) -> dict:
    """chain -> {key -> coordinates}, recomputed WITHOUT serialization.

    Deliberately re-derived here rather than carried through the manifest:
    it means the written output is checked against a freshly applied
    transform, so a serializer that drops a digit is visible as itself
    rather than absorbed into the comparison.
    """
    transforms = operator_transforms(source_text, source_format, assembly_id)
    source = _atoms(source_text, source_format)
    out: dict[str, dict[tuple, tuple[float, float, float]]] = {}
    for source_chain, operator_id, generated in instances:
        # A product expression gives a COMPOSED placement, which the
        # manifest records joined with `x` -- `X0x1`. Recomposed here from
        # the individual operators rather than looked up, right-to-left as
        # the format defines, so the scorer's arithmetic is a second
        # opinion on the builder's composition and not a copy of it.
        transform = None
        for part in reversed(operator_id.split("x")):
            operator = transforms[part]
            transform = operator if transform is None else compose(transform, operator)
        assert transform is not None
        out[generated] = {
            key: transform.apply(*xyz)
            for key, xyz in source.get(source_chain, {}).items()
        }
    return out


def _score_one(entry: dict, record: dict) -> dict:
    pdb_id, assembly_id = entry["pdb_id"], entry["assembly_id"]
    case_id = f"{pdb_id}-a{assembly_id}"
    reference_id = entry.get("reference_assembly_id", assembly_id)
    subset = entry.get("reference_mode") == "subset"
    expect = entry["expect"]

    if expect == "refused":
        if record["ok"]:
            return {"pass": False, "note": "built, but the corpus expects a refusal"}
        reference = _cif_atom_site_rows(
            (CACHE / f"{pdb_id}-assembly{reference_id}.cif").read_text(errors="ignore")
        )
        stated = entry.get("expect_atoms")
        # The refusal names the count it refuses on. RCSB's file is the
        # only thing that can say whether that count is right, and a
        # refusal branch nothing external checks is one that can drift.
        matches = str(len(reference)) in record["failure_reason"].replace(",", "")
        return {
            "pass": bool(matches and (stated is None or stated == len(reference))),
            "note": f"refused; RCSB's own assembly has {len(reference):,} atoms",
            "reference_atoms": len(reference),
        }

    if not record["ok"]:
        return {"pass": False, "note": f"refused: {record['failure_reason']}"}

    suffix = "pdb" if SOURCE_FORMAT == "pdb" else "cif"
    built = (CACHE / f"built_{LABEL}" / f"{case_id}.{suffix}").read_text(errors="ignore")
    source = (CACHE / f"{pdb_id}.{suffix}").read_text(errors="ignore")
    mine = _atoms(built, SOURCE_FORMAT)
    theirs = _reference_atoms(
        (CACHE / f"{pdb_id}-assembly{reference_id}.cif").read_text(errors="ignore")
    )

    n_mine = sum(len(v) for v in mine.values())
    n_theirs = sum(len(v) for v in theirs.values())
    result = {
        "atoms": n_mine,
        "reference_atoms": n_theirs,
        "chains": len(mine),
        "reference_chains": len(theirs),
    }
    if subset:
        # A subset entry is scored against a LARGER assembly, so equality
        # is the wrong test. What must hold is that every atom of ours is
        # in theirs, which the per-atom check below establishes, and that
        # we produced the placements the expression calls for.
        if n_mine >= n_theirs:
            return {**result, "pass": False, "note": "not smaller than its reference"}
    elif n_mine != n_theirs:
        return {**result, "pass": False, "note": "atom count differs"}

    pairs, problem = _pair_chains(mine, theirs, subset=subset)
    if problem:
        return {**result, "pass": False, "note": problem}

    unrounded = _unrounded(source, SOURCE_FORMAT, record["instances"], assembly_id)

    worst = worst_transform = worst_serialisation = 0.0
    square_sum = 0.0
    exact = 0
    for ours_chain, theirs_chain in pairs:
        a, b = mine[ours_chain], theirs[theirs_chain]
        raw = unrounded.get(ours_chain, {})
        for key, written in a.items():
            reference_xyz = b[key]
            deviation = max(abs(p - q) for p, q in zip(written, reference_xyz))
            worst = max(worst, deviation)
            square_sum += sum((p - q) ** 2 for p, q in zip(written, reference_xyz))
            if deviation == 0.0:
                exact += 1
            if key in raw:
                worst_transform = max(
                    worst_transform,
                    max(abs(p - q) for p, q in zip(raw[key], reference_xyz)),
                )
                worst_serialisation = max(
                    worst_serialisation,
                    max(abs(p - q) for p, q in zip(raw[key], written)),
                )

    result.update(
        {
            "max_deviation": worst,
            "transform_error": worst_transform,
            "serialisation_error": worst_serialisation,
            "rmsd": math.sqrt(square_sum / n_mine) if n_mine else 0.0,
            "exact_atoms": exact,
        }
    )
    result["pass"] = (
        worst <= COORDINATE_TOLERANCE
        and worst_transform <= TRANSFORM_TOLERANCE
        and worst_serialisation <= SERIALISATION_TOLERANCE
    )
    return result


LABEL = ""
SOURCE_FORMAT = "pdb"


def main() -> int:
    global LABEL, SOURCE_FORMAT
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    if payload["corpus_version"] != corpus["corpus_version"]:
        print(
            f"predictions were built against corpus v{payload['corpus_version']}, "
            f"this is v{corpus['corpus_version']} -- rebuild rather than mis-score",
            file=sys.stderr,
        )
        return 2
    LABEL = payload["label"]
    SOURCE_FORMAT = payload.get("source_format", "pdb")

    print(f"label={payload['label']}  built FROM {SOURCE_FORMAT}  "
          f"mutation={payload['mutation']}  built={payload['environment']['built']}")
    print(
        f"{'case':<12} {'atoms':>9} {'chains':>7} {'max dev':>9} "
        f"{'transform':>10} {'serial':>8} {'rmsd':>8}  verdict"
    )
    failures = skipped = 0
    for entry in corpus["structures"]:
        case_id = f"{entry['pdb_id']}-a{entry['assembly_id']}"
        allowed = entry.get("source_formats")
        if allowed and SOURCE_FORMAT not in allowed:
            print(f"{case_id:<12} {'-':>9} {'-':>7} not buildable from {SOURCE_FORMAT}")
            skipped += 1
            continue
        record = payload["predictions"].get(case_id)
        if record is None:
            print(f"{case_id:<12} not in predictions")
            failures += 1
            continue
        scored = _score_one(entry, record)
        if not scored["pass"]:
            failures += 1
        if "max_deviation" in scored:
            print(
                f"{case_id:<12} {scored['atoms']:>9,} {scored['chains']:>7} "
                f"{scored['max_deviation']:>9.4f} {scored['transform_error']:>10.6f} "
                f"{scored['serialisation_error']:>8.6f} {scored['rmsd']:>8.5f}  "
                f"{'PASS' if scored['pass'] else 'FAIL'}"
            )
        else:
            print(
                f"{case_id:<12} {'-':>9} {'-':>7} {'-':>9} {'-':>10} {'-':>8} "
                f"{'-':>8}  {'PASS' if scored['pass'] else 'FAIL'}  {scored['note']}"
            )

    print()
    scored = len(corpus["structures"]) - skipped
    tail = f" ({skipped} not applicable to {SOURCE_FORMAT})" if skipped else ""
    if failures:
        print(f"{failures} of {scored} FAILED{tail}")
    else:
        print(f"all {scored} agree with RCSB{tail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
