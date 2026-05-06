"""Pick an Android device from currently-running adb devices.

Strategy: prefer the last-used serial if it's still online, otherwise the first
online device reported by `adb devices`. The chosen serial is persisted to
`data/last_device.txt` so subsequent runs prefer it.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

_LAST_DEVICE_FILE = Path(__file__).resolve().parent.parent / "data" / "last_device.txt"


def list_online_devices() -> List[str]:
    """Return serials of devices currently in the `device` state."""
    adb = shutil.which("adb")
    if not adb:
        return []
    try:
        result = subprocess.run(
            [adb, "devices"], capture_output=True, text=True, timeout=10, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    serials: List[str] = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def _read_last_device() -> Optional[str]:
    try:
        return _LAST_DEVICE_FILE.read_text().strip() or None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _write_last_device(serial: str) -> None:
    try:
        _LAST_DEVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_DEVICE_FILE.write_text(serial + "\n")
    except OSError:
        pass


def pick_android_device() -> Optional[str]:
    """Pick a serial from online devices: last-used if still online, else first.

    Persists the chosen serial to `data/last_device.txt`.
    Returns None if no devices are online.
    """
    online = list_online_devices()
    if not online:
        return None
    last = _read_last_device()
    chosen = last if last in online else online[0]
    _write_last_device(chosen)
    return chosen
