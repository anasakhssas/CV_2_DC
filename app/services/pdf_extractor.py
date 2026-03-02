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


# ── Multi-column layout detection & reassembly ───────────────


def _detect_column_boundary(blocks: list, page_width: float) -> float | None:
    """Return the x-position boundary between two columns, or *None* if single-column.

    Strategy:
    1. Collect left-edge (x0) positions of all text blocks, sort them.
    2. Look for the widest gap inside the middle 60 % of the page.
    3. Validate that both sides contain genuine column content, not just
       short section headings.  We require:
       - at least ``_MIN_BLOCKS_PER_COLUMN`` blocks per side, **and**
       - at least ``_MIN_CHARS_PER_COLUMN`` total characters per side.
       This prevents centered headers or short left-aligned headings
       from tricking the detector on single-column CVs.
    """
    _MIN_BLOCKS_PER_COLUMN = 5
    _MIN_CHARS_PER_COLUMN = 200  # a real column has paragraphs, not just headings

    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
    if len(text_blocks) < _MIN_BLOCKS_PER_COLUMN * 2:
        return None

    x_starts = sorted({round(b[0]) for b in text_blocks})
    left_bound = page_width * 0.20
    right_bound = page_width * 0.80

    best_gap = 0.0
    best_boundary: float | None = None

    for i in range(len(x_starts) - 1):
        gap = x_starts[i + 1] - x_starts[i]
        mid = (x_starts[i] + x_starts[i + 1]) / 2.0
        if gap > best_gap and left_bound < mid < right_bound:
            best_gap = gap
            best_boundary = mid

    if best_gap <= page_width * 0.10 or best_boundary is None:
        return None

    # Classify blocks into left / right by their horizontal center
    left_blocks = [b for b in text_blocks if (b[0] + b[2]) / 2.0 < best_boundary]
    right_blocks = [b for b in text_blocks if (b[0] + b[2]) / 2.0 >= best_boundary]

    left_count = len(left_blocks)
    right_count = len(right_blocks)
    left_chars = sum(len(b[4].strip()) for b in left_blocks)
    right_chars = sum(len(b[4].strip()) for b in right_blocks)

    if (
        left_count < _MIN_BLOCKS_PER_COLUMN
        or right_count < _MIN_BLOCKS_PER_COLUMN
        or left_chars < _MIN_CHARS_PER_COLUMN
        or right_chars < _MIN_CHARS_PER_COLUMN
    ):
        logger.debug(
            "Gap found (%.0f) but content insufficient: "
            "left=%d blocks/%d chars, right=%d blocks/%d chars",
            best_gap, left_count, left_chars, right_count, right_chars,
        )
        return None

    return best_boundary


def _reassemble_columns(blocks: list, boundary: float) -> str:
    """Re-order text blocks so that *left column* comes first (sorted by y),
    then *right column* (sorted by y).  This avoids the interleaving that
    ``page.get_text("text")`` produces on multi-column CVs.
    """
    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]

    left = sorted(
        [b for b in text_blocks if (b[0] + b[2]) / 2.0 < boundary],
        key=lambda b: b[1],
    )
    right = sorted(
        [b for b in text_blocks if (b[0] + b[2]) / 2.0 >= boundary],
        key=lambda b: b[1],
    )

    parts: list[str] = []
    for b in left + right:
        parts.append(b[4].rstrip("\n"))
    return "\n".join(parts)


def _extract_page_text(page) -> str:
    """Extract text from a single page, handling multi-column layouts."""
    blocks = page.get_text("blocks")
    page_width = page.rect.width

    boundary = _detect_column_boundary(blocks, page_width)
    if boundary is not None:
        logger.info(
            "Multi-column layout detected (boundary=%.0f / page_width=%.0f)",
            boundary, page_width,
        )
        return _reassemble_columns(blocks, boundary)

    # Single-column: default extraction
    return page.get_text("text") or ""


# ── Main extraction ──────────────────────────────────────────


def extract_pdf(pdf_path: str | Path) -> PDFContent:
    """Extrait texte + images d'un fichier PDF.

    Détecte automatiquement si le PDF est numérique ou scanné.
    Gère les mises en page multi-colonnes en réassemblant le texte
    colonne par colonne (gauche puis droite).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    doc = fitz.open(str(pdf_path))
    content = PDFContent(num_pages=len(doc))

    all_text_parts: list[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # ── Texte (with multi-column awareness) ──────────
        page_text = _extract_page_text(page)
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


def get_largest_font_lines(pdf_path: str | Path, page_num: int = 0) -> list[str]:
    """Retourne les lignes de texte ayant la plus grande taille de police sur la page.

    Dans un CV, le nom du candidat est presque toujours écrit en plus grande police
    que le reste du texte.

    Returns:
        Liste de chaînes de texte à la taille de police maximale trouvée.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    if page_num >= len(doc):
        doc.close()
        return []

    page = doc[page_num]
    blocks = page.get_text("dict")["blocks"]
    doc.close()

    # Collecter tous les spans avec leur taille et texte
    spans_by_size: dict[float, list[str]] = {}
    for block in blocks:
        for line in block.get("lines", []):
            line_text = "".join(s["text"] for s in line.get("spans", [])).strip()
            if not line_text:
                continue
            for span in line.get("spans", []):
                size = round(span["size"], 1)
                text = span["text"].strip()
                if text:
                    if size not in spans_by_size:
                        spans_by_size[size] = []
                    if line_text not in spans_by_size[size]:
                        spans_by_size[size].append(line_text)

    if not spans_by_size:
        return []

    max_size = max(spans_by_size.keys())
    logger.info("Taille de police max trouvée: %.1fpt — textes: %s", max_size, spans_by_size[max_size])
    return spans_by_size[max_size]
