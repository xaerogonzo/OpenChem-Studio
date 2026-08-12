"""Score computed TD-DFT spectra against experimental transitions.

    python benchmarks/uvvis/score.py <directory of ORCA .out files>

THE CRITERIA ARE PRE-REGISTERED, in `reference.json` and in the constants
below, and were written down before any job ran. That is the point of them:
"+0.6 eV isn't terrible" is an easy thing to conclude once you have seen
+0.6 eV, and much harder to write down in advance.

THREE CRITERIA, DELIBERATELY NOT COLLAPSED INTO ONE SCORE. The recorded
def2-SVP / def2-SVPD pair is exactly why -- one gets position wrong and
intensity right, the other the reverse, and any weighted average of the two
would report them as comparable when the whole question is which failure you
are choosing. A reader has to be able to conclude "positions improved,
intensity failed".

A TRANSITION IS LOCATED BY DECLARED ORBITAL CHARACTER, NEVER BY NEAREST
ENERGY. Matching on energy would use the answer to find the thing being
scored. This matters more than it sounds: the recorded `nroots 8` run
reported benzene's strongest band as missing when it was merely outside the
requested roots, and produced entirely plausible numbers while doing it. A
transition that cannot be located unambiguously is UNSCORABLE and says so --
it is never quietly replaced by the nearest root.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: Pre-registered acceptance thresholds. See README.md for what each one
#: costs the shipped feature if it fails.
POSITION_TOLERANCE_EV = 0.30
#: A symmetry-forbidden band must come back essentially dark. Scored as an
#: absolute ceiling rather than a ratio, because 2x of zero is zero and no
#: computation could ever fail it.
FORBIDDEN_MAX_F = 0.01
#: An allowed band's oscillator strength, as a factor either way.
INTENSITY_FACTOR = 2.0
#: Two roots are one degenerate band only if the computation agrees they are.
DEGENERACY_TOLERANCE_EV = 0.05
#: How much of a state's excitation amplitude must lie in the declared
#: donor/acceptor orbitals for it to count as that character. 0.5 admits a
#: genuinely mixed state (benzene's states run ~0.47 + ~0.49 across two
#: excitations) while excluding a state that merely brushes those orbitals.
CHARACTER_WEIGHT = 0.5

_STATE_RE = re.compile(r"^STATE\s+(\d+):\s+E=\s+\S+\s+au\s+(\d+\.\d+)\s+eV")
_CONTRIB_RE = re.compile(r"^\s+(\d+)([ab])\s*->\s*(\d+)([ab])\s*:\s+(\d+\.\d+)")
_NUM = r"-?\d+\.\d+(?:[eE][+-]?\d+)?"
_ABSORPTION_RE = re.compile(
    rf"^\s+0-1A\s+->\s+(\d+)-1A\s+({_NUM})\s+\S+\s+\S+\s+({_NUM})"
)
_ORBITAL_RE = re.compile(r"^\s+(\d+)\s+(\d+\.\d+)\s+-?\d+\.\d+\s+-?\d+\.\d+\s*$")

#: ORCA prints FOUR blocks with identical row shapes -- absorption via
#: electric dipole, absorption via velocity dipole, and the two CD spectra.
#: Only the first carries `fosc(D2)`; the CD blocks put the rotatory strength
#: R in the same column position. Parsing the file without bounding the block
#: lets the LAST one win, which is how this scorer first reported a
#: symmetry-FORBIDDEN band at f = 0.60 while the real value on the same line
#: of the same file was 0.000000029. It read as a dramatic functional
#: difference and was a parser reading the wrong table.
_ABSORPTION_HEADER = "ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS"
_NEXT_BLOCK = "ABSORPTION SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS"


class Unscorable(Exception):
    """The output cannot answer the question asked of it.

    Raised rather than returned so that no caller can accidentally treat a
    failure to locate a transition as a transition located at zero.
    """


def parse_homo(text: str) -> int:
    """Index of the highest occupied orbital, from ORBITAL ENERGIES."""
    block = text.split("ORBITAL ENERGIES", 1)
    if len(block) < 2:
        raise Unscorable("no ORBITAL ENERGIES block")
    homo = -1
    for line in block[1].splitlines()[:400]:
        match = _ORBITAL_RE.match(line)
        if not match:
            if line.strip().startswith("---") or not line.strip():
                continue
            if homo >= 0:
                break  # past the table
            continue
        index, occupation = int(match.group(1)), float(match.group(2))
        if occupation > 1.0:
            homo = index
    if homo < 0:
        raise Unscorable("could not find an occupied orbital")
    return homo


def parse_states(text: str) -> dict[int, dict]:
    """Every excited state: its energy and its excitation amplitudes.

    Energy comes from the ABSORPTION SPECTRUM block rather than the STATE
    header, because the former carries six decimals and the latter three.
    """
    states: dict[int, dict] = {}
    current: int | None = None
    for line in text.splitlines():
        state = _STATE_RE.match(line)
        if state:
            current = int(state.group(1))
            states[current] = {"energy_ev": float(state.group(2)), "contributions": []}
            continue
        if current is not None:
            contribution = _CONTRIB_RE.match(line)
            if contribution:
                states[current]["contributions"].append(
                    {
                        "donor": int(contribution.group(1)),
                        "acceptor": int(contribution.group(3)),
                        "weight": float(contribution.group(5)),
                    }
                )
            elif line.strip() and not line.startswith(" "):
                current = None

    if not states:
        raise Unscorable("no STATE blocks -- did the TD-DFT step run?")

    if _ABSORPTION_HEADER not in text:
        raise Unscorable(f"no {_ABSORPTION_HEADER!r} block")
    block = text.split(_ABSORPTION_HEADER, 1)[1].split(_NEXT_BLOCK, 1)[0]
    for line in block.splitlines():
        absorption = _ABSORPTION_RE.match(line)
        if absorption:
            index = int(absorption.group(1))
            if index in states:
                states[index]["energy_ev"] = float(absorption.group(2))
                states[index]["f"] = float(absorption.group(3))
    missing = sorted(i for i, s in states.items() if "f" not in s)
    if missing:
        raise Unscorable(f"states {missing} have no oscillator strength row")
    return states


def _character_weight(state: dict, homo: int, donors: list[int], acceptors: list[int]) -> float:
    """How much of this state's amplitude lies in the declared orbitals."""
    lumo = homo + 1
    wanted_donors = {homo + offset for offset in donors}
    wanted_acceptors = {lumo + offset for offset in acceptors}
    return sum(
        c["weight"]
        for c in state["contributions"]
        if c["donor"] in wanted_donors and c["acceptor"] in wanted_acceptors
    )


