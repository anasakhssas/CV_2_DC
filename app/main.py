"""Cv2DC — Application FastAPI pour transformer un CV en Dossier de Compétences."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import UPLOAD_DIR, OUTPUT_DIR
from app.models import DossierCompetences, PhotoResult
from app.utils.helpers import clean_text

from app.services.pdf_extractor import extract_pdf
from app.services.photo_extractor import extract_photo
from app.services.education_extractor import extract_educations, determine_last_degree, find_education_section
from app.services.experience_extractor import extract_experiences
from app.services.skills_extractor import extract_skills, extract_top_tools
from app.services.language_extractor import extract_languages, extract_languages_with_levels
from app.services.name_extractor import extract_candidate_name
from app.services.years_calculator import calculate_years_of_experience
from app.services import llm_service
from app.services.docx_generator import generate_dossier_docx

# ── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cv2dc")

# ── App FastAPI ─────────────────────────────────────────────
app = FastAPI(
    title="Cv2DC — CV vers Dossier de Compétences",
    description=(
        "Transforme un CV PDF en un dossier de compétences structuré : "
        "photo, formations, expériences, années d'expérience, langues, "
        "hard & soft skills."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir les fichiers de sortie (photos…)
OUTPUT_DIR.mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

import re as _re
from app.models import Education as EduModel

# Mots-clés techniques qui ne doivent pas apparaître dans un diplôme ou une école
_TECH_KEYWORDS = _re.compile(
    r"(?i)\b(python|java|javascript|sql|fastapi|spring|react|docker|kubernetes|"
    r"postgresql|mongodb|mysql|git|aws|azure|gcp|tensorflow|pytorch|langchain|"
    r"hugging\s*face|mlflow|ci/cd|rest\s*api|graphql|snowflake|ml|dl|nlp|"
    r"llm|computer\s*vision|machine\s*learning|deep\s*learning|containerization|"
    r"model\s*deployment|spring\s*boot)\b"
)

def _is_valid_education(e: dict) -> bool:
    """Valide qu'une entrée LLM est bien un diplôme et non du contenu parasite."""
    degree = (e.get("degree") or "").strip()
    school = (e.get("school") or "").strip()

    # Degree trop long → probablement du contenu mélangé
    if len(degree.split()) > 12:
        logger.warning("Education rejetée (degree trop long: %d mots): %s", len(degree.split()), degree[:80])
        return False

    # Degree contient des mots-clés techniques
    if _TECH_KEYWORDS.search(degree):
        logger.warning("Education rejetée (mots-clés techniques dans degree): %s", degree[:80])
        return False

    # School contient des mots-clés techniques
    if school and _TECH_KEYWORDS.search(school):
        logger.warning("Education rejetée (mots-clés techniques dans school): %s", school[:80])
        return False

    # Degree vide
    if not degree:
        return False

    # Degree ressemble à une date ou une localisation (pas un vrai diplôme)
    if _re.fullmatch(r"[\d\s/\-–—|.,]+", degree):
        logger.warning("Education rejetée (degree ressemble à une date): %s", degree[:80])
        return False

    # Degree commence par des chiffres/slashes et contient un pipe → date | location
    if _re.match(r"^\d[\d\s/\-–—]*\|", degree):
        logger.warning("Education rejetée (date|location pattern): %s", degree[:80])
        return False

    # Degree contient un pattern ville/pays (ex: "Rabat, Morocco")
    if _re.fullmatch(r"[\d\s/|\-–—]*[A-ZÀ-Ÿa-zà-ÿ]+(?:,\s*[A-ZÀ-Ÿa-zà-ÿ]+)*", degree) and len(degree.split()) <= 3:
        # Vérifier que ce n'est pas un vrai diplôme avec un keyword
        if not _TECH_KEYWORDS.search(degree) and not _re.search(
            r'(?i)\b(master|licence|bachelor|baccalaur[éeè]at|bac\b|'
            r'ing[éeè]nieur|doctorat|phd|dut|bts|dipl[ôo]me|degree|cpge|deust)\b', degree
        ):
            logger.warning("Education rejetée (degree ressemble à une localisation): %s", degree[:80])
            return False

    return True


