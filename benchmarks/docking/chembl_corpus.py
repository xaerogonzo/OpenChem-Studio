"""Stage 0 of the Within-Assay Docking Ranking Benchmark: build the oracle.

    uv run --no-sync python benchmarks/docking/chembl_corpus.py
    uv run --no-sync python benchmarks/docking/chembl_corpus.py --presence

**THIS IS NOT CASF.** CASF-2016 decouples scoring from docking over 285
complexes and 57 targets; this assembles, per catalogued receptor, sets of
compounds measured IN ONE ASSAY, so that a ranking of them means something.
Its numbers are not comparable to `[source:su2019]`'s pooled ~0.6 or
`[source:nguyen2020]`'s 0.498 +/- 0.026, and `rank_report.py` prints that
rather than leaving it here.

**WHY THIS EXISTS AT ALL.** `docs/ROADMAP.md` route 2 shipped a rescoring
axis whose acceptance criterion -- rank correlation against MEASURED
affinities -- was recorded 2026-09-03 as unmeasurable, because every route to
a set carrying them was closed: the PDBbind hosts, CASF-2016's tarball,
PDBbind+ behind an account, Binding MOAD's domain now serving a commercial
antibody catalogue, and RCSB's own `rcsb_binding_affinity` too sparse and
assay-heterogeneous to rank with (104 records for 4EY7 spanning Kd 8 nM to
IC50 7120 nM for ONE ligand). The roadmap named the reopener itself -- "a
curated affinity set assembled from BindingDB/ChEMBL for targets already in
the library" -- and ChEMBL is reachable with no account.

**ONE ASSAY IS THE WHOLE POINT.** A 4000-fold spread across assays is not a
ranking oracle. Within one assay, one endpoint and one laboratory, an ordering
is a real ordering. That single restriction is what this module exists to
enforce, and most of the rest is bookkeeping around it.

## The join is PINNED, and SIFTS is the verifier

A UniProt accession is not a construct. Mutations, truncations, fusions,
thermostabilisation and functional state all break "same accession implies
same target" -- and `ReceptorEntry` already carries `state` and `caveat`
because this project calls docking an agonist into an inactive structure "a
real (and easy) mistake". A ChEMBL antagonist series against an active-state
structure is that mistake at series scale.

So `JOIN` below is a table with a reason per row, in `receptor_library.py`'s
own doctrine ("EVERY FIELD BELOW CAME FROM THE RCSB API, NOT FROM
RECOLLECTION"), and `verify_join` FAILS on disagreement rather than resolving
anything. That turns the silent cases into documented rows:

    5C1M / 4DKL   P42866 is MOUSE mu-opioid. A human-only filter returns
                  SILENCE, not an error -- and the mouse target carries 727
                  Ki values of its own, so the exact-organism rule is not a
                  principle here, it is what the data supports.
    4M48          Q7K4Y6 is the DROSOPHILA dopamine transporter. No ChEMBL
                  target at all.
    5KIR          COX-2 has 27 Ki values, because that endpoint is measured
                  as IC50. A Ki-only rule silently refuses an enzyme class.
    4 of the 8    the deposit carries a SECOND UniProt for its
    below         crystallisation fusion -- T4 lysozyme P00720 in 3PBL, 2RH1
                  and 3EML, cytochrome b562 P0ABE7 in 6WGT, flavodoxin
                  P00323 in 5TGZ. Each has ChEMBL targets of its own, so an
                  unfiltered "take the accession with the most activities"
                  join can return a chaperone's affinity data as the
                  receptor's.

## What this stage costs

Network only, minutes, and NO Vina. That is deliberate: the corpus and its
drop funnel are evidence on their own, and every physicochemical baseline is
computed HERE -- before a single search runs -- so the size-confound check
that decides whether the expensive stage is worth starting is free.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openchem.chem.receptor_library import find
from openchem.domain.affinity_range import SEPARATION_ALPHA
from openchem.net import open_url

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SERIES_DIR = DATA / "series"

CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"
SIFTS_API = "https://www.ebi.ac.uk/pdbe/api/mappings/uniprot"

#: Bumped whenever a stored series changes shape. `rank_report.py` refuses a
#: corpus whose version differs from what the run recorded, so a re-fetch
#: cannot silently change the numbers under a finished measurement.
SCHEMA_VERSION = 1

#: One endpoint per series, never mixed. Ki is the PRIMARY stratum; an IC50
#: series is admissible and is reported SEPARATELY, because within one assay
#: an IC50 ordering is a valid ordering while a Ki and an IC50 are not one
#: quantity. Nothing pools them into a single correlation.
PRIMARY_ENDPOINT = "Ki"

#: ChEMBL's own unit for these endpoints. Anything else is REFUSED rather than
#: converted -- a coerced unit is how a nanomolar and a micromolar value end
#: up in one ordering.
REQUIRED_UNITS = "nM"

#: ChEMBL's maximum page size. The fetch asserts the collected count against
#: `page_meta.total_count`, because a truncated page silently SHORTENS a
#: series and a shorter series is a different ordering.
PAGE = 1000

TIMEOUT_S = 60.0


def series_minimum(alpha: float = SEPARATION_ALPHA) -> int:
    """The smallest series in which a PERFECT ordering would be significant.

    DERIVED, NOT TYPED, and from the same alpha `affinity_range.py` uses, so
    the two conventions cannot drift. Under the null that the docking order is
    unrelated to the measured one, all n! orderings are equally likely and two
    of them are perfect -- one in each direction, because this benchmark does
    not fix the direction in advance. So the exact two-sided rate of the
    extreme outcome is 2/n!:

        n = 3   0.3333   refused
        n = 4   0.0833   refused
        n = 5   0.0167   the smallest that clears alpha = 0.05

    Same shape as `affinity_range.minimum_replicates()`, which solves the
    rank-sum version of the identical question.

    **EXACT ONLY WITH NO TIES.** Tied potencies share midranks and the
    permutation argument above stops counting distinct orderings, which is why
    `rank_report.py` prints the distinct-value count beside every rho rather
    than trusting n.
    """
    n = 2
    while 2 / math.factorial(n) > alpha:
        n += 1
        if n > 20:  # unreachable for any sane alpha; refuses to loop forever
            raise ValueError(f"no series size satisfies alpha={alpha}")
    return n


MIN_SERIES = series_minimum()


@dataclass(frozen=True)
class JoinRow:
    """One catalogued receptor, and the ChEMBL target it may be joined to.

    `organism_match` is a STRATUM, not a switch. Every row shipped today is
    `exact` -- the structure's own species has enough data, mouse mu-opioid
    included -- so no ortholog fallback is implemented rather than written and
    left unreachable. A future row needing one declares `ortholog` here and
    `rank_report.py` reports it separately; it never enters the primary
    headline.
    """

    pdb_id: str
    uniprot: str
    chembl_target_id: str
    organism: str
    organism_match: str
    why: str


#: **EVERY FIELD READ FROM THE APIs, NOT FROM RECOLLECTION**, and re-checked by
#: `verify_join` on every build. Eight targets chosen for FAMILY SPREAD rather
#: than data volume: eight from one family would measure one pocket eight
#: times.
JOIN = (
    JoinRow(
        pdb_id="5C1M", uniprot="P42866", chembl_target_id="CHEMBL2858",
        organism="Mus musculus", organism_match="exact",
        why="Opioid. The receptor the ranking complaint was reported against. "
            "The deposit is MOUSE mu-opioid and so is the ChEMBL target, which "
            "carries 727 '=' Ki values -- so no ortholog substitution is needed "
            "for the one case that most tempted it. Deposit state is 'active'.",
    ),
    JoinRow(
        pdb_id="6WGT", uniprot="P28223", chembl_target_id="CHEMBL224",
        organism="Homo sapiens", organism_match="exact",
        why="Serotonergic. SIFTS also returns P0ABE7 (cytochrome b562, the BRIL "
            "crystallisation fusion), which has ChEMBL targets of its own -- the "
            "receptor chain is the one named here.",
    ),
    JoinRow(
        pdb_id="3PBL", uniprot="P35462", chembl_target_id="CHEMBL234",
        organism="Homo sapiens", organism_match="exact",
        why="Dopaminergic. SIFTS also returns P00720 (T4 lysozyme fusion). "
            "Deposit state is 'inactive', so an agonist series against it is the "
            "mistake `receptor_library.py` names; the assay description travels "
            "with each series so a reader can see which was measured.",
    ),
    JoinRow(
        pdb_id="2RH1", uniprot="P07550", chembl_target_id="CHEMBL210",
        organism="Homo sapiens", organism_match="exact",
        why="Adrenergic. SIFTS also returns P00720 (T4 lysozyme fusion). The "
            "smallest Ki pool of the eight at 796, which is why it is here: a "
            "corpus of only data-rich targets would not show what the funnel "
            "does to a thin one.",
    ),
    JoinRow(
        pdb_id="5TGZ", uniprot="P21554", chembl_target_id="CHEMBL218",
        organism="Homo sapiens", organism_match="exact",
        why="Cannabinoid. SIFTS also returns P00323 (flavodoxin, FLAV_NITV2) -- "
            "a THIRD distinct fusion partner, which is why the rule here is "
            "'the pinned chain' rather than a blocklist of two accessions.",
    ),
    JoinRow(
        pdb_id="5I6X", uniprot="P31645", chembl_target_id="CHEMBL228",
        organism="Homo sapiens", organism_match="exact",
        why="Transporter, and not a GPCR -- the family spread is the reason it "
            "is in the corpus. One SIFTS accession, no fusion.",
    ),
    JoinRow(
        pdb_id="3HS4", uniprot="P00918", chembl_target_id="CHEMBL205",
        organism="Homo sapiens", organism_match="exact",
        why="A METALLOENZYME, and the row that dictates this benchmark's "
            "receptor preparation. Its sulfonamide series binds THROUGH the "
            "catalytic zinc, so `strip_cofactors` must stay False -- see "
            "rank_power.py's PREP. 11050 Ki values, the largest pool here.",
    ),
    JoinRow(
        pdb_id="3EML", uniprot="P29274", chembl_target_id="CHEMBL251",
        organism="Homo sapiens", organism_match="exact",
        why="Adenosine A2a. SIFTS also returns P00720 (T4 lysozyme fusion). One "
            "of the two receptors whose miss in the docking-power benchmark was "
            "a SCORING failure rather than a search failure, which makes it "
            "worth having where scoring is the subject.",
    ),
)


def _get(url: str) -> dict[str, Any]:
    with open_url(url, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_join(row: JoinRow) -> list[str]:
    """Check the pinned row against SIFTS and ChEMBL. Returns disagreements.

    A VERIFIER, NOT A RESOLVER. If SIFTS stops mapping this deposit to this
    accession, or ChEMBL's target changes organism, that is a fact worth
    failing on -- not something to route around by picking whatever has the
    most activities, which is the move that returns a crystallisation
    chaperone's data as the receptor's.
    """
    problems: list[str] = []
    try:
        mapping = _get(f"{SIFTS_API}/{row.pdb_id.lower()}")
        accessions = set(mapping[row.pdb_id.lower()]["UniProt"].keys())
    except Exception as exc:  # noqa: BLE001 - reported, never silently accepted
        return [f"{row.pdb_id}: SIFTS lookup failed ({exc})"]
    if row.uniprot not in accessions:
        problems.append(
            f"{row.pdb_id}: pinned {row.uniprot} is not in SIFTS {sorted(accessions)}"
        )
    try:
        target = _get(f"{CHEMBL_API}/target/{row.chembl_target_id}.json")
    except Exception as exc:  # noqa: BLE001
        return problems + [f"{row.pdb_id}: ChEMBL target lookup failed ({exc})"]
    if (target.get("organism") or "") != row.organism:
        problems.append(
            f"{row.pdb_id}: {row.chembl_target_id} organism is "
            f"{target.get('organism')!r}, pinned {row.organism!r}"
        )
    components = {c.get("accession") for c in target.get("target_components", [])}
    if row.uniprot not in components:
        problems.append(
            f"{row.pdb_id}: {row.chembl_target_id} does not carry {row.uniprot} "
            f"(has {sorted(c for c in components if c)})"
        )
    return problems


def fetch_activities(target_chembl_id: str, endpoint: str = PRIMARY_ENDPOINT) -> list[dict]:
    """Every '=' activity of one endpoint carrying a pChEMBL value.

    **THE COUNT IS ASSERTED AGAINST `total_count`.** ChEMBL paginates, and a
    page silently dropped shortens a series -- which is not a smaller sample
    of the same ordering, it is a DIFFERENT ordering. Failing closed here is
    cheaper than a rho computed over an arbitrary subset that looks fine.
    """
    query = urllib.parse.urlencode(
        {
            "target_chembl_id": target_chembl_id,
            "standard_type": endpoint,
            "standard_relation": "=",
            "pchembl_value__isnull": "false",
            "limit": PAGE,
        }
    )
    url = f"{CHEMBL_API}/activity.json?{query}"
    rows: list[dict] = []
    expected: int | None = None
    while url:
        payload = _get(url)
        meta = payload.get("page_meta", {})
        if expected is None:
            expected = int(meta.get("total_count", 0))
        rows.extend(payload.get("activities", []))
        nxt = meta.get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else ""
    if expected is not None and len(rows) != expected:
        raise RuntimeError(
            f"{target_chembl_id}: collected {len(rows)} activities but ChEMBL "
            f"reports {expected}. A truncated fetch changes the ordering, so "
            "this refuses rather than scoring a subset."
        )
    return rows


@dataclass(frozen=True)
class Ligand:
    """One compound in one series, with everything an audit needs.

    `canonical_smiles` is stored EXACTLY as ChEMBL gave it and never
    re-canonicalised in place -- a silent transformation of the stored input
    is how a corpus stops being reproducible from its source. The InChIKey is
    computed locally instead, so the presence lookup's key is auditable.

    The physicochemical fields are computed from the SAME SMILES the docking
    will embed, so a baseline and a docking score describe one molecule.
    """

    molecule_chembl_id: str
    activity_id: int
    canonical_smiles: str
    inchikey: str
    standard_value: float
    standard_units: str
    pchembl_value: float
    heavy_atoms: int
    mol_weight: float
    clogp: float
    tpsa: float
    #: How many rows this compound had in this assay, and how far they spread.
    #: Kept because a compound measured twice at 100 nM and 10 uM is a fact
    #: about the assay, not noise to average away silently. Median is used; no
    #: threshold refuses on the spread.
    n_rows: int
    row_spread_pchembl: float


def _describe(smiles: str) -> dict[str, Any] | None:
    """The free baselines, and the InChIKey. None when RDKit refuses it."""
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return {
        "inchikey": Chem.MolToInchiKey(mol),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "mol_weight": Descriptors.MolWt(mol),
        "clogp": Crippen.MolLogP(mol),
        "tpsa": rdMolDescriptors.CalcTPSA(mol),
    }


def build_series(row: JoinRow, activities: list[dict], endpoint: str) -> tuple[list[dict], dict[str, int]]:
    """Group one target's activities into single-assay series, and say what
    was dropped and why.

    **THE FUNNEL IS AN OUTPUT, NOT A LOG LINE.** "How far does ChEMBL get you"
    is a permanent, citable answer that costs no Vina time, and it is the
    result if nothing else survives.
    """
    from collections import defaultdict

    funnel: dict[str, int] = defaultdict(int)
    by_assay: dict[str, list[dict]] = defaultdict(list)

    for activity in activities:
        funnel["rows_fetched"] += 1
        if activity.get("data_validity_comment"):
            funnel["dropped_data_validity"] += 1
            continue
        if activity.get("potential_duplicate"):
            funnel["dropped_potential_duplicate"] += 1
            continue
        if (activity.get("standard_units") or "") != REQUIRED_UNITS:
            funnel["dropped_wrong_units"] += 1
            continue
        smiles = activity.get("canonical_smiles") or ""
        if not smiles:
            funnel["dropped_no_smiles"] += 1
            continue
        if "." in smiles:
            # REFUSED, never split. Taking the largest fragment is a silent
            # transformation, and a salt is not the thing that was measured.
            funnel["dropped_multi_component"] += 1
            continue
        assay = activity.get("assay_chembl_id")
        if not assay:
            funnel["dropped_no_assay"] += 1
            continue
        by_assay[assay].append(activity)

    series: list[dict] = []
    for assay, rows in sorted(by_assay.items()):
        by_molecule: dict[str, list[dict]] = defaultdict(list)
        for activity in rows:
            by_molecule[activity["molecule_chembl_id"]].append(activity)

        ligands: list[Ligand] = []
        for molecule_id, molecule_rows in sorted(by_molecule.items()):
            values = sorted(float(r["pchembl_value"]) for r in molecule_rows)
            representative = molecule_rows[0]
            described = _describe(representative["canonical_smiles"])
            if described is None:
                funnel["dropped_smiles_did_not_parse"] += 1
                continue
            ligands.append(
                Ligand(
                    molecule_chembl_id=molecule_id,
                    activity_id=int(representative["activity_id"]),
                    canonical_smiles=representative["canonical_smiles"],
                    standard_value=float(representative["standard_value"]),
                    standard_units=representative["standard_units"],
                    pchembl_value=values[len(values) // 2],
                    n_rows=len(values),
                    row_spread_pchembl=values[-1] - values[0],
                    **described,
                )
            )

        if len(ligands) < MIN_SERIES:
            funnel["series_too_small"] += 1
            continue
        potencies = [ligand.pchembl_value for ligand in ligands]
        if len({round(p, 12) for p in potencies}) < 2:
            # DEFINEDNESS, not a quality bar: zero variance makes Spearman
            # undefined and the shipped one correctly returns None.
            funnel["series_no_variation"] += 1
            continue

        first = rows[0]
        series.append(
            {
                "schema_version": SCHEMA_VERSION,
                "series_id": f"{row.pdb_id}_{assay}",
                "grouping": "assay",
                "endpoint": endpoint,
                "activity_relation": "=",
                "activity_units": REQUIRED_UNITS,
                "organism_match": row.organism_match,
                "pdb_id": row.pdb_id,
                "uniprot": row.uniprot,
                "chembl_target_id": row.chembl_target_id,
                "target_organism": row.organism,
                "join_reason": row.why,
                "assay_chembl_id": assay,
                "assay_description": first.get("assay_description") or "",
                "assay_type": first.get("assay_type") or "",
                "bao_label": first.get("bao_label") or "",
                "document_chembl_id": first.get("document_chembl_id") or "",
                "document_year": first.get("document_year"),
                "document_journal": first.get("document_journal") or "",
                "n_ligands": len(ligands),
                "span_pchembl": max(potencies) - min(potencies),
                "distinct_pchembl": len({round(p, 12) for p in potencies}),
                "ligands": [ligand.__dict__ for ligand in ligands],
            }
        )
        funnel["series_kept"] += 1

    return series, dict(funnel)


def free_baselines(series: dict) -> dict[str, float | None]:
    """The physicochemical correlations, computed at BUILD time.

    They cost nothing here and they decide whether the expensive stage is
    worth starting. This project has already shipped an endpoint that turned
    out to be molecular size (r = +0.98), and a series where potency tracks
    heavy-atom count almost perfectly cannot DISCRIMINATE between a docking
    score that ranks and one that has merely learned size -- the control is
    present and can never fire.

    So `main` prints them and names the size-decoupled series, and
    `rank_power.py` is pointed at those first: it is how Vina time gets spent
    where the control can actually say no.
    """
    from _stats import spearman

    potency = [ligand["pchembl_value"] for ligand in series["ligands"]]
    return {
        name: spearman([ligand[name] for ligand in series["ligands"]], potency)
        for name in ("heavy_atoms", "mol_weight", "clogp", "tpsa")
    }


#: Below this, potency and heavy-atom count are loose enough that a docking
#: score CAN be distinguished from a size proxy on that series.
#:
#: A REPORTING SPLIT, NOT AN ADMISSION RULE -- every series is kept and every
#: series is measured. This only decides which ones are worth the Vina time
#: first, and a series above it still appears in the report with its baseline
#: beside it so a reader can see the control could not fire there.
SIZE_DECOUPLED_BELOW = 0.3


def is_size_decoupled(heavy_atom_rho: float | None) -> bool:
    """Can a docking score be told apart from a size proxy on this series?

    **`None` IS THE STRONGEST DECOUPLING, NOT A MISSING VALUE**, and reading it
    as missing was this function's first bug. `spearman` returns None on zero
    variance in EITHER column; the potency column is guaranteed at least two
    distinct values by the corpus filter, so None here means the SIZE column is
    constant -- every compound in the series has the same heavy-atom count.
    Potency cannot be explained by a quantity that does not vary, so such a
    series is the IDEAL place to spend Vina time, and an `is not None` guard
    excludes exactly those.

    Real rather than hypothetical: `5C1M_CHEMBL758126` is six compounds
    identical in heavy atoms, molecular weight, cLogP and TPSA across a 1.99
    log potency span -- an isomer series, where nothing physicochemical can be
    the answer and only geometry can.

    A REPORTING SPLIT, NOT AN ADMISSION RULE. Every series is kept and
    measured; this decides only which are worth docking first.
    """
    return heavy_atom_rho is None or abs(heavy_atom_rho) < SIZE_DECOUPLED_BELOW


#: The largest series worth docking, in ligands.
#:
#: PURELY A COST BOUND, and it is what keeps the selection from needing to
#: take a SUBSET of a series -- which would be a second, undeclared choice
#: inside an already-curated one. Series are selected whole or not at all.
#: At six replicates a 14-ligand series is 84 searches.
MAX_LIGANDS_FOR_DOCKING = 14

#: How many series per target reach Stage 1.
SERIES_PER_TARGET = 2


def select_for_docking(all_series: list[dict], baselines: dict[str, dict]) -> list[str]:
    """Which series Stage 1 docks, decided ONCE and written into the manifest.

    The corpus holds ~1600 series and docking them all is not affordable, so a
    subset is chosen -- which makes this a **curated benchmark, not a random
    sample**, and the manifest says so rather than letting a reader assume
    otherwise.

    The rule, declared in full because a selection rule invented after seeing
    a result is the result:

        1  size-decoupled only, so the baseline control CAN fire
        2  n between the derived minimum and MAX_LIGANDS_FOR_DOCKING, so no
           series is subsetted and none is unaffordable
        3  per target, the SERIES_PER_TARGET with the most ligands
        4  ties broken by series_id, so the choice is deterministic

    **SORTED BY LIGAND COUNT, NOT BY POTENCY SPAN**, and that is the one
    judgement here worth arguing about. A wide span is easier to rank, so
    selecting on it would flatter every number that follows; the ligand count
    selects for statistical POWER instead, which is a property of the test
    rather than of how favourable its answer will be.
    """
    chosen: list[str] = []
    for row in JOIN:
        candidates = [
            series
            for series in all_series
            if series["pdb_id"] == row.pdb_id
            and MIN_SERIES <= series["n_ligands"] <= MAX_LIGANDS_FOR_DOCKING
            and is_size_decoupled(baselines[series["series_id"]]["heavy_atoms"])
        ]
        candidates.sort(key=lambda s: (-s["n_ligands"], s["series_id"]))
        chosen += [series["series_id"] for series in candidates[:SERIES_PER_TARGET]]
    return chosen


def write_corpus(
    all_series: list[dict],
    funnels: dict[str, dict],
    endpoint: str,
    selection: list[str] | None = None,
) -> Path:
    """Series to `data/series/<id>.json`, plus the frozen manifest.

    **THE MANIFEST IS FROZEN BEFORE ANY DOCKING**, which is the difference
    between a curated benchmark and a tuned one. The eight targets were chosen
    after sweeping 21, so this IS a curated selection and the manifest says so;
    what it must not become is a selection revised after seeing a rho.

        discover -> curate -> FREEZE -> measure

    `rank_report.py` refuses a corpus whose `schema_version` or ChEMBL release
    differs from the one the run recorded.
    """
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    for series in all_series:
        (SERIES_DIR / f"{series['series_id']}.json").write_text(
            json.dumps(series, indent=1), encoding="utf-8"
        )
    release = _get(f"{CHEMBL_API}/status.json").get("chembl_db_version", "unknown")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "chembl_release": release,
        "chembl_api": CHEMBL_API,
        "endpoint": endpoint,
        "relation": "=",
        "units": REQUIRED_UNITS,
        "series_minimum": MIN_SERIES,
        "series_minimum_derived_from_alpha": SEPARATION_ALPHA,
        "selection_rule_version": (
            "1: family spread over the 21 catalogued targets that reach a "
            "ChEMBL target with Ki data; pinned join with SIFTS as verifier; "
            "one assay and one endpoint per series; n >= the derived minimum; "
            "at least two distinct potencies"
        ),
        "curated_not_random": True,
        "docking_selection_rule": (
            f"size-decoupled series with {MIN_SERIES} <= n <= "
            f"{MAX_LIGANDS_FOR_DOCKING}; per target the {SERIES_PER_TARGET} with "
            "the most ligands, ties by series_id. Sorted by LIGAND COUNT and "
            "not by potency span: a wide span is easier to rank, so selecting "
            "on it would flatter the result, where the count selects for "
            "statistical power."
        ),
        #: FROZEN BEFORE ANY DOCKING. `rank_power.py` docks these and nothing
        #: else, and `rank_report.py` reports against this list -- so a series
        #: cannot be added or dropped after a rho has been seen.
        "docking_selection": list(selection or []),
        "targets": [_target_record(row, funnels) for row in JOIN],
        "series": sorted(series["series_id"] for series in all_series),
    }
    path = DATA / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return path


def _target_record(row: JoinRow, funnels: dict[str, dict]) -> dict[str, Any]:
    """One manifest row, carrying the receptor's own state and caveat.

    `state` and `caveat` travel with the join because they are what says
    whether an antagonist series belongs against this deposit at all -- an
    accession match does not.
    """
    entry = find(row.pdb_id)
    return {
        "pdb_id": row.pdb_id,
        "uniprot": row.uniprot,
        "chembl_target_id": row.chembl_target_id,
        "organism": row.organism,
        "organism_match": row.organism_match,
        "why": row.why,
        "receptor_state": getattr(entry, "state", ""),
        "receptor_caveat": getattr(entry, "caveat", ""),
        "ligand_code": getattr(entry, "ligand_code", ""),
        "funnel": funnels.get(row.pdb_id, {}),
    }


def _rho(value: float | None) -> str:
    return "  n/a " if value is None else f"{value:+6.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=PRIMARY_ENDPOINT)
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument(
        "--presence",
        action="store_true",
        help="resolve the PDB chemical-component leakage bound for every "
        "compound in the built corpus, and cache it",
    )
    args = parser.parse_args()

    wanted = {t.upper() for t in args.targets} if args.targets else None
    rows = [row for row in JOIN if wanted is None or row.pdb_id in wanted]
    print(__doc__.split("\n\n")[0])
    print(f"\nseries minimum n = {MIN_SERIES}, derived from alpha = {SEPARATION_ALPHA}")

    print("\nVERIFYING THE PINNED JOIN against SIFTS and ChEMBL")
    problems: list[str] = []
    for row in rows:
        found = verify_join(row)
        print(f"  {row.pdb_id}  {row.chembl_target_id:12s} " + ("OK" if not found else "DISAGREES"))
        problems += found
    if problems:
        print("\nREFUSING TO BUILD -- the pinned join no longer matches the sources:")
        for problem in problems:
            print(f"  {problem}")
        return 1

    all_series: list[dict] = []
    funnels: dict[str, dict] = {}
    for row in rows:
        activities = fetch_activities(row.chembl_target_id, args.endpoint)
        series, funnel = build_series(row, activities, args.endpoint)
        funnels[row.pdb_id] = funnel
        all_series += series
        print(
            f"\n{row.pdb_id} {row.chembl_target_id} ({row.organism}) -- "
            f"{len(activities)} activities -> {len(series)} series"
        )
        for key in sorted(funnel):
            print(f"    {key:34s} {funnel[key]}")

    print("\nFREE BASELINES, computed before any Vina runs.")
    print("A series whose potency already tracks size cannot tell a ranking")
    print("docking score from one that has merely learned size.")
    baselines = {series["series_id"]: free_baselines(series) for series in all_series}
    decoupled = [sid for sid, base in baselines.items() if is_size_decoupled(base["heavy_atoms"])]
    print(
        f"\n  {len(all_series)} series, of which {len(decoupled)} are "
        f"size-decoupled (|rho(heavy, potency)| < {SIZE_DECOUPLED_BELOW})"
    )
    if not decoupled:
        print("  NONE -- on every series here the potency tracks heavy-atom")
        print("  count, so the baseline control cannot fire and a docking rho")
        print("  would be uninterpretable. Widen the corpus before spending")
        print("  Vina time.")

    selection = select_for_docking(all_series, baselines)
    path = write_corpus(all_series, funnels, args.endpoint, selection)
    print(f"\nwrote {len(all_series)} series and {path}")

    print("\nFROZEN DOCKING SELECTION -- Stage 1 docks these and nothing else")
    by_id = {series["series_id"]: series for series in all_series}
    header = (
        f"  {'series':30s} {'n':>3s} {'span':>5s} {'heavy':>6s} {'MW':>6s} "
        f"{'cLogP':>6s} {'TPSA':>6s}"
    )
    print(header)
    searches = 0
    for series_id in selection:
        series, base = by_id[series_id], baselines[series_id]
        searches += series["n_ligands"]
        print(
            f"  {series_id:30s} {series['n_ligands']:>3d} "
            f"{series['span_pchembl']:>5.2f} {_rho(base['heavy_atoms'])} "
            f"{_rho(base['mol_weight'])} {_rho(base['clogp'])} {_rho(base['tpsa'])}"
        )
    print(
        f"\n  {len(selection)} series, {searches} ligands. At 6 replicates that is "
        f"{searches * 6} searches;\n  at the 6-38 s per search measured on this "
        "machine at exhaustiveness 25,\n  roughly "
        f"{searches * 6 * 6 / 3600:.1f} to {searches * 6 * 38 / 3600:.1f} hours."
    )

    if args.presence:
        _resolve_presence(all_series)
    return 0


def _resolve_presence(all_series: list[dict]) -> None:
    """Resolve and cache the leakage bound for every compound in the corpus.

    Cached per InChIKey and shared across series, because the same compound
    appears in several assays and the answer does not depend on which.
    """
    from pdb_presence import PdbPresence, lookup

    cache_path = DATA / "pdb_presence.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    keys = sorted({ligand["inchikey"] for s in all_series for ligand in s["ligands"]})
    print(f"\nLEAKAGE BOUND: {len(keys)} distinct compounds")
    for index, key in enumerate(keys, 1):
        if key not in cache:
            verdict, ids = lookup(key)
            cache[key] = {"verdict": verdict.name, "components": ids}
            if index % 50 == 0:
                cache_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    counts = {verdict.name: 0 for verdict in PdbPresence}
    for key in keys:
        counts[cache[key]["verdict"]] += 1
    # PRINTED EVEN WHEN ZERO. An absent line reads as "no problem"; a printed
    # 0 reads as "checked".
    for name in sorted(counts):
        print(f"  {name:11s} {counts[name]}")
    print(
        "\n  ABSENT is a SUFFICIENT exclusion from PDBbind under exact-InChIKey\n"
        "  identity, so it is a MINIMAL leakage bound rather than a claim of a\n"
        "  leakage-free evaluation. PRESENT implies nothing: a compound can be\n"
        "  in the PDB bound to a protein PDBbind never included."
    )


if __name__ == "__main__":
    raise SystemExit(main())
