"""Execute a things:/// URL by shelling out to macOS `open`. Mockable seam."""

from __future__ import annotations

import subprocess


class RunnerError(Exception):
    """Executing the URL via `open` failed."""


def run_url(url: str) -> None:
    try:
        result = subprocess.run(
            ["open", "-g", url],
            capture_output=True,
        )
    except FileNotFoundError as exc:  # `open` missing → not macOS
        raise RunnerError(
            "The macOS `open` command was not found; this server runs on macOS only."
        ) from exc
    if result.returncode != 0:
        detail = getattr(result, "stderr", b"") or b""
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        raise RunnerError(f"`open` failed (exit {result.returncode}): {detail.strip()}")
