# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import sys
import re
import io

# Pour extraction PDF
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("PyPDF2 non installé. Extraction PDF désactivée.")

sys.path.insert(0, '/app/scripts')

app = Flask(__name__)
CORS(app, origins=["*"])

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "job_intelligent",
    "user": "admin",
    "password": "admin123",
    "port": "5432"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)

# ==================== UTILITAIRES EXTRACTION ====================

def extract_text_from_file(file_storage):
    """Extrait le texte d'un fichier uploadé (PDF ou TXT)"""
    filename = file_storage.filename.lower()
    content = file_storage.read()

    if filename.endswith('.pdf'):
        if not PYPDF2_AVAILABLE:
            raise ImportError("PyPDF2 non installé. Installez-le avec: pip install PyPDF2")
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()

    elif filename.endswith(('.txt', '.md', '.csv')):
        return content.decode('utf-8', errors='ignore')

    else:
        try:
            return content.decode('utf-8', errors='ignore')
        except:
            raise ValueError(f"Format de fichier non supporté: {filename}")

def extract_name(text):
    """Extrait le nom depuis les premières lignes"""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:5]:
        if any(k in line.lower() for k in ['cv', 'curriculum', 'résumé', 'resume', '@', 'http', 'linkedin', 'github']):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.isalpha() for w in words):
            return line.title()
    return "Candidat"

def extract_title(text):
    """Extrait le titre/poste du CV"""
    text_lower = text.lower()

    keywords = {
        'data scientist': 'Data Scientist',
        'data analyst': 'Data Analyst',
        'data engineer': 'Data Engineer',
        'ingénieur données': 'Ingénieur Données',
        'ingénieur data': 'Data Engineer',
        'développeur web': 'Développeur Web',
        'développeur fullstack': 'Développeur Fullstack',
        'devops': 'DevOps',
        'cloud engineer': 'Cloud Engineer',
        'machine learning': 'ML Engineer',
        'stagiaire': 'Stagiaire',
        'étudiante en ingénierie': 'Étudiante Ingénierie',
        'étudiant en ingénierie': 'Étudiant Ingénierie',
        'big data': 'Big Data Engineer',
    }

    for kw, title in keywords.items():
        if kw in text_lower:
            return title

    lines = text_lower.split('\n')[:20]
    for line in lines:
        if any(k in line for k in ['data', 'développeur', 'ingénieur', 'analyst', 'scientist']):
            clean = line.strip()
            if len(clean) > 5 and len(clean) < 80:
                return clean.title()

    return "Non détecté"

