#!/usr/bin/env python3
"""
Launch the Cannon Defense crosshair overlay control panel.

Usage (from anywhere)::

    python path/to/CannonDefense/run_cannon_crosshair.py

Settings file: ``CannonDefense/crosshair_settings.json`` (created on first Save).

Dependencies: ``pip install -r CannonDefense/requirements.txt`` (Windows).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    root_dir = Path(__file__).resolve().parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    from overlay.crosshair_app import main as run_ui

    run_ui()


if __name__ == "__main__":
    main()
