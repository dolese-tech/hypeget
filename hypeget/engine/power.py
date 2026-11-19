"""'When all downloads finish' actions: put the PC to sleep or shut it down."""
from __future__ import annotations

import subprocess
import sys


def command(action: str) -> list[str] | None:
    """The OS command for a power action, or None if unsupported here."""
    if sys.platform.startswith("win"):
        if action == "shutdown":
            return ["shutdown", "/s", "/t", "0", "/c", "HyperGet: all downloads finished"]
        if action == "sleep":
            # SetSuspendState(hibernate=0, force=1, wakeEventsDisabled=0)
            return ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
    elif sys.platform == "darwin":
        if action == "shutdown":
            return ["osascript", "-e", 'tell app "System Events" to shut down']
        if action == "sleep":
            return ["pmset", "sleepnow"]
    else:
        if action == "shutdown":
            return ["systemctl", "poweroff"]
        if action == "sleep":
            return ["systemctl", "suspend"]
    return None


def run(action: str) -> bool:
    cmd = command(action)
    if not cmd:
        return False
    try:
        subprocess.Popen(cmd)  # noqa: S603
        return True
    except OSError:
        return False
