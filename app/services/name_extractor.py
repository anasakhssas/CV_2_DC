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
    r"engineer|developer|developer|ingénieur|développeur|developpeur|"
    r"manager|analyst|consultant|architect|designer|director|"
    r"stagiaire|intern|chef|lead|senior|junior|fullstack|frontend|backend|"
    r"data\s*scientist|devops|technicien|responsable"
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


def extract_candidate_name(text: str) -> tuple[str | None, float]:
    """Extrait le nom du candidat depuis le texte du CV.

    Stratégie :
    - Analyser les 20 premières lignes non vides (le nom est presque toujours en haut)
    - Filtrer les lignes qui ne sont pas un nom (email, tél, URL, section, poste)
    - Valider via pattern nom (2–4 mots capitalisés)

    Returns:
        (nom, confidence)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Analyser les 20 premières lignes
    candidates: list[tuple[int, str]] = []  # (position, ligne)

    for i, line in enumerate(lines[:20]):
        if _is_valid_name_line(line):
            candidates.append((i, line))

    if not candidates:
        logger.info("Nom candidat non trouvé dans les 20 premières lignes")
        return None, 0.0

    # Prendre le candidat le plus proche du début
    best_pos, best_line = candidates[0]
    name = _normalize_name(best_line)

    # Confiance : plus c'est en haut, plus c'est fiable
    confidence = 0.95 if best_pos <= 3 else (0.80 if best_pos <= 7 else 0.65)

    logger.info("Nom détecté: %s (ligne %d, confiance %.2f)", name, best_pos, confidence)
    return name, confidence
