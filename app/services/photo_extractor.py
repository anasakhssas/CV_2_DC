"""Extraction de la photo du candidat depuis le PDF."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.config import PHOTO_MIN_SIZE, PHOTO_OUTPUT_SIZE
from app.models import PhotoResult
from app.services.pdf_extractor import PDFContent, render_page_as_image

logger = logging.getLogger(__name__)

# Chargement du classificateur Haar pour la détection de visages
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]
)


def _score_image(img_info: dict) -> int:
    """Score une image candidate pour déterminer si c'est la photo du CV."""
    score = 0
    w, h = img_info["width"], img_info["height"]

    # Taille minimum
    if w < PHOTO_MIN_SIZE or h < PHOTO_MIN_SIZE:
        return -1

    # Contient un visage → +60
    try:
        img_array = np.frombuffer(img_info["data"], dtype=np.uint8)
        img_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img_cv is not None:
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
            if len(faces) > 0:
                score += 60
    except Exception as e:
        logger.debug("Erreur détection visage: %s", e)

    # Grande résolution → +20
    if w >= 200 and h >= 200:
        score += 20

    # Position page 1 → +10
    if img_info.get("page", 0) == 0:
        score += 10

    # Ratio portrait (carré ou vertical) → +10
    ratio = h / w if w > 0 else 0
    if 0.8 <= ratio <= 1.8:
        score += 10

    return score


def _crop_and_resize(img_bytes: bytes, output_path: Path) -> str:
    """Redimensionne l'image à la taille standard et sauvegarde."""
    img = Image.open(io.BytesIO(img_bytes))
    img = img.convert("RGB")

    # Centre-crop carré
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    img = img.resize(PHOTO_OUTPUT_SIZE, Image.LANCZOS)
    img.save(str(output_path), "JPEG", quality=90)
    return str(output_path)


def _detect_face_from_page(pdf_path: str | Path, output_path: Path) -> PhotoResult | None:
    """Fallback : convertit la page 1 en image et détecte un visage."""
    try:
        page_bytes = render_page_as_image(pdf_path, page_num=0, dpi=200)
        img_array = np.frombuffer(page_bytes, dtype=np.uint8)
        img_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img_cv is None:
            return None

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))

        if len(faces) == 0:
            return None

        # Prendre le plus grand visage
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]

        # Ajouter marge autour du visage
        margin = int(max(w, h) * 0.4)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img_cv.shape[1], x + w + margin)
        y2 = min(img_cv.shape[0], y + h + margin)

        face_crop = img_cv[y1:y2, x1:x2]
        _, buffer = cv2.imencode(".jpg", face_crop)
        saved = _crop_and_resize(buffer.tobytes(), output_path)

        return PhotoResult(found=True, file_path=saved, confidence=0.7, method="face_detection")

    except Exception as e:
        logger.warning("Erreur détection visage page: %s", e)
        return None


def extract_photo(
    pdf_content: PDFContent,
    pdf_path: str | Path,
    output_dir: Path,
) -> PhotoResult:
    """Extrait la photo du candidat.

    Stratégie :
    1. Extraction directe des images du PDF → score → meilleure candidate.
    2. Fallback : rendu page 1 → détection de visage → crop.
    """
    output_path = output_dir / "photo.jpg"

    # ── Stratégie 1 : extraction directe ─────────────────────
    if pdf_content.images:
        candidates = []
        for img_info in pdf_content.images:
            score = _score_image(img_info)
            if score > 0:
                candidates.append((score, img_info))

        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            best = candidates[0]
            saved = _crop_and_resize(best[1]["data"], output_path)
            conf = min(1.0, best[0] / 100)
            return PhotoResult(
                found=True,
                file_path=saved,
                confidence=round(conf, 2),
                method="direct_extraction",
            )

    # ── Stratégie 2 : face detection sur page 1 ─────────────
    result = _detect_face_from_page(pdf_path, output_path)
    if result:
        return result

    return PhotoResult(found=False, confidence=0, method=None)
