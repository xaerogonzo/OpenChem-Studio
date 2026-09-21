#!/usr/bin/env bash
# The naming rounds' app-suite gate, as a tool. Runs the app suite's shards in CHUNKS of files, each chunk its own pytest process, so the
# known Windows access violation in conftest.dispose (exit 139, no summary line, no FAILED lines) costs one chunk instead of a shard.
#
#   bash tools/run_app_gate.sh --sha 470ff2c --out /d/_scratch/gate-470ff2c        # a DETACHED worktree at that commit, both shards + vendored
#   bash tools/run_app_gate.sh --tree /d/_scratch/OpenChem-Studio-470ff2c --shards 2   # an existing tree, one shard
#   bash tools/run_app_gate.sh --tree . --shards 1,2 --dry-run                      # print the chunk plan and run nothing
#
# WHY IT EXISTS. Through naming round 8 this lived in a session scratchpad and was rebuilt by hand. The rules it encodes were each paid for:
#   * The crash is deterministic PER CHUNK COMPOSITION: the same chunk of 25 files crashed identically twice and passed on the third
#     attempt, and a whole shard crashed at a different test on every run. So a chunk that exits 139 is retried, up to three attempts; ANY
#     other non-zero exit is a real result and is never retried.
#   * A DETACHED worktree (`git worktree add --detach`) keeps the main tree editable during the ~hour a gate takes. It has no .venv, so the
#     main checkout's interpreter runs it with PYTHONPATH at the worktree's `src`. Put it at `<drive>:\_scratch\<repo>-<short-sha>` (the
#     baseline's "Extra checkouts" convention) and REMOVE it when done: `git worktree remove <path>`; the script never deletes anything.
#   * The vendored suite is its own pytest process (tools/naming_consumers.py explains why: its conftest replaces py2opsin.py2opsin globally).
#   * JAVA_HOME must be set AND `java` on PATH: OPSIN shells out to a bare `java`, and without it ~200 tests fail like a code regression.
#     Set them in TWO exports; `export JAVA_HOME=... PATH="$JAVA_HOME/bin:$PATH"` on one line expands the OLD, empty JAVA_HOME.
#   * `set -o pipefail` and a summary that is a PAIR (a summary line AND a clean exit): a crashed run has no FAILED lines to grep.
#
# The final line of summary.txt is `RESULT: PASS` or `RESULT: FAIL`, and the exit status agrees.
set -o pipefail

SHA=""; TREE=""; OUT=""; SHARDS="1,2"; CHUNK=25; DRY=0; VENDOR=1; STAGE=""; COMPARE=""; PREFLIGHT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sha) SHA="$2"; shift 2 ;;
    --tree) TREE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --shards) SHARDS="$2"; shift 2 ;;
    --chunk) CHUNK="$2"; shift 2 ;;
    --stage) STAGE="$2"; shift 2 ;;
    --compare) COMPARE="$2"; shift 2 ;;
    --no-vendor) VENDOR=0; shift ;;
    --dry-run) DRY=1; shift ;;
    --preflight) PREFLIGHT=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

MAIN="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-$MAIN/.venv/Scripts/python.exe}"
[ -x "$PY" ] || PY="${PY_FALLBACK:-$MAIN/.venv/bin/python}"
[ -x "$PY" ] || { echo "no interpreter at $PY: run \`uv sync\` in $MAIN, or set PY" >&2; exit 2; }
if [ "$DRY" -eq 0 ]; then
  : "${JAVA_HOME:?set JAVA_HOME to a JRE (in its own export), and put its bin on PATH}"
  command -v java >/dev/null || { echo "no \`java\` on PATH: OPSIN needs a bare java, and without it ~200 tests fail like a regression" >&2; exit 2; }
fi

