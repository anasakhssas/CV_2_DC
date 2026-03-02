"""Extraction des langues depuis le CV par correspondance dans une liste prédéfinie."""

from __future__ import annotations

import re
import logging

from app.config import LANGUAGE_LEVEL_MAP
from app.models import Language

logger = logging.getLogger(__name__)

# ── Liste de référence : toutes les variantes → nom normalisé ──────────────
# Chaque clé est un mot-clé (en minuscules) tel qu'il peut apparaître dans un CV.
# La valeur est le nom affiché dans le dossier de compétences.
PREDEFINED_LANGUAGES: dict[str, str] = {
    # Arabe
    "arabe":      "Arabe",
    "arabic":     "Arabe",
    # Français
    "français":   "Français",
    "francais":   "Français",
    "french":     "Français",
    # Anglais
    "anglais":    "Anglais",
    "english":    "Anglais",
    # Espagnol
    "espagnol":   "Espagnol",
    "spanish":    "Espagnol",
    "español":    "Espagnol",
    # Allemand
    "allemand":   "Allemand",
    "german":     "Allemand",
    "deutsch":    "Allemand",
    # Italien
    "italien":    "Italien",
    "italian":    "Italien",
    # Portugais
    "portugais":  "Portugais",
    "portuguese": "Portugais",
    # Chinois
    "chinois":    "Chinois",
    "chinese":    "Chinois",
    "mandarin":   "Chinois",
    # Japonais
    "japonais":   "Japonais",
    "japanese":   "Japonais",
    # Russe
    "russe":      "Russe",
    "russian":    "Russe",
    # Turc
    "turc":       "Turc",
    "turkish":    "Turc",
    # Néerlandais
    "néerlandais": "Néerlandais",
    "neerlandais": "Néerlandais",
    "dutch":       "Néerlandais",
    # Coréen
    "coréen":     "Coréen",
    "korean":     "Coréen",
    # Amazigh / Berbère
    "amazigh":    "Amazigh",
    "berbère":    "Amazigh",
    "berbere":    "Amazigh",
    "tamazight":  "Amazigh",
    # Hindi
    "hindi":      "Hindi",
    # Turc (déjà listé) / Persan
    "persan":     "Persan",
    "persian":    "Persan",
    "farsi":      "Persan",
    # Hébreu
    "hébreu":     "Hébreu",
    "hebreu":     "Hébreu",
    "hebrew":     "Hébreu",
}

# Ordre d'affichage souhaité (les plus courantes d'abord)
_DISPLAY_ORDER = [
    "Arabe", "Français", "Anglais", "Espagnol", "Allemand", "Italien",
    "Portugais", "Amazigh", "Chinois", "Japonais", "Russe", "Turc",
    "Néerlandais", "Coréen", "Hindi", "Persan", "Hébreu",
]


def _find_language_level(text: str, language_keyword: str) -> tuple[float, str | None, str | None]:
    """Cherche le niveau d'une langue dans le contexte proche du mot-clé.

    Retourne (level, level_label, evidence).
    Cherche APRÈS le mot-clé de la langue, jusqu'au prochain séparateur
    (virgule, point-virgule, saut de ligne, ou prochain mot-clé de langue).
    Cela évite de « saigner » le niveau d'une langue voisine.
    """
    text_lower = text.lower()
    pattern = r"(?<![a-zA-ZÀ-ÿ])" + re.escape(language_keyword) + r"(?![a-zA-ZÀ-ÿ])"
    match = re.search(pattern, text_lower)
    if not match:
        return 3.0, None, None

    # Contexte : début de la ligne courante → prochain séparateur après le mot-clé
    # On ne regarde PAS en arrière au-delà du début de la ligne pour éviter le bleed
    line_start = text_lower.rfind("\n", 0, match.start())
    line_start = line_start + 1 if line_start >= 0 else 0
    # Aussi ne pas remonter avant une virgule/point-virgule/pipe
    sep_before = max(
        text_lower.rfind(",", line_start, match.start()),
        text_lower.rfind(";", line_start, match.start()),
        text_lower.rfind("|", line_start, match.start()),
    )
    ctx_start = sep_before + 1 if sep_before >= 0 else line_start

    after_text = text_lower[match.end():]

    # Trouver la fin du contexte : prochain séparateur ou prochain nom de langue
    sep_match = re.search(r"[,;|\n]", after_text)
    # Aussi chercher le prochain mot-clé de langue
    next_lang_pos = len(after_text)
    for kw in PREDEFINED_LANGUAGES:
        if kw == language_keyword:
            continue
        lang_pat = r"(?<![a-zA-ZÀ-ÿ])" + re.escape(kw) + r"(?![a-zA-ZÀ-ÿ])"
        lang_m = re.search(lang_pat, after_text)
        if lang_m and lang_m.start() < next_lang_pos:
            next_lang_pos = lang_m.start()

    ctx_end_offset = min(
        sep_match.start() if sep_match else len(after_text),
        next_lang_pos,
        80,  # max 80 chars après
    )
    context = text_lower[ctx_start:match.end() + ctx_end_offset]
    evidence = text[ctx_start:match.end() + ctx_end_offset].strip().replace("\n", " ")

    # Cherche les mots-clés de niveau dans le contexte (le plus spécifique d'abord)
    best_level: float | None = None
    best_label: str | None = None
    best_len = 0

    for level_keyword, level_value in LANGUAGE_LEVEL_MAP.items():
        level_pattern = r"(?<![a-zA-ZÀ-ÿ])" + re.escape(level_keyword) + r"(?![a-zA-ZÀ-ÿ])"
        if re.search(level_pattern, context) and len(level_keyword) > best_len:
            best_len = len(level_keyword)
            best_level = level_value
            best_label = level_keyword.title()

    if best_level is not None:
        return best_level, best_label, evidence

    return 3.0, None, evidence


