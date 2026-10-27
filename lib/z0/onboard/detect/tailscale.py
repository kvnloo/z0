"""Tailscale (§4): the IPv4 must be in 100.64.0.0/10 and comes only from this detection
(H2). From `status --json` only Self.TailscaleIPs, Self.DNSName and BackendState are read."""
from __future__ import annotations

import ipaddress
import json

CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _tailnet_ipv4(text: str):
    for line in (text or "").split():
        try:
            ip = ipaddress.ip_address(line.strip())
        except ValueError:
            continue
        if ip.version == 4 and ip in CGNAT:
            return str(ip)
    return None


def detect(ctx) -> dict:
    if not ctx.which("tailscale"):
        return {"installed": False, "logged_in": False}
    out: dict = {"installed": True, "logged_in": False}
    ip = _tailnet_ipv4(ctx.run(["tailscale", "ip", "-4"]).out)
    status = ctx.run(["tailscale", "status", "--json"])
    try:
        data = json.loads(status.out) if status.ok else {}
    except ValueError:
        data = {}
    if isinstance(data, dict):
        out["logged_in"] = data.get("BackendState") == "Running"
        self_node = data.get("Self") if isinstance(data.get("Self"), dict) else {}
        if not ip:
            ip = _tailnet_ipv4(" ".join(str(x) for x in self_node.get("TailscaleIPs") or []))
        dns = str(self_node.get("DNSName") or "").rstrip(".")
        if dns:
            out["magicdns"] = dns
    if ip and out["logged_in"]:
        out["ipv4"] = ip
    return out
