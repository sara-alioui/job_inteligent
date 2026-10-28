import pandas as pd
import psycopg2
import re

# ============================================
# CONNEXION
# ============================================
DB_CONFIG = {
    "host": "postgres",
    "database": "job_intelligent",
    "user": "admin",
    "password": "admin123",
    "port": "5432"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ============================================
# CHARGEMENT
# ============================================
def load_data():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM jobs_raw", conn)
    conn.close()
    print(f"✅ {len(df)} offres chargées")
    return df

# ============================================
# NETTOYAGE
# ============================================
def clean_data(df):

    print(f"📊 Avant nettoyage : {len(df)} offres")

    # 0. Générer des external_id uniques si manquants
    df['external_id'] = df.apply(
        lambda r: r['external_id'] if pd.notna(r['external_id']) and r['external_id'] != ''
        else f"{r['source']}_{r['title']}_{r['company']}_{r['location']}",
        axis=1
    )

    # 1. Supprimer les doublons par external_id
    before = len(df)
    df = df.drop_duplicates(subset=['external_id'], keep='first')
    print(f"✅ Après déduplication external_id : {len(df)} offres (supprimé {before - len(df)})")

    # 2. Supprimer les doublons par titre+entreprise+ville MAIS séparément par source
    before = len(df)
    df = df.drop_duplicates(subset=['source', 'title', 'company', 'location'], keep='first')
    print(f"✅ Après déduplication source/titre/entreprise/ville : {len(df)} offres (supprimé {before - len(df)})")

    # 3. Normaliser les titres
    df['title'] = df['title'].str.strip()
    df['title'] = df['title'].str.replace(r'\s+', ' ', regex=True)
    df['title'] = df['title'].apply(normalize_title)

    # 4. Normaliser company
    df['company'] = df['company'].str.strip()
    df['company'] = df['company'].str.title()

    # 5. Normaliser location
    df['location'] = df['location'].fillna('Non précisé')
    df['location'] = df['location'].str.strip()
    df['location'] = df['location'].str.title()
    # Remplacer "Fr", "France" par quelque chose de plus lisible
    df['location'] = df['location'].replace({'Fr': 'France', 'France ': 'France'})

    # 6. Nettoyer descriptions
    df['description'] = df['description'].fillna('')
    df['description'] = df['description'].apply(clean_text)

    # 7. Remplir les nulls
    df['salary'] = df['salary'].fillna('Non précisé')
    df['contract_type'] = df['contract_type'].fillna('Non précisé')
    df['experience'] = df['experience'].fillna('Non précisé')
    df['qualification'] = df['qualification'].fillna('Non précisé')
    df['city'] = df['city'].fillna('')
    df['department'] = df['department'].fillna('')

    # 8. Catégorie métier
    df['job_category'] = df['title'].apply(categorize_job)

    print(f"✅ Nettoyage terminé : {len(df)} offres propres")
    return df

def normalize_title(title):
    """Normalise les titres de postes"""
    if pd.isna(title):
        return title
    title = title.strip()
    # Supprimer H/F, F/H, (H/F), etc.
    title = re.sub(r'\b[HhFf]/[HhFf]\b', '', title)
    title = re.sub(r'\([HhFf]/[HhFf]\)', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def clean_text(text):
    """Nettoie le texte des descriptions"""
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

def categorize_job(title):
    """Catégorise le poste"""
    if pd.isna(title):
        return 'Autre'
    title_lower = title.lower()
    if 'engineer' in title_lower or 'ingénieur' in title_lower or 'engineering' in title_lower:
        return 'Data Engineer'
    elif 'scientist' in title_lower or 'science' in title_lower:
        return 'Data Scientist'
    elif 'analyst' in title_lower or 'analyste' in title_lower:
        return 'Data Analyst'
    elif 'architect' in title_lower or 'architecte' in title_lower:
        return 'Data Architect'
    elif 'manager' in title_lower or 'lead' in title_lower:
        return 'Data Manager'
    else:
        return 'Autre'

# ============================================
# SAUVEGARDE
# ============================================
def save_cleaned_data(df):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs_cleaned (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50),
            external_id VARCHAR(255) UNIQUE,
            title TEXT,
            title_normalized TEXT,
            job_category VARCHAR(50),
            company TEXT,
            location TEXT,
            city TEXT,
            department TEXT,
            url TEXT,
            description TEXT,
            contract_type TEXT,
            salary TEXT,
            publication_date DATE,
            qualification TEXT,
            experience TEXT,
            scraped_at TIMESTAMP
        );
    """)

    cur.execute("TRUNCATE TABLE jobs_cleaned CASCADE")

    inserted = 0
    for _, row in df.iterrows():
        try:
            cur.execute("""
                INSERT INTO jobs_cleaned 
                (source, external_id, title, title_normalized, job_category,
                 company, location, city, department, url, description,
                 contract_type, salary, publication_date, qualification,
                 experience, scraped_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (external_id) DO NOTHING
            """, (
                row['source'], row['external_id'], row['title'], row['title'],
                row['job_category'], row['company'], row['location'],
                row['city'], row['department'], row['url'], row['description'],
                row['contract_type'], row['salary'], row['publication_date'],
                row['qualification'], row['experience'], row['scraped_at']
            ))
            inserted += 1
        except Exception as e:
            continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {inserted} offres sauvegardées dans jobs_cleaned")

# ============================================
# RAPPORT
# ============================================
def print_report(df):
    print("\n" + "="*50)
    print("📊 RAPPORT DE NETTOYAGE")
    print("="*50)
    print(f"Total offres : {len(df)}")
    print(f"\n🏷️ Par source :")
    print(df['source'].value_counts().to_string())
    print(f"\n💼 Par catégorie :")
    print(df['job_category'].value_counts().to_string())
    print(f"\n📍 Top 10 villes :")
    print(df['location'].value_counts().head(10).to_string())
    print("="*50)

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    df = load_data()
    df = clean_data(df)
    print_report(df)
    save_cleaned_data(df)
    print("\n🎉 Nettoyage terminé avec succès !")
