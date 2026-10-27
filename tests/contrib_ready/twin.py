"""Load the contrib_ready twin and generate Bend cases for every row it decides.

The expected column comes from scripts/contrib_ready.py; the actual column comes from
executing bend/contrib_ready/MODEL.bend through the pinned Bend. No host effects:
Bend runs in a temp dir with an isolated HOME (tests/bend_verifier.py).

Domains:
- every row of every finite function (contrib_ready.DOMAINS), exhaustively;
- whole matrices, bounded: the full REQUIRED matrix with each cell value, every
  single deviation and every pair of deviations from the all-pass matrix, and every
  shape change (a cell dropped, duplicated, swapped with its neighbour, a prefix, an
  extra cell, the reversed order), each under every blocker.
"""
from __future__ import annotations

from enum import Enum
import importlib.util
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "bend/contrib_ready"
SCRIPT = ROOT / "scripts/contrib_ready.py"
CHUNK = 150


def load(source=None, name="contrib_ready_twin"):
    """The twin as a module; `source` loads a textual mutant instead."""
    folder = None
    path = SCRIPT
    if source is not None:
        folder = tempfile.mkdtemp(prefix="z0-contrib-mutant-")
        path = Path(folder) / "contrib_ready_mutant.py"
        path.write_text(source)
        name = f"contrib_ready_mutant_{abs(hash(source))}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
    return module


cr = load()

# Bend-side encoder per result type (MODEL.bend).
CODER = {
    "counts": "code_bool", "classify": "code_cell", "merge_cell": "code_cell",
    "merge_blocker": "code_blocker", "decide_with": "code_status", "req_code": "",
    "is_ready": "code_bool",
}


def bend_arg(value):
    if isinstance(value, bool):
        return "True{}" if value else "False{}"
    if isinstance(value, Enum):
        return f"M.{value.value}{{}}"
    raise TypeError(f"no Bend encoding for {value!r}")


def bend_cells(cells):
    text = "M.KEnd{}"
    for req, cell in reversed(list(cells)):
        text = f"M.KCell{{{bend_arg(req)}, {bend_arg(cell)}, {text}}}"
    return text


def matrices(module=cr):
    """Bounded whole matrices: (label, cells), each distinct matrix once."""
    seen = set()
    for label, cells in _matrices(module):
        key = tuple(cells)
        if key not in seen:
            seen.add(key)
            yield label, cells


def _matrices(module):
    req, cell = module.REQUIRED, module.Cell
    passing = module.required_all(cell.PASS_CANDIDATE)
    for value in cell:
        yield f"all {value.name}", module.required_all(value)
    for i, value in itertools.product(range(len(req)), cell):
        if value is not cell.PASS_CANDIDATE:
            cells = list(passing)
            cells[i] = (req[i], value)
            yield f"one {value.name} at {i}", cells
    others = (cell.NONE, cell.PASS_OTHER_SHA)
    for (i, j), (a, b) in itertools.product(itertools.combinations(range(len(req)), 2),
                                            itertools.product(others, others)):
        cells = list(passing)
        cells[i], cells[j] = (req[i], a), (req[j], b)
        yield f"pair {a.name}@{i} {b.name}@{j}", cells
    for i in range(len(req)):
        yield f"drop {i}", passing[:i] + passing[i + 1:]
        yield f"duplicate {i}", passing[:i + 1] + passing[i:]
        yield f"prefix {i}", passing[:i]
        if i + 1 < len(req):
            yield f"swap {i}", passing[:i] + [passing[i + 1], passing[i]] + passing[i + 2:]
    yield "extra", passing + [passing[0]]
    yield "reversed", list(reversed(passing))


def cases(module=cr):
    """Yield (bend_expression, expected_code, label) for every row."""
    for name, domain in module.DOMAINS.items():
        coder = CODER[name]
        for row in itertools.product(*domain):
            call = f"M.{name}({', '.join(bend_arg(v) for v in row)})"
            expr = f"M.{coder}({call})" if coder else call
            yield expr, module.code(getattr(module, name)(*row)), (name, row)
    blockers = list(module.Blocker)
    for (label, cells), blocker in itertools.product(matrices(module), blockers):
        if label.startswith("pair") and blocker is not module.Blocker.NONE:
            continue  # blockers do not read cells (R3); the singles cover them
        expr = f"M.code_status(M.decide({bend_cells(cells)}, {bend_arg(blocker)}))"
        yield expr, module.code(module.decide(cells, blocker)), ("decide", (label, blocker))


def model_types(text):
    """Map each `type X is Data:` in MODEL.bend to its constructor names."""
    import re
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


def run_parity(bend, env, model_dir=DOMAIN, module=cr):
    """Return the number of matched rows; raise AssertionError on the first mismatch."""
    rows = list(cases(module))
    with tempfile.TemporaryDirectory(prefix="z0-contrib-twin-") as folder:
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
            actual = result.stdout.strip().splitlines()[0].rstrip(",").split(",")
            if len(actual) != len(chunk):
                raise AssertionError(f"Bend printed {len(actual)} codes for {len(chunk)} cases")
            for got, (_, want, (name, row)) in zip(actual, chunk):
                if int(got) != want:
                    raise AssertionError(f"twin mismatch {name}{row!r}: bend={got} python={want}")
    return len(rows)


def bend_available():
    return bool(os.environ.get("BEND")) and bool(os.environ.get("LEAN_BIN"))


def main():
    sys.path.insert(0, str(ROOT / "tests"))
    from bend_verifier import verifier_environment
    with verifier_environment(DOMAIN) as (bend, env):
        count = run_parity(bend, env)
    print(f"z0 contrib_ready: {count} Bend/Python cases match")


if __name__ == "__main__":
    main()
