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
    temperature: float = 0.1,
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
        user_prompt += f"\n\nRetourne un JSON valide selon ce schéma (remplace les valeurs d'exemple par les vraies données du CV):\n{json.dumps(json_schema, indent=2, ensure_ascii=False)}"

    logger.info("LLM prompt (first 500): %s", user_prompt[:500])

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        logger.info("LLM response (first 500): %s", content[:500] if content else "<empty>")
        if content:
            return json.loads(content)
        return None

    except Exception as e:
        logger.error("Erreur LLM: %s", e)
        return None


def enhance_experiences(cv_text: str) -> dict | None:
    """Utilise le LLM pour extraire les expériences de manière structurée."""
    from datetime import date
    current_year = date.today().year

    instruction = f"""Extrais toutes les expériences professionnelles du CV. Aujourd'hui nous sommes en {current_year}.
Pour chaque expérience, retourne:
- start_date: date de début VERBATIM telle qu'écrite dans le CV
- end_date: date de fin VERBATIM (ou "présent" si en cours)
- position: COPIE VERBATIM l'intitulé du poste tel qu'écrit dans le CV. Ne traduis PAS.
- company: COPIE VERBATIM le nom de l'entreprise tel qu'écrit dans le CV. Ne traduis PAS.
- mission_summary: résumé en 1-2 phrases basé uniquement sur le texte du CV
- achievements: réalisations avec métriques UNIQUEMENT si présentes dans le CV (sinon [])
- technologies: liste des technologies explicitement mentionnées dans le CV
- methodologies: méthodologies mentionnées (Agile, Scrum, etc.)
- team_size: taille équipe UNIQUEMENT si mentionnée explicitement avec un nombre (sinon null)

RÈGLES STRICTES:
- INTERDIT d'inventer, traduire ou compléter les noms de postes ou entreprises.
- Si un champ est absent du CV → null ou []."""

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


def enhance_education(cv_text: str, section_text: str | None = None) -> dict | None:
    """Utilise le LLM pour extraire les formations."""
    from datetime import date
    current_year = date.today().year

    # Use focused section text if available, else full CV (capped)
    text_to_analyze = (section_text or cv_text)[:4000]
    logger.info("enhance_education: section_text=%d chars, using %d chars",
                len(section_text) if section_text else 0, len(text_to_analyze))

    instruction = f"""Tu reçois le texte brut de la section FORMATIONS d'un CV. Année actuelle: {current_year}.
Extrais UNIQUEMENT les diplômes académiques officiels (exclure certifications, MOOCs, workshops).

Pour CHAQUE formation, remplis ces champs:
  year        → année de FIN uniquement (entier). Si période "A - B" prends B. Si "en cours" prends année prévue.
  degree      → copie EXACTEMENT le nom du diplôme tel qu'il apparaît dans le texte. Zéro modification.
  school      → copie EXACTEMENT le nom de l'établissement tel qu'il apparaît dans le texte. Zéro modification.
  degree_level→ déduis strictement: Baccalauréat/Bac→"Bac", DUT/BTS→"Bac+2", Licence/Bachelor/BSc→"Bac+3", Master/MSc/MBA/Ingénieur/Cycle ingénieur→"Bac+5", Doctorat/PhD→"Bac+8", sinon null.
  status      → "en_cours" si year >= {current_year} ou texte indique en cours/actuel/présent, sinon "obtained".
  evidence    → la ligne exacte du texte source.

EXEMPLE:
Texte: "ENSAM Rabat | Cycle Ingénieur | 2022 - 2025"
Résultat:
  year=2025, degree="Cycle Ingénieur", school="ENSAM Rabat", degree_level="Bac+5", status="obtained", evidence="ENSAM Rabat | Cycle Ingénieur | 2022 - 2025"

Texte: "Lycée Ibn Sina | Baccalauréat Sciences Physiques | 2021"
Résultat:
  year=2021, degree="Baccalauréat Sciences Physiques", school="Lycée Ibn Sina", degree_level="Bac", status="obtained", evidence="Lycée Ibn Sina | Baccalauréat Sciences Physiques | 2021"

RÈGLE ABSOLUE: ne jamais traduire, paraphraser ou compléter les champs degree/school. Copie mot pour mot."""

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
    return extract_structured(text_to_analyze, instruction, schema, temperature=0.01)
