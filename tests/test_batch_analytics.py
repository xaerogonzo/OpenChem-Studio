"""Correlation, distributions, PCA and clustering.

Every claim here is checked against an INDEPENDENT implementation rather
than against a recorded value: `numpy.corrcoef`, `numpy.polyfit`, a
separately-written rank transform, and an eigendecomposition of the
correlation matrix. A test that only pins our own output would pass
equally well if the arithmetic were wrong from the first run.
"""

from __future__ import annotations

import numpy as np
import pytest
from rdkit import Chem

from openchem.chem.analytics import correlate, describe, pca
from openchem.chem.clustering import cluster_molecules


# --- correlation --------------------------------------------------------


def test_pearson_matches_numpy():
    rng = np.random.default_rng(7)
    x = rng.normal(size=60)
    y = 0.7 * x + rng.normal(scale=0.5, size=60)
    assert correlate(list(x), list(y)).pearson_r == pytest.approx(
        float(np.corrcoef(x, y)[0, 1]), abs=1e-12
    )


def test_the_fitted_line_matches_polyfit():
    rng = np.random.default_rng(11)
    x = rng.normal(size=40)
    y = -1.3 * x + 4.0 + rng.normal(scale=0.2, size=40)
    result = correlate(list(x), list(y))
    slope, intercept = np.polyfit(x, y, 1)
    assert result.slope == pytest.approx(float(slope), abs=1e-12)
    assert result.intercept == pytest.approx(float(intercept), abs=1e-12)


def test_spearman_averages_ties():
    """A ring-count column over 200 molecules is mostly ties. Without tie
    averaging rho would depend on the row order, which is not a property of
    the data."""
    tied = [1.0, 2.0, 2.0, 2.0, 5.0, 6.0, 6.0, 8.0, 9.0, 10.0]
    other = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0]

    def reference_ranks(values):
        array = np.asarray(values, dtype=float)
        order = np.argsort(array)
        raw = np.empty_like(array)
        raw[order] = np.arange(len(array))
        averaged = raw.copy()
        for value in np.unique(array):
            mask = array == value
            averaged[mask] = raw[mask].mean()
        return averaged

    expected = float(np.corrcoef(reference_ranks(tied), reference_ranks(other))[0, 1])
    assert correlate(tied, other).spearman_rho == pytest.approx(expected, abs=1e-12)


def test_spearman_sees_a_monotonic_curve_that_pearson_underrates():
    """The case a single coefficient hides: a real relationship on the
    wrong axes."""
    xs = [float(i) for i in range(1, 21)]
    ys = [x**4 for x in xs]
    result = correlate(xs, ys)
    assert result.spearman_rho == pytest.approx(1.0)
    assert result.pearson_r < 0.95


def test_a_constant_column_gives_zero_rather_than_nan():
    """Constant columns are ordinary in a project table -- every molecule
    passing Lipinski -- and a nan propagates into a sort order and a
    caption where it reads as a crash."""
    result = correlate([1.0, 1.0, 1.0, 1.0], [3.0, 1.0, 4.0, 1.0])
    assert result.pearson_r == 0.0
    assert result.slope == 0.0
    assert result.intercept == pytest.approx(2.25)


def test_too_few_points_says_so_instead_of_quoting_a_coefficient():
    assert "too few" in correlate([1.0], [2.0]).describe()


def test_the_description_always_carries_n():
    """r without its sample size is not a result."""
    assert "n = 5" in correlate([1.0, 2, 3, 4, 5], [2.0, 4, 5, 4, 5]).describe()


# --- distributions ------------------------------------------------------


def test_summary_statistics_match_numpy():
    rng = np.random.default_rng(3)
    values = list(rng.normal(loc=5, scale=2, size=37))
    array = np.asarray(values)
    result = describe(values)
    assert result.mean == pytest.approx(float(array.mean()), abs=1e-12)
    assert result.median == pytest.approx(float(np.median(array)), abs=1e-12)
    assert result.minimum == pytest.approx(float(array.min()))
    assert result.maximum == pytest.approx(float(array.max()))


