"""Extraction des formations / études depuis le texte du CV.

Architecture : Regex-first + LLM-validator
──────────────────────────────────────────
1. Regex localise la section éducation et extrait les entrées brutes
2. Block-based parser découpe en blocs cohérents (vs ligne par ligne)
3. Normalisation des diplômes via mapping regex
4. Détection multi-colonnes pour les PDFs complexes
5. Si LLM dispo → validation + correction des résultats regex
6. Si regex vide → LLM en extraction complète (fallback)
"""

from __future__ import annotations

import re
import logging
from app.models import Education, LastDegree
from app.config import DEGREE_LEVELS, DEGREE_LEVEL_LABELS, DEGREE_NORMALIZATION

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  REGEX PATTERNS
# ─────────────────────────────────────────────────────────────

# Heading pattern – STRICT: keyword must be the main content of the line,
# not buried inside a sentence.  We require the keyword to appear near the
# start of the line (at most a few decoration chars before it) so that
# "d'études axé sur…" in a PROFIL paragraph is NOT matched.
_SECTION_HEADING = re.compile(
    r"(?i)(?:^|\n)\s{0,4}[#*\-–—]*\s*("
    r"formations?|parcours\s*acad[e\u00e9]mique|"
    r"dipl[o\u00f4]mes?|education|academic\s*background|scolarit[e\u00e9]|"
    r"cursus|background\s*acad[e\u00e9]mique|background\s*scolaire|"
    r"qualifications?|academic\s*qualifications?|"
    r"parcours\s*scolaire|parcours\s*universitaire|"
    r"\u00e9tudes\s*sup[e\u00e9]rieures|formations?\s*acad[e\u00e9]miques?"
    r")\b[^\n]{0,30}$",
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
    r"baccalaur[e\u00e9]at|baccalaureat|baccalaureate|bac|"
    r"classes?\s*pr[e\u00e9]pa|cpge|mp|pc|psi|\u00e9conomique|scientifique|"
    r"dipl[o\u00f4]me|degree|graduate|undergraduate|postgraduate"
    r")\b"
)

# Pattern année
_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")

# Ligne qui ressemble à une plage de dates (expérience)
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

# Bullet-point start
_BULLET_START = re.compile(r"^[•\-\*▪►▸◦‣⁃]\s+")

# Mots-clés techniques (un diplôme ne devrait pas en contenir beaucoup)
_TECH_KEYWORDS = re.compile(
    r"(?i)\b(python|java|javascript|sql|fastapi|spring|react|docker|kubernetes|"
    r"postgresql|mongodb|mysql|git|aws|azure|tensorflow|pytorch|langchain)\b"
)


# ─────────────────────────────────────────────────────────────
#  MULTI-COLUMN DETECTION
# ─────────────────────────────────────────────────────────────

def detect_column_layout(text: str) -> bool:
    """Détecte si le texte semble provenir d'un PDF multicolonnes.

    Heuristique : si > 30% des lignes non-vides ont un grand espace
    au milieu (4+ espaces entre deux mots), le PDF est probablement
    multicolonnes.
    """
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    wide_gap_count = sum(1 for l in lines if re.search(r"\S\s{4,}\S", l))
    ratio = wide_gap_count / len(lines)
    is_multi = ratio > 0.3
    if is_multi:
        logger.info("🔲 Layout multicolonnes détecté (%.0f%% lignes avec large gap)", ratio * 100)
    return is_multi


def _fix_multicolumn_text(text: str) -> str:
    """Tente de corriger le texte extrait d'un PDF multicolonnes.

    Stratégie : pour les lignes avec un grand gap, on coupe au milieu
    et on empile gauche puis droite.
    """
    left_lines: list[str] = []
    right_lines: list[str] = []

    for line in text.split("\n"):
        # Cherche un gap de 4+ espaces
        gap_match = re.search(r"(\S)\s{4,}(\S)", line)
        if gap_match:
            mid = gap_match.start() + 1
            left_part = line[:mid].strip()
            right_part = line[mid:].strip()
            if left_part:
                left_lines.append(left_part)
            if right_part:
                right_lines.append(right_part)
        else:
            left_lines.append(line)

    # On concatène : d'abord la colonne gauche, puis la droite
    return "\n".join(left_lines) + "\n" + "\n".join(right_lines)


# ─────────────────────────────────────────────────────────────
#  SECTION DETECTION
# ─────────────────────────────────────────────────────────────