def extract_experience(text):
    """Extrait les années d'expérience"""
    text_lower = text.lower()

    patterns = [
        r"(\d+)\s*(?:an|ans|year|years)\s*(?:d'expérience|experience|de\s*stage|stage)",
        r"expérience\s*:?\s*(\d+)\s*(?:an|ans)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        if matches:
            return f"{matches[0]} ans"

    generic = re.findall(r'(\d+)\s*(?:an|ans)', text_lower)
    if generic:
        return f"{max([int(x) for x in generic])} ans"

    return "Non précisé"

def extract_education(text):
    """Extrait le niveau d'études"""
    text_lower = text.lower()

    education_levels = [
        ('doctorat', 'Doctorat'),
        ('phd', 'PhD'),
        ('master', 'Master'),
        ('msc', 'Master'),
        ('mastère', 'Master'),
        ('licence', 'Licence'),
        ('bachelor', 'Bachelor'),
        ('baccalauréat', 'Baccalauréat'),
        ('bac', 'Baccalauréat'),
        ('classes préparatoires', 'CPGE'),
        ('prépa', 'CPGE'),
        ('ingénieur', "École d'Ingénieurs"),
    ]

    for keyword, level in education_levels:
        if keyword in text_lower:
            return level

    return "Non précisé"

def extract_languages(text):
    """Extrait les langues parlées"""
    text_lower = text.lower()
    languages = []

    lang_map = {
        'français': 'fr',
        'francais': 'fr',
        'french': 'fr',
        'anglais': 'en',
        'english': 'en',
        'arabe': 'ar',
        'arabic': 'ar',
        'espagnol': 'es',
        'spanish': 'es',
        'allemand': 'de',
        'german': 'de',
        'italien': 'it',
        'italian': 'it',
        'chinois': 'zh',
        'mandarin': 'zh',
    }

    for keyword, code in lang_map.items():
        if keyword in text_lower and code not in languages:
            languages.append(code)

    return languages if languages else ["fr"]

def extract_skills_from_text(text):
    """Extrait les compétences techniques du texte"""
    text_lower = text.lower()
    found = []

    skills_dict = {
        'python': 'Python', 'sql': 'SQL', 'java': 'Java',
        'javascript': 'JavaScript', 'js': 'JavaScript', 'typescript': 'TypeScript',
        'scala': 'Scala', 'r': 'R', 'php': 'PHP', 'c++': 'C++', 'c#': 'C#',
        'go': 'Go', 'rust': 'Rust', 'react': 'React', 'angular': 'Angular',
        'vue': 'Vue.js', 'django': 'Django', 'flask': 'Flask', 'spring': 'Spring',
        'node': 'Node.js', 'html': 'HTML/CSS', 'css': 'HTML/CSS',
        'pandas': 'Pandas', 'numpy': 'NumPy', 'scikit-learn': 'Scikit-learn',
        'sklearn': 'Scikit-learn', 'tensorflow': 'TensorFlow', 'pytorch': 'PyTorch',
        'keras': 'Keras', 'spark': 'Spark', 'hadoop': 'Hadoop', 'hive': 'Hive',
        'kafka': 'Kafka', 'flink': 'Flink', 'airflow': 'Airflow', 'dbt': 'dbt',
        'postgresql': 'PostgreSQL', 'postgres': 'PostgreSQL', 'mysql': 'MySQL',
        'mongodb': 'MongoDB', 'elasticsearch': 'Elasticsearch', 'redis': 'Redis',
        'snowflake': 'Snowflake', 'bigquery': 'BigQuery',
        'aws': 'AWS', 'azure': 'Azure', 'gcp': 'GCP', 'google cloud': 'GCP',
        'docker': 'Docker', 'kubernetes': 'Kubernetes', 'k8s': 'Kubernetes',
        'terraform': 'Terraform', 'ansible': 'Ansible', 'jenkins': 'Jenkins',
        'power bi': 'Power BI', 'powerbi': 'Power BI', 'tableau': 'Tableau',
        'looker': 'Looker', 'metabase': 'Metabase',
        'machine learning': 'Machine Learning', 'deep learning': 'Deep Learning',
        'nlp': 'NLP', 'computer vision': 'Computer Vision',
        'xgboost': 'XGBoost', 'lightgbm': 'LightGBM',
        'git': 'Git', 'github': 'GitHub', 'gitlab': 'GitLab',
        'excel': 'Excel', 'vba': 'VBA', 'matlab': 'MATLAB', 'nosql': 'NoSQL',
    }

    for keyword, skill_name in skills_dict.items():
        if keyword in text_lower and skill_name not in found:
            found.append(skill_name)

    return found[:15]

def extract_location(text):
    """Extrait la localisation"""
    text_lower = text.lower()

    cities = {
        'paris': 'Paris', 'lyon': 'Lyon', 'marseille': 'Marseille',
        'toulouse': 'Toulouse', 'nice': 'Nice', 'nantes': 'Nantes',
        'strasbourg': 'Strasbourg', 'montpellier': 'Montpellier',
        'bordeaux': 'Bordeaux', 'lille': 'Lille', 'rennes': 'Rennes',
        'grenoble': 'Grenoble', 'dijon': 'Dijon',
        'bruxelles': 'Bruxelles', 'genève': 'Genève', 'geneve': 'Genève',
        'luxembourg': 'Luxembourg', 'casablanca': 'Casablanca',
        'rabat': 'Rabat', 'marrakech': 'Marrakech', 'tanger': 'Tanger',
        'agadir': 'Agadir', 'fès': 'Fès', 'fes': 'Fès',
    }

    for keyword, city in cities.items():
        if keyword in text_lower:
            return city

    return "France"

# ==================== ROUTES ====================

@app.route('/api/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/api/stats')
def stats():
    """Statistiques globales pour le dashboard"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as total FROM jobs_cleaned")
    total = cur.fetchone()['total']

    cur.execute("SELECT source, COUNT(*) as count FROM jobs_cleaned GROUP BY source ORDER BY count DESC")
    by_source = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT job_category, COUNT(*) as count FROM jobs_cleaned GROUP BY job_category ORDER BY count DESC")
    by_category = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT location, COUNT(*) as count FROM jobs_cleaned GROUP BY location ORDER BY count DESC LIMIT 10")
    by_location = [dict(r) for r in cur.fetchall()]

    conn.close()

    return jsonify({
        "total_jobs": total,
        "by_source": by_source,
        "by_category": by_category,
        "by_location": by_location,
        "top_skills": []
    })

@app.route('/api/jobs')
def jobs():
    """Liste des offres avec filtres"""
    source = request.args.get('source')
    category = request.args.get('category')
    location = request.args.get('location')
    search = request.args.get('search')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    conn = get_connection()
    cur = conn.cursor()

    where = []
    params = []

    if source:
        where.append("source = %s")
        params.append(source)
    if category:
        where.append("job_category = %s")
        params.append(category)
    if location:
        where.append("location ILIKE %s")
        params.append(f"%{location}%")
    if search:
        where.append("(title ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where_clause = "WHERE " + " AND ".join(where) if where else ""
    offset = (page - 1) * per_page

    cur.execute(f"""
        SELECT id, source, title, company, location, job_category,
               contract_type, salary, url, publication_date, scraped_at
        FROM jobs_cleaned
        {where_clause}
        ORDER BY scraped_at DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    jobs_list = [dict(r) for r in cur.fetchall()]

    cur.execute(f"SELECT COUNT(*) as total FROM jobs_cleaned {where_clause}", params)
    total = cur.fetchone()['total']

    conn.close()

    return jsonify({
        "jobs": jobs_list,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    })

@app.route('/api/jobs/<int:job_id>')
def job_detail(job_id):
    """Détail d'une offre"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM jobs_cleaned WHERE id = %s", (job_id,))
    job = cur.fetchone()

    if not job:
        return jsonify({"error": "Offre non trouvée"}), 404

    cur.execute("SELECT skill_name FROM job_skills WHERE job_id = %s", (job_id,))
    skills = [r['skill_name'] for r in cur.fetchall()]

    conn.close()

    result = dict(job)
    result['skills'] = skills
    return jsonify(result)

@app.route('/api/extract-cv', methods=['POST'])
def extract_cv():
    """Extraction du profil depuis un fichier PDF ou texte"""
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Aucun fichier sélectionné"}), 400
        try:
            cv_text = extract_text_from_file(file)
        except ImportError as e:
            return jsonify({"error": str(e)}), 500
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Erreur extraction: {str(e)}"}), 500
    else:
        body = request.get_json() or {}
        cv_text = body.get('cv_text', '')

    if not cv_text or len(cv_text.strip()) < 10:
        return jsonify({"error": "Aucun contenu trouvé dans le CV"}), 400

    profile = {
        "name":             extract_name(cv_text),
        "title":            extract_title(cv_text),
        "experience_years": extract_experience(cv_text),
        "education":        extract_education(cv_text),
        "languages":        extract_languages(cv_text),
        "skills":           extract_skills_from_text(cv_text),
        "location":         extract_location(cv_text)
    }

    return jsonify({"profile": profile})

@app.route('/api/recommend', methods=['POST'])
def recommend_endpoint():
    """Recommandation d'offres basée sur le profil"""
    body = request.get_json()

    if not body:
        return jsonify({"error": "Corps de requête manquant"}), 400

    skills_raw = body.get('skills', '')
    title      = body.get('title', '')
    experience = body.get('experience', '')
    location   = body.get('location', '')
    category   = body.get('category', '')
    top_n      = int(body.get('top_n', 20))

    # Accepte skills en string ou liste
    if isinstance(skills_raw, str):
        skill_list = [s.strip().lower() for s in skills_raw.split(',') if s.strip()]
    else:
        skill_list = [s.strip().lower() for s in skills_raw if s.strip()]

    if not skill_list and not title:
        return jsonify({"error": "Fournissez au moins des compétences ou un titre"}), 400

    try:
        conn = get_connection()
        cur  = conn.cursor()

        conditions = []
        params     = []

        if title:
            conditions.append("LOWER(title) LIKE %s")
            params.append(f"%{title.lower()}%")

        if category:
            conditions.append("job_category = %s")
            params.append(category)

        if location:
            conditions.append("LOWER(location) LIKE %s")
            params.append(f"%{location.lower()}%")

        where_clause = ("WHERE " + " OR ".join(conditions)) if conditions else ""

        cur.execute(f"""
            SELECT id, title, company, location, contract_type, salary,
                   description, url, job_category, experience
            FROM jobs_cleaned
            {where_clause}
            LIMIT 100
        """, params)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        recommendations = []
        for job in rows:
            desc      = (job.get('description') or '').lower()
            job_title = (job.get('title') or '').lower()
            combined  = desc + " " + job_title

            matched = [s for s in skill_list if s in combined]
            missing = [s for s in skill_list if s not in combined]
            score   = int((len(matched) / max(len(skill_list), 1)) * 100) if skill_list else 50

            if title and title.lower() in job_title:
                score = min(99, score + 20)

            recommendations.append({
                "title":          job['title'],
                "company":        job['company'],
                "location":       job['location'],
                "contract_type":  job['contract_type'],
                "salary":         job['salary'],
                "url":            job['url'],
                "score":          score,
                "required_skills": matched or skill_list[:3],
                "missing_skills":  missing[:3],
                "reasoning":      f"Correspondance sur {len(matched)}/{len(skill_list)} compétences clés."
            })

        recommendations.sort(key=lambda x: x['score'], reverse=True)

        return jsonify({
            "recommendations": recommendations[:top_n],
            "total": len(recommendations)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/filters')
def filters():
    """Valeurs disponibles pour les filtres"""
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("SELECT DISTINCT source FROM jobs_cleaned ORDER BY source")
    sources = [r['source'] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT job_category FROM jobs_cleaned ORDER BY job_category")
    categories = [r['job_category'] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT location FROM jobs_cleaned WHERE location != 'Non précisé' ORDER BY location LIMIT 50")
    locations = [r['location'] for r in cur.fetchall()]

    conn.close()

    return jsonify({"sources": sources, "categories": categories, "locations": locations})

if __name__ == '__main__':
    print("🚀 JobSpark API démarrée sur http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)