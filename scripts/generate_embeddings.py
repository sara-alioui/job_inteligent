import psycopg2
import pandas as pd
import pickle
import os
from sklearn.feature_extraction.text import TfidfVectorizer
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

def load_jobs():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, title, company, location, description, 
               job_category, contract_type, salary, source
        FROM jobs_cleaned
        WHERE description IS NOT NULL AND description != ''
    """, conn)
    conn.close()
    print(f"✅ {len(df)} offres chargées")
    return df

def build_text(row):
    """Combine titre + description + compétences pour le vecteur"""
    parts = [
        str(row.get('title', '')),
        str(row.get('job_category', '')),
        str(row.get('description', '')),
    ]
    return ' '.join(parts).lower()

def generate_embeddings(df):
    print("🔄 Génération des embeddings TF-IDF...")
    
    corpus = df.apply(build_text, axis=1).tolist()
    
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        stop_words=None,
        min_df=2,
        max_df=0.95
    )
    
    matrix = vectorizer.fit_transform(corpus)
    matrix_normalized = normalize(matrix)
    
    print(f"✅ Matrice TF-IDF : {matrix_normalized.shape}")
    return vectorizer, matrix_normalized

def save_embeddings(df, vectorizer, matrix):
    data = {
        "job_ids": df['id'].tolist(),
        "vectorizer": vectorizer,
        "matrix": matrix,
        "df": df[['id', 'title', 'company', 'location', 
                  'job_category', 'contract_type', 'salary', 'source']].to_dict('records')
    }
    with open(EMBEDDINGS_PATH, 'wb') as f:
        pickle.dump(data, f)
    print(f"✅ Embeddings sauvegardés dans {EMBEDDINGS_PATH}")

def save_to_db(df, vectorizer, matrix):
    """Sauvegarde aussi les stats dans PostgreSQL"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings_meta (
            id SERIAL PRIMARY KEY,
            total_jobs INTEGER,
            vocab_size INTEGER,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("TRUNCATE TABLE embeddings_meta")
    cur.execute("""
        INSERT INTO embeddings_meta (total_jobs, vocab_size)
        VALUES (%s, %s)
    """, (len(df), len(vectorizer.vocabulary_)))
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Métadonnées sauvegardées en base")

if __name__ == "__main__":
    df = load_jobs()
    
    if len(df) == 0:
        print("❌ Aucune offre trouvée dans jobs_cleaned")
        exit(1)
    
    vectorizer, matrix = generate_embeddings(df)
    save_embeddings(df, vectorizer, matrix)
    save_to_db(df, vectorizer, matrix)
    
    print("\n🎉 Embeddings générés avec succès !")
    print(f"   - {len(df)} offres vectorisées")
    print(f"   - {len(vectorizer.vocabulary_)} termes dans le vocabulaire")