"""Extraction et scoring des hard & soft skills depuis le CV."""

from __future__ import annotations

import re
import logging
from collections import defaultdict

from app.models import Skill, Tool
from app.config import (
    HARD_SKILLS_TAXONOMY,
    SOFT_SKILLS_TAXONOMY,
    TOOLS_TAXONOMY,
    SKILL_ALIASES,
)

logger = logging.getLogger(__name__)

# ── Sections du CV ──────────────────────────────────────────
_SECTION_LABELS = {
    "skills": re.compile(
        r"(?i)^[\s#*\-]*(compétences|competences|skills|"
        r"technical\s*skills|compétences\s*techniques)\s*$",
        re.MULTILINE,
    ),
    "experience": re.compile(
        r"(?i)^[\s#*\-]*(expérience|experience|parcours|work)\b",
        re.MULTILINE,
    ),
    "projects": re.compile(
        r"(?i)^[\s#*\-]*(projet|project)\b",
        re.MULTILINE,
    ),
    "certifications": re.compile(
        r"(?i)^[\s#*\-]*(certif|certification|formation continue)\b",
        re.MULTILINE,
    ),
}

# Poids par section
_SECTION_WEIGHTS: dict[str, int] = {
    "skills": 3,
    "experience": 4,
    "projects": 3,
    "certifications": 5,
    "other": 1,
}

# Verbes d'impact (bonus preuve)
_IMPACT_VERBS = re.compile(
    r"(?i)\b(improved|reduced|achieved|delivered|increased|"
    r"optimized|deployed|led|designed|built|created|migrated|"
    r"amélioré|réduit|livré|augmenté|développé|conçu|dirigé|"
    r"automated|launched|mentored|coached)\b"
)


def _normalize_skill(name: str) -> str:
    """Normalise le nom d'un skill via aliases."""
    lower = name.lower().strip()
    return SKILL_ALIASES.get(lower, name.strip())


def _detect_section(text: str, pos: int) -> str:
    """Détermine dans quelle section du CV se trouve une position."""
    best_section = "other"
    best_pos = -1
    for section_name, pattern in _SECTION_LABELS.items():
        for m in pattern.finditer(text):
            if m.start() <= pos and m.start() > best_pos:
                best_pos = m.start()
                best_section = section_name
    return best_section


def _compute_level(score: float, has_impact: bool, mention_count: int) -> int:
    """Calcule le niveau /5 basé sur les preuves observées.

    1/5 : cité une fois, sans usage concret
    2/5 : cité + utilisé dans 1 projet/expérience
    3/5 : utilisé dans plusieurs contextes (2+)
    4/5 : responsabilité claire ou résultats/metrics
    5/5 : expertise démontrée (lead, certif, projets lourds)
    """
    if score >= 15 or (has_impact and mention_count >= 3):
        return 5
    elif score >= 10 or has_impact:
        return 4
    elif score >= 6 or mention_count >= 2:
        return 3
    elif score >= 3:
        return 2
    else:
        return 1


