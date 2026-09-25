#!/usr/bin/env python3
"""Stranger-machine acceptance: install the wheel, then pack, install, restore.

Delegates to ``scripts/operator_acceptance.py``, which refuses to run against
an editable checkout. Build artifacts first (``scripts/build_release.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.operator_acceptance import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
