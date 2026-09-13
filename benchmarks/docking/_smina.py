"""Stage 3 of the smina spike: SIBLING adapters against the published ABCs.

    uv run --no-sync python benchmarks/docking/_smina.py --self-check
    uv run --no-sync python benchmarks/docking/_smina.py --self-check --ledger <mutated copy>
    set OPENCHEM_SMINA=...  &&  uv run --no-sync python benchmarks/docking/_smina.py --live

**The rule this module is written under: do not let the implementation
inherit the answer to the question it is testing.** So:

- `SminaEngine` implements the `VinaEngine` ABC and shares NO code with
  `ExecutableVinaEngine` -- its argv, subprocess handling and parsing are
  written from smina's own `--help` and from `smina_fixtures/`. It implements
  that ABC only because it is the one engine seam `VinaDockingProvider` and
  the harness accept; there is no engine-neutral one, and that is seam 1.
- `SminaPoseRescorer` implements `PoseRescorer` and does not subclass
  `VinaPoseRescorer`. It reproduces only the CONTRACT in the ABC's docstring.

Nothing here is in `src/`, and `git diff src/` stays empty for the spike.

## What the adapters had to do, which is the evidence

**`dock` TRANSLATES.** The ABC promises "Vina's own output-PDBQT text (pass
to `parse_vina_output_pdbqt`)", and smina's output carries `REMARK
minimizedAffinity` with no `REMARK VINA RESULT` line (seam 2). The RMSD
bounds that line needs are not in smina's file at all -- only in the table it
prints to stdout. So the translation pairs each MODEL with its stdout row and
ASSERTS the pairing (the remark's affinity must round to the table's), which
means every number written is one smina reported. Nothing is invented. But
the line it writes is named VINA RESULT and carries a smina number: the
contract is Vina's.

**The COMPAT flags travel on every call** (`--addH 0 --flex_hydrogens`),
chosen in the pre-registration from smina's help text. Oracle (a) could not
discriminate them on fentanyl, so their justification is the documentation,
not a measurement.

**`score_pose(refine=True)` is `--minimize`,** which smina's own help
recommends over its `--local_only`. Oracle (e) measured it as a DIFFERENT
operation from Vina's `--local_only` (destinations 0.126 A apart), and the
engine id on every `PoseScore` is what keeps the two apart (seam 7).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from openchem.chem.vina_engine import VinaEngine  # noqa: E402
from openchem.domain.docking import (  # noqa: E402
    AS_DOCKED,
    REFINE_THEN_SCORE,
    RESCORE_PROTOCOLS,
    DockingBox,
    PoseScore,
)
from openchem.plugins.interfaces import PoseRescorer, RescoreRequest  # noqa: E402
from openchem.services.progress import ProgressHandle  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "smina_fixtures"
LEDGER = HERE / "smina_seam_ledger.json"
REPO = HERE.parent.parent

#: Pre-registered in `smina_oracles.py`. See the module docstring for why they
#: are justified by documentation rather than by oracle (a).
COMPAT_FLAGS = ("--addH", "0", "--flex_hydrogens")

_AFFINITY_RE = re.compile(r"^Affinity:\s+(-?\d+(?:\.\d+)?)", re.MULTILINE)
_MODEL_RE = re.compile(r"^MODEL\s+\d+\s*\n(.*?)^ENDMDL", re.MULTILINE | re.DOTALL)
#: FIRST match per model. A minimised file carries the new value and then the
#: input's value passed through (smina_fixtures/probe_min.pdbqt).
_MINIMIZED_AFFINITY_RE = re.compile(r"^REMARK minimizedAffinity\s+(-?\d+(?:\.\d+)?)", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*(\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$", re.MULTILINE)


def smina_affinity(stdout: str) -> float:
    match = _AFFINITY_RE.search(stdout)
    if match is None:
        raise ValueError("smina printed no 'Affinity:' line; the run produced no score.")
    return float(match.group(1))


def translate_to_vina_format(pdbqt: str, stdout: str) -> str:
    """smina's docking output rewritten into the format the ABC promises.

    Every number written is one smina reported: the affinity from the
    model's FIRST `minimizedAffinity` remark (full precision), the RMSD
    bounds from the matching row of the stdout table. The pairing is
    ASSERTED, because a mis-paired row would attach one pose's RMSD to
    another and read perfectly.
    """
    blocks = [m.group(1) for m in _MODEL_RE.finditer(pdbqt)]
    rows = [m.groups() for m in _TABLE_ROW_RE.finditer(stdout)]
    if len(blocks) != len(rows):
        raise ValueError(f"{len(blocks)} MODEL blocks but {len(rows)} stdout table rows; cannot pair")
    out = []
    for index, (block, (mode, table_affinity, lb, ub)) in enumerate(zip(blocks, rows), start=1):
        remark = _MINIMIZED_AFFINITY_RE.search(block)
        if remark is None or int(mode) != index:
            raise ValueError(f"model {index} has no minimizedAffinity remark or the table is out of order")
        if abs(round(float(remark.group(1)), 1) - float(table_affinity)) > 0.051:
            raise ValueError(
                f"model {index}: remark {remark.group(1)} does not round to table {table_affinity}; mis-paired"
            )
        out.append(f"MODEL {index}\nREMARK VINA RESULT:    {remark.group(1)}  {lb}  {ub}\n{block}ENDMDL\n")
    return "".join(out)


class SminaEngine(VinaEngine):
    """smina through its command line. A sibling of `ExecutableVinaEngine`."""

    engine_id = "smina-executable"

    def __init__(self, executable_path: str) -> None:
        self._executable_path = executable_path

    def is_available(self) -> bool:
        return bool(self._executable_path) and pathlib.Path(self._executable_path).is_file()

    def version(self) -> str:
        if not self.is_available():
            return "unknown"
        done = subprocess.run([self._executable_path, "--version"], capture_output=True, text=True)
        return (done.stdout or done.stderr).strip() or "unknown"

    @staticmethod
    def _box(box: DockingBox) -> list[str]:
        return [
            "--center_x", str(box.center[0]), "--center_y", str(box.center[1]), "--center_z", str(box.center[2]),
            "--size_x", str(box.size[0]), "--size_y", str(box.size[1]), "--size_z", str(box.size[2]),
        ]

    @staticmethod
    def _scoring(scoring_function: str) -> list[str]:
        # "vina" is the ABC's default and smina's alias for its own default,
        # so -- like the Vina engine -- the default goes unsaid on the argv.
        # That the two smina names are ONE function is measured by `--live`,
        # not assumed.
        return [] if scoring_function in ("", "vina") else ["--scoring", scoring_function]

    def dock_argv(self, receptor_pdbqt, ligand_pdbqt, box, num_poses, exhaustiveness, seed, scoring_function, out):
        argv = [
            self._executable_path, "-r", str(receptor_pdbqt), "-l", str(ligand_pdbqt), *self._box(box),
            "--num_modes", str(num_poses), "--exhaustiveness", str(exhaustiveness), "-o", str(out),
        ]
        if seed is not None:
            argv += ["--seed", str(seed)]
        return argv + self._scoring(scoring_function) + list(COMPAT_FLAGS)

    def score_argv(self, receptor_pdbqt, pose_pdbqt, box, scoring_function, refine):
        return [
            self._executable_path, "-r", str(receptor_pdbqt), "-l", str(pose_pdbqt), *self._box(box),
            "--minimize" if refine else "--score_only",
            *self._scoring(scoring_function), *COMPAT_FLAGS,
        ]

    def dock(self, receptor_pdbqt, ligand_pdbqt, box, num_poses, exhaustiveness, seed, progress: ProgressHandle,
             scoring_function: str = "vina") -> str:
        if not self.is_available():
            raise RuntimeError("No smina executable configured.")
        with tempfile.TemporaryDirectory() as scratch:
            out = pathlib.Path(scratch) / "out.pdbqt"
            progress.report(0.5, "Docking")
            done = subprocess.run(
                self.dock_argv(receptor_pdbqt, ligand_pdbqt, box, num_poses, exhaustiveness, seed,
                               scoring_function, out),
                capture_output=True, text=True,
            )
            if done.returncode != 0:
                raise RuntimeError(_last_line(done, "smina"))
            return translate_to_vina_format(out.read_text(encoding="utf-8"), done.stdout)

    def score_pose(self, receptor_pdbqt, pose_pdbqt, box, scoring_function, refine=False) -> float:
        if not self.is_available():
            raise RuntimeError("No smina executable configured.")
        done = subprocess.run(
            self.score_argv(receptor_pdbqt, pose_pdbqt, box, scoring_function, refine),
            capture_output=True, text=True,
        )
        if done.returncode != 0:
            raise RuntimeError(_last_line(done, "smina"))
        return smina_affinity(done.stdout)


def _last_line(done: subprocess.CompletedProcess, tool: str) -> str:
    text = (done.stderr or done.stdout or "").strip()
    return text.splitlines()[-1] if text else f"{tool} exited {done.returncode} with no output."


class SminaPoseRescorer(PoseRescorer):
    """A second score from one of smina's built-in functions."""

    rescorer_id = "smina-rescore"
    #: PER FUNCTION, because they are not one quantity. smina prints
    #: "(kcal/mol)" after every Affinity line whatever the function -- and
    #: `dkoes_scoring`'s printed weights are koes2013 Table 3's docked-trained
    #: coefficients (vdw -0.00990, ad4_solvation -0.04893, hydrogen_bond
    #: 0.15305, #torsions^2 -0.31726, constant 2.46902) with every sign
    #: NEGATED, and that table's footnote says they "were trained against pK
    #: binding affinities". So its number is a negated pK, and the label smina
    #: prints beside it is wrong. Measured by printing smina's weights and
    #: reading the paper's table, 2026-09-12.
    UNITS = {"default": "kcal/mol", "vinardo": "kcal/mol", "dkoes_scoring": "-pK (smina prints kcal/mol)"}
    SUPPORTED = tuple(UNITS)

    def __init__(self, score_function: str, engine: SminaEngine) -> None:
        if score_function not in self.SUPPORTED:
            raise ValueError(f"Unsupported smina function {score_function!r}; expected one of {self.SUPPORTED}.")
        self.score_function = score_function
        self.units = self.UNITS[score_function]
        self._engine = engine

    def is_available(self) -> bool:
        return self._engine.is_available()

    def rescore(self, request: RescoreRequest, protocol: str) -> list[PoseScore]:
        if protocol not in RESCORE_PROTOCOLS:
            raise ValueError(f"Unknown rescore protocol {protocol!r}.")
        if not self.is_available():
            return [
                PoseScore(function=self.score_function, protocol=protocol, units=self.units, inapplicable=True,
                          error="No smina executable is available.", error_summary="No backend")
                for _ in request.pose_pdbqt_paths
            ]
        version = self._engine.version()
        receptor_hash = hashlib.sha256(request.receptor_pdbqt.read_bytes()).hexdigest()
        scores = []
        for pose in request.pose_pdbqt_paths:
            common: dict[str, Any] = {
                "function": self.score_function, "protocol": protocol, "units": self.units,
                "engine": self._engine.engine_id, "engine_version": version,
                "receptor_pdbqt_sha256": receptor_hash,
                "pose_pdbqt_sha256": hashlib.sha256(pose.read_bytes()).hexdigest(),
            }
            try:
                value = self._engine.score_pose(
                    request.receptor_pdbqt, pose, request.box, self.score_function,
                    refine=protocol == REFINE_THEN_SCORE,
                )
            except Exception as exc:  # noqa: BLE001 - a rescore must never fail a docking job
                scores.append(PoseScore(error=f"smina {self.score_function} failed: {exc}",
                                        error_summary="Rescore failed", **common))
                continue
            scores.append(PoseScore(value=value, **common))
        return scores