def test_the_standard_deviation_is_the_sample_one():
    """A project table is a sample of chemical space, not the population,
    and at n = 5 the population form is 12% too small."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    array = np.asarray(values)
    assert describe(values).std_dev == pytest.approx(float(array.std(ddof=1)))
    assert describe(values).std_dev != pytest.approx(float(array.std(ddof=0)))


def test_every_value_lands_in_a_bin():
    values = list(np.random.default_rng(5).normal(size=80))
    result = describe(values)
    assert sum(result.counts) == len(values)
    assert len(result.bin_edges) == len(result.counts) + 1


def test_an_identical_column_gets_one_bin_not_a_fake_range():
    assert describe([4.0] * 12).counts == [12]


def test_an_empty_column_describes_as_empty_rather_than_raising():
    assert describe([]).n == 0


# --- PCA ----------------------------------------------------------------


def _matrix(rows=40, columns=6, seed=1):
    return np.random.default_rng(seed).normal(size=(rows, columns))


def test_explained_variance_matches_an_eigendecomposition():
    data = _matrix()
    result = pca(
        data.tolist(), [f"c{i}" for i in range(data.shape[1])], [f"u{i}" for i in range(len(data))], 3
    )
    standardised = (data - data.mean(0)) / data.std(0)
    eigenvalues = np.sort(np.linalg.eigvalsh(np.cov(standardised.T, ddof=0)))[::-1]
    expected = eigenvalues / eigenvalues.sum()
    assert np.allclose(result.explained_variance_ratio, expected[:3], atol=1e-10)


def test_standardising_stops_one_big_unit_from_becoming_pc1():
    """The reason this is not a plain covariance PCA. A molecular weight
    column beside a QED score would otherwise BE PC1, and the projection
    would be a plot of molecular weight wearing a different label.
    """
    data = _matrix(seed=2)
    scaled = data.copy()
    scaled[:, 3] *= 1000.0  # same information, absurd units
    labels = [f"c{i}" for i in range(data.shape[1])]
    uuids = [f"u{i}" for i in range(len(data))]
    plain = pca(data.tolist(), labels, uuids)
    rescaled = pca(scaled.tolist(), labels, uuids)
    assert np.allclose(plain.explained_variance_ratio, rescaled.explained_variance_ratio, atol=1e-10)


def test_a_collinear_column_loads_with_the_one_it_duplicates():
    data = _matrix(seed=4)
    data[:, 3] = 100.0 * data[:, 0] + 5.0
    result = pca(
        data.tolist(), [f"c{i}" for i in range(6)], [f"u{i}" for i in range(len(data))]
    )
    loadings = dict(zip(result.column_labels, result.loadings[0]))
    assert loadings["c0"] == pytest.approx(loadings["c3"], abs=1e-9)


def test_a_zero_variance_column_is_dropped_and_named():
    """Silently keeping it as an all-zero column would dilute every
    loading without saying so."""
    data = np.column_stack([_matrix(seed=6), np.ones(40)])
    result = pca(
        data.tolist(), [f"c{i}" for i in range(6)] + ["constant"], [f"u{i}" for i in range(40)]
    )
    assert result.dropped_columns == ["constant"]
    assert "constant" not in result.column_labels


def test_pca_is_deterministic():
    """The whole reason this and not UMAP: two runs on one project give one
    picture of chemical space."""
    data = _matrix(seed=8).tolist()
    labels = [f"c{i}" for i in range(6)]
    uuids = [f"u{i}" for i in range(40)]
    assert pca(data, labels, uuids).scores == pca(data, labels, uuids).scores


def test_top_loadings_rank_by_magnitude_not_by_sign():
    """A strongly negative loading says as much about what the axis means
    as a positive one."""
    data = _matrix(seed=9)
    data[:, 2] = -6.0 * data[:, 0]
    result = pca(data.tolist(), [f"c{i}" for i in range(6)], [f"u{i}" for i in range(40)])
    assert {label for label, _value in result.top_loadings(0, 2)} == {"c0", "c2"}


def test_an_empty_matrix_projects_to_nothing_rather_than_raising():
    assert pca([], [], []).scores == []


# --- clustering ---------------------------------------------------------

_FAMILIES = {
    "hexane": "CCCCCC",
    "heptane": "CCCCCCC",
    "octane": "CCCCCCCC",
    "nonane": "CCCCCCCCC",
    "toluene": "Cc1ccccc1",
    "xylene": "Cc1ccccc1C",
    "ethylbenzene": "CCc1ccccc1",
    "cumene": "CC(C)c1ccccc1",
    "glucose": "OCC1OC(O)C(O)C(O)C1O",
}


def _family_mols():
    return {name: Chem.MolFromSmiles(smiles) for name, smiles in _FAMILIES.items()}


def test_a_homologous_series_lands_in_one_cluster():
    assignment = cluster_molecules(_family_mols(), threshold=0.65)
    alkanes = {assignment.cluster_of[name] for name in ("hexane", "heptane", "octane", "nonane")}
    assert len(alkanes) == 1
    assert assignment.cluster_of["glucose"] not in alkanes


def test_a_permissive_threshold_recovers_both_families():
    """At 0.2 the two real families separate cleanly and the sugar stands
    alone -- which is the answer a chemist would give."""
    assignment = cluster_molecules(_family_mols(), threshold=0.2)
    assert sorted(assignment.cluster_sizes, reverse=True) == [4, 4, 1]


def test_the_threshold_is_a_similarity_not_a_distance():
    """Getting this inversion wrong produces a plausible clustering that
    means the opposite of what was asked for."""
    loose = cluster_molecules(_family_mols(), threshold=0.2)
    strict = cluster_molecules(_family_mols(), threshold=0.9)
    assert strict.cluster_count > loose.cluster_count


def test_clusters_are_numbered_largest_first():
    """At 0.65 the alkanes are the only multi-member cluster, so "largest
    is cluster 1" has one answer. At a looser threshold two clusters tie at
    four members and either could legitimately be first."""
    assignment = cluster_molecules(_family_mols(), threshold=0.65)
    assert assignment.cluster_sizes == sorted(assignment.cluster_sizes, reverse=True)
    assert assignment.cluster_of["hexane"] == 1
    assert assignment.singleton_count == assignment.cluster_count - 1


def test_clustering_is_deterministic():
    first = cluster_molecules(_family_mols(), threshold=0.5)
    second = cluster_molecules(_family_mols(), threshold=0.5)
    assert first.cluster_of == second.cluster_of


def test_an_unusable_structure_is_reported_not_silently_dropped():
    mols = _family_mols()
    mols["broken"] = None
    assignment = cluster_molecules(mols, threshold=0.65)
    assert assignment.skipped == ["broken"]
    assert "broken" not in assignment.cluster_of


def test_clustering_nothing_says_so():
    assert cluster_molecules({}).describe() == "Nothing to cluster."
