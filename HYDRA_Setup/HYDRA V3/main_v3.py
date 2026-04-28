# -*- coding: utf-8 -*-
"""HYDRA V3 — root entry point (laptop-friendly).

Runs locally with Python 3.10+. No Docker, no VPS — just:

    cd hydra-v3
    .\.venv\Scripts\python.exe main_v3.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Hand off to the engine loop.
from engine.v3 import main_v3  # noqa: F401  (executes the loop on import)
