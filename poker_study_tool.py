"""
Post‑Game Poker Study Tool (Prototype)
====================================

This module implements a prototype for a browser‑based post‑game poker
study tool.  The goal of the project is to help players review
their tournament hands after the session is complete.  It provides
functions to extract hand information from screenshots (using a
placeholder OCR implementation), convert that data into a structured
format, generate high‑level analysis notes based on general poker
concepts, and record the player's actual decision for later review.

The tool is designed for educational purposes only; it is not
intended for real‑time assistance during play.  The functions here
represent a starting point for building a web application (for
example, with Streamlit) and can be extended or integrated into a
full stack solution that runs in the browser.

Key components:
  • `ocr_image`: Extracts textual information from a screenshot of
    a poker table.  In this prototype, the function returns dummy
    values.  In a production system you would integrate OpenCV
    preprocessing and pytesseract for OCR.
  • `parse_hand_state`: Normalizes OCR output into a `HandState`
    data structure.
  • `general_concept_analysis`: Generates a human‑readable note
    describing solver‑style concepts based on stack size, position
    and hand class.  These rules come from commonly known poker
    strategy and are intentionally high‑level.
  • `StudySession`: A class that stores hands, allows entry of
    the player's choice after reviewing the analysis, and supports
    the hidden/reveal workflow.

To run a simple CLI demonstration, execute this module directly.  It
will prompt the user to enter hand data, show the concept analysis,
and then ask for the player's actual action.

This code requires Python 3.7+.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HandState:
    """Represents the key elements of a poker decision point.

    Attributes:
        hero_hand: Two‑card string such as "QJo".  Use 'o'/'s' suffix
            for offsuit/suited; uppercase for ranks; optional.
        position: The player's table position (UTG, HJ, CO, BTN, SB, BB).
        effective_bb: Effective stack depth in big blinds.
        opener: A description of the opponent's action prompting the decision.
        board: Optional list of board cards (flop, turn, river) as
            uppercase two‑character strings, e.g. ["7c","8d","2s"].
        pot: Optional pot size in chips.
    """

    hero_hand: str
    position: str
    effective_bb: float
    opener: str
    board: Optional[list[str]] = None
    pot: Optional[float] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ---------------------------------------------------------------------------
# OCR processing (placeholder implementation)
# ---------------------------------------------------------------------------

def ocr_image(image_path: str) -> Dict[str, str]:
    """Extract hand information from a screenshot image.

    This helper attempts to use OpenCV and pytesseract to perform
    optical character recognition on a poker table screenshot.  In a
    production system, you would crop specific regions (such as the
    hero's cards, the community board, and bet boxes) and apply OCR
    separately to each.  Here we attempt a naive full‑frame OCR and
    fall back to dummy values if the required libraries are not
    available or OCR fails.

    Args:
        image_path: Path to the screenshot file on disk.

    Returns:
        A dictionary with keys like 'hero_hand', 'position',
        'effective_bb', 'opener', 'board', and 'pot'.  If OCR is not
        available, the values will be filled with placeholders to allow
        downstream processing.
    """
    # Attempt to import OCR libraries
    try:
        import cv2  # type: ignore
        import pytesseract  # type: ignore

        # Load and pre‑process the image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Unable to read image: {image_path}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Simple thresholding to improve contrast
        try:
            import numpy as np  # type: ignore

            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed = thresh
        except Exception:
            processed = gray
        # Run OCR on the entire image
        raw_text = pytesseract.image_to_string(processed)
        # Very naive parsing: split the text by whitespace and try to
        # extract tokens that look like cards (two characters with
        # rank/suit) and numbers.  This is not robust but may serve
        # as a starting point.  Users are encouraged to replace this
        # with a more sophisticated parser.
        tokens = raw_text.split()
        # Find potential hero hand (two cards separated by space or not)
        hero_cards = []
        for tok in tokens:
            if len(tok) == 2 and tok[0].upper() in "AKQJT98765432" and tok[1].lower() in "shdc":
                hero_cards.append(tok)
            elif len(tok) == 4 and all(c.upper() in "AKQJT98765432" for c in tok[::2]):
                # e.g. 'QhJs' or 'AhKd'
                hero_cards.append(tok[:2])
                hero_cards.append(tok[2:])
        hero_hand = "".join(hero_cards[:2])
        # As a placeholder, guess position and opener from keywords
        position = ""  # Unknown in naive OCR
        opener = ""  # Unknown in naive OCR
        # Attempt to find numbers for stacks and pot
        numbers = [tok for tok in tokens if tok.replace('.', '', 1).isdigit()]
        effective_bb = numbers[0] if numbers else ""
        pot = numbers[1] if len(numbers) > 1 else ""
        # Attempt to find board cards (three or more tokens like '7c', etc.)
        board_cards = [tok for tok in tokens if len(tok) == 2 and tok[0].upper() in "AKQJT98765432" and tok[1].lower() in "shdc"]
        # Remove hero cards from board if overlapped
        board = [c for c in board_cards if c not in hero_cards][:5]
        return {
            "hero_hand": hero_hand or "",
            "position": position or "",
            "effective_bb": effective_bb or "",
            "opener": opener or "",
            "board": " ".join(board) or "",
            "pot": pot or "",
            "raw_text": raw_text,
        }
    except Exception:
        # Fallback dummy values for environments without OCR
        return {
            "hero_hand": "QJo",
            "position": "CO",
            "effective_bb": "15",
            "opener": "HJ opens 2.2bb",
            "board": "7c 8d 2s",
            "pot": "5500",
        }


def parse_hand_state(ocr_output: Dict[str, str]) -> HandState:
    """Convert OCR results into a HandState object.

    The OCR pipeline returns all values as strings; this function
    normalizes numeric fields and splits board cards into a list.

    Args:
        ocr_output: A dictionary of string values from ocr_image.

    Returns:
        A HandState instance with parsed values.
    """
    board_str = ocr_output.get("board") or ""
    board = [c.strip() for c in board_str.split() if c.strip()] or None

    # Convert numeric fields if possible
    def to_float(value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    return HandState(
        hero_hand=ocr_output.get("hero_hand", ""),
        position=ocr_output.get("position", ""),
        effective_bb=to_float(ocr_output.get("effective_bb")) or 0.0,
        opener=ocr_output.get("opener", ""),
        board=board,
        pot=to_float(ocr_output.get("pot")),
    )


# ---------------------------------------------------------------------------
# General concept analysis
# ---------------------------------------------------------------------------

def classify_stack_bucket(bb: float) -> str:
    if bb <= 10:
        return "short"
    if bb <= 25:
        return "medium"
    return "deep"


def determine_position_group(pos: str) -> str:
    # Map specific positions to general groups
    early_positions = {"UTG", "UTG1", "UTG2", "HJ"}
    late_positions = {"CO", "BTN"}
    blinds = {"SB", "BB"}
    if pos.upper() in early_positions:
        return "early"
    if pos.upper() in late_positions:
        return "late"
    if pos.upper() in blinds:
        return "blinds"
    return "middle"


def hand_class(hand: str) -> str:
    """Classify the hero hand into broad categories.

    Args:
        hand: Two‑card descriptor like "QJo" or "AKs".

    Returns:
        A string describing the class (e.g. 'premium', 'strong broadway',
        'small pair', 'suited connector', 'weak offsuit').
    """
    h = hand.upper()
    # Remove 'o'/'s' for easier matching
    rank_part = h.rstrip("OS")
    # Pairs
    if len(rank_part) == 2 and rank_part[0] == rank_part[1]:
        if rank_part in {"AA", "KK", "QQ"}:
            return "premium"
        elif rank_part in {"JJ", "TT", "99", "88", "77"}:
            return "strong pair"
        else:
            return "small pair"
    # Ace‑king / Ace‑queen hands
    if rank_part in {"AK", "AQ"}:
        return "premium"
    # Strong broadways
    if rank_part in {"KQ", "QJ", "JT", "JQ", "KJ"}:
        return "strong broadway"
    # Suited connectors and one‑gappers (approximate)
    connectors = {"98", "87", "76", "65", "54"}
    if rank_part[::-1] in connectors or rank_part in connectors:
        return "suited connector"
    # Default to weak offsuit
    return "weak offsuit"


def general_concept_analysis(state: HandState) -> str:
    """Generate a high‑level analysis note based on general poker concepts.

    This function uses simplified rules to describe typical solver
    behaviour without computing precise solutions.  It examines stack
    depth, position, and hand class to craft a suggestion.  Feel free
    to extend these rules for more nuance.

    Args:
        state: The HandState describing the decision.

    Returns:
        A human‑readable string summarizing high‑level strategy.
    """
    bucket = classify_stack_bucket(state.effective_bb)
    pos_group = determine_position_group(state.position)
    hand_type = hand_class(state.hero_hand)

    # Base statement on stack bucket
    if bucket == "short":
        base = "At short stacks (≤10bb), jam or fold decisions dominate; flatting is rare."
    elif bucket == "medium":
        base = "At medium stacks (10–25bb), jam/fold plays are common, but small raises and occasional flats may appear."
    else:
        base = "At deep stacks (≥25bb), a wider range of actions (open, 3‑bet, flat) becomes viable."

    # Position influences range tightness
    if pos_group == "early":
        position_note = "Being in an early position, ranges are tighter and dominated by premiums and strong broadways."
    elif pos_group == "late":
        position_note = "In a late position, ranges widen considerably, adding suited connectors and weaker broadways."
    elif pos_group == "blinds":
        position_note = "In the blinds, one often defends a wide range against opens but is cautious out of position."
    else:
        position_note = "From a middle position, one plays a moderately tight range with selected speculative hands."

    # Hand type specific notes
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

    return f"{base} {position_note} {hand_note}"


# ---------------------------------------------------------------------------
# Study session management
# ---------------------------------------------------------------------------

class StudySession:
    """Manages a collection of hands for study with hidden/reveal workflow."""

    def __init__(self) -> None:
        self.hands: Dict[str, Dict[str, Optional[str]]] = {}

    def add_hand(self, state: HandState) -> str:
        """Add a new hand without logging the player's action.

        The hand is stored with a unique identifier; the 'player_action'
        field is initially None.  Returns the ID for later updates.
        """
        hand_id = state.to_json()  # using JSON representation as unique key
        self.hands[hand_id] = {
            "state": state.to_json(),
            "analysis": general_concept_analysis(state),
            "player_action": None,
        }
        return hand_id

    def record_action(self, hand_id: str, action: str) -> None:
        """Record the player's actual action for a given hand."""
        if hand_id not in self.hands:
            raise KeyError("Unknown hand ID")
        self.hands[hand_id]["player_action"] = action

    def to_json(self) -> str:
        return json.dumps(self.hands, indent=2)


# ---------------------------------------------------------------------------
# CLI demonstration
# ---------------------------------------------------------------------------

def _demo_cli():
    """Simple command‑line interface for testing the hidden/reveal flow."""
    print("\nWelcome to the post‑game poker study tool prototype.\n")
    session = StudySession()
    while True:
        print("Enter hand details without your action.")
        hero_hand = input("Hero hand (e.g. QJo, AKs): ").strip()
        position = input("Position (UTG, HJ, CO, BTN, SB, BB): ").strip()
        effective_bb = float(input("Effective stack in bb: ").strip() or "0")
        opener = input("Describe the opener (e.g. HJ opens 2.2bb): ").strip()
        board = input("Board cards (space separated, e.g. 7c 8d 2s) or leave blank: ").strip()
        pot = input("Pot size (optional): ").strip()

        ocr_data = {
            "hero_hand": hero_hand,
            "position": position,
            "effective_bb": str(effective_bb),
            "opener": opener,
            "board": board,
            "pot": pot,
        }
        state = parse_hand_state(ocr_data)
        analysis = general_concept_analysis(state)
        print("\nGeneral concept analysis:")
        print(analysis)
        # Add to session
        hand_id = session.add_hand(state)
        print("\nEnter your actual action for this spot (e.g. jam, fold, call, raise):")
        action = input("Your action: ").strip()
        session.record_action(hand_id, action)

        cont = input("\nAdd another hand? (y/n): ").strip().lower()
        if cont != "y":
            break

    print("\nStudy session summary (JSON):")
    print(session.to_json())


if __name__ == "__main__":
    _demo_cli()