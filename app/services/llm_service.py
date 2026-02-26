"""Service LLM (Groq — gratuit) pour enrichir l'extraction quand disponible.

Ce service est OPTIONNEL. L'extraction de base fonctionne sans API key.
Le LLM sert uniquement à améliorer/valider les extractions basées sur patterns.
Groq offre un accès gratuit avec des modèles rapides (Llama 3, Mixtral…).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy init du client Groq."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            return None
        try:
            from groq import Groq
            _client = Groq(api_key=GROQ_API_KEY)
        except ImportError:
            logger.warning("groq non installé — extraction LLM désactivée")
            return None
    return _client


def is_available() -> bool:
    """Vérifie si le LLM est disponible."""
    return bool(GROQ_API_KEY) and _get_client() is not None


def extract_structured(
    cv_text: str,
    instruction: str,
    json_schema: dict[str, Any] | None = None,
) -> dict | None:
    """Envoie le texte du CV au LLM pour extraction structurée.

    Args:
        cv_text: Texte brut du CV.
        instruction: Instruction spécifique d'extraction.
        json_schema: Schéma JSON attendu en sortie.

    Returns:
        Dictionnaire structuré ou None si indisponible.
    """
    client = _get_client()
    if not client:
        return None

    system_prompt = (
        "Tu es un extracteur de CV professionnel. Tu extrais UNIQUEMENT les informations "
        "présentes dans le texte fourni. INTERDICTION d'inventer ou d'estimer des données absentes. "
        "Si une information n'est pas trouvée, retourne null pour ce champ. "
        "Chaque extraction doit être accompagnée d'une citation du texte source."
    )

    user_prompt = f"{instruction}\n\n--- TEXTE CV ---\n{cv_text[:6000]}\n--- FIN CV ---"

    if json_schema:
        user_prompt += f"\n\nRetourne un JSON valide selon ce schéma:\n{json.dumps(json_schema, indent=2)}"

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if content:
            return json.loads(content)
        return None

    except Exception as e:
        logger.error("Erreur LLM: %s", e)
        return None


def enhance_experiences(cv_text: str) -> dict | None:
    """Utilise le LLM pour extraire les expériences de manière structurée."""
    instruction = """Extrais toutes les expériences professionnelles du CV.
Pour chaque expérience, retourne:
- start_date: date de début (texte original)
- end_date: date de fin (texte original)
- position: poste occupé
- company: entreprise
- mission_summary: résumé de la mission (bullet points originaux)
- achievements: réalisations avec métriques (uniquement si présentes)
- technologies: liste des technologies mentionnées
- methodologies: méthodologies mentionnées (Agile, Scrum, etc.)
- team_size: taille équipe UNIQUEMENT si mentionnée explicitement (sinon null)

IMPORTANT: Chaque champ doit avoir une citation du texte source. Si absent → null."""

    schema = {
        "experiences": [
            {
                "start_date": "string|null",
                "end_date": "string|null",
                "position": "string|null",
                "company": "string|null",
                "mission_summary": "string|null",
                "achievements": ["string"],
                "technologies": ["string"],
                "methodologies": ["string"],
                "team_size": "int|null",
                "evidence": "string",
            }
        ]
    }
    return extract_structured(cv_text, instruction, schema)


def enhance_education(cv_text: str) -> dict | None:
    """Utilise le LLM pour extraire les formations."""
    instruction = """Extrais toutes les formations académiques du CV.
Pour chaque formation, retourne:
- year: année d'obtention (la date de fin si période)
- degree: nom exact du diplôme (ne pas modifier)
- school: établissement
- degree_level: niveau (Bac+2, Bac+3, Bac+5, Doctorat)
- status: "obtained" ou "en_cours"

EXCLURE: certifications, formations en ligne, workshops.
UNIQUEMENT les diplômes académiques."""

    schema = {
        "educations": [
            {
                "year": "int|null",
                "degree": "string",
                "school": "string|null",
                "degree_level": "string|null",
                "status": "string",
                "evidence": "string",
            }
        ]
    }
    return extract_structured(cv_text, instruction, schema)
