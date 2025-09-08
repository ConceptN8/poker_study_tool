"""
Decision Engine for Tournament Poker
===================================

This module houses the logic for producing solver‑style
recommendations based on tournament context and a simple range
database.  It does not compute equilibrium strategies on the fly;
instead, it looks up precomputed actions from a CSV table and
applies coarse adjustments for ICM, PKO format and other
tournament‑specific factors.

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
  • ``size`` is a human‑readable description such as ``Jam`` or
    ``2.2bb``.

If no exact match is found, the engine falls back to general
concept notes from ``poker_study_tool.general_concept_analysis``.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, Tuple, Optional

import pandas as pd

from poker_study_tool import hand_class, general_concept_analysis, HandState


def load_ranges(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load the preflop range table into a DataFrame.

    If ``csv_path`` is not provided, the default example table
    ``ranges/preflop_balanced_example.csv`` is used.  The DataFrame
    indexes rows by (position, stack_bb_bucket, vs_situation, hand_class).
    """
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ranges', 'preflop_balanced_example.csv')
    df = pd.read_csv(csv_path)
    df = df.set_index(['position', 'stack_bb_bucket', 'vs_situation', 'hand_class'])
    return df


_RANGE_TABLE: Optional[pd.DataFrame] = None


def get_range_table() -> pd.DataFrame:
    global _RANGE_TABLE
    if _RANGE_TABLE is None:
        _RANGE_TABLE = load_ranges()
    return _RANGE_TABLE


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
    """Compute a simple ICM pressure coefficient based on tournament metadata.

    The coefficient is a multiplier applied to the aggressiveness of
    recommendations.  Values >1 tighten ranges; values <1 loosen
    them.  The calculation considers:

      • players_left and places_paid: distance to the money bubble.
      • re‑entry availability: unlimited re‑entry lowers pressure.
      • bubble protection: reduces fear of busting for covered stacks.
      • bounty tournaments (PKO): loosens calling/jamming ranges slightly.
      • table type: 6‑max tables encourage wider steals and calls.

    Any missing key defaults to a neutral value (pressure = 1.0).
    """
    pressure = 1.0
    if not meta:
        return pressure
    # Distance to bubble: fewer players left relative to places paid → higher pressure
    try:
        players_left = None
        # players_left may be provided as "17/28" or just a number
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
        # Ignore errors in parsing
        pass
    # Re‑entry loosens play because chips are less valuable
    reentry = str(meta.get('reentry', '')).lower()
    if 'unlimited' in reentry or 'multi' in reentry:
        pressure *= 0.9
    # Bubble protection reduces risk of busting for covered stacks
    if meta.get('bubble_protection'):
        pressure *= 0.95
    # Progressive bounty tournaments encourage looser calls to win bounties
    # meta may contain bounty_flag or is_pko from OCR or UI
    if meta.get('bounty_flag') or meta.get('is_pko'):
        pressure *= 0.95
    # Table type: 6‑max or 7‑max tables typically play looser than 9‑max
    tt = meta.get('table_type')
    if isinstance(tt, str):
        if tt.strip().startswith('6'):
            pressure *= 0.95
        elif tt.strip().startswith('7'):
            pressure *= 0.98
    return pressure


def recommend_preflop(state: HandState, meta: Dict[str, Optional[str]]) -> Tuple[str, str, str]:
    """Return a tuple (action, size, note) for a preflop hand.

    ``state`` holds the basic hand information (hero hand, position,
    effective stack, opener description), while ``meta`` contains
    tournament metadata parsed from screenshots or entered by the
    user.  The function looks up the appropriate action/size pair in
    the range table and applies a pressure adjustment.  It returns
    the recommended action, the suggested bet size (as a string)
    and a short rationale.
    """
    table = get_range_table()
    # Determine vs_situation: simple heuristic
    if not state.opener or state.opener.strip() == '':
        vs_situation = 'unopened'
    else:
        # If opener contains 'open' or 'raises'
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
        # Fallback to general concept note
        analysis = general_concept_analysis(state)
        return ("Unknown", "N/A", analysis)
    # Apply ICM pressure adjustments: if pressure >1, tighten jam sizes to calls or fold
    pressure = compute_icm_pressure(meta)
    if pressure > 1.1:
        # tighten: if jam, downgrade to open; if open, downgrade size; if call, leave
        if action.lower() == 'jam':
            action = 'Open'
            size = '2.2bb'
            note += " Adjusted to smaller open due to ICM pressure."
        elif action.lower() == 'open':
            # reduce size from e.g. 2.5bb to 2.2bb
            if size.endswith('bb'):
                try:
                    val = float(size.rstrip('bb'))
                    new_val = max(2.0, val - 0.3)
                    size = f"{new_val:.1f}bb"
                except ValueError:
                    pass
            note += " Slightly reduced open size under ICM pressure."
    elif pressure < 0.95:
        # loosen: if fold or open, upgrade to jam for short stacks
        if action.lower() in {'fold', 'call'} and state.effective_bb < 12:
            action = 'Jam'
            size = 'Jam'
            note += " Loosened to jam due to low ICM pressure."
    return (action, size, note)