def _build_educations(text: str) -> list[EduModel]:
    """Regex-first + LLM-validator pipeline.

    Architecture inversée (meilleure fiabilité) :
    1. Regex extrait les candidats (rapide, gratuit, déterministe)
    2. LLM valide + corrige les résultats regex (pas d'hallucination)
    3. Si regex vide → LLM en extraction complète (fallback)
    """
    # ── Étape 1 : Extraction regex ──────────────────────────
    regex_educations = extract_educations(text)
    logger.info("📐 Regex: %d formation(s) trouvées", len(regex_educations))

    # ── Étape 2 : LLM valide les résultats regex ───────────
    if regex_educations and llm_service.is_available():
        # Préparer les résultats regex pour le LLM
        regex_data = [
            {
                "year": edu.year,
                "degree": edu.degree,
                "school": edu.school,
                "degree_level": edu.degree_level,
                "status": edu.status,
                "evidence": edu.evidence,
            }
            for edu in regex_educations
        ]

        validated = llm_service.validate_educations(regex_data, text)
        if validated and validated.get("educations"):
            llm_educations = []
            for e in validated["educations"]:
                if not _is_valid_education(e):
                    continue
                try:
                    llm_educations.append(EduModel(
                        year=e.get("year"),
                        degree=e.get("degree", ""),
                        school=e.get("school"),
                        degree_level=e.get("degree_level"),
                        status=e.get("status", "obtained"),
                        evidence=e.get("evidence", "")[:500],
                        confidence=min(float(e.get("confidence", 0.85)), 1.0),
                    ))
                except Exception as llm_e:
                    logger.warning("Formation validée LLM invalide ignorée: %s | data=%s", llm_e, e)
            if llm_educations:
                logger.info("✅ %d formation(s) validées par LLM", len(llm_educations))
                return llm_educations
        logger.warning("LLM validation a échoué — utilisation des résultats regex bruts")

    # Si regex a trouvé des résultats mais LLM indisponible → retourner regex
    if regex_educations:
        logger.info("📐 Retour des %d formation(s) regex (LLM indisponible)", len(regex_educations))
        return regex_educations

    # ── Étape 3 : Fallback LLM extraction complète ─────────
    if llm_service.is_available():
        logger.info("🔄 Fallback: LLM extraction complète (regex n'a rien trouvé)")
        edu_section = find_education_section(text)
        llm_edu = llm_service.enhance_education(text, section_text=edu_section or None)
        if llm_edu and llm_edu.get("educations"):
            llm_educations = []
            for e in llm_edu["educations"]:
                if not _is_valid_education(e):
                    continue
                try:
                    llm_educations.append(EduModel(
                        year=e.get("year"),
                        degree=e.get("degree", ""),
                        school=e.get("school"),
                        degree_level=e.get("degree_level"),
                        status=e.get("status", "obtained"),
                        evidence=e.get("evidence", "")[:500],
                        confidence=0.85,
                    ))
                except Exception as llm_e:
                    logger.warning("Formation LLM fallback invalide ignorée: %s | data=%s", llm_e, e)
            if llm_educations:
                logger.info("✅ %d formation(s) extraites via LLM fallback", len(llm_educations))
                return llm_educations

    logger.warning("⚠️ Aucune formation trouvée (ni regex ni LLM)")
    return []


# ─────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "app": "Cv2DC",
        "version": "1.0.0",
        "description": "Upload un CV PDF sur /extract pour obtenir le dossier de compétences.",
        "endpoints": {
            "POST /extract": "Extraction complète du CV",
            "POST /extract/photo": "Extraction photo uniquement",
            "POST /extract/education": "Extraction formations uniquement",
            "POST /extract/experiences": "Extraction expériences uniquement",
            "POST /extract/skills": "Extraction compétences uniquement",
            "POST /extract/tools": "Top 5 outils maîtrisés",
            "POST /extract/languages": "Extraction langues uniquement",
            "POST /extract/name": "Extraction nom du candidat uniquement",
            "GET /download/{cv_stem}": "Télécharger le dossier de compétences .docx",
            "GET /health": "Vérification santé",
        },
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_available": llm_service.is_available(),
    }


# ─────────────────────────────────────────────────────────────
#  EXTRACTION COMPLÈTE
# ─────────────────────────────────────────────────────────────

