"""The ranking oracle's curation rules, on constructed rows and no network.

Everything here is about REFUSING things, because that is where a corpus goes
wrong invisibly: a dropped page shortens a series into a different ordering, a
coerced unit puts nanomolar and micromolar in one column, and a split salt
measures a molecule nobody assayed. None of those looks wrong in the output.

The join table and the fetch are exercised against the live APIs by
`chembl_corpus.py` itself; what is tested here is the logic that decides what
survives.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "docking"


@pytest.fixture(scope="module")
def corpus():
    """The benchmark module, loaded by path.

    Its own directory goes on `sys.path` because the module defers
    `from _stats import spearman` to call time, which is the convention the
    other benchmarks here use (`from _config import vina_executable`).
    """
    if str(_BENCH) not in sys.path:
        sys.path.insert(0, str(_BENCH))
    spec = importlib.util.spec_from_file_location("_bench_chembl_corpus", _BENCH / "chembl_corpus.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, or the dataclass cannot resolve its own
    # `__module__`. Same recipe as `tests/test_conformer_benchmark_overlap.py`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _activity(**overrides):
    """One ChEMBL activity row, in the shape the API really returns."""
    row = {
        "activity_id": 1,
        "molecule_chembl_id": "CHEMBL1",
        "canonical_smiles": "CCO",
        "standard_value": "100.0",
        "standard_units": "nM",
        "pchembl_value": "7.0",
        "assay_chembl_id": "CHEMBL_ASSAY",
        "assay_description": "Binding affinity at the thing",
        "assay_type": "B",
        "document_chembl_id": "CHEMBL_DOC",
        "document_year": 2011,
        "document_journal": "J. Med. Chem.",
        "data_validity_comment": None,
        "potential_duplicate": 0,
        "bao_label": "single protein format",
    }
    row.update(overrides)
    return row


def _distinct_series(n: int, **overrides):
    """`n` different compounds at `n` different potencies, one assay."""
    smiles = ["C" * (i + 1) + "O" for i in range(n)]
    return [
        _activity(
            activity_id=i,
            molecule_chembl_id=f"CHEMBL{i}",
            canonical_smiles=smiles[i],
            pchembl_value=str(5.0 + i * 0.5),
            **overrides,
        )
        for i in range(n)
    ]


def _row(corpus):
    return corpus.JOIN[0]


# -- the derived minimum ---------------------------------------------------


def test_the_series_minimum_is_derived_from_the_shipped_alpha(corpus):
    """NOT A TYPED NUMBER. Under the null that the docking order is unrelated
    to the measured one, all n! orderings are equally likely and two of them
    are perfect -- one per direction, because this benchmark does not fix the
    direction in advance. So the two-sided rate of the extreme outcome is
    2/n!, and the minimum is the smallest n clearing alpha.

    Imported from `domain/affinity_range.py` so the corpus and the shipped
    separation rule cannot come to use two different alphas.
    """
    import math

    from openchem.domain.affinity_range import SEPARATION_ALPHA

    assert corpus.MIN_SERIES == corpus.series_minimum(SEPARATION_ALPHA)
    assert 2 / math.factorial(corpus.MIN_SERIES) <= SEPARATION_ALPHA
    assert 2 / math.factorial(corpus.MIN_SERIES - 1) > SEPARATION_ALPHA


def test_the_minimum_moves_with_alpha_rather_than_being_a_constant(corpus):
    """The guard that fails if somebody replaces the derivation with `5`.

    A stricter alpha must demand a larger series; a looser one a smaller. A
    hardcoded return passes neither.
    """
    assert corpus.series_minimum(0.05) == 5
    assert corpus.series_minimum(0.001) > 5
    assert corpus.series_minimum(0.5) < 5


# -- what is refused, and why ----------------------------------------------


def test_a_series_shorter_than_the_minimum_is_refused(corpus):
    series, funnel = corpus.build_series(
        _row(corpus), _distinct_series(corpus.MIN_SERIES - 1), "Ki"
    )

    assert series == []
    assert funnel["series_too_small"] == 1


def test_a_series_at_the_minimum_is_kept(corpus):
    """The other side of the boundary, so the rule is a threshold rather than
    a refusal of everything."""
    series, _ = corpus.build_series(_row(corpus), _distinct_series(corpus.MIN_SERIES), "Ki")

    assert len(series) == 1
    assert series[0]["n_ligands"] == corpus.MIN_SERIES


def test_a_series_with_one_potency_is_refused_for_DEFINEDNESS(corpus):
    """Not a quality bar. Zero variance makes Spearman undefined and the
    shipped one correctly returns None, so such a series could only enter a
    table as a blank -- or, worse, as a 0.0 that reads as "uncorrelated"."""
    rows = _distinct_series(corpus.MIN_SERIES + 2)
    for row in rows:
        row["pchembl_value"] = "7.0"

    series, funnel = corpus.build_series(_row(corpus), rows, "Ki")

    assert series == []
    assert funnel["series_no_variation"] == 1


def test_the_span_is_reported_and_never_used_to_admit(corpus):
    """A pKi span is printed beside every result and stratifies the report; it
    does NOT gate the corpus, because a minimum span would be a constant
    somebody fitted -- the thing this project refuses. A narrow but genuinely
    varying series is kept, and its span is what tells a reader how much to
    believe its rho."""
    rows = _distinct_series(corpus.MIN_SERIES)
    for index, row in enumerate(rows):
        row["pchembl_value"] = str(7.0 + index * 0.01)

    series, _ = corpus.build_series(_row(corpus), rows, "Ki")

    assert len(series) == 1
    assert series[0]["span_pchembl"] < 0.05


def test_a_wrong_unit_is_refused_and_never_converted(corpus):
    """A coerced unit is how a nanomolar and a micromolar value end up in one
    ordering. The row is dropped and counted."""
    rows = _distinct_series(corpus.MIN_SERIES)
    rows[0]["standard_units"] = "uM"

    series, funnel = corpus.build_series(_row(corpus), rows, "Ki")

    assert funnel["dropped_wrong_units"] == 1
    assert series == [] or all(
        ligand["standard_units"] == corpus.REQUIRED_UNITS for ligand in series[0]["ligands"]
    )


def test_a_flagged_or_duplicate_row_is_dropped(corpus):
    rows = _distinct_series(corpus.MIN_SERIES + 2)
    rows[0]["data_validity_comment"] = "Outside typical range"
    rows[1]["potential_duplicate"] = 1

    series, funnel = corpus.build_series(_row(corpus), rows, "Ki")

    assert funnel["dropped_data_validity"] == 1
    assert funnel["dropped_potential_duplicate"] == 1
    assert series[0]["n_ligands"] == corpus.MIN_SERIES


def test_a_multi_component_smiles_is_REFUSED_never_split(corpus):
    """Taking the largest fragment is a silent transformation, and a salt is
    not the thing that was measured. The guard asserts the parent did not
    sneak in under its own name."""
    rows = _distinct_series(corpus.MIN_SERIES + 1)
    rows[0]["canonical_smiles"] = "CCCCCCCCO.Cl"

    series, funnel = corpus.build_series(_row(corpus), rows, "Ki")

    assert funnel["dropped_multi_component"] == 1
    assert all(
        "." not in ligand["canonical_smiles"] for ligand in series[0]["ligands"]
    )
    assert rows[0]["molecule_chembl_id"] not in {
        ligand["molecule_chembl_id"] for ligand in series[0]["ligands"]
    }


def test_two_assays_never_merge_into_one_series(corpus):
    """THE RULE THE WHOLE CORPUS EXISTS FOR. Mixing assays is what made the
    RCSB route useless -- 104 records for one ligand spanning a 4000-fold
    range. Two assays are two series or they are nothing."""
    rows = _distinct_series(corpus.MIN_SERIES, assay_chembl_id="A")
    rows += [
        _activity(
            activity_id=100 + i,
            molecule_chembl_id=f"CHEMBLB{i}",
            canonical_smiles="N" * (i + 1) + "CO",
            pchembl_value=str(6.0 + i * 0.4),
            assay_chembl_id="B",
        )
        for i in range(corpus.MIN_SERIES)
    ]

    series, _ = corpus.build_series(_row(corpus), rows, "Ki")

    assert {s["assay_chembl_id"] for s in series} == {"A", "B"}
    assert all(s["grouping"] == "assay" for s in series)


def test_one_compound_measured_twice_keeps_a_median_and_records_the_spread(corpus):
    """A compound measured twice in one assay is a fact ABOUT THE ASSAY, not
    noise to average away silently. The median is used and the disagreement
    travels with the ligand -- no threshold refuses on it, because what counts
    as too much disagreement is exactly the constant this project will not
    invent."""
    rows = _distinct_series(corpus.MIN_SERIES)
    twin = dict(rows[0])
    twin["activity_id"] = 999
    twin["pchembl_value"] = "9.0"
    rows.append(twin)

    series, _ = corpus.build_series(_row(corpus), rows, "Ki")
    ligand = next(l for l in series[0]["ligands"] if l["molecule_chembl_id"] == "CHEMBL0")

    assert ligand["n_rows"] == 2
    assert ligand["row_spread_pchembl"] == pytest.approx(4.0)
    assert series[0]["n_ligands"] == corpus.MIN_SERIES


# -- the size-confound classifier ------------------------------------------


def test_an_undefined_size_correlation_counts_as_DECOUPLED(corpus):
    """THE BUG THIS PREDICATE WAS EXTRACTED FOR.

    `spearman` returns None on zero variance in either column. The potency
    column is guaranteed to vary by the corpus filter, so None means the SIZE
    column is constant -- every compound the same heavy-atom count. Potency
    cannot be explained by a quantity that does not vary, so that series is
    the IDEAL place to spend Vina time.

    The first version guarded on `is not None` and excluded exactly those. It
    is not hypothetical: `5C1M_CHEMBL758126` is six compounds identical in
    heavy atoms, MW, cLogP and TPSA across a 1.99 log potency span.
    """
    assert corpus.is_size_decoupled(None) is True


def test_a_series_whose_potency_tracks_size_is_not_decoupled(corpus):
    """The other half, and the one that makes the rule a filter rather than a
    tautology. Without it every series is 'decoupled' and the control this
    project added after shipping a size-proxy endpoint can never fire."""
    assert corpus.is_size_decoupled(0.95) is False
    assert corpus.is_size_decoupled(-0.95) is False
    assert corpus.is_size_decoupled(0.05) is True


# -- the fetch fails closed ------------------------------------------------


def test_a_truncated_fetch_raises_rather_than_scoring_a_subset(corpus, monkeypatch):
    """A dropped page does not make a smaller sample of the same ordering --
    it makes a DIFFERENT ordering, and a rho over it looks perfectly healthy.

    So the collected count is asserted against ChEMBL's own `total_count`.
    """
    monkeypatch.setattr(
        corpus,
        "_get",
        lambda url: {"page_meta": {"total_count": 500, "next": None}, "activities": [_activity()]},
    )

    with pytest.raises(RuntimeError, match="collected 1 activities but ChEMBL reports 500"):
        corpus.fetch_activities("CHEMBL999")


def test_a_complete_fetch_is_accepted(corpus, monkeypatch):
    """The control: the guard above must not refuse a correct fetch."""
    monkeypatch.setattr(
        corpus,
        "_get",
        lambda url: {"page_meta": {"total_count": 1, "next": None}, "activities": [_activity()]},
    )

    assert len(corpus.fetch_activities("CHEMBL999")) == 1


# -- the pinned join -------------------------------------------------------


def test_every_pinned_target_is_a_catalogued_receptor(corpus):
    """The corpus may only name receptors the application can actually dock
    into. A pdb_id that is not in the library would build a series nothing
    could ever measure."""
    from openchem.chem.receptor_library import find

    for row in corpus.JOIN:
        assert find(row.pdb_id) is not None, f"{row.pdb_id} is not in the receptor library"


def test_no_receptor_is_pinned_twice(corpus):
    ids = [row.pdb_id for row in corpus.JOIN]
    assert len(ids) == len(set(ids))


def test_every_row_declares_a_known_organism_stratum_and_a_reason(corpus):
    """`organism_match` is a CLOSED vocabulary, for the reason
    `DIRECTORY_KINDS` is: a typo'd stratum would silently create a third
    population that no report knows to separate. And a row with no reason is
    a join nobody can audit."""
    for row in corpus.JOIN:
        assert row.organism_match in {"exact", "ortholog"}
        assert len(row.why) > 40, f"{row.pdb_id} has no usable justification"


def test_the_fusion_partners_are_never_the_pinned_accession(corpus):
    """Four of the eight deposits carry a second UniProt for their
    crystallisation fusion -- T4 lysozyme, cytochrome b562, flavodoxin -- and
    each has ChEMBL targets of its own. An unfiltered "take the accession with
    the most activities" join can return a chaperone's affinity data as the
    receptor's, silently.

    Asserted as a floor rather than a blocklist: the rule is that the pinned
    chain is named, and this catches the specific accessions that have already
    turned up.
    """
    known_fusions = {"P00720", "P0ABE7", "P00323"}
    for row in corpus.JOIN:
        assert row.uniprot not in known_fusions
