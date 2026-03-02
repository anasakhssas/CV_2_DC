"""Extraction du nom du candidat depuis le CV."""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# ── Filtres : lignes à ignorer ───────────────────────────────
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"[\+\d][\d\s\-\.\(\)]{7,}")
_URL_RE = re.compile(r"(?i)(https?://|www\.|linkedin\.com|github\.com)")
_DATE_RE = re.compile(r"\b(19|20)\d{2}\b")
_ADDRESS_RE = re.compile(r"(?i)\b(rue|avenue|boulevard|avenue|allée|impasse|bp|"
                         r"street|road|ave|blvd|apt|zip|cedex)\b")

# Mots-clés de sections / titres à exclure
_SECTION_WORDS = re.compile(
    r"(?i)^("
    r"curriculum\s*vitae|cv|resume|profil|profile|présentation|"
    r"compétence|competence|experience|expérience|formation|education|"
    r"contact|coordonnées|langue|skills|projet|project|loisir|"
    r"certif|référence|summary|objective|about"
    r")\b"
)

# Titres de postes fréquents (à ne pas confondre avec un nom)
_JOB_TITLE_WORDS = re.compile(
    r"(?i)\b("
    r"engineer|engineering|developer|développeur|developpeur|ingénieur|ingenieur|"
    r"manager|analyst|consultant|architect|designer|director|officer|"
    r"stagiaire|intern|student|étudiant|etudiant|apprenti|"
    r"chef|lead|senior|junior|fullstack|frontend|backend|"
    r"data\s*scientist|data\s*engineer|devops|technicien|responsable|"
    r"researcher|researcher|scientist|specialist|spécialiste|"
    r"artificial\s*intelligence|machine\s*learning|software|hardware|"
    r"master|bachelor|licence|doctorat|phd|graduate|undergraduate"
    r")\b"
)

# Un nom : 2 à 4 mots, uniquement lettres + tirets + apostrophes
_NAME_PATTERN = re.compile(
    r"^[A-ZÀÂÄÉÈÊËÎÏÔÙÛÜÇ][a-zA-ZÀ-ÿ\'\-]+(?:\s+[A-ZÀ-Ÿ][a-zA-ZÀ-ÿ\'\-]+){1,3}$"
)

# Nom tout en majuscules (ex: "RACHID BATAL")
_NAME_UPPER = re.compile(
    r"^[A-ZÀÂÄÉÈÊËÎÏÙÛÜ\-]{2,}(?:\s+[A-ZÀÂÄÉÈÊËÎÏÙÛÜ\-]{2,}){1,3}$"
)


def _is_valid_name_line(line: str) -> bool:
    """Retourne True si la ligne peut être un nom de candidat."""
    line = line.strip()

    if len(line) < 4 or len(line) > 60:
        return False

    # Exclure si contient email, téléphone, URL
    if _EMAIL_RE.search(line):
        return False
    if _PHONE_RE.search(line):
        return False
    if _URL_RE.search(line):
        return False
    if _DATE_RE.search(line):
        return False
    if _ADDRESS_RE.search(line):
        return False
    if _SECTION_WORDS.search(line):
        return False
    if _JOB_TITLE_WORDS.search(line):
        return False

    # Doit matcher pattern nom
    if _NAME_PATTERN.match(line):
        return True
    if _NAME_UPPER.match(line):
        return True

    return False


def _normalize_name(name: str) -> str:
    """Normalise la casse du nom (Title Case)."""
    # Si tout en majuscules → Title Case
    if name.isupper():
        return name.title()
    return name.strip()


def extract_candidate_name(text: str, pdf_path: str | None = None) -> tuple[str | None, float]:
    """Extrait le nom du candidat depuis le texte du CV.

    Stratégie (par ordre de priorité) :
    1. Plus grande police dans le PDF (si pdf_path fourni) — confiance 0.98
    2. LLM (si disponible) — prompt avec exemples
    3. Fallback regex — analyse les 20 premières lignes

    Returns:
        (nom, confidence)
    """
    # ── 1) Plus grande police ────────────────────────────────
    if pdf_path:
        try:
            from app.services.pdf_extractor import get_largest_font_lines
            largest_lines = get_largest_font_lines(pdf_path, page_num=0)
            for line in largest_lines:
                if _is_valid_name_line(line):
                    name = _normalize_name(line)
                    logger.info("Nom détecté via police (plus grand): %s", name)
                    return name, 0.98
            if largest_lines:
                logger.info("Plus grande police trouvée mais pas un nom valide: %s", largest_lines)
        except Exception as e:
            logger.warning("Erreur détection police: %s", e)

    # ── 2) LLM ──────────────────────────────────────────────
    try:
        from app.services import llm_service
        if llm_service.is_available():
            result = llm_service.extract_name(text)
            if result:
                name = (result.get("candidate_name") or "").strip()
                confidence = float(result.get("confidence") or 0.0)
                if name and confidence > 0.5:
                    name = _normalize_name(name)
                    logger.info("Nom extrait via LLM: %s (confiance %.2f)", name, confidence)
                    return name, confidence
            logger.warning("LLM n'a pas trouvé de nom — fallback regex")
    except Exception as e:
        logger.warning("Erreur LLM pour extraction nom: %s — fallback regex", e)

    # ── 3) Fallback regex ────────────────────────────────────
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    candidates: list[tuple[int, str]] = []

    for i, line in enumerate(lines[:20]):
        if _is_valid_name_line(line):
            candidates.append((i, line))

    if not candidates:
        logger.info("Nom candidat non trouvé dans les 20 premières lignes")
        return None, 0.0

    best_pos, best_line = candidates[0]
    name = _normalize_name(best_line)

    confidence = 0.95 if best_pos <= 3 else (0.80 if best_pos <= 7 else 0.65)
    logger.info("Nom détecté (regex): %s (ligne %d, confiance %.2f)", name, best_pos, confidence)
    return name, confidence
