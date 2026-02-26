"""Extraction des formations / études depuis le texte du CV."""

from __future__ import annotations

import re
import logging
from app.models import Education, LastDegree
from app.config import DEGREE_LEVELS, DEGREE_LEVEL_LABELS

logger = logging.getLogger(__name__)

# ── Patterns de section ─────────────────────────────────────
_SECTION_PATTERNS = re.compile(
    r"(?i)^[\s#*\-]*("
    r"formation|études|etudes|parcours\s*académique|parcours\s*academique|"
    r"diplômes|diplomes|education|academic\s*background"
    r")\s*$",
    re.MULTILINE,
)

# Mots clés diplômes académiques
_DEGREE_KEYWORDS = re.compile(
    r"(?i)\b("
    r"doctorat|phd|doctorate|"
    r"master|msc|mba|ingénieur|ingenieur|"
    r"licence|bachelor|bsc|"
    r"dut|bts|deust|deug|"
    r"baccalauréat|baccalaureat|bac"
    r")\b"
)

# Pattern année
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Mots à exclure (certifications, pas diplômes)
_EXCLUDE_KEYWORDS = re.compile(
    r"(?i)\b(certification|certificate|training|workshop|bootcamp|course|mooc|udemy|coursera|linkedin)\b"
)


def _find_education_section(text: str) -> str:
    """Trouve et retourne la section éducation du CV."""
    matches = list(_SECTION_PATTERNS.finditer(text))
    if not matches:
        return ""

    # Prendre la première correspondance
    start = matches[0].end()

    # Trouver la prochaine section (titre en majuscules ou pattern section)
    next_section = re.search(
        r"(?i)^[\s#*\-]*("
        r"expérience|experience|compétence|competence|skills|"
        r"projet|project|langue|language|certif|"
        r"loisir|hobby|intérêt|interest|profil|profile|"
        r"référence|reference|contact"
        r")\b",
        text[start:],
        re.MULTILINE,
    )

    end = start + next_section.start() if next_section else len(text)
    return text[start:end].strip()


def _extract_entries_from_section(section: str) -> list[dict]:
    """Extrait les entrées diplôme depuis la section éducation."""
    entries = []
    lines = section.split("\n")

    current_entry: dict | None = None

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Ignorer certifications
        if _EXCLUDE_KEYWORDS.search(line_stripped):
            continue

        # Chercher si la ligne contient un diplôme
        degree_match = _DEGREE_KEYWORDS.search(line_stripped)
        years = _YEAR_PATTERN.findall(line_stripped)

        if degree_match or years:
            if current_entry and current_entry.get("degree"):
                entries.append(current_entry)

            current_entry = {
                "degree": line_stripped,
                "years": [int(y) for y in years],
                "evidence": line_stripped,
            }
        elif current_entry:
            # Ligne supplémentaire (école, spécialité…)
            current_entry["degree"] += " " + line_stripped
            current_entry["evidence"] += " | " + line_stripped

    if current_entry and current_entry.get("degree"):
        entries.append(current_entry)

    return entries


def _determine_degree_level(degree_text: str) -> tuple[int, str]:
    """Détermine le niveau du diplôme."""
    text_lower = degree_text.lower()
    best_level = 0
    for keyword, level in DEGREE_LEVELS.items():
        if keyword in text_lower:
            if level > best_level:
                best_level = level

    label = DEGREE_LEVEL_LABELS.get(best_level, "Inconnu")
    return best_level, label


def extract_educations(text: str) -> list[Education]:
    """Extrait toutes les formations depuis le texte du CV."""
    # Essayer d'abord la section dédiée
    section = _find_education_section(text)

    # Fallback : chercher dans tout le texte
    if not section:
        logger.info("Section éducation non trouvée, recherche globale")
        section = text

    raw_entries = _extract_entries_from_section(section)

    educations: list[Education] = []
    for entry in raw_entries:
        years = entry.get("years", [])
        year = max(years) if years else None  # Année fin = année diplôme

        degree_text = entry["degree"]

        # Déterminer le niveau
        level_num, level_label = _determine_degree_level(degree_text)

        # Vérifier si "en cours"
        status = "obtained"
        if re.search(r"(?i)(en cours|in progress|ongoing|current)", degree_text):
            status = "en_cours"

        # Confiance basée sur présence année + mot clé diplôme
        confidence = 0.5
        if year:
            confidence += 0.25
        if _DEGREE_KEYWORDS.search(degree_text):
            confidence += 0.25

        educations.append(Education(
            year=year,
            degree=degree_text.strip(),
            degree_level=level_label if level_num > 0 else None,
            status=status,
            evidence=entry.get("evidence", ""),
            confidence=round(confidence, 2),
        ))

    return educations


def determine_last_degree(educations: list[Education]) -> LastDegree | None:
    """Détermine le dernier diplôme (le plus élevé).

    Règle RH : dernier diplôme = diplôme le plus élevé obtenu.
    Si même niveau → le plus récent.
    """
    if not educations:
        return None

    def _sort_key(edu: Education) -> tuple:
        level_num = 0
        text_lower = edu.degree.lower()
        for keyword, level in DEGREE_LEVELS.items():
            if keyword in text_lower:
                level_num = max(level_num, level)
        return (level_num, edu.year or 0)

    best = max(educations, key=_sort_key)

    level_num, level_label = _determine_degree_level(best.degree)

    return LastDegree(
        degree=best.degree,
        level=level_label if level_num > 0 else None,
        school=best.school,
        year=best.year,
        confidence=best.confidence,
    )
