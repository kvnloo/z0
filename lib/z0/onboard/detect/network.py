"""HTTPS reachability (§4): HEAD with a 3 s timeout, in parallel. Any HTTP answer counts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def detect(ctx) -> dict:
    probes = (ctx.registry.get("onboarding") or {}).get("network_probes") or {}
    if not probes:
        return {}
    names = sorted(probes)

    def head(name):
        try:
            return bool(ctx.http_head(probes[name], 3.0))
        except Exception:  # noqa: BLE001 - detectors never raise
            return False

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        return dict(zip(names, pool.map(head, names)))
