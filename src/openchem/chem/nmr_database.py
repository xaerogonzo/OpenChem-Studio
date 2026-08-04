"""A local index of assigned experimental shifts, keyed by HOSE code.

This is what turns prediction from a calculation into a LOOKUP: find
database atoms whose environment matches the query atom's, and report
what they were actually measured at. Two things follow from that which no
computed method gives us.

First, accuracy comes from experiment rather than from a model, so it is
as good as the coverage and no worse.

Second, and the reason this was worth building at all: the SPREAD of the
matching values is a real, earned measure of confidence. Every previous
attempt in this project to report a prediction quality was refused
because the number would have been invented -- Marvin can rate its own
because it has a reference database behind it, and now so can we. A shift
averaged over forty measurements that agree to 0.3 ppm is a different
claim from one averaged over two that disagree by nine, and this is the
first thing here that can tell them apart honestly.

MEASURED, on a real held-out benchmark rather than claimed. The index was
rebuilt excluding every twentieth record, and those molecules were then
predicted against their own recorded shifts -- none of them contributing
to what was being asked (`benchmarks/nmr/score_lookup.py`, format 2,
nmrshiftdb2 as downloaded 2026-08-03):

    13C -- 24,330 held-out atoms, coverage 99.8%
        good     n=11,390   MAE  1.12 ppm   median 0.50
        medium   n=10,933   MAE  3.36 ppm   median 2.31
        rough    n= 1,957   MAE 10.00 ppm   median 7.17
        ALL      n=24,280   MAE  2.85 ppm   median 1.23

    1H  --  7,727 held-out atoms, coverage 99.7%
        good     n= 3,052   MAE  0.10 ppm   median 0.05
        medium   n= 3,098   MAE  0.26 ppm   median 0.17
        rough    n= 1,555   MAE  0.77 ppm   median 0.53
        ALL      n= 7,705   MAE  0.30 ppm   median 0.13

The band breakdown is the important part. A 9x error spread between the
top and bottom bands means the confidence rating is doing real work
rather than decorating the output -- which is exactly the claim this
project refused to make three times over for want of evidence.

It also sets expectations honestly against the ab initio path: on
well-covered environments this is BETTER than a scaled ORCA calculation
(1.12 against ~1.5 ppm) and instant rather than minutes, while its
overall average is worse. The difference is that it says which atoms are
which.

WHAT FORMAT 2 CHANGED, since the numbers above replace an earlier table.
Environment codes are now written from the heavy-atom view on both sides
(`heavy_atom_view`), which merged two vocabularies that could not match
each other. Paired over the same held-out atoms, same download, both
scored through this module's own `lookup`:

                     before      after     paired delta, 95% CI
        13C  MAE      2.91       2.85     -0.092  [-0.122, -0.064]
             median   1.28       1.23
        1H   MAE      0.31       0.30     -0.025  [-0.031, -0.019]

Per-band accuracy barely moved; what moved is WHICH BAND AN ATOM LANDS
IN -- 555 more carbons rated `good`, 67 fewer `rough`. The bootstrap
resamples molecules rather than atoms, because atoms of one molecule
share a structure and an assignment. Not a large gain, but an unambiguous
one, and it cost a normalisation rather than a dependency.

(For continuity with older notes: the first version of this table read
2.98 overall with bands 1.17/3.38/9.93, measured in July on a smaller
download and on format-1 codes. It is not comparable to either column
above -- the database has grown ~4% since -- which is why the before
column was re-measured rather than quoted.)

A spot-check against literature values for common compounds gives 0.56
ppm, but that number flatters: those compounds are themselves in the
database. The held-out figures above are the ones to believe.

A LEARNED CORRECTION WAS TRIED AGAINST THIS AND LOST. Recorded here
because "we measured it and it was not better" is a result, and because
the next person to have the idea should start from the numbers rather
than repeat the work. A HistGradientBoostingRegressor was trained on the
same nmrshiftdb2 download, on the identical held-out split, from the
lookup's own statistics at all six sphere depths plus the usual cheap
RDKit atom descriptors. Same atoms, same protocol -- against the FORMAT 1
lookup, which is the baseline it was built to beat and the reason the
HOSE column below reads 2.91 rather than 2.85:

                    good      medium     rough        ALL
    13C  HOSE       1.11       3.36      10.02       2.91
         model      1.75       3.62       9.97       3.32
         hybrid     1.11       3.36       9.97       2.91

    1H   HOSE       0.10       0.26       0.77       0.31
         model      0.15       0.28       0.75       0.33
         hybrid     0.10       0.26       0.75       0.30

The hybrid -- lookup where it rates itself good or medium, model where it
rates itself rough -- TIES on carbon and gains 0.01 ppm on hydrogen. A
paired bootstrap over molecules puts the carbon `rough` difference at
-0.049 ppm, 95% CI [-0.13, +0.03]: not distinguishable from zero. The one
band where the model genuinely wins is 1H `rough`, by 0.020 ppm, which is
below the reproducibility of a proton shift between solvents.

The reason is worth keeping. Disabling the leave-one-out correction --
letting a training atom see its own measurement inside the index mean --
makes the model score 2.89, i.e. the lookup's own 2.91, and it gets there
in 49 iterations of 400. Its optimum is to COPY the lookup. Forced to
predict for itself, it does worse. Permutation importance agrees: every
atom descriptor lands at or below 0.01 ppm against 0.21 for the sphere-1
lookup mean. These features hold nothing the lookup does not already
have, and 3.75x the iterations does not change it.

So nothing under `src/` imports scikit-learn. The full table and four
ablations are in `benchmarks/nmr/README.md`.

Worth stating plainly, because it is the useful comparison: the format-2
normalisation above gained -0.092 ppm across ALL carbons, with a
confidence interval clear of zero. The model's only statistically real
effect was -0.020 ppm on 1H `rough` alone. The unglamorous fix was
roughly five times the win, over every atom instead of one band, for one
normalisation instead of 130 MB of dependencies.

STORAGE is SQLite in the app data directory, built once from the
nmrshiftdb2 distribution. Parsing 150 MB of SDF per prediction is not an
option, and an in-memory dict of every environment is not either. At six
spheres the finished index is ~15 MB for 204,353 environments drawn from
613,193 measurements across 41,304 molecules.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import platformdirs
from openchem import paths as app_paths

logger = logging.getLogger("openchem.chemistry")

_APP_NAME = "OpenChemStudio"

# Below this many matching measurements a mean is not worth reporting --
# one atom in one molecule is an anecdote, not a reference value.
MIN_MATCHES = 3

# A match whose measurements disagree by more than this has found a code
# that is not actually pinning the shift down. Reported rather than
# hidden, and used to prefer a different sphere depth where one exists.
WIDE_SPREAD_PPM = {"C": 8.0, "H": 0.5}

#: What each quality band was MEASURED to be worth, in ppm, on the format-2
#: held-out run recorded at the top of this module (24,280 carbons, every
#: twentieth molecule excluded from the index before predicting it).
#:
#: A constant rather than three numbers in a docstring because
#: `chem/nmr_hybrid.py` SELECTS on them -- which method wins an atom
#: depends on these values, so a copy that drifts changes predictions
#: silently. It drifted once already: the hybrid shipped with 1.17/3.38/
#: 9.93 from an earlier run while this module's own docstring said
#: 1.12/3.36/10.00.
#:
#: CARBON ONLY. The held-out benchmark measured carbons; there is no
#: equivalent figure for protons and inventing one would be nonsense at
#: proton scale.
HELD_OUT_BAND_MAE: dict[str, float] = {"good": 1.12, "medium": 3.36, "rough": 10.00}

#: What generation of environment codes the index holds.
#:
#: 1 -- codes written from the record as deposited, so a record carrying
#:      explicit hydrogens produced codes no hydrogen-free query could
#:      match. Two vocabularies in one table; see `heavy_atom_view`.
#: 2 -- codes written from the heavy-atom view, one vocabulary.
#:
#: An index at 1 still ANSWERS: the query side normalises too, so its
#: hydrogen-free two thirds match exactly as they always did. It just
#: holds a third of its environments where nothing can reach them. That
#: is a reason to offer a rebuild, not to refuse to predict, which is why
#: `stale_format` reports rather than raises.
INDEX_FORMAT = 2


def default_database_path() -> Path:
    return app_paths.data_root() / "nmrshiftdb.sqlite"


@dataclass(frozen=True)
class ShiftPrediction:
    """A predicted shift and the evidence behind it.

    `spread` is the standard deviation of the matching measurements, and
    `match_count` how many there were. Both travel with the value because
    the value alone cannot be judged.
    """

    shift: float
    spread: float
    match_count: int
    spheres: int
    element: str

    # A match found only after widening to this few spheres is describing
    # a generic environment, however many measurements back it. Measured:
    # chlorobenzene's para carbon falls back to three spheres, pools 5176
    # measurements of "a para CH on some monosubstituted benzene", and
    # lands 2.1 ppm out -- while a count-and-spread-only rating called it
    # the best prediction in the set. Depth is therefore part of the
    # rating, not just evidence volume.
    SPECIFIC_SPHERES = 4

    @property
    def quality(self) -> str:
        """A rating derived from the evidence, not asserted about it.

        Three things have to hold for "good": the environment was matched
        at a specific depth, enough measurements back it, and those
        measurements agree. Any one of them failing is what separates a
        number worth trusting from one worth checking.
        """
        limit = WIDE_SPREAD_PPM.get(self.element, 1.0)
        if (
            self.spheres >= self.SPECIFIC_SPHERES
            and self.match_count >= MIN_MATCHES
            and self.spread <= limit / 2
        ):
            return "good"
        if self.match_count >= MIN_MATCHES and self.spread <= limit:
            return "medium"
        return "rough"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or default_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    """One row per (environment, sphere depth, element) with the
    statistics already aggregated.

    Aggregating at BUILD time rather than storing every measurement keeps
    the index small and makes a lookup a single indexed row read. The cost
    is that the raw measurements are not queryable afterwards, which
    nothing here needs.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS shift_environments (
            hose_code TEXT NOT NULL,
            spheres   INTEGER NOT NULL,
            element   TEXT NOT NULL,
            count     INTEGER NOT NULL,
            mean      REAL NOT NULL,
            spread    REAL NOT NULL,
            PRIMARY KEY (hose_code, spheres, element)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    connection.commit()


def lookup(
    connection: sqlite3.Connection, codes: list[str], element: str, spheres_start: int
) -> ShiftPrediction | None:
    """The prediction for one atom, trying its codes largest sphere first.

    Widening only when the current depth has too few matches is the whole
    trick: it spends specificity where the database can afford it and
    falls back to a broader environment where it cannot, rather than
    picking one depth globally and being wrong in both directions.
    """
    for offset, code in enumerate(codes):
        spheres = spheres_start - offset
        row = connection.execute(
            "SELECT count, mean, spread FROM shift_environments "
            "WHERE hose_code = ? AND spheres = ? AND element = ?",
            (code, spheres, element),
        ).fetchone()
        if row is None or row[0] < MIN_MATCHES:
            continue
        count, mean, spread = row
        return ShiftPrediction(
            shift=mean, spread=spread, match_count=count, spheres=spheres, element=element
        )
    return None


def database_summary(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM metadata").fetchall()
    return {key: value for key, value in rows}


def stale_format(path: Path | None = None) -> bool:
    """Whether the index predates the single-vocabulary codes.

    Absent metadata counts as stale: format 1 never wrote the key, so
    "missing" and "1" mean the same thing.
    """
    path = path or default_database_path()
    if not path.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'format'"
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is None or row[0] != str(INDEX_FORMAT)


def is_populated(path: Path | None = None) -> bool:
    path = path or default_database_path()
    if not path.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            (count,) = connection.execute(
                "SELECT count(*) FROM shift_environments"
            ).fetchone()
        return count > 0
    except sqlite3.Error:
        return False


# --- Building -------------------------------------------------------------


@dataclass
class _Accumulator:
    """Running mean and variance per environment.

    Welford's algorithm rather than storing every value and computing at
    the end: the build sees millions of measurements and holding them all
    to compute a standard deviation would need far more memory than the
    finished index does.
    """

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def spread(self) -> float:
        return (self.m2 / (self.count - 1)) ** 0.5 if self.count > 1 else 0.0


def heavy_atom_view(mol) -> tuple[object, dict[int, int]]:
    """(the molecule without explicit hydrogens, original index -> new index).

    WHY EVERY ENVIRONMENT IS CODED FROM THIS and not from the molecule as
    given. `hose_code` walks every bond, so an explicit hydrogen becomes
    part of the code -- and 34.3% of nmrshiftdb2's records carry explicit
    hydrogens while the rest do not. Measured, not assumed: that third was
    speaking a code vocabulary the other two thirds could not match, so
    the index was really two indexes, neither able to answer the other's
    questions. A molecule drawn in this application has no explicit
    hydrogens at all, so before this it could only ever match the 65.7%.

    It was also a live bug on the query side. Toluene's methyl carbon,
    looked up from `Chem.AddHs(...)`, returned 8.89 ppm against a
    literature 21.4; from the same molecule without explicit hydrogens,
    21.52. Same molecule, same index, two answers, no error either way.

    A HYDROGEN'S OWN INDEX MAPS TO THE HEAVY ATOM IT SITS ON rather than
    disappearing. nmrshiftdb2 files a proton's shift against its heavy
    atom -- 6,987 of the held-out split's 1H assignments do -- but 444 of
    them point straight at an explicit hydrogen instead. Dropping those
    would discard real measurements; sending them to the parent files them
    exactly where the other convention already puts them. (Checked against
    the distribution: hydrogen-indexed assignments occur only in 1H
    spectra, and their shifts span 0.11-13.10 ppm, which is what a proton
    shift looks like.)
    """
    from rdkit import Chem

    mapping: dict[int, int] = {}
    kept = 0
    has_explicit_hydrogen = False
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 1:
            has_explicit_hydrogen = True
            continue
        mapping[atom.GetIdx()] = kept
        kept += 1

    # The overwhelmingly common case, and worth not paying for: a molecule
    # with no explicit hydrogens is already its own heavy-atom view.
    if not has_explicit_hydrogen:
        return mol, mapping

    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 1:
            continue
        for neighbour in atom.GetNeighbors():
            if neighbour.GetAtomicNum() != 1:
                mapping[atom.GetIdx()] = mapping[neighbour.GetIdx()]
                break
        # An H bonded to nothing heavy (H2, a lone proton) has no parent to
        # file under and is left unmapped, so the caller drops it rather
        # than guessing.

    return Chem.RemoveAllHs(mol), mapping


def iter_assigned_spectra(
    sdf_path: Path,
) -> Iterator[tuple[int, object, str, list[tuple[int, float]]]]:
    """(record index, mol, element, [(atom index, shift), ...]) per spectrum.

    nmrshiftdb2 stores assignments in SD properties named like
    `Spectrum 13C 0`, whose value is `shift;intensity+multiplicity;atom`
    entries joined by `|`. Confirmed against the real distribution.

    A LIST, not a dict, and that is load-bearing. In a 1H spectrum the
    index is the HEAVY ATOM the protons sit on, so one index legitimately
    carries several measurements -- a real record reads
    `0.99;0.0;14|1.15;0.0;14|1.42;0.0;14`, three protons on one carbon,
    and `4.64;0.0;8|5.13;0.0;8`, two diastereotopic protons on another.
    Keying by atom index would have kept the last of each and thrown the
    rest away, quietly, while still producing a plausible-looking index.

    That the 1H index is the heavy atom also matches how this project
    already describes a proton's environment (`hose_codes_for_element`),
    so the two sides of the lookup agree without a conversion step.

    Atom numbers are validated against the molecule rather than trusted:
    an off-by-one would attach real measurements to the wrong atoms
    throughout, and no later test could tell that apart from a bad
    predictor.

    THE MOLECULE YIELDED IS THE HEAVY-ATOM VIEW and the indices are its,
    not the record's -- see `heavy_atom_view` for why. Validation happens
    against the record's own atom count first, because that is the
    numbering the file is written in; remapping comes after.
    """
    from rdkit import Chem

    supplier = Chem.SDMolSupplier(str(sdf_path), removeHs=False, sanitize=True)
    for record_index, mol in enumerate(supplier):
        if mol is None:
            continue
        atom_count = mol.GetNumAtoms()
        try:
            heavy, mapping = heavy_atom_view(mol)
        except Exception:  # noqa: BLE001 - a bad record costs itself, not the build
            continue
        for prop in mol.GetPropNames():
            if not prop.startswith("Spectrum "):
                continue
            parts = prop.split()
            if len(parts) < 2:
                continue
            element = _element_from_nucleus(parts[1])
            if element is None:
                continue
            assignments = [
                (mapping[index], shift)
                for index, shift in _parse_assignments(mol.GetProp(prop), atom_count)
                if index in mapping
            ]
            if assignments:
                # The record index is yielded because a molecule cannot be
                # identified by object identity here: SDMolSupplier frees
                # each Mol once the next is read, so id() values are
                # RECYCLED and counting distinct ones reported 237 for a
                # 56,000-record file.
                yield record_index, heavy, element, assignments


def _element_from_nucleus(nucleus: str) -> str | None:
    """"13C" -> "C". Only the nuclei this app reports are indexed;
    anything else in the database is skipped rather than stored under a
    key nothing will ever query."""
    stripped = nucleus.lstrip("0123456789")
    return stripped if stripped in ("C", "H") else None


def _parse_assignments(raw: str, atom_count: int) -> list[tuple[int, float]]:
    assignments: list[tuple[int, float]] = []
    for entry in raw.split("|"):
        fields = entry.strip().split(";")
        # The real records end with a trailing "|", so the final split is
        # empty -- skipped here rather than special-cased at the caller.
        if len(fields) < 3:
            continue
        try:
            shift = float(fields[0])
            atom_index = int(fields[2])
        except ValueError:
            continue
        # Rejected rather than clamped: an index outside the molecule
        # means this record's numbering is not what we assumed, and
        # guessing would attach a real measurement to the wrong atom.
        if 0 <= atom_index < atom_count:
            assignments.append((atom_index, shift))
    return assignments


@dataclass(frozen=True)
class BuildStats:
    molecules: int
    spectra: int
    measurements: int
    environments: int
    skipped_molecules: int


def build_index(
    sdf_path: Path,
    database_path: Path,
    max_spheres: int = 4,
    on_progress=None,
) -> BuildStats:
    """Parse the nmrshiftdb2 distribution into the queryable index.

    `database_path` is REQUIRED, deliberately. It used to default to the
    user's real index, and this function begins by DELETING what is
    there -- so a caller that simply forgot the argument silently
    destroyed a built index instead of writing where it meant to. That
    happened: a test that did not redirect it wiped a real 15 MB index
    and left metadata reading `source: in.sd, molecules: 0`. A required
    argument cannot be forgotten.

    Every measurement is filed under its atom's code at EVERY sphere
    depth, not just the deepest. That is what makes the widening fallback
    in `lookup` possible: a query that finds too few matches at four
    spheres needs the three-sphere statistics to already exist, and
    recomputing them at query time would mean scanning the table.

    A molecule RDKit cannot sanitize is skipped and counted, not fixed.
    The database is a public deposition and a handful of its records are
    genuinely malformed; guessing at their structure would put wrong
    environments in the index, which is worse than a slightly smaller one.
    """
    from openchem.chem.hose_codes import hose_codes

    accumulators: dict[tuple[str, int, str], _Accumulator] = {}
    spectra = measurements = skipped = 0
    seen_records: set[int] = set()

    for record_index, mol, element, assignments in iter_assigned_spectra(sdf_path):
        spectra += 1
        seen_records.add(record_index)

        for atom_index, shift in assignments:
            # The recorded index is the atom whose environment the shift
            # belongs to -- the carbon itself for 13C, and the heavy atom
            # a proton sits on for 1H. Both are looked up the same way,
            # which is exactly why `hose_codes_for_element` describes a
            # proton by its parent: the two sides agree without a
            # conversion step.
            try:
                codes = hose_codes(mol, atom_index, max_spheres)
            except Exception:  # noqa: BLE001 - a bad record costs itself, not the build
                skipped += 1
                continue
            for offset, code in enumerate(codes):
                spheres = max_spheres - offset
                key = (code, spheres, element)
                accumulator = accumulators.get(key)
                if accumulator is None:
                    accumulator = accumulators[key] = _Accumulator()
                accumulator.add(shift)
            measurements += 1

        if on_progress is not None and spectra % 5000 == 0:
            on_progress(spectra, measurements, len(accumulators))

    connection = connect(database_path)
    try:
        create_schema(connection)
        connection.execute("DELETE FROM shift_environments")
        connection.executemany(
            "INSERT INTO shift_environments (hose_code, spheres, element, count, mean, spread) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (code, spheres, element, acc.count, acc.mean, acc.spread)
                for (code, spheres, element), acc in accumulators.items()
                # Singletons are not worth the disk: a lookup refuses them
                # anyway (MIN_MATCHES), and they are the bulk of the table.
                if acc.count >= MIN_MATCHES
            ],
        )
        connection.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            [
                ("source", sdf_path.name),
                ("format", str(INDEX_FORMAT)),
                ("max_spheres", str(max_spheres)),
                ("molecules", str(len(seen_records))),
                ("measurements", str(measurements)),
            ],
        )
        connection.commit()
        (kept,) = connection.execute("SELECT count(*) FROM shift_environments").fetchone()
    finally:
        connection.close()

    return BuildStats(
        molecules=len(seen_records),
        spectra=spectra,
        measurements=measurements,
        environments=kept,
        skipped_molecules=skipped,
    )


