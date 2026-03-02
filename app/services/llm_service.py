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

    instruction = f"""Tu reçois le texte brut d'un CV. Année actuelle: {current_year}.
Extrais UNIQUEMENT les diplômes académiques officiels obtenus dans un établissement scolaire ou universitaire.

CRITÈRES STRICTS pour qu'une entrée soit considérée comme un diplôme :
- Doit mentionner un type de diplôme reconnu : Baccalauréat, Licence, Bachelor, DUT, BTS, Master, MBA, MSc, Ingénieur, Cycle Ingénieur, Doctorat, PhD
- Doit mentionner un établissement scolaire ou universitaire (lycée, université, école, faculté, institut...)
- EXCLURE absolument : certifications, MOOCs, workshops, formations courtes, cours en ligne (Coursera, Udemy...), compétences techniques, outils, langages de programmation

UN DIPLÔME = au maximum 10 mots pour le champ "degree". Si degree dépasse 10 mots, c'est sûrement une erreur.

Pour CHAQUE diplôme trouvé :
  year        → année de FIN uniquement (entier ou null si absent).
  degree      → NOM COURT du diplôme uniquement (ex: "Cycle Ingénieur", "Bachelor of Science in Physics", "Baccalauréat Sciences Physiques"). JAMAIS plus de 10 mots.
  school      → nom de l'établissement uniquement (ex: "Faculté Polydisciplinaire Taza", "ENSAM Rabat"). JAMAIS une liste de technologies.
  degree_level→ "Bac" | "Bac+2" | "Bac+3" | "Bac+5" | "Bac+8" | null
  status      → "en_cours" si year >= {current_year} ou texte indique en cours, sinon "obtained"
  evidence    → ligne exacte du texte source (courte, max 100 caractères)

EXEMPLES CORRECTS :
  degree="Cycle Ingénieur", school="ENSAM Rabat", year=2025
  degree="Bachelor of Science in Physics", school="Faculté Polydisciplinaire Taza", year=2023
  degree="Baccalauréat Sciences Physiques", school="Lycée Tahla", year=2019

EXEMPLES INCORRECTS (à ne PAS extraire) :
  ❌ degree contenant "Python, Java, FastAPI..." → c'est une compétence, pas un diplôme
  ❌ school contenant "Spring Boot, React..." → c'est une technologie, pas une école
  ❌ degree avec plus de 10 mots → probablement une erreur de découpage

Si aucun diplôme clairement identifiable → retourner {{"educations": []}}"""

    schema = {
        "educations": [
            {
                "year": "int|null",
                "degree": "string (max 10 mots)",
                "school": "string|null",
                "degree_level": "string|null",
                "status": "string",
                "evidence": "string",
            }
        ]
    }
    return extract_structured(text_to_analyze, instruction, schema, temperature=0.01)


def enhance_soft_skills(cv_text: str) -> dict | None:
    """Utilise le LLM pour extraire les soft skills depuis le CV."""
    instruction = """Analyse ce CV et extrais UNIQUEMENT les soft skills (compétences comportementales / interpersonnelles).

DÉFINITION soft skill : qualité humaine, comportementale ou organisationnelle.
Exemples : communication, leadership, travail en équipe, rigueur, adaptabilité, autonomie,
curiosité, esprit d'initiative, gestion du stress, créativité, sens des responsabilités…

RÈGLES STRICTES :
- N'inclure AUCUN langage de programmation, framework, outil technique, ni domaine technique (Python, Docker, ML, etc.)
- N'inclure AUCUN hard skill métier (machine learning, DevOps, data science, etc.)
- Extraire SEULEMENT ce qui est EXPLICITEMENT présent dans le texte du CV (section soft skills, profil, résumé, etc.)
- Si aucun soft skill n'est trouvé, retourner {"soft_skills": []}
- Retourner AU MAXIMUM 5 soft skills
- Pour chaque soft skill, indiquer le texte source exact (evidence)"""

    schema = {
        "soft_skills": [
            {
                "name": "string — nom normalisé du soft skill en français",
                "evidence": "string — citation exacte du CV",
            }
        ]
    }
    return extract_structured(cv_text, instruction, schema, temperature=0.1)


def extract_name(cv_text: str) -> dict | None:
    """Utilise le LLM pour extraire le nom complet du candidat."""
    # On envoie seulement les 30 premières lignes — le nom est toujours en haut
    first_lines = "\n".join(cv_text.splitlines()[:30])

    instruction = """Tu dois extraire le NOM COMPLET (prénom + nom) du candidat depuis les premières lignes de ce CV.

RÈGLES :
- Le nom est généralement la première ou deuxième ligne non vide du CV
- Un nom = 2 à 4 mots composés de lettres uniquement (pas de chiffres, pas de symboles)
- Ce N'EST PAS un nom : un titre de poste, une phrase de profil, un intitulé de section

EXEMPLES DE NOMS CORRECTS :
  ✅ "Mohammed Rachid Batal"
  ✅ "Sarah El Amrani"
  ✅ "Jean-Pierre Dupont"
  ✅ "FATIMA ZAHRA BENALI"
  ✅ "Youssef Ait Taleb"
  ✅ "Alice Martin"

EXEMPLES DE CE QUI N'EST PAS UN NOM :
  ❌ "Engineering Student" → titre de profil
  ❌ "Data Science & AI Engineering" → description de domaine
  ❌ "Curriculum Vitae" → titre de document
  ❌ "Full Stack Developer" → titre de poste
  ❌ "Contact : +212 6..." → coordonnées

Si tu trouves le nom → retourne {"candidate_name": "Prénom Nom", "confidence": 0.95}
Si tu n'es pas sûr → retourne {"candidate_name": null, "confidence": 0.0}"""

    schema = {
        "candidate_name": "string|null",
        "confidence": "float entre 0 et 1",
    }
    return extract_structured(first_lines, instruction, schema, temperature=0.0)
