"""
Decision Engine for Tournament Poker
===================================

This module houses the logic for producing solver-style
recommendations based on tournament context and a simple range
database. It does not compute equilibrium strategies on the fly;
instead, it looks up precomputed actions from a CSV table and
applies coarse adjustments for ICM, PKO format and other
tournament-specific factors.

The CSV file ``ranges/preflop_balanced_example.csv`` defines
recommendations for a handful of common scenarios. Each row has
columns:

    position,stack_bb_bucket,vs_situation,hand_class,action,size

Where:
  • ``position`` is one of {UTG, HJ, CO, BTN, SB, BB}.
  • ``stack_bb_bucket`` is one of {<10,10-20,20-40,40+}.
  • ``vs_situation`` describes the preflop action so far (e.g.
    ``unopened``, ``vs_open``). For this simple example only
    ``unopened`` and ``vs_minraise`` are used.
  • ``hand_class`` matches categories defined in
    ``poker_study_tool.hand_class``.
  • ``action`` is one of {Open, Jam, Fold, Call, Raise}.
  • ``size`` is a human-readable description such as ``Jam`` or
    ``2.2bb``.

If no exact match is found, the engine falls back to general
concept notes from ``poker_study_tool.general_concept_analysis``.
"""

from __future__ import annotations

from pathlib import Path
import csv
import os
from typing import Dict, Tuple, Optional

import pandas as pd

from poker_study_tool import hand_class, general_concept_analysis, HandState


# --- CSV path handling ---
def find_range_csv() -> str:
    """Try common locations for the preflop CSV file."""
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
        "Could not find ranges/preflop_balanced_example.csv in expected locations."
    )


# --- Load ranges into a DataFrame ---
def load_ranges(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load the preflop range table into a DataFrame."""
    if csv_path is None:
        csv_path = find_range_csv()
    df = pd.read_csv(csv_path)
    df = df.set_index(['position', 'stack_bb_bucket', 'vs_situation', 'hand_class'])
    return df


_RANGE_TABLE: Optional[pd.DataFrame] = None


def get_range_table() -> pd.DataFrame:
    """Cache and return the preflop range table."""
    global _RANGE_TABLE
    if _RANGE_TABLE is None:
        _RANGE_TABLE = load_ranges()
    return _RANGE_TABLE


# --- Helpers for bucket + ICM ---
def compute_stack_bucket(bb: float) -> str:
    """Map a stack size to a range bucket string used in the CSV."""
    if bb < 10:
        return '<10'
    if bb < 20:
        return '10-20'
    if bb < 40:
        return '20-40'
    return '40+'


def compute_icm_pressure(meta: Dict[str, Optional[str]]) -> float:
    """Compute a simple ICM pressure coefficient based on tournament metadata."""
    pressure = 1.0
    if not meta:
        return pressure

    try:
        players_left = None
        pl = meta.get('players_left')
        if isinstance(pl, str) and '/' in pl:
            players_left = int(pl.split('/')[0].strip())
        elif pl is not None:
            players_left = int(float(pl))
        places_paid = int(meta.get('places_paid', 0))
        if players_left is not None and places_paid > 0:
            distance = players_left - places_paid
            if distance <= 6:
                pressure *= 1.2
            elif distance <= 18:
                pressure *= 1.1
    except Exception:
        pass

    reentry = str(meta.get('reentry', '')).lower()
    if 'unlimited' in reentry or 'multi' in reentry:
        pressure *= 0.9

    if meta.get('bubble_protection'):
        pressure *= 0.95

    if meta.get('bounty_flag') or meta.get('is_pko'):
        pressure *= 0.95

    tt = meta.get('table_type')
    if isinstance(tt, str):
        if tt.strip().startswith('6'):
            pressure *= 0.95
        elif tt.strip().startswith('7'):
            pressure *= 0.98
    return pressure


# --- Main recommendation logic ---
def recommend_preflop(state: HandState, meta: Dict[str, Optional[str]]) -> Tuple[str, str, str]:
    """Return a tuple (action, size, note) for a preflop hand."""
    table = get_range_table()

    # Determine vs_situation
    if not state.opener or state.opener.strip() == '':
        vs_situation = 'unopened'
    else:
        if 'open' in state.opener.lower() or 'raise' in state.opener.lower():
            vs_situation = 'vs_open'
        else:
            vs_situation = 'unopened'

    bucket = compute_stack_bucket(state.effective_bb)
    h_class = hand_class(state.hero_hand)
    key = (state.position, bucket, vs_situation, h_class)

    if key in table.index:
        row = table.loc[key]
        action = row['action']
        size = row['size']
        note = f"Lookup match for {h_class} at {state.effective_bb}bb in {state.position} vs {vs_situation}."
    else:
        analysis = general_concept_analysis(state)
        return ("Unknown", "N/A", analysis)

    pressure = compute_icm_pressure(meta)
    if pressure > 1.1:
        if action.lower() == 'jam':
            action = 'Open'
            size = '2.2bb'
            note += " Adjusted to smaller open due to ICM pressure."
        elif action.lower() == 'open':
            if size.endswith('bb'):
                try:
                    val = float(size.rstrip('bb'))
                    new_val = max(2.0, val - 0.3)
                    size = f"{new_val:.1f}bb"
                except ValueError:
                    pass
            note += " Slightly reduced open size under ICM pressure."
    elif pressure < 0.95:
        if action.lower() in {'fold', 'call'} and state.effective_bb < 12:
            action = 'Jam'
            size = 'Jam'
            note += " Loosened to jam due to low ICM pressure."

    return (action, size, note)