def locate(states: dict[int, dict], homo: int, identify: dict, reference_ev: float) -> list[int]:
    """The root indices forming one declared band, or Unscorable.

    The gate runs in this order and every step can refuse:
    enough roots -> matching character -> the declared rank exists ->
    the degenerate set is really degenerate.
    """
    highest = max(s["energy_ev"] for s in states.values())
    if highest < reference_ev:
        raise Unscorable(
            f"not enough roots: highest computed excitation {highest:.2f} eV is below "
            f"the reference {reference_ev:.2f} eV"
        )

    donors, acceptors = identify["donor"], identify["acceptor"]
    matching = sorted(
        (index for index, state in states.items()
         if _character_weight(state, homo, donors, acceptors) >= CHARACTER_WEIGHT),
        key=lambda index: states[index]["energy_ev"],
    )
    if not matching:
        raise Unscorable("no root carries the declared orbital character")

    degeneracy = identify.get("degeneracy", 1)
    if identify["kind"] == "orbital":
        if len(matching) != degeneracy:
            raise Unscorable(
                f"ambiguous: {len(matching)} roots carry the declared character, "
                f"expected exactly {degeneracy}"
            )
        chosen = matching
    elif identify["kind"] == "orbital_rank":
        rank = identify["rank"]
        if len(matching) < rank + degeneracy - 1:
            raise Unscorable(
                f"rank {rank} (x{degeneracy}) does not exist: only {len(matching)} "
                "roots carry the declared character"
            )
        chosen = matching[rank - 1 : rank - 1 + degeneracy]
    else:
        raise Unscorable(f"unknown identification kind {identify['kind']!r}")

    # `require_degenerate` separates two genuinely different situations that
    # a single "degeneracy" field conflates.
    #
    # Benzene's 1E1u MUST be degenerate: D6h requires it, so a functional
    # that splits it is telling you something is wrong, and enforcing that
    # is a real check.
    #
    # Pyridine's analogue MUST NOT be: the nitrogen lowers the symmetry to
    # C2v and lifts the degeneracy, measured at 0.24 / 0.12 / 0.08 eV
    # across the three arms. It is still ONE observed band -- the two
    # components overlap in a spectrum and an experimental oscillator
    # strength integrates both -- so it is summed like a degenerate pair
    # while being refused as one.
    if degeneracy > 1 and identify.get("require_degenerate", True):
        energies = [states[i]["energy_ev"] for i in chosen]
        if max(energies) - min(energies) > DEGENERACY_TOLERANCE_EV:
            raise Unscorable(
                f"declared {degeneracy}-fold degenerate but the computation splits them "
                f"by {max(energies) - min(energies):.3f} eV"
            )
    return chosen