@app.post("/extract", response_model=DossierCompetences)
async def extract_full(file: UploadFile = File(...)):
    """Extraction complète d'un CV PDF → Dossier de Compétences.

    Pipeline:
    1. Extraction texte + images du PDF
    2. Photo candidat
    3. Formations (études)
    4. Dernier diplôme
    5. Expériences professionnelles
    6. Années d'expérience (union d'intervalles)
    7. Langues (Top 3 avec niveau /5)
    8. Hard & Soft skills (Top 5 chaque, niveau /5)
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés.")

    # Sauvegarder le fichier uploadé
    pdf_path = UPLOAD_DIR / file.filename
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info("📄 Traitement du CV: %s", file.filename)

    try:
        # ── 1. Extraction PDF ────────────────────────────
        pdf_content = extract_pdf(pdf_path)
        text = clean_text(pdf_content.text)

        if not text and pdf_content.is_scanned:
            raise HTTPException(
                status_code=422,
                detail="Le PDF semble être un scan sans texte extractible. "
                       "Veuillez fournir un PDF numérique (Word → PDF).",
            )

        if not text:
            raise HTTPException(status_code=422, detail="Aucun texte trouvé dans le PDF.")

        logger.info("✅ Texte extrait: %d caractères, %d images", len(text), len(pdf_content.images))

        # Préparer le dossier de sortie
        cv_output_dir = OUTPUT_DIR / Path(file.filename).stem
        cv_output_dir.mkdir(exist_ok=True)

        missing_info: list[str] = []

        # ── 0. Nom du candidat ──────────────────────────────
        candidate_name, name_confidence = extract_candidate_name(text, pdf_path=str(pdf_path))
        if not candidate_name:
            missing_info.append("Nom du candidat non détecté")

        # ── 2. Photo ─────────────────────────────────────
        try:
            photo_result = extract_photo(pdf_content, pdf_path, cv_output_dir)
            if not photo_result.found:
                missing_info.append("Photo candidat non trouvée")
        except Exception as e:
            logger.warning("Erreur extraction photo: %s", e)
            photo_result = PhotoResult(found=False)
            missing_info.append("Erreur extraction photo")

        # ── 3. Formations ────────────────────────────────
        educations = _build_educations(text)
        if not educations:
            missing_info.append("Aucune formation détectée")

        # ── 4. Dernier diplôme ───────────────────────────
        last_degree = determine_last_degree(educations)
        if not last_degree:
            missing_info.append("Dernier diplôme non déterminé")

        # ── 5. Expériences ───────────────────────────────
        experiences = extract_experiences(text)
        if not experiences:
            missing_info.append("Aucune expérience détectée")

        # ── 6. Années d'expérience ────────────────────
        years_of_experience = None
        if experiences:
            try:
                years_of_experience = calculate_years_of_experience(experiences)
                logger.info("✅ Années d'expérience: %.1f ans (dont %.1f hors stages)",
                            years_of_experience.total_years,
                            years_of_experience.total_years_excluding_internships)
            except Exception as e:
                logger.warning("Erreur calcul années d'expérience: %s", e)

        # ── 7. Langues ───────────────────────────────
        languages = extract_languages(text)
        languages_with_levels = extract_languages_with_levels(text)
        if not languages:
            missing_info.append("Aucune langue détectée")

        # ── 8. Skills ────────────────────────────────────
        hard_skills, soft_skills = extract_skills(text)
        if not hard_skills:
            missing_info.append("Aucun hard skill détecté")
        if not soft_skills:
            missing_info.append("Aucun soft skill détecté")

        # ── 9. Top 5 Outils maîtrisés ────────────────────
        top_tools = extract_top_tools(text)
        if not top_tools:
            missing_info.append("Aucun outil maîtrisé détecté")

        # ── LLM Enhancement (optionnel) ──────────────────
        if llm_service.is_available():
            logger.info("🤖 Enrichissement LLM activé")

            # Enrichissement soft skills
            llm_ss = llm_service.enhance_soft_skills(text)
            if llm_ss and llm_ss.get("soft_skills"):
                from app.models import Skill as SkillModel
                llm_soft: list = []
                for s in llm_ss["soft_skills"]:
                    name = (s.get("name") or "").strip()
                    if not name:
                        continue
                    try:
                        llm_soft.append(SkillModel(
                            name=name,
                            level=3,
                            category="soft",
                            score=5.0,
                            evidence=[s.get("evidence", "")[:200]],
                            confidence=0.85,
                        ))
                    except Exception as llm_e:
                        logger.warning("Soft skill LLM invalide ignoré: %s", llm_e)
                if llm_soft:
                    soft_skills = llm_soft[:5]
                    logger.info("✅ %d soft skill(s) extraits via LLM", len(soft_skills))

            # Enrichissement expériences
            llm_exp = llm_service.enhance_experiences(text)
            if llm_exp and llm_exp.get("experiences"):
                from app.models import Experience as ExpModel
                llm_experiences = []
                for e in llm_exp["experiences"]:
                    try:
                        llm_experiences.append(ExpModel(
                            start_date=e.get("start_date"),
                            end_date=e.get("end_date"),
                            position=e.get("position"),
                            company=e.get("company"),
                            mission_summary=e.get("mission_summary"),
                            achievements=e.get("achievements") or [],
                            technologies=e.get("technologies") or [],
                            methodologies=e.get("methodologies") or [],
                            team_size=e.get("team_size"),
                            evidence=e.get("evidence", "")[:500],
                            confidence=0.9,
                        ))
                    except Exception as llm_e:
                        logger.warning("Expérience LLM invalide ignorée: %s", llm_e)
                if llm_experiences:
                    experiences = llm_experiences
                    logger.info("✅ %d expérience(s) extraites via LLM", len(experiences))

        # ── Confiance globale ────────────────────────────
        confidences = []
        for e in educations:
            confidences.append(e.confidence)
        for e in experiences:
            confidences.append(e.confidence)
        overall = round(sum(confidences) / len(confidences), 2) if confidences else 0.5

        # ── Construire le dossier ────────────────────────
        dossier = DossierCompetences(
            source_file=file.filename,
            extraction_date=datetime.now().isoformat(),
            candidate_name=candidate_name,
            candidate_name_confidence=name_confidence,
            photo=photo_result,
            educations=educations,
            last_degree=last_degree,
            experiences=experiences,
            years_of_experience=years_of_experience,
            languages=languages,
            languages_with_levels=languages_with_levels,
            hard_skills=hard_skills,
            soft_skills=soft_skills,
            top_tools=top_tools,
            missing_information=missing_info,
            overall_confidence=overall,
        )

        # Sauvegarder le JSON
        output_json = cv_output_dir / "dossier_competences.json"
        with open(output_json, "w", encoding="utf-8") as f:
            f.write(dossier.model_dump_json(indent=2))
        logger.info("✅ JSON généré: %s", output_json)

        # Générer le fichier Word (.docx)
        try:
            docx_path = generate_dossier_docx(dossier, cv_output_dir)
            logger.info("✅ DOCX généré: %s", docx_path)
        except Exception as docx_err:
            logger.warning("Génération DOCX échouée (JSON toujours disponible): %s", docx_err)

        return dossier

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erreur lors du traitement du CV")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


# ─────────────────────────────────────────────────────────────
#  ENDPOINTS INDIVIDUELS
# ─────────────────────────────────────────────────────────────

@app.post("/extract/photo")
async def extract_photo_only(file: UploadFile = File(...)):
    """Extraction de la photo uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    cv_output_dir = OUTPUT_DIR / Path(file.filename).stem
    cv_output_dir.mkdir(exist_ok=True)
    result = extract_photo(pdf_content, pdf_path, cv_output_dir)
    return result


