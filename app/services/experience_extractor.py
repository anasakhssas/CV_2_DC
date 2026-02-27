"""Extraction des expériences professionnelles depuis le texte du CV."""

from __future__ import annotations

import re
import logging
from app.models import Experience

logger = logging.getLogger(__name__)

# ── Patterns ────────────────────────────────────────────────
_SECTION_PATTERNS = re.compile(
    r"(?i)^[\s#*\-]*("
    r"expériences?|experiences?|parcours\s*professionnel|"
    r"professional\s*experience|work\s*experience|emploi"
    r")\s*(professionnelles?|professional)?\s*[:\-]?\s*$",
    re.MULTILINE,
)

# Dates : "Jan 2022", "01/2022", "2022", "Janvier 2022"
_DATE_PATTERN = re.compile(
    r"(?i)("
    r"(?:jan(?:vier|uary)?|fév(?:rier)?|feb(?:ruary)?|mar(?:s|ch)?|"
    r"avr(?:il)?|apr(?:il)?|mai|may|juin|jun(?:e)?|"
    r"juil(?:let)?|jul(?:y)?|août|aug(?:ust)?|sep(?:tembre|t(?:ember)?)?|"
    r"oct(?:obre|ober)?|nov(?:embre|ember)?|déc(?:embre)?|dec(?:ember)?)"
    r"\s*\.?\s*"
    r"(19|20)\d{2}"
    r"|"
    r"(?:0?[1-9]|1[0-2])\s*[/\-]\s*(19|20)\d{2}"
    r"|"
    r"(19|20)\d{2}"
    r")"
)

_DATE_RANGE_PATTERN = re.compile(
    r"(?i)("
    r"(?:(?:jan(?:vier|uary)?|fév(?:rier)?|feb(?:ruary)?|mar(?:s|ch)?|"
    r"avr(?:il)?|apr(?:il)?|mai|may|juin|jun(?:e)?|"
    r"juil(?:let)?|jul(?:y)?|août|aug(?:ust)?|sep(?:tembre|t(?:ember)?)?|"
    r"oct(?:obre|ober)?|nov(?:embre|ember)?|déc(?:embre)?|dec(?:ember)?)"
    r"\s*\.?\s*)?"
    r"(?:(?:0?[1-9]|1[0-2])\s*[/\-]\s*)?"
    r"(19|20)\d{2}"
    r")"
    r"\s*[\-–—à/]\s*"
    r"("
    r"(?:(?:jan(?:vier|uary)?|fév(?:rier)?|feb(?:ruary)?|mar(?:s|ch)?|"
    r"avr(?:il)?|apr(?:il)?|mai|may|juin|jun(?:e)?|"
    r"juil(?:let)?|jul(?:y)?|août|aug(?:ust)?|sep(?:tembre|t(?:ember)?)?|"
    r"oct(?:obre|ober)?|nov(?:embre|ember)?|déc(?:embre)?|dec(?:ember)?)"
    r"\s*\.?\s*)?"
    r"(?:(?:0?[1-9]|1[0-2])\s*[/\-]\s*)?"
    r"(?:(19|20)\d{2}|présent|present|aujourd'?hui|actuel(?:lement)?|now|current|ce\s*jour)"
    r")"
)

_PRESENT_KEYWORDS = re.compile(
    r"(?i)(présent|present|aujourd'?hui|actuel(?:lement)?|now|current|ce\s*jour)"
)

_METHODOLOGY_KEYWORDS = re.compile(
    r"(?i)\b(agile|scrum|kanban|waterfall|ci/cd|devops|lean|safe|xp|tdd|bdd|v-model)\b"
)

_TEAM_SIZE_PATTERN = re.compile(
    r"(?i)(?:team|équipe|equipe)\s*(?:of|de)?\s*(\d+)"
    r"|(\d+)\s*(?:engineers|developers|développeurs|personnes|members|collaborateurs)"
)

_ACHIEVEMENT_VERBS = re.compile(
    r"(?i)^\s*[\-•*]?\s*(improved|reduced|achieved|delivered|increased|"
    r"optimized|developed|implemented|designed|led|managed|built|created|"
    r"amélioré|réduit|livré|augmenté|développé|conçu|dirigé|"
    r"deployed|migrated|automated|launched)"
)

# Technologies fréquentes dans les expériences
_TECH_PATTERN = re.compile(
    r"(?i)\b("
    r"python|java|javascript|typescript|react|angular|vue\.?js|node\.?js|"
    r"express|fastapi|django|flask|spring|laravel|"
    r"docker|kubernetes|aws|azure|gcp|"
    r"postgresql|mysql|mongodb|redis|elasticsearch|"
    r"git|jenkins|gitlab|github|terraform|ansible|"
    r"linux|nginx|apache|kafka|rabbitmq|"
    r"tensorflow|pytorch|pandas|numpy|spark|"
    r"html|css|sass|tailwind|bootstrap|"
    r"graphql|rest|grpc|microservices|"
    r"junit|pytest|selenium|cypress|jest|"
    r"figma|jira|confluence|"
    r"power\s*bi|tableau|excel|"
    r"c\+\+|c#|\.net|php|ruby|go|rust|kotlin|swift|scala"
    r")\b"
)


