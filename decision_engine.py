"""
Decision Engine for Tournament Poker
===================================

This module houses the logic for producing solver-style recommendations
based on tournament context and a simple range database. It looks up
precomputed actions from a CSV table and applies coarse adjustments
for ICM, PKO format and other tournament-specific factors.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
from typing import Dict, Tuple, Optional

from poker_study_tool import hand_class, general_concept_analysis, HandState


# Locate CSV in several likely locations
def find_range_csv() -> str:
    here = Path(__file__).resolve().parent
    for candidate in [
        here / "ranges" / "preflop_balanced_example.csv",
        here.parent / "ranges" / "preflop_balanced_example.csv",
        Path.cwd() / "ranges" / "preflop_balanced_example.csv",
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("ranges/preflop_balanced_example.csv not found")


# Load preflop ranges into DataFrame and cache it
_range_table: Optional[pd.DataFrame] = None

def load_ranges(csv_path: Optional[str] = None) -> pd.DataFrame:
    if csv_path is None:
        csv_path = find_range_csv()
    df = pd.read_csv(csv_path)
    df = df.set_index(['position','stack_bb_bucket','vs_situation','hand_class'])
    return df

def get_range_table() -> pd.DataFrame:
    global _range_table
    if _range_table is None:
        _range_table = load_ranges()
    return _range_table


# Map stack size to bucket string used in CSV
def compute_stack_bucket(bb: float) -> str:
    if bb < 10: return '<10'
    if bb < 20: return '10-20'
    if bb < 40: return '20-40'
    return '40+'


# Simple ICM pressure coefficient
def compute_icm_pressure(meta: Dict[str, Optional[str]]) -> float:
    pressure = 1.0
    if not meta:
        return pressure
    try:
        players_left, places_paid = None, int(meta.get('places_paid', 0))
        pl = meta.get('players_left')
        if isinstance(pl, str) and '/' in pl:
            players_left = int(pl.split('/')[0].strip())
        elif pl is not None:
            players_left = int(float(pl))
        if players_left is not None and places_paid:
            distance = players_left - places_paid
            if distance <= 6: pressure *= 1.2
            elif distance <= 18: pressure *= 1.1
    except Exception:
        pass

    reentry = str(meta.get('reentry','')).lower()
    if 'unlimited' in reentry or 'multi' in reentry:
        pressure *= 0.9
    if meta.get('bubble_protection'): pressure *= 0.95
    if meta.get('bounty_flag') or meta.get('is_pko'): pressure *= 0.95
    tt = meta.get('table_type')
    if isinstance(tt,str):
        if tt.strip().startswith('6'): pressure *= 0.95
        elif tt.strip().startswith('7'): pressure *= 0.98
    return pressure


# Main logic: return (action, size, note)
def recommend_preflop(state: HandState, meta: Dict[str, Optional[str]]) -> Tuple[str,str,str]:
    table = get_range_table()
    vs_situation = 'unopened'
    if state.opener and any(word in state.opener.lower() for word in ['open','raise']):
        vs_situation = 'vs_open'

    bucket = compute_stack_bucket(state.effective_bb)
    h_class = hand_class(state.hero_hand)
    key = (state.position, bucket, vs_situation, h_class)

    if key in table.index:
        row = table.loc[key]
        action, size = row['action'], row['size']
        note = f"Matched {h_class} at {state.effective_bb}bb in {state.position} vs {vs_situation}."
    else:
        analysis = general_concept_analysis(state)
        return ("Unknown","N/A",analysis)

    pressure = compute_icm_pressure(meta)
    if pressure > 1.1:
        if action.lower() == 'jam':
            action, size = 'Open', '2.2bb'
            note += " Adjusted to smaller open due to ICM."
        elif action.lower() == 'open' and size.endswith('bb'):
            try:
                val = float(size.rstrip('bb'))
                size = f"{max(2.0, val-0.3):.1f}bb"
            except:
                pass
            note += " Slightly reduced open size under ICM."
    elif pressure < 0.95:
        if action.lower() in {'fold','call'} and state.effective_bb < 12:
            action = size = 'Jam'
            note += " Loosened to jam due to low ICM."

    return action, size, note