def find_education_section(text: str) -> str:
    """Trouve et retourne la section éducation du CV (API publique)."""
    return _find_education_section(text)


def _find_education_section(text: str) -> str:
    """Trouve et retourne la section éducation du CV."""
    m = _SECTION_HEADING.search(text)
    if not m:
        return ""

    # Skip past the entire heading line (find the newline AFTER the match end)
    end_of_heading = text.find("\n", m.end())
    start = end_of_heading + 1 if end_of_heading >= 0 else m.end()

    # Find end: next known section heading that appears AFTER start
    next_m = _NEXT_SECTION_HEADING.search(text, start)
    end = next_m.start() if next_m else len(text)

    return text[start:end].strip()


# ─────────────────────────────────────────────────────────────
#  BLOCK-BASED PARSER (amélioration vs ligne par ligne)
# ─────────────────────────────────────────────────────────────

def _split_into_education_blocks(section: str) -> list[str]:
    """Découpe la section éducation en blocs par entrée diplôme.

    A new block starts when:
      • a line carries a *component* (school / degree / date-range / year)
        that **duplicates** a component already present in the current block,
        AND the current block already has ≥ 2 distinct component types;
      • a degree-keyword line appears after the current block already has
        school + year (school-first format where the degree line has no
        explicit degree keyword on the first entry).

    A "component type" is one of: school, degree, year.
    """
    blocks: list[str] = []
    current: list[str] = []
    cur_school = False
    cur_degree = False
    cur_year = False

    for line in section.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _EXCLUDE_KEYWORDS.search(stripped):
            continue

        line_school = bool(_SCHOOL_KEYWORDS.search(stripped))
        line_degree = bool(_DEGREE_KEYWORDS.search(stripped[:60]))
        line_year = bool(_YEAR_PATTERN.search(stripped))
        line_date_range = bool(_DATE_RANGE_LINE.match(stripped))
        line_year_first = bool(_YEAR_PATTERN.match(stripped))

        start_new = False
        if current:
            components = sum([cur_school, cur_degree, cur_year])
            if components >= 2:
                # A duplicate component signals a new entry
                if line_school and cur_school:
                    start_new = True
                elif line_degree and cur_degree:
                    start_new = True
                elif line_date_range and cur_year:
                    start_new = True
                elif line_year_first and cur_year:
                    start_new = True

            # Degree-keyword line after school+year (school-first format)
            if (
                not start_new
                and line_degree
                and cur_school
                and cur_year
                and not cur_degree
            ):
                start_new = True

        if start_new:
            blocks.append("\n".join(current))
            current = []
            cur_school = cur_degree = cur_year = False

        current.append(stripped)
        if line_school:
            cur_school = True
        if line_degree:
            cur_degree = True
        if line_year:
            cur_year = True

    if current:
        blocks.append("\n".join(current))

    return blocks


# Pattern: "Degree text | year" or "Degree text | year - year"
_PIPE_YEAR = re.compile(r"\s*\|\s*(?:(\d{4})\s*(?:[-–—]\s*\d{4})?\s*)$")