@app.post("/extract/education")
async def extract_education_only(file: UploadFile = File(...)):
    """Extraction des formations uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    text = clean_text(pdf_content.text)
    educations = _build_educations(text)
    last_degree = determine_last_degree(educations)
    return {"educations": educations, "last_degree": last_degree}


@app.post("/debug/text", include_in_schema=False)
async def debug_text(file: UploadFile = File(...)):
    """Debug: retourne le texte brut extrait du PDF (ne pas exposer en production)."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    raw = pdf_content.text
    cleaned = clean_text(raw)
    lines = cleaned.split("\n")
    return {
        "num_pages": pdf_content.num_pages,
        "num_chars": len(cleaned),
        "num_lines": len(lines),
        "lines": lines,          # full line list for inspection
        "text": cleaned,
    }


@app.post("/extract/experiences")
async def extract_experiences_only(file: UploadFile = File(...)):
    """Extraction des expériences uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    text = clean_text(pdf_content.text)
    experiences = extract_experiences(text)

    if llm_service.is_available():
        llm_exp = llm_service.enhance_experiences(text)
        if llm_exp and llm_exp.get("experiences"):
            from app.models import Experience as ExpModel
            llm_experiences = []
            for e in llm_exp["experiences"]:
                try:
                    llm_experiences.append(ExpModel(
                        start_date=e.get("start_date"),
                        end_date=e.get("end_date"),
                        position=e.get("position"),
                        company=e.get("company"),
                        mission_summary=e.get("mission_summary"),
                        achievements=e.get("achievements") or [],
                        technologies=e.get("technologies") or [],
                        methodologies=e.get("methodologies") or [],
                        team_size=e.get("team_size"),
                        evidence=e.get("evidence", "")[:500],
                        confidence=0.9,
                    ))
                except Exception as llm_e:
                    logger.warning("Expérience LLM invalide ignorée: %s", llm_e)
            if llm_experiences:
                experiences = llm_experiences

    return {"experiences": experiences}


@app.post("/extract/skills")
async def extract_skills_only(file: UploadFile = File(...)):
    """Extraction des compétences uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    text = clean_text(pdf_content.text)
    hard_skills, soft_skills = extract_skills(text)

    # LLM enhancement pour soft skills
    if llm_service.is_available():
        llm_ss = llm_service.enhance_soft_skills(text)
        if llm_ss and llm_ss.get("soft_skills"):
            from app.models import Skill as SkillModel
            llm_soft = []
            for s in llm_ss["soft_skills"]:
                name = (s.get("name") or "").strip()
                if not name:
                    continue
                try:
                    llm_soft.append(SkillModel(
                        name=name,
                        level=3,
                        category="soft",
                        score=5.0,
                        evidence=[s.get("evidence", "")[:200]],
                        confidence=0.85,
                    ))
                except Exception:
                    pass
            if llm_soft:
                soft_skills = llm_soft[:5]

    return {"hard_skills": hard_skills, "soft_skills": soft_skills}


