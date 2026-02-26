"""Extraction et normalisation des langues depuis le CV."""

from __future__ import annotations

import re
import logging
from app.models import Language
from app.config import LANGUAGE_LEVEL_MAP

logger = logging.getLogger(__name__)

# ── Section langues ─────────────────────────────────────────
_SECTION_PATTERN = re.compile(
    r"(?i)^[\s#*\-]*("
    r"langues|languages|compétences\s*linguistiques|language\s*skills|"
    r"linguistic\s*skills"
    r")\s*$",
    re.MULTILINE,
)

# Langues connues (FR + EN + AR + ES + DE + …)
_KNOWN_LANGUAGES = {
    # Français
    "français": "Français", "francais": "Français", "french": "Français",
    # Anglais
    "anglais": "Anglais", "english": "Anglais",
    # Arabe
    "arabe": "Arabe", "arabic": "Arabe",
    # Espagnol
    "espagnol": "Espagnol", "spanish": "Espagnol", "español": "Espagnol",
    # Allemand
    "allemand": "Allemand", "german": "Allemand", "deutsch": "Allemand",
    # Italien
    "italien": "Italien", "italian": "Italien",
    # Portugais
    "portugais": "Portugais", "portuguese": "Portugais",
    # Chinois
    "chinois": "Chinois", "chinese": "Chinois", "mandarin": "Chinois",
    # Japonais
    "japonais": "Japonais", "japanese": "Japonais",
    # Russe
    "russe": "Russe", "russian": "Russe",
    # Turc
    "turc": "Turc", "turkish": "Turc",
    # Néerlandais
    "néerlandais": "Néerlandais", "dutch": "Néerlandais",
    # Coréen
    "coréen": "Coréen", "korean": "Coréen",
    # Amazigh / Berbère
    "amazigh": "Amazigh", "berbère": "Amazigh", "tamazight": "Amazigh",
    # Hindi
    "hindi": "Hindi",
}

# Niveau CEFR pattern
_CEFR_PATTERN = re.compile(r"\b([ABC][12])\b", re.IGNORECASE)

# Niveau textuel
_LEVEL_KEYWORDS = re.compile(
    r"(?i)\b("
    r"native|mother\s*tongue|langue\s*maternelle|bilingue|bilingual|"
    r"fluent|couramment|courant|"
    r"professional\s*(?:working\s*)?proficiency|full\s*professional\s*proficiency|"
    r"upper\s*intermediate|intermédiaire\s*avancé|"
    r"intermediate|intermédiaire|"
    r"basic|basique|notions|scolaire|elementary|"
    r"beginner|débutant"
    r")\b"
)


def _find_language_section(text: str) -> str:
    """Trouve la section langues."""
    matches = list(_SECTION_PATTERN.finditer(text))
    if not matches:
        return ""

    start = matches[0].end()
    next_section = re.search(
        r"(?i)^[\s#*\-]*("
        r"compétence|competence|skills|expérience|experience|"
        r"formation|education|projet|project|loisir|hobby|"
        r"intérêt|interest|référence|reference|certif|contact"
        r")\b",
        text[start:],
        re.MULTILINE,
    )
    end = start + next_section.start() if next_section else len(text)
    return text[start:end].strip()


def _detect_level(context: str) -> tuple[float, str, float]:
    """Détecte le niveau d'une langue depuis le contexte.

    Returns:
        (level_numeric, level_label, confidence)
    """
    context_lower = context.lower().strip()

    # 1) Chercher CEFR
    cefr = _CEFR_PATTERN.search(context)
    if cefr:
        cefr_val = cefr.group(1).upper()
        level = LANGUAGE_LEVEL_MAP.get(cefr_val.lower(), 3)
        return level, cefr_val, 0.95

    # 2) Chercher mots clés de niveau
    for level_key, level_val in sorted(LANGUAGE_LEVEL_MAP.items(), key=lambda x: -len(x[0])):
        if level_key in context_lower:
            return level_val, level_key.title(), 0.85

    # 3) Aucun niveau trouvé
    return 0, "Inconnu", 0.3


def extract_languages(text: str) -> list[Language]:
    """Extrait les langues avec normalisation du niveau /5.

    Retourne le Top 3 langues triées par niveau décroissant.
    """
    # Chercher section dédiée d'abord
    section = _find_language_section(text)

    # Fallback : chercher dans tout le texte
    search_text = section if section else text

    found_languages: dict[str, Language] = {}

    # Parcourir chaque ligne à la recherche de langues connues
    for line in search_text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        line_lower = line_stripped.lower()

        for lang_key, lang_name in _KNOWN_LANGUAGES.items():
            if lang_key in line_lower:
                # Éviter les faux positifs (ex: "French fries")
                if not re.search(r"(?i)\b" + re.escape(lang_key) + r"\b", line_stripped):
                    continue

                level, label, confidence = _detect_level(line_stripped)

                # Si déjà trouvé avec un meilleur niveau, garder le meilleur
                if lang_name in found_languages:
                    existing = found_languages[lang_name]
                    if level > existing.level:
                        found_languages[lang_name] = Language(
                            name=lang_name,
                            level=level,
                            level_label=label,
                            evidence=line_stripped,
                            confidence=confidence,
                        )
                else:
                    found_languages[lang_name] = Language(
                        name=lang_name,
                        level=level if level > 0 else 2.5,  # défaut si pas de niveau
                        level_label=label if level > 0 else "Non spécifié",
                        evidence=line_stripped,
                        confidence=confidence if level > 0 else 0.3,
                    )

    # Trier par niveau décroissant, garder Top 3
    languages = sorted(found_languages.values(), key=lambda l: l.level, reverse=True)
    return languages[:3]
