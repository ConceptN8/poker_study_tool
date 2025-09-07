"""
Simplified Streamlit Interface for Post‑Game Poker Study
=======================================================

This Streamlit application provides a lightweight, fully
browser‑based tool for reviewing hands after a poker tournament.
Users manually enter hand details rather than relying on OCR to
extract information from screenshots.  The app stores hands
in session state, generates high‑level strategic notes based on
general poker concepts, and offers quiz and review modes for
reinforcement learning.

To run this app locally:

    streamlit run streamlit_app.py

This version is intentionally minimal to run reliably on
Streamlit Community Cloud.
"""

import json
from typing import List

import streamlit as st

from poker_study_tool import HandState, general_concept_analysis


def get_session_hands() -> List[dict]:
    """Retrieve or initialize the list of hands in Streamlit session state."""
    if "hands" not in st.session_state:
        st.session_state["hands"] = []
    return st.session_state["hands"]


def main() -> None:
    st.set_page_config(page_title="Post‑Game Poker Study Tool", layout="wide")
    st.title("Post‑Game Poker Study Tool")

    menu = st.sidebar.selectbox(
        "Navigation",
        ["Analyse", "Quiz", "Review"],
        index=0,
    )
    if menu == "Analyse":
        render_analyse_page()
    elif menu == "Quiz":
        render_quiz_page()
    elif menu == "Review":
        render_review_page()


def render_analyse_page() -> None:
    st.header("Analyse a new hand")
    hands = get_session_hands()
    # Input fields
    hero_hand = st.text_input("Hero hand (e.g. QJo, AKs)")
    position = st.selectbox(
        "Position",
        ["UTG", "UTG1", "UTG2", "HJ", "CO", "BTN", "SB", "BB"],
        index=4,
    )
    effective_bb = st.number_input(
        "Effective stack (bb)", min_value=0.0, max_value=300.0, value=15.0, step=0.5
    )
    opener = st.text_input(
        "Opener (e.g. 'HJ opens 2.2bb', 'folded to you')",
        value=""
    )
    board_input = st.text_input(
        "Board cards (space separated, optional)", value=""
    )
    pot = st.number_input(
        "Pot size (optional)", min_value=0.0, value=0.0, step=0.5
    )
    players_left = st.number_input(
        "Number of players left (optional)", min_value=0, max_value=1000, value=0, step=1
    )
    buy_in = st.number_input(
        "Tournament buy‑in ($, optional)", min_value=0.0, value=0.0, step=0.1
    )
    action_history = st.text_input(
        "Action history (e.g. 'UTG opens 2bb, CO calls')", value=""
    )
    if st.button("Analyse hand"):
        # Build HandState
        board_cards = [card.strip() for card in board_input.split() if card.strip()] or None
        state = HandState(
            hero_hand=hero_hand,
            position=position,
            effective_bb=float(effective_bb),
            opener=opener,
            board=board_cards,
            pot=float(pot) if pot > 0 else None,
            players_left=int(players_left) if players_left > 0 else None,
            action_history=action_history if action_history else None,
            buy_in=float(buy_in) if buy_in > 0 else None,
        )
        analysis = general_concept_analysis(state)
        # Store the hand with empty action
        hands.append({
            "state": state.to_dict(),
            "analysis": analysis,
            "action": None,
        })
        st.success("Hand added. See below for analysis and to record your action.")
    # Display last added hand for action entry
    if hands:
        last_hand = hands[-1]
        state_dict = last_hand["state"]
        st.subheader("Most recently analysed hand")
        st.write(f"Hero Hand: {state_dict.get('hero_hand')} | Position: {state_dict.get('position')} | Stack: {state_dict.get('effective_bb')}bb")
        if state_dict.get("players_left"):
            st.write(f"Players Left: {state_dict.get('players_left')}")
        if state_dict.get("buy_in"):
            st.write(f"Buy‑In: ${state_dict.get('buy_in')}")
        st.write(f"Opener: {state_dict.get('opener')}")
        st.write(f"Board: {' '.join(state_dict.get('board') or []) if state_dict.get('board') else 'None'}")
        st.write(f"Pot: {state_dict.get('pot') if state_dict.get('pot') is not None else 'Unknown'}")
        st.info(last_hand["analysis"])
        # Record action
        action_val = st.text_input("Your action (jam, fold, call, raise, check)", key=f"action_{len(hands)-1}")
        if st.button("Save action", key=f"save_{len(hands)-1}"):
            last_hand["action"] = action_val
            st.success("Action saved.")
    else:
        st.write("No hands added yet.")


def render_quiz_page() -> None:
    st.header("Quiz Mode")
    hands = get_session_hands()
    if not hands:
        st.info("No hands available. Add some on the Analyse page first.")
        return
    # Maintain quiz index
    if "quiz_idx" not in st.session_state:
        st.session_state["quiz_idx"] = 0
    idx = st.session_state["quiz_idx"]
    hand = hands[idx]
    state = hand["state"]
    st.subheader(f"Hand {idx + 1} of {len(hands)}")
    st.write(f"Hero Hand: {state['hero_hand']} | Position: {state['position']} | Stack: {state['effective_bb']}bb")
    if state.get("players_left"):
        st.write(f"Players Left: {state['players_left']}")
    if state.get("buy_in"):
        st.write(f"Buy‑In: ${state['buy_in']}")
    st.write(f"Opener: {state['opener']}")
    st.write(f"Board: {' '.join(state.get('board', [])) if state.get('board') else 'None'}")
    st.write(f"Pot: {state.get('pot', 'Unknown')}")
    st.info(hand["analysis"])
    guess = st.radio(
        "Your guess for the best action",
        ["jam", "call", "raise", "fold", "check"],
        index=0,
        key=f"guess_{idx}"
    )
    if st.button("Reveal & Next"):
        recorded = hand.get("action") or "No action recorded"
        st.success(f"Your recorded action: {recorded}")
        st.write(f"Your guess: {guess}")
        # Advance index
        if idx + 1 < len(hands):
            st.session_state["quiz_idx"] = idx + 1
        else:
            st.session_state["quiz_idx"] = 0
            st.info("End of quiz. Starting over.")


def render_review_page() -> None:
    st.header("Review Log")
    hands = get_session_hands()
    if not hands:
        st.info("No hands recorded yet.")
        return
    rows = []
    for hand in hands:
        state = hand["state"]
        rows.append({
            "Hero Hand": state.get("hero_hand"),
            "Position": state.get("position"),
            "Stack (bb)": state.get("effective_bb"),
            "Players Left": state.get("players_left"),
            "Buy‑In ($)": state.get("buy_in"),
            "Opener": state.get("opener"),
            "Action History": state.get("action_history"),
            "Board": " ".join(state.get("board", [])) if state.get("board") else "",
            "Pot": state.get("pot"),
            "Concept Note": hand["analysis"],
            "Your Action": hand.get("action") or "Unrecorded",
        })
    st.dataframe(rows)
    if st.button("Download JSON"):
        json_data = json.dumps(hands, indent=2)
        st.download_button(
            label="Download hands as JSON",
            data=json_data,
            file_name="poker_study_session.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
