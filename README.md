# Cv2DC

Transforme un CV PDF en Dossier de Compétences (JSON).

## Installation

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration (optionnel)

```bash
copy .env.example .env
# Ajouter la clé Groq dans .env — gratuite : https://console.groq.com/keys
```

## Lancer

```bash
uvicorn app.main:app --reload --port 8000
```

## Tester

Ouvrir `http://localhost:8000/docs` → uploader un CV PDF sur `POST /extract`.

## Ce qui est extrait

- Nom du candidat
- Photo
- Formations + Dernier diplôme
- Expériences professionnelles + Années d'expérience
- Langues (Top 3, niveau /5)
- Hard Skills (Top 5, niveau /5)
- Soft Skills (Top 5, niveau /5)
- Outils maîtrisés (Top 5, niveau /5)
