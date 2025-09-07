"""
Simplified Post‑Game Poker Study Library
======================================

This module defines a minimal set of classes and functions used by
the Streamlit app for post‑game poker study.  Unlike earlier versions
that attempted full optical character recognition and complex parsing,
this version relies entirely on user‑provided inputs.  It keeps the
application lightweight so it runs reliably on limited hosting
environments such as Streamlit Community Cloud.

Key components:

  • HandState dataclass: captures all of the relevant details for a
    single decision point in a poker tournament.

  • general_concept_analysis: uses high‑level poker heuristics to
    generate guidance based on stack size, position and hand strength.
    The intent is to provide solver‑style insights without computing
    precise ranges or running a real solver.

The functions here are deliberately simple.  If you wish to add
additional logic (for example, deeper ICM adjustments or more
hand categories), you can extend the classification rules within
general_concept_analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class HandState:
    """Representation of a decision point in a poker tournament.

    Each attribute corresponds to a typical piece of information
    required to make a decision.  Missing values (None or empty
    strings) are permitted, allowing users to supply only the
    information they know.
    """
    hero_hand: str
    position: str
    effective_bb: float
    opener: str
    board: Optional[List[str]] = None
    pot: Optional[float] = None
    players_left: Optional[int] = None
    action_history: Optional[str] = None
    buy_in: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def classify_stack_bucket(bb: float) -> str:
    if bb <= 10:
        return "short"
    if bb <= 25:
        return "medium"
    return "deep"


def determine_position_group(pos: str) -> str:
    pos = pos.upper()
    early_positions = {"UTG", "UTG1", "UTG2", "HJ"}
    late_positions = {"CO", "BTN"}
    blinds = {"SB", "BB"}
    if pos in early_positions:
        return "early"
    if pos in late_positions:
        return "late"
    if pos in blinds:
        return "blinds"
    return "middle"


def hand_class(hand: str) -> str:
    """Classify a two‑card poker hand into broad categories."""
    h = hand.upper().strip()
    # Remove suited/offsuit suffix
    rank_part = h.rstrip("OS")
    # Pairs
    if len(rank_part) == 2 and rank_part[0] == rank_part[1]:
        if rank_part in {"AA", "KK", "QQ"}:
            return "premium"
        elif rank_part in {"JJ", "TT", "99", "88", "77"}:
            return "strong pair"
        else:
            return "small pair"
    # Ace‑king and Ace‑queen
    if rank_part in {"AK", "AQ"}:
        return "premium"
    # Strong broadways
    if rank_part in {"KQ", "QJ", "JT", "JQ", "KJ"}:
        return "strong broadway"
    # Suited connectors / one‑gappers (approximate)
    connectors = {"98", "87", "76", "65", "54"}
    if rank_part in connectors or rank_part[::-1] in connectors:
        return "suited connector"
    # Default case
    return "weak offsuit"


def general_concept_analysis(state: HandState) -> str:
    """Generate a strategy note based on basic heuristics.

    This helper constructs a narrative around the stack depth,
    position category and hand class.  It also incorporates
    ICM (Independent Chip Model) considerations based on the
    number of players remaining.  The result is a sentence
    describing typical solver tendencies without providing
    explicit frequencies.
    """
    bucket = classify_stack_bucket(state.effective_bb)
    pos_group = determine_position_group(state.position)
    hand_type = hand_class(state.hero_hand)
    # Stack depth note
    if bucket == "short":
        base = "At short stacks (≤10bb), jam or fold decisions dominate; flatting is rare."
    elif bucket == "medium":
        base = "At medium stacks (10–25bb), jam/fold plays are common, but small raises and occasional flats may appear."
    else:
        base = "At deep stacks (≥25bb), a wider range of actions (open, 3‑bet, flat) becomes viable."
    # Position note
    if pos_group == "early":
        position_note = "Being in an early position, ranges are tighter and dominated by premiums and strong broadways."
    elif pos_group == "late":
        position_note = "In a late position, ranges widen considerably, adding suited connectors and weaker broadways."
    elif pos_group == "blinds":
        position_note = "In the blinds, one often defends a wide range against opens but must be cautious when out of position."
    else:
        position_note = "From a middle position, one plays a moderately tight range with selected speculative hands."
    # Hand type note
    if hand_type == "premium":
        hand_note = "Premium hands almost always justify aggressive actions: raising or jamming."
    elif hand_type == "strong pair":
        hand_note = "Strong pairs are typically good for raising or jamming, especially against earlier position opens."
    elif hand_type == "small pair":
        hand_note = "Small pairs often become jam candidates at short stacks, or used for set mining at deeper stacks."
    elif hand_type == "strong broadway":
        hand_note = "Strong broadway hands are near the top of your opening range; solvers mix between calling, raising and folding based on ICM pressure."
    elif hand_type == "suited connector":
        hand_note = "Suited connectors gain value in multi‑way pots and are more commonly played from late position with deeper stacks."
    else:
        hand_note = "Weaker offsuit hands are typically folded except when defending the big blind or exploiting short stacks."
    # ICM note
    icm_note = ""
    if state.players_left is not None and state.players_left > 0:
        if state.players_left <= 6:
            icm_note = "ICM pressure is high; survival is prioritized over chip accumulation."
        elif state.players_left <= 18:
            icm_note = "ICM pressure is moderate; balance chip accumulation with survival."
        else:
            icm_note = "ICM pressure is low; chip accumulation is prioritized over survival."
    return f"{base} {position_note} {hand_note} {icm_note}".strip()