def extract_skills(text: str) -> tuple[list[Skill], list[Skill]]:
    """Extrait Top 5 hard skills + Top 5 soft skills avec niveau /5.

    Returns:
        (hard_skills, soft_skills) triés par score décroissant.
    """
    text_lower = text.lower()

    # ── Détecter tous les skills présents ────────────────
    skill_data: dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "category": "",
        "score": 0.0,
        "mentions": 0,
        "has_impact": False,
        "evidence": [],
    })

    def _register_skill(name: str, category: str, position: int, context_line: str):
        normalized = _normalize_skill(name)
        key = normalized.lower()
        data = skill_data[key]
        data["name"] = normalized
        data["category"] = category

        # Score par section
        section = _detect_section(text, position)
        weight = _SECTION_WEIGHTS.get(section, 1)
        data["score"] += weight

        # Compteur mentions (max +3)
        if data["mentions"] < 3:
            data["score"] += 1
        data["mentions"] += 1

        # Bonus impact
        if _IMPACT_VERBS.search(context_line):
            data["has_impact"] = True
            data["score"] += 2

        # Evidence (max 3)
        if len(data["evidence"]) < 3:
            snippet = context_line.strip()[:200]
            if snippet and snippet not in data["evidence"]:
                data["evidence"].append(snippet)

    # ── Recherche hard skills ────────────────────────────
    for skill in HARD_SKILLS_TAXONOMY:
        # Mot entier (word boundary)
        pattern = re.compile(r"(?i)\b" + re.escape(skill) + r"\b")
        for m in pattern.finditer(text):
            # Extraire la ligne de contexte
            line_start = text.rfind("\n", 0, m.start())
            line_end = text.find("\n", m.end())
            context = text[line_start + 1:line_end if line_end > 0 else len(text)]
            _register_skill(skill, "hard", m.start(), context)

    # ── Recherche soft skills ────────────────────────────
    for skill in SOFT_SKILLS_TAXONOMY:
        pattern = re.compile(r"(?i)\b" + re.escape(skill) + r"\b")
        for m in pattern.finditer(text):
            line_start = text.rfind("\n", 0, m.start())
            line_end = text.find("\n", m.end())
            context = text[line_start + 1:line_end if line_end > 0 else len(text)]
            _register_skill(skill, "soft", m.start(), context)

    # ── Construire résultats ─────────────────────────────
    hard_skills: list[Skill] = []
    soft_skills: list[Skill] = []

    for key, data in skill_data.items():
        level = _compute_level(data["score"], data["has_impact"], data["mentions"])
        confidence = min(1.0, 0.3 + data["mentions"] * 0.15 + (0.2 if data["has_impact"] else 0))

        skill_obj = Skill(
            name=data["name"],
            level=level,
            category=data["category"],
            score=round(data["score"], 1),
            evidence=data["evidence"],
            confidence=round(confidence, 2),
        )

        if data["category"] == "hard":
            hard_skills.append(skill_obj)
        else:
            soft_skills.append(skill_obj)

    # Trier par score et garder Top 5
    hard_skills.sort(key=lambda s: s.score, reverse=True)
    soft_skills.sort(key=lambda s: s.score, reverse=True)

    return hard_skills[:5], soft_skills[:5]


def extract_top_tools(text: str) -> list[Tool]:
    """Extrait le Top 5 des outils maîtrisés avec niveau /5.

    Un "outil" est un logiciel / plateforme concret (Docker, Jira, Figma…)
    distinct des langages et concepts (qui sont des hard skills).
    """
    tool_data: dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "score": 0.0,
        "mentions": 0,
        "has_impact": False,
        "evidence": [],
    })

    # Hard-skill items that ended up in TOOLS_TAXONOMY should NOT appear as
    # separate tools — they are already scored under hard_skills.
    _hard_lower = {s.lower() for s in HARD_SKILLS_TAXONOMY}

    for tool in TOOLS_TAXONOMY:
        if tool.lower() in _hard_lower:
            continue          # skip: already a hard skill
        pattern = re.compile(r"(?i)\b" + re.escape(tool) + r"\b")
        for m in pattern.finditer(text):
            line_start = text.rfind("\n", 0, m.start())
            line_end = text.find("\n", m.end())
            context = text[line_start + 1:line_end if line_end > 0 else len(text)]

            normalized = _normalize_skill(tool)
            key = normalized.lower()
            data = tool_data[key]
            data["name"] = normalized

            section = _detect_section(text, m.start())
            weight = _SECTION_WEIGHTS.get(section, 1)
            data["score"] += weight

            if data["mentions"] < 3:
                data["score"] += 1
            data["mentions"] += 1

            if _IMPACT_VERBS.search(context):
                data["has_impact"] = True
                data["score"] += 2

            if len(data["evidence"]) < 3:
                snippet = context.strip()[:200]
                if snippet and snippet not in data["evidence"]:
                    data["evidence"].append(snippet)

    tools: list[Tool] = []
    for key, data in tool_data.items():
        # Minimum quality gate: at least 2 mentions OR a meaningful section score
        # (score >= 4 means ≥1 mention inside an experience/project/cert section).
        # This eliminates single incidental mentions like "GitLab and SonarQube".
        if data["mentions"] < 2 and data["score"] < 4:
            logger.debug("Tool '%s' filtered out (score=%.1f, mentions=%d)",
                         data["name"], data["score"], data["mentions"])
            continue

        level = _compute_level(data["score"], data["has_impact"], data["mentions"])
        confidence = min(1.0, 0.3 + data["mentions"] * 0.15 + (0.2 if data["has_impact"] else 0))

        tools.append(Tool(
            name=data["name"],
            level=level,
            score=round(data["score"], 1),
            evidence=data["evidence"],
            confidence=round(confidence, 2),
        ))

    tools.sort(key=lambda t: t.score, reverse=True)
    return tools[:5]
