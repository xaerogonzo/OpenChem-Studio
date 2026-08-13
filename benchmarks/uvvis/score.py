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


def _relative(index: int, anchor: int, name: str) -> str:
    """`HOMO`, `HOMO-1`, `LUMO+2` -- an orbital named against its anchor.

    Written out rather than string-substituting a `+0` away, which would
    also mangle `HOMO+10` on any molecule big enough to have one.
    """
    offset = index - anchor
    return name if offset == 0 else f"{name}{offset:+d}"


def _diagnose(states: dict[int, dict], homo: int, identify: dict) -> str:
    """What the computation actually produced, for a refusal message.

    **A REFUSAL SHOULD BE A SCIENTIFIC RESULT, NOT A SHRUG.** "rank does
    not exist" does not say whether the roots ran out, whether the target
    is simply absent, or whether Rydberg states displaced the valence
    manifold -- and those want three different responses. This appends the
    evidence so the reader can tell them apart without opening the output.

    The Rydberg case is the one worth naming: the character filter is
    anchored *relative to HOMO/LUMO*, so with enough diffuse functions the
    LUMO can itself become a Rydberg orbital and "LUMO+1" stops meaning
    what it meant at def2-SVP. That shows up here as a matching set that
    is too small, or as matching roots at unexpected energies.
    """
    donors, acceptors = identify["donor"], identify["acceptor"]
    matching = sorted(
        (i for i, s in states.items()
         if _character_weight(s, homo, donors, acceptors) >= CHARACTER_WEIGHT),
        key=lambda i: states[i]["energy_ev"],
    )
    highest = max(s["energy_ev"] for s in states.values())
    lines = [
        f"[{len(states)} roots, highest {highest:.2f} eV; "
        f"{len(matching)} carry the declared character"
    ]
    if matching:
        lines.append(
            "matched: "
            + ", ".join(f"#{i} {states[i]['energy_ev']:.2f} eV f={states[i]['f']:.3f}"
                        for i in matching[:6])
        )
    else:
        # No match at all -- show what the low roots ARE, which is how a
        # shifted HOMO/LUMO anchor becomes visible.
        lowest = sorted(states, key=lambda i: states[i]["energy_ev"])[:3]
        for i in lowest:
            top = sorted(states[i]["contributions"], key=lambda c: -c["weight"])[:2]
            shape = ", ".join(
                f"{_relative(c['donor'], homo, 'HOMO')}->"
                f"{_relative(c['acceptor'], homo + 1, 'LUMO')} {c['weight']:.2f}"
                for c in top
            )
            lines.append(f"root #{i} {states[i]['energy_ev']:.2f} eV: {shape}")
    return " | ".join(lines) + "]"


def locate(states: dict[int, dict], homo: int, identify: dict, reference_ev: float) -> list[int]:
    """`_locate` with the diagnosis attached to every refusal.

    Wrapped rather than appended at each `raise`, because there are five of
    them and the one that gets forgotten is the one that fires.
    """
    try:
        return _locate(states, homo, identify, reference_ev)
    except Unscorable as exc:
        raise Unscorable(f"{exc}  {_diagnose(states, homo, identify)}") from None


def _locate(states: dict[int, dict], homo: int, identify: dict, reference_ev: float) -> list[int]:
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


#: What B3LYP/def2-SVP must still produce. **A FINGERPRINT, NOT A GLANCE**:
#: state identity, energy AND oscillator strength, because a changed parser
#: can produce a perfectly plausible table while reading a different root,
#: and every conclusion about a new arm is then worthless. Scoring aborts
#: rather than continues if this moves.
CONTROL_ARM = "b3lyp-svp"
CONTROL = {
    ("formaldehyde", "n->pi* (1A2)"): (4.075, 0.0),
    ("acetone", "n->pi* (1A2)"): (4.446, 0.0),
    ("benzene", "1E1u"): (7.918, 1.9212),
}
CONTROL_EV_TOLERANCE = 0.01
CONTROL_F_TOLERANCE = 0.01

_INPUT_HEADER_RE = re.compile(r"^\|\s*\d+>\s*!\s*(.+?)\s*$", re.M)
_INPUT_NROOTS_RE = re.compile(r"^\|\s*\d+>\s*nroots\s+(\d+)", re.M)
_INPUT_XYZ_RE = re.compile(
    r"^\|\s*\d+>\s{2,}([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)", re.M
)
_ORCA_FUNCTIONAL_RE = re.compile(r"Exchange Functional\s+Exchange\s+\.+\s*(\S+)")


def job_fingerprint(text: str) -> dict:
    """What this job ACTUALLY ran, read from its own output.

    A benchmark result must never be trusted because the FILENAME says
    `b3lyp-tzvp`. ORCA echoes the whole input file, so the header, the root
    count and the geometry can be recovered from the output itself, and its
    own report of the functional it applied can be checked against them.
    """
    header = _INPUT_HEADER_RE.search(text)
    nroots = _INPUT_NROOTS_RE.search(text)
    functional = _ORCA_FUNCTIONAL_RE.search(text)
    return {
        "header": header.group(1) if header else None,
        "nroots": int(nroots.group(1)) if nroots else None,
        "functional": functional.group(1) if functional else None,
        "geometry": [
            (m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)))
            for m in _INPUT_XYZ_RE.finditer(text)
        ],
    }


