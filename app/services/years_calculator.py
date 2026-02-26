"""Calcul des années d'expérience avec union d'intervalles."""

from __future__ import annotations

import re
import logging
from datetime import date, datetime
from app.models import Experience, YearsOfExperience

logger = logging.getLogger(__name__)

# Mois FR/EN → numéro
_MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1, "janvier": 1,
    "feb": 2, "february": 2, "fév": 2, "février": 2, "fevrier": 2,
    "mar": 3, "march": 3, "mars": 3,
    "apr": 4, "april": 4, "avr": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6,
    "jul": 7, "july": 7, "juil": 7, "juillet": 7,
    "aug": 8, "august": 8, "août": 8, "aout": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9,
    "oct": 10, "october": 10, "octobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "déc": 12, "décembre": 12, "decembre": 12,
}

_PRESENT_KEYWORDS = re.compile(
    r"(?i)(présent|present|aujourd'?hui|actuel|now|current|ce\s*jour)"
)


def _parse_date(date_str: str | None, is_end: bool = False) -> date | None:
    """Parse une date texte en objet date.

    Règles :
    - "Présent" → date du jour
    - Année seule → Jan (start) ou Déc (end)
    - Mois + année → 1er du mois
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Présent / Now
    if _PRESENT_KEYWORDS.search(date_str):
        return date.today()

    # Chercher mois + année
    month_match = None
    for key, month_num in _MONTH_MAP.items():
        if re.search(r"(?i)\b" + re.escape(key) + r"\b", date_str):
            month_match = month_num
            break

    # Chercher année
    year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
    if not year_match:
        return None

    year = int(year_match.group())

    if month_match:
        return date(year, month_match, 1)
    else:
        # Année seule : conservateur
        return date(year, 12 if is_end else 1, 1)


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Fusionne les intervalles qui se chevauchent (union d'intervalles)."""
    if not intervals:
        return []

    # Trier par date de début
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]

    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # Chevauchement → fusionner
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def calculate_years_of_experience(experiences: list[Experience]) -> YearsOfExperience:
    """Calcule les années d'expérience en évitant le double comptage.

    Utilise l'union d'intervalles pour gérer les chevauchements.
    """
    intervals: list[tuple[date, date]] = []
    intervals_no_internship: list[tuple[date, date]] = []
    missing_dates: list[str] = []

    for exp in experiences:
        start = _parse_date(exp.start_date, is_end=False)
        end = _parse_date(exp.end_date, is_end=True)

        if not start:
            missing_dates.append(
                f"Date début manquante: {exp.position or 'inconnu'} @ {exp.company or 'inconnu'}"
            )
            continue

        if not end:
            # Si pas de date fin, utiliser la date actuelle
            end = date.today()
            missing_dates.append(
                f"Date fin absente (→ présent): {exp.position or 'inconnu'} @ {exp.company or 'inconnu'}"
            )

        if end < start:
            missing_dates.append(
                f"Date fin < début (ignorée): {exp.position or 'inconnu'}"
            )
            continue

        intervals.append((start, end))

        # Exclure stages
        is_internship = False
        text_check = f"{exp.position or ''} {exp.mission_summary or ''}".lower()
        if re.search(r"(?i)\b(stage|stagiaire|intern|internship)\b", text_check):
            is_internship = True

        if not is_internship:
            intervals_no_internship.append((start, end))

    # Fusionner les intervalles
    merged = _merge_intervals(intervals)
    merged_no_intern = _merge_intervals(intervals_no_internship)

    # Calculer durée totale en mois
    total_months = 0
    serializable_intervals = []
    for start, end in merged:
        months = (end.year - start.year) * 12 + (end.month - start.month)
        total_months += max(months, 0)
        serializable_intervals.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "months": months,
        })

    total_months_no_intern = 0
    for start, end in merged_no_intern:
        months = (end.year - start.year) * 12 + (end.month - start.month)
        total_months_no_intern += max(months, 0)

    total_years = round(total_months / 12, 1) if total_months else 0
    total_years_no_intern = round(total_months_no_intern / 12, 1) if total_months_no_intern else 0

    # Confiance
    confidence = 1.0
    if missing_dates:
        confidence -= min(0.5, len(missing_dates) * 0.1)

    return YearsOfExperience(
        total_months=total_months,
        total_years=total_years,
        total_years_excluding_internships=total_years_no_intern,
        intervals=serializable_intervals,
        missing_dates=missing_dates,
        confidence=round(max(0, confidence), 2),
    )
