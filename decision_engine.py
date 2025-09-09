"""
Decision Engine for Tournament Poker
===================================

This module houses the logic for producing solver-style
recommendations based on tournament context and a simple range
database.  It does not compute equilibrium strategies on the fly;
instead, it looks up precomputed actions from a CSV table and
applies coarse adjustments for ICM, PKO format and other
tournament-specific factors.

The CSV file ``ranges/preflop_balanced_example.csv`` defines
recommendations for a handful of common scenarios.  Each row has
columns:

    position,stack_bb_bucket,vs_situation,hand_class,action,size

Where:
  • ``position`` is one of {UTG, HJ, CO, BTN, SB, BB}.
  • ``stack_bb_bucket`` is one of {<10,10-20,20-40,40+}.
  • ``vs_situation`` describes the preflop action so far (e.g.
    ``unopened``, ``vs_open``).  For this simple example only
    ``unopened`` and ``vs_minraise`` are used.
  • ``hand_class`` matches categories defined in
    ``poker_study_tool.hand_class``.
  • ``action`` is one of {Open, Jam, Fold, Call, Raise}.  Fold is
    used when not opening; Open means raise first in.
  • ``size`` is a human-readable description such as ``Jam`` or
    ``2.2bb``.

If no exact match is found, the engine falls back to general
concept notes from ``poker_study_tool.general_concept_analysis``.
"""

from pathlib import Path
from __future__ import annotations

import csv
import os
from typing import Dict, Tuple, Optional
import pandas as pd

from poker_study_tool import hand_class, general_concept_analysis, HandState


def find_range_csv() -> str:
    """Try common locations for the preflop CSV."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "ranges" / "preflop_balanced_example.csv",
        here.parent / "ranges" / "preflop_balanced_example.csv",
        Path.cwd() / "ranges" / "preflop_balanced_example.csv",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    raise FileNotFoundError(
        "Could not find ranges/preflop_balanced_example.csv"
    )


def load_ranges(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load the preflop range table into a DataFrame."""
    if csv_path is None:
        csv_path = find_range_csv()
    df = pd.read_csv(csv_path)
    df = df.set_index(['position', 'stack_bb_bucket', 'vs_situation', 'hand_class'])
    return df
