"""Desktop session, audio input, systemd --user, linger, launchd (§4)."""
from __future__ import annotations

import os


def _audio_in(ctx) -> bool:
    """A capture device, found without side effects (law P0).

    1. /proc/asound/pcm lists every ALSA PCM; a `capture` line is an input. No process.
    2. `pactl` only when a PulseAudio/PipeWire socket already exists at
       $XDG_RUNTIME_DIR/pulse/native. Without one (ssh, cron, containers) libpulse
       falls back to ~/.config/pulse and writes a runtime link there and a dir in /tmp,
       so pactl is never run then.
    3. `arecord -l` (reads ALSA, writes nothing).
    """
    pcm = ctx.read_text(ctx.sys("/proc/asound/pcm")) or ""
    if any("capture" in line for line in pcm.splitlines()):
        return True
    runtime = ctx.env.get("XDG_RUNTIME_DIR") or ""
    if runtime and os.path.isabs(runtime) and ctx.lexists(ctx.expand(os.path.join(runtime, "pulse", "native"))):
        sources = ctx.run(["pactl", "list", "short", "sources"])
        if any(line.strip() and ".monitor" not in line for line in sources.out.splitlines()):
            return True
    return "card" in ctx.run(["arecord", "-l"]).out


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
    audio_in = _audio_in(ctx)
    state = ctx.run(["systemctl", "--user", "is-system-running"]).out.strip()
    user = env.get("USER") or env.get("LOGNAME") or ""
    linger = False
    if user:
        linger = "Linger=yes" in ctx.run(["loginctl", "show-user", user, "-p", "Linger"]).out
    return {"desktop": desktop, "audio_in": bool(audio_in),
            "systemd_user": state in ("running", "degraded", "starting"),
            "linger": linger, "launchd": False}