def _parse_block(block: str) -> dict | None:
    """Parse un bloc de texte en une entrée diplôme structurée.

    Uses a two-pass approach:
      Pass 1 – classify each line by explicit keywords (school / degree / year-only).
      Pass 2 – assign remaining lines (no keyword) by context: if we already
               know the school, unassigned text is the degree and vice-versa.

    Handles common CV formats:
      Format A (school first):   École Nationale … | Engineering Student … | 2026
      Format B (degree first):   Licence … | Faculté … | 2023
      Format C (year first):     2029 - 2031 | Master … | School of … | GPA …
      Format D (no keyword):     Data Science & AI Engineering | ENSAM Rabat | 2023-2026

    Retourne un dict {degree, school, years, evidence} ou None si invalide.
    """
    raw_lines = [l.strip() for l in block.split("\n") if l.strip()]
    if not raw_lines:
        return None

    # ── Pre-process each line ──────────────────────────────────
    info: list[dict] = []
    all_years: list[int] = []

    for raw in raw_lines:
        txt = raw

        # Strip pipe+year suffix  (e.g.  "Degree title | 2023")
        pipe_m = _PIPE_YEAR.search(txt)
        pipe_year: int | None = None
        if pipe_m:
            if pipe_m.group(1):
                pipe_year = int(pipe_m.group(1))
            txt = txt[: pipe_m.start()].strip()

        years = [int(y) for y in _YEAR_PATTERN.findall(txt)]
        if pipe_year:
            years.append(pipe_year)
        all_years.extend(years)

        text_clean = re.sub(r"\b(?:19|20)\d{2}\b", "", txt)
        text_clean = re.sub(r"[\s\-–—:|/]+$", "", text_clean).strip()

        has_school = bool(_SCHOOL_KEYWORDS.search(txt))
        has_degree = bool(_DEGREE_KEYWORDS.search(txt[:60]))
        year_only = bool(years) and not text_clean

        info.append(
            {
                "raw": raw,
                "text": text_clean,
                "years": years,
                "has_school": has_school,
                "has_degree": has_degree,
                "year_only": year_only,
                "role": None,  # 'school' | 'degree' | 'year' | 'extra'
            }
        )

    # ── Pass 1: assign lines that carry explicit keywords ──────
    for li in info:
        if li["year_only"]:
            li["role"] = "year"
        elif li["has_school"] and not li["has_degree"]:
            li["role"] = "school"
        elif li["has_degree"] and not li["has_school"]:
            li["role"] = "degree"
        elif li["has_school"] and li["has_degree"]:
            li["role"] = "school"  # "Master at University X" → treat as school

    # ── Pass 2: assign remaining lines by context ──────────────
    has_explicit_school = any(li["role"] == "school" for li in info)
    has_explicit_degree = any(li["role"] == "degree" for li in info)

    for li in info:
        if li["role"] is not None or not li["text"]:
            continue
        if has_explicit_school and not has_explicit_degree:
            li["role"] = "degree"
            has_explicit_degree = True
        elif has_explicit_degree and not has_explicit_school:
            li["role"] = "school"
            has_explicit_school = True
        elif not has_explicit_school and not has_explicit_degree:
            # Neither keyword → first unassigned text is degree
            li["role"] = "degree"
            has_explicit_degree = True
        else:
            li["role"] = "extra"

    # ── Collect school & degree ────────────────────────────────
    school_parts = [li["text"] for li in info if li["role"] == "school" and li["text"]]
    degree_parts = [li["text"] for li in info if li["role"] == "degree" and li["text"]]

    school: str | None = school_parts[0] if school_parts else None
    if school:
        # Remove trailing "City, Country"
        school = re.sub(
            r",?\s+[A-ZÀ-Ÿ][a-zà-ÿ]+,\s*[A-ZÀ-Ÿ][a-zà-ÿ]+\s*$", "", school
        ).strip() or school

    if not degree_parts:
        return None

    degree_text = " ".join(degree_parts).strip()

    # Séparer année du texte du diplôme si elle est dedans
    degree_clean = re.sub(r"\b(?:19|20)\d{2}\b", "", degree_text)
    degree_clean = re.sub(r"[\s\-–—:|]+$", "", degree_clean)  # trailing separators
    degree_clean = re.sub(r"^[\s\-–—:|]+", "", degree_clean)  # leading separators
    degree_clean = re.sub(r"\s+", " ", degree_clean).strip()
    if not degree_clean:
        degree_clean = degree_text

    # Vérifier que ce n'est pas du contenu technique
    tech_count = len(_TECH_KEYWORDS.findall(degree_clean))
    if tech_count >= 3:
        logger.warning("Bloc rejeté (trop de mots-clés techniques): %s", degree_clean[:80])
        return None

    return {
        "degree": degree_clean,
        "school": school,
        "years": list(set(all_years)),  # dédupliquer
        "evidence": " | ".join(li["raw"] for li in info),
    }


def _extract_entries_from_section(section: str) -> list[dict]:
    """Extrait les entrées diplôme via le block-based parser."""
    blocks = _split_into_education_blocks(section)
    logger.info("Section découpée en %d blocs", len(blocks))

    entries: list[dict] = []
    for block in blocks:
        parsed = _parse_block(block)
        if parsed:
            entries.append(parsed)

    return entries


# ─────────────────────────────────────────────────────────────
#  DEGREE NORMALIZATION
# ─────────────────────────────────────────────────────────────

