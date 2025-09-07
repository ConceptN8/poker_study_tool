"""
Streamlit Interface for the Post‑Game Poker Study Tool
=====================================================

This module defines a Streamlit application that wraps the core logic
from `poker_study_tool.py` into a simple browser user interface.
The app allows users to upload screenshots or videos from their poker
session, extract relevant information via OCR, apply general poker
concepts to generate high‑level analysis, and log their own actions
for study and review.  It also provides a quiz mode where players
can test their intuition against the concept notes before revealing
their past actions.

Because this environment does not include Streamlit or pytesseract,
the app has not been executed here.  It is meant to serve as a
template that can be run locally or deployed to a service such as
Streamlit Cloud.  To run it yourself, install the required
dependencies (streamlit, opencv‑python, pytesseract) and execute

    streamlit run streamlit_app.py

The app uses Streamlit's session state to persist uploaded hands
and user actions across page interactions.
"""

import io
import json
import os
from typing import List, Optional

import streamlit as st

from poker_study_tool import (
    HandState,
    ocr_image,
    parse_hand_state,
    general_concept_analysis,
    StudySession,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def process_uploaded_file(file) -> Optional[HandState]:
    """Process an uploaded image or video file.

    For images, this function saves the file to a temporary location,
    runs the OCR pipeline defined in poker_study_tool.ocr_image, and
    returns a parsed HandState.  For videos, it extracts the first
    frame as a JPEG and applies the same process.  Video support is
    simplified and may need refinement in a production setting.

    Args:
        file: An uploaded file from st.file_uploader.

    Returns:
        A HandState instance or None if processing fails.
    """
    if file is None:
        return None

    # Determine file type
    filename = file.name.lower()
    suffix = os.path.splitext(filename)[1]
    temp_path = None
    try:
        # Create a temporary directory per session if not set
        if "temp_dir" not in st.session_state:
            st.session_state["temp_dir"] = os.path.join(
                "/tmp", f"poker_study_{os.getpid()}"
            )
            os.makedirs(st.session_state["temp_dir"], exist_ok=True)
        temp_dir = st.session_state["temp_dir"]
        # Save file to a temporary location
        temp_path = os.path.join(temp_dir, filename)
        with open(temp_path, "wb") as fh:
            fh.write(file.read())

        if suffix in {".png", ".jpg", ".jpeg"}:
            # Image file: run OCR directly
            ocr_data = ocr_image(temp_path)
        elif suffix in {".mp4", ".mov", ".avi"}:
            # Video file: extract first frame using cv2 if available
            try:
                import cv2  # type: ignore

                cap = cv2.VideoCapture(temp_path)
                success, frame = cap.read()
                cap.release()
                if not success:
                    st.error("Failed to read video frame for OCR")
                    return None
                # Convert frame to JPEG buffer
                _, buf = cv2.imencode(".jpg", frame)
                image_bytes = io.BytesIO(buf.tobytes())
                # Save the frame to a temporary file for OCR
                frame_path = temp_path + "_frame.jpg"
                with open(frame_path, "wb") as fh_frame:
                    fh_frame.write(image_bytes.getvalue())
                ocr_data = ocr_image(frame_path)
            except Exception as exc:
                st.error(f"Video processing failed: {exc}")
                return None
        else:
            st.error("Unsupported file type. Please upload a PNG, JPG, or MP4 file.")
            return None

        # Parse OCR output into a HandState
        state = parse_hand_state(ocr_data)
        return state
    finally:
        # We do not delete the temporary file because OCR might run lazily;
        # the temporary directory will be cleaned up when the session ends.
        pass


def get_session() -> StudySession:
    """Retrieve or initialize the StudySession in Streamlit session state."""
    if "study_session" not in st.session_state:
        st.session_state["study_session"] = StudySession()
    return st.session_state["study_session"]


# ---------------------------------------------------------------------------
# Streamlit application
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Post‑Game Poker Study Tool", layout="wide")
    st.title("Post‑Game Poker Study Tool")

    # Sidebar navigation
    page = st.sidebar.radio(
        "Navigation",
        ["Upload & Analyse", "Quiz Mode", "Review Log"],
        index=0,
    )

    if page == "Upload & Analyse":
        render_upload_page()
    elif page == "Quiz Mode":
        render_quiz_page()
    elif page == "Review Log":
        render_review_page()


def render_upload_page() -> None:
    st.header("Upload hands for analysis")
    st.write(
        "Upload a screenshot (PNG/JPG) or short video (MP4) of a decision point."
        " The tool will extract the relevant information and provide general concept notes."
    )

    uploaded_files = st.file_uploader(
        "Choose file(s)",
        type=["png", "jpg", "jpeg", "mp4", "mov", "avi"],
        accept_multiple_files=True,
    )

    session = get_session()
    if uploaded_files:
        for file in uploaded_files:
            state = process_uploaded_file(file)
            if state is None:
                continue
            # Display OCR results and concept analysis
            st.subheader(
                f"Hand: {state.hero_hand} | Position: {state.position} | {state.effective_bb}bb"
            )
            st.write("**Board:**", state.board or "None")
            st.write("**Opener:**", state.opener)
            st.write("**Pot:**", state.pot if state.pot is not None else "Unknown")
            # Additional tournament context inputs
            # Players left: ask the user to enter or confirm the number of players remaining
            players_left_input = st.number_input(
                "Number of players left in the tournament",
                min_value=2,
                max_value=10000,
                value=int(state.players_left) if state.players_left else 6,
                step=1,
                key=f"pl_{file.name}",
            )
            state.players_left = int(players_left_input)
            # Tournament buy‑in: allow user to confirm buy‑in amount
            buy_in_input = st.number_input(
                "Tournament buy-in ($)",
                min_value=0.0,
                value=float(state.buy_in) if state.buy_in else 0.0,
                step=0.1,
                key=f"bi_{file.name}",
            )
            state.buy_in = float(buy_in_input)
            # Action history: ask the user to describe the action so far from other players
            action_hist_input = st.text_input(
                "Action so far from other players",
                value=state.action_history or state.opener,
                key=f"ah_{file.name}",
            )
            state.action_history = action_hist_input
            # Recompute analysis after capturing players_left
            analysis = general_concept_analysis(state)
            st.info(analysis)
            # Add to session and store the ID
            hand_id = session.add_hand(state)
            # Ask user to log their action (they may leave this blank to log later)
            action = st.text_input(
                f"Your action for this hand (jam/fold/call/raise)", key=hand_id
            )
            if action:
                session.record_action(hand_id, action)
                st.success("Action recorded.")
        st.write(
            """
        After uploading, navigate to **Quiz Mode** to test your intuition or **Review Log** to see all hands."
            """
        )
    else:
        st.write("No files uploaded yet.")


def render_quiz_page() -> None:
    st.header("Quiz Mode")
    st.write(
        "Test your decision making against general concept guidelines."
        " For each hand, guess the optimal action based on the concept note before revealing your own recorded action."
    )
    session = get_session()
    hands = list(session.hands.items())
    if not hands:
        st.info("No hands available. Please upload hands on the 'Upload & Analyse' page.")
        return
    # Display one hand at a time using an index in session state
    if "quiz_index" not in st.session_state:
        st.session_state["quiz_index"] = 0
    index = st.session_state["quiz_index"]
    hand_id, entry = hands[index]
    state_json = entry["state"]
    state_dict = json.loads(state_json)
    st.subheader(f"Hand {index + 1} of {len(hands)}")
    st.write(
        f"**Hero Hand:** {state_dict['hero_hand']} | **Position:** {state_dict['position']} | **Stack:** {state_dict['effective_bb']}bb"
    )
    # Show additional tournament context if available
    players_left = state_dict.get('players_left')
    if players_left:
        st.write(f"**Players Left:** {players_left}")
    buy_in = state_dict.get('buy_in')
    if buy_in:
        st.write(f"**Buy-In:** ${buy_in}")
    st.write(f"**Opener:** {state_dict['opener']}")
    st.write(f"**Board:** {state_dict.get('board', 'None')}")
    st.write(f"**Pot:** {state_dict.get('pot', 'Unknown')}")
    st.info(entry["analysis"])
    # Guess input
    guess = st.radio(
        "Your guess for the correct action:",
        ("jam", "call", "raise", "fold", "check"),
        index=0,
        key=f"guess_{index}"
    )
    if st.button("Reveal & Next"):
        # Show recorded action
        recorded = entry.get("player_action") or "No action recorded"
        st.success(f"Your recorded action: **{recorded}**")
        st.write(f"Your guess: **{guess}**")
        # Move to next hand if available
        if index + 1 < len(hands):
            st.session_state["quiz_index"] = index + 1
        else:
            st.session_state["quiz_index"] = 0
            st.info("End of quiz. Returning to first hand.")


def render_review_page() -> None:
    st.header("Review Log")
    st.write(
        "All hands you have uploaded along with concept notes and your recorded actions."
    )
    session = get_session()
    if not session.hands:
        st.info("No hands recorded yet.")
        return
    # Create a simple table view
    rows: List[dict] = []
    for hand_json, entry in session.hands.items():
        state_dict = json.loads(entry["state"])
        rows.append(
            {
                "Hero Hand": state_dict.get("hero_hand"),
                "Position": state_dict.get("position"),
                "Stack (bb)": state_dict.get("effective_bb"),
                "Players Left": state_dict.get("players_left"),
                "Buy-In ($)": state_dict.get("buy_in"),
                "Opener": state_dict.get("opener"),
                "Action History": state_dict.get("action_history"),
                "Board": " ".join(state_dict.get("board", []))
                if state_dict.get("board")
                else "",
                "Pot": state_dict.get("pot"),
                "Concept Note": entry["analysis"],
                "Your Action": entry["player_action"] or "Unrecorded",
            }
        )
    # Display as a DataFrame
    st.dataframe(rows)
    # Option to export
    if st.button("Export Session as JSON"):
        json_output = get_session().to_json()
        st.download_button(
            label="Download JSON",
            data=json_output,
            file_name="poker_study_session.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()