def check_comparability(prints: dict[tuple[str, str], dict]) -> list[str]:
    """Every arm of a molecule must differ ONLY in the method header.

    This experiment isolates the vertical-excitation basis. If someone
    later makes each arm optimise its own geometry -- a helpful-looking
    change -- it silently becomes a basis + functional + geometry
    experiment and every delta in the table means something else.
    `nroots` is checked for the same reason.
    """
    problems: list[str] = []
    molecules = sorted({m for m, _ in prints})
    for molecule in molecules:
        arms = {a: p for (m, a), p in prints.items() if m == molecule}
        reference_arm, reference = sorted(arms.items())[0]
        for arm, other in sorted(arms.items())[1:]:
            if other["nroots"] != reference["nroots"]:
                problems.append(
                    f"{molecule}: {arm} ran nroots={other['nroots']} against "
                    f"{reference_arm}'s {reference['nroots']}"
                )
            if len(other["geometry"]) != len(reference["geometry"]):
                problems.append(f"{molecule}: {arm} has a different atom count")
                continue
            worst = max(
                (max(abs(a - b) for a, b in zip(x[1:], y[1:]))
                 for x, y in zip(other["geometry"], reference["geometry"])),
                default=0.0,
            )
            if worst > 1e-6:
                problems.append(
                    f"{molecule}: {arm}'s geometry differs from {reference_arm}'s by "
                    f"{worst:.2e} A -- the arms are no longer comparable"
                )
        for arm, p in sorted(arms.items()):
            if p["header"] is None or p["nroots"] is None or not p["geometry"]:
                problems.append(f"{molecule}: {arm} -- could not read its own input echo")
    return problems


def check_control(directory: Path, molecules: dict) -> list[str]:
    """The control arm must still reproduce its recorded fingerprint."""
    problems: list[str] = []
    for (molecule, label), (energy, strength) in CONTROL.items():
        path = directory / f"{molecule}_{CONTROL_ARM}_td.out"
        if not path.is_file():
            problems.append(f"control {molecule} missing ({path.name})")
            continue
        try:
            scored = score_molecule(
                path.read_text(encoding="utf-8", errors="replace"), molecules[molecule]
            )
        except Unscorable as exc:
            problems.append(f"control {molecule} became UNSCORABLE: {exc}")
            continue
        row = next((r for r in scored["rows"] if r["label"] == label), None)
        if row is None or "computed_ev" not in row:
            problems.append(f"control {molecule} {label!r} no longer scores")
            continue
        if abs(row["computed_ev"] - energy) > CONTROL_EV_TOLERANCE:
            problems.append(
                f"control {molecule} {label}: {row['computed_ev']:.3f} eV against a "
                f"recorded {energy:.3f}"
            )
        if abs(row["computed_f"] - strength) > CONTROL_F_TOLERANCE:
            problems.append(
                f"control {molecule} {label}: f = {row['computed_f']:.4f} against a "
                f"recorded {strength:.4f}"
            )
    return problems


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

    # THE GUARDS RUN BEFORE ANY SCORING, and refuse rather than warn. A
    # table produced from jobs that are not comparable, or from a parser
    # that has started reading a different root, is worse than no table:
    # it looks exactly like a result.
    prints: dict[tuple[str, str], dict] = {}
    for path in sorted(directory.glob("*_td.out")):
        molecule, rest = path.name.split("_", 1)
        prints[(molecule, rest.rsplit("_td.out", 1)[0])] = job_fingerprint(
            path.read_text(encoding="utf-8", errors="replace")
        )

    problems = check_comparability(prints) + check_control(directory, molecules)
    if problems:
        print("REFUSING TO SCORE -- the jobs are not comparable, or the control moved:")
        for problem in problems:
            print(f"  - {problem}")
        print("\nA delta between arms only means anything if everything except the\n"
              "method header is identical, and only if the control still reproduces\n"
              "the figures the rest of this benchmark was validated against.")
        return 1

    print("Guards passed: every arm shares one geometry and root count, and the")
    print(f"{CONTROL_ARM} control still reproduces its recorded fingerprint.\n")
    print("WHAT EACH ARM ACTUALLY RAN (from its own input echo, not its filename):")
    for arm in arms:
        headers = {p["header"] for (m, a), p in prints.items() if a == arm}
        functionals = {p["functional"] for (m, a), p in prints.items() if a == arm}
        # "exchange functional", NOT "the functional". ORCA reports B3LYP's
        # exchange component as `B88`, which is accurate and reads like the
        # wrong method ran if the label is loose. For wB97X-D3 the same
        # field says WB97X-D3, because a range-separated hybrid does not
        # decompose that way.
        print(f"  {arm:<14} ! {' / '.join(sorted(h for h in headers if h))}"
              f"   [ORCA exchange functional: "
              f"{', '.join(sorted(f for f in functionals if f))}]")

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