@app.post("/extract/tools")
async def extract_tools_only(file: UploadFile = File(...)):
    """Top 5 outils maîtrisés uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    text = clean_text(pdf_content.text)
    top_tools = extract_top_tools(text)
    return {"top_tools": top_tools}


@app.post("/extract/languages")
async def extract_languages_only(file: UploadFile = File(...)):
    """Extraction des langues uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    text = clean_text(pdf_content.text)
    languages = extract_languages(text)
    languages_with_levels = extract_languages_with_levels(text)
    return {"languages": languages, "languages_with_levels": languages_with_levels}


@app.post("/extract/name")
async def extract_name_only(file: UploadFile = File(...)):
    """Extraction du nom et prénom du candidat uniquement."""
    pdf_path = await _save_upload(file)
    pdf_content = extract_pdf(pdf_path)
    text = clean_text(pdf_content.text)
    name, confidence = extract_candidate_name(text, pdf_path=str(pdf_path))
    return {
        "candidate_name": name,
        "confidence": round(confidence, 2),
    }


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

async def _save_upload(file: UploadFile) -> Path:
    """Sauvegarde un fichier uploadé et retourne le chemin."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés.")
    pdf_path = UPLOAD_DIR / file.filename
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return pdf_path


# ─────────────────────────────────────────────────────────────
#  TÉLÉCHARGEMENT DU DOSSIER .DOCX
# ─────────────────────────────────────────────────────────────

@app.get("/download/{cv_stem}")
def download_dossier(cv_stem: str):
    """
    Télécharge le dossier de compétences Word (.docx) pour un CV donné.

    Args:
        cv_stem: Nom du fichier CV sans extension (ex: 'cv_dupont').
    """
    cv_output_dir = OUTPUT_DIR / cv_stem
    if not cv_output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Aucun dossier trouvé pour '{cv_stem}'.")

    # Cherche le premier .docx dans le répertoire
    docx_files = list(cv_output_dir.glob("*.docx"))
    if not docx_files:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Dossier de compétences .docx non encore généré pour '{cv_stem}'. "
                "Lancez d'abord POST /extract."
            ),
        )

    docx_path = docx_files[0]
    return FileResponse(
        path=str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=docx_path.name,
    )
