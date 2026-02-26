"""Extraction de texte et images depuis un PDF."""

from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass, field

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PDFContent:
    """Résultat de l'extraction PDF."""
    text: str = ""
    pages_text: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)  # [{data, ext, width, height, page}]
    num_pages: int = 0
    is_scanned: bool = False


def extract_pdf(pdf_path: str | Path) -> PDFContent:
    """Extrait texte + images d'un fichier PDF.

    Détecte automatiquement si le PDF est numérique ou scanné.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    doc = fitz.open(str(pdf_path))
    content = PDFContent(num_pages=len(doc))

    all_text_parts: list[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # ── Texte ────────────────────────────────────────
        page_text = page.get_text("text") or ""
        content.pages_text.append(page_text)
        all_text_parts.append(page_text)

        # ── Images ───────────────────────────────────────
        image_list = page.get_images(full=True)
        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if base_image:
                    content.images.append({
                        "data": base_image["image"],
                        "ext": base_image["ext"],
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "page": page_num,
                        "xref": xref,
                    })
            except Exception as e:
                logger.warning("Erreur extraction image p%d #%d: %s", page_num, img_index, e)

    content.text = "\n".join(all_text_parts).strip()

    # Détection PDF scanné : très peu de texte extractible
    char_count = len(content.text.replace(" ", "").replace("\n", ""))
    if char_count < 50 and content.num_pages > 0:
        content.is_scanned = True
        logger.info("PDF détecté comme scanné (< 50 caractères)")

    doc.close()
    return content


def render_page_as_image(pdf_path: str | Path, page_num: int = 0, dpi: int = 200) -> bytes:
    """Convertit une page PDF en image PNG (fallback pour scan)."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes
