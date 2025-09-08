"""
Image Preprocessing Utilities
=============================

This module provides helper functions for preparing poker client
screenshots for optical character recognition (OCR).  The Natural8
client uses dark backgrounds with high‑contrast text, but a variety
of factors (monitor glare, off‑angle photos, compression artifacts)
can degrade OCR accuracy.  The functions below perform common
clean‑ups such as deskewing, denoising, contrast boosting and
binarisation.  They are written as thin wrappers around OpenCV
primitives and designed to be composed into a pipeline.

Notes:
  • The pipeline functions accept and return NumPy arrays in BGR
    format (OpenCV default).  Conversions to grayscale or other
    colour spaces happen internally.
  • The functions here do not depend on Streamlit or any other
    higher‑level modules and can be imported directly in tests.
  • Because each screenshot has unique lighting conditions, you
    may need to experiment with parameters (e.g. kernel sizes,
    thresholding methods) to achieve optimal results.
"""

from __future__ import annotations

import cv2
import numpy as np


def load_bgr(path: str) -> np.ndarray:
    """Load an image from disk into a BGR NumPy array.

    This helper exists so that callers do not need to import cv2
    themselves.  If the file cannot be read, an exception is raised.
    """
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Unable to read image: {path}")
    return img


def deskew(img: np.ndarray) -> np.ndarray:
    """Attempt to deskew the input image by estimating the rotation.

    The Natural8 client is usually captured straight on, so this
    function returns the original image unchanged by default.  It
    contains a simple heuristic using Hough line detection to detect
    the dominant skew angle and rotate accordingly.  For extreme
    angles it may fail; in such cases, returning the original image
    is preferable to introducing artefacts.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (9, 9), 0)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=20)
    angle = 0.0
    if lines is not None and len(lines) > 0:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 != x1:
                angle = np.arctan2((y2 - y1), (x2 - x1))
                angles.append(angle)
        if angles:
            # Take median angle and convert to degrees
            median_angle = np.median(angles)
            angle_deg = median_angle * 180 / np.pi
            # Only correct if angle is significant (between 1 and 10 degrees)
            if abs(angle_deg) > 1.0 and abs(angle_deg) < 10.0:
                (h, w) = img.shape[:2]
                centre = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(centre, angle_deg, 1.0)
                return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return img


def denoise_sharpen(img: np.ndarray) -> np.ndarray:
    """Apply denoising followed by unsharp masking to an image.

    Denoising reduces salt‑and‑pepper noise or JPEG artefacts, while
    unsharp masking emphasises edges and characters.  The parameters
    are conservative defaults chosen for Natural8 dark themes.
    """
    # Bilateral filter preserves edges while smoothing noise
    denoised = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
    # Convert to float for precision in unsharp masking
    blurred = cv2.GaussianBlur(denoised, (9, 9), 0)
    sharpened = cv2.addWeighted(denoised, 1.5, blurred, -0.5, 0)
    return sharpened


def boost_contrast(img: np.ndarray) -> np.ndarray:
    """Increase the local contrast of an image using CLAHE.

    Contrast Limited Adaptive Histogram Equalisation (CLAHE) is
    effective for dark backgrounds with bright text.  Only the
    luminance channel in LAB colour space is processed to avoid
    distorting colours.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    lab2 = cv2.merge((l2, a, b))
    return cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)


def upscale(img: np.ndarray, fx: float = 1.6) -> np.ndarray:
    """Enlarge an image by a scaling factor using bicubic interpolation."""
    return cv2.resize(img, None, fx=fx, fy=fx, interpolation=cv2.INTER_CUBIC)


def binarize(img: np.ndarray, mode: str = "adaptive") -> np.ndarray:
    """Convert an image to a binary (black/white) representation.

    The default uses adaptive thresholding which works well on
    non‑uniform lighting.  Otsu thresholding is also provided for
    evenly lit captures.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if mode == "otsu":
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            2,
        )
    return thresh


def preprocess_for_ocr(path: str) -> np.ndarray:
    """Load an image and apply a full preprocessing pipeline for OCR.

    Pipeline order: load → deskew → denoise & sharpen → contrast boost → upscale → binarise.
    Returns a single channel (binary) image suitable for feeding into
    Tesseract or other OCR engines.  Intermediate steps are not
    returned but can be inspected individually by calling component
    functions directly.
    """
    img = load_bgr(path)
    img = deskew(img)
    img = denoise_sharpen(img)
    img = boost_contrast(img)
    img = upscale(img)
    binary = binarize(img, mode="adaptive")
    return binary