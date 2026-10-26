"""Generate exhaustive Bend cases for every kernel decide_* domain and run them.

The expected column comes from lib/z0/onboard/kernel.py; the actual column comes from
executing bend/onboard/MODEL.bend through the pinned Bend. No host effects: Bend runs
in a temp dir with an isolated HOME (tests/bend_verifier.py).
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
DOMAIN = ROOT / "bend/onboard"
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

from z0.onboard import kernel as k  # noqa: E402

# Bend-side encoder per decide_* result type (MODEL.bend).
CODER = {
    "decide_profile": "code_profile",
    "decide_torch_index": "code_index",
    "decide_replan": "code_replan",
}
CHUNK = 600


def bend_arg(value):
    if isinstance(value, bool):
        return "True{}" if value else "False{}"
    if isinstance(value, Enum):
        return f"M.{value.value}{{}}"
    raise TypeError(f"no Bend encoding for {value!r}")


def cases(kernel=k):
    """Yield (bend_expression, expected_code) for every row of every domain."""
    for name, domain in kernel.DOMAINS.items():
        coder = CODER.get(name, "code_verdict")
        for row in itertools.product(*domain):
            expr = f"M.{coder}(M.{name}({', '.join(bend_arg(v) for v in row)}))"
            yield expr, kernel.code(getattr(kernel, name)(*row)), (name, row)


def model_types(text):
    """Map each `type X is Data:` in MODEL.bend to its constructor names."""
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
    """Return the number of matched rows; raise AssertionError on the first mismatch."""
    rows = list(cases(kernel))
    with tempfile.TemporaryDirectory(prefix="z0-onboard-twin-") as folder:
        working = Path(folder)
        shutil.copy2(Path(model_dir) / "MODEL.bend", working / "MODEL.bend")
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start:start + CHUNK]
            (working / "cases.bend").write_text(bend_program([e for e, _, _ in chunk]))
            result = subprocess.run([bend, "cases.bend"], cwd=working, env=env,
                                    capture_output=True, text=True, timeout=1800)
            if result.returncode:
                raise RuntimeError("Bend twin execution failed: "
                                   + (result.stderr + result.stdout)[-2000:])
            actual = result.stdout.strip().rstrip(",").split(",")
            if len(actual) != len(chunk):
                raise AssertionError(f"Bend printed {len(actual)} codes for {len(chunk)} cases")
            for got, (_, want, (name, row)) in zip(actual, chunk):
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
    print(f"z0 onboard: {count} exhaustive Bend/Python kernel cases match")


if __name__ == "__main__":
    main()