def score_transition(states, homo, transition) -> dict:
    """Position / intensity for one declared transition."""
    row: dict = {"label": transition["label"], "verified": transition["verified"]}
    try:
        roots = locate(states, homo, transition["identify"], transition["energy_ev"])
    except Unscorable as exc:
        row["unscorable"] = str(exc)
        return row

    # SUMMED, not averaged: an experimental oscillator strength comes from
    # integrating ONE band, and components at (or near) the same energy
    # cannot be separated in that integral -- so the band total is the
    # comparable quantity. Getting this wrong costs exactly a factor of the
    # degeneracy, which is why it hides: ROADMAP.md compared one of
    # benzene's two 1E1u components against the band's experimental value
    # and read 2.1x too strong as "essentially correct".
    strength = sum(states[i]["f"] for i in roots)

    # INTENSITY-WEIGHTED, so a SPLIT band reports where the absorption
    # maximum actually is rather than the midpoint of its components. For a
    # truly degenerate pair the two are identical, so this costs benzene
    # nothing. Falls back to the plain mean when the band is dark, where
    # the weights are all zero and the weighted mean is undefined.
    energies = [states[i]["energy_ev"] for i in roots]
    if strength > 0:
        energy = sum(states[i]["energy_ev"] * states[i]["f"] for i in roots) / strength
    else:
        energy = sum(energies) / len(energies)

    row["roots"] = roots
    row["components_f"] = [states[i]["f"] for i in roots]
    row["computed_ev"] = energy
    row["reference_ev"] = transition["energy_ev"]
    row["delta_ev"] = energy - transition["energy_ev"]
    row["position_ok"] = abs(row["delta_ev"]) <= POSITION_TOLERANCE_EV
    row["computed_f"] = strength

    kind = transition["f"]["kind"]
    row["f_kind"] = kind
    if kind in ("absent", "unsourced"):
        # UNAVAILABLE, never a verdict. Scoring FAIL against a reference
        # whose provenance did not survive checking would be reporting a
        # defect in the computation that is really a defect in the
        # reference -- and for benzene the two candidate values fall on
        # opposite sides of the criterion.
        row["intensity_ok"] = None
    elif kind == "forbidden":
        row["reference_f"] = 0.0
        row["intensity_ok"] = strength <= FORBIDDEN_MAX_F
    else:
        reference_f = transition["f"]["value"]
        row["reference_f"] = reference_f
        row["intensity_ok"] = (
            reference_f / INTENSITY_FACTOR <= strength <= reference_f * INTENSITY_FACTOR
        )
    return row


def score_molecule(text: str, entry: dict) -> dict:
    homo = parse_homo(text)
    states = parse_states(text)
    rows = [score_transition(states, homo, t) for t in entry["transitions"]]

    result: dict = {"rows": rows, "n_roots": len(states)}

    if not entry.get("strongest_band_declared"):
        result["identity_ok"] = None
        return result

    declared = next((t for t in entry["transitions"] if t.get("strongest")), None)
    matching_row = next((r for r in rows if r["label"] == declared["label"]), None)
    if matching_row is None or "roots" not in matching_row:
        result["identity_ok"] = None
        result["identity_note"] = "the declared strongest band could not be located"
        return result

    brightest = max(states, key=lambda i: states[i]["f"])
    result["identity_ok"] = brightest in matching_row["roots"]
    result["brightest_root"] = brightest
    result["brightest_ev"] = states[brightest]["energy_ev"]
    result["brightest_f"] = states[brightest]["f"]
    return result


