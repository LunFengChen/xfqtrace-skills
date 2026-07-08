from __future__ import annotations

import json
import queue
import threading
import urllib.request
from importlib import resources
from typing import Any

from packaging.version import InvalidVersion, Version

CHANNEL_URL = "https://raw.githubusercontent.com/LunFengChen/xfqtrace-skills/main/src/xfqtrace_skills/channels/stable.json"


def local_channel() -> dict[str, Any]:
    path = resources.files("xfqtrace_skills").joinpath("channels", "stable.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_worker(out: "queue.Queue[tuple[dict[str, Any] | None, str | None]]", timeout: float) -> None:
    try:
        with urllib.request.urlopen(CHANNEL_URL, timeout=timeout) as resp:
            out.put((json.loads(resp.read().decode("utf-8")), None))
    except Exception as exc:
        out.put((None, str(exc)))


def fetch_remote_channel(timeout: float = 2.0) -> tuple[dict[str, Any] | None, str | None]:
    """Fast remote check; never waits longer than roughly timeout seconds."""
    out: "queue.Queue[tuple[dict[str, Any] | None, str | None]]" = queue.Queue(maxsize=1)
    worker = threading.Thread(target=_fetch_worker, args=(out, timeout), daemon=True)
    worker.start()
    try:
        return out.get(timeout=timeout)
    except queue.Empty:
        return None, f"timeout after {timeout:.1f}s"


def fetch_channel(timeout: float = 2.0) -> dict[str, Any]:
    channel, _ = fetch_remote_channel(timeout=timeout)
    return channel or local_channel()


def newer(remote: str | None, current: str | None) -> bool:
    if not remote or not current:
        return False
    try:
        return Version(str(remote)) > Version(str(current))
    except InvalidVersion:
        return str(remote) != str(current)
