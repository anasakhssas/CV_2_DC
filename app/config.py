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
    "master": 7, "ingénieur": 7, "ingenieur": 7, "msc": 7, "mba": 7,
    "licence": 6, "bachelor": 6, "bsc": 6,
    "dut": 5, "bts": 5, "deust": 5, "deug": 5,
    "baccalauréat": 4, "baccalaureat": 4, "bac": 4,
}

# ── Labels de niveau diplôme ────────────────────────────────
DEGREE_LEVEL_LABELS: dict[int, str] = {
    8: "Bac+8 / Doctorat",
    7: "Bac+5 / Master-Ingénieur",
    6: "Bac+3 / Licence",
    5: "Bac+2 / DUT-BTS",
    4: "Baccalauréat",
}

# ── Mapping langues → niveau /5 ─────────────────────────────
LANGUAGE_LEVEL_MAP: dict[str, float] = {
    # Natif / bilingue
    "native": 5, "mother tongue": 5, "langue maternelle": 5,
    "bilingue": 5, "bilingual": 5, "c2": 5,
    # Courant
    "fluent": 4, "couramment": 4, "courant": 4,
    "professional proficiency": 4, "c1": 4,
    "full professional proficiency": 4.5,
    # Intermédiaire avancé
    "b2": 3.5, "upper intermediate": 3.5,
    "intermédiaire avancé": 3.5,
    # Intermédiaire
    "intermediate": 3, "intermédiaire": 3, "b1": 3,
    # Basique
    "basic": 2, "basique": 2, "notions": 2,
    "scolaire": 2, "a2": 2, "elementary": 2,
    # Débutant
    "beginner": 1, "débutant": 1, "a1": 1,
}

# ── Taxonomie compétences ───────────────────────────────────
HARD_SKILLS_TAXONOMY: set[str] = {
    "python", "java", "javascript", "typescript", "c", "c++", "c#", "go",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "sql", "nosql", "mongodb", "postgresql", "mysql", "oracle", "redis",
    "elasticsearch", "neo4j", "cassandra", "sqlite",
    "react", "angular", "vue", "vue.js", "next.js", "nuxt.js", "svelte",
    "html", "css", "sass", "tailwind", "bootstrap",
    "node.js", "express", "fastapi", "django", "flask", "spring",
    "spring boot", "laravel", "asp.net", ".net",
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "gitlab ci",
    "github actions", "ci/cd", "nginx", "apache",
    "aws", "azure", "gcp", "google cloud", "heroku", "digitalocean",
    "linux", "windows server", "bash", "powershell",
    "git", "svn", "jira", "confluence", "trello",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "spark", "hadoop", "airflow", "kafka", "rabbitmq",
    "power bi", "tableau", "grafana", "kibana",
    "figma", "adobe xd", "photoshop", "illustrator",
    "rest", "graphql", "grpc", "websocket", "soap",
    "microservices", "architecture", "design patterns",
    "machine learning", "deep learning", "nlp", "computer vision",
    "data science", "data engineering", "etl", "data warehouse",
    "devops", "sre", "agile", "scrum", "kanban",
    "selenium", "cypress", "jest", "junit", "pytest",
    "oauth", "jwt", "ssl", "tls",
    "blockchain", "solidity", "web3",
    "unity", "unreal engine",
    "excel", "word", "powerpoint",
    "sap", "odoo", "salesforce",
}

SOFT_SKILLS_TAXONOMY: set[str] = {
    "communication", "leadership", "teamwork", "problem solving",
    "problem-solving", "critical thinking", "adaptability", "adaptabilité",
    "time management", "gestion du temps", "creativity", "créativité",
    "collaboration", "decision making", "prise de décision",
    "conflict resolution", "gestion des conflits",
    "emotional intelligence", "intelligence émotionnelle",
    "negotiation", "négociation", "presentation", "présentation",
    "mentoring", "coaching", "empathy", "empathie",
    "flexibility", "flexibilité", "initiative",
    "attention to detail", "souci du détail",
    "work ethic", "éthique de travail",
    "stress management", "gestion du stress",
    "analytical thinking", "pensée analytique",
    "organization", "organisation",
    "autonomy", "autonomie",
    "curiosity", "curiosité",
    "proactivity", "proactivité",
    "motivation", "perseverance", "persévérance",
    "interpersonal skills", "compétences interpersonnelles",
    "public speaking", "prise de parole en public",
}

# ── Taxonomie Outils maîtrisés ─────────────────────────────
TOOLS_TAXONOMY: set[str] = {
    # Gestion de version / Collaboration code
    "git", "github", "gitlab", "bitbucket", "svn",
    # Éditeurs / IDEs
    "vs code", "vscode", "intellij", "pycharm", "eclipse", "netbeans",
    "android studio", "xcode", "sublime text", "vim", "neovim",
    # DevOps / Conteneurs
    "docker", "kubernetes", "k8s", "jenkins", "gitlab ci", "github actions",
    "terraform", "ansible", "helm", "vagrant",
    # Cloud (plateformes)
    "aws", "azure", "gcp", "google cloud", "heroku", "vercel", "netlify",
    "digitalocean", "render", "railway",
    # Gestion de projet
    "jira", "trello", "confluence", "notion", "asana", "monday",
    "clickup", "linear",
    # Design / UI-UX
    "figma", "adobe xd", "sketch", "invision", "zeplin",
    "photoshop", "illustrator", "canva",
    # API / Tests
    "postman", "insomnia", "swagger", "openapi",
    "selenium", "cypress", "jest", "pytest", "junit",
    # Bases de données (clients)
    "pgadmin", "dbeaver", "mongodb compass", "tableplus", "datagrip",
    # BI / Visualisation
    "power bi", "tableau", "grafana", "kibana", "metabase",
    "google analytics", "looker",
    # Monitoring / Logs
    "prometheus", "datadog", "new relic", "sentry", "elasticsearch",
    "logstash", "splunk",
    # Messaging / Communication
    "kafka", "rabbitmq", "redis",
    # Office / Bureautique
    "excel", "word", "powerpoint", "google sheets", "google docs",
    "microsoft teams", "slack", "zoom",
    # CMS / ERP
    "wordpress", "drupal", "odoo", "sap", "salesforce", "hubspot",
    # Autres
    "nginx", "apache", "linux", "ubuntu", "centos",
    "sonarqube", "gradle", "maven", "npm", "yarn", "pip", "conda",
}

# ── Normalisation synonymes skills ──────────────────────────
SKILL_ALIASES: dict[str, str] = {
    "js": "JavaScript", "ts": "TypeScript",
    "py": "Python", "postgres": "PostgreSQL",
    "mongo": "MongoDB", "k8s": "Kubernetes",
    "tf": "Terraform", "react.js": "React",
    "reactjs": "React", "angularjs": "Angular",
    "vuejs": "Vue.js", "nextjs": "Next.js",
    "expressjs": "Express", "node": "Node.js",
    "nodejs": "Node.js", "problem-solving": "Problem solving",
    "problem solving": "Problem solving",
}