def _flag(value) -> str:
    return "  -  " if value is None else (" PASS" if value else " FAIL")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    directory = Path(argv[0])
    reference = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    molecules = reference["molecules"]

    arms = sorted({p.name.split("_", 1)[1].rsplit("_td.out", 1)[0]
                   for p in directory.glob("*_td.out")})
    if not arms:
        print(f"No *_td.out files in {directory}", file=sys.stderr)
        return 1

    verdict: dict[str, dict[str, bool]] = {}

    for arm in arms:
        print(f"\n{'=' * 100}\nARM: {arm}\n{'=' * 100}")
        print(
            f"{'molecule':<14}{'transition':<26}{'ref eV':>8}{'calc eV':>9}{'d eV':>8}"
            f"{'pos':>6}{'ref f':>8}{'calc f':>9}{'int':>6}"
        )
        print("-" * 100)
        passes = {"position": True, "identity": True, "intensity": True}
        unavailable: set[str] = set()

        for name, entry in molecules.items():
            out = directory / f"{name}_{arm}_td.out"
            if not out.is_file():
                print(f"{name:<14}(no output file)")
                passes["position"] = passes["identity"] = passes["intensity"] = False
                continue
            try:
                scored = score_molecule(out.read_text(encoding="utf-8", errors="replace"), entry)
            except Unscorable as exc:
                print(f"{name:<14}UNSCORABLE: {exc}")
                passes["position"] = passes["identity"] = passes["intensity"] = False
                continue

            for row in scored["rows"]:
                tag = "" if row["verified"] else " *"
                if "unscorable" in row:
                    print(f"{name:<14}{row['label'] + tag:<26}UNSCORABLE: {row['unscorable']}")
                    if row["verified"]:
                        passes["position"] = passes["intensity"] = False
                    continue
                ref_f = row.get("reference_f")
                print(
                    f"{name:<14}{row['label'] + tag:<26}"
                    f"{row['reference_ev']:>8.2f}{row['computed_ev']:>9.3f}"
                    f"{row['delta_ev']:>+8.2f}{_flag(row['position_ok']):>6}"
                    f"{('n/a' if ref_f is None else f'{ref_f:.3f}'):>8}"
                    f"{row['computed_f']:>9.4f}{_flag(row['intensity_ok']):>6}"
                )
                # A DEGENERATE BAND'S COMPONENTS ARE PRINTED AS WELL AS THEIR
                # SUM, because the two are easy to confuse and the confusion
                # is worth exactly a factor of the degeneracy. ROADMAP.md's
                # "f = 0.9607 against an experimental 0.9 -- essentially
                # correct" is one COMPONENT of benzene's doubly-degenerate
                # 1E1u; the band carries both. Which one the experimental
                # figure refers to decides whether TD-DFT is right here or
                # 2x too strong, so the reader is shown both rather than one.
                if len(row["components_f"]) > 1:
                    parts = " + ".join(f"{f:.4f}" for f in row["components_f"])
                    print(f"{'':<14}{'  (' + str(len(row['components_f'])) + ' components)':<26}"
                          f"{parts} = {row['computed_f']:.4f}")
                if row["verified"]:
                    passes["position"] &= row["position_ok"]
                    if row["intensity_ok"] is None:
                        # A verified transition whose intensity could not be
                        # scored makes the ARM's intensity verdict unavailable
                        # rather than passing. Otherwise benzene's 1E1u --
                        # the only band whose intensity is in question -- goes
                        # unscored while the three dark bands it sits beside
                        # carry the column to PASS, which reads as "intensity
                        # is fine" and is the opposite of what was measured.
                        unavailable.add("intensity")
                    else:
                        passes["intensity"] &= row["intensity_ok"]

            if scored["identity_ok"] is not None:
                verified_entry = all(t["verified"] for t in entry["transitions"])
                mark = _flag(scored["identity_ok"]).strip()
                print(
                    f"{name:<14}{'-> strongest band':<26}"
                    f"brightest root {scored['brightest_root']} at "
                    f"{scored['brightest_ev']:.3f} eV, f = {scored['brightest_f']:.4f}   {mark}"
                )
                if verified_entry:
                    passes["identity"] &= scored["identity_ok"]

        verdict[arm] = {k: (None if k in unavailable else v) for k, v in passes.items()}

    # The provisional note is printed only when there IS something
    # provisional. It outlived its subject once already -- the header went
    # on announcing excluded rows after pyridine was sourced and there were
    # none left -- which is the same shape as everything else this
    # benchmark exists to catch.
    provisional = any(
        not tr["verified"] for e in molecules.values() for tr in e["transitions"]
    )
    print()
    print("=" * 100)
    if provisional:
        print("VERDICT -- verified transitions only; rows marked * are PROVISIONAL")
        print("and excluded, because their reference values are not yet checked "
              "against a source.")
    else:
        print("VERDICT -- every reference value below is sourced.")
    print("=" * 100)
    print(f"{'arm':<16}{'position':>12}{'identity':>12}{'intensity':>12}{'SHIPPABLE':>12}")
    for arm, passes in verdict.items():
        # An unavailable criterion cannot make an arm shippable. `all()`
        # over a None would be a TypeError-free lie: None is falsy, so this
        # is already correct, but it is written out because "unknown" and
        # "failed" reaching the same verdict is a coincidence worth stating
        # rather than relying on.
        shippable = all(v is True for v in passes.values())
        print(
            f"{arm:<16}{_flag(passes['position']):>12}{_flag(passes['identity']):>12}"
            f"{_flag(passes['intensity']):>12}{_flag(shippable):>12}"
        )
    print(
        f"\nCriteria: position |dE| <= {POSITION_TOLERANCE_EV} eV; the brightest computed root "
        f"must be the declared strongest band;\nintensity within {INTENSITY_FACTOR}x "
        f"(a forbidden band must come back below f = {FORBIDDEN_MAX_F})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
