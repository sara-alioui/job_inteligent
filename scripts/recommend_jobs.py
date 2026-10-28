import psycopg2
import pickle
import os
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "database": "job_intelligent",
    "user": "admin",
    "password": "admin123",
    "port": "5432"
}

EMBEDDINGS_PATH = "/opt/airflow/scripts/embeddings.pkl"

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def load_embeddings():
    if not os.path.exists(EMBEDDINGS_PATH):
        raise FileNotFoundError(
            f"❌ Embeddings non trouvés : {EMBEDDINGS_PATH}\n"
            "Lancez d'abord generate_embeddings.py"
        )
    with open(EMBEDDINGS_PATH, 'rb') as f:
        return pickle.load(f)

def build_profile_text(skills, title="", experience=""):
    """Construit le texte du profil candidat"""
    parts = []
    if title:
        parts.append(title)
    if skills:
        if isinstance(skills, list):
            parts.extend(skills)
        else:
            parts.append(skills)
    if experience:
        parts.append(experience)
    return ' '.join(parts).lower()

def recommend(skills, title="", experience="", top_n=10, category_filter=None):
    """
    Recommande les offres les plus pertinentes.
    
    Args:
        skills: liste ou string de compétences (ex: ["Python", "SQL", "Spark"])
        title: titre recherché (ex: "Data Engineer")
        experience: niveau d'expérience (ex: "3 ans machine learning")
        top_n: nombre de recommandations
        category_filter: filtre par catégorie (ex: "Data Engineer")
    
    Returns:
        liste de dicts avec les offres recommandées + score
    """
    data = load_embeddings()
    vectorizer = data['vectorizer']
    matrix = data['matrix']
    jobs = data['df']
    
    # Vectoriser le profil candidat
    profile_text = build_profile_text(skills, title, experience)
    print(f"🔍 Profil candidat : {profile_text[:100]}...")
    
    profile_vector = vectorizer.transform([profile_text])
    profile_vector_norm = normalize(profile_vector)
    
    # Calculer la similarité cosinus
    scores = cosine_similarity(profile_vector_norm, matrix)[0]
    
    # Appliquer filtre catégorie si demandé
    if category_filter:
        for i, job in enumerate(jobs):
            if job.get('job_category', '') != category_filter:
                scores[i] = 0
    
    # Trier par score décroissant
    top_indices = np.argsort(scores)[::-1][:top_n * 2]
    
    results = []
    seen_titles = set()
    
    for idx in top_indices:
        if len(results) >= top_n:
            break
        
        job = jobs[idx]
        score = float(scores[idx])
        
        if score < 0.01:
            continue
        
        # Éviter les doublons par titre+entreprise
        key = f"{job['title']}_{job['company']}"
        if key in seen_titles:
            continue
        seen_titles.add(key)
        
        results.append({
            "id": job['id'],
            "title": job['title'],
            "company": job['company'],
            "location": job['location'],
            "job_category": job['job_category'],
            "contract_type": job['contract_type'],
            "salary": job['salary'],
            "source": job['source'],
            "score": round(score * 100, 1)
        })
    
    return results

def save_recommendation_to_db(profile, results):
    """Sauvegarde les recommandations en base pour historique"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommendations_history (
            id SERIAL PRIMARY KEY,
            profile_skills TEXT,
            profile_title TEXT,
            recommended_job_ids TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    job_ids = ','.join([str(r['id']) for r in results])
    cur.execute("""
        INSERT INTO recommendations_history (profile_skills, profile_title, recommended_job_ids)
        VALUES (%s, %s, %s)
    """, (
        json.dumps(profile.get('skills', [])),
        profile.get('title', ''),
        job_ids
    ))
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    # Test de recommandation
    print("🎯 Test du système de recommandation\n")
    
    profile = {
        "skills": ["Python", "SQL", "Spark", "Airflow", "ETL", "PostgreSQL"],
        "title": "Data Engineer",
        "experience": "pipeline données traitement big data"
    }
    
    results = recommend(
        skills=profile['skills'],
        title=profile['title'],
        experience=profile['experience'],
        top_n=5
    )
    
    print(f"\n✅ Top {len(results)} recommandations :\n")
    for i, job in enumerate(results, 1):
        print(f"{i}. [{job['score']}%] {job['title']} - {job['company']}")
        print(f"   📍 {job['location']} | 💼 {job['contract_type']} | 🏷️ {job['job_category']}")
        print()
    
    if results:
        save_recommendation_to_db(profile, results)
        print("✅ Recommandations sauvegardées en base")