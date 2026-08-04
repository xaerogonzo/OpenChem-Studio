"""Assigned literature 13C shifts, keyed by RDKit atom index.

WHY A FILE AND NOT A DICT AT THE CALL SITE. Every number here is a
published assignment that was checked before use, and the checking is
the expensive part -- an atom-index mapping that looks right and is
silently off by one produces a confident wrong verdict in whichever
direction the error happens to fall. Recording the source, the solvent
and the validation alongside the numbers is what makes them reusable.

WHY NOT nmrshiftdb2. It is the HOSE lookup's own index
(`chem/nmr_database.py`), so scoring the lookup against it would be
circular. Ground truth has to be independent of the thing being scored.

SOLVENT MATTERS. Everything here is CDCl3, matching the values already
used elsewhere in this project. A shift measured in DMSO-d6 or C6D6 is
not interchangeable -- Moreland's own paper reports both CDCl3 and
DMSO-d6 tables precisely because carbons 6, 7 and 4' move by several ppm
between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LiteratureSpectrum:
    name: str
    smiles: str
    solvent: str
    citation: str
    doi: str
    #: RDKit atom index -> (published label, shift in ppm). The index is
    #: for `Chem.AddHs(Chem.MolFromSmiles(smiles))`; AddHs appends, so
    #: heavy-atom indices are the same either way.
    shifts: dict[int, tuple[str, float]] = field(default_factory=dict)
    notes: str = ""


#: Quinine, from Table I of Moreland/Philip/Carroll. The whole column is
#: reported without parenthesised (uncertain) values, unlike quinidine's.
#:
#: MAPPING, and how it was checked. The published numbering is the
#: cinchona convention; mapping it onto RDKit indices was derived from
#: the bicyclo[2.2.2] topology rather than by eye -- N(19) and C(16) are
#: the bridgeheads, and the three two-carbon bridges are identified by
#: what hangs off them: the vinyl-bearing bridge is C2-C3, the
#: carbinol-bearing one C7-C8, the remaining one C5-C6.
#:
#: The mapping was then VALIDATED against this project's own database
#: lookup, which is independent of the paper: all seven carbons the
#: lookup rates `good` agree with Moreland to a mean of 1.03 ppm. The
#: ring-fusion pair is the one place the assignment could plausibly have
#: flipped (the paper calls them 9'/10' rather than the IUPAC 4a'/8a'),
#: and it resolves cleanly -- atom 5 matches 143.67 to 0.47 ppm, where
#: the flipped reading would have been ~18 ppm out.
QUININE = LiteratureSpectrum(
    name="quinine",
    # Confirmed against PubChem CID 3034034 -- InChIKey
    # LOUPRKONTZGTKE-WZBLMQSHSA-N. Worth stating because the first draft of
    # this entry was 9-EPIQUININE (the C-9 epimer, -FEBSWUBLSA-), which is a
    # different column of the very table below: its C-2/C-6/C-7/C-8 differ
    # from quinine's by 1.6/2.5/3.5/1.5 ppm, so the error would have shown
    # up as a plausible-looking bias rather than as nonsense.
    #
    # The quinuclidine bridgehead nitrogen carries NO stereo tag. It is not
    # a resolvable centre, and tagging it makes the structure unembeddable
    # -- `EmbedMolecule` fails even with `useRandomCoords`.
    smiles="COc1ccc2nccc(c2c1)[C@@H](O)[C@@H]1C[C@@H]2CCN1C[C@@H]2C=C",
    solvent="CDCl3",
    citation=(
        "Moreland, C. G.; Philip, A.; Carroll, F. I. "
        "J. Org. Chem. 1974, 39 (16), 2413-2416, Table I."
    ),
    doi="10.1021/jo00930a020",
    shifts={
        20: ("C-2", 56.86),
        21: ("C-3", 39.76),
        16: ("C-4", 27.71),
        17: ("C-5", 27.46),
        18: ("C-6", 43.00),
        15: ("C-7", 21.44),
        14: ("C-8", 59.85),
        12: ("C-9", 71.51),
        22: ("C-10", 141.66),
        23: ("C-11", 114.08),
        0: ("OCH3", 55.44),
        7: ("C-2'", 147.01),
        8: ("C-3'", 121.09),
        9: ("C-4'", 148.33),
        11: ("C-5'", 101.40),
        2: ("C-6'", 157.44),
        3: ("C-7'", 118.30),
        4: ("C-8'", 130.89),
        10: ("C-9'", 126.43),
        5: ("C-10'", 143.67),
    },
    notes=(
        "The assignments predate 2D NMR -- they rest on off-resonance "
        "decoupling for multiplicity plus the Lindemann-Adams and "
        "Grant-Paul empirical shift correlations. The paper itself records "
        "one live disagreement: its C-5 (27.46) and C-7 (21.44) are "
        "REVERSED from Roberts et al., though they agree with Wenkert et "
        "al. Treat those two atoms as the least certain rows here; the "
        "difference between them is 6 ppm, so a swap would show up as two "
        "compensating errors rather than one."
    ),
)

#: Caffeine, the case `chem/nmr_hybrid.py` records in its docstring.
#: Standard CDCl3 values; the three N-methyls are distinguished by which
#: nitrogen carries them, read off the ring connectivity: N7 sits between
#: C-5 and C-8, N1 between the two carbonyls, N3 between C-2 and C-4.
CAFFEINE = LiteratureSpectrum(
    name="caffeine",
    smiles="Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    solvent="CDCl3",
    citation="Standard reference values; see chem/nmr_hybrid.py.",
    doi="",
    shifts={
        0: ("N7-CH3", 33.6),
        2: ("C-8", 141.5),
        4: ("C-4", 148.7),
        5: ("C-5", 107.6),
        6: ("C-6", 155.4),
        9: ("N1-CH3", 27.9),
        10: ("C-2", 151.7),
        13: ("N3-CH3", 29.7),
    },
)

SPECTRA = {spectrum.name: spectrum for spectrum in (QUININE, CAFFEINE)}
