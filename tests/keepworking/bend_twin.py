"""Generate exhaustive Bend cases for every keepworking decide domain and run them.

Expected column: lib/z0/keepworking/kernel.py. Actual column: executing
bend/keepworking/MODEL.bend through the pinned Bend in a temp dir.
"""
from __future__ import annotations

from enum import Enum
import itertools
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "bend/keepworking"
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

from z0.keepworking import kernel as k  # noqa: E402

CODER = {"entry_ok": "code_bool", "decide_stop": "code_verdict"}


def bend_arg(value):
    if isinstance(value, bool):
        return "True{}" if value else "False{}"
    if isinstance(value, Enum):
        return f"M.{value.value}{{}}"
    raise TypeError(f"no Bend encoding for {value!r}")


def cases(kernel=k):
    for name, domain in kernel.DOMAINS.items():
        for row in itertools.product(*domain):
            expr = f"M.{CODER[name]}(M.{name}({', '.join(bend_arg(v) for v in row)}))"
            yield expr, kernel.code(getattr(kernel, name)(*row)), (name, row)


def model_types(text):
    types, current = {}, None
    for line in text.splitlines():
        match = re.match(r"type (\w+) is Data:\s*$", line)
        if match:
            current = types.setdefault(match.group(1), [])
            continue
        ctor = re.match(r"  (\w+)\{", line)
        if current is not None and ctor:
            current.append(ctor.group(1))
        elif line.strip() and not line.startswith("  "):
            current = None
    return types


def bend_program(exprs):
    body = " ++\n    ".join(f'Nat.show({e}) ++ ","' for e in exprs)
    return ("import Base\nimport ./MODEL.bend as M\n\n"
            "def main() -> IO(Unit):\n  IO.print(\n    " + body + ")\n")


def run_parity(bend, env, model_dir=DOMAIN, kernel=k):
    rows = list(cases(kernel))
    with tempfile.TemporaryDirectory(prefix="z0-keepworking-twin-") as folder:
        working = Path(folder)
        shutil.copy2(Path(model_dir) / "MODEL.bend", working / "MODEL.bend")
        (working / "cases.bend").write_text(bend_program([e for e, _, _ in rows]))
        result = subprocess.run([bend, "cases.bend"], cwd=working, env=env,
                                capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise RuntimeError("Bend twin execution failed: " + (result.stderr + result.stdout)[-2000:])
        actual = result.stdout.strip().splitlines()[0].rstrip(",").split(",")
        if len(actual) != len(rows):
            raise AssertionError(f"Bend printed {len(actual)} codes for {len(rows)} cases")
        for got, (_, want, (name, row)) in zip(actual, rows):
            if int(got) != want:
                raise AssertionError(f"twin mismatch {name}{tuple(str(v) for v in row)}: "
                                     f"bend={got} python={want}")
    return len(rows)


def bend_available():
    return bool(os.environ.get("BEND")) and bool(os.environ.get("LEAN_BIN"))


def main():
    from bend_verifier import verifier_environment
    with verifier_environment(DOMAIN) as (bend, env):
        count = run_parity(bend, env)
    print(f"z0 keepworking: {count} exhaustive Bend/Python kernel cases match")


if __name__ == "__main__":
    main()
