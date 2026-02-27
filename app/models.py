"""Modèles Pydantic pour le Dossier de Compétences."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

# forward ref
__all__ = [
    "Education", "LastDegree", "Experience",
    "Language", "Skill", "Tool", "PhotoResult", "DossierCompetences",
]


# ── Études ──────────────────────────────────────────────────
class Education(BaseModel):
    year: Optional[int] = Field(None, description="Année d'obtention du diplôme")
    degree: str = Field(..., description="Nom du diplôme")
    school: Optional[str] = Field(None, description="Établissement")
    degree_level: Optional[str] = Field(None, description="Niveau (ex: Bac+5)")
    status: str = Field("obtained", description="obtained | en_cours")
    evidence: Optional[str] = Field(None, description="Texte source du CV")
    confidence: float = Field(1.0, ge=0, le=1)


# ── Dernier diplôme ─────────────────────────────────────────
class LastDegree(BaseModel):
    degree: str
    level: Optional[str] = None
    school: Optional[str] = None
    year: Optional[int] = None
    confidence: float = Field(1.0, ge=0, le=1)


# ── Expérience ──────────────────────────────────────────────
class Experience(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    position: Optional[str] = None
    company: Optional[str] = None
    mission_summary: Optional[str] = None
    achievements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list)
    team_size: Optional[int] = Field(None, description="Uniquement si mentionné dans le CV")
    evidence: Optional[str] = None
    confidence: float = Field(1.0, ge=0, le=1)



# ── Langues ─────────────────────────────────────────────────
class Language(BaseModel):
    name: str
    level: float = Field(..., ge=0, le=5, description="Niveau /5")
    level_label: Optional[str] = None
    evidence: Optional[str] = None
    confidence: float = Field(1.0, ge=0, le=1)


# ── Compétences ─────────────────────────────────────────────
class Skill(BaseModel):
    name: str
    level: int = Field(..., ge=1, le=5, description="Niveau /5")
    category: str = Field(..., description="hard | soft")
    score: float = Field(0, description="Score interne de classement")
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(1.0, ge=0, le=1)


# ── Outil maîtrisé ─────────────────────────────────────────
class Tool(BaseModel):
    name: str
    level: int = Field(..., ge=1, le=5, description="Niveau de maîtrise /5")
    score: float = Field(0, description="Score interne de classement")
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(1.0, ge=0, le=1)


# ── Photo ───────────────────────────────────────────────────
class PhotoResult(BaseModel):
    found: bool = False
    file_path: Optional[str] = None
    confidence: float = Field(0, ge=0, le=1)
    method: Optional[str] = Field(None, description="direct_extraction | face_detection")


# ── Dossier de Compétences complet ──────────────────────────
class DossierCompetences(BaseModel):
    # Infos générales
    source_file: str
    extraction_date: str
    candidate_name: Optional[str] = Field(None, description="Nom du candidat")
    candidate_name_confidence: float = Field(0.0, ge=0, le=1)
    # Photo
    photo: PhotoResult = Field(default_factory=PhotoResult)

    # Formation
    educations: list[Education] = Field(default_factory=list)
    last_degree: Optional[LastDegree] = None

    # Expériences
    experiences: list[Experience] = Field(default_factory=list)

    # Langues (top 3)
    languages: list[Language] = Field(default_factory=list)

    # Compétences
    hard_skills: list[Skill] = Field(default_factory=list, description="Top 5 hard skills")
    soft_skills: list[Skill] = Field(default_factory=list, description="Top 5 soft skills")
    top_tools: list[Tool] = Field(default_factory=list, description="Top 5 outils maîtrisés")

    # Métadonnées
    missing_information: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(1.0, ge=0, le=1)
