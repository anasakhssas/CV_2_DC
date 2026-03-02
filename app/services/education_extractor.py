"""Extraction des formations / études depuis le texte du CV."""

from __future__ import annotations

import re
import logging
from app.models import Education, LastDegree
from app.config import DEGREE_LEVELS, DEGREE_LEVEL_LABELS

logger = logging.getLogger(__name__)

# Heading pattern – lenient: match anywhere on a line, allow trailing content
_SECTION_HEADING = re.compile(
    r"(?i)(?:^|\n)[^\n]*\b("
    r"formations?|\u00e9tudes|etudes|parcours\s*acad[e\u00e9]mique|"
    r"dipl[o\u00f4]mes?|education|academic\s*background|scolarit[e\u00e9]|"
    r"cursus|background\s*acad[e\u00e9]mique|background\s*scolaire|"
    r"qualifications?|academic\s*qualifications?|"
    r"parcours\s*scolaire|parcours\s*universitaire|"
    r"\u00e9tudes\s*sup[e\u00e9]rieures|formations?\s*acad[e\u00e9]miques?|"
    r"lyc[e\u00e9]e|universit[e\u00e9]|\u00e9tablissements?|schooling"
    r")\b",
    re.MULTILINE,
)

# Next-section heading to determine where education ends
_NEXT_SECTION_HEADING = re.compile(
    r"(?i)(?:^|\n)[^\n]*\b("
    r"exp[e\u00e9]riences?|professional\s*experience|work\s*experience|emploi|"
    r"comp[e\u00e9]tences?|skills|langues?|languages?|certif|projets?|projects?|"
    r"loisirs?|hobbies?|interests?|r[e\u00e9]f[e\u00e9]rences?|contact|profil|summary"
    r")\b",
    re.MULTILINE,
)
_DEGREE_KEYWORDS = re.compile(
    r"(?i)\b("
    r"doctorat|phd|doctorate|these|th\u00e8se|"
    r"master|mastere|mast\u00e8re|msc|mba|m2|m1|"
    r"ing[e\u00e9]nieur|cycle\s*ing[e\u00e9]nieur|\u00e9cole\s*d.ing[e\u00e9]nieur|"
    r"licence|bachelor|bsc|ba|l3|l2|l1|"
    r"dut|bts|deust|deug|bpro|"
    r"baccalaur[e\u00e9]at|baccalaureat|bac|"
    r"classes?\s*pr[e\u00e9]pa|cpge|mp|pc|psi|\u00e9conomique|scientifique|"
    r"dipl[o\u00f4]me|degree|graduate|undergraduate|postgraduate"
    r")\b"
)

# Pattern année ── non-capturing group pour que findall retourne l'année entière
_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")

# Ligne qui ressemble à une plage de dates (expérience) : JJ/MM/AAAA - JJ/MM/AAAA
_DATE_RANGE_LINE = re.compile(
    r"(?i)^\s*(?:\d{1,2}[/\-])?(?:\d{1,2}[/\-])?(?:19|20)\d{2}"
    r"\s*[\-–—à/]\s*"
    r"(?:\d{1,2}[/\-])?(?:\d{1,2}[/\-])?(?:(?:19|20)\d{2}|présent|present|actuel)"
)

# Mots à exclure (certifications, pas diplômes)
_EXCLUDE_KEYWORDS = re.compile(
    r"(?i)\b(certification|certificate|training|workshop|bootcamp|course|mooc|udemy|coursera|linkedin)\b"
)

# Indicateurs d'école / établissement
_SCHOOL_KEYWORDS = re.compile(
    r"(?i)\b("
    r"université|universite|university|école|ecole|school|"
    r"institut|institute|faculty|faculté|faculte|"
    r"ensam|ensa|enset|est|iut|iup|cpge|classes? prépa|"
    r"lycée|lycee|college|hautes?\s*études|grandes?\s*écoles?"
    r")\b"
)


def find_education_section(text: str) -> str:
    """Trouve et retourne la section éducation du CV (API publique)."""
    return _find_education_section(text)


def _find_education_section(text: str) -> str:
    """Trouve et retourne la section éducation du CV."""
    m = _SECTION_HEADING.search(text)
    if not m:
        return ""

    # Start after the matched heading line
    start = text.index("\n", m.start()) + 1 if "\n" in text[m.start():] else m.end()

    # Find end: next known section heading that appears AFTER start
    next_m = _NEXT_SECTION_HEADING.search(text, start)
    end = next_m.start() if next_m else len(text)

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

        # Ignorer les lignes qui ressemblent à des plages de dates d'expérience
        if _DATE_RANGE_LINE.match(line_stripped) and not _DEGREE_KEYWORDS.search(line_stripped):
            continue

        degree_match = _DEGREE_KEYWORDS.search(line_stripped)
        years = _YEAR_PATTERN.findall(line_stripped)

        if degree_match or (years and not _DATE_RANGE_LINE.match(line_stripped)):
            if current_entry and current_entry.get("degree"):
                entries.append(current_entry)

            current_entry = {
                "degree": line_stripped,
                "school": None,
                "years": [int(y) for y in years],
                "evidence": line_stripped,
            }
        elif current_entry:
            # Ligne supplémentaire : détecter école ou enrichir le diplôme
            if _SCHOOL_KEYWORDS.search(line_stripped) and not current_entry["school"]:
                current_entry["school"] = line_stripped
                current_entry["evidence"] += " | " + line_stripped
            elif not current_entry["school"] and not _YEAR_PATTERN.search(line_stripped):
                # Deuxième ligne non-date → probablement l'école
                current_entry["school"] = line_stripped
                current_entry["evidence"] += " | " + line_stripped
            else:
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
    logger.info("Education section found: %d chars", len(section))

    if section:
        raw_entries = _extract_entries_from_section(section)
        logger.info("Regex entries from section: %d", len(raw_entries))
    else:
        raw_entries = []

    # Fallback 1 : chercher dans tout le texte si section non trouvée
    if not raw_entries:
        logger.info("Fallback: searching full text for degree keywords")
        raw_entries = _extract_entries_from_section(text)
        logger.info("Regex entries from full text: %d", len(raw_entries))

    # Fallback 2 : chercher ligne par ligne les mots-clés de diplôme
    if not raw_entries:
        logger.info("Fallback 2: line-by-line degree keyword scan")
        for line in text.split("\n"):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if _EXCLUDE_KEYWORDS.search(line_stripped):
                continue
            if _DEGREE_KEYWORDS.search(line_stripped):
                years = _YEAR_PATTERN.findall(line_stripped)
                raw_entries.append({
                    "degree": line_stripped,
                    "school": None,
                    "years": [int(y) for y in years],
                    "evidence": line_stripped,
                })
        logger.info("Fallback 2 entries: %d", len(raw_entries))

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
            school=entry.get("school"),
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
