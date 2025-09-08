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
import tempfile
from typing import List

import streamlit as st

from poker_study_tool import HandState, general_concept_analysis
# Import advanced modules for OCR and decision logic
from app import ocr_natural8, decision_engine


def get_session_hands() -> List[dict]:
    """Retrieve or initialize the list of hands in Streamlit session state."""
    if "hands" not in st.session_state:
        st.session_state["hands"] = []
    return st.session_state["hands"]


def save_uploaded_file(uploaded_file) -> str:
    """Save an uploaded file to a temporary location and return its path.

    Streamlit's file_uploader returns a BytesIO‑like object.  Tesseract
    expects a filesystem path, so we persist the bytes to a temporary
    file.  The caller is responsible for cleaning up the file if
    needed.
    """
    if uploaded_file is None:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(uploaded_file.read())
        return tmp.name


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
    """Analyse page with OCR upload and preflop recommendations."""
    st.header("Analyse a new hand")
    hands = get_session_hands()
    # File uploaders for Natural8 screenshots
    st.markdown("#### Upload screenshots")
    table_file = st.file_uploader(
        "Table screenshot (Natural8)", type=["png", "jpg", "jpeg"], key="table_file"
    )
    lobby_file = st.file_uploader(
        "Lobby screenshot (optional)", type=["png", "jpg", "jpeg"], key="lobby_file"
    )
    use_ocr = st.checkbox("Use OCR to prefill fields", value=True)
    debug_ocr = st.checkbox("Show OCR debug overlays", value=False)
    ocr_meta: dict = {}
    if use_ocr and table_file is not None:
        table_path = save_uploaded_file(table_file)
        lobby_path = save_uploaded_file(lobby_file) if lobby_file is not None else None
        try:
            # Only table screenshot is used for metadata extraction.  The Natural8 OCR
            # helper currently accepts a single image path and returns a dict.
            ocr_meta = ocr_natural8.extract_metadata(table_path, debug=debug_ocr)
        except Exception as e:
            st.error(f"OCR error: {e}")
            ocr_meta = {}
    # Derive default values from OCR metadata
    players_left_default = 0
    buy_in_default = 0.0
    pot_default = 0.0
    is_pko_default = False
    reentry_default = "None"
    bubble_protection_default = False
    table_type_default = "9‑max"
    blind_interval_default = 3
    if ocr_meta:
        # players left: could be "17/28" or just number
        pl = ocr_meta.get("players_left")
        try:
            if pl:
                if isinstance(pl, str) and "/" in pl:
                    players_left_default = int(pl.split("/")[0].strip())
                else:
                    players_left_default = int(float(pl))
        except Exception:
            players_left_default = 0
        # buy‑in
        try:
            if ocr_meta.get("buy_in"):
                buy_in_default = float(ocr_meta["buy_in"])
        except Exception:
            buy_in_default = 0.0
        # pot size
        try:
            if ocr_meta.get("pot"):
                pot_default = float(ocr_meta["pot"])
        except Exception:
            pot_default = 0.0
        # PKO / bounty flag
        if ocr_meta.get("bounty_flag"):
            is_pko_default = True
        # re‑entry string
        if ocr_meta.get("reentry"):
            reentry_str = str(ocr_meta.get("reentry")).strip()
            # Normalise common values
            if reentry_str.lower().startswith("none"):
                reentry_default = "None"
            elif reentry_str.lower().startswith("unlimited"):
                reentry_default = "Unlimited"
            elif reentry_str.lower().startswith("multi"):
                reentry_default = "Multi"
            else:
                reentry_default = reentry_str.capitalize()
        # Bubble protection
        if ocr_meta.get("bubble_protection"):
            bubble_protection_default = True
        # Table type: may be "6", "7", etc.
        tt = ocr_meta.get("table_type")
        if tt:
            tt_str = str(tt).strip()
            if tt_str.startswith("6"):
                table_type_default = "6‑max"
            elif tt_str.startswith("7"):
                table_type_default = "7‑max"
            elif tt_str.startswith("8"):
                table_type_default = "8‑max"
            elif tt_str.startswith("9"):
                table_type_default = "9‑max"
        # Blind interval
        try:
            if ocr_meta.get("blind_interval"):
                blind_interval_default = int(float(ocr_meta["blind_interval"]))
        except Exception:
            blind_interval_default = 3
    # Input fields with OCR defaults
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
        "Pot size (optional)", min_value=0.0, value=pot_default, step=0.5
    )
    players_left = st.number_input(
        "Number of players left (optional)", min_value=0, max_value=1000, value=players_left_default, step=1
    )
    buy_in = st.number_input(
        "Tournament buy‑in ($, optional)", min_value=0.0, value=buy_in_default, step=0.1
    )
    action_history = st.text_input(
        "Action history (e.g. 'UTG opens 2bb, CO calls')", value=""
    )
    # Optional tournament metadata fields
    st.markdown("#### Optional tournament metadata")
    is_pko = st.checkbox("Bounty / PKO event?", value=is_pko_default)
    reentry = st.selectbox(
        "Re‑entry format",
        ["None", "Single", "Multi", "Unlimited"],
        index=["None", "Single", "Multi", "Unlimited"].index(reentry_default)
    )
    bubble_protection = st.checkbox("Bubble protection available?", value=bubble_protection_default)
    table_type = st.selectbox(
        "Table type",
        ["9‑max", "8‑max", "7‑max", "6‑max"],
        index=["9‑max", "8‑max", "7‑max", "6‑max"].index(table_type_default)
    )
    blind_interval = st.number_input(
        "Blind interval (minutes, optional)", min_value=1, max_value=60, value=blind_interval_default, step=1
    )
    if st.button("Analyse hand"):
        # Build HandState from inputs
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
        # Use OCR metadata for tournament context and include optional overrides
        meta = dict(ocr_meta) if ocr_meta else {}
        # Add/override metadata from user inputs
        meta['buy_in'] = buy_in if buy_in > 0 else meta.get('buy_in')
        meta['players_left'] = players_left if players_left > 0 else meta.get('players_left')
        meta['pot'] = pot if pot > 0 else meta.get('pot')
        meta['is_pko'] = is_pko
        meta['reentry'] = reentry
        meta['bubble_protection'] = bubble_protection
        meta['table_type'] = table_type
        meta['blind_interval'] = blind_interval
        # Preflop recommendation from decision engine
        try:
            rec_action, rec_size, rec_note = decision_engine.recommend_preflop(state, meta)
            rec_message = f"Recommended action: **{rec_action} {rec_size}**\n\n{rec_note}"
        except Exception as e:
            rec_action, rec_size, rec_note = "Unknown", "", f"Recommendation error: {e}"
            rec_message = rec_note
        # Save hand record with recommendation
        analysis = general_concept_analysis(state)
        hands.append({
            "state": state.to_dict(),
            "analysis": analysis,
            "recommended_action": rec_action,
            "recommended_size": rec_size,
            "recommended_note": rec_note,
            "action": None,
            "meta": meta,
        })
        st.success("Hand added. See below for analysis and recommended action.")
        st.markdown(rec_message)
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
        # Display recommendation if available
        if last_hand.get("recommended_action") and last_hand.get("recommended_action") != "Unknown":
            st.success(f"Recommended: {last_hand['recommended_action']} {last_hand['recommended_size']}")
            st.write(last_hand.get("recommended_note", ""))
        # Record actual action
        action_val = st.text_input(
            "Your action (jam, fold, call, raise, check)",
            key=f"action_{len(hands)-1}"
        )
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
            "Recommended": f"{hand.get('recommended_action', '')} {hand.get('recommended_size', '')}".strip(),
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