def predict_spectrum(
    mol,
    molecule_uuid: str,
    element: str = "C",
    database_path: Path | None = None,
    max_spheres: int = 4,
):
    """A database-backed NMRSpectrumResult, or None if nothing matched.

    Returns real ppm directly -- no referencing or scaling step, because
    the values ARE measured shifts rather than computed shieldings. That
    is the whole difference between this and the ORCA path.

    Per-atom `quality` and match counts go into `Provenance.parameters`
    rather than being averaged into one headline figure: a spectrum where
    two carbons are well covered and one is a guess should say so per
    atom, which is exactly what a single overall rating would hide.
    """
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.scientific_result import NMRSpectrumResult
    from openchem.chem.hose_codes import hose_codes

    path = database_path or default_database_path()
    if not is_populated(path):
        return NMRSpectrumResult(
            spectrum_type="nmr_13c" if element == "C" else "nmr_1h",
            name=f"{element} NMR (database)",
            units="ppm",
            method="hose_lookup",
            molecule_uuid=molecule_uuid,
            values={},
            elements={},
            cache_state=CacheState.FAILED,
            error=(
                "No experimental shift database has been built yet. "
                "Build it from Tools > External Tools."
            ),
            provenance=Provenance(created_by="core", method="hose_lookup"),
        )

    # Coded from the heavy-atom view, for the reason `heavy_atom_view`
    # gives: an explicit hydrogen in the query changes every code and
    # silently matches nothing the index holds.
    heavy, mapping = heavy_atom_view(mol)

    connection = connect(path)
    values: dict[int, float] = {}
    elements: dict[int, str] = {}
    details: dict[str, dict[str, float | int | str]] = {}
    try:
        for atom in mol.GetAtoms():
            if element == "C" and atom.GetSymbol() != "C":
                continue
            if element == "H":
                # A proton's shift is keyed to the heavy atom it sits on,
                # matching how the database records it.
                if atom.GetSymbol() != "C" or atom.GetTotalNumHs() == 0:
                    continue
            heavy_index = mapping.get(atom.GetIdx())
            if heavy_index is None:
                continue
            prediction = lookup(
                connection, hose_codes(heavy, heavy_index, max_spheres), element, max_spheres
            )
            if prediction is None:
                continue
            # Reported against the CALLER's numbering, not the heavy view's.
            # Every consumer of this result -- the correlation plot, the
            # spectrum widget -- keys shifts back to the molecule it passed
            # in, so returning the internal indices would put every label
            # on the wrong atom.
            values[atom.GetIdx()] = prediction.shift
            elements[atom.GetIdx()] = element
            details[str(atom.GetIdx())] = {
                "quality": prediction.quality,
                "matches": prediction.match_count,
                "spread_ppm": round(prediction.spread, 3),
                "spheres": prediction.spheres,
            }
    finally:
        connection.close()

    if not values:
        return NMRSpectrumResult(
            spectrum_type="nmr_13c" if element == "C" else "nmr_1h",
            name=f"{element} NMR (database)",
            units="ppm",
            method="hose_lookup",
            molecule_uuid=molecule_uuid,
            values={},
            elements={},
            cache_state=CacheState.FAILED,
            error=(
                f"No {element} environment in this molecule was found in the database. "
                "That is a coverage gap, not a failure -- the ab initio path has no such limit."
            ),
            provenance=Provenance(created_by="core", method="hose_lookup"),
        )

    return NMRSpectrumResult(
        spectrum_type="nmr_13c" if element == "C" else "nmr_1h",
        name=f"{element} NMR (experimental database)",
        units="ppm",
        method="hose_lookup",
        molecule_uuid=molecule_uuid,
        values=values,
        elements=elements,
        provenance=Provenance(
            created_by="core",
            method="hose_lookup",
            parameters={
                "reference_source": "nmrshiftdb2 (assigned experimental spectra)",
                "max_spheres": max_spheres,
                "per_atom": details,
                # Stated so a partial prediction is never mistaken for a
                # complete one: an atom absent from `values` was not
                # found, not measured at zero.
                "atoms_predicted": len(values),
            },
        ),
    )


DEFAULT_SPHERES = 6


def compute_database_nmr(mol, molecule_uuid: str, parameters: dict | None = None):
    """The "nmr" category's database calculator.

    Instant where the ab initio path takes minutes, and it reports its own
    confidence per atom -- but only for environments the database has
    seen. The two are complements, not alternatives, which is why both are
    registered rather than one replacing the other.
    """
    parameters = parameters or {}
    element = parameters.get("nucleus", "13C").lstrip("0123456789") or "C"
    return predict_spectrum(
        mol,
        molecule_uuid,
        element=element,
        max_spheres=int(parameters.get("spheres", DEFAULT_SPHERES)),
    )