def _find_experience_section(text: str) -> str:
    """Localise la section expériences."""
    matches = list(_SECTION_PATTERNS.finditer(text))
    if not matches:
        return ""

    start = matches[0].end()
    next_section = re.search(
        r"(?i)^[\s#*\-]*("
        r"formation|education|études|etudes|compétence|competence|skills|"
        r"langue|language|certif|projet|project|"
        r"loisir|hobby|intérêt|interest|référence|reference"
        r")\b",
        text[start:],
        re.MULTILINE,
    )
    end = start + next_section.start() if next_section else len(text)
    return text[start:end].strip()


def _split_into_experience_blocks(section: str) -> list[str]:
    """Découpe la section en blocs d'expérience individuels."""
    # Chercher les plages de dates comme séparateurs
    matches = list(_DATE_RANGE_PATTERN.finditer(section))
    if not matches:
        # Essayer avec des dates simples
        matches = list(_DATE_PATTERN.finditer(section))

    if not matches:
        return [section] if section.strip() else []

    blocks: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        # Remonter au début de la ligne
        line_start = section.rfind("\n", 0, start)
        start = line_start + 1 if line_start >= 0 else start

        if i + 1 < len(matches):
            next_start = matches[i + 1].start()
            next_line_start = section.rfind("\n", 0, next_start)
            end = next_line_start if next_line_start > start else next_start
        else:
            end = len(section)

        block = section[start:end].strip()
        if block:
            blocks.append(block)

    return blocks


def _parse_experience_block(block: str) -> Experience:
    """Parse un bloc texte en Experience structurée."""
    lines = block.split("\n")

    # ── Dates ────────────────────────────────────────────
    start_date = None
    end_date = None
    date_range = _DATE_RANGE_PATTERN.search(block)
    if date_range:
        # group(1) = full start date, group(3) = full end date
        start_date = date_range.group(1).strip() if date_range.group(1) else None
        end_date = date_range.group(3).strip() if date_range.group(3) else None
        if end_date and _PRESENT_KEYWORDS.search(end_date):
            end_date = "présent"
    elif _DATE_PATTERN.search(block):
        dates_found = _DATE_PATTERN.findall(block)
        if dates_found:
            start_date = dates_found[0][0] if dates_found[0][0] else str(dates_found[0])

    # ── Poste & Entreprise (format pipe: date | poste | entreprise) ──────
    position = None
    company = None

    # Chercher la ligne qui contient la plage de dates
    date_line = ""
    for line in lines[:5]:
        if _DATE_RANGE_PATTERN.search(line):
            date_line = line
            break

    if date_line:
        # Retirer la date range de la ligne, garder le reste
        rest = _DATE_RANGE_PATTERN.sub("", date_line).strip().strip("|– \t")
        pipe_parts = [p.strip() for p in rest.split("|") if p.strip()]
        if len(pipe_parts) >= 2:
            position = pipe_parts[0]
            company = pipe_parts[1]
        elif len(pipe_parts) == 1:
            position = pipe_parts[0]

    # Fallback poste : premières lignes non-date
    if not position:
        for line in lines[:4]:
            line_clean = line.strip().strip("-–•*")
            if line_clean and not re.match(r"^[\d/\-\s]+$", line_clean):
                if not _DATE_RANGE_PATTERN.fullmatch(line_clean):
                    position = line_clean
                    break

    # Fallback entreprise : patterns at/chez/@
    if not company:
        for line in lines[:6]:
            line_clean = line.strip()
            at_match = re.search(r"(?i)\b(?:at|chez|@)\s+(.+)", line_clean)
            if at_match:
                company = at_match.group(1).strip()
                break

    # ── Mission / Description ────────────────────────────
    bullet_lines = []
    achievements = []
    for line in lines:
        line_stripped = line.strip()
        if re.match(r"^\s*[\-•*]\s*", line):
            content = re.sub(r"^\s*[\-•*]\s*", "", line).strip()
            if _ACHIEVEMENT_VERBS.search(content):
                achievements.append(content)
            else:
                bullet_lines.append(content)

    mission_summary = " ".join(bullet_lines[:5]) if bullet_lines else None

    # ── Technologies ─────────────────────────────────────
    techs = list({m.group() for m in _TECH_PATTERN.finditer(block)})

    # ── Méthodologies ────────────────────────────────────
    methodologies = list({m.group() for m in _METHODOLOGY_KEYWORDS.finditer(block)})

    # ── Taille équipe (seulement si explicite) ───────────
    team_size = None
    team_match = _TEAM_SIZE_PATTERN.search(block)
    if team_match:
        size_str = team_match.group(1) or team_match.group(2)
        try:
            team_size = int(size_str)
        except (ValueError, TypeError):
            pass

    # ── Confiance ────────────────────────────────────────
    confidence = 0.5
    if start_date:
        confidence += 0.2
    if position:
        confidence += 0.2
    if company:
        confidence += 0.1

    return Experience(
        start_date=start_date,
        end_date=end_date,
        position=position,
        company=company,
        mission_summary=mission_summary,
        achievements=achievements,
        technologies=techs,
        methodologies=methodologies,
        team_size=team_size,
        evidence=block[:500],
        confidence=round(confidence, 2),
    )


def extract_experiences(text: str) -> list[Experience]:
    """Extrait les expériences professionnelles depuis le texte du CV."""
    section = _find_experience_section(text)
    if not section:
        logger.info("Section expérience non trouvée, recherche globale")
        section = text

    blocks = _split_into_experience_blocks(section)
    experiences = [_parse_experience_block(block) for block in blocks if block.strip()]

    return experiences
