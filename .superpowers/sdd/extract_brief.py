"""Extract one Task N section from a plan file."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract(plan: Path, n: int) -> str:
    lines = plan.read_text(encoding="utf-8").splitlines(True)
    out: list[str] = []
    infence = False
    intask = False
    heading = re.compile(r"#+[ \t]+Task[ \t]+(\d+)")
    for line in lines:
        if line.startswith("```"):
            infence = not infence
        if not infence:
            match = heading.match(line)
            if match:
                intask = int(match.group(1)) == n
        if intask:
            out.append(line)
    return "".join(out)


def main() -> None:
    plan = Path(sys.argv[1])
    n = int(sys.argv[2])
    dest = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(f".superpowers/sdd/task-{n}-brief.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = extract(plan, n)
    if not text.strip():
        raise SystemExit(f"task {n} not found in {plan}")
    dest.write_text(text, encoding="utf-8")
    print(f"wrote {dest}: {text.count(chr(10))} lines")


if __name__ == "__main__":
    main()