if [ -n "$SHA" ]; then
  [ -z "$TREE" ] || { echo "--sha and --tree are alternatives" >&2; exit 2; }
  SHORT="$(git -C "$MAIN" rev-parse --short "$SHA")" || exit 2
  # `<drive>:\_scratch\<repo>-<short-sha>` on the repo's own drive (Git Bash spells it /d/_scratch/...); elsewhere, beside the checkout.
  case "$MAIN" in /[a-z]/*) SCRATCH="/${MAIN:1:1}/_scratch" ;; *) SCRATCH="$(dirname "$MAIN")/_scratch" ;; esac
  TREE="$SCRATCH/$(basename "$MAIN" | tr ' ' '-')-$SHORT"
  if [ ! -d "$TREE" ]; then
    mkdir -p "$(dirname "$TREE")"
    [ "$DRY" -eq 0 ] && git -C "$MAIN" worktree add --detach "$TREE" "$SHA" >&2
  fi
fi
[ -n "$TREE" ] || { echo "give --sha (a new detached worktree) or --tree (an existing one)" >&2; exit 2; }
# A dry run creates nothing, so with --sha and no tree yet it plans against the main checkout's shard split (the same code at that commit
# is what the real run uses; say so, because the two can differ when the commits do).
if [ "$DRY" -eq 1 ] && [ ! -d "$TREE" ]; then echo "(dry run: $TREE does not exist; planning against $MAIN)" >&2; TREE="$MAIN"; fi
[ -d "$TREE" ] || [ "$DRY" -eq 1 ] || { echo "no tree at $TREE" >&2; exit 2; }
TREE="$(cd "$TREE" 2>/dev/null && pwd || echo "$TREE")"
[ -n "$OUT" ] || OUT="$TREE/.gate-out"
export PYTHONPATH="$TREE/src"

# The two tests every gate since round 5 has deselected: one needs the network, one is a WebEngine grab that fails in a second way under load.
DESELECT=(--deselect "tests/test_naming_providers.py::test_pubchem_name_round_trips_back_through_opsin"
          --deselect "tests/test_mol3d_viewer_backend.py::test_the_3d_view_grabs_a_real_png")

shard_files() { (cd "$TREE" && "$PY" tools/suite_shards.py --splits=2 --group="$1" | tr -d '\r'); }  # the splitter prints CRLF

if [ "$DRY" -eq 1 ]; then
  for g in ${SHARDS//,/ }; do
    files=$(shard_files "$g"); n=$(echo "$files" | wc -w)
    echo "shard $g: $n files, chunks of $CHUNK -> $(( (n + CHUNK - 1) / CHUNK )) chunks"
    i=0; chunk=1; cur=""
    for f in $files; do
      cur="$cur $f"; i=$((i+1))
      if [ $((i % CHUNK)) -eq 0 ]; then echo "chunk s${g}c$chunk: $(echo $cur | wc -w) files"; chunk=$((chunk+1)); cur=""; fi
    done
    [ -n "$cur" ] && echo "chunk s${g}c$chunk: $(echo $cur | wc -w) files"
  done
  exit 0
fi

rm -rf "$OUT"; mkdir -p "$OUT"
cd "$TREE" || exit 2
echo "HEAD $(git rev-parse --short HEAD)  tree $TREE" > "$OUT/head.txt"
"$PY" -c "import openchem; print(openchem.__file__)" > "$OUT/which.txt" 2>&1
# The interpreter must import THIS tree's openchem, not the main checkout's (a detached worktree has no venv of its own, so a wrong PYTHONPATH
# silently tests the wrong code). Windows Python prints backslash paths and Git Bash holds forward-slash ones, so compare through the OS spelling.
TREE_OS="$(cygpath -w "$TREE" 2>/dev/null || echo "$TREE")"
TREE_OS="$TREE_OS" "$PY" -c "import os, openchem; t = os.path.realpath(os.environ['TREE_OS']).lower(); p = os.path.realpath(openchem.__file__).lower(); raise SystemExit(0 if p.startswith(t) else 1)"   || { echo "the interpreter imports openchem from somewhere other than $TREE (see $OUT/which.txt)" >&2; exit 2; }
echo "preflight ok: $(cat "$OUT/which.txt")" >> "$OUT/summary.txt"
[ "$PREFLIGHT" -eq 1 ] && { cat "$OUT/summary.txt"; exit 0; }
FAIL=0

if [ -n "$STAGE" ]; then
  "$PY" -u tools/naming_stage_artifact.py --stage "$STAGE" ${COMPARE:+--compare "$COMPARE"} > "$OUT/artifact.log" 2>&1
  rc=$?; echo "EXIT $rc" >> "$OUT/artifact.log"; echo "stage artifact $STAGE: exit $rc" >> "$OUT/summary.txt"; [ $rc -eq 0 ] || FAIL=1
fi

if [ "$VENDOR" -eq 1 ]; then
  "$PY" -u -m pytest tests/vendor -q -p no:cacheprovider -ra > "$OUT/vendored.log" 2>&1
  rc=$?; echo "vendored suite: exit $rc: $(tail -n 1 "$OUT/vendored.log" | cut -c1-120)" >> "$OUT/summary.txt"; [ $rc -eq 0 ] || FAIL=1
fi

run_chunk() {
  local id="$1"; shift
  local attempt rc
  for attempt in 1 2 3; do
    "$PY" -u -m pytest -q -ra -p no:cacheprovider "${DESELECT[@]}" "$@" > "$OUT/$id.attempt$attempt.log" 2>&1
    rc=$?
    echo "$id attempt $attempt exit $rc: $(tail -n 1 "$OUT/$id.attempt$attempt.log" | cut -c1-120)" >> "$OUT/summary.txt"
    [ $rc -ne 139 ] && return $rc
  done
  return 139
}

for g in ${SHARDS//,/ }; do
  files=$(shard_files "$g")
  echo "shard $g: $(echo "$files" | wc -w) files" >> "$OUT/summary.txt"
  i=0; chunk=0; cur=""
  for f in $files; do
    cur="$cur $f"; i=$((i+1))
    if [ $((i % CHUNK)) -eq 0 ]; then
      chunk=$((chunk+1)); run_chunk "s${g}c$chunk" $cur; rc=$?
      echo "s${g}c$chunk FINAL exit $rc" >> "$OUT/summary.txt"; [ $rc -eq 0 ] || FAIL=1; cur=""
    fi
  done
  if [ -n "$cur" ]; then
    chunk=$((chunk+1)); run_chunk "s${g}c$chunk" $cur; rc=$?
    echo "s${g}c$chunk FINAL exit $rc" >> "$OUT/summary.txt"; [ $rc -eq 0 ] || FAIL=1
  fi
done

if [ "$FAIL" -eq 0 ]; then echo "RESULT: PASS" >> "$OUT/summary.txt"; else echo "RESULT: FAIL" >> "$OUT/summary.txt"; fi
echo DONE > "$OUT/done.txt"
tail -n 1 "$OUT/summary.txt"
exit "$FAIL"
