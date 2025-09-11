#d

from __future__ import annotations

import os
import re
import yaml
import cv2
import numpy as np
from PIL import Image
from typing import Dict, Any, Optional, Tuple, List

# IMPORTANT: absolute import (no relative ".preprocess") for Heroku
import preprocess as pp


def load_template(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load a YAML template describing Natural8 OCR regions and patterns.

    If `path` is None, defaults to `natural8_template.yaml` located in the
    project root (same directory as your Streamlit/Procfile).
    The template should define:
      - regions: dict[name] -> [x, y, w, h] in fractional coords (0–1)
      - patterns: dict[field] -> regex string
      - (optional) tournament_fields: mapping for lobby parsing
    """
    if path is None:
        # project root: file lives at repo root next to requirements.txt
        repo_root = os.path.dirname(os.path.abspath(__file__))
        # If this file is inside an "app" package, step up once:
        # repo_root = os.path.dirname(repo_root)
        candidate = os.path.join(repo_root, "natural8_template.yaml")
        if not os.path.exists(candidate):
            # Fallback: one level up (covers /app layout)
            candidate = os.path.join(os.path.dirname(repo_root), "natural8_template.yaml")
        path = candidate

    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def crop_region(img_bgr: np.ndarray, box_frac: Tuple[float, float, float, float]) -> np.ndarray:
    """
    Crop a region from an image using fractional coordinates (x, y, w, h).
    """
    h, w = img_bgr.shape[:2]
    fx, fy, fw, fh = box_frac
    x, y, cw, ch = int(fx * w), int(fy * h), int(fw * w), int(fh * h)
    x2, y2 = max(0, x), max(0, y)
    return img_bgr[y2 : min(y2 + ch, h), x2 : min(x2 + cw, w)]


def ocr_text(img_bgr: np.ndarray) -> str:
    """
    Light preprocessing + OCR. We keep conservative filters because
    screenshots can be slightly blurry / angled.
    """
    gray = pp.to_gray(img_bgr)
    sharp = pp.unsharp(gray)
    thr = pp.adaptive(threshold_src=sharp)
    text = pp.tesseract_text(thr)
    return text


def parse_fields(text: str, patterns: Dict[str, str]) -> Dict[str, Any]:
    """
    Apply regex patterns to OCR text and return structured fields.
    """
    out: Dict[str, Any] = {}
    for name, pat in patterns.items():
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if not m:
            out[name] = None
            continue
        g = m.groupdict() if hasattr(m, "groupdict") else {}
        out[name] = g if g else m.group(0)
    return out


def extract_hand_state(
    img_bgr: np.ndarray,
    template: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extract core fields from a Natural8 table screenshot:
      - buy_in, players_left, hero_stack, blinds, antes (if present)
      - position, action_so_far (street-level cues if available)

    Returns a dict used by the decision engine / UI.
    """
    if template is None:
        template = load_template()

    regions = template.get("regions", {})
    patterns = template.get("patterns", {})

    results: Dict[str, Any] = {}
    # OCR each defined region and parse with regex
    for name, frac_box in regions.items():
        roi = crop_region(img_bgr, tuple(frac_box))
        txt = ocr_text(roi)
        results[f"text_{name}"] = txt  # keep raw for debugging

    # Combine all text (simple baseline). You can make this region-specific later.
    combined = "\n".join(results.get(f"text_{k}", "") for k in regions.keys())
    parsed = parse_fields(combined, patterns)

    # Minimal normalization examples
    if parsed.get("players_left") and isinstance(parsed["players_left"], str):
        try:
            parsed["players_left"] = int(re.sub(r"[^0-9]", "", parsed["players_left"]))
        except Exception:
            pass

    results.update(parsed)
    return results



def extract_metadata(img_bgr, template: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """
    Accepts image input in various formats (np.ndarray, file path, bytes, or file-like object) and normalizes it to a BGR numpy array before extracting table metadata.

    Args:
        img_bgr: The table screenshot as a BGR numpy array, file path, bytes, or file-like object.
        template: OCR template with regions and patterns. If None, the default template is loaded.
        **kwargs: Additional keyword arguments (ignored).

    Returns:
        Dict[str, Any]: OCR-extracted metadata dictionary from the table screenshot.
    """
    # Normalize input to BGR image
    if isinstance(img_bgr, np.ndarray):
        pass  # already a decoded image
    elif isinstance(img_bgr, str):
        # If a file path is provided, read the image from disk
        img_bgr = cv2.imread(img_bgr)
    elif isinstance(img_bgr, (bytes, bytearray)):
        # If bytes are provided, decode them into an image
        buf = np.frombuffer(img_bgr, np.uint8)
        img_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    elif hasattr(img_bgr, "read"):
        # If a file-like object is provided, read and decode its data
        data = img_bgr.read()
        buf = np.frombuffer(data, np.uint8)
        img_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    else:
        raise TypeError(f"Unsupported image input type: {type(img_bgr)}")

    if img_bgr is None or not hasattr(img_bgr, "shape"):
        raise ValueError("Could not decode image input into a valid BGR array")

    return extract_hand_state(img_bgr, template)