# ---------------------------------------------------------------------------
# --self-check: no binary runs
# ---------------------------------------------------------------------------

VERDICTS = {"held", "adapter_workaround", "interface_change_required"}
_EVIDENCE_RE = re.compile(r"^([\w./\-]+):(\d+)$")


def check_argv(failures: list[str]) -> None:
    from unittest.mock import MagicMock, patch

    box = DockingBox(center=(1.0, 2.0, 3.0), size=(16.0, 17.0, 18.0))
    with tempfile.TemporaryDirectory() as scratch:
        exe = pathlib.Path(scratch) / "smina.exe"
        exe.write_text("")
        engine = SminaEngine(str(exe))
        fixture_pdbqt = (FIXTURES / "probe_dock_out.pdbqt").read_text(encoding="utf-8")
        fixture_stdout = (FIXTURES / "probe_dock_stdout.txt").read_text(encoding="utf-8")
        seen: list[list[str]] = []

        def fake_run(argv, **_):
            seen.append(list(argv))
            if "-o" in argv:
                pathlib.Path(argv[argv.index("-o") + 1]).write_text(fixture_pdbqt, encoding="utf-8")
                return MagicMock(returncode=0, stdout=fixture_stdout, stderr="")
            return MagicMock(returncode=0, stdout="Affinity: -7.00000 (kcal/mol)\n", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            engine.dock("R.pdbqt", "L.pdbqt", box, 9, 25, 11, ProgressHandle(), "vinardo")
            engine.score_pose("R.pdbqt", "P.pdbqt", box, "vina", refine=False)
            engine.score_pose("R.pdbqt", "P.pdbqt", box, "dkoes_scoring", refine=True)

    box_args = ["--center_x", "1.0", "--center_y", "2.0", "--center_z", "3.0",
                "--size_x", "16.0", "--size_y", "17.0", "--size_z", "18.0"]
    # SPELLED OUT, never `*COMPAT_FLAGS`: an expectation built from the
    # constant under test passed with the flags deleted -- measured, by
    # mutating COMPAT_FLAGS to () before this line was changed.
    compat = ["--addH", "0", "--flex_hydrogens"]
    out_path = seen[0][seen[0].index("-o") + 1]
    expected = [
        [str(exe), "-r", "R.pdbqt", "-l", "L.pdbqt", *box_args, "--num_modes", "9", "--exhaustiveness", "25",
         "-o", out_path, "--seed", "11", "--scoring", "vinardo", *compat],
        [str(exe), "-r", "R.pdbqt", "-l", "P.pdbqt", *box_args, "--score_only", *compat],
        [str(exe), "-r", "R.pdbqt", "-l", "P.pdbqt", *box_args, "--minimize", "--scoring", "dkoes_scoring",
         *compat],
    ]
    for label, got, want in zip(("dock", "score_only", "minimize"), seen, expected):
        if got != want:
            failures.append(f"argv[{label}]: got {got} want {want}")
    if len(seen) != 3:
        failures.append(f"argv: expected 3 subprocess calls, saw {len(seen)}")


def check_parsers(failures: list[str]) -> None:
    from openchem.chem.vina_engine import parse_vina_output_pdbqt

    pdbqt = (FIXTURES / "probe_dock_out.pdbqt").read_text(encoding="utf-8")
    stdout = (FIXTURES / "probe_dock_stdout.txt").read_text(encoding="utf-8")
    # Seam 2's evidence, kept as an assertion: the SHIPPED parser reads
    # smina's own file as no poses at all.
    if parse_vina_output_pdbqt(pdbqt):
        failures.append("parse_vina_output_pdbqt now reads raw smina output; seam 2's evidence changed")
    poses = parse_vina_output_pdbqt(translate_to_vina_format(pdbqt, stdout))
    remarks = [float(_MINIMIZED_AFFINITY_RE.search(m.group(1)).group(1)) for m in _MODEL_RE.finditer(pdbqt)]
    table = [(float(r[2]), float(r[3])) for r in (m.groups() for m in _TABLE_ROW_RE.finditer(stdout))]
    if [p.binding_affinity_kcal_mol for p in poses] != remarks:
        failures.append("translated affinities are not smina's remarks")
    if [(p.rmsd_lb, p.rmsd_ub) for p in poses] != table:
        failures.append("translated RMSD bounds are not smina's table")
    if len(poses) != 9:
        failures.append(f"expected 9 translated poses, got {len(poses)}")
    for fixture, want in (("probe_score_only_stdout.txt", -8.75406), ("probe_minimize_stdout.txt", -8.73664)):
        got = smina_affinity((FIXTURES / fixture).read_text(encoding="utf-8"))
        if got != want:
            failures.append(f"{fixture}: parsed {got}, want {want}")
    # The passthrough trap: the minimised FILE's last remark is the input's.
    minimized = (FIXTURES / "probe_min.pdbqt").read_text(encoding="utf-8")
    first, last = (_MINIMIZED_AFFINITY_RE.findall(minimized)[i] for i in (0, -1))
    if float(first) != -8.73663902 or float(last) != -8.75381088:
        failures.append(f"minimised-file remarks moved: first {first}, last {last}")
    # A mis-paired table must be refused, not translated.
    try:
        translate_to_vina_format(pdbqt, stdout.replace("-8.8 ", "-5.0 ", 1))
        failures.append("a mis-paired stdout table was translated instead of refused")
    except ValueError:
        pass


def check_provenance(failures: list[str]) -> None:
    from openchem.ui.panels.docking_panel import _rescore_note

    class _Spy(SminaEngine):
        def __init__(self):
            super().__init__("unused")

        def is_available(self):
            return True

        def version(self):
            return "smina 2020.12.10 (spy)"

        def score_pose(self, *args, **kwargs):
            return -7.36951

    with tempfile.TemporaryDirectory() as scratch:
        s = pathlib.Path(scratch)
        (s / "r.pdbqt").write_text("receptor", encoding="utf-8")
        (s / "p.pdbqt").write_text("pose", encoding="utf-8")
        request = RescoreRequest(
            receptor_pdbqt=s / "r.pdbqt", pose_pdbqt_paths=(s / "p.pdbqt",),
            box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
            receptor_structure_text="", receptor_source_format="pdb", receptor_prep_options={},
            pose_molblocks=(),
        )
        smina_score = SminaPoseRescorer("vinardo", _Spy()).rescore(request, AS_DOCKED)[0]
        dkoes_score = SminaPoseRescorer("dkoes_scoring", _Spy()).rescore(request, AS_DOCKED)[0]
    if PoseScore.from_dict(dkoes_score.to_dict()).units == "kcal/mol":
        failures.append("provenance: a dkoes_scoring value is stored as kcal/mol; it is a negated pK")
    restored = PoseScore.from_dict(smina_score.to_dict())
    for field in ("function", "protocol", "value", "engine", "engine_version",
                  "receptor_pdbqt_sha256", "pose_pdbqt_sha256"):
        if getattr(restored, field) != getattr(smina_score, field):
            failures.append(f"provenance: {field} did not survive to_dict/from_dict")
    vina_score = PoseScore(function="vinardo", protocol=AS_DOCKED, value=-5.369, engine="vina-executable",
                           engine_version="AutoDock Vina v1.2.7")
    if PoseScore.from_dict(vina_score.to_dict()).engine == restored.engine:
        failures.append("provenance: smina's and Vina's vinardo persist as indistinguishable records")
    # THE PERSISTED RECORD HOLDS AND THE SCREEN DOES NOT. Kept as an assertion
    # so the day the panel names the engine, this line reddens and the ledger
    # has to be updated rather than silently going stale.
    if _rescore_note(restored.function) != _rescore_note(vina_score.function):
        failures.append("provenance: the panel's rescore note now distinguishes engines; update seam 8")


def check_ledger(failures: list[str], path: pathlib.Path) -> None:
    """COMPLETENESS, never correctness. A verdict's truth rests on the oracle
    or line it cites, and this function cannot read either."""
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        failures.append(f"ledger: unreadable ({exc})")
        return
    seams = ledger.get("seams", {})
    for number in map(str, range(1, 9)):
        entry = seams.get(number)
        if not isinstance(entry, dict):
            failures.append(f"ledger: seam {number} missing")
            continue
        for field in ("title", "verdict", "evidence", "established_by", "finding"):
            if not str(entry.get(field, "")).strip():
                failures.append(f"ledger: seam {number} has empty {field!r}")
        if entry.get("verdict") not in VERDICTS:
            failures.append(f"ledger: seam {number} verdict {entry.get('verdict')!r} not in {sorted(VERDICTS)}")
        match = _EVIDENCE_RE.match(str(entry.get("evidence", "")))
        if match is None:
            failures.append(f"ledger: seam {number} evidence is not file:line")
            continue
        target = REPO / match.group(1)
        if not target.is_file():
            failures.append(f"ledger: seam {number} evidence file {match.group(1)} does not exist")
        elif int(match.group(2)) > len(target.read_text(encoding="utf-8").splitlines()):
            failures.append(f"ledger: seam {number} evidence line is past the end of {match.group(1)}")
    counted = {verdict: 0 for verdict in VERDICTS}
    for entry in seams.values():
        if isinstance(entry, dict) and entry.get("verdict") in counted:
            counted[entry["verdict"]] += 1
    if ledger.get("tally") != counted:
        failures.append(f"ledger: tally {ledger.get('tally')} does not match the verdicts {counted}")


def self_check(ledger_path: pathlib.Path) -> int:
    failures: list[str] = []
    for label, check in (("argv", check_argv), ("parsers", check_parsers), ("provenance", check_provenance)):
        before = len(failures)
        check(failures)
        print(f"  {label:<11} {'ok' if len(failures) == before else 'FAILED'}")
    before = len(failures)
    check_ledger(failures, ledger_path)
    print(f"  {'ledger':<11} {'ok' if len(failures) == before else 'FAILED'}  ({ledger_path.name})")
    for failure in failures:
        print(f"    - {failure}")
    print("SELF-CHECK", "PASSED" if not failures else f"FAILED ({len(failures)})")
    return 0 if not failures else 1


# ---------------------------------------------------------------------------
# --live: the SHIPPED provider with smina injected, on the oracles' case
# ---------------------------------------------------------------------------

def live() -> int:
    from _config import smina_executable, vina_executable
    from openbabel import pybel
    from openchem import paths
    from openchem.chem.binding_site import box_from_ligand
    from openchem.chem.docking_providers import VinaDockingProvider
    from openchem.chem.receptor_library import find
    from openchem.chem.vina_engine import ExecutableVinaEngine
    from openchem.domain.docking import pose_score_of
    from seed_spread import component_smiles, embed

    engine = SminaEngine(smina_executable())
    entry = find("5C1M")
    structure = (paths.data_root() / "receptors" / "5C1M.pdb").read_text(encoding="utf-8")
    site = box_from_ligand(structure, "pdb", entry.ligand_code)
    mol = embed(component_smiles("7V7"))
    report: dict[str, Any] = {"smina_version": engine.version()}

    # L1: the shipped provider, engine injected, rescore requested by NAME.
    provider = VinaDockingProvider(engine=engine)
    poses = provider.dock(
        receptor_structure_text=structure, receptor_source_format="pdb", ligand_mol=mol, box=site.box,
        num_poses=9, progress=ProgressHandle(),
        receptor_prep_options={"strip_waters": True, "strip_cofactors": True,
                               "strip_ligand_codes": (entry.ligand_code,)},
        search_options={"exhaustiveness": 8, "seed": 11, "rescore_with": "vinardo"},
    )
    scores = [pose_score_of(p) for p in poses]
    report["L1_shipped_provider_with_smina"] = {
        "poses": len(poses),
        "provider_engine_id": provider.engine_id,
        "run_settings": provider._last_run_settings,
        "affinities": [p.binding_affinity_kcal_mol for p in poses],
        "rescore_function": scores[0].function if scores and scores[0] else None,
        "rescore_engine": scores[0].engine if scores and scores[0] else None,
        "rescore_values": [s.value if s else None for s in scores],
    }
    print(json.dumps(report["L1_shipped_provider_with_smina"], indent=1))

    # L2: are smina's "vina" and "default" one function? Measured, not assumed.
    with tempfile.TemporaryDirectory() as scratch:
        s = pathlib.Path(scratch)
        receptor, pose = s / "receptor.pdbqt", s / "pose.pdbqt"
        vina_provider = VinaDockingProvider(engine=ExecutableVinaEngine(vina_executable()))
        vina_provider._convert_receptor_to_pdbqt(
            pybel, structure, "pdb", receptor,
            {"strip_waters": True, "strip_cofactors": True, "strip_ligand_codes": (entry.ligand_code,)}, 7.4,
        )
        translated = engine.dock(receptor, _ligand(vina_provider, pybel, mol, s), site.box, 9, 8, 11,
                                 ProgressHandle())
        pose.write_text(_MODEL_RE.search(translated).group(1), encoding="utf-8")
        named = {}
        for name in ("vina", "default"):
            argv = [engine._executable_path, "-r", str(receptor), "-l", str(pose), *engine._box(site.box),
                    "--score_only", "--scoring", name, *COMPAT_FLAGS]
            named[name] = smina_affinity(subprocess.run(argv, capture_output=True, text=True).stdout)
    report["L2_vina_and_default_names"] = named
    print(f"L2 smina --scoring vina {named['vina']} / default {named['default']}")

    out = HERE / "smina_live.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def _ligand(provider, pybel, mol, scratch: pathlib.Path) -> pathlib.Path:
    path = scratch / "ligand.pdbqt"
    provider._convert_ligand_to_pdbqt(pybel, mol, path, 7.4)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--ledger", type=pathlib.Path, default=LEDGER)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        return live()
    if args.self_check:
        return self_check(args.ledger)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