def normalize_degree_name(degree: str) -> str:
    """Normalise le nom d'un diplôme via le mapping regex de config.

    Ex: "cycle d'ingenieur" → "Cycle Ingénieur"
        "classes preparatoires aux grandes ecoles" → "Classes Préparatoires (CPGE)"
        "baccalaureat" → "Baccalauréat"

    Si aucun pattern ne matche, retourne le degree original nettoyé.
    """
    for pattern, replacement in DEGREE_NORMALIZATION:
        if re.search(pattern, degree):
            # Remplacer seulement la partie qui matche
            degree = re.sub(pattern, replacement, degree, count=1)
            break  # un seul remplacement principal

    # Nettoyage final : espaces multiples, tirets multiples
    degree = re.sub(r"\s+", " ", degree).strip()
    return degree


# ─────────────────────────────────────────────────────────────
#  DEGREE LEVEL
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
#  CONFIDENCE SCORING (amélioré)
# ─────────────────────────────────────────────────────────────

def _compute_confidence(entry: dict) -> float:
    """Calcule un score de confiance plus fin pour un diplôme.

    Facteurs :
    - Présence d'une année (+0.2)
    - Mot-clé diploma reconnu (+0.2)
    - Établissement détecté (+0.15)
    - Niveau diploma identifié (+0.15)
    - Pas de mots-clés techniques dans degree (+0.1)
    - Evidence courte et propre (+0.1)
    Base : 0.1
    """
    score = 0.1
    degree_text = entry.get("degree", "")
    years = entry.get("years", [])
    school = entry.get("school")

    if years:
        score += 0.2
    if _DEGREE_KEYWORDS.search(degree_text):
        score += 0.2
    if school and _SCHOOL_KEYWORDS.search(school):
        score += 0.15
    elif school:
        score += 0.05

    level_num, _ = _determine_degree_level(degree_text)
    if level_num > 0:
        score += 0.15

    tech_count = len(_TECH_KEYWORDS.findall(degree_text))
    if tech_count == 0:
        score += 0.1

    evidence = entry.get("evidence", "")
    if len(evidence) < 200:
        score += 0.1

    return round(min(score, 1.0), 2)


# ─────────────────────────────────────────────────────────────
#  MAIN EXTRACTION (regex-first)
# ─────────────────────────────────────────────────────────────

def extract_educations(text: str) -> list[Education]:
    """Extrait toutes les formations depuis le texte du CV (regex-first).

    Pipeline :
    1. Détection multicolonnes + correction si besoin
    2. Localisation section éducation
    3. Block-based parsing
    4. Normalisation des noms de diplômes
    5. Scoring de confiance amélioré
    """
    # ── Étape 0 : détection / correction multicolonnes ──
    working_text = text
    if detect_column_layout(text):
        working_text = _fix_multicolumn_text(text)
        logger.info("Texte corrigé pour multicolonnes (%d chars)", len(working_text))

    # ── Étape 1 : section dédiée ──
    section = _find_education_section(working_text)
    logger.info("Education section found: %d chars", len(section))

    raw_entries: list[dict] = []
    if section:
        raw_entries = _extract_entries_from_section(section)
        logger.info("Block-based entries from section: %d", len(raw_entries))

    # ── Fallback 1 : chercher dans tout le texte ──
    if not raw_entries:
        logger.info("Fallback 1: searching full text for degree keywords")
        raw_entries = _extract_entries_from_section(working_text)
        logger.info("Block-based entries from full text: %d", len(raw_entries))

    # ── Fallback 2 : scan ligne par ligne ──
    if not raw_entries:
        logger.info("Fallback 2: line-by-line degree keyword scan")
        for line in working_text.split("\n"):
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

    # ── Conversion en modèles Education ──
    educations: list[Education] = []
    for entry in raw_entries:
        years = entry.get("years", [])
        year = max(years) if years else None  # Année fin = année diplôme

        degree_text = entry["degree"]

        # Normaliser le nom du diplôme
        degree_text = normalize_degree_name(degree_text)

        # Déterminer le niveau
        level_num, level_label = _determine_degree_level(degree_text)

        # Vérifier si "en cours"
        status = "obtained"
        if re.search(r"(?i)(en cours|in progress|ongoing|current)", degree_text):
            status = "en_cours"

        # Confiance améliorée
        confidence = _compute_confidence(entry)

        educations.append(Education(
            year=year,
            degree=degree_text.strip(),
            school=entry.get("school"),
            degree_level=level_label if level_num > 0 else None,
            status=status,
            evidence=entry.get("evidence", ""),
            confidence=confidence,
        ))

    logger.info("Regex extraction terminée: %d formation(s)", len(educations))
    return educations


# ─────────────────────────────────────────────────────────────
#  DERNIER DIPLÔME
# ─────────────────────────────────────────────────────────────

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
