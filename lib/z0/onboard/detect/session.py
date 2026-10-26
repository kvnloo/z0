"""Desktop session, audio input, systemd --user, linger, launchd (§4)."""
from __future__ import annotations


def detect(ctx, os_name: str) -> dict:
    env = ctx.env
    if os_name == "darwin":
        return {"desktop": "aqua", "audio_in": False, "systemd_user": False, "linger": False,
                "launchd": True}
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        desktop = "hyprland"
    elif env.get("WAYLAND_DISPLAY") or env.get("XDG_SESSION_TYPE") == "wayland":
        desktop = "wayland"
    elif env.get("DISPLAY") or env.get("XDG_SESSION_TYPE") == "x11":
        desktop = "x11"
    else:
        desktop = "none"
    sources = ctx.run(["pactl", "list", "short", "sources"])
    audio_in = any(line.strip() and ".monitor" not in line for line in sources.out.splitlines())
    if not audio_in:
        audio_in = "card" in ctx.run(["arecord", "-l"]).out
    state = ctx.run(["systemctl", "--user", "is-system-running"]).out.strip()
    user = env.get("USER") or env.get("LOGNAME") or ""
    linger = False
    if user:
        linger = "Linger=yes" in ctx.run(["loginctl", "show-user", user, "-p", "Linger"]).out
    return {"desktop": desktop, "audio_in": bool(audio_in),
            "systemd_user": state in ("running", "degraded", "starting"),
            "linger": linger, "launchd": False}
