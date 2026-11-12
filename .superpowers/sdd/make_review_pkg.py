import subprocess
import sys
from pathlib import Path

base, head, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
log = subprocess.check_output(["git", "log", "--oneline", f"{base}..{head}"], text=True)
stat = subprocess.check_output(["git", "diff", "--stat", f"{base}..{head}"], text=True)
diff = subprocess.check_output(["git", "diff", "-U10", f"{base}..{head}"], text=True)
out.write_text(f"# Review package {base}..{head}\n\n## log\n{log}\n## stat\n{stat}\n## diff\n{diff}", encoding="utf-8")
print(f"wrote {out}")
