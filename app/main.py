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
from app.services.language_extractor import extract_languages
from app.services.name_extractor import extract_candidate_name
from app.services import llm_service

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

        # ── 0. Nom du candidat ──────────────────────────────
        candidate_name, name_confidence = extract_candidate_name(text)
        if not candidate_name:
            missing_info.append("Nom du candidat non détecté")

        # Préparer le dossier de sortie
        cv_output_dir = OUTPUT_DIR / Path(file.filename).stem
        cv_output_dir.mkdir(exist_ok=True)

        missing_info: list[str] = []

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
        educations = extract_educations(text)
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

        # ── 6. Langues ───────────────────────────────────
        languages = extract_languages(text)
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

            # Enrichissement formations
            edu_section = find_education_section(text)
            llm_edu = llm_service.enhance_education(text, section_text=edu_section or None)
            if llm_edu and llm_edu.get("educations"):
                from app.models import Education as EduModel
                llm_educations = []
                for e in llm_edu["educations"]:
                    try:
                        llm_educations.append(EduModel(
                            year=e.get("year"),
                            degree=e.get("degree", ""),
                            school=e.get("school"),
                            degree_level=e.get("degree_level"),
                            status=e.get("status", "obtained"),
                            evidence=e.get("evidence", "")[:500],
                            confidence=0.9,
                        ))
                    except Exception as llm_e:
                        logger.warning("Formation LLM invalide ignorée: %s", llm_e)
                if llm_educations:
                    educations = llm_educations
                    last_degree = determine_last_degree(educations)
                    logger.info("✅ %d formation(s) extraites via LLM", len(educations))

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
        for l in languages:
            confidences.append(l.confidence)
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
            languages=languages,
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

        logger.info("✅ Dossier de compétences généré: %s", output_json)
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
    educations = extract_educations(text)

    if llm_service.is_available():
        edu_section = find_education_section(text)
        logger.info("Education section found: %d chars", len(edu_section))
        llm_edu = llm_service.enhance_education(text, section_text=edu_section or None)
        logger.info("LLM education result keys: %s", list(llm_edu.keys()) if llm_edu else "None")
        if llm_edu and llm_edu.get("educations"):
            from app.models import Education as EduModel
            llm_educations = []
            for e in llm_edu["educations"]:
                try:
                    llm_educations.append(EduModel(
                        year=e.get("year"),
                        degree=e.get("degree", ""),
                        school=e.get("school"),
                        degree_level=e.get("degree_level"),
                        status=e.get("status", "obtained"),
                        evidence=e.get("evidence", "")[:500],
                        confidence=0.9,
                    ))
                except Exception as llm_e:
                    logger.warning("Formation LLM invalide ignorée: %s | data=%s", llm_e, e)
            if llm_educations:
                educations = llm_educations
                logger.info("✅ %d formation(s) LLM utilisées", len(educations))
            else:
                logger.warning("LLM returned educations list but none passed validation")

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
    top_tools = extract_top_tools(text)
    return {"hard_skills": hard_skills, "soft_skills": soft_skills, "top_tools": top_tools}


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
    return {"languages": languages}


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
