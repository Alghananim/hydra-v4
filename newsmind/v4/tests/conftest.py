"""Pytest config — add the project root to sys.path so `contracts`, `newsmind`
import without a package install.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
