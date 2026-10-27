#!/usr/bin/env python3
"""ExecStartPre for dash-bridge.service (written by `z0 onboard`): wait until this
host's tailnet IPv4 equals DASH_HOST, so the bridge never binds anywhere else.
Exit 0 when it matches; exit 1 after the deadline (systemd retries the unit)."""
import os
import shutil
import subprocess
import sys
import time

want = os.environ.get("DASH_HOST", "")
deadline = time.monotonic() + float(os.environ.get("DASH_WAIT_TAILNET_S", "90"))
tailscale = shutil.which("tailscale")
while True:
    got = ""
    if tailscale:
        try:
            got = subprocess.run([tailscale, "ip", "-4"], capture_output=True, text=True,
                                 timeout=10).stdout.split()[0:1]
            got = got[0] if got else ""
        except (OSError, subprocess.SubprocessError):
            got = ""
    if want and got == want:
        sys.exit(0)
    if time.monotonic() > deadline:
        print("dash-wait-tailnet: the tailnet IPv4 does not match DASH_HOST yet", file=sys.stderr)
        sys.exit(1)
    time.sleep(3)
