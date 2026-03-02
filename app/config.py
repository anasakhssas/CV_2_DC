"""Configuration de l'application Cv2DC."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Répertoires ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Groq / LLM (gratuit) ─────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── Extraction photo ────────────────────────────────────────
PHOTO_MIN_SIZE = 150          # pixels minimum (largeur & hauteur)
PHOTO_OUTPUT_SIZE = (512, 512)

# ── Niveaux diplômes ────────────────────────────────────────
DEGREE_LEVELS: dict[str, int] = {
    "doctorat": 8, "phd": 8, "doctorate": 8,
    "master": 7, "mastere": 7, "mastère": 7, "ingénieur": 7, "ingenieur": 7,
    "cycle ingénieur": 7, "cycle ingenieur": 7, "école d'ingénieur": 7,
    "msc": 7, "mba": 7, "m2": 7,
    "licence": 6, "bachelor": 6, "bsc": 6, "ba": 6, "l3": 6,
    "dut": 5, "bts": 5, "deust": 5, "deug": 5, "bpro": 5,
    "baccalauréat": 4, "baccalaureat": 4, "bac": 4,
    "classes prépa": 4, "cpge": 4,
}

# ── Labels de niveau diplôme ────────────────────────────────
DEGREE_LEVEL_LABELS: dict[int, str] = {
    8: "Bac+8 / Doctorat",
    7: "Bac+5 / Master-Ingénieur",
    6: "Bac+3 / Licence",
    5: "Bac+2 / DUT-BTS",
    4: "Baccalauréat / Prépa",
}

# ── Mapping langues → niveau /5 ─────────────────────────────
LANGUAGE_LEVEL_MAP: dict[str, float] = {
    # Natif / bilingue
    "native": 5, "natif": 5, "natif(ve)": 5, "langue maternelle": 5,
    "mother tongue": 5, "maternelle": 5, "maternel": 5,
    "bilingue": 5, "bilingual": 5, "c2": 5,
    # Avancé / Courant
    "avancé": 4, "avance": 4, "advanced": 4,
    "fluent": 4, "couramment": 4, "courant": 4, "courante": 4,
    "professional proficiency": 4, "c1": 4,
    "full professional proficiency": 4.5,
    # Intermédiaire avancé
    "b2": 3.5, "upper intermediate": 3.5,
    "intermédiaire avancé": 3.5, "intermediaire avancé": 3.5,
    "intermediaire avance": 3.5,
    # Intermédiaire
    "intermediate": 3, "intermédiaire": 3, "intermediaire": 3, "b1": 3, "moyen": 3,
    # Basique
    "basic": 2, "basique": 2, "notions": 2,
    "scolaire": 2, "a2": 2, "elementary": 2,
    # Débutant
    "beginner": 1, "débutant": 1, "a1": 1,
}

# ── Taxonomie compétences (ce que l'on SAIT FAIRE) ──────────
# Hard skills = domaines de compétence / savoir-faire métier,
# PAS des technologies (celles-ci vont dans TOOLS_TAXONOMY).
HARD_SKILLS_TAXONOMY: set[str] = {
    # ── Data & IA ──────────────────────────────────────────
    "machine learning", "deep learning",
    "computer vision", "vision par ordinateur",
    "nlp", "natural language processing",
    "traitement du langage naturel", "traitement automatique du langage",
    "text mining", "sentiment analysis", "analyse de sentiment",
    "data science", "data engineering",
    "data analysis", "analyse de données", "analyse des données",
    "data preprocessing", "préparation des données", "préparation de données",
    "feature engineering",
    "statistical analysis", "analyse statistique", "statistiques",
    "predictive modeling", "modélisation prédictive",
    "model training", "entraînement de modèles",
    "model optimization", "optimisation de modèles",
    "model evaluation", "évaluation de modèles",
    "data visualization", "visualisation de données", "visualisation des données",
    "business intelligence",
    "etl", "data pipeline", "pipeline de données",
    "data warehouse", "data warehousing",
    "big data", "data lake",
    "recommender system", "système de recommandation",
    "time series", "série temporelle", "prévision",
    "generative ai", "ia générative", "llm", "large language model",
    "prompt engineering",
    "rag", "retrieval augmented generation",
    # ── Développement logiciel ─────────────────────────────
    "backend development", "développement backend",
    "frontend development", "développement frontend",
    "full-stack development", "full stack", "full-stack",
    "web development", "développement web",
    "mobile development", "développement mobile",
    "api design", "conception d'api", "conception api",
    "rest api", "api rest", "restful api",
    "graphql", "grpc", "websocket", "soap",
    "microservices", "architecture microservices",
    "software architecture", "architecture logicielle",
    "system design", "conception de système",
    "database design", "conception de base de données", "modélisation de données",
    "object-oriented programming", "programmation orientée objet", "oop",
    "functional programming", "programmation fonctionnelle",
    "design patterns", "clean code", "solid principles",
    "unit testing", "tests unitaires",
    "integration testing", "tests d'intégration",
    "test-driven development", "tdd",
    "web scraping", "automatisation",
    # ── DevOps / Infra / Cloud ─────────────────────────────
    "devops", "devsecops", "sre",
    "ci/cd", "intégration continue", "continuous integration",
    "continuous deployment", "continuous delivery",
    "cloud computing", "cloud architecture", "architecture cloud",
    "cloud deployment", "déploiement cloud",
    "containerization", "conteneurisation",
    "infrastructure as code",
    "monitoring", "observabilité",
    # ── Sécurité ───────────────────────────────────────────
    "cybersecurity", "cybersécurité", "sécurité informatique",
    "penetration testing", "test d'intrusion",
    "secure coding", "codage sécurisé",
    # ── Méthodes & Management ──────────────────────────────
    "agile", "scrum", "kanban",
    "project management", "gestion de projet",
    "technical leadership", "lead technique",
    "code review", "revue de code",
    "business analysis", "analyse métier",
    "reporting",
    # ── Domaines métier ────────────────────────────────────
    "finance", "comptabilité", "accounting",
    "marketing digital", "seo", "e-commerce",
    "embedded systems", "systèmes embarqués",
    "iot", "internet of things",
    "blockchain", "web3", "smart contracts",
    "game development", "développement de jeux",
    "erp", "crm",
    "network administration", "administration réseau",
    "linux administration", "administration système",
}

SOFT_SKILLS_TAXONOMY: set[str] = {
    # ── Communication ──────────────────────────────────────
    "communication", "communication skills", "compétences en communication",
    "written communication", "verbal communication",
    "presentation", "présentation", "public speaking", "prise de parole en public",
    # ── Leadership & management ────────────────────────────
    "leadership", "team leadership", "lead", "leading",
    "mentoring", "coaching", "management",
    "decision making", "prise de décision",
    # ── Travail en équipe ──────────────────────────────────
    "teamwork", "team player", "travail en équipe", "esprit d'équipe",
    "esprit équipe", "collaboration", "collaborative",
    "interpersonal skills", "compétences interpersonnelles",
    # ── Résolution de problèmes ────────────────────────────
    "problem solving", "problem-solving", "résolution de problèmes",
    "critical thinking", "pensée critique", "analytical thinking", "pensée analytique",
    "analytical skills", "esprit analytique", "esprit d'analyse",
    # ── Adaptabilité ──────────────────────────────────────
    "adaptability", "adaptabilité", "flexibility", "flexibilité",
    "versatility", "polyvalence", "polyvalent",
    "resilience", "résilience",
    # ── Organisation & rigueur ─────────────────────────────
    "time management", "gestion du temps",
    "organization", "organisation", "organised", "organisé",
    "attention to detail", "souci du détail", "rigueur", "rigoureux",
    "work ethic", "éthique de travail",
    "stress management", "gestion du stress",
    # ── Autonomie & initiative ─────────────────────────────
    "autonomy", "autonomie", "autonomous", "autonome",
    "initiative", "proactivity", "proactivité", "proactive",
    "self-motivated", "self motivated",
    # ── Créativité & innovation ────────────────────────────
    "creativity", "créativité", "creative", "créatif",
    "innovation", "innovative", "innovant",
    # ── Qualités personnelles ──────────────────────────────
    "curiosity", "curiosité", "curious",
    "motivation", "motivated", "motivé",
    "perseverance", "persévérance", "determination", "détermination",
    "empathy", "empathie",
    "conflict resolution", "gestion des conflits",
    "negotiation", "négociation",
    "emotional intelligence", "intelligence émotionnelle",
    # ── Sens des responsabilités ───────────────────────────
    "responsibility", "responsabilité", "sens des responsabilités",
    "accountability", "reliability", "fiabilité",
    # ── Autres ────────────────────────────────────────────
    "fast learner", "quick learner", "apprentissage rapide",
    "continuous learning", "veille technologique",
    "open-minded", "ouverture d'esprit",
    "multitasking", "gestion des priorités",
}

# ── Taxonomie Outils / Technologies (ce que l'on UTILISE) ──
# Langages, frameworks, plateformes, bibliothèques, logiciels.
TOOLS_TAXONOMY: set[str] = {
    # Langages de programmation
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "go", "rust", "ruby", "php", "swift", "kotlin", "scala",
    "r", "matlab", "bash", "powershell", "sql", "nosql",
    # Bases de données
    "mongodb", "postgresql", "mysql", "oracle", "sqlite",
    "redis", "elasticsearch", "neo4j", "cassandra", "snowflake",
    "mariadb", "dynamodb", "firebase",
    # Frontend
    "react", "angular", "vue", "vue.js", "next.js", "nuxt.js", "svelte",
    "html", "css", "sass", "tailwind", "bootstrap", "jquery",
    # Backend / Frameworks
    "node.js", "express", "fastapi", "django", "flask",
    "spring", "spring boot", "laravel", "asp.net", ".net",
    "rails", "symfony", "nestjs", "strapi",
    # DevOps / Conteneurs
    "docker", "kubernetes", "k8s", "terraform", "ansible",
    "jenkins", "gitlab ci", "github actions", "helm", "vagrant", "nginx",
    # Gestion de version
    "git", "github", "gitlab", "bitbucket", "svn",
    # Cloud
    "aws", "azure", "gcp", "google cloud", "heroku", "vercel",
    "netlify", "digitalocean", "render", "railway",
    # Systèmes
    "linux", "ubuntu", "centos", "windows server",
    # Data / ML / IA — bibliothèques & plateformes
    "tensorflow", "pytorch", "keras", "scikit-learn", "scikit learn",
    "pandas", "numpy", "scipy", "matplotlib", "seaborn", "plotly",
    "xgboost", "lightgbm", "hugging face", "transformers",
    "langchain", "openai", "gemini", "mistral", "ollama",
    "spark", "pyspark", "hadoop", "hive",
    "airflow", "apache airflow", "prefect", "luigi",
    "kafka", "apache kafka", "rabbitmq",
    "mlflow", "wandb", "dvc",
    # BI / Visualisation
    "power bi", "tableau", "grafana", "kibana", "metabase",
    "looker", "google analytics",
    # IDE / Éditeurs
    "vs code", "vscode", "intellij", "pycharm", "eclipse",
    "jupyter", "google colab",
    # Gestion de projet
    "jira", "trello", "confluence", "notion", "asana", "monday",
    # Design / UI-UX
    "figma", "adobe xd", "photoshop", "illustrator", "canva",
    # API / Tests
    "postman", "insomnia", "swagger", "openapi",
    "selenium", "cypress", "jest", "pytest", "junit",
    # Monitoring / Logs
    "prometheus", "datadog", "sentry", "sonarqube",
    "elasticsearch", "logstash", "splunk",
    # Sécurité
    "oauth", "jwt", "ssl", "tls",
    # Build / Packaging
    "gradle", "maven", "npm", "yarn", "pip", "conda", "poetry",
    # Office / Bureautique
    "excel", "word", "powerpoint", "google sheets",
    "microsoft teams", "slack",
    # ERP / CRM
    "sap", "odoo", "salesforce", "hubspot",
    # Blockchain / Web3
    "solidity",
    # Autres
    "wordpress", "unity", "unreal engine",
}

# ── Normalisation des noms de diplômes ───────────────────────
# regex pattern → forme normalisée
DEGREE_NORMALIZATION: list[tuple[str, str]] = [
    (r"(?i)cycle\s+(?:d[''\u2019]?\s*)?ing[éeè]nieu?r", "Cycle Ingénieur"),
    (r"(?i)dipl[ôo]me\s+(?:d[''\u2019]?\s*)?ing[éeè]nieu?r", "Diplôme d'Ingénieur"),
    (r"(?i)\bmaster\s*2\b", "Master 2"),
    (r"(?i)\bmaster\s*1\b", "Master 1"),
    (r"(?i)licence\s+professionnelle", "Licence Professionnelle"),
    (r"(?i)licence\s+fondamentale", "Licence Fondamentale"),
    (r"(?i)classes?\s+pr[éeè]pa(?:ratoires?)?\s*(?:aux\s+grandes\s+[éeè]coles)?", "Classes Préparatoires (CPGE)"),
    (r"(?i)\bcpge\b", "Classes Préparatoires (CPGE)"),
    (r"(?i)baccalaur[éeè]at", "Baccalauréat"),
]

# ── Normalisation synonymes ──────────────────────────────────
SKILL_ALIASES: dict[str, str] = {
    # Langages
    "js": "JavaScript", "ts": "TypeScript",
    "py": "Python", "cpp": "C++", "csharp": "C#",
    # Bases de données
    "postgres": "PostgreSQL", "mongo": "MongoDB",
    "elastic": "Elasticsearch",
    # Frameworks / outils
    "k8s": "Kubernetes", "tf": "Terraform",
    "react.js": "React", "reactjs": "React",
    "angularjs": "Angular", "vuejs": "Vue.js",
    "nextjs": "Next.js", "expressjs": "Express",
    "node": "Node.js", "nodejs": "Node.js",
    "sklearn": "scikit-learn", "sk-learn": "scikit-learn",
    "hf": "Hugging Face", "gpt": "OpenAI",
    "langchain": "LangChain",
    # Cloud
    "gcp": "GCP", "google cloud platform": "GCP",
    # Soft skills
    "problem-solving": "Problem solving",
    "problem solving": "Problem solving",
    # Compétences FR ↔ EN (canonicalisation)
    "analyse de données": "Data Analysis",
    "analyse des données": "Data Analysis",
    "visualisation de données": "Data Visualization",
    "visualisation des données": "Data Visualization",
    "préparation des données": "Data Preprocessing",
    "ia générative": "Generative AI",
    "traitement du langage naturel": "NLP",
    "traitement automatique du langage": "NLP",
    "vision par ordinateur": "Computer Vision",
    "modélisation prédictive": "Predictive Modeling",
    "développement backend": "Backend Development",
    "développement frontend": "Frontend Development",
    "développement web": "Web Development",
    "développement mobile": "Mobile Development",
    "architecture logicielle": "Software Architecture",
    "conception api": "API Design",
    "conception d'api": "API Design",
    "gestion de projet": "Project Management",
    "intégration continue": "CI/CD",
    "conteneurisation": "Containerization",
    "déploiement cloud": "Cloud Deployment",
    "architecture cloud": "Cloud Architecture",
    "sécurité informatique": "Cybersecurity",
}
