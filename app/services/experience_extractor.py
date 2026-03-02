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
    r"(?:\d{1,2}\s*[/\-]\s*)?"  # optional DD/
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
    r"(?:\d{1,2}\s*[/\-]\s*)?"  # optional DD/
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

# Job title keywords — helps distinguish position lines from company names
_JOB_TITLE_KEYWORDS = re.compile(
    r"(?i)\b("
    r"intern|internship|stage|stagiaire|alternant|alternance|"
    r"engineer|ingénieur|ingenieur|"
    r"developer|développeur|developpeur|"
    r"analyst|analyste|"
    r"manager|gestionnaire|"
    r"specialist|spécialiste|specialiste|"
    r"consultant|"
    r"designer|concepteur|"
    r"architect|architecte|"
    r"lead|chef|responsable|"
    r"director|directeur|"
    r"coordinator|coordinateur|"
    r"administrator|administrateur|"
    r"technician|technicien|"
    r"assistant|"
    r"officer|"
    r"data\s+scientist|data\s+engineer|data\s+analyst|"
    r"full[\s\-]?stack|front[\s\-]?end|back[\s\-]?end|"
    r"devops|sre|qa|"
    r"marketing|"
    r"junior|senior|"
    r"cto|ceo|cfo|coo|vp"
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
        r"langue|language|certif|projets?|projects?|"
        r"loisir|hobby|intérêt|interest|référence|reference"
        r")\b",
        text[start:],
        re.MULTILINE,
    )
    end = start + next_section.start() if next_section else len(text)
    return text[start:end].strip()


# Pattern to detect a "Company, Title" or "Title | Company" header line
# that typically precedes the date range line.
_COMPANY_TITLE_LINE = re.compile(
    r"(?i)^\s*[A-ZÀ-Ÿ][\w\s',\-–&.]+(?:,|\|)\s*[A-ZÀ-Ÿ][\w\s'\-]+$"
)


