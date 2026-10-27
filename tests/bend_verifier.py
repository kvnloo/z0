"""Compatibility import; the only verifier implementation lives in lib/laws."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'lib'))
from laws.verifier import FILES_SHA256, verifier_environment  # noqa: E402,F401
