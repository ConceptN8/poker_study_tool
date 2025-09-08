"""
Natural8 OCR Parsing
====================

This module encapsulates the logic for parsing relevant fields from
Natural8 poker client screenshots.  It uses a YAML template to
define the approximate locations of HUD elements and regular
expressions for extracting numeric values.  Combined with the
preprocessing utilities, this allows the application to recover
tournament metadata (players left, buy‑in, average stack, etc.)
without manual input.

The OCR procedure is intentionally split into several stages:

  1. Load and preprocess the full screenshot (deskew, denoise,
     contrast, upscale, binarise) using functions from
     ``app.preprocess``.
  2. Crop subregions specified in the template (header, pot box,
     lobby information) according to percentage‑based coordinates.
  3. Run Tesseract OCR on each crop with varying Page Segmentation
     Modes (PSM) and whitelists tailored for the expected content.
  4. Apply regular expression patterns from the template to parse
     structured values from the OCR text.

The functions return simple dictionaries of parsed values.  If a
field cannot be extracted, the corresponding key is omitted or set
to ``None``.  Caller code is responsible for defaulting missing
fields and handling user overrides.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Tuple, Optional

import cv2
import numpy as np
import pytesseract
import yaml

from . import preprocess as pp


def load_template(path: Optional[str] = None) -> dict:
    """Load a YAML template describing Natural8 OCR regions and patterns.

    If ``path`` is None, defaults to ``natural8_template.yaml`` located
    in the project root.  The template must contain keys:
      • ``regions``: mapping of names to ``[x, y, w, h]`` values in
        fractional coordinates (0–1).
      • ``patterns``: mapping of field names to regular expressions.
      • Optional ``tournament_fields`` for parsing lobby metadata.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'natural8_template.yaml')
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def crop_region(img: np.ndarray, rect: Tuple[float, float, float, float]) -> np.ndarray:
    """Crop a subregion from an image using fractional coordinates.

    ``rect`` is a tuple ``(x, y, w, h)`` with values between 0 and 1.
    It is multiplied by the image dimensions to determine pixel
    coordinates.  Values outside the range [0, 1] are clamped.
    """
    h, w = img.shape[:2]
    x_frac, y_frac, w_frac, h_frac = rect
    x0 = int(max(0, min(1, x_frac)) * w)
    y0 = int(max(0, min(1, y_frac)) * h)
    x1 = int(max(0, min(1, x_frac + w_frac)) * w)
    y1 = int(max(0, min(1, y_frac + h_frac)) * h)
    return img[y0:y1, x0:x1]


def run_tesseract(img: np.ndarray, psm: int = 6, whitelist: Optional[str] = None) -> str:
    """Perform OCR on a binarised image using Tesseract.

    Arguments:
      • ``psm``: Page Segmentation Mode.  Common values:
          – 6: Assume a single uniform block of text.
          – 7: Treat image as a single text line.
      • ``whitelist``: If provided, restricts Tesseract's output to
        the specified characters (e.g. ``"0123456789Bb."``).

    Returns:
      The raw OCR string stripped of leading/trailing whitespace.
    """
    config = f"--psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    text = pytesseract.image_to_string(img, lang='eng', config=config)
    return text.strip()


def parse_patterns(text: str, patterns: Dict[str, str]) -> Dict[str, Optional[str]]:
    """Match multiple regex patterns against the given text.

    For each key in ``patterns``, attempts to search ``text`` using
    ``re.search`` with the corresponding pattern.  If a match is
    found, the first captured group is returned; otherwise ``None``
    is stored.  All patterns are compiled with the flags
    ``re.IGNORECASE`` and ``re.DOTALL``.
    """
    results: Dict[str, Optional[str]] = {}
    for key, pattern in patterns.items():
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        match = regex.search(text)
        results[key] = match.group(1) if match else None
    return results


def extract_table_metadata(image_path: str, template: dict, debug: bool = False) -> Dict[str, Optional[str]]:
    """Extract table‑level metadata (players left, pot size, hero stack) from a screenshot.

    This function reads the screenshot, applies preprocessing and
    crops the predefined regions.  It then runs OCR with two
    configurations on each region: a general mode for words and a
    digit mode for numbers.  The results are combined using the
    provided regex patterns.
    """
    img = pp.load_bgr(image_path)
    # Preprocess once globally for faster cropping
    processed = pp.preprocess_for_ocr(image_path)
    meta: Dict[str, Optional[str]] = {}
    for region_name, rect in template.get('regions', {}).items():
        crop_full = crop_region(processed, rect)
        # For general OCR use psm 6
        text_general = run_tesseract(crop_full, psm=6)
        # For digits use psm 7 and whitelist digits and dot/B
        text_digits = run_tesseract(crop_full, psm=7, whitelist="0123456789Bb./ :")
        combined = text_general + "\n" + text_digits
        # Parse patterns relevant to this region
        patterns = template.get('patterns', {})
        if patterns:
            parsed = parse_patterns(combined, patterns)
            # Merge into meta, only store new non‑None values
            for k, v in parsed.items():
                if v:
                    meta[k] = v
        if debug:
            # Save debug overlay images to temporary directory
            debug_dir = '/tmp/ocr_debug'
            os.makedirs(debug_dir, exist_ok=True)
            # Colour overlay: draw the region on the original image
            clone = img.copy()
            h, w = img.shape[:2]
            x_frac, y_frac, w_frac, h_frac = rect
            x0 = int(x_frac * w)
            y0 = int(y_frac * h)
            x1 = int((x_frac + w_frac) * w)
            y1 = int((y_frac + h_frac) * h)
            cv2.rectangle(clone, (x0, y0), (x1, y1), (0, 255, 0), 2)
            out_path = os.path.join(debug_dir, f"{region_name}.png")
            cv2.imwrite(out_path, clone)
    return meta


def extract_lobby_metadata(image_path: str, template: dict) -> Dict[str, Optional[str]]:
    """Extract tournament lobby metadata using ``tournament_fields`` patterns.

    Lobby screenshots display details such as buy‑in, bounty value,
    starting chips, blind intervals, re‑entry rules and bubble
    protection.  Because the entire lobby is text rich, this
    function runs OCR on the whole preprocessed image and applies
    the provided patterns.  It assumes the YAML template includes
    ``tournament_fields`` with regexes capturing the relevant
    values.  If absent, returns an empty dict.
    """
    if 'tournament_fields' not in template:
        return {}
    processed = pp.preprocess_for_ocr(image_path)
    # Use a generous PSM for full pages
    text = run_tesseract(processed, psm=6)
    return parse_patterns(text, template['tournament_fields'])


def extract_metadata(image_path: str, debug: bool = False) -> Dict[str, Optional[str]]:
    """High‑level helper to extract any available metadata from a Natural8 screenshot.

    This convenience function first loads the default Natural8
    template and then calls both ``extract_table_metadata`` and
    ``extract_lobby_metadata``.  It merges the results, preferring
    values from the table parser when duplicates occur.  The
    ``debug`` flag controls whether overlay images are written for
    visual inspection.  Users of the Streamlit app can toggle this
    to diagnose OCR issues.
    """
    template = load_template()
    meta = {}
    # Attempt table metadata extraction
    meta.update(extract_table_metadata(image_path, template, debug=debug))
    # Attempt lobby metadata extraction
    lobby_meta = extract_lobby_metadata(image_path, template)
    # Do not overwrite existing keys
    for k, v in lobby_meta.items():
        if k not in meta and v is not None:
            meta[k] = v
    return meta