def _split_into_experience_blocks(section: str) -> list[str]:
    """Découpe la section en blocs d'expérience individuels.

    Improved: also captures the line ABOVE the date-range line when it
    contains the company/position (common CV format).
    """
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
        # Remonter au début de la ligne contenant la date
        line_start = section.rfind("\n", 0, start)
        start = line_start + 1 if line_start >= 0 else start

        # Scan backwards for header-like lines (short, no period ending,
        # not a bullet point).  Stop at any non-header content.
        scan_pos = start
        while scan_pos > 0:
            prev_end = scan_pos - 1
            prev_ls = section.rfind("\n", 0, prev_end)
            prev_ls = prev_ls + 1 if prev_ls >= 0 else 0
            prev_line = section[prev_ls:prev_end].strip()
            if (
                not prev_line
                or _DATE_RANGE_PATTERN.search(prev_line)
                or len(prev_line) >= 60
                or prev_line.endswith((".", ",", ";"))
                or re.match(r"^\s*[\-•*▪►▸]", prev_line)
            ):
                break
            start = prev_ls
            scan_pos = prev_ls

        if i + 1 < len(matches):
            next_start = matches[i + 1].start()
            # Remonter au début de la ligne contenant la prochaine date
            next_line_start = section.rfind("\n", 0, next_start)

            if next_line_start >= 0 and next_line_start > start:
                # Scan backwards from next date line for header lines belonging
                # to the NEXT block (to exclude them from this block).
                cut = next_line_start
                scan2 = cut
                while scan2 > start:
                    pend2 = scan2 - 1 if scan2 > 0 else 0
                    pls2 = section.rfind("\n", 0, pend2)
                    pls2 = pls2 + 1 if pls2 >= 0 else 0
                    pline2 = section[pls2:pend2].strip()
                    if (
                        not pline2
                        or _DATE_RANGE_PATTERN.search(pline2)
                        or len(pline2) >= 60
                        or pline2.endswith((".", ",", ";"))
                        or re.match(r"^\s*[\-•*▪►▸]", pline2)
                    ):
                        break
                    if pls2 <= start:
                        break
                    cut = pls2
                    scan2 = pls2
                end = cut
            else:
                end = next_start
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

    # ── Poste & Entreprise ──────────────────────────────
    position = None
    company = None

    # Find the date line and its index
    date_line = ""
    date_line_idx = -1
    for idx, line in enumerate(lines):
        if _DATE_RANGE_PATTERN.search(line):
            date_line = line
            date_line_idx = idx
            break

    # Collect short "header" lines above and below the date that are NOT
    # description text (< 60 chars, no period ending, no bullet).
    def _is_header_like(line: str) -> bool:
        s = line.strip()
        return bool(
            s
            and len(s) < 60
            and not s.endswith((".", ",", ";"))
            and not re.match(r"^\s*[\-•*▪►▸\uf0b7]", s)
            and not _DATE_RANGE_PATTERN.search(s)
        )

    headers_above: list[str] = []
    headers_below: list[str] = []

    if date_line_idx >= 0:
        # Lines ABOVE the date
        for idx in range(date_line_idx - 1, -1, -1):
            if _is_header_like(lines[idx]):
                headers_above.insert(0, lines[idx].strip())
            else:
                break
        # Lines BELOW the date (first 1-2 short lines after date)
        for idx in range(date_line_idx + 1, min(date_line_idx + 4, len(lines))):
            if _is_header_like(lines[idx]):
                headers_below.append(lines[idx].strip())
            else:
                break

    all_headers = headers_above + headers_below

    # Strategy 1: "Company, Title" on a single header line above date
    # e.g. "ONCF, Data Engineer Intern"
    for h in headers_above:
        comma_parts = [p.strip() for p in h.split(",", 1) if p.strip()]
        if len(comma_parts) == 2:
            company = comma_parts[0]
            position = comma_parts[1]
            break

    # Strategy 2: Classify header lines by job-title keywords
    if not position and all_headers:
        for h in all_headers:
            if _JOB_TITLE_KEYWORDS.search(h):
                if not position:
                    position = h
            else:
                if not company:
                    company = h
        # If we found position but no company, the remaining headers are company
        if position and not company:
            for h in all_headers:
                if h != position:
                    company = h
                    break
        # If we found company but no position, remaining headers are position
        if company and not position:
            for h in all_headers:
                if h != company:
                    position = h
                    break

    # Strategy 3: "Company, Title DATE" on same line (inline format)
    # e.g. "Bank Al-Maghrib, Data Analyst Intern 07/2024 – 08/2024 | Rabat"
    if not position and date_line:
        dm = _DATE_RANGE_PATTERN.search(date_line)
        if dm:
            before_date = date_line[: dm.start()].strip()
            if before_date:
                comma_parts = [p.strip() for p in before_date.split(",", 1) if p.strip()]
                if len(comma_parts) == 2:
                    company = comma_parts[0]
                    position = comma_parts[1]
                elif before_date:
                    position = before_date

    # Strategy 4: Date line may have extra info after pipes
    # e.g. "07/2024 – 08/2024 | Rabat, Morocco"
    if date_line:
        rest = _DATE_RANGE_PATTERN.sub("", date_line).strip().strip("|– \t")
        pipe_parts = [p.strip() for p in rest.split("|") if p.strip()]
        non_location_parts = [
            p for p in pipe_parts
            if not re.fullmatch(r"[A-ZÀ-Ÿa-zà-ÿ\s]+,\s*[A-ZÀ-Ÿa-zà-ÿ\s]+", p)
        ]
        if not position and non_location_parts:
            for p in non_location_parts:
                if _JOB_TITLE_KEYWORDS.search(p) and not position:
                    position = p
                elif not company:
                    company = p

    # Fallback: first non-date, non-bullet line
    if not position:
        for line in lines[:6]:
            s = line.strip()
            if s and not _DATE_RANGE_PATTERN.search(s) and not re.match(r"^[\d/\-\s]+$", s):
                position = s
                break

    # Fallback: "at/chez/@" patterns
    if not company:
        for line in lines[:6]:
            at_match = re.search(r"(?i)\b(?:at|chez|@)\s+(.+)", line.strip())
            if at_match:
                company = at_match.group(1).strip()
                break

    # ── Mission / Description ────────────────────────────
    # Collect content lines: everything after the date line that is not
    # a header (position/company) or date line itself.
    skip_lines = set(all_headers)
    bullet_lines = []
    achievements = []
    content_started = False
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Skip recognized header lines (position, company)
        if line_stripped in skip_lines:
            continue
        if _DATE_RANGE_PATTERN.search(line_stripped):
            content_started = True
            continue
        if not content_started:
            continue

        # Check if it's a bullet point
        if re.match(r"^\s*[\-•*▪►▸]\s+", line):
            content = re.sub(r"^\s*[\-•*▪►▸]\s+", "", line).strip()
        else:
            content = line_stripped

        if not content:
            continue

        if _ACHIEVEMENT_VERBS.search(content):
            achievements.append(content)
        else:
            bullet_lines.append(content)

    mission_summary = " ".join(bullet_lines[:5]) if bullet_lines else None

    # ── Technologies ─────────────────────────────────────
    techs = list({re.sub(r"\s+", " ", m.group()) for m in _TECH_PATTERN.finditer(block)})

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
