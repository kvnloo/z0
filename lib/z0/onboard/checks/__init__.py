"""Component acceptance beyond the per-step checks (design §6.4, §8.1, §8.2).

Each module exports `evaluate(view) -> list[dict]`, one entry per named check:
`{"component", "name", "status": passed|failed|unavailable|skipped, "detail",
"required": bool, "warnings": [...]}`. `view` is a VerifyView (verify.py): the plan,
every step's result, the acceptance tiers, the journal and an ActionCtx for read-only
probes. Checks never write.
"""
from __future__ import annotations

from . import dash, z0, z0evals, z0intelligence

CHECKS = {"z0": z0.evaluate, "z0evals": z0evals.evaluate,
          "z0intelligence": z0intelligence.evaluate, "dash": dash.evaluate}

__all__ = ["CHECKS"]