def extract_languages(text: str) -> list[str]:
    """Scanne le texte du CV et retourne les langues présentes dans la liste prédéfinie.

    Algorithme :
      1. Normaliser le texte (bas de casse, accents simplifiés pour le matching).
      2. Pour chaque mot-clé de PREDEFINED_LANGUAGES, chercher une correspondance
         mot-entier (\\b) dans le texte complet.
      3. Dédupliquer par nom normalisé.
      4. Retourner dans l'ordre d'affichage standard (pas de limite de nombre).
    """
    text_lower = text.lower()
    found: set[str] = set()

    for keyword, normalized_name in PREDEFINED_LANGUAGES.items():
        if normalized_name in found:
            continue  # déjà détectée via un autre alias
        pattern = r"(?<![a-zA-ZÀ-ÿ])" + re.escape(keyword) + r"(?![a-zA-ZÀ-ÿ])"
        if re.search(pattern, text_lower):
            found.add(normalized_name)
            logger.debug("Langue détectée : %s (via « %s »)", normalized_name, keyword)

    # Retourner dans l'ordre de référence; langues inconnues à la fin
    ordered = [l for l in _DISPLAY_ORDER if l in found]
    extras  = sorted(found - set(_DISPLAY_ORDER))
    result  = ordered + extras

    logger.info("Langues trouvées : %s", result)
    return result


def extract_languages_with_levels(text: str) -> list[Language]:
    """Scanne le texte du CV et retourne les langues avec leur niveau /5.

    Algorithme :
      1. Détecte les langues présentes via PREDEFINED_LANGUAGES.
      2. Pour chaque langue, cherche le niveau dans le contexte proche
         (LANGUAGE_LEVEL_MAP : "courant" → 4, "natif" → 5, "B2" → 3.5, etc.).
      3. Retourne des objets Language avec name, level, level_label.
    """
    text_lower = text.lower()
    found: dict[str, str] = {}  # normalized_name → keyword utilisé

    for keyword, normalized_name in PREDEFINED_LANGUAGES.items():
        if normalized_name in found:
            continue
        pattern = r"(?<![a-zA-ZÀ-ÿ])" + re.escape(keyword) + r"(?![a-zA-ZÀ-ÿ])"
        if re.search(pattern, text_lower):
            found[normalized_name] = keyword
            logger.debug("Langue détectée : %s (via « %s »)", normalized_name, keyword)

    # Construire les Language avec niveaux
    languages: list[Language] = []
    for normalized_name in _DISPLAY_ORDER:
        if normalized_name not in found:
            continue
        keyword = found[normalized_name]
        level, level_label, evidence = _find_language_level(text, keyword)
        languages.append(Language(
            name=normalized_name,
            level=level,
            level_label=level_label,
            evidence=evidence,
            confidence=0.9 if level_label else 0.6,
        ))

    # Langues hors de _DISPLAY_ORDER
    for normalized_name in sorted(found.keys()):
        if normalized_name in {l.name for l in languages}:
            continue
        keyword = found[normalized_name]
        level, level_label, evidence = _find_language_level(text, keyword)
        languages.append(Language(
            name=normalized_name,
            level=level,
            level_label=level_label,
            evidence=evidence,
            confidence=0.9 if level_label else 0.6,
        ))

    logger.info("Langues avec niveaux : %s", [(l.name, l.level) for l in languages])
    